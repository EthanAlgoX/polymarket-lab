from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
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
        merged[price] += size
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
        return parsed if parsed.is_finite() else None

    return OrderBook(
        asset_id=str(raw.get("asset_id", "")),
        market=str(raw.get("market", "")),
        timestamp=str(raw.get("timestamp", "")),
        bids=_levels(raw.get("bids"), reverse=True),
        asks=_levels(raw.get("asks"), reverse=False),
        tick_size=optional_decimal("tick_size"),
        min_order_size=optional_decimal("min_order_size"),
        last_trade_price=optional_decimal("last_trade_price"),
        book_hash=str(raw.get("hash", "")),
    )
