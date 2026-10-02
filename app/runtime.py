from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal, DecimalException
from typing import Any

from app.clients.clob_client import ClobClient
from app.clients.gamma_client import GammaClient
from app.clients.geoblock_client import GeoblockClient
from app.clients.http import PublicHTTPClient
from app.clients.websocket_client import MarketWebSocket
from app.config import Settings, validated_scanner_parameters
from app.database import Database
from app.exceptions import InvalidMarketError
from app.models import DepthResult, FeeQuote, FeeStatus, Market, OrderBook, RuntimeStatus
from app.services.catalog import MarketCatalog
from app.services.depth_calculator import calculate_depth
from app.services.market_discovery import normalize_market, parse_list
from app.services.orderbooks import normalize_orderbook
from app.services.quote_freshness import UNKNOWN_QUOTE_AGE, elapsed_seconds, oldest_quote_age, quote_age_seconds
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
        self.calculation_books: dict[str, OrderBook] = {}
        self.results: dict[str, DepthResult] = {}
        self.fee_reasons: dict[str, str] = {}
        self.websocket = MarketWebSocket(settings.websocket_url, self.handle_websocket)
        self._tasks: set[asyncio.Task[None]] = set()
        self._stop = asyncio.Event()
        self._refresh_lock = asyncio.Lock()

    async def start(self) -> None:
        self.settings.ensure_directories()
        self.database.initialize()
        try:
            parameters = validated_scanner_parameters(self.settings, self.database.settings())
            self.settings = self.settings.model_copy(update=parameters)
        except Exception as exc:
            self._record_error("CONFIG", exc)
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
            try:
                await self.catalog.crawl()
                await self.refresh_markets()
                await self.refresh_books_and_scan()
            except Exception as exc:
                self._record_error("CATALOG", exc)
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=600)

    def valid_opportunity(self, market: Market, result: DepthResult) -> bool:
        if self.catalog.is_resolved(market.market_id):
            return False
        refreshed = self.status.last_orderbook_refresh
        if refreshed is None or self.status.clob_status != "正常" or self.status.gamma_status != "正常":
            return False
        books = [self.calculation_books.get(token) for token in market.token_ids]
        age = self._calculation_age(market, result)
        if age is None or not result.executable_quantity.is_finite():
            return False
        if any(
            book is None
            or book.asset_id != token
            or (book.market and book.market != market.condition_id)
            or book.min_order_size is None
            or not book.min_order_size.is_finite()
            or book.min_order_size <= 0
            or result.executable_quantity < book.min_order_size
            for token, book in zip(market.token_ids, books, strict=True)
        ):
            return False
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

    def _calculation_age(self, market: Market, result: DepthResult) -> Decimal | None:
        refreshed = self.status.last_orderbook_refresh
        books = [self.calculation_books.get(token) for token in market.token_ids]
        if refreshed is None or any(book is None for book in books):
            return None
        now = datetime.now(UTC)
        source_age = oldest_quote_age((book.timestamp for book in books if book is not None), now=now)
        if source_age is None or not result.quote_age.is_finite() or result.quote_age < 0:
            return None
        try:
            return max(source_age, result.quote_age + elapsed_seconds(refreshed, now=now))
        except (DecimalException, TypeError, ValueError):
            return None

    async def _market_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.market_refresh_seconds)
            except TimeoutError:
                try:
                    await self.refresh_markets()
                    await self.refresh_books_and_scan()
                    await self.refresh_geoblock()
                except Exception as exc:
                    self._record_error("REST", exc)

    async def _book_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.rest_refresh_seconds)
            except TimeoutError:
                try:
                    await self.refresh_books_and_scan()
                except Exception as exc:
                    self._record_error("REST", exc)

    async def apply_parameters(self, values: dict[str, str]) -> None:
        async with self._refresh_lock:
            parameters = validated_scanner_parameters(self.settings, values)
            self.database.upsert_settings(parameters)
            self.settings = self.settings.model_copy(update=parameters)
            self.results = {}
            self.calculation_books = {}
            self.status.opportunity_count = 0
            self.database.reconcile_opportunities(set(), "参数更新; 等待新盘口")

    async def create_paper_trade(self, market_id: str) -> int:
        async with self._refresh_lock:
            market = self.markets.get(market_id)
            result = self.results.get(market_id)
            if market is None or result is None:
                raise ValueError("没有可追溯的实时订单簿计算结果")
            if any(token not in self.calculation_books for token in market.token_ids):
                raise ValueError("缺少用于该计算的独立 REST 两腿盘口快照")
            if not self.valid_opportunity(market, result):
                raise ValueError("当前快照过期或未通过全部机会门槛; 请刷新盘口")
            return self.database.add_paper_trade(
                market,
                result,
                audit_context=self._audit_context(market, self.calculation_books, self.status.last_orderbook_refresh),
            )

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
        async with self._refresh_lock:
            await self._refresh_markets()

    async def _refresh_markets(self) -> None:
        source_revision: int | None = None
        requested_count = 0
        try:
            if self.catalog.items:
                source_revision = self.catalog.snapshot.revision
                sample = self.catalog.scanner_markets(
                    self.settings.max_markets,
                    minimum_liquidity=Decimal(self.settings.minimum_liquidity),
                    minimum_volume=Decimal(self.settings.minimum_volume),
                )
                previous_by_id = {str(raw["id"]): raw for raw in sample}
                requested_count = len(previous_by_id)
                raw_markets = await self.gamma.fetch_markets_by_ids(list(previous_by_id))
                for raw in raw_markets:
                    sampled = previous_by_id[str(raw["id"])]
                    raw["category"] = sampled.get("category", "")
                    # Settlement identity changes are never borrowed from an
                    # unrelated newer row under the same sampled market ID.
                    if raw.get("conditionId") != sampled.get("conditionId"):
                        raise ValueError("Gamma sampled market condition changed")
                    if parse_list(raw.get("clobTokenIds")) != parse_list(sampled.get("clobTokenIds")) or parse_list(
                        raw.get("outcomes")
                    ) != parse_list(sampled.get("outcomes")):
                        raise ValueError("Gamma sampled market outcome/token order changed")
            else:
                raw_markets = await self.gamma.fetch_markets(self.settings.max_markets)
            next_markets: dict[str, Market] = {}
            skipped = 0
            for raw in raw_markets:
                try:
                    market = normalize_market(raw)
                except InvalidMarketError:
                    skipped += 1
                    continue
                if self.catalog.is_resolved(market.market_id):
                    continue
                if market.liquidity < Decimal(self.settings.minimum_liquidity):
                    continue
                if market.volume < Decimal(self.settings.minimum_volume):
                    continue
                next_markets[market.market_id] = market
                self.database.upsert_market(market)
            self.markets = next_markets
            if source_revision is not None:
                self.catalog.record_scanner_verification(
                    source_revision,
                    {key: market.category for key, market in next_markets.items()},
                    requested_count,
                )
            self.results = {}
            self.calculation_books = {}
            self.status.opportunity_count = 0
            self.status.gamma_status = "正常"
            self.status.active_market_count = len(raw_markets)
            self.status.binary_market_count = len(next_markets)
            self.status.last_market_refresh = datetime.now(UTC)
            tokens = {token for market in next_markets.values() for token in market.token_ids}
            self.books = {token: book for token, book in self.books.items() if token in tokens}
            self.fee_reasons = {}
            self.websocket.set_tokens(tokens)
            self.status.subscribed_tokens = len(tokens)
            self.database.reconcile_opportunities(set(), "市场更新; 等待新盘口")
            self.database.add_event(
                "INFO",
                "REST",
                "markets_refreshed",
                f"读取 {len(raw_markets)}; 可扫描 {len(next_markets)}; 跳过 {skipped}",
            )
        except Exception as exc:
            self.status.gamma_status = f"错误: {type(exc).__name__}"
            self._record_error("REST", exc)
            self.results = {}
            self.calculation_books = {}
            self.status.opportunity_count = 0
            if source_revision is not None:
                self.catalog.record_scanner_verification(source_revision, {}, requested_count, failed=True)
            try:
                self.database.reconcile_opportunities(set(), "市场元数据暂时无法核实")
            except Exception as reconcile_exc:
                self._record_error("DATABASE", reconcile_exc)

    async def refresh_books_and_scan(self) -> None:
        async with self._refresh_lock:
            await self._refresh_books_and_scan()

    async def _refresh_books_and_scan(self) -> None:
        if not self.markets:
            self.results = {}
            self.calculation_books = {}
            self.status.opportunity_count = 0
            self.database.reconcile_opportunities(set(), "当前无可扫描市场")
            return
        try:
            tokens = [token for market in self.markets.values() for token in market.token_ids]
            batch_books = await self.clob.fetch_books(tokens)
            received_at = datetime.now(UTC)
            await self._calculate_and_publish(batch_books, received_at)
            self.status.clob_status = "正常"
        except Exception as exc:
            self.status.clob_status = f"错误: {type(exc).__name__}"
            self._record_error("REST", exc)
            self.results = {}
            self.calculation_books = {}
            self.status.opportunity_count = 0
            try:
                self.database.reconcile_opportunities(set(), "盘口获取或计算失败")
            except Exception as reconcile_exc:
                self._record_error("DATABASE", reconcile_exc)
            return

    async def _calculate_and_publish(self, batch_books: dict[str, OrderBook], received_at: datetime) -> None:
        if self.status.gamma_status != "正常":
            for book in batch_books.values():
                self._store_book(book)
            self.results = {}
            self.calculation_books = {}
            self.status.opportunity_count = 0
            self.status.last_orderbook_refresh = received_at
            self.database.reconcile_opportunities(set(), "市场元数据暂时无法核实")
            return
        new_results: dict[str, DepthResult] = {}
        active_fingerprints: set[str] = set()
        fee_reasons: dict[str, str] = {}
        for market in self.markets.values():
            if self.catalog.is_resolved(market.market_id):
                continue
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
                fee_reasons[market.market_id] = fee.reason
            source_age = oldest_quote_age((yes.timestamp, no.timestamp), now=received_at)
            age = source_age if source_age is not None else UNKNOWN_QUOTE_AGE
            result = calculate_depth(
                yes,
                no,
                Decimal(self.settings.default_quantity),
                fee,
                slippage_rate=Decimal(self.settings.slippage_rate),
                safety_rate=Decimal(self.settings.safety_rate),
                extra_cost=Decimal(self.settings.extra_cost),
                quote_age=age,
                expected_condition_id=market.condition_id,
            )
            minimum = max(yes.min_order_size or Decimal("0"), no.min_order_size or Decimal("0"))
            if result.status in {"VALID", "PARTIAL", "FEE_UNKNOWN"}:
                if source_age is None or age > Decimal(self.settings.max_quote_age_seconds):
                    result.status = "STALE"
                elif yes.min_order_size is None or no.min_order_size is None:
                    result.status = "MIN_ORDER_UNKNOWN"
                elif result.executable_quantity < minimum:
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
                active_fingerprints.add(result.snapshot_fingerprint)
                self.database.upsert_opportunity(
                    market,
                    result,
                    audit_context=self._audit_context(market, batch_books, received_at),
                )
        self.database.reconcile_opportunities(active_fingerprints, "盘口更新或未通过当前门槛")
        for book in batch_books.values():
            self._store_book(book)
        self.results = new_results
        self.calculation_books = dict(batch_books)
        self.fee_reasons = fee_reasons
        self.status.last_orderbook_refresh = received_at
        self.status.opportunity_count = len(active_fingerprints)

    def _audit_context(
        self, market: Market, books: dict[str, OrderBook], received_at: datetime | None
    ) -> dict[str, Any]:
        return {
            "source": "Polymarket public CLOB REST /books",
            "as_of": received_at.isoformat() if received_at else None,
            "market": market.model_dump(mode="json", exclude={"raw"}),
            "parameters": {
                key: getattr(self.settings, key)
                for key in (
                    "default_quantity",
                    "slippage_rate",
                    "safety_rate",
                    "extra_cost",
                    "minimum_executable_quantity",
                    "minimum_net_profit",
                    "minimum_net_roi",
                    "max_quote_age_seconds",
                )
            },
            "orderbooks": [books[token].model_dump(mode="json") for token in market.token_ids if token in books],
        }

    def _store_book(self, book: OrderBook) -> None:
        if book.asset_id not in self.websocket.tokens:
            return
        previous = self.books.get(book.asset_id)
        if previous is not None:
            now = datetime.now(UTC)
            previous_age = quote_age_seconds(previous.timestamp, now=now)
            incoming_age = quote_age_seconds(book.timestamp, now=now)
            if previous_age is not None and (incoming_age is None or incoming_age > previous_age):
                return
        self.books[book.asset_id] = book

    async def handle_websocket(self, payload: dict[str, Any]) -> None:
        self.status.websocket_status = "已连接"
        self.status.websocket_messages = self.websocket.messages
        self.status.last_websocket_message = datetime.now(UTC)
        event_type = payload.get("event_type")
        if event_type == "book":
            book = normalize_orderbook(payload)
            self._store_book(book)
        elif event_type == "market_resolved":
            await self._handle_resolution(payload)

    async def _handle_resolution(self, payload: dict[str, Any]) -> None:
        market_id = payload.get("id")
        market = self.markets.get(market_id) if isinstance(market_id, str) else None
        assets = payload.get("assets_ids")
        if (
            market is None
            or payload.get("market") != market.condition_id
            or not isinstance(assets, list)
            or any(not isinstance(asset, str) for asset in assets)
            or set(assets) != set(market.token_ids)
            or payload.get("winning_asset_id") not in market.token_ids
        ):
            return
        # Record the terminal state before awaiting the current REST refresh.
        # A later discovery publication must not resurrect this known ID.
        self.catalog.exclude_resolved(market.market_id)
        async with self._refresh_lock:
            self.markets = {key: value for key, value in self.markets.items() if key != market.market_id}
            self.results = {key: value for key, value in self.results.items() if key != market.market_id}
            self.fee_reasons.pop(market.market_id, None)
            tokens = {token for active in self.markets.values() for token in active.token_ids}
            self.books = {token: book for token, book in self.books.items() if token in tokens}
            self.calculation_books = {token: book for token, book in self.calculation_books.items() if token in tokens}
            self.websocket.set_tokens(tokens)
            self.status.subscribed_tokens = len(tokens)
            self.status.binary_market_count = len(self.markets)
            self.status.active_market_count = len(self.markets)
            valid = {
                result.snapshot_fingerprint
                for key, result in self.results.items()
                if self.valid_opportunity(self.markets[key], result)
            }
            self.status.opportunity_count = len(valid)
            self.database.reconcile_opportunities(valid, "公开市场已结算或不再满足门槛")

    def _record_error(self, source: str, exc: Exception) -> None:
        message = f"{type(exc).__name__}: {str(exc)[:300]}"
        self.status.recent_error = message
        logger.error("runtime operation failed", extra={"event": source.lower(), "error_type": type(exc).__name__})
        try:
            self.database.add_event("ERROR", source, "operation_failed", message)
        except Exception as logging_exc:
            logger.error(
                "runtime error could not be persisted",
                extra={"event": "event_write_failed", "error_type": type(logging_exc).__name__},
            )

    def market_payload(self, market: Market) -> dict[str, Any]:
        payload = market.model_dump(mode="json", exclude={"raw"})
        result = self.results.get(market.market_id)
        payload["calculation"] = result.model_dump(mode="json") if result else None
        if result:
            age = self._calculation_age(market, result)
            payload["calculation"]["quote_age"] = str(age if age is not None else UNKNOWN_QUOTE_AGE)
            if result.status in {"VALID", "PARTIAL", "FEE_UNKNOWN"} and (
                age is None or age > Decimal(self.settings.max_quote_age_seconds)
            ):
                payload["calculation"]["status"] = "STALE"
        payload["is_candidate"] = bool(result and self.valid_opportunity(market, result))
        payload["fee_reason"] = self.fee_reasons.get(market.market_id)
        return payload
