"""Fail-closed source quote ages using exact Decimal elapsed seconds."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, DecimalException

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MAX_FUTURE_SKEW = Decimal("1")
UNKNOWN_QUOTE_AGE = Decimal("999999")


def _seconds(delta: timedelta) -> Decimal:
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal("1000000")


def elapsed_seconds(since: datetime, *, now: datetime | None = None) -> Decimal:
    return max(Decimal("0"), _seconds((now or datetime.now(UTC)) - since))


def quote_age_seconds(timestamp: str | None, *, now: datetime | None = None) -> Decimal | None:
    """Read epoch milliseconds; missing, invalid or future clocks are unknown.

    Up to one second of source clock skew is tolerated as age zero. Larger
    future values must never make old or malformed quotes appear fresh.
    """
    try:
        source = Decimal(timestamp) if timestamp is not None else None
        if source is None or not source.is_finite() or source <= 0:
            return None
        age = _seconds((now or datetime.now(UTC)) - EPOCH) - source / Decimal("1000")
        if not age.is_finite() or age < -MAX_FUTURE_SKEW:
            return None
        return max(Decimal("0"), age)
    except (DecimalException, TypeError, ValueError):
        return None


def oldest_quote_age(timestamps: Iterable[str | None], *, now: datetime | None = None) -> Decimal | None:
    observed_at = now or datetime.now(UTC)
    ages: list[Decimal] = []
    for timestamp in timestamps:
        age = quote_age_seconds(timestamp, now=observed_at)
        if age is None:
            return None
        ages.append(age)
    return max(ages) if ages else None
