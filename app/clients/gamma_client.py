from __future__ import annotations

from typing import Any

from app.clients.http import PublicHTTPClient


class GammaClient:
    def __init__(self, http: PublicHTTPClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    async def fetch_markets_by_ids(self, market_ids: list[str]) -> list[dict[str, Any]]:
        """Verify a bounded scanner sample without reusing old catalog flags."""
        ids = list(dict.fromkeys(market_ids))
        collected: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for offset in range(0, len(ids), 100):
            requested = set(ids[offset : offset + 100])
            payload = await self.http.request_json(
                "GET",
                f"{self.base_url}/markets",
                params={"id": ids[offset : offset + 100], "limit": len(requested), "closed": "false"},
            )
            if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                raise ValueError("unexpected Gamma selected-market response")
            for item in payload:
                market_id = str(item.get("id"))
                if market_id not in requested:
                    raise ValueError("unexpected Gamma selected-market identity")
                if market_id in seen_ids:
                    raise ValueError("duplicate Gamma selected-market identity")
                seen_ids.add(market_id)
            collected.extend(payload)
        return collected

    async def fetch_markets(self, maximum: int = 100) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while len(collected) < maximum:
            limit = min(100, maximum - len(collected))
            params: dict[str, object] = {"limit": limit, "closed": "false", "ascending": "false"}
            if cursor:
                params["after_cursor"] = cursor
            payload = await self.http.request_json("GET", f"{self.base_url}/markets/keyset", params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("markets"), list):
                raise ValueError("unexpected Gamma keyset response")
            if any(not isinstance(item, dict) for item in payload["markets"]):
                raise ValueError("unexpected Gamma market schema")
            for flag in ("has_more", "limit_reached"):
                if flag in payload and not isinstance(payload[flag], bool):
                    raise ValueError(f"unexpected Gamma {flag}")
            cursor_value = payload.get("next_cursor")
            if cursor_value is not None and not isinstance(cursor_value, str):
                raise ValueError("unexpected Gamma cursor")
            page = payload["markets"]
            collected.extend(page)
            if payload.get("has_more") is False or payload.get("limit_reached") is True:
                break
            if not cursor_value:
                if payload.get("has_more") is True:
                    raise ValueError("more markets reported without a next cursor")
                break
            if not page:
                raise ValueError("empty market page with a next cursor")
            if cursor_value in seen_cursors:
                raise ValueError("repeated market cursor")
            seen_cursors.add(cursor_value)
            cursor = cursor_value
        return collected[:maximum]
