from __future__ import annotations

from decimal import Decimal

from app.models import FeeQuote, FeeStatus, Market, OrderBook, PriceLevel
from app.services.depth_calculator import calculate_depth
from app.services.scanner import is_valid_opportunity


def market() -> Market:
    return Market(
        market_id="1",
        condition_id="c",
        question="q",
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
        outcomes=["Yes", "No"],
        token_ids=["y", "n"],
        yes_token_id="y",
        no_token_id="n",
    )


def result():
    level = [PriceLevel(price=Decimal("0.4"), size=Decimal("10"))]
    return calculate_depth(
        OrderBook(asset_id="y", asks=level),
        OrderBook(asset_id="n", asks=level),
        Decimal("10"),
        FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0")),
    )


def test_valid_opportunity() -> None:
    valid, reason = is_valid_opportunity(
        market(),
        result(),
        min_quantity=Decimal("1"),
        min_profit=Decimal("0.1"),
        min_roi=Decimal("0.002"),
        max_quote_age=Decimal("5"),
    )
    assert valid and reason == "有效机会"


def test_closed_market_rejected() -> None:
    m = market().model_copy(update={"closed": True})
    assert not is_valid_opportunity(
        m,
        result(),
        min_quantity=Decimal("1"),
        min_profit=Decimal("0"),
        min_roi=Decimal("0"),
        max_quote_age=Decimal("5"),
    )[0]


def test_stale_quote_rejected() -> None:
    r = result().model_copy(update={"quote_age": Decimal("6")})
    assert not is_valid_opportunity(
        market(),
        r,
        min_quantity=Decimal("1"),
        min_profit=Decimal("0"),
        min_roi=Decimal("0"),
        max_quote_age=Decimal("5"),
    )[0]


def test_profit_threshold_rejected() -> None:
    assert not is_valid_opportunity(
        market(),
        result(),
        min_quantity=Decimal("1"),
        min_profit=Decimal("100"),
        min_roi=Decimal("0"),
        max_quote_age=Decimal("5"),
    )[0]
