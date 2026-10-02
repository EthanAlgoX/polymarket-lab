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


@pytest.mark.asyncio
async def test_handler_failure_isolated_to_one_message_and_retry_not_deduplicated() -> None:
    received: list[str] = []
    calls = 0

    async def handler(payload: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("bad snapshot")
        received.append(payload["asset_id"])

    client = MarketWebSocket("wss://example.invalid", handler)
    bad = {"event_type": "book", "asset_id": "a"}
    good = {"event_type": "book", "asset_id": "b"}
    await client._process(json.dumps([bad, good]))
    await client._process(json.dumps(bad))
    assert received == ["b", "a"]
    assert client.errors == 1
    assert client.messages == 2
    assert len(client._seen) == 2


@pytest.mark.asyncio
async def test_busy_stream_still_sends_fixed_interval_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    clock = SimpleNamespace(now=0.0)
    received = 0
    sent: list[tuple[str, float]] = []

    async def handler(payload: dict[str, Any]) -> None:
        nonlocal received
        received += 1
        if received == 3:
            await client.stop()

    class Socket:
        async def send(self, value: str) -> None:
            sent.append((value, clock.now))

        async def recv(self) -> str:
            clock.now += 10
            return json.dumps({"event_type": "book", "asset_id": "a", "timestamp": str(clock.now)})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object):
            pass

    monkeypatch.setattr("app.clients.websocket_client.connect", lambda *_args, **_kwargs: Socket())
    monkeypatch.setattr("app.clients.websocket_client.time", SimpleNamespace(monotonic=lambda: clock.now))
    client = MarketWebSocket("wss://example.invalid", handler)
    client.set_tokens({"a"})
    await client.run()
    assert received == 3
    assert [(value, moment) for value, moment in sent if value == "PING"] == [("PING", 10), ("PING", 20)]
