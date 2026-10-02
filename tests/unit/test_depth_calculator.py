from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import FeeQuote, FeeStatus, OrderBook, PriceLevel
from app.services.depth_calculator import calculate_depth
from app.services.fees import taker_fee


def book(token: str, asks: list[tuple[str, str]]) -> OrderBook:
    return OrderBook(
        asset_id=token, book_hash=token, asks=[PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in asks]
    )


def fee(rate: str = "0") -> FeeQuote:
    return FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal(rate))


def test_weighted_multilevel_fill() -> None:
    result = calculate_depth(
        book("y", [("0.40", "5"), ("0.50", "5")]), book("n", [("0.40", "10")]), Decimal("10"), fee()
    )
    assert result.yes_average_price == Decimal("0.45")
    assert result.executable_quantity == Decimal("10")
    assert result.gross_profit == Decimal("1.500000")


def test_common_quantity_uses_shallower_side() -> None:
    result = calculate_depth(book("y", [("0.4", "3")]), book("n", [("0.4", "8")]), Decimal("10"), fee())
    assert result.executable_quantity == Decimal("3")
    assert result.yes_depth_shortfall == Decimal("7")
    assert result.no_depth_shortfall == Decimal("2")
    assert result.partial_fill is True


def test_partial_can_be_disallowed() -> None:
    result = calculate_depth(
        book("y", [("0.4", "3")]), book("n", [("0.4", "3")]), Decimal("10"), fee(), allow_partial=False
    )
    assert result.status == "PARTIAL_NOT_ALLOWED"


def test_empty_side_has_clear_status() -> None:
    result = calculate_depth(book("y", []), book("n", [("0.5", "2")]), Decimal("1"), fee())
    assert result.status == "NO_ASKS"
    assert result.settlement_value == Decimal("0.000000")


def test_unknown_fee_never_becomes_zero() -> None:
    unknown = FeeQuote(status=FeeStatus.UNKNOWN, reason="no rate")
    result = calculate_depth(book("y", [("0.4", "2")]), book("n", [("0.4", "2")]), Decimal("1"), unknown)
    assert result.status == "FEE_UNKNOWN"
    assert result.estimated_fees is None
    assert result.net_profit is None


def test_buffers_reduce_net_profit() -> None:
    result = calculate_depth(
        book("y", [("0.4", "10")]),
        book("n", [("0.4", "10")]),
        Decimal("10"),
        fee(),
        slippage_rate=Decimal("0.01"),
        safety_rate=Decimal("0.01"),
    )
    assert result.slippage_buffer == Decimal("0.080000")
    assert result.safety_buffer == Decimal("0.080000")
    assert result.net_profit == Decimal("1.840000")


@pytest.mark.parametrize("target", ["0", "-1"])
def test_invalid_target(target: str) -> None:
    with pytest.raises(ValueError):
        calculate_depth(book("y", []), book("n", []), Decimal(target), fee())


@pytest.mark.parametrize(
    ("shares", "price", "rate", "expected"),
    [("100", "0.5", "30", "0.75000"), ("1", "0.01", "0", "0.00000"), ("0.000001", "0.01", "30", "0.00000")],
)
def test_official_fee_formula(shares: str, price: str, rate: str, expected: str) -> None:
    assert taker_fee(Decimal(shares), Decimal(price), fee(rate)) == Decimal(expected)


def test_decimal_precision_is_exact() -> None:
    result = calculate_depth(
        book("y", [("0.333333", "0.000003")]), book("n", [("0.333333", "0.000003")]), Decimal("0.000003"), fee()
    )
    assert result.executable_quantity == Decimal("0.000003")
    assert isinstance(result.total_cost, Decimal)
