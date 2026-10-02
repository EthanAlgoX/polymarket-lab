from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.models import DepthResult, FeeQuote, FeeStatus, Market, OrderBook, PriceLevel
from app.runtime import ScannerRuntime
from app.services.depth_calculator import calculate_depth
from app.services.market_discovery import normalize_market

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def install_pair(runtime: ScannerRuntime, identifier: str) -> tuple[Market, DepthResult]:
    market = normalize_market(
        {
            "id": identifier,
            "conditionId": f"condition-{identifier}",
            "question": f"Public market {identifier}?",
            "outcomes": ["Yes", "No"],
            "clobTokenIds": [f"yes-{identifier}", f"no-{identifier}"],
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "enableOrderBook": True,
            "feesEnabled": False,
        }
    )
    books = [
        OrderBook(
            asset_id=token,
            market=market.condition_id,
            timestamp=str(int(NOW.timestamp() * 1000)),
            min_order_size=Decimal("1"),
            asks=[PriceLevel(price=Decimal("0.4"), size=Decimal("100"))],
        )
        for token in market.token_ids
    ]
    result = calculate_depth(
        books[0], books[1], Decimal("10"), FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0"))
    )
    runtime.markets[identifier] = market
    runtime.results[identifier] = result
    runtime.calculation_books.update({book.asset_id: book for book in books})
    return market, result


@pytest.mark.asyncio
async def test_diagnostics_partition_every_selected_market_by_current_gate(tmp_path):
    runtime = ScannerRuntime(
        Settings(_env_file=None, enable_live_scanner=False, database_url=f"sqlite:///{tmp_path / 'audit.db'}")
    )
    await runtime.start()
    runtime.status.gamma_status = runtime.status.clob_status = "正常"
    runtime.status.last_orderbook_refresh = NOW
    try:
        install_pair(runtime, "eligible")
        install_pair(runtime, "pending")
        runtime.results.pop("pending")
        _, no_edge = install_pair(runtime, "no-edge")
        no_edge.net_profit = Decimal("-1")
        _, fee_unknown = install_pair(runtime, "fees")
        fee_unknown.fee_status = FeeStatus.UNKNOWN
        fee_unknown.estimated_fees = None
        _, partial = install_pair(runtime, "partial")
        partial.status = "PARTIAL"
        partial.partial_fill = True
        minimum_market, _ = install_pair(runtime, "minimum")
        runtime.calculation_books[minimum_market.yes_token_id].min_order_size = None
        unknown_market, _ = install_pair(runtime, "unknown-time")
        runtime.calculation_books[unknown_market.yes_token_id].timestamp = "NaN"
        stale_market, _ = install_pair(runtime, "stale")
        runtime.calculation_books[stale_market.no_token_id].timestamp = str(int((NOW.timestamp() - 6) * 1000))
        crossed_market, _ = install_pair(runtime, "crossed")
        crossed_yes = runtime.calculation_books[crossed_market.yes_token_id]
        crossed_yes.bids = [PriceLevel(price=Decimal("0.6"), size=Decimal("10"))]
        runtime.results["crossed"] = calculate_depth(
            crossed_yes,
            runtime.calculation_books[crossed_market.no_token_id],
            Decimal("10"),
            FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0")),
        )
        assert runtime.results["crossed"].executable_quantity == 0

        payload = runtime.scanner_diagnostics(now=NOW)
        assert payload["selected_count"] == 9
        assert payload["calculated_count"] == 8
        assert payload["candidate_count"] == 1
        assert payload["rejected_count"] == 8
        assert payload["reason_counts"] == {
            "AWAITING_CALCULATION": 1,
            "BELOW_NET_PROFIT": 1,
            "CROSSED_BOOK": 1,
            "FEE_UNKNOWN": 1,
            "MIN_ORDER_UNKNOWN": 1,
            "PARTIAL": 1,
            "QUOTE_TIME_UNKNOWN": 1,
            "STALE": 1,
        }
        assert sum(payload["reason_counts"].values()) + payload["candidate_count"] == payload["selected_count"]
        assert payload["calculation_as_of"] == payload["checked_at"] == NOW.isoformat()
        assert payload["thresholds"]["max_quote_age_seconds"] == "5"
        assert payload["candidate_count"] == sum(
            runtime.valid_opportunity(market, runtime.results[mid], now=NOW)
            for mid, market in runtime.markets.items()
            if mid in runtime.results
        )
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_diagnostics_never_treat_receipt_time_as_source_quote_freshness(tmp_path):
    runtime = ScannerRuntime(
        Settings(_env_file=None, enable_live_scanner=False, database_url=f"sqlite:///{tmp_path / 'age.db'}")
    )
    await runtime.start()
    runtime.status.gamma_status = runtime.status.clob_status = "正常"
    runtime.status.last_orderbook_refresh = NOW
    try:
        install_pair(runtime, "pair")
        assert runtime.scanner_diagnostics(now=NOW)["candidate_count"] == 1
        later = NOW + timedelta(seconds=6)
        # Refetching a source snapshot does not change its source timestamp.
        runtime.status.last_orderbook_refresh = later
        payload = runtime.scanner_diagnostics(now=later)
        assert payload["calculation_as_of"] == payload["checked_at"] == later.isoformat()
        assert payload["candidate_count"] == 0
        assert payload["reason_counts"] == {"STALE": 1}
        runtime.status.gamma_status = "错误: PublicHTTPError"
        assert runtime.scanner_diagnostics(now=later)["reason_counts"] == {"METADATA_UNVERIFIED": 1}
    finally:
        await runtime.stop()


def test_opportunity_api_returns_one_current_age_and_matching_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setattr("app.main.deepseek_key", lambda: "")
    monkeypatch.setattr("app.main.LLM_CONFIG_PATH", tmp_path / "llm-config.json")

    class FrozenTime:
        @staticmethod
        def now(timezone):
            return NOW + timedelta(seconds=2)

    with TestClient(app) as client:
        runtime = app.state.runtime
        runtime.status.gamma_status = runtime.status.clob_status = "正常"
        runtime.status.last_orderbook_refresh = NOW
        _, original = install_pair(runtime, "pair")
        assert original.quote_age == Decimal("0")
        monkeypatch.setattr("app.main.datetime", FrozenTime)
        monkeypatch.setattr("app.runtime.datetime", FrozenTime)
        payload = client.get("/api/opportunities").json()
        assert payload["total"] == payload["scanner_diagnostics"]["candidate_count"] == 1
        item = payload["items"][0]
        assert item["calculation"] == item["market"]["calculation"]
        assert item["calculation"]["quote_age"] == "2"
        assert original.quote_age == Decimal("0")
        status = client.get("/api/system/status").json()
        assert status["opportunity_count"] == status["scanner_diagnostics"]["candidate_count"] == 1
