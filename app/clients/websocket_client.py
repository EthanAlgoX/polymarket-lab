from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from websockets.asyncio.client import connect

logger = logging.getLogger(__name__)
MAX_SEEN_MESSAGES = 10_000


class MarketMessage(BaseModel):
    event_type: str
    asset_id: str | None = None
    timestamp: str | None = None


MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class MarketWebSocket:
    def __init__(self, url: str, handler: MessageHandler) -> None:
        self.url = url
        self.handler = handler
        self.tokens: set[str] = set()
        self._stop = asyncio.Event()
        self.connected = False
        self.messages = 0
        self.errors = 0
        self.reconnects = 0
        self.last_message: datetime | None = None
        self._seen: OrderedDict[str, None] = OrderedDict()

    def set_tokens(self, tokens: set[str]) -> None:
        self.tokens = set(tokens)

    async def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            if not self.tokens:
                await asyncio.sleep(1)
                continue
            try:
                async with connect(self.url, open_timeout=15, close_timeout=5) as websocket:
                    self.connected = True
                    delay = 1.0
                    # A new connection must deliver its initial snapshots even
                    # when a quiet token has the same hash and timestamp.
                    self._seen.clear()
                    subscribed = set(self.tokens)
                    await websocket.send(
                        json.dumps({"assets_ids": sorted(subscribed), "type": "market", "custom_feature_enabled": True})
                    )
                    heartbeat_at = time.monotonic() + 10
                    while not self._stop.is_set():
                        if self.tokens != subscribed:
                            self.connected = False
                            await websocket.close()
                            break
                        remaining = heartbeat_at - time.monotonic()
                        if remaining <= 0:
                            await websocket.send("PING")
                            heartbeat_at = time.monotonic() + 10
                            remaining = 10
                        try:
                            raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                        except TimeoutError:
                            await websocket.send("PING")
                            heartbeat_at = time.monotonic() + 10
                            continue
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        if raw == "PONG":
                            continue
                        await self._process(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected = False
                self.errors += 1
                self.reconnects += 1
                logger.warning(
                    "websocket disconnected",
                    extra={"event": "websocket_disconnect", "error_type": type(exc).__name__},
                )
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                delay = min(delay * 2, 30)
        self.connected = False

    async def _process(self, raw: str) -> None:
        try:
            payload: object = json.loads(raw)
        except json.JSONDecodeError:
            self.errors += 1
            return
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                MarketMessage.model_validate(item)
            except ValidationError:
                self.errors += 1
                continue
            # Batched price changes can share a timestamp and omit asset_id/hash.
            # Deduplicate only the complete canonical payload, not that header.
            fingerprint = hashlib.sha256(
                json.dumps(item, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if fingerprint in self._seen:
                continue
            try:
                await self.handler(item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.errors += 1
                logger.warning(
                    "websocket message could not be processed",
                    extra={"event": "websocket_message_error", "error_type": type(exc).__name__},
                )
                continue
            self._seen[fingerprint] = None
            if len(self._seen) > MAX_SEEN_MESSAGES:
                self._seen.popitem(last=False)
            self.messages += 1
            self.last_message = datetime.now(UTC)
