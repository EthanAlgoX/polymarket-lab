from __future__ import annotations

import hashlib
from decimal import ROUND_HALF_UP, Decimal

from app.models import DepthResult, FeeQuote, FeeStatus, OrderBook, PriceLevel
from app.services.fees import taker_fee

MONEY = Decimal("0.000001")


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


def calculate_depth(
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
) -> DepthResult:
    if target <= 0:
        raise ValueError("target quantity must be positive")
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
    if fee.status is FeeStatus.KNOWN and yes_avg is not None and no_avg is not None:

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
    elif fee.status is FeeStatus.UNKNOWN:
        status = "FEE_UNKNOWN"
    elif partial and not allow_partial:
        status = "PARTIAL_NOT_ALLOWED"
    elif executable <= 0:
        status = "NO_LIQUIDITY"
    else:
        status = "VALID" if not partial else "PARTIAL"
    fingerprint = hashlib.sha256(
        f"{yes.asset_id}:{yes.book_hash}:{no.asset_id}:{no.book_hash}:{target}".encode()
    ).hexdigest()[:24]
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
        fee_status=fee.status,
        snapshot_fingerprint=fingerprint,
    )
