from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.config import EDITABLE_SETTING_KEYS, Settings
from app.database import Database, MarketRow, OpportunityRow, utc_iso
from app.models import DepthResult, FeeQuote, FeeStatus, Market, OrderBook, PriceLevel
from app.runtime import ScannerRuntime
from app.services.depth_calculator import calculate_depth


def sample_market() -> Market:
    return Market(
        market_id="1",
        condition_id="condition",
        event_id="event-one",
        question="Public question?",
        slug="original-question",
        category="sports",
        active=True,
        accepting_orders=True,
        enable_order_book=True,
        outcomes=["Yes", "No"],
        token_ids=["yes", "no"],
        yes_token_id="yes",
        no_token_id="no",
        liquidity=Decimal("2000"),
        volume=Decimal("1000"),
        fees_enabled=False,
    )


def sample_books() -> dict[str, OrderBook]:
    return {
        token: OrderBook(
            asset_id=token,
            market="condition",
            timestamp="1791028800000",
            asks=[PriceLevel(price=Decimal("0.4"), size=Decimal("10"))],
            min_order_size=Decimal("1"),
        )
        for token in ("yes", "no")
    }


def sample_result() -> DepthResult:
    books = sample_books()
    return calculate_depth(
        books["yes"],
        books["no"],
        Decimal("10"),
        FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0")),
        expected_condition_id="condition",
    )


def audit_context() -> dict[str, Any]:
    return {
        "source": "Polymarket public CLOB REST /books",
        "as_of": "2026-10-03T12:00:00+00:00",
        "market": sample_market().model_dump(mode="json"),
        "parameters": {"default_quantity": "10", "slippage_rate": "0.001", "extra_cost": "0"},
        "orderbooks": [book.model_dump(mode="json") for book in sample_books().values()],
    }


