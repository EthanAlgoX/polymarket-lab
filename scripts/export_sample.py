from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.database import Database
from app.services.csv_export import PAPER_CSV_FIELDS, csv_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Export every saved paper record as a spreadsheet-safe CSV.")
    parser.add_argument("--output", type=Path, default=Path("exports/paper-trades.csv"))
    output = parser.parse_args().output
    output.parent.mkdir(parents=True, exist_ok=True)
    database = Database(get_settings().database_url)
    count = 0
    rows = database.iter_paper_trades()

    def counted_rows() -> Iterator[dict[str, Any]]:
        nonlocal count
        try:
            for row in rows:
                count += 1
                yield row
        finally:
            rows.close()

    descriptor, temporary_name = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}-", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for chunk in csv_chunks(counted_rows(), PAPER_CSV_FIELDS):
                handle.write(chunk)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
        database.close()
    print(f"Exported {count} rows to {output}")


if __name__ == "__main__":
    main()
