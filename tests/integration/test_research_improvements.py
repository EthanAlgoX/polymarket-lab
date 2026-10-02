from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app, book_analysis
from app.models import OrderBook, PriceLevel
from app.services.catalog import CatalogSnapshot


def catalog_row(market_id: str) -> dict:
    return {
        "id": market_id,
        "question": "Which team wins?",
        "event": "Sample event",
        "eventId": "e1",
        "slug": "sample",
        "category": "sports",
        "tags": [],
        "outcomes": ["No", "Yes"],
        "tokens": ["n", "y"],
        "prices": [0.25, 0.73],
        "volume24h": 100,
        "volume": 1000,
        "liquidity": 500,
        "description": "Public rules.",
    }


def test_catalog_response_uses_one_revision_even_if_publication_changes(monkeypatch) -> None:
    monkeypatch.setattr("app.main.deepseek_key", lambda: "")
    with TestClient(app) as client:
        catalog = app.state.runtime.catalog
        first = CatalogSnapshot(items={"1": catalog_row("1")}, revision=7, updated_at="2026-10-03T00:00:00Z")
        second = CatalogSnapshot(items={"2": catalog_row("2"), "3": catalog_row("3")}, revision=8)
        catalog._snapshot = first
        summary = catalog.summary

        def publish_during_response(snapshot=None):
            catalog._snapshot = second
            return summary(snapshot)

        monkeypatch.setattr(catalog, "summary", publish_during_response)
        response = client.get("/api/catalog?limit=1")
        response.raise_for_status()
        data = response.json()
        assert data["revision"] == 7
        assert data["total"] == data["filteredTotal"] == 1
        assert data["items"][0]["id"] == "1"
        assert sum(category["count"] for category in data["categories"]) == 1
        assert catalog.snapshot.revision == 8


def test_inspect_metrics_keep_token_order_and_unknown_fee_gate(monkeypatch) -> None:
    monkeypatch.setattr("app.main.deepseek_key", lambda: "")
    with TestClient(app) as client:
        rt = app.state.runtime
        row = catalog_row("1")
        raw = {
            **row,
            "conditionId": "condition",
            "clobTokenIds": ["n", "y"],
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "enableOrderBook": True,
            "feesEnabled": True,
        }
        rt.catalog._snapshot = CatalogSnapshot(items={"1": row}, raw={"1": raw})
        timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
        books = {
            token: OrderBook(
                asset_id=token,
                timestamp=timestamp,
                bids=[PriceLevel(price=Decimal(bid), size=Decimal("100"))],
                asks=[PriceLevel(price=Decimal(ask), size=Decimal("100"))],
            )
            for token, bid, ask in [("n", "0.24", "0.25"), ("y", "0.70", "0.73")]
        }

        async def fetch_books(tokens):
            assert tokens == ["n", "y"]
            return books

        monkeypatch.setattr(rt.clob, "fetch_books", fetch_books)
        response = client.get("/api/inspect/1")
        response.raise_for_status()
        data = response.json()
        assert data["outcomes"] == ["No", "Yes"] and data["tokens"] == ["n", "y"]
        assert [metric["asset_id"] for metric in data["book_analytics"]] == ["n", "y"]
        assert [metric["best_ask"] for metric in data["book_analytics"]] == ["0.25", "0.73"]
        assert all(metric["stale"] is False for metric in data["book_analytics"])
        assert data["calculation"]["status"] == "FEE_UNKNOWN"
        assert data["calculation"]["net_profit"] is None
        status = client.get("/api/system/status").json()
        assert status["public_http"]["attempts"] == 0
        assert "scanner_selection" in status


def test_metric_freshness_does_not_turn_unknown_or_old_time_into_fresh() -> None:
    for timestamp in ("", "NaN", "Infinity", "0", "1700000000000", "9999999999999"):
        result = book_analysis(OrderBook(asset_id="y", timestamp=timestamp), Decimal("5"))
        assert result is not None and result["stale"] is True
    assert book_analysis(None, Decimal("5")) is None


