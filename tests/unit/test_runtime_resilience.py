from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import app.runtime as runtime_module
from app.config import Settings
from app.database import PaperTradeRow
from app.models import OrderBook
from app.runtime import ScannerRuntime
from app.services.orderbooks import normalize_orderbook


def raw_market(market_id: str = "old", **changes: Any) -> dict[str, Any]:
    return {
        "id": market_id,
        "conditionId": f"condition-{market_id}",
        "question": f"Question {market_id}?",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": [f"yes-{market_id}", f"no-{market_id}"],
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "liquidityNum": "2000",
        "feesEnabled": False,
        **changes,
    }


def fresh_books(tokens: list[str]) -> dict[str, OrderBook]:
    timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
    return {
        token: normalize_orderbook(
            {
                "asset_id": token,
                "timestamp": timestamp,
                "min_order_size": "1",
                "asks": [{"price": "0.4", "size": "100"}],
            }
        )
        for token in tokens
    }


async def scanner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ScannerRuntime:
    runtime = ScannerRuntime(Settings(enable_live_scanner=False, database_url=f"sqlite:///{tmp_path / 'runtime.db'}"))
    await runtime.start()

    async def fetch_markets(maximum: int) -> list[dict[str, Any]]:
        return [raw_market()]

    async def fetch_books(tokens: list[str]) -> dict[str, OrderBook]:
        return fresh_books(tokens)

    monkeypatch.setattr(runtime.gamma, "fetch_markets", fetch_markets)
    monkeypatch.setattr(runtime.clob, "fetch_books", fetch_books)
    await runtime.refresh_markets()
    return runtime


