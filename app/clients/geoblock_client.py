from __future__ import annotations

from typing import Any

from app.clients.http import PublicHTTPClient


class GeoblockClient:
    def __init__(self, http: PublicHTTPClient, url: str) -> None:
        self.http = http
        self.url = url

    async def check(self) -> dict[str, Any]:
        payload = await self.http.request_json("GET", self.url)
        if not isinstance(payload, dict) or not isinstance(payload.get("blocked"), bool):
            raise ValueError("unexpected geoblock response")
        return {
            "blocked": payload["blocked"],
            "country": str(payload.get("country", "")),
            "region": str(payload.get("region", "")),
        }
