from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.clients.clob_client import ClobClient
from app.clients.gamma_client import GammaClient
from app.clients.geoblock_client import GeoblockClient
from app.clients.http import PublicHTTPClient
from app.clients.websocket_client import MarketWebSocket
from app.config import Settings
from app.database import Database
from app.exceptions import InvalidMarketError
from app.models import DepthResult, FeeQuote, FeeStatus, Market, OrderBook, RuntimeStatus
from app.services.catalog import MarketCatalog
from app.services.depth_calculator import calculate_depth
from app.services.market_discovery import normalize_market
from app.services.orderbooks import normalize_orderbook
from app.services.scanner import is_valid_opportunity

logger = logging.getLogger(__name__)


class ScannerRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = PublicHTTPClient(settings.request_timeout, settings.user_agent, settings.max_concurrency)
        self.gamma = GammaClient(self.http, settings.gamma_url)
        self.catalog = MarketCatalog(self.http, settings.gamma_url)
        self.clob = ClobClient(self.http, settings.clob_url)
        self.geoblock = GeoblockClient(self.http, settings.geoblock_url)
        self.database = Database(settings.database_url)
        self.status = RuntimeStatus(started_at=datetime.now(UTC))
        self.markets: dict[str, Market] = {}
        self.books: dict[str, OrderBook] = {}
        self.results: dict[str, DepthResult] = {}
        self.fee_reasons: dict[str, str] = {}
        self.websocket = MarketWebSocket(settings.websocket_url, self.handle_websocket)
        self._tasks: set[asyncio.Task[None]] = set()
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self.settings.ensure_directories()
        self.database.initialize()
        if not self.settings.enable_live_scanner:
            return
        await self.refresh_geoblock()
        try:
            await self.catalog.seed()
        except Exception as exc:
            self._record_error("CATALOG", exc)
        await self.refresh_markets()
        if self.markets:
            await self.refresh_books_and_scan()
        self.websocket.set_tokens({token for market in self.markets.values() for token in market.token_ids})
        self._tasks = {
            asyncio.create_task(self._catalog_loop(), name="catalog-refresh"),
            asyncio.create_task(self._market_loop(), name="market-refresh"),
            asyncio.create_task(self._book_loop(), name="book-refresh"),
            asyncio.create_task(self.websocket.run(), name="market-websocket"),
        }

    async def stop(self) -> None:
        self._stop.set()
        await self.websocket.stop()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.http.close()
        self.database.close()

    async def _catalog_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.catalog.seed()
            except Exception as exc:
                self._record_error("CATALOG", exc)
            await self.catalog.crawl()
            await self.refresh_markets()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=600)

    def valid_opportunity(self, market: Market, result: DepthResult) -> bool:
        refreshed = self.status.last_orderbook_refresh
        if refreshed is None or self.status.clob_status != "正常":
            return False
        age = result.quote_age + Decimal(str(max(0, (datetime.now(UTC) - refreshed).total_seconds())))
        check = result.model_copy(update={"quote_age": age})
        valid, _ = is_valid_opportunity(
            market,
            check,
            min_quantity=Decimal(self.settings.minimum_executable_quantity),
            min_profit=Decimal(self.settings.minimum_net_profit),
            min_roi=Decimal(self.settings.minimum_net_roi),
            max_quote_age=Decimal(self.settings.max_quote_age_seconds),
        )
        return valid

    async def _market_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.market_refresh_seconds)
            except TimeoutError:
                await self.refresh_markets()
                await self.refresh_geoblock()

    async def _book_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.rest_refresh_seconds)
            except TimeoutError:
                await self.refresh_books_and_scan()

    async def refresh_geoblock(self) -> None:
        try:
            geo = await self.geoblock.check()
            self.status.geoblock_status = (
                f"受限 ({geo['country']}/{geo['region']})" if geo["blocked"] else f"未受限 ({geo['country']})"
            )
        except Exception as exc:
            self.status.geoblock_status = f"检查失败: {type(exc).__name__}"
            self._record_error("GEOBLOCK", exc)
        self.status.geoblock_checked_at = datetime.now(UTC)

    async def refresh_markets(self) -> None:
        try:
            raw_markets = (
                self.catalog.scanner_markets(self.settings.max_markets)
                if self.catalog.items
                else await self.gamma.fetch_markets(self.settings.max_markets)
            )
            next_markets: dict[str, Market] = {}
            skipped = 0
            for raw in raw_markets:
                try:
                    market = normalize_market(raw)
                except InvalidMarketError:
                    skipped += 1
                    continue
                if market.liquidity < Decimal(self.settings.minimum_liquidity):
                    continue
                next_markets[market.market_id] = market
                self.database.upsert_market(market)
            self.markets = next_markets
            self.status.gamma_status = "正常"
            self.status.active_market_count = len(raw_markets)
            self.status.binary_market_count = len(next_markets)
            self.status.last_market_refresh = datetime.now(UTC)
            tokens = {token for market in next_markets.values() for token in market.token_ids}
            self.websocket.set_tokens(tokens)
            self.status.subscribed_tokens = len(tokens)
            self.database.add_event(
                "INFO",
                "REST",
                "markets_refreshed",
                f"读取 {len(raw_markets)}; 可扫描 {len(next_markets)}; 跳过 {skipped}",
            )
        except Exception as exc:
            self.status.gamma_status = f"错误: {type(exc).__name__}"
            self._record_error("REST", exc)

    async def refresh_books_and_scan(self) -> None:
        if not self.markets:
            return
        try:
            tokens = [token for market in self.markets.values() for token in market.token_ids]
            batch_books = await self.clob.fetch_books(tokens)
            received_at = datetime.now(UTC)
            self.books.update(batch_books)
            self.status.clob_status = "正常"
        except Exception as exc:
            self.status.clob_status = f"错误: {type(exc).__name__}"
            self._record_error("REST", exc)
            self.results = {}
            self.status.opportunity_count = 0
            return
        new_results: dict[str, DepthResult] = {}
        valid_count = 0
        for market in self.markets.values():
            yes = batch_books.get(market.yes_token_id)
            no = batch_books.get(market.no_token_id)
            if yes is None or no is None:
                continue
            if market.fees_enabled is False:
                fee = FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0"))
            elif market.fee_rate is not None:
                fee = FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=market.fee_rate * Decimal("1000"))
            else:
                fee = FeeQuote(status=FeeStatus.UNKNOWN, reason="未核实当前费率公式")
            if fee.reason:
                self.fee_reasons[market.market_id] = fee.reason
            try:
                snapshot_at = min(float(yes.timestamp), float(no.timestamp)) / 1000
                age = Decimal(str(max(0, received_at.timestamp() - snapshot_at)))
            except (ValueError, TypeError):
                age = Decimal("999999")
            result = calculate_depth(
                yes,
                no,
                Decimal(self.settings.default_quantity),
                fee,
                slippage_rate=Decimal(self.settings.slippage_rate),
                safety_rate=Decimal(self.settings.safety_rate),
                extra_cost=Decimal(self.settings.extra_cost),
                quote_age=age,
            )
            minimum = max(yes.min_order_size or Decimal("0"), no.min_order_size or Decimal("0"))
            if result.executable_quantity < minimum:
                result.status = "BELOW_MIN_ORDER"
            new_results[market.market_id] = result
            valid, _ = is_valid_opportunity(
                market,
                result,
                min_quantity=Decimal(self.settings.minimum_executable_quantity),
                min_profit=Decimal(self.settings.minimum_net_profit),
                min_roi=Decimal(self.settings.minimum_net_roi),
                max_quote_age=Decimal(self.settings.max_quote_age_seconds),
            )
            if valid:
                valid_count += 1
                self.database.upsert_opportunity(market, result)
        self.results = new_results
        self.status.last_orderbook_refresh = received_at
        self.status.opportunity_count = valid_count

    async def handle_websocket(self, payload: dict[str, Any]) -> None:
        self.status.websocket_status = "已连接"
        self.status.websocket_messages = self.websocket.messages
        self.status.last_websocket_message = datetime.now(UTC)
        event_type = payload.get("event_type")
        if event_type == "book":
            book = normalize_orderbook(payload)
            if book.asset_id:
                self.books[book.asset_id] = book

    def _record_error(self, source: str, exc: Exception) -> None:
        message = f"{type(exc).__name__}: {str(exc)[:300]}"
        self.status.recent_error = message
        logger.error("runtime operation failed", extra={"event": source.lower(), "error_type": type(exc).__name__})
        self.database.add_event("ERROR", source, "operation_failed", message)

    def market_payload(self, market: Market) -> dict[str, Any]:
        payload = market.model_dump(mode="json", exclude={"raw"})
        result = self.results.get(market.market_id)
        payload["calculation"] = result.model_dump(mode="json") if result else None
        if result and self.status.last_orderbook_refresh:
            payload["calculation"]["quote_age"] = str(
                result.quote_age
                + Decimal(str(max(0, (datetime.now(UTC) - self.status.last_orderbook_refresh).total_seconds())))
            )
        payload["is_candidate"] = bool(result and self.valid_opportunity(market, result))
        payload["fee_reason"] = self.fee_reasons.get(market.market_id)
        return payload
