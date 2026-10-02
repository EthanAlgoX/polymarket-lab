from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.models import FeeQuote, FeeStatus

FEE_QUANTUM = Decimal("0.00001")


def taker_fee(shares: Decimal, price: Decimal, quote: FeeQuote) -> Decimal | None:
    """Official formula: shares x feeRate x price x (1-price), rounded to 5 dp."""
    if quote.status is not FeeStatus.KNOWN or quote.base_fee_bps is None:
        return None
    rate = quote.base_fee_bps / Decimal("1000")
    fee = shares * rate * price * (Decimal("1") - price)
    return fee.quantize(FEE_QUANTUM, rounding=ROUND_HALF_UP)
