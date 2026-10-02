from __future__ import annotations

import csv
import io
import os
import socket
import subprocess
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement
from sqlalchemy import insert

from app.database import Database, PaperTradeRow
from app.models import FeeQuote, FeeStatus, Market, OrderBook, PriceLevel
from app.services.csv_export import PAPER_CSV_FIELDS, csv_chunks
from app.services.depth_calculator import calculate_depth
from scripts import reset_database

ROOT = Path(__file__).resolve().parents[2]


def cli(
    tmp_path: Path,
    module: str,
    *arguments: str,
    input_text: str | None = None,
    env_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if "DEEPSEEK" not in key.upper()}
    environment.update(
        {
            "PMS_DATABASE_URL": f"sqlite:///{tmp_path / 'cli.db'}",
            "PMS_ENABLE_LIVE_SCANNER": "false",
            "PYTHONPATH": str(ROOT),
        }
    )
    environment.update(env_updates or {})
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        input=input_text,
        text=True,
        timeout=30,
        check=False,
    )


def test_documented_init_and_empty_export_commands_make_headers_without_fake_records(tmp_path: Path) -> None:
    initialized = cli(tmp_path, "scripts.init_db")
    assert initialized.returncode == 0, initialized.stderr
    assert (tmp_path / "cli.db").exists()
    result = cli(tmp_path, "scripts.export_sample")
    assert result.returncode == 0, result.stderr
    output = tmp_path / "exports/paper-trades.csv"
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.reader(handle)) == [PAPER_CSV_FIELDS]
    assert "Exported 0 rows" in result.stdout


def test_init_command_is_idempotent_and_does_not_close_existing_signal_history(tmp_path: Path) -> None:
    assert cli(tmp_path, "scripts.init_db").returncode == 0
    database = Database(f"sqlite:///{tmp_path / 'cli.db'}")
    market = Market(
        market_id="m",
        condition_id="c",
        question="q",
        active=True,
        accepting_orders=True,
        enable_order_book=True,
        outcomes=["Yes", "No"],
        token_ids=["y", "n"],
        yes_token_id="y",
        no_token_id="n",
    )
    result = calculate_depth(
        OrderBook(asset_id="y", asks=[PriceLevel(price="0.4", size="10")]),
        OrderBook(asset_id="n", asks=[PriceLevel(price="0.4", size="10")]),
        target=Decimal("10"),
        fee=FeeQuote(status=FeeStatus.KNOWN, base_fee_bps="0"),
    )
    try:
        database.upsert_opportunity(market, result)
        first = database.list_opportunities()[0]
        assert cli(tmp_path, "scripts.init_db").returncode == 0
        after = database.list_opportunities()[0]
        assert after["status"] == "active" and after["first_seen"] == first["first_seen"]
    finally:
        database.close()


