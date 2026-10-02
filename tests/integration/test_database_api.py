from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import Base, Database
from app.main import app
from app.models import FeeQuote, FeeStatus, Market, OrderBook, PriceLevel
from app.services.depth_calculator import calculate_depth


def sample_market() -> Market:
    return Market(
        market_id="1",
        condition_id="c",
        question="Sample?",
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
        outcomes=["Yes", "No"],
        token_ids=["y", "n"],
        yes_token_id="y",
        no_token_id="n",
    )


def sample_result():
    levels = [PriceLevel(price=Decimal("0.4"), size=Decimal("10"))]
    return calculate_depth(
        OrderBook(asset_id="y", asks=levels),
        OrderBook(asset_id="n", asks=levels),
        Decimal("10"),
        FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0")),
    )


def test_database_write_read_and_settings(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    database.initialize()
    database.upsert_market(sample_market())
    database.upsert_setting("quantity", "10")
    assert database.settings()["quantity"] == "10"
    database.upsert_opportunity(sample_market(), sample_result())
    assert len(database.list_opportunities()) == 1
    trade_id = database.add_paper_trade(sample_market(), sample_result())
    assert trade_id == 1
    assert database.paper_trade_count() == 1
    assert database.paper_profit_total() == Decimal("1.984000")
    database.close()


def test_database_transaction_rollback(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'rollback.db'}")
    database.initialize()
    try:
        with database.Session.begin() as session:
            database.upsert_setting("outside", "ok")
            session.execute(Base.metadata.tables["application_settings"].insert().values(key="a", value="1"))
            raise RuntimeError("rollback")
    except RuntimeError:
        pass
    assert "a" not in database.settings()
    database.close()


def test_main_routes_and_health() -> None:
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        for route in ("/", "/opportunities", "/paper-trades", "/history", "/settings", "/logs"):
            response = client.get(route)
            assert response.status_code == 200
            assert "不提交订单" in response.text
        assert client.get("/api/markets?limit=1").status_code == 200
        assert client.get("/api/markets/missing").status_code == 404


def test_settings_validation_and_csv() -> None:
    with TestClient(app) as client:
        response = client.put(
            "/api/settings",
            json={
                "minimum_net_profit": "0.2",
                "minimum_net_roi": "0.003",
                "default_quantity": "25",
                "slippage_rate": "0.001",
                "safety_rate": "0.001",
            },
        )
        assert response.status_code == 200
        invalid = client.put(
            "/api/settings",
            json={
                "minimum_net_profit": "-1",
                "minimum_net_roi": "2",
                "default_quantity": "0",
                "slippage_rate": "1",
                "safety_rate": "1",
            },
        )
        assert invalid.status_code == 422
        export = client.get("/api/exports/paper-trades.csv")
        assert export.status_code == 200
        assert export.content.startswith(b"\xef\xbb\xbf")


def test_paper_trade_requires_live_snapshot() -> None:
    with TestClient(app) as client:
        response = client.post("/api/paper-trades", json={"market_id": "missing"})
        assert response.status_code == 409


def test_translation_api_registers_public_text_and_bounds_requests(monkeypatch) -> None:
    monkeypatch.setattr("app.main.deepseek_key", lambda: "")
    with TestClient(app) as client:
        app.state.runtime.markets["1"] = sample_market()
        assert client.get("/api/markets/1").status_code == 200
        response = client.post("/api/translations", json={"texts": ["Sample?", "Yes", "No", "not served text"]})
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "deepseek-flash"
        assert data["available"] is False
        assert data["items"][0]["text"] == "Sample?"
        assert "DeepSeek" in data["items"][0]["reason"]
        assert [row["text"] for row in data["items"][1:3]] == ["是", "否"]
        assert "公开市场" in data["items"][3]["reason"]
        assert client.post("/api/translations", json={"texts": ["x"] * 81}).status_code == 422
        assert client.post("/api/translations", json={"texts": ["x" * 20001]}).status_code == 422
