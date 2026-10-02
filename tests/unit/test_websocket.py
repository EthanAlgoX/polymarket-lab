from __future__ import annotations

from typing import Any

import pytest

from app.clients.websocket_client import MarketWebSocket


@pytest.mark.asyncio
async def test_websocket_valid_invalid_and_duplicate_messages() -> None:
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    client = MarketWebSocket("wss://example.invalid", handler)
    valid = '{"event_type":"book","asset_id":"a","timestamp":"1","hash":"h"}'
    await client._process(valid)
    await client._process(valid)
    await client._process("not-json")
    await client._process('{"asset_id":"missing-type"}')
    assert len(received) == 1
    assert client.messages == 1
    assert client.errors == 2


def test_subscription_replacement() -> None:
    client = MarketWebSocket("wss://example.invalid", lambda _: None)  # type: ignore[arg-type]
    client.set_tokens({"a", "b"})
    client.set_tokens({"c"})
    assert client.tokens == {"c"}
