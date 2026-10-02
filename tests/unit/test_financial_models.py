from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import FeeQuote, FeeStatus, OrderBook, PriceLevel
from app.services.market_discovery import normalize_market


@pytest.mark.parametrize(
    ("price", "size"), [("-0.1", "1"), ("1.1", "1"), ("NaN", "1"), ("0.5", "0"), ("0.5", "-1"), ("0.5", "Infinity")]
)
def test_price_levels_reject_invalid_financial_fields(price: str, size: str) -> None:
    with pytest.raises(ValidationError):
        PriceLevel(price=Decimal(price), size=Decimal(size))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tick_size", "0"),
        ("tick_size", "1.1"),
        ("min_order_size", "-1"),
        ("last_trade_price", "-0.1"),
        ("last_trade_price", "Infinity"),
    ],
)
def test_orderbook_metadata_has_financial_bounds(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        OrderBook(asset_id="x", **{field: Decimal(value)})


def test_known_fee_with_missing_rate_becomes_unknown() -> None:
    missing = FeeQuote(status=FeeStatus.KNOWN)
    assert missing.status is FeeStatus.UNKNOWN and missing.reason == "fee rate absent"
    for rate in (Decimal("-1"), Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(ValidationError):
            FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=rate)


def test_market_model_rejects_wrong_token_mapping_even_if_market_was_normalized() -> None:
    market = normalize_market(
        {
            "id": "1",
            "conditionId": "c",
            "outcomes": ["No", "Yes"],
            "clobTokenIds": ["n", "y"],
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "enableOrderBook": True,
        }
    )
    assert market.yes_token_id == "y"
    payload = market.model_dump()
    payload["yes_token_id"] = "n"
    with pytest.raises(ValidationError):
        type(market).model_validate(payload)
