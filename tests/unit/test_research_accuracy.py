from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import Settings
from app.models import FeeQuote, FeeStatus, OrderBook, PriceLevel
from app.runtime import ScannerRuntime
from app.services.catalog import MarketCatalog, category_for
from app.services.depth_calculator import calculate_depth
from app.services.market_discovery import normalize_market


def market_raw(**changes):
    raw = {
        "id": "1",
        "conditionId": "c",
        "question": "Q",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": ["a", "b"],
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "feesEnabled": True,
    }
    return {**raw, **changes}


def book(token, levels):
    return OrderBook(asset_id=token, asks=[PriceLevel(price=Decimal(p), size=Decimal(q)) for p, q in levels])


def test_fee_is_per_consumed_level_and_roi_uses_full_budget():
    fee = FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("70"))
    result = calculate_depth(
        book("a", [("0.1", "50"), ("0.9", "50")]),
        book("b", [("0.1", "100")]),
        Decimal("100"),
        fee,
        slippage_rate=Decimal("0"),
        safety_rate=Decimal("0"),
        extra_cost=Decimal("1"),
    )
    assert result.estimated_fees == Decimal("1.26")
    assert result.net_profit == Decimal("37.74")
    assert result.net_roi == Decimal("37.74") / Decimal("62.26")


@pytest.mark.parametrize("schedule", [{"rate": "garbage"}, {"rate": "NaN"}, {"rate": "0.07", "exponent": 0}])
def test_bad_fee_is_unknown(schedule):
    assert normalize_market(market_raw(feeSchedule=schedule)).fee_rate is None


def test_climate_science_does_not_make_an_ipo_weather():
    assert (
        category_for({"title": "Largest IPO", "tags": [{"slug": "climate-science"}, {"slug": "finance"}]}) == "economy"
    )


@pytest.mark.asyncio
async def test_schema_error_never_claims_catalog_complete():
    class BadHTTP:
        async def request_json(self, *args, **kwargs):
            return {"unexpected": True}

    catalog = MarketCatalog(BadHTTP(), "https://example.test")
    catalog.items["keep"] = {"id": "keep"}
    await catalog.crawl()
    assert catalog.coverage == "partial"
    assert "keep" in catalog.items
    assert catalog.error is not None


@pytest.mark.asyncio
async def test_stale_profitable_snapshot_is_not_a_candidate(tmp_path):
    rt = ScannerRuntime(Settings(enable_live_scanner=False, database_url=f"sqlite:///{tmp_path / 'r.db'}"))
    m = normalize_market(market_raw())
    result = calculate_depth(
        book("a", [(".4", "10")]),
        book("b", [(".4", "10")]),
        Decimal("10"),
        FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0")),
    )
    rt.status.clob_status = "正常"
    rt.status.last_orderbook_refresh = datetime.now(UTC) - timedelta(seconds=60)
    assert result.net_profit > 0
    assert not rt.valid_opportunity(m, result)
    await rt.http.close()
    rt.database.close()
