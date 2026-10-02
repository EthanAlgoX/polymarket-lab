from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.clients.clob_client import ClobClient
from app.clients.gamma_client import GammaClient
from app.clients.geoblock_client import GeoblockClient
from app.clients.http import PublicHTTPClient
from app.clients.websocket_client import MarketWebSocket
from app.config import Settings
from app.services.market_discovery import parse_list


@pytest.mark.live
@pytest.mark.asyncio
async def test_public_endpoints_and_market_websocket() -> None:
    settings = Settings(enable_live_scanner=True)
    http = PublicHTTPClient(settings.request_timeout, settings.user_agent, 10)
    gamma = GammaClient(http, settings.gamma_url)
    clob = ClobClient(http, settings.clob_url)
    geoblock = GeoblockClient(http, settings.geoblock_url)
    try:
        markets = await gamma.fetch_markets(30)
        assert len(markets) >= 20, f"Gamma returned only {len(markets)} markets"
        tokens: list[str] = []
        for market in markets:
            tokens.extend(parse_list(market.get("clobTokenIds", market.get("clob_token_ids"))))
            if len(tokens) >= 5:
                break
        assert len(tokens) >= 5, "fewer than five public token IDs discovered"
        books = await clob.fetch_books(tokens[:5])
        assert len(books) >= 5, f"CLOB returned only {len(books)} books"
        geo = await geoblock.check()
        assert "blocked" in geo
        received: list[dict[str, Any]] = []

        async def handler(payload: dict[str, Any]) -> None:
            received.append(payload)

        websocket = MarketWebSocket(settings.websocket_url, handler)
        websocket.set_tokens(set(tokens[:2]))
        task = asyncio.create_task(websocket.run())
        try:
            for _ in range(15):
                if received:
                    break
                await asyncio.sleep(1)
            assert received, "WebSocket produced no validated market message in 15 seconds"
        finally:
            await websocket.stop()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    finally:
        await http.close()
