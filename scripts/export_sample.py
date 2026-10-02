from __future__ import annotations

import csv
from pathlib import Path

from app.config import get_settings
from app.database import Database


def main() -> None:
    output = Path("exports/paper-trades.csv")
    output.parent.mkdir(exist_ok=True)
    database = Database(get_settings().database_url)
    rows = database.list_paper_trades(5000)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        else:
            handle.write("status\n暂无数据\n")
    database.close()
    print(f"Exported {len(rows)} rows to exports/paper-trades.csv")


if __name__ == "__main__":
    main()
