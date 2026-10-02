from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

from app.database import PaperTradeRow
from app.main import app
from app.models import FeeQuote, FeeStatus, OrderBook, PriceLevel
from app.services.catalog import CatalogSnapshot
from app.services.depth_calculator import calculate_depth
from app.services.market_discovery import normalize_market


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


def test_deliberate_offline_mode_is_identifiable_without_upstream_requests(client):
    status = client.get("/api/system/status").json()
    catalog = client.get("/api/catalog").json()
    assert status["live_scanner_enabled"] is False
    assert catalog["liveScannerEnabled"] is False
    assert status["public_http"]["calls"] == 0
    assert catalog["total"] == 0


def install_market(rt):
    raw = {
        "id": "1",
        "conditionId": "condition",
        "question": "Sample?",
        "event": "Sample event",
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "feesEnabled": False,
        "clobTokenIds": ["y", "n"],
        "outcomes": ["Yes", "No"],
    }
    item = {
        **raw,
        "tokens": ["y", "n"],
        "category": "sports",
        "volume24h": 100,
        "volume": 100,
        "liquidity": 100,
        "description": "Public rules.",
        "prices": [0.4, 0.4],
    }
    rt.catalog._snapshot = CatalogSnapshot(items={"1": item}, raw={"1": raw})
    timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
    books = {
        token: OrderBook(
            asset_id=token,
            market="condition",
            timestamp=timestamp,
            min_order_size=Decimal("1"),
            asks=[PriceLevel(price=Decimal("0.4"), size=Decimal("1000"))],
        )
        for token in ("y", "n")
    }
    return raw, books


