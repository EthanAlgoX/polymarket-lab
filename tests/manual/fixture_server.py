"""Serve isolated [TEST] data for browser acceptance checks; never contact providers.

Run from the repository directory with the project's Python:
    .venv/bin/python tests/manual/fixture_server.py --port 8128

Cases 101..108 cover a positive candidate, unknown fees/minimum size, crossed and
stale books, a now-closed market, three outcomes, and Up/Down. Forty extra catalog
rows and 101 preloaded paper/history rows exercise pagination. All databases and
translation caches are temporary and removed after shutdown.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import uvicorn
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
# Prevent app.main's normal logger from creating a persistent fixture log file.
logging.basicConfig(level=logging.INFO)

from app.config import Settings  # noqa: E402
from app.database import OpportunityRow, PaperTradeRow  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Market, OrderBook  # noqa: E402
from app.runtime import ScannerRuntime  # noqa: E402
from app.services.orderbooks import normalize_orderbook  # noqa: E402
from app.services.translation import DeepSeekTranslator, TranslationService  # noqa: E402

RULES = (
    "[TEST] Synthetic public test rules: deadline 2030-12-31 23:59 UTC. "
    "A value ≥ 100 resolves Yes; otherwise No. Two outcomes pay $1 in total. "
    "Source URL https://example.com/test-settlement . This is local fixture data only."
)
CASE_NAMES = {
    "101": "Positive complete Yes/No pair",
    "102": "Unknown fee schedule",
    "103": "Unknown minimum order size",
    "104": "Crossed orderbook",
    "105": "Invalid zero snapshot timestamp",
    "106": "Catalog open, current Gamma closed",
    "107": "Three outcomes, descriptive books only",
    "108": "Up/Down pair, outside Yes/No scanner",
}
CASE_CATEGORIES = ("sports", "crypto", "weather", "economy", "politics", "other", "sports", "crypto")


class FixtureRuntime(ScannerRuntime):
    def _audit_context(
        self, market: Market, books: dict[str, OrderBook], received_at: datetime | None
    ) -> dict[str, Any]:
        context = super()._audit_context(market, books, received_at)
        context["source"] = "[TEST] local synthetic CLOB /books stub; no external request"
        context["fixture"] = True
        return context


def raw_market(market_id: str, *, outcomes: list[str] | None = None) -> dict[str, Any]:
    labels = outcomes or ["Yes", "No"]
    return {
        "id": market_id,
        "conditionId": f"test-condition-{market_id}",
        "question": f"[TEST] {market_id} {CASE_NAMES.get(market_id, 'Catalog pagination row')}",
        "slug": f"test-only-{market_id}",
        "description": RULES,
        "outcomes": labels,
        "outcomePrices": ["0.4" for _ in labels],
        "clobTokenIds": [f"test-token-{market_id}-{index}" for index in range(len(labels))],
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "liquidityNum": "10000",
        "volumeNum": "20000",
        "volume24hr": "100000" if market_id in CASE_NAMES else "1",
        "feesEnabled": False,
        "createdAt": "2026-01-01T00:00:00Z",
        "endDate": "2030-12-31T23:59:00Z",
        "negRisk": False,
    }


def build_markets() -> dict[str, dict[str, Any]]:
    markets = {market_id: raw_market(market_id) for market_id in CASE_NAMES}
    markets["102"]["feesEnabled"] = True
    markets["107"] = raw_market("107", outcomes=["[TEST] Alpha", "[TEST] Beta", "[TEST] Gamma"])
    markets["108"] = raw_market("108", outcomes=["Up", "Down"])
    for index in range(201, 241):
        key = str(index)
        markets[key] = raw_market(key, outcomes=["[TEST] A", "[TEST] B", "[TEST] C"])
    return markets


def seed_catalog(runtime: FixtureRuntime, markets: dict[str, dict[str, Any]]) -> None:
    events = []
    for index, (market_id, raw) in enumerate(markets.items()):
        category = CASE_CATEGORIES[index] if index < len(CASE_CATEGORIES) else "other"
        events.append(
            {
                "id": f"test-event-{market_id}",
                "title": f"[TEST] Event {market_id}",
                "slug": f"test-event-{market_id}",
                "tags": [{"slug": category, "label": f"[TEST] {category}"}],
                "markets": [raw],
            }
        )
    items: dict[str, dict[str, Any]] = {}
    originals: dict[str, dict[str, Any]] = {}
    runtime.catalog.ingest(events, items, originals)
    runtime.catalog._publish(items, originals, "sample")


def install_stubs(runtime: FixtureRuntime, markets: dict[str, dict[str, Any]]) -> None:
    token_rows = {token: (market_id, raw) for market_id, raw in markets.items() for token in raw["clobTokenIds"]}

    async def no_external_request(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("[TEST] fixture must not send an external HTTP request")

    async def current_markets(market_ids: list[str]) -> list[dict[str, Any]]:
        rows = []
        for market_id in market_ids:
            if market_id in markets:
                row = dict(markets[market_id])
                if market_id == "106":
                    row.update(closed=True, acceptingOrders=False)
                rows.append(row)
        return rows

    async def current_books(token_ids: list[str]) -> dict[str, OrderBook]:
        timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
        books = {}
        for token in dict.fromkeys(token_ids):
            if token not in token_rows:
                continue
            market_id, raw = token_rows[token]
            payload = {
                "asset_id": token,
                "market": raw["conditionId"],
                "timestamp": "0" if market_id == "105" else timestamp,
                "hash": f"test-book-{token}-{timestamp}",
                "bids": [{"price": "0.6" if market_id == "104" else "0.39", "size": "1000"}],
                "asks": [{"price": "0.4", "size": "1000"}],
                "tick_size": "0.01",
                "min_order_size": "5" if market_id != "103" else None,
                "last_trade_price": "0.4",
            }
            books[token] = normalize_orderbook(payload)
        return books

    runtime.http.request_json = no_external_request  # type: ignore[method-assign]
    runtime.gamma.fetch_markets_by_ids = current_markets  # type: ignore[method-assign]
    runtime.clob.fetch_books = current_books  # type: ignore[method-assign]


def seed_records(runtime: FixtureRuntime) -> None:
    result = runtime.results["101"]
    market = runtime.markets["101"]
    payload = result.model_dump(mode="json")
    payload["audit"] = runtime._audit_context(market, runtime.calculation_books, runtime.status.last_orderbook_refresh)
    payload_json = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    base = datetime.now(UTC) - timedelta(days=1)
    with runtime.database.Session.begin() as session:
        for index in range(101):
            observed = base + timedelta(seconds=index)
            title = f"[TEST] Preloaded simulation/history {index + 1:03d}"
            session.add(
                PaperTradeRow(
                    created_at=observed,
                    market_id="101",
                    market_question=title,
                    target_quantity=str(result.target_quantity),
                    executable_quantity=str(result.executable_quantity),
                    total_cost=str(result.total_cost),
                    net_profit=str(result.net_profit),
                    net_roi=str(result.net_roi),
                    status="SUCCESS",
                    trigger_type="fixture",
                    data_source="[TEST] synthetic local fixture",
                    payload_json=payload_json,
                )
            )
            session.add(
                OpportunityRow(
                    fingerprint=hashlib.sha256(f"test-preloaded-{index}".encode()).hexdigest(),
                    market_id="101",
                    question=title,
                    status="disappeared",
                    first_seen=observed,
                    last_seen=observed,
                    initial_net_profit=str(result.net_profit),
                    max_net_profit=str(result.net_profit),
                    min_net_profit=str(result.net_profit),
                    max_net_roi=str(result.net_roi),
                    max_quantity=str(result.executable_quantity),
                    payload_json=payload_json,
                    disappeared_reason="[TEST] preloaded historical observation, not current",
                )
            )
    runtime.database.add_event("INFO", "[TEST]", "fixture_ready", "[TEST] No external providers or paid translation")


@asynccontextmanager
async def fixture_lifespan(application: FastAPI) -> AsyncIterator[None]:
    with TemporaryDirectory(prefix="polymarket-ui-fixture-") as directory:
        root = Path(directory)
        settings = Settings(
            _env_file=None,
            enable_live_scanner=False,
            database_url=f"sqlite:///{root / 'scanner.sqlite3'}",
            default_quantity="10",
            minimum_liquidity="0",
            minimum_volume="0",
            minimum_executable_quantity="1",
            minimum_net_profit="0.10",
            minimum_net_roi="0.002",
            slippage_rate="0",
            safety_rate="0",
            extra_cost="0",
            max_quote_age_seconds=5,
            max_markets=8,
        )
        runtime = FixtureRuntime(settings)
        application.state.runtime = runtime
        translations = TranslationService(
            root / "translations.sqlite3", DeepSeekTranslator("", api_base="https://api.deepseek.com")
        )
        application.state.translations = translations
        refresh_task: asyncio.Task[None] | None = None
        try:
            await runtime.start()
            markets = build_markets()
            install_stubs(runtime, markets)
            seed_catalog(runtime, markets)
            runtime.status.geoblock_status = "[TEST] Disabled: synthetic data only"
            await runtime.refresh_markets()
            await runtime.refresh_books_and_scan()
            assert runtime.valid_opportunity(runtime.markets["101"], runtime.results["101"])
            seed_records(runtime)
            await translations.start()

            async def keep_quotes_fresh() -> None:
                while True:
                    await asyncio.sleep(1)
                    await runtime.refresh_books_and_scan()

            refresh_task = asyncio.create_task(keep_quotes_fresh(), name="fixture-quotes")
            yield
        finally:
            if refresh_task is not None:
                refresh_task.cancel()
                await asyncio.gather(refresh_task, return_exceptions=True)
            await translations.close()
            await runtime.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="[TEST] isolated local UI fixture server, no external requests")
    parser.add_argument("--port", type=int, default=8128)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.port == 8000:
        parser.error("Port 8000 is reserved for the real application; choose a separate fixture port")
    app.router.lifespan_context = fixture_lifespan
    print(f"[TEST] Synthetic fixture only: http://127.0.0.1:{args.port} | temporary DB | no paid translation")
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
