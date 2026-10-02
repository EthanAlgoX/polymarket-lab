from __future__ import annotations

from typing import Any

from app.clients.http import PublicHTTPClient


class GammaClient:
    def __init__(self, http: PublicHTTPClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    async def fetch_markets(self, maximum: int = 100) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(collected) < maximum:
            limit = min(100, maximum - len(collected))
            params: dict[str, object] = {"limit": limit, "closed": "false", "ascending": "false"}
            if cursor:
                params["after_cursor"] = cursor
            payload = await self.http.request_json("GET", f"{self.base_url}/markets/keyset", params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("markets"), list):
                raise ValueError("unexpected Gamma keyset response")
            page = [item for item in payload["markets"] if isinstance(item, dict)]
            collected.extend(page)
            cursor_value = payload.get("next_cursor")
            if not page or not isinstance(cursor_value, str) or not cursor_value:
                break
            cursor = cursor_value
        return collected[:maximum]