@pytest.mark.parametrize(
    ("bad_timestamp", "max_age"),
    [("NaN", 5), ("Infinity", 5), ("9999999999999", 5), ("", 5), ("0", 5), ("NaN", 1000000)],
)
def test_inspect_invalid_source_age_is_stale_despite_positive_zero_fee_math(
    monkeypatch, bad_timestamp, max_age
) -> None:
    monkeypatch.setattr("app.main.deepseek_key", lambda: "")
    with TestClient(app) as client:
        rt = app.state.runtime
        original_max_age = rt.settings.max_quote_age_seconds
        monkeypatch.setattr(rt.settings, "max_quote_age_seconds", max_age)
        row = catalog_row("1")
        raw = {
            **row,
            "conditionId": "condition",
            "clobTokenIds": ["n", "y"],
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "enableOrderBook": True,
            "feesEnabled": False,
        }
        rt.catalog._snapshot = CatalogSnapshot(items={"1": row}, raw={"1": raw})
        timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
        books = {
            token: OrderBook(
                asset_id=token,
                timestamp=source_time,
                asks=[PriceLevel(price=Decimal("0.4"), size=Decimal("1000"))],
            )
            for token, source_time in (("n", bad_timestamp), ("y", timestamp))
        }

        async def fetch_books(tokens):
            assert tokens == ["n", "y"]
            return books

        monkeypatch.setattr(rt.clob, "fetch_books", fetch_books)
        response = client.get("/api/inspect/1")
        response.raise_for_status()
        data = response.json()
        assert data["book_analytics"][0]["stale"] is True
        assert data["book_analytics"][0]["quote_age_seconds"] is None
        assert data["book_analytics"][1]["stale"] is False
        assert data["calculation"]["status"] == "STALE"
        assert Decimal(data["calculation"]["quote_age"]) >= Decimal("999999")
        assert Decimal(data["calculation"]["estimated_fees"]) == Decimal("0")
        assert Decimal(data["calculation"]["net_profit"]) > 0
        assert data["outcomes"] == ["No", "Yes"]
        assert [book["asset_id"] for book in data["books"]] == ["n", "y"]
        monkeypatch.setattr(rt.settings, "max_quote_age_seconds", original_max_age)


def test_inspect_age_and_minimum_size_ignore_unrequested_books(monkeypatch) -> None:
    monkeypatch.setattr("app.main.deepseek_key", lambda: "")
    with TestClient(app) as client:
        rt = app.state.runtime
        row = catalog_row("1")
        raw = {
            **row,
            "conditionId": "condition",
            "clobTokenIds": ["n", "y"],
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "enableOrderBook": True,
            "feesEnabled": False,
        }
        rt.catalog._snapshot = CatalogSnapshot(items={"1": row}, raw={"1": raw})
        timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
        books = {
            token: OrderBook(
                asset_id=token,
                timestamp=timestamp,
                min_order_size=Decimal("2"),
                asks=[PriceLevel(price=Decimal("0.4"), size=Decimal("1000"))],
            )
            for token in ("n", "y")
        }
        books["unrequested"] = OrderBook(asset_id="unrequested", timestamp="NaN", min_order_size=Decimal("1000000"))

        async def fetch_books(tokens):
            assert tokens == ["n", "y"]
            return books

        monkeypatch.setattr(rt.clob, "fetch_books", fetch_books)
        response = client.get("/api/inspect/1?quantity=10")
        response.raise_for_status()
        data = response.json()
        assert data["minimumOrderSize"] == "2"
        assert data["calculation"]["status"] == "VALID"
        assert Decimal(data["calculation"]["quote_age"]) < Decimal(rt.settings.max_quote_age_seconds)
        assert [book["asset_id"] for book in data["books"]] == ["n", "y"]
        assert [metric["asset_id"] for metric in data["book_analytics"]] == ["n", "y"]
