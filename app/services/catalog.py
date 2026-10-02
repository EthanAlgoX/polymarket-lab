from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
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


def _category_summary(items: Mapping[str, dict[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    totals: dict[str, dict[str, Any]] = {
        key: {"id": key, "label": label, "count": 0, "volume24h": 0, "liquidity": 0}
        for key, label in CATEGORIES.items()
    }
    for row in items.values():
        category = totals.get(row.get("category", "other"), totals["other"])
        category["count"] += 1
        category["volume24h"] += row.get("volume24h", 0)
        category["liquidity"] += row.get("liquidity", 0)
    return tuple(MappingProxyType(category) for category in totals.values())


@dataclass(frozen=True)
class CatalogSnapshot:
    """One publication; its maps and their rows are never mutated by discovery."""

    items: Mapping[str, dict[str, Any]] = field(default_factory=lambda: MappingProxyType({}))
    raw: Mapping[str, dict[str, Any]] = field(default_factory=lambda: MappingProxyType({}))
    updated_at: str | None = None
    coverage: str = "loading"
    data_coverage: str = "loading"
    revision: int = 0
    pages: int = 0
    events: int = 0
    error: str | None = None
    refreshing: bool = False
    scanner_selection: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    categories: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        for name in ("items", "raw", "scanner_selection"):
            value = getattr(self, name)
            if not isinstance(value, MappingProxyType):
                object.__setattr__(self, name, MappingProxyType(dict(value)))
        if not self.categories:
            object.__setattr__(self, "categories", _category_summary(self.items))


class MarketCatalog:
    """Read-only event discovery, separate from bounded order-book subscriptions."""

    def __init__(self, http: Any, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.seed_items: dict[str, dict[str, Any]] = {}
        self.seed_raw: dict[str, dict[str, Any]] = {}
        self._pending_seed = False
        self._snapshot = CatalogSnapshot()

    @property
    def snapshot(self) -> CatalogSnapshot:
        return self._snapshot

    @property
    def items(self) -> Mapping[str, dict[str, Any]]:
        return self._snapshot.items

    @property
    def raw(self) -> Mapping[str, dict[str, Any]]:
        return self._snapshot.raw

    @property
    def updated_at(self) -> str | None:
        return self._snapshot.updated_at

    @property
    def coverage(self) -> str:
        return self._snapshot.coverage

    @property
    def pages(self) -> int:
        return self._snapshot.pages

    @property
    def events(self) -> int:
        return self._snapshot.events

    @property
    def error(self) -> str | None:
        return self._snapshot.error

    @property
    def refreshing(self) -> bool:
        return self._snapshot.refreshing

    def _publish(
        self,
        items: dict[str, dict[str, Any]],
        raw_items: dict[str, dict[str, Any]],
        coverage: str,
        *,
        pages: int = 0,
        events: int = 0,
        refreshing: bool = False,
    ) -> None:
        self._snapshot = CatalogSnapshot(
            items=MappingProxyType(dict(items)),
            raw=MappingProxyType(dict(raw_items)),
            updated_at=datetime.now(UTC).isoformat(),
            coverage=coverage,
            data_coverage=coverage,
            revision=self._snapshot.revision + 1,
            pages=pages,
            events=events,
            refreshing=refreshing,
            categories=_category_summary(items),
        )

    def ingest(self, events: list[dict[str, Any]], items: dict, raw_items: dict) -> None:
        for event in events:
            category = category_for(event)
            for raw in event.get("markets", []):
                market_id = str(raw["id"])
                if not (
                    parse_bool(raw.get("active"))
                    and not parse_bool(raw.get("closed"))
                    and parse_bool(raw.get("acceptingOrders"))
                    and parse_bool(raw.get("enableOrderBook"))
                ):
                    # A market may close between the seed and its traversal
                    # page. An explicit later state removes its seeded row.
                    items.pop(market_id, None)
                    raw_items.pop(market_id, None)
                    continue
                outcomes, tokens = parse_list(raw.get("outcomes")), parse_list(raw.get("clobTokenIds"))
                if not outcomes or len(outcomes) != len(tokens):
                    continue
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
        self._pending_seed = True
        # Seeds make startup useful. Subsequent seeds stay private until the
        # traversal succeeds, so a refresh never mixes old and new data.
        if not self._snapshot.items:
            self._publish(fresh_items, fresh_raw, "sample")

    async def crawl(self) -> None:
        if self.refreshing:
            return
        previous = self._snapshot
        had_previous_data = bool(previous.items)
        self._snapshot = replace(previous, refreshing=True, error=None, pages=0, events=0)
        # A seed is consumed once. Reusing an old seed after a failed seed
        # request would resurrect markets removed from a later traversal.
        items = dict(self.seed_items) if self._pending_seed else {}
        raw_items = dict(self.seed_raw) if self._pending_seed else {}
        self._pending_seed = False
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages = events_read = 0
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
                for flag in ("has_more", "limit_reached"):
                    if flag in payload and not isinstance(payload[flag], bool):
                        raise ValueError(f"unexpected {flag}")
                self.ingest(events, items, raw_items)
                pages += 1
                events_read += len(events)
                next_cursor = payload.get("next_cursor")
                if payload.get("limit_reached") is True:
                    self._publish(items, raw_items, "capped", pages=pages, events=events_read)
                    break
                if payload.get("has_more") is False or not next_cursor:
                    if payload.get("has_more") is True:
                        raise ValueError("more events reported without a next cursor")
                    self._publish(items, raw_items, "paginated", pages=pages, events=events_read)
                    break
                if not events:
                    raise ValueError("empty event page with a next cursor")
                if next_cursor in seen_cursors:
                    raise ValueError("repeated event cursor")
                seen_cursors.add(next_cursor)
                cursor = next_cursor
                if not had_previous_data:
                    self._publish(items, raw_items, "partial", pages=pages, events=events_read, refreshing=True)
                else:
                    self._snapshot = replace(self._snapshot, pages=pages, events=events_read)
            else:
                self._publish(items, raw_items, "capped", pages=pages, events=events_read)
        except Exception as exc:
            fallback = previous if had_previous_data else self._snapshot
            self._snapshot = replace(
                fallback,
                error=f"{type(exc).__name__}: {str(exc)[:160]}",
                coverage="partial",
                pages=pages,
                events=events_read,
                refreshing=False,
            )
        finally:
            self._snapshot = replace(self._snapshot, refreshing=False)

    def scanner_markets(
        self,
        maximum: int,
        minimum_liquidity: Decimal = Decimal("0"),
        minimum_volume: Decimal = Decimal("0"),
    ) -> list[dict[str, Any]]:
        snapshot = self._snapshot
        maximum = max(0, maximum)
        binary: list[dict[str, Any]] = []
        excluded = {"notBinary": 0, "belowLiquidity": 0, "belowVolume": 0, "missingRaw": 0}
        for row in snapshot.items.values():
            raw = snapshot.raw.get(row["id"])
            if len(row["outcomes"]) != 2 or {s.casefold() for s in row["outcomes"]} != {"yes", "no"}:
                excluded["notBinary"] += 1
            elif raw is None:
                excluded["missingRaw"] += 1
            elif parse_decimal(raw.get("liquidityNum", raw.get("liquidity"))) < minimum_liquidity:
                excluded["belowLiquidity"] += 1
            elif parse_decimal(raw.get("volumeNum", raw.get("volume"))) < minimum_volume:
                excluded["belowVolume"] += 1
            else:
                binary.append(row)
        binary.sort(key=lambda x: (-parse_decimal(x["volume24h"]), -parse_decimal(x["liquidity"]), x["id"]))
        categories = {category: [row for row in binary if row["category"] == category] for category in CATEGORIES}
        selected: dict[str, dict[str, Any]] = {}
        # Allocate one per category each round before filling by volume. A
        # small budget must not be consumed by the first category alone.
        for position in range(8):
            for category_rows in categories.values():
                if len(selected) >= maximum:
                    break
                if position < len(category_rows):
                    item = category_rows[position]
                    selected[item["id"]] = snapshot.raw[item["id"]]
        for item in binary:
            if len(selected) >= maximum:
                break
            selected[item["id"]] = snapshot.raw[item["id"]]
        selection = {
            "maximum": maximum,
            "eligibleTotal": len(binary),
            "selectedTotal": len(selected),
            "minimumLiquidity": str(minimum_liquidity),
            "minimumVolume": str(minimum_volume),
            "volumeBasis": "total",
            "method": "category-round-robin-then-volume",
            "categoryCounts": {
                category: sum(snapshot.items[key]["category"] == category for key in selected)
                for category in CATEGORIES
            },
            "excluded": excluded,
        }
        self._snapshot = replace(snapshot, scanner_selection=MappingProxyType(selection))
        return list(selected.values())

    def summary(self, snapshot: CatalogSnapshot | None = None) -> dict[str, Any]:
        snapshot = self._snapshot if snapshot is None else snapshot
        return {
            "updatedAt": snapshot.updated_at,
            "coverage": snapshot.coverage,
            "dataCoverage": snapshot.data_coverage,
            "revision": snapshot.revision,
            "refreshing": snapshot.refreshing,
            "pages": snapshot.pages,
            "events": snapshot.events,
            "total": len(snapshot.items),
            "error": snapshot.error,
            "scannerSelection": dict(snapshot.scanner_selection),
            "categories": [dict(category) for category in snapshot.categories],
        }
