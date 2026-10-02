from __future__ import annotations

import pytest

from app.clients.gamma_client import GammaClient


@pytest.fixture(autouse=True)
def public_metadata_fixture(monkeypatch, tmp_path):
    # Unit/API tests never spend translation credits or reach public endpoints.
    monkeypatch.setattr("app.main.deepseek_key", lambda: "")
    monkeypatch.setattr("app.main.LLM_CONFIG_PATH", tmp_path / "llm-config.json")

    async def catalog_metadata(self, market_ids):
        from app.main import app

        return [dict(app.state.runtime.catalog.raw[mid]) for mid in market_ids if mid in app.state.runtime.catalog.raw]

    monkeypatch.setattr(GammaClient, "fetch_markets_by_ids", catalog_metadata)