@pytest.mark.parametrize(
    "change",
    [
        None,
        {"closed": True},
        {"acceptingOrders": False},
        {"conditionId": "other"},
        {"clobTokenIds": ["n", "y"]},
        {"outcomes": ["No", "Yes"]},
    ],
)
def test_inspection_pauses_unavailable_or_changed_identity(client, monkeypatch, change):
    rt = app.state.runtime
    raw, _ = install_market(rt)

    async def metadata(ids):
        return [] if change is None else [{**raw, **change}]

    async def unexpected_books(ids):
        pytest.fail("A closed or changed market must not fetch its old books")

    monkeypatch.setattr(rt.gamma, "fetch_markets_by_ids", metadata)
    monkeypatch.setattr(rt.clob, "fetch_books", unexpected_books)
    response = client.get("/api/inspect/1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["unavailableReason"] and payload["metadataAsOf"]
    assert payload["calculation"] is None
    assert payload["books"] == [None, None]


@pytest.mark.parametrize(
    "kind,expected", [("minimum", "MIN_ORDER_UNKNOWN"), ("crossed", "CROSSED_BOOK"), ("foreign", "INVALID_PAIR")]
)
def test_inspection_preserves_structural_rejection(client, monkeypatch, kind, expected):
    rt = app.state.runtime
    _, books = install_market(rt)
    if kind == "minimum":
        books["y"].min_order_size = None
    elif kind == "crossed":
        books["y"].bids = [PriceLevel(price=Decimal("0.6"), size=Decimal("10"))]
        books["y"].timestamp = "NaN"
    else:
        books["y"].market = books["n"].market = "foreign"

    async def fetch_books(ids):
        return books

    monkeypatch.setattr(rt.clob, "fetch_books", fetch_books)
    payload = client.get("/api/inspect/1?quantity=10").json()
    assert payload["available"] is True
    assert payload["calculation"]["status"] == expected


def test_inspection_uses_current_fee_metadata(client, monkeypatch):
    rt = app.state.runtime
    raw, books = install_market(rt)

    async def metadata(ids):
        return [{**raw, "feesEnabled": True}]

    async def fetch_books(ids):
        return books

    monkeypatch.setattr(rt.gamma, "fetch_markets_by_ids", metadata)
    monkeypatch.setattr(rt.clob, "fetch_books", fetch_books)
    payload = client.get("/api/inspect/1").json()
    assert payload["calculation"]["status"] == "FEE_UNKNOWN"
    assert payload["calculation"]["net_profit"] is None


def test_inspection_metadata_error_fails_without_using_old_books(client, monkeypatch):
    rt = app.state.runtime
    install_market(rt)

    async def metadata(ids):
        raise RuntimeError("public endpoint unavailable")

    monkeypatch.setattr(rt.gamma, "fetch_markets_by_ids", metadata)
    assert client.get("/api/inspect/1").status_code == 502


@pytest.mark.parametrize(
    "query", ["category=invalid", "sort=invalid", "min_liquidity=inf", "min_liquidity=NaN", "search=" + "x" * 501]
)
def test_catalog_rejects_bad_queries(client, query):
    assert client.get("/api/catalog?" + query).status_code == 422


def test_database_failure_reports_degraded_health(client, monkeypatch):
    monkeypatch.setattr(app.state.runtime.database, "health", lambda: False)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_csv_exports_all_rows_and_escapes_only_text(client):
    database = app.state.runtime.database
    rows = [
        {
            "market_id": "1",
            "market_question": ' =HYPERLINK("example")',
            "target_quantity": "1",
            "executable_quantity": "1",
            "total_cost": "2",
            "net_profit": "-1",
            "net_roi": "-0.5",
            "status": "SUCCESS",
            "payload_json": "{}",
        }
        for _ in range(5001)
    ]
    with database.Session.begin() as session:
        session.execute(insert(PaperTradeRow), rows)
    response = client.get("/api/exports/paper-trades.csv")
    assert response.content.startswith(b"\xef\xbb\xbf")
    parsed = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(parsed) == 5001
    assert parsed[0]["market_question"].startswith("' =")
    assert parsed[0]["net_profit"] == "-1"
    assert parsed[0]["created_at"].endswith("+00:00")
    assert len(client.get("/api/paper-trades?offset=5000").json()["items"]) == 1


def test_empty_exports_have_stable_headers_and_missing_details_are_404(client):
    for endpoint in ("paper-trades", "opportunities"):
        response = client.get(f"/api/exports/{endpoint}.csv")
        parsed = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert len(parsed) == 1 and parsed[0][0] == "id"
    assert client.get("/api/paper-trades/999").status_code == 404
    assert client.get("/api/opportunities/history/999").status_code == 404


def test_record_details_return_original_audit_inputs(client):
    rt = app.state.runtime
    raw, books = install_market(rt)
    market = normalize_market(raw)
    result = calculate_depth(
        books["y"], books["n"], Decimal("10"), FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0"))
    )
    audit = {"source": "public CLOB REST", "orderbooks": [book.model_dump(mode="json") for book in books.values()]}
    identifier = rt.database.add_paper_trade(market, result, audit_context=audit)
    rt.database.upsert_opportunity(market, result, audit_context=audit)
    payload = client.get(f"/api/paper-trades/{identifier}").json()
    assert payload["details"]["audit"] == audit
    assert payload["created_at"].endswith("+00:00")
    historical = client.get("/api/opportunities/history/1").json()
    assert historical["details"]["audit"] == audit
    assert "details" not in client.get("/api/opportunities/history").json()["items"][0]


def test_logs_report_utc_timestamps(client):
    app.state.runtime.database.add_event("INFO", "TEST", "time_check", "Public test event")
    payload = client.get("/api/logs").json()
    assert payload["items"][0]["created_at"].endswith("+00:00")


def test_settings_use_active_runtime_and_do_not_modify_global_defaults(client):
    from app.main import settings

    before = settings.model_dump()
    response = client.put(
        "/api/settings",
        json={
            "minimum_net_profit": "0.2",
            "minimum_net_roi": "0.01",
            "default_quantity": "30",
            "slippage_rate": "0.002",
            "safety_rate": "0.003",
        },
    )
    assert response.status_code == 200
    assert client.get("/api/settings").json() == response.json()
    assert app.state.runtime.settings.default_quantity == "30"
    assert settings.model_dump() == before


@pytest.mark.parametrize("stage", ["runtime", "translation"])
def test_startup_failure_closes_runtime_resources(monkeypatch, stage):
    from app.runtime import ScannerRuntime
    from app.services.translation import TranslationService

    original_stop = ScannerRuntime.stop
    stopped = []

    async def stop(self):
        await original_stop(self)
        stopped.append(self.http._client.is_closed)

    async def fail(self):
        raise RuntimeError("startup failure")

    monkeypatch.setattr(ScannerRuntime, "stop", stop)
    monkeypatch.setattr(ScannerRuntime if stage == "runtime" else TranslationService, "start", fail)
    with pytest.raises(RuntimeError, match="startup failure"), TestClient(app):
        pass
    assert stopped == [True]
