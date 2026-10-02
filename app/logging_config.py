from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
        }
        for key in (
            "market_id",
            "token_id",
            "duration_ms",
            "retry_count",
            "error_type",
            "origin",
            "status",
            "kind",
            "attempt",
            "retry_delay",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    Path("logs").mkdir(exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    # The app logs sanitized request metadata itself. HTTPX's INFO request
    # lines include raw query strings and URL userinfo; keep those out of logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if root.handlers:
        return
    formatter = JsonFormatter()
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    file_handler = RotatingFileHandler("logs/scanner.jsonl", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(stream)
    root.addHandler(file_handler)
