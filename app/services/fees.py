from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.models import FeeQuote, FeeStatus

FEE_QUANTUM = Decimal("0.00001")


def taker_fee(shares: Decimal, price: Decimal, quote: FeeQuote) -> Decimal | None:
    """Official formula: shares x feeRate x price x (1-price), rounded to 5 dp."""
    if not shares.is_finite() or shares < 0 or not price.is_finite() or not Decimal("0") <= price <= Decimal("1"):
        raise ValueError("fee quantity and price must be finite and within their valid ranges")
    if (
        quote.status is not FeeStatus.KNOWN
        or quote.base_fee_bps is None
        or not quote.base_fee_bps.is_finite()
        or quote.base_fee_bps < 0
    ):
        return None
    rate = quote.base_fee_bps / Decimal("1000")
    fee = shares * rate * price * (Decimal("1") - price)
    return fee.quantize(FEE_QUANTUM, rounding=ROUND_HALF_UP)
