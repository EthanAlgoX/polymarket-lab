from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from typing import Any

from app.services.market_discovery import parse_bool, parse_decimal, parse_list

CATEGORIES = {
    "sports": "体育",
    "weather": "天气",
    "crypto": "加密",
    "economy": "经济 / 金融",
    "politics": "政治 / 地缘",
    "other": "其他",
}


def category_for(event: dict[str, Any]) -> str:
    tags = {str(x.get("slug", "")).lower() for x in event.get("tags", [])}
    title = str(event.get("title", "")).lower()
    if tags & {"weather", "temperature"} or "highest temperature" in title:
        return "weather"
    if tags & {"crypto", "bitcoin", "ethereum", "solana", "crypto-prices", "up-or-down"}:
        return "crypto"
    if tags & {"sports", "soccer", "nba", "nfl", "mlb", "nhl", "tennis", "esports", "ncaa", "ufc", "formula-1"}:
        return "sports"
    if tags & {
        "economy",
        "economics",
        "finance",
        "fed",
        "fomc",
        "business",
        "stocks",
        "economic-policy",
        "macro-indicators",
    }:
        return "economy"
    if tags & {"politics", "geopolitics", "elections", "world", "trump", "ukraine", "iran", "israel"}:
        return "politics"
    return "other"


class MarketCatalog:
    """Read-only event discovery, separate from bounded order-book subscriptions."""

    def __init__(self, http: Any, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.seed_items: dict[str, dict[str, Any]] = {}
        self.seed_raw: dict[str, dict[str, Any]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.raw: dict[str, dict[str, Any]] = {}
        self.updated_at: str | None = None
        self.coverage = "loading"
        self.pages = 0
        self.events = 0
        self.error: str | None = None
        self.refreshing = False

    def ingest(self, events: list[dict[str, Any]], items: dict, raw_items: dict) -> None:
        for event in events:
            category = category_for(event)
            for raw in event.get("markets", []):
                if not (
                    parse_bool(raw.get("active"))
                    and not parse_bool(raw.get("closed"))
                    and parse_bool(raw.get("acceptingOrders"))
                    and parse_bool(raw.get("enableOrderBook"))
                ):
                    continue
                outcomes, tokens = parse_list(raw.get("outcomes")), parse_list(raw.get("clobTokenIds"))
                if not outcomes or len(outcomes) != len(tokens):
                    continue
                market_id = str(raw["id"])
                prices = parse_list(raw.get("outcomePrices"))
                price_values = []
                for value in prices:
                    try:
                        number = float(value)
                        price_values.append(number if math.isfinite(number) and 0 <= number <= 1 else None)
                    except (ValueError, TypeError):
                        price_values.append(None)
                row = {
                    "id": market_id,
                    "question": raw.get("question", ""),
                    "event": event.get("title", ""),
                    "eventId": str(event["id"]),
                    "slug": event.get("slug", ""),
                    "category": category,
                    "tags": [x.get("label", "") for x in event.get("tags", [])],
                    "outcomes": outcomes,
                    "prices": price_values,
                    "tokens": tokens,
                    "volume24h": float(parse_decimal(raw.get("volume24hr"))),
                    "volume": float(parse_decimal(raw.get("volumeNum", raw.get("volume")))),
                    "liquidity": float(parse_decimal(raw.get("liquidityNum", raw.get("liquidity")))),
                    "endDate": raw.get("endDate"),
                    "createdAt": raw.get("createdAt"),
                    "updatedAt": raw.get("updatedAt"),
                    "negRisk": parse_bool(raw.get("negRisk")),
                    "feeSchedule": raw.get("feeSchedule"),
                    "feesEnabled": raw.get("feesEnabled"),
                    "description": raw.get("description", event.get("description", "")),
                    "resolutionSource": raw.get("resolutionSource") or event.get("resolutionSource"),
                }
                items[market_id] = row
                raw_copy = dict(raw)
                raw_copy["category"] = category
                raw_items[market_id] = raw_copy

    async def seed(self) -> None:
        requests = [
            {"order": "volume24hr", "ascending": "false"},
            {"order": "createdAt", "ascending": "false"},
            {"tag_id": "84", "order": "volume24hr", "ascending": "false"},
            {"tag_id": "21", "order": "volume24hr", "ascending": "false"},
            {"tag_id": "1", "order": "volume24hr", "ascending": "false"},
        ]
        results = await asyncio.gather(
            *[
                self.http.request_json(
                    "GET",
                    f"{self.base_url}/events/keyset",
                    params={"active": "true", "closed": "false", "limit": 100, **params},
                )
                for params in requests
            ],
            return_exceptions=True,
        )
        fresh_items: dict[str, dict[str, Any]] = {}
        fresh_raw: dict[str, dict[str, Any]] = {}
        for result in results:
            if isinstance(result, dict):
                self.ingest(result.get("events", []), fresh_items, fresh_raw)
        if not fresh_items:
            raise RuntimeError("No public markets received")
        self.seed_items, self.seed_raw = fresh_items, fresh_raw
        self.items.update(fresh_items)
        self.raw.update(fresh_raw)
        self.updated_at = datetime.now(UTC).isoformat()
        self.coverage = "sample"

    async def crawl(self) -> None:
        if self.refreshing:
            return
        self.refreshing = True
        self.error = None
        items, raw_items, cursor = dict(self.seed_items), dict(self.seed_raw), None
        self.pages = self.events = 0
        try:
            for _ in range(100):
                params: dict[str, object] = {
                    "active": "true",
                    "closed": "false",
                    "limit": 100,
                    "order": "id",
                    "ascending": "false",
                }
                if cursor:
                    params["after_cursor"] = cursor
                payload = await self.http.request_json("GET", f"{self.base_url}/events/keyset", params=params)
                if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
                    raise ValueError("unexpected event schema")
                events = payload["events"]
                if payload.get("next_cursor") is not None and not isinstance(payload["next_cursor"], str):
                    raise ValueError("unexpected cursor")
                self.ingest(events, items, raw_items)
                self.pages += 1
                self.events += len(events)
                # Make discovery useful while the full traversal continues.
                self.items.update(items)
                self.raw.update(raw_items)
                self.updated_at = datetime.now(UTC).isoformat()
                cursor = payload.get("next_cursor")
                if not cursor or not events:
                    self.items, self.raw = items, raw_items
                    self.coverage = "paginated"
                    break
            else:
                self.coverage = "capped"
                self.items, self.raw = items, raw_items
            self.updated_at = datetime.now(UTC).isoformat()
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {str(exc)[:160]}"
            self.coverage = "partial"
        finally:
            self.refreshing = False

    def scanner_markets(self, maximum: int) -> list[dict[str, Any]]:
        rows = sorted(self.items.values(), key=lambda x: (x["volume24h"], x["liquidity"]), reverse=True)
        binary = [x for x in rows if {s.lower() for s in x["outcomes"]} == {"yes", "no"}]
        selected: dict[str, dict] = {}
        # Reserve category coverage; a pure volume ranking misses weather entirely.
        for category in CATEGORIES:
            for item in [x for x in binary if x["category"] == category][:8]:
                selected[item["id"]] = self.raw[item["id"]]
        for item in binary:
            if len(selected) >= maximum:
                break
            selected[item["id"]] = self.raw[item["id"]]
        return list(selected.values())[:maximum]

    def summary(self) -> dict[str, Any]:
        return {
            "updatedAt": self.updated_at,
            "coverage": self.coverage,
            "refreshing": self.refreshing,
            "pages": self.pages,
            "events": self.events,
            "total": len(self.items),
            "error": self.error,
            "categories": [
                {
                    "id": key,
                    "label": label,
                    "count": sum(x["category"] == key for x in self.items.values()),
                    "volume24h": sum(x["volume24h"] for x in self.items.values() if x["category"] == key),
                    "liquidity": sum(x["liquidity"] for x in self.items.values() if x["category"] == key),
                }
                for key, label in CATEGORIES.items()
            ],
        }
