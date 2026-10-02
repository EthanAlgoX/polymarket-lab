"""Shared bounded-memory CSV output for HTTP and local export commands."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator
from decimal import Decimal, InvalidOperation
from typing import Any

CSV_NUMERIC_FIELDS = {
    "id",
    "target_quantity",
    "executable_quantity",
    "total_cost",
    "net_profit",
    "net_roi",
    "max_net_profit",
    "max_net_roi",
    "max_quantity",
}
PAPER_CSV_FIELDS = [
    "id",
    "created_at",
    "market_id",
    "market_question",
    "target_quantity",
    "executable_quantity",
    "total_cost",
    "net_profit",
    "net_roi",
    "status",
    "failure_reason",
    "trigger_type",
    "data_source",
]
OPPORTUNITY_CSV_FIELDS = [
    "id",
    "market_id",
    "question",
    "first_seen",
    "last_seen",
    "status",
    "max_net_profit",
    "max_net_roi",
    "max_quantity",
    "disappeared_reason",
]


def _numeric(value: str) -> bool:
    try:
        return Decimal(value).is_finite()
    except (InvalidOperation, ValueError):
        return False


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    safe = dict(row)
    for key, value in safe.items():
        if (
            isinstance(value, str)
            and value.lstrip().startswith(("=", "+", "-", "@"))
            and (key not in CSV_NUMERIC_FIELDS or not _numeric(value))
        ):
            safe[key] = "'" + value
    return safe


def csv_chunks(rows: Iterable[dict[str, Any]], fields: list[str]) -> Iterator[bytes]:
    """Include stable headers/BOM, escape formulas, and preserve real negative numbers."""
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    try:
        stream.write("\ufeff")
        writer.writeheader()
        yield stream.getvalue().encode("utf-8")
        stream.seek(0)
        stream.truncate(0)
        for count, row in enumerate(rows, 1):
            writer.writerow(_safe_row(row))
            if count % 500 == 0:
                yield stream.getvalue().encode("utf-8")
                stream.seek(0)
                stream.truncate(0)
        if stream.tell():
            yield stream.getvalue().encode("utf-8")
    finally:
        close = getattr(rows, "close", None)
        if close is not None:
            close()
        stream.close()
