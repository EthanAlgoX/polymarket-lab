from __future__ import annotations

import json
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


@pytest.mark.asyncio
async def test_same_timestamp_different_changes_survive_but_exact_duplicates_drop() -> None:
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    client = MarketWebSocket("wss://example.invalid", handler)
    first = {
        "event_type": "price_change",
        "timestamp": "123",
        "price_changes": [{"asset_id": "a", "side": "BUY", "price": "0.4", "size": "10"}],
    }
    second = {
        "event_type": "price_change",
        "timestamp": "123",
        "price_changes": [{"asset_id": "a", "side": "BUY", "price": "0.4", "size": "20"}],
    }
    third = {
        "event_type": "price_change",
        "timestamp": "123",
        "price_changes": [{"asset_id": "b", "side": "BUY", "price": "0.5", "size": "10"}],
    }
    await client._process(json.dumps([first, second, third]))
    await client._process(json.dumps(first, sort_keys=True, indent=2))
    assert received == [first, second, third]
    assert client.messages == 3
    assert len(client._seen) == 3


@pytest.mark.asyncio
async def test_dedup_bound_evicts_oldest_instead_of_clearing_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    monkeypatch.setattr("app.clients.websocket_client.MAX_SEEN_MESSAGES", 2)
    client = MarketWebSocket("wss://example.invalid", handler)
    messages = [{"event_type": "book", "asset_id": "a", "timestamp": str(index)} for index in range(3)]
    for message in messages:
        await client._process(json.dumps(message))
    await client._process(json.dumps(messages[2]))
    assert received == messages
    assert len(client._seen) == 2
    await client._process(json.dumps(messages[0]))
    assert received == [*messages, messages[0]]
    assert len(client._seen) == 2


@pytest.mark.asyncio
async def test_new_connection_delivers_unchanged_initial_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[dict[str, Any]] = []
    snapshot = '{"event_type":"book","asset_id":"a","timestamp":"123","hash":"same-book"}'

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)
        if len(received) == 2:
            await client.stop()

    class Socket:
        async def send(self, _: str) -> None:
            pass

        async def recv(self) -> str:
            return snapshot

        async def __aenter__(self) -> Socket:
            return self

        async def __aexit__(self, *_: object) -> None:
            pass

    monkeypatch.setattr("app.clients.websocket_client.connect", lambda *_args, **_kwargs: Socket())
    client = MarketWebSocket("wss://example.invalid", handler)
    client.set_tokens({"a"})
    await client._process(snapshot)
    await client.run()
    assert len(received) == 2
    assert received[0] == received[1]
    assert client.connected is False