def test_export_command_streams_more_than_old_limit_and_escapes_formula_text(tmp_path: Path) -> None:
    assert cli(tmp_path, "scripts.init_db").returncode == 0
    database = Database(f"sqlite:///{tmp_path / 'cli.db'}")
    try:
        with database.Session.begin() as session:
            session.execute(
                insert(PaperTradeRow),
                [
                    {
                        "market_id": str(index),
                        "market_question": "\t=1+1",
                        "target_quantity": "10",
                        "executable_quantity": "10",
                        "total_cost": "8",
                        "net_profit": "-2.000000",
                        "net_roi": "-0.25",
                        "status": "SUCCESS",
                        "payload_json": "{}",
                    }
                    for index in range(5001)
                ],
            )
    finally:
        database.close()
    completed = cli(tmp_path, "scripts.export_sample", "--output", "nested/directory/all.csv")
    assert completed.returncode == 0, completed.stderr
    with (tmp_path / "nested/directory/all.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 5001 and "Exported 5001 rows" in completed.stdout
    assert rows[0]["market_question"] == "'\t=1+1"
    assert rows[0]["net_profit"] == "-2.000000" and rows[0]["net_roi"] == "-0.25"
    assert rows[0]["id"] == "5001" and rows[-1]["id"] == "1"


def test_export_failure_preserves_previous_complete_file_and_removes_temp_file(tmp_path: Path) -> None:
    output = tmp_path / "existing.csv"
    output.write_text("previous complete export", encoding="utf-8")
    completed = cli(tmp_path, "scripts.export_sample", "--output", str(output))
    assert completed.returncode != 0
    assert output.read_text(encoding="utf-8") == "previous complete export"
    assert list(tmp_path.glob(".existing.csv-*.tmp")) == []


def test_shared_csv_preserves_valid_numbers_but_escapes_formulas_in_every_column() -> None:
    rows = [{"id": "=1+1", "market_question": "@SUM(1)", "net_profit": "-2.000000", "net_roi": "=1+1"}]
    result = list(csv.DictReader(io.StringIO(b"".join(csv_chunks(rows, PAPER_CSV_FIELDS)).decode("utf-8-sig"))))
    assert result[0]["id"] == "'=1+1" and result[0]["net_roi"] == "'=1+1"
    assert result[0]["market_question"] == "'@SUM(1)" and result[0]["net_profit"] == "-2.000000"


def test_csv_cancellation_closes_its_source_iterator() -> None:
    class Rows:
        closed = False

        def __iter__(self) -> Iterator[dict[str, Any]]:
            yield {"id": 1}

        def close(self) -> None:
            self.closed = True

    rows = Rows()
    chunks = csv_chunks(rows, PAPER_CSV_FIELDS)
    assert next(chunks).startswith(b"\xef\xbb\xbf")
    chunks.close()
    assert rows.closed


@pytest.mark.parametrize(("platform", "install_uvloop"), [("win32", False), ("linux", True), ("darwin", True)])
def test_locked_native_dependencies_have_valid_platform_markers(platform: str, install_uvloop: bool) -> None:
    requirement = next(
        Requirement(line)
        for line in (ROOT / "requirements-lock.txt").read_text().splitlines()
        if line.startswith("uvloop==")
    )
    assert requirement.marker is not None
    assert requirement.marker.evaluate({"sys_platform": platform}) is install_uvloop


def test_reset_command_uses_custom_database_and_preserves_exports(tmp_path: Path, unused_tcp_port: int) -> None:
    custom = tmp_path / "custom/location/configured.db"
    custom.parent.mkdir(parents=True)
    database = Database(f"sqlite:///{custom}")
    database.initialize()
    database.upsert_setting("before_reset", "saved")
    database.close()
    exports = tmp_path / "exports/keep.csv"
    exports.parent.mkdir()
    exports.write_text("keep this export", encoding="utf-8")
    completed = cli(
        tmp_path,
        "scripts.reset_database",
        "--confirm",
        "RESET",
        env_updates={"PMS_DATABASE_URL": f"sqlite:///{custom}", "PMS_PORT": str(unused_tcp_port)},
    )
    assert completed.returncode == 0, completed.stderr
    assert str(custom) in completed.stdout
    reset = Database(f"sqlite:///{custom}")
    try:
        assert reset.health() and reset.settings() == {}
        assert exports.read_text(encoding="utf-8") == "keep this export"
        assert not (tmp_path / "data/scanner.db").exists()
    finally:
        reset.close()


def test_reset_cancellation_keeps_saved_data(tmp_path: Path, unused_tcp_port: int) -> None:
    assert cli(tmp_path, "scripts.init_db").returncode == 0
    database = Database(f"sqlite:///{tmp_path / 'cli.db'}")
    try:
        database.upsert_setting("keep", "saved")
        completed = cli(
            tmp_path, "scripts.reset_database", input_text="cancel\n", env_updates={"PMS_PORT": str(unused_tcp_port)}
        )
        assert completed.returncode == 1 and "Cancelled" in completed.stdout
        assert database.settings() == {"keep": "saved"}
    finally:
        database.close()


def test_reset_refuses_configured_active_port(tmp_path: Path) -> None:
    assert cli(tmp_path, "scripts.init_db").returncode == 0
    database = Database(f"sqlite:///{tmp_path / 'cli.db'}")
    try:
        database.upsert_setting("keep", "saved")
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            completed = cli(
                tmp_path,
                "scripts.reset_database",
                "--confirm",
                "RESET",
                env_updates={"PMS_PORT": str(server.getsockname()[1])},
            )
        assert completed.returncode == 1 and "port is active" in completed.stdout
        assert database.settings() == {"keep": "saved"}
    finally:
        database.close()


def test_reset_connection_errors_fail_closed_without_touching_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unused_tcp_port: int
) -> None:
    from app.config import Settings

    path = tmp_path / "preserved.db"
    database = Database(f"sqlite:///{path}")
    try:
        database.initialize()
        database.upsert_setting("keep", "saved")
        settings = Settings(_env_file=None, database_url=f"sqlite:///{path}", port=unused_tcp_port)
        monkeypatch.setattr(reset_database, "get_settings", lambda: settings)
        monkeypatch.setattr(sys, "argv", ["reset_database", "--confirm", "RESET"])

        def unable_to_probe(*args: Any, **kwargs: Any) -> None:
            raise OSError("simulated unavailable network stack")

        monkeypatch.setattr(reset_database.socket, "create_connection", unable_to_probe)
        assert reset_database.main() == 1
        assert database.settings() == {"keep": "saved"}
    finally:
        database.close()
