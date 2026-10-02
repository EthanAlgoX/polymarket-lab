"""Explicitly reset the configured local SQLite file after stopping the service."""

from __future__ import annotations

import argparse
import socket
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings
from app.database import Base, Database


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the configured SQLite database; stop the app first.")
    parser.add_argument("--confirm", choices=["RESET"], help="Explicit confirmation for a scripted local reset.")
    arguments = parser.parse_args()
    settings = get_settings()
    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        print("[ERROR] Reset supports a configured local SQLite file only.")
        return 1
    path = Path(url.database).resolve()
    print(f"WARNING: This permanently removes the local records in {path}. Stop the app first.")
    if arguments.confirm != "RESET":
        try:
            confirmation = input("Type RESET to continue: ").strip()
        except EOFError:
            confirmation = ""
        if confirmation != "RESET":
            print("Cancelled.")
            return 1
    host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(settings.host, settings.host)
    try:
        with socket.create_connection((host, settings.port), timeout=1):
            print("[ERROR] The configured server port is active. Stop the service before resetting.")
            return 1
    except ConnectionRefusedError:
        pass
    except OSError:
        print("[ERROR] Could not verify that the configured service is stopped. Database was preserved.")
        return 1
    path.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    database = Database(settings.database_url)
    try:
        Base.metadata.create_all(database.engine)
    finally:
        database.close()
    print("[OK] Empty database schema created. Source files and exports were preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
