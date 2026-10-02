from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from websockets.asyncio.client import connect

logger = logging.getLogger(__name__)


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
        self._seen: set[str] = set()

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
                    subscribed = set(self.tokens)
                    await websocket.send(
                        json.dumps({"assets_ids": sorted(subscribed), "type": "market", "custom_feature_enabled": True})
                    )
                    while not self._stop.is_set():
                        if self.tokens != subscribed:
                            self.connected = False
                            await websocket.close()
                            break
                        try:
                            raw = await asyncio.wait_for(websocket.recv(), timeout=10)
                        except TimeoutError:
                            await websocket.send("PING")
                            continue
                        if raw == "PONG":
                            continue
                        await self._process(str(raw))
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
                message = MarketMessage.model_validate(item)
            except ValidationError:
                self.errors += 1
                continue
            fingerprint = f"{message.event_type}:{message.asset_id}:{message.timestamp}:{item.get('hash', '')}"
            if fingerprint in self._seen:
                continue
            self._seen.add(fingerprint)
            if len(self._seen) > 10_000:
                self._seen.clear()
            self.messages += 1
            self.last_message = datetime.now(UTC)
            await self.handler(item)
