"""Read-only Decimal summaries of each outcome token's actual order book.

Spread, depth imbalance and microprice are descriptive market microstructure
metrics, not probability forecasts or expected profit. The implementation is
independent; no market-making or execution code is imported.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, DecimalException, localcontext

from app.models import OrderBook, PriceLevel

ZERO = Decimal("0")
ONE = Decimal("1")
DEPTH_BAND = Decimal("0.02")


def _levels(levels: list[PriceLevel]) -> dict[Decimal, Decimal]:
    merged: dict[Decimal, Decimal] = defaultdict(lambda: ZERO)
    for level in levels:
        if level.price.is_finite() and level.size.is_finite() and ZERO <= level.price <= ONE and level.size > ZERO:
            try:
                merged[level.price] += level.size
            except DecimalException:
                merged.pop(level.price, None)
    return dict(merged)


def _number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == ZERO:
        return "0"
    if abs(value.adjusted()) > 50:
        # Avoid expanding malicious exponents into megabytes of display text.
        return str(value.normalize())
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _analyze_book(book: OrderBook) -> dict[str, str | None]:
    """Summarize one token without mutating it or inventing its other outcome.

    Depth includes bids within two cents below the best bid and asks within two
    cents above the best ask. Quantity is shares; collateral is price * shares.
    Two-sided derived metrics require an uncrossed book. A locked book is valid.
    No freshness is inferred here: the caller must attach its actual source age.
    """
    with localcontext() as context:
        context.prec = 50
        bids = _levels(book.bids)
        asks = _levels(book.asks)
        best_bid = max(bids, default=None)
        best_ask = min(asks, default=None)
        bid_size = bids.get(best_bid) if best_bid is not None else None
        ask_size = asks.get(best_ask) if best_ask is not None else None
        bid_band = {p: s for p, s in bids.items() if best_bid is not None and p >= best_bid - DEPTH_BAND}
        ask_band = {p: s for p, s in asks.items() if best_ask is not None and p <= best_ask + DEPTH_BAND}

        midpoint = spread = spread_bps = imbalance = microprice = None
        if best_bid is None and best_ask is None:
            quality = "unavailable"
        elif best_bid is None or best_ask is None:
            quality = "one-sided"
        elif best_bid > best_ask:
            quality = "crossed"
        else:
            quality = "normal"
            midpoint = (best_bid + best_ask) / Decimal("2")
            spread = best_ask - best_bid
            spread_bps = spread / midpoint * Decimal("10000") if midpoint > ZERO else None
            if bid_size is not None and ask_size is not None:
                total_size = bid_size + ask_size
                imbalance = (bid_size - ask_size) / total_size
                microprice = (best_ask * bid_size + best_bid * ask_size) / total_size

        tick = book.tick_size
        valid_tick = tick if tick is not None and tick.is_finite() and ZERO < tick <= ONE else None
        return {
            "asset_id": book.asset_id,
            "timestamp": book.timestamp,
            "quality": quality,
            "depth_band": _number(DEPTH_BAND),
            "tick_size": _number(valid_tick),
            "best_bid": _number(best_bid),
            "best_ask": _number(best_ask),
            "best_bid_size": _number(bid_size),
            "best_ask_size": _number(ask_size),
            "midpoint": _number(midpoint),
            "spread": _number(spread),
            "spread_bps": _number(spread_bps),
            "imbalance": _number(imbalance),
            "microprice": _number(microprice),
            "bid_depth_quantity": _number(sum(bid_band.values(), ZERO)),
            "ask_depth_quantity": _number(sum(ask_band.values(), ZERO)),
            "bid_depth_collateral": _number(sum((price * size for price, size in bid_band.items()), ZERO)),
            "ask_depth_collateral": _number(sum((price * size for price, size in ask_band.items()), ZERO)),
        }


def analyze_book(book: OrderBook) -> dict[str, str | None]:
    try:
        return _analyze_book(book)
    except DecimalException:
        result = _analyze_book(OrderBook(asset_id=book.asset_id, timestamp=book.timestamp))
        result["quality"] = "invalid"
        return result
