from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.models import OrderBook, PriceLevel
from app.services.book_analytics import analyze_book


def level(price: str, size: str) -> PriceLevel:
    return PriceLevel(price=Decimal(price), size=Decimal(size))


def test_exact_decimal_metrics_and_two_cent_depth() -> None:
    book = OrderBook(
        asset_id="actual-outcome-token",
        timestamp="1750000000000",
        tick_size=Decimal("0.001"),
        bids=[level("0.47", "100"), level("0.48", "200"), level("0.49", "300"), level("0.469", "9999")],
        asks=[level("0.54", "80"), level("0.51", "100"), level("0.53", "50"), level("0.52", "20")],
    )
    original = book.model_dump()
    result = analyze_book(book)
    assert result["quality"] == "normal"
    assert result["best_bid"] == "0.49"
    assert result["best_ask"] == "0.51"
    assert result["best_bid_size"] == "300"
    assert result["best_ask_size"] == "100"
    assert result["midpoint"] == "0.5"
    assert result["spread"] == "0.02"
    assert result["spread_bps"] == "400"
    assert result["imbalance"] == "0.5"
    assert result["microprice"] == "0.505"
    assert result["depth_band"] == "0.02"
    assert result["bid_depth_quantity"] == "600"
    assert result["ask_depth_quantity"] == "170"
    assert result["bid_depth_collateral"] == "290"
    assert result["ask_depth_collateral"] == "87.9"
    assert result["tick_size"] == "0.001"
    assert book.model_dump() == original
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize(
    ("bids", "asks", "quality"),
    [
        ([], [], "unavailable"),
        ([level("0.4", "100")], [], "one-sided"),
        ([], [level("0.6", "100")], "one-sided"),
        ([level("0.6", "100")], [level("0.4", "100")], "crossed"),
    ],
)
def test_unavailable_sides_and_crossed_book_do_not_invent_two_sided_metrics(
    bids: list[PriceLevel], asks: list[PriceLevel], quality: str
) -> None:
    result = analyze_book(OrderBook(asset_id="a", bids=bids, asks=asks))
    assert result["quality"] == quality
    for field in ("midpoint", "spread", "spread_bps", "imbalance", "microprice"):
        assert result[field] is None
    assert result["bid_depth_quantity"] == ("100" if bids else "0")
    assert result["ask_depth_quantity"] == ("100" if asks else "0")


def test_locked_book_and_zero_midpoint_are_safe() -> None:
    result = analyze_book(OrderBook(asset_id="a", bids=[level("0", "3")], asks=[level("0", "1")]))
    assert result["quality"] == "normal"
    assert result["midpoint"] == "0"
    assert result["spread"] == "0"
    assert result["spread_bps"] is None
    assert result["imbalance"] == "0.5"
    assert result["microprice"] == "0"
    assert result["bid_depth_collateral"] == "0"


def test_invalid_levels_are_ignored_and_equal_prices_are_merged() -> None:
    result = analyze_book(
        OrderBook(
            asset_id="a",
            bids=[
                level("-0.1", "10"),
                level("1.01", "10"),
                level("0.5", "0"),
                level("0.5", "-1"),
                # Simulate corrupted internal data that bypassed model validation.
                PriceLevel.model_construct(price=Decimal("NaN"), size=Decimal("10")),
                PriceLevel.model_construct(price=Decimal("Infinity"), size=Decimal("10")),
                PriceLevel.model_construct(price=Decimal("0.5"), size=Decimal("Infinity")),
                level("0.5", "0.1"),
                level("0.500", "0.2"),
            ],
            asks=[level("0.6", "0.1")],
        ).model_copy(update={"tick_size": Decimal("NaN")})
    )
    assert result["quality"] == "normal"
    assert result["best_bid_size"] == "0.3"
    assert result["bid_depth_collateral"] == "0.15"
    assert result["imbalance"] == "0.5"
    assert result["microprice"] == "0.575"
    assert result["tick_size"] is None


def test_decimal_precision_and_probability_boundaries() -> None:
    result = analyze_book(
        OrderBook(
            asset_id="other-token",
            bids=[level("0.000000000000000001", "1")],
            asks=[level("0.000000000000000003", "3")],
        )
    )
    assert result["spread"] == "0.000000000000000002"
    assert result["midpoint"] == "0.000000000000000002"
    assert result["microprice"] == "0.0000000000000000015"
    assert result["spread_bps"] == "10000"
    assert result["imbalance"] == "-0.5"
    edge = analyze_book(OrderBook(asset_id="a", bids=[level("0.99", "1")], asks=[level("1", "2")]))
    assert edge["ask_depth_collateral"] == "2"
    assert Decimal(edge["best_bid"]) <= Decimal(edge["microprice"]) <= Decimal(edge["best_ask"])  # type: ignore[arg-type]


@pytest.mark.parametrize("tick", ["0", "-0.01", "1.01", "Infinity"])
def test_tick_size_has_finite_probability_bounds(tick: str) -> None:
    book = OrderBook(asset_id="a").model_copy(update={"tick_size": Decimal(tick)})
    assert analyze_book(book)["tick_size"] is None
