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


@pytest.mark.parametrize("target", ["0", "-1", "NaN", "Infinity", "-Infinity"])
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


@pytest.mark.parametrize("parameter", ["slippage_rate", "safety_rate", "quote_age", "extra_cost"])
@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity"])
def test_bad_financial_inputs_cannot_increase_profit(parameter: str, value: str) -> None:
    with pytest.raises(ValueError):
        calculate_depth(
            book("y", [("0.4", "2")]), book("n", [("0.4", "2")]), Decimal("1"), fee(), **{parameter: Decimal(value)}
        )


@pytest.mark.parametrize(
    ("price", "size"), [("-0.1", "2"), ("1.1", "2"), ("NaN", "2"), ("0.4", "-2"), ("0.4", "0"), ("0.4", "Infinity")]
)
def test_corrupted_internal_levels_fail_closed(price: str, size: str) -> None:
    bad = OrderBook(asset_id="y", asks=[PriceLevel.model_construct(price=Decimal(price), size=Decimal(size))])
    result = calculate_depth(bad, book("n", [("0.4", "2")]), Decimal("1"), fee())
    assert result.status == "INVALID_BOOK"
    assert result.executable_quantity == 0
    assert result.net_profit is None and result.net_roi is None


@pytest.mark.parametrize("same_market", [True, False])
def test_invalid_pair_never_creates_a_complete_set(same_market: bool) -> None:
    yes, no = book("y", [("0.4", "2")]), book("y" if same_market else "n", [("0.4", "2")])
    if not same_market:
        yes.market, no.market = "condition-one", "condition-two"
    result = calculate_depth(yes, no, Decimal("1"), fee())
    assert result.status == "INVALID_PAIR"
    assert result.settlement_value == 0 and result.net_profit is None


def test_unsorted_crossed_book_is_rejected_and_locked_book_is_supported() -> None:
    yes = book("y", [("0.45", "2"), ("0.40", "2")])
    yes.bids = [
        PriceLevel(price=Decimal("0.39"), size=Decimal("3")),
        PriceLevel(price=Decimal("0.41"), size=Decimal("2")),
    ]
    assert calculate_depth(yes, book("n", [("0.4", "2")]), Decimal("1"), fee()).status == "CROSSED_BOOK"
    yes.bids = [PriceLevel(price=Decimal("0.40"), size=Decimal("2"))]
    assert calculate_depth(yes, book("n", [("0.4", "2")]), Decimal("1"), fee()).status == "VALID"


def test_known_fee_without_a_valid_rate_cannot_be_valid() -> None:
    for rate in (None, Decimal("NaN"), Decimal("-1")):
        invalid = FeeQuote.model_construct(status=FeeStatus.KNOWN, base_fee_bps=rate)
        result = calculate_depth(book("y", [("0.4", "2")]), book("n", [("0.4", "2")]), Decimal("1"), invalid)
        assert result.status == "FEE_UNKNOWN" and result.fee_status is FeeStatus.UNKNOWN
        assert result.estimated_fees is None and result.net_profit is None


def test_minimum_order_quantity_is_checked_by_the_calculator() -> None:
    yes = book("y", [("0.4", "2")])
    yes.min_order_size = Decimal("2")
    assert calculate_depth(yes, book("n", [("0.4", "2")]), Decimal("1"), fee()).status == "BELOW_MIN_ORDER"


def test_fingerprint_identifies_actual_depth_and_cost_parameters_without_hashes() -> None:
    yes, no = book("y", [("0.4", "2")]), book("n", [("0.4", "2")])
    yes.book_hash = no.book_hash = ""
    initial = calculate_depth(yes, no, Decimal("1"), fee()).snapshot_fingerprint
    assert calculate_depth(yes, no, Decimal("1"), fee()).snapshot_fingerprint == initial
    assert calculate_depth(yes, no, Decimal("1"), fee("50")).snapshot_fingerprint != initial
    assert calculate_depth(yes, no, Decimal("1"), fee(), extra_cost=Decimal("1")).snapshot_fingerprint != initial
    yes.asks = [PriceLevel(price=Decimal("0.41"), size=Decimal("2"))]
    assert calculate_depth(yes, no, Decimal("1"), fee()).snapshot_fingerprint != initial


@pytest.mark.parametrize(("shares", "price"), [("-1", "0.5"), ("NaN", "0.5"), ("1", "-0.1"), ("1", "1.1")])
def test_invalid_fee_inputs_raise_instead_of_creating_negative_fees(shares: str, price: str) -> None:
    with pytest.raises(ValueError):
        taker_fee(Decimal(shares), Decimal(price), fee("50"))


def test_extreme_finite_fee_cannot_raise_decimal_errors_out_of_the_scanner() -> None:
    result = calculate_depth(book("y", [("0.4", "2")]), book("n", [("0.4", "2")]), Decimal("1"), fee("1e9999"))
    assert result.status == "INVALID_CALCULATION"
    assert result.executable_quantity == 0 and result.net_profit is None


@pytest.mark.parametrize(
    ("yes_condition", "no_condition", "expected_status"),
    [
        ("foreign", "foreign", "INVALID_PAIR"),
        ("condition", "foreign", "INVALID_PAIR"),
        ("foreign", "", "INVALID_PAIR"),
        ("condition", "condition", "VALID"),
        ("condition", "", "VALID"),
        ("", "", "VALID"),
    ],
)
def test_orderbooks_are_bound_to_the_callers_known_condition(
    yes_condition: str, no_condition: str, expected_status: str
) -> None:
    yes, no = book("y", [("0.4", "2")]), book("n", [("0.4", "2")])
    yes.market, no.market = yes_condition, no_condition
    result = calculate_depth(yes, no, Decimal("1"), fee(), expected_condition_id="condition")
    assert result.status == expected_status
    if expected_status == "INVALID_PAIR":
        assert result.executable_quantity == 0 and result.net_profit is None
    else:
        assert result.executable_quantity == 1 and result.net_profit is not None


def test_expected_condition_is_traceable_even_when_schema_omits_it_from_books() -> None:
    yes, no = book("y", [("0.4", "2")]), book("n", [("0.4", "2")])
    without = calculate_depth(yes, no, Decimal("1"), fee())
    known = calculate_depth(yes, no, Decimal("1"), fee(), expected_condition_id="condition")
    assert without.status == known.status == "VALID"
    assert without.snapshot_fingerprint != known.snapshot_fingerprint
