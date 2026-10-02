from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.config import Settings
from app.models import OrderBook, PriceLevel
from app.runtime import ScannerRuntime
from app.services.market_discovery import normalize_market
from app.services.quote_freshness import UNKNOWN_QUOTE_AGE, elapsed_seconds, oldest_quote_age, quote_age_seconds

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
NOW_MILLISECONDS = Decimal(int(NOW.timestamp()) * 1000)


@pytest.mark.parametrize("timestamp", [None, "", "not-a-time", "NaN", "Infinity", "-Infinity", "0", "-1", "1e1000000"])
def test_missing_invalid_or_nonfinite_timestamp_is_unknown(timestamp: str | None) -> None:
    assert quote_age_seconds(timestamp, now=NOW) is None


def test_future_clock_tolerance_is_bounded_and_fractional_age_is_exact() -> None:
    assert quote_age_seconds(str(NOW_MILLISECONDS + Decimal("1000")), now=NOW) == Decimal("0")
    assert quote_age_seconds(str(NOW_MILLISECONDS + Decimal("1000.000001")), now=NOW) is None
    assert quote_age_seconds(str(NOW_MILLISECONDS - Decimal("0.123456789")), now=NOW) == Decimal("0.000123456789")
    assert elapsed_seconds(NOW - timedelta(microseconds=123456), now=NOW) == Decimal("0.123456")
    assert elapsed_seconds(NOW + timedelta(seconds=1), now=NOW) == Decimal("0")


def test_pair_age_uses_oldest_source_and_rejects_any_unknown_leg() -> None:
    recent, old = str(NOW_MILLISECONDS - Decimal("250")), str(NOW_MILLISECONDS - Decimal("2000"))
    assert oldest_quote_age((recent, old), now=NOW) == Decimal("2")
    assert oldest_quote_age((old, recent), now=NOW) == Decimal("2")
    assert oldest_quote_age((old, "NaN"), now=NOW) is None
    assert oldest_quote_age(("Infinity", recent), now=NOW) is None
    assert oldest_quote_age((), now=NOW) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bad_timestamp", "max_age"),
    [("NaN", 5), ("Infinity", 5), ("9999999999999", 5), ("", 5), ("0", 5), ("NaN", 1000000)],
)
async def test_runtime_invalid_source_time_cannot_create_zero_fee_candidate(
    bad_timestamp: str, max_age: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = ScannerRuntime(Settings(enable_live_scanner=False, database_url=f"sqlite:///{tmp_path / 'freshness.db'}"))
    runtime.database.initialize()
    # Even an internally overridden threshold above the display sentinel must
    # never change unknown source time into an eligible quote.
    runtime.settings.max_quote_age_seconds = max_age
    market = normalize_market(
        {
            "id": "1",
            "conditionId": "condition",
            "question": "Question?",
            "outcomes": ["Yes", "No"],
            "clobTokenIds": ["yes", "no"],
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "enableOrderBook": True,
            "feesEnabled": False,
        }
    )
    runtime.markets = {"1": market}
    fresh_timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
    books = {
        token: OrderBook(
            asset_id=token,
            timestamp=timestamp,
            asks=[PriceLevel(price=Decimal("0.4"), size=Decimal("100"))],
        )
        for token, timestamp in (("yes", bad_timestamp), ("no", fresh_timestamp))
    }

    async def fetch_books(tokens: list[str]) -> dict[str, OrderBook]:
        assert tokens == ["yes", "no"]
        return books

    monkeypatch.setattr(runtime.clob, "fetch_books", fetch_books)
    try:
        await runtime.refresh_books_and_scan()
        result = runtime.results["1"]
        assert result.status == "STALE"
        assert result.quote_age == UNKNOWN_QUOTE_AGE
        assert result.estimated_fees == Decimal("0")
        assert result.net_profit is not None and result.net_profit > 0
        assert not runtime.valid_opportunity(market, result)
        assert runtime.status.opportunity_count == 0
    finally:
        await runtime.stop()
