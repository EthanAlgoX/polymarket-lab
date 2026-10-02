from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any

from app.models import OrderBook, PriceLevel


def _levels(value: object, *, reverse: bool) -> list[PriceLevel]:
    merged: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0"))
    if not isinstance(value, list):
        return []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            price = Decimal(str(item.get("price", "")))
            size = Decimal(str(item.get("size", "")))
        except (InvalidOperation, ValueError):
            continue
        if not price.is_finite() or not size.is_finite() or price < 0 or price > 1 or size <= 0:
            continue
        try:
            merged[price] += size
        except DecimalException:
            # An unrepresentable aggregate must not become usable liquidity.
            merged.pop(price, None)
    return [PriceLevel(price=p, size=merged[p]) for p in sorted(merged, reverse=reverse)]


def normalize_orderbook(raw: dict[str, Any]) -> OrderBook:
    def optional_decimal(key: str) -> Decimal | None:
        value = raw.get(key)
        if value in (None, ""):
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        if not parsed.is_finite():
            return None
        if key == "tick_size" and not Decimal("0") < parsed <= Decimal("1"):
            return None
        if key == "min_order_size" and parsed <= 0:
            return None
        if key == "last_trade_price" and not Decimal("0") <= parsed <= Decimal("1"):
            return None
        return parsed

    return OrderBook(
        asset_id=str(raw.get("asset_id") or "").strip(),
        market=str(raw.get("market") or "").strip(),
        timestamp=str(raw.get("timestamp") or ""),
        bids=_levels(raw.get("bids"), reverse=True),
        asks=_levels(raw.get("asks"), reverse=False),
        tick_size=optional_decimal("tick_size"),
        min_order_size=optional_decimal("min_order_size"),
        last_trade_price=optional_decimal("last_trade_price"),
        book_hash=str(raw.get("hash", "")),
    )
