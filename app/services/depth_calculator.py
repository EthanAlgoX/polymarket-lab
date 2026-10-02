from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal, DecimalException

from app.models import DepthResult, FeeQuote, FeeStatus, OrderBook, PriceLevel
from app.services.fees import taker_fee

MONEY = Decimal("0.000001")
ZERO = Decimal("0")


def _valid_book(book: OrderBook) -> bool:
    levels = (*book.bids, *book.asks)
    if any(
        not level.price.is_finite()
        or not ZERO <= level.price <= Decimal("1")
        or not level.size.is_finite()
        or level.size <= ZERO
        for level in levels
    ):
        return False
    return not (
        book.min_order_size is not None and (not book.min_order_size.is_finite() or book.min_order_size <= ZERO)
    )


def _fingerprint(yes: OrderBook, no: OrderBook, target: Decimal, fee: FeeQuote, **parameters: object) -> str:
    def book_data(book: OrderBook) -> dict[str, object]:
        return {
            "asset_id": book.asset_id,
            "market": book.market,
            "timestamp": book.timestamp,
            "hash": book.book_hash,
            "bids": sorted((str(level.price), str(level.size)) for level in book.bids),
            "asks": sorted((str(level.price), str(level.size)) for level in book.asks),
            "tick_size": str(book.tick_size),
            "min_order_size": str(book.min_order_size),
        }

    data = {
        "yes": book_data(yes),
        "no": book_data(no),
        "target": str(target),
        "fee_status": str(fee.status),
        "fee_rate": str(fee.base_fee_bps),
        **{key: str(value) for key, value in parameters.items()},
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def _unusable_result(
    status: str, target: Decimal, quote_age: Decimal, fee_status: FeeStatus, fingerprint: str, extra_cost: Decimal
) -> DepthResult:
    return DepthResult(
        status=status,
        target_quantity=target,
        executable_quantity=ZERO,
        yes_executable_quantity=ZERO,
        no_executable_quantity=ZERO,
        yes_average_price=None,
        no_average_price=None,
        yes_cost=ZERO,
        no_cost=ZERO,
        total_cost=ZERO,
        settlement_value=ZERO,
        gross_profit=ZERO,
        estimated_fees=None,
        slippage_buffer=ZERO,
        safety_buffer=ZERO,
        extra_cost=extra_cost,
        net_profit=None,
        net_roi=None,
        yes_depth_shortfall=target,
        no_depth_shortfall=target,
        partial_fill=True,
        quote_age=quote_age,
        fee_status=fee_status,
        snapshot_fingerprint=fingerprint,
    )


def _walk(levels: list[PriceLevel], quantity: Decimal) -> tuple[Decimal, Decimal]:
    filled = Decimal("0")
    cost = Decimal("0")
    for level in sorted(levels, key=lambda item: item.price):
        take = min(level.size, quantity - filled)
        if take <= 0:
            break
        filled += take
        cost += take * level.price
        if filled >= quantity:
            break
    return filled, cost


def _calculate_depth(
    yes: OrderBook,
    no: OrderBook,
    target: Decimal,
    fee: FeeQuote,
    *,
    slippage_rate: Decimal = Decimal("0.001"),
    safety_rate: Decimal = Decimal("0.001"),
    quote_age: Decimal = Decimal("0"),
    allow_partial: bool = True,
    extra_cost: Decimal = Decimal("0"),
    expected_condition_id: str | None = None,
) -> DepthResult:
    if not target.is_finite() or target <= 0:
        raise ValueError("target quantity must be finite and positive")
    for name, value in (
        ("slippage_rate", slippage_rate),
        ("safety_rate", safety_rate),
        ("extra_cost", extra_cost),
        ("quote_age", quote_age),
    ):
        if not value.is_finite() or value < ZERO:
            raise ValueError(f"{name} must be finite and nonnegative")
    fingerprint = _fingerprint(
        yes,
        no,
        target,
        fee,
        slippage_rate=slippage_rate,
        safety_rate=safety_rate,
        extra_cost=extra_cost,
        allow_partial=allow_partial,
        expected_condition_id=expected_condition_id,
    )
    verified_fee = (
        fee.status is FeeStatus.KNOWN
        and fee.base_fee_bps is not None
        and fee.base_fee_bps.is_finite()
        and fee.base_fee_bps >= ZERO
    )
    fee_status = FeeStatus.KNOWN if verified_fee else FeeStatus.UNKNOWN
    if (
        not yes.asset_id.strip()
        or not no.asset_id.strip()
        or yes.asset_id == no.asset_id
        or (yes.market and no.market and yes.market != no.market)
        or (expected_condition_id and any(book.market and book.market != expected_condition_id for book in (yes, no)))
    ):
        return _unusable_result("INVALID_PAIR", target, quote_age, fee_status, fingerprint, extra_cost)
    if not _valid_book(yes) or not _valid_book(no):
        return _unusable_result("INVALID_BOOK", target, quote_age, fee_status, fingerprint, extra_cost)
    if any(
        book.bids and book.asks and max(level.price for level in book.bids) > min(level.price for level in book.asks)
        for book in (yes, no)
    ):
        return _unusable_result("CROSSED_BOOK", target, quote_age, fee_status, fingerprint, extra_cost)
    yes_available, _ = _walk(yes.asks, target)
    no_available, _ = _walk(no.asks, target)
    executable = min(target, yes_available, no_available)
    yes_filled, yes_cost = _walk(yes.asks, executable)
    no_filled, no_cost = _walk(no.asks, executable)
    partial = executable < target
    yes_avg = yes_cost / yes_filled if yes_filled else None
    no_avg = no_cost / no_filled if no_filled else None
    total = yes_cost + no_cost
    settlement = executable
    gross = settlement - total
    fee_value: Decimal | None = None
    if verified_fee and yes_avg is not None and no_avg is not None:

        def level_fees(levels: list[PriceLevel]) -> Decimal | None:
            remaining = executable
            total_fee = Decimal("0")
            for level in sorted(levels, key=lambda item: item.price):
                take = min(remaining, level.size)
                if take <= 0:
                    break
                value = taker_fee(take, level.price, fee)
                if value is None:
                    return None
                total_fee += value
                remaining -= take
            return total_fee

        yes_fee, no_fee = level_fees(yes.asks), level_fees(no.asks)
        if yes_fee is not None and no_fee is not None:
            fee_value = yes_fee + no_fee
    slippage = (total * slippage_rate).quantize(MONEY, rounding=ROUND_HALF_UP)
    safety = (total * safety_rate).quantize(MONEY, rounding=ROUND_HALF_UP)
    net = gross - fee_value - slippage - safety - extra_cost if fee_value is not None else None
    budget = total + (fee_value or Decimal("0")) + slippage + safety + extra_cost
    roi = net / budget if net is not None and budget else None
    if not yes.asks or not no.asks:
        status = "NO_ASKS"
    elif fee_status is FeeStatus.UNKNOWN:
        status = "FEE_UNKNOWN"
    elif partial and not allow_partial:
        status = "PARTIAL_NOT_ALLOWED"
    elif executable <= 0:
        status = "NO_LIQUIDITY"
    elif executable < max(yes.min_order_size or ZERO, no.min_order_size or ZERO):
        status = "BELOW_MIN_ORDER"
    else:
        status = "VALID" if not partial else "PARTIAL"
    return DepthResult(
        status=status,
        target_quantity=target,
        executable_quantity=executable,
        yes_executable_quantity=yes_available,
        no_executable_quantity=no_available,
        yes_average_price=yes_avg,
        no_average_price=no_avg,
        yes_cost=yes_cost.quantize(MONEY),
        no_cost=no_cost.quantize(MONEY),
        total_cost=total.quantize(MONEY),
        settlement_value=settlement.quantize(MONEY),
        gross_profit=gross.quantize(MONEY),
        estimated_fees=fee_value,
        slippage_buffer=slippage,
        safety_buffer=safety,
        extra_cost=extra_cost,
        net_profit=net.quantize(MONEY) if net is not None else None,
        net_roi=roi,
        yes_depth_shortfall=max(Decimal("0"), target - yes_available),
        no_depth_shortfall=max(Decimal("0"), target - no_available),
        partial_fill=partial,
        quote_age=quote_age,
        fee_status=fee_status,
        snapshot_fingerprint=fingerprint,
    )


def calculate_depth(
    yes: OrderBook,
    no: OrderBook,
    target: Decimal,
    fee: FeeQuote,
    *,
    slippage_rate: Decimal = Decimal("0.001"),
    safety_rate: Decimal = Decimal("0.001"),
    quote_age: Decimal = ZERO,
    allow_partial: bool = True,
    extra_cost: Decimal = ZERO,
    expected_condition_id: str | None = None,
) -> DepthResult:
    """Evaluate equal shares on distinct outcome books, failing closed on bad arithmetic."""
    try:
        return _calculate_depth(
            yes,
            no,
            target,
            fee,
            slippage_rate=slippage_rate,
            safety_rate=safety_rate,
            quote_age=quote_age,
            allow_partial=allow_partial,
            extra_cost=extra_cost,
            expected_condition_id=expected_condition_id,
        )
    except DecimalException:
        fingerprint = _fingerprint(
            yes,
            no,
            target,
            fee,
            slippage_rate=slippage_rate,
            safety_rate=safety_rate,
            extra_cost=extra_cost,
            allow_partial=allow_partial,
            expected_condition_id=expected_condition_id,
        )
        return _unusable_result("INVALID_CALCULATION", target, quote_age, FeeStatus.UNKNOWN, fingerprint, extra_cost)