@pytest.mark.asyncio
async def test_market_change_waits_for_book_publication_and_removes_old_state(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    requested: list[str] = []

    async def blocked_books(tokens: list[str]) -> dict[str, OrderBook]:
        requested.extend(tokens)
        entered.set()
        await release.wait()
        return fresh_books(tokens)

    async def new_markets(maximum: int) -> list[dict[str, Any]]:
        return [raw_market("new")]

    monkeypatch.setattr(runtime.clob, "fetch_books", blocked_books)
    monkeypatch.setattr(runtime.gamma, "fetch_markets", new_markets)
    books_task = asyncio.create_task(runtime.refresh_books_and_scan())
    markets_task = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        markets_task = asyncio.create_task(runtime.refresh_markets())
        await asyncio.sleep(0)
        assert not markets_task.done()
        assert set(runtime.markets) == {"old"}
        release.set()
        await asyncio.gather(books_task, markets_task)
        assert requested == ["yes-old", "no-old"]
        assert set(runtime.markets) == {"new"}
        assert runtime.results == runtime.books == runtime.fee_reasons == {}
        assert runtime.status.opportunity_count == 0
        assert runtime.websocket.tokens == {"yes-new", "no-new"}
        assert runtime.database.list_opportunities()[0]["status"] == "disappeared"
    finally:
        release.set()
        await runtime.stop()


@pytest.mark.asyncio
async def test_calculation_error_does_not_escape_and_next_refresh_recovers(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    original = runtime_module.calculate_depth
    calls = 0

    def fail_once(*args: Any, **kwargs: Any):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("malformed book")
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime_module, "calculate_depth", fail_once)
    try:
        await runtime.refresh_books_and_scan()
        assert runtime.results == {}
        assert runtime.status.opportunity_count == 0
        assert runtime.status.clob_status.startswith("错误")
        await runtime.refresh_books_and_scan()
        assert runtime.results["old"].status == "VALID"
        assert runtime.status.clob_status == "正常"
        assert runtime.status.opportunity_count == 1
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_book_loop_survives_unexpected_refresh_failure(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    runtime.settings = runtime.settings.model_copy(update={"rest_refresh_seconds": 0.001})
    calls = 0

    async def failing_refresh():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("refresh failed")
        runtime._stop.set()

    monkeypatch.setattr(runtime, "refresh_books_and_scan", failing_refresh)
    try:
        await asyncio.wait_for(runtime._book_loop(), 1)
        assert calls == 2
        assert "RuntimeError" in runtime.status.recent_error
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_error_event_write_failure_cannot_kill_scan(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)

    async def failing_books(tokens: list[str]):
        raise RuntimeError("upstream unavailable")

    def failing_event(*args: Any, **kwargs: Any):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(runtime.clob, "fetch_books", failing_books)
    monkeypatch.setattr(runtime.database, "add_event", failing_event)
    try:
        await runtime.refresh_books_and_scan()
        assert runtime.results == {}
        assert runtime.status.opportunity_count == 0
        assert runtime.status.clob_status.startswith("错误")
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_older_unknown_or_unsubscribed_ws_book_cannot_replace_rest_display(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        current = runtime.books["yes-old"]
        for token, timestamp in [
            ("yes-old", str(Decimal(current.timestamp) - 1000)),
            ("yes-old", "NaN"),
            ("foreign", current.timestamp),
        ]:
            await runtime.handle_websocket(
                {
                    "event_type": "book",
                    "asset_id": token,
                    "timestamp": timestamp,
                    "asks": [{"price": "0.9", "size": "100"}],
                }
            )
        assert runtime.books["yes-old"] is current
        assert "foreign" not in runtime.books
        # Equal timestamps may still contain an updated full snapshot.
        await runtime.handle_websocket(
            {
                "event_type": "book",
                "asset_id": "yes-old",
                "timestamp": current.timestamp,
                "asks": [{"price": "0.45", "size": "100"}],
            }
        )
        assert runtime.books["yes-old"].best_ask == Decimal("0.45")
        assert runtime.results["old"].yes_average_price == Decimal("0.4")
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_parameters_restore_on_restart_and_invalid_group_preserves_env(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    settings = runtime.settings
    try:
        await runtime.refresh_books_and_scan()
        await runtime.apply_parameters({"default_quantity": "25", "minimum_net_profit": "0.2"})
        assert runtime.settings.default_quantity == "25"
        assert settings.default_quantity == "10"
        assert runtime.results == {}
        assert runtime.status.opportunity_count == 0
        assert runtime.database.list_opportunities()[0]["status"] == "disappeared"
    finally:
        await runtime.stop()
    restarted = ScannerRuntime(settings)
    try:
        await restarted.start()
        assert restarted.settings.default_quantity == "25"
        assert restarted.settings.minimum_net_profit == "0.2"
        restarted.database.upsert_settings({"slippage_rate": "NaN"})
    finally:
        await restarted.stop()
    invalid = ScannerRuntime(settings)
    try:
        await invalid.start()
        assert invalid.settings.default_quantity == settings.default_quantity
        assert invalid.settings.slippage_rate == settings.slippage_rate
        assert invalid.status.recent_error is not None
        assert invalid.status.recent_error.startswith("ValueError:")
        assert "NaN" not in invalid.status.recent_error
    finally:
        await invalid.stop()


@pytest.mark.asyncio
async def test_failed_parameter_persistence_preserves_live_settings_and_results(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        settings, results = runtime.settings, runtime.results

        def fail(*args: Any):
            raise RuntimeError("write failed")

        monkeypatch.setattr(runtime.database, "upsert_settings", fail)
        with pytest.raises(RuntimeError, match="write failed"):
            await runtime.apply_parameters({"default_quantity": "25"})
        assert runtime.settings is settings
        assert runtime.results is results
        assert runtime.status.opportunity_count == 1
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_paper_trade_waits_for_parameter_update_and_rejects_previous_result(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        async with runtime._refresh_lock:
            parameters = asyncio.create_task(runtime.apply_parameters({"default_quantity": "25"}))
            await asyncio.sleep(0)
            paper = asyncio.create_task(runtime.create_paper_trade("old"))
            await asyncio.sleep(0)
            assert not paper.done()
        await parameters
        with pytest.raises(ValueError, match="实时订单簿"):
            await paper
        assert runtime.database.paper_trade_count() == 0
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_verified_resolution_removes_candidate_and_stale_discovery_cannot_revive(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        assert runtime.status.opportunity_count == 1
        await runtime.handle_websocket(
            {
                "event_type": "market_resolved",
                "id": "old",
                "market": "condition-old",
                "assets_ids": ["yes-old", "no-old"],
                "winning_asset_id": "yes-old",
            }
        )
        assert runtime.markets == runtime.results == runtime.books == runtime.calculation_books == {}
        assert runtime.websocket.tokens == set()
        assert runtime.status.opportunity_count == 0
        assert runtime.database.list_opportunities()[0]["status"] == "disappeared"
        await runtime.refresh_markets()
        assert runtime.markets == {}
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_resolution_cannot_remove_different_condition_or_unknown_tokens(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    try:
        for condition, tokens, winner in [
            ("foreign", ["yes-old", "no-old"], "yes-old"),
            ("condition-old", ["yes-old", "foreign"], "yes-old"),
            ("condition-old", ["yes-old", "no-old"], "foreign"),
        ]:
            await runtime.handle_websocket(
                {
                    "event_type": "market_resolved",
                    "id": "old",
                    "market": condition,
                    "assets_ids": tokens,
                    "winning_asset_id": winner,
                }
            )
        assert set(runtime.markets) == {"old"}
        assert not runtime.catalog.is_resolved("old")
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_paper_record_persists_rest_inputs_even_after_ws_display_change(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        current = runtime.books["yes-old"]
        await runtime.handle_websocket(
            {
                "event_type": "book",
                "asset_id": "yes-old",
                "timestamp": current.timestamp,
                "asks": [{"price": "0.7", "size": "100"}],
            }
        )
        trade_id = await runtime.create_paper_trade("old")
        assert trade_id > 0
        assert runtime.books["yes-old"].best_ask == Decimal("0.7")
        assert runtime.calculation_books["yes-old"].best_ask == Decimal("0.4")
        with runtime.database.Session() as session:
            stored = session.get(PaperTradeRow, trade_id)
            assert stored is not None
            record = json.loads(stored.payload_json)
        assert record["audit"]["source"] == "Polymarket public CLOB REST /books"
        assert record["audit"]["orderbooks"][0]["asset_id"] == "yes-old"
        assert record["audit"]["orderbooks"][0]["asks"][0]["price"] == "0.4"
        assert record["audit"]["parameters"]["default_quantity"] == "10"
        assert record["audit"]["as_of"] is not None
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_missing_min_order_size_is_unknown_and_never_a_candidate(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)

    async def unknown_minimum(tokens: list[str]):
        books = fresh_books(tokens)
        books[tokens[0]].min_order_size = None
        return books

    monkeypatch.setattr(runtime.clob, "fetch_books", unknown_minimum)
    try:
        await runtime.refresh_books_and_scan()
        assert runtime.results["old"].status == "MIN_ORDER_UNKNOWN"
        assert runtime.results["old"].net_profit > 0
        assert runtime.status.opportunity_count == 0
        assert not runtime.valid_opportunity(runtime.markets["old"], runtime.results["old"])
        with pytest.raises(ValueError, match="未通过全部机会门槛"):
            await runtime.create_paper_trade("old")
    finally:
        await runtime.stop()


def catalog_sample(runtime: ScannerRuntime, raws: list[dict[str, Any]]) -> None:
    items, originals = {}, {}
    runtime.catalog.ingest([{"id": "event", "title": "Event", "markets": raws}], items, originals)
    runtime.catalog._publish(items, originals, "sample")


@pytest.mark.asyncio
async def test_scanner_verifies_current_flags_before_reusing_catalog_sample(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    catalog_sample(runtime, [raw_market("closed"), raw_market("paused"), raw_market("missing"), raw_market("live")])

    async def current_markets(ids: list[str]):
        assert set(ids) == {"closed", "paused", "missing", "live"}
        return [raw_market("closed", closed=True), raw_market("paused", acceptingOrders=False), raw_market("live")]

    monkeypatch.setattr(runtime.gamma, "fetch_markets_by_ids", current_markets)
    try:
        await runtime.refresh_markets()
        assert set(runtime.markets) == {"live"}
        assert runtime.websocket.tokens == {"yes-live", "no-live"}
        verification = runtime.catalog.summary()["scannerSelection"]["verification"]
        assert verification["requestedTotal"] == 4
        assert verification["verifiedTotal"] == 1
        assert sum(verification["categoryCounts"].values()) == 1
        assert not verification["failed"]
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_gamma_failure_clears_old_candidates_and_books_cannot_reactivate_them(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        assert runtime.valid_opportunity(runtime.markets["old"], runtime.results["old"])
        previous_market = runtime.markets["old"]
        previous_result = runtime.results["old"]
        catalog_sample(runtime, [raw_market()])

        async def fail_metadata(ids: list[str]):
            raise RuntimeError("Gamma unavailable")

        monkeypatch.setattr(runtime.gamma, "fetch_markets_by_ids", fail_metadata)
        await runtime.refresh_markets()
        assert set(runtime.markets) == {"old"}
        assert runtime.results == runtime.calculation_books == {}
        assert runtime.status.gamma_status.startswith("错误")
        assert not runtime.valid_opportunity(previous_market, previous_result)
        await runtime.refresh_books_and_scan()
        assert runtime.results == runtime.calculation_books == {}
        assert runtime.status.clob_status == "正常"
        assert runtime.database.list_opportunities()[0]["status"] == "disappeared"
        assert runtime.catalog.summary()["scannerSelection"]["verification"]["failed"]
    finally:
        await runtime.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"conditionId": "foreign"},
        {"outcomes": ["No", "Yes"], "clobTokenIds": ["no-old", "yes-old"]},
        {"clobTokenIds": ["yes-old", "foreign"]},
    ],
)
async def test_changed_settlement_identity_cannot_reuse_catalog_mapping(tmp_path, monkeypatch, changes):
    runtime = await scanner(tmp_path, monkeypatch)
    catalog_sample(runtime, [raw_market()])

    async def changed_metadata(ids: list[str]):
        return [raw_market(**changes)]

    monkeypatch.setattr(runtime.gamma, "fetch_markets_by_ids", changed_metadata)
    try:
        await runtime.refresh_markets()
        assert runtime.status.gamma_status.startswith("错误")
        assert runtime.results == {}
        assert runtime.status.opportunity_count == 0
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_current_source_times_reject_candidate_after_clock_rollback(tmp_path, monkeypatch):
    from datetime import timedelta
    from types import SimpleNamespace

    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        market, result = runtime.markets["old"], runtime.results["old"]
        assert runtime.valid_opportunity(market, result)
        now = datetime.now(UTC)
        monkeypatch.setattr(
            runtime_module, "datetime", SimpleNamespace(now=lambda _timezone: now - timedelta(seconds=10))
        )
        assert not runtime.valid_opportunity(market, result)
        with pytest.raises(ValueError, match="过期"):
            await runtime.create_paper_trade("old")
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_two_matching_foreign_conditions_are_not_this_known_market(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)

    async def foreign_conditions(tokens: list[str]):
        books = fresh_books(tokens)
        for book in books.values():
            book.market = "foreign-condition"
        return books

    monkeypatch.setattr(runtime.clob, "fetch_books", foreign_conditions)
    try:
        await runtime.refresh_books_and_scan()
        assert runtime.results["old"].status == "INVALID_PAIR"
        assert runtime.results["old"].net_profit is None
        assert runtime.status.opportunity_count == 0
    finally:
        await runtime.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["expired", "missing", "rollback"])
async def test_payload_relabels_aged_calculation_without_mutating_original(tmp_path, monkeypatch, problem):
    from datetime import timedelta
    from types import SimpleNamespace

    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        market, result = runtime.markets["old"], runtime.results["old"]
        assert runtime.market_payload(market)["calculation"]["status"] == "VALID"
        now = datetime.now(UTC)
        if problem == "expired":
            monkeypatch.setattr(
                runtime_module,
                "datetime",
                SimpleNamespace(
                    now=lambda _timezone: now + timedelta(seconds=runtime.settings.max_quote_age_seconds + 10)
                ),
            )
        elif problem == "rollback":
            monkeypatch.setattr(
                runtime_module, "datetime", SimpleNamespace(now=lambda _timezone: now - timedelta(seconds=10))
            )
        else:
            runtime.calculation_books["yes-old"].timestamp = "NaN"
        payload = runtime.market_payload(market)
        assert payload["calculation"]["status"] == "STALE"
        assert not payload["is_candidate"]
        assert result.status == "VALID"
        if problem != "expired":
            assert payload["calculation"]["quote_age"] == "999999"
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_expired_payload_preserves_structural_invalid_status(tmp_path, monkeypatch):
    runtime = await scanner(tmp_path, monkeypatch)
    try:
        await runtime.refresh_books_and_scan()
        runtime.results["old"].status = "INVALID_PAIR"
        runtime.calculation_books["yes-old"].timestamp = "NaN"
        payload = runtime.market_payload(runtime.markets["old"])
        assert payload["calculation"]["status"] == "INVALID_PAIR"
        assert not payload["is_candidate"]
    finally:
        await runtime.stop()