def assert_utc(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


@pytest.mark.asyncio
async def test_saved_parameters_are_applied_again_after_process_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    url = f"sqlite:///{tmp_path / 'restart.db'}"
    first = ScannerRuntime(Settings(_env_file=None, database_url=url, enable_live_scanner=False))
    parameters = {
        "minimum_net_profit": "0.2",
        "minimum_net_roi": "0.01",
        "default_quantity": "25",
        "slippage_rate": "0.02",
        "safety_rate": "0.03",
    }
    try:
        await first.start()
        await first.apply_parameters(parameters)
        assert all(getattr(first.settings, key) == value for key, value in parameters.items())
    finally:
        await first.stop()
    restarted = ScannerRuntime(Settings(_env_file=None, database_url=url, enable_live_scanner=False))
    try:
        await restarted.start()
        assert all(getattr(restarted.settings, key) == value for key, value in parameters.items())
        assert restarted.database.settings() == parameters
        assert restarted._tasks == set()
    finally:
        await restarted.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_value", ["NaN", "-1", "100001", "not-a-number"])
async def test_invalid_saved_group_falls_back_as_a_whole(
    bad_value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    url = f"sqlite:///{tmp_path / 'invalid.db'}"
    database = Database(url)
    database.initialize()
    database.upsert_settings({"minimum_net_profit": "0.99", "default_quantity": bad_value})
    database.close()
    settings = Settings(
        _env_file=None, database_url=url, enable_live_scanner=False, minimum_net_profit="0.15", default_quantity="12"
    )
    defaults = {key: getattr(settings, key) for key in EDITABLE_SETTING_KEYS}
    runtime = ScannerRuntime(settings)
    try:
        await runtime.start()
        assert {key: getattr(runtime.settings, key) for key in EDITABLE_SETTING_KEYS} == defaults
        assert any(row.source == "CONFIG" for row in runtime.database.list_events())
        assert runtime.database.settings()["minimum_net_profit"] == "0.99"
    finally:
        await runtime.stop()


def test_multi_setting_write_rolls_back_first_key_when_second_write_fails(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'atomic.db'}")
    try:
        database.initialize()
        database.upsert_settings({"first": "old-one", "second": "old-two"})
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER reject_second BEFORE UPDATE OF value ON application_settings "
                "WHEN NEW.key = 'second' BEGIN SELECT RAISE(ABORT, 'forced second-key failure'); END"
            )
        with pytest.raises(IntegrityError):
            database.upsert_settings({"first": "new-one", "second": "new-two"})
        assert database.settings() == {"first": "old-one", "second": "old-two"}
    finally:
        database.close()


def test_history_disappears_reactivates_and_becomes_unverified_after_restart(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'history.db'}"
    database = Database(url)
    market, result = sample_market(), sample_result()
    try:
        database.initialize()
        database.upsert_opportunity(market, result, audit_context=audit_context())
        initial = database.list_opportunities()[0]
        assert initial["status"] == "active" and initial["disappeared_reason"] is None
        database.reconcile_opportunities({result.snapshot_fingerprint}, "still present")
        assert database.list_opportunities()[0]["status"] == "active"
        database.reconcile_opportunities(set(), "depth changed")
        assert database.list_opportunities()[0]["status"] == "disappeared"
        assert database.list_opportunities()[0]["disappeared_reason"] == "depth changed"
        revised = result.model_copy(update={"net_profit": Decimal("3"), "net_roi": Decimal("0.4")})
        database.upsert_opportunity(market, revised, audit_context=audit_context())
        active = database.list_opportunities()[0]
        assert len(database.list_opportunities()) == 1
        assert active["status"] == "active" and active["disappeared_reason"] is None
        assert active["first_seen"] == initial["first_seen"]
        assert Decimal(active["max_net_profit"]) == Decimal("3")
    finally:
        database.close()
    restarted = Database(url)
    try:
        restarted.initialize()
        row = restarted.list_opportunities()[0]
        assert row["status"] == "disappeared" and "重启" in row["disappeared_reason"]
        detail = restarted.get_opportunity_details(row["id"])
        assert detail is not None and detail["details"]["audit"] == audit_context()
    finally:
        restarted.close()


def test_market_metadata_updates_and_unique_token_order_can_be_swapped(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'metadata.db'}")
    try:
        database.initialize()
        original = sample_market()
        database.upsert_market(original)
        payload = original.model_dump()
        payload.update(
            {
                "question": "Updated question?",
                "slug": "updated-question",
                "event_id": "event-two",
                "category": "weather",
                "outcomes": ["No", "Yes"],
                "token_ids": ["no", "yes"],
                "liquidity": Decimal("4000"),
                "volume": Decimal("1500"),
            }
        )
        database.upsert_market(Market.model_validate(payload))
        with database.Session() as session:
            row = session.get(MarketRow, "1")
            assert row is not None
            assert (row.question, row.slug, row.event_id, row.category) == (
                "Updated question?",
                "updated-question",
                "event-two",
                "weather",
            )
            assert (Decimal(row.liquidity), Decimal(row.volume)) == (Decimal("4000"), Decimal("1500"))
            tokens = sorted(row.tokens, key=lambda token: token.outcome_index)
            assert [(token.outcome, token.token_id, token.outcome_index) for token in tokens] == [
                ("No", "no", 0),
                ("Yes", "yes", 1),
            ]
            assert_utc(utc_iso(row.updated_at))
    finally:
        database.close()


def test_failed_simulations_are_excluded_from_profit_and_details_preserve_audit(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'audit.db'}")
    market, result, context = sample_market(), sample_result(), audit_context()
    try:
        database.initialize()
        trade_id = database.add_paper_trade(market, result, audit_context=context)
        failed_id = database.add_paper_trade(
            market, result.model_copy(update={"status": "STALE"}), audit_context=context
        )
        assert database.paper_trade_count() == 2
        assert database.paper_profit_total() == result.net_profit
        successful = database.get_paper_trade_details(trade_id)
        failed = database.get_paper_trade_details(failed_id)
        assert successful is not None and failed is not None
        assert successful["status"] == "SUCCESS" and failed["status"] == "FAILED"
        assert failed["failure_reason"] == "STALE"
        assert successful["details"]["audit"] == failed["details"]["audit"] == context
        assert successful["details"]["snapshot_fingerprint"] == result.snapshot_fingerprint
        assert_utc(successful["created_at"])
        database.upsert_opportunity(market, result, audit_context=context)
        row = database.list_opportunities()[0]
        assert "details" not in row and "audit" not in row
        detail = database.get_opportunity_details(row["id"])
        assert detail is not None and detail["details"]["audit"] == context
        assert detail["details"]["yes_cost"] == str(result.yes_cost)
        assert_utc(detail["first_seen"])
        assert_utc(detail["last_seen"])
        assert database.get_paper_trade_details(9999) is database.get_opportunity_details(9999) is None
    finally:
        database.close()


def test_summary_queries_do_not_load_large_audit_payloads(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'summary.db'}")
    statements: list[str] = []

    def record_query(
        connection: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        statements.append(statement)

    try:
        database.initialize()
        database.upsert_opportunity(sample_market(), sample_result(), audit_context=audit_context())
        database.add_paper_trade(sample_market(), sample_result(), audit_context=audit_context())
        event.listen(database.engine, "before_cursor_execute", record_query)
        assert len(database.list_opportunities()) == len(database.list_paper_trades()) == 1
        assert len(list(database.iter_opportunities())) == len(list(database.iter_paper_trades())) == 1
        assert statements and all("payload_json" not in statement for statement in statements)
    finally:
        event.remove(database.engine, "before_cursor_execute", record_query)
        database.close()


def test_utc_formatter_normalizes_explicit_offset_and_sqlite_naive_times() -> None:
    assert utc_iso(datetime(2026, 10, 3, 8, tzinfo=timezone(timedelta(hours=8)))) == "2026-10-03T00:00:00+00:00"
    assert utc_iso(datetime(2026, 10, 3, 0)) == "2026-10-03T00:00:00+00:00"


def test_nonfinite_audit_payload_is_rejected_without_partial_record(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'invalid-audit.db'}")
    try:
        database.initialize()
        for write in (database.add_paper_trade, database.upsert_opportunity):
            with pytest.raises(ValueError):
                write(sample_market(), sample_result(), audit_context={"bad": float("nan")})
        assert database.paper_trade_count() == 0
        with database.Session() as session:
            assert session.scalars(select(OpportunityRow)).all() == []
    finally:
        database.close()
