from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from app.clients.geoblock_client import GeoblockClient
from app.clients.http import PublicHTTPClient
from app.config import Settings
from app.exceptions import ExternalAPIError
from app.runtime import ScannerRuntime
from app.services.market_discovery import normalize_market


def valid_raw_market() -> dict[str, Any]:
    return {
        "id": "1",
        "conditionId": "condition",
        "question": "Question?",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": ["yes-token", "no-token"],
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "liquidityNum": "2000",
    }


@pytest.mark.asyncio
async def test_public_http_success_and_close() -> None:
    client = PublicHTTPClient(2, "test-agent", 1)
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": True})))
    assert await client.request_json("GET", "https://example.test") == {"ok": True}
    await client.close()


@pytest.mark.asyncio
async def test_public_http_non_retryable_400() -> None:
    client = PublicHTTPClient(2, "test-agent", 1)
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(400, text="bad", request=request))
    )
    with pytest.raises(ExternalAPIError, match="400"):
        await client.request_json("GET", "https://example.test")
    await client.close()


@pytest.mark.asyncio
async def test_public_http_retries_5xx() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="later", request=request)

    client = PublicHTTPClient(2, "test-agent", 1)
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ExternalAPIError, match="after retries"):
        await client.request_json("GET", "https://example.test")
    assert calls == 3
    await client.close()


@pytest.mark.asyncio
async def test_geoblock_redacts_ip_and_validates() -> None:
    class Stub:
        async def request_json(self, *args: object, **kwargs: object) -> object:
            return {"blocked": False, "ip": "203.0.113.10", "country": "ZZ", "region": ""}

    client = GeoblockClient(Stub(), "https://example.test")  # type: ignore[arg-type]
    result = await client.check()
    assert result == {"blocked": False, "country": "ZZ", "region": ""}
    assert "ip" not in result


@pytest.mark.asyncio
async def test_runtime_offline_lifecycle_and_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(enable_live_scanner=False, database_url=f"sqlite:///{tmp_path / 'runtime.db'}")
    runtime = ScannerRuntime(settings)
    await runtime.start()
    assert runtime.database.health()
    market = normalize_market(valid_raw_market())
    runtime.markets[market.market_id] = market
    payload = runtime.market_payload(market)
    assert payload["question"] == "Question?"
    assert payload["calculation"] is None
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_websocket_book_message(tmp_path: Path) -> None:
    settings = Settings(enable_live_scanner=False, database_url=f"sqlite:///{tmp_path / 'runtime-ws.db'}")
    runtime = ScannerRuntime(settings)
    await runtime.handle_websocket(
        {
            "event_type": "book",
            "asset_id": "token",
            "bids": [],
            "asks": [{"price": "0.5", "size": "2"}],
        }
    )
    assert runtime.books["token"].best_ask is not None
    assert runtime.status.websocket_status == "已连接"
    await runtime.http.close()
    runtime.database.close()
