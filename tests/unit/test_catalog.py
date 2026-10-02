from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

import pytest

from app.config import Settings
from app.runtime import ScannerRuntime
from app.services.catalog import CATEGORIES, MarketCatalog


def event(market_id: str, category: str = "sports", **changes: Any) -> dict[str, Any]:
    raw = {
        "id": market_id,
        "conditionId": f"condition-{market_id}",
        "question": f"Question {market_id}?",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": [f"yes-{market_id}", f"no-{market_id}"],
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "liquidityNum": "2000",
        "volumeNum": "1000",
        "volume24hr": "100",
        **changes,
    }
    return {
        "id": f"event-{market_id}",
        "title": f"Event {market_id}",
        "tags": [{"slug": category}],
        "markets": [raw],
    }


class StubHTTP:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls = 0
        self.params: list[dict[str, object]] = []

    async def request_json(self, *args: object, **kwargs: Any) -> Any:
        self.calls += 1
        self.params.append(kwargs["params"])
        response = self.responses.pop(0)
        if callable(response):
            response = response()
        if isinstance(response, Exception):
            raise response
        return response


def seed_responses(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"events": events}] * 5


@pytest.mark.asyncio
async def test_seed_is_atomic_and_subsequent_seed_does_not_relabel_old_data() -> None:
    http = StubHTTP(seed_responses([event("old")]) + seed_responses([event("new")]))
    catalog = MarketCatalog(http, "https://example.test")
    await catalog.seed()
    previous = catalog.snapshot
    assert previous.coverage == "sample"
    assert previous.revision == 1
    with pytest.raises(TypeError):
        catalog.items["injected"] = {}  # type: ignore[index]
    await catalog.seed()
    assert catalog.snapshot is previous
    assert set(catalog.items) == {"old"}
    assert set(catalog.raw) == {"old"}
    assert set(catalog.seed_items) == {"new"}


@pytest.mark.asyncio
async def test_successful_refresh_replaces_data_and_removes_closed_markets() -> None:
    http = StubHTTP(
        [
            *seed_responses([event("old"), event("keep")]),
            {"events": [event("old"), event("keep")]},
            *seed_responses([event("new"), event("keep"), event("old", closed=True)]),
            {"events": [event("new"), event("keep"), event("old", closed=True)]},
        ]
    )
    catalog = MarketCatalog(http, "https://example.test")
    await catalog.seed()
    await catalog.crawl()
    previous = catalog.snapshot
    await catalog.seed()
    assert catalog.snapshot is previous
    await catalog.crawl()
    assert set(catalog.items) == set(catalog.raw) == {"new", "keep"}
    assert set(previous.items) == set(previous.raw) == {"old", "keep"}
    assert catalog.snapshot.revision == previous.revision + 1
    assert catalog.updated_at != previous.updated_at
    assert catalog.coverage == "paginated"
    assert not catalog.refreshing
    old_summary = catalog.summary(previous)
    assert old_summary["revision"] == previous.revision
    assert old_summary["total"] == sum(row["count"] for row in old_summary["categories"]) == 2


@pytest.mark.asyncio
async def test_failed_refresh_keeps_previous_data_time_and_revision() -> None:
    http = StubHTTP([*seed_responses([event("old")]), {"events": [event("old")]}])
    catalog = MarketCatalog(http, "https://example.test")
    await catalog.seed()
    await catalog.crawl()
    previous = catalog.snapshot

    def observe_during_refresh() -> dict[str, Any]:
        current = catalog.snapshot
        assert current.items is previous.items
        assert current.raw is previous.raw
        assert current.updated_at == previous.updated_at
        assert current.revision == previous.revision
        assert current.pages == 1
        assert current.refreshing
        return {"unexpected": True}

    http.responses.extend(
        [
            *seed_responses([event("new")]),
            {"events": [event("new")], "next_cursor": "next", "has_more": True},
            observe_during_refresh,
        ]
    )
    await catalog.seed()
    await catalog.crawl()
    current = catalog.snapshot
    assert current.items is previous.items
    assert current.raw is previous.raw
    assert current.updated_at == previous.updated_at
    assert current.revision == previous.revision
    assert current.coverage == "partial"
    assert current.data_coverage == "paginated"
    assert current.error == "ValueError: unexpected event schema"
    assert not current.refreshing
    assert current.pages == 1


@pytest.mark.asyncio
async def test_old_seed_is_not_reused_on_a_later_traversal() -> None:
    http = StubHTTP([*seed_responses([event("old")]), {"events": [event("old")]}, {"events": [event("new")]}])
    catalog = MarketCatalog(http, "https://example.test")
    await catalog.seed()
    await catalog.crawl()
    # A failed seed request in the next cycle must not resurrect this old seed.
    await catalog.crawl()
    assert set(catalog.items) == {"new"}


@pytest.mark.asyncio
async def test_market_closing_between_seed_and_traversal_is_removed() -> None:
    http = StubHTTP(
        [*seed_responses([event("closing"), event("keep")]), {"events": [event("closing", closed=True), event("keep")]}]
    )
    catalog = MarketCatalog(http, "https://example.test")
    await catalog.seed()
    assert "closing" in catalog.items
    await catalog.crawl()
    assert set(catalog.items) == set(catalog.raw) == {"keep"}


@pytest.mark.asyncio
async def test_repeated_cursor_stops_and_never_claims_completion() -> None:
    http = StubHTTP(
        [
            {"events": [event("first")], "next_cursor": "repeat", "has_more": True},
            {"events": [event("second")], "next_cursor": "repeat", "has_more": True},
        ]
    )
    catalog = MarketCatalog(http, "https://example.test")
    await catalog.crawl()
    assert http.calls == 2
    assert http.params[1]["after_cursor"] == "repeat"
    assert catalog.coverage == "partial"
    assert catalog.error == "ValueError: repeated event cursor"
    assert set(catalog.items) == {"first"}
    assert not catalog.refreshing


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flags", "coverage", "error"),
    [
        ({"has_more": False, "next_cursor": "terminal"}, "paginated", None),
        ({"has_more": True, "limit_reached": True}, "capped", None),
        ({"has_more": True}, "partial", "more events reported without a next cursor"),
        ({"has_more": "false"}, "partial", "unexpected has_more"),
        ({"limit_reached": "true"}, "partial", "unexpected limit_reached"),
    ],
)
async def test_explicit_pagination_state_is_honest(flags: dict[str, object], coverage: str, error: str | None) -> None:
    http = StubHTTP([{"events": [event("one")], **flags}])
    catalog = MarketCatalog(http, "https://example.test")
    await catalog.crawl()
    assert catalog.coverage == coverage
    assert (catalog.error is None) == (error is None)
    if error is not None:
        assert error in catalog.error


@pytest.mark.asyncio
async def test_small_scanner_budget_reserves_categories_before_filling() -> None:
    events = [event(f"{category}-{i}", category) for category in CATEGORIES for i in range(9)]
    catalog = MarketCatalog(StubHTTP(seed_responses(events)), "https://example.test")
    await catalog.seed()
    selected = catalog.scanner_markets(5)
    assert len(selected) == 5
    assert len({row["category"] for row in selected}) == 5
    selected = catalog.scanner_markets(6)
    assert {row["category"] for row in selected} == set(CATEGORIES)
    selected = catalog.scanner_markets(20)
    counts = Counter(row["category"] for row in selected)
    assert len(selected) == 20
    assert max(counts.values()) - min(counts.values()) <= 1
    assert catalog.summary()["scannerSelection"]["categoryCounts"] == dict(counts)


@pytest.mark.asyncio
async def test_thresholds_filter_before_allocation_and_keep_original_financial_fields() -> None:
    events = [
        event("low-liquidity", liquidityNum="999.999999999999999999", volume24hr="100000"),
        event("low-volume", volumeNum="99.999999999999999999", volume24hr="100000"),
        event("non-binary", outcomes=["Up", "Down"]),
        event("good-a", feeSchedule={"rate": "0.07", "exponent": 1}),
        event("good-b", "weather", outcomes=["No", "Yes"], clobTokenIds=["no-first", "yes-second"]),
    ]
    catalog = MarketCatalog(StubHTTP(seed_responses(events)), "https://example.test")
    await catalog.seed()
    selected = catalog.scanner_markets(2, minimum_liquidity=Decimal("1000"), minimum_volume=Decimal("100"))
    assert {row["id"] for row in selected} == {"good-a", "good-b"}
    assert selected[0]["feeSchedule"] == {"rate": "0.07", "exponent": 1}
    weather = next(row for row in selected if row["id"] == "good-b")
    assert weather["outcomes"] == ["No", "Yes"]
    assert weather["clobTokenIds"] == ["no-first", "yes-second"]
    selection = catalog.summary()["scannerSelection"]
    assert selection["selectedTotal"] == selection["eligibleTotal"] == 2
    assert selection["minimumLiquidity"] == "1000"
    assert selection["minimumVolume"] == "100"
    assert selection["volumeBasis"] == "total"
    assert selection["excluded"] == {"notBinary": 1, "belowLiquidity": 1, "belowVolume": 1, "missingRaw": 0}


@pytest.mark.asyncio
async def test_selection_ties_are_stable_and_zero_budget_is_empty() -> None:
    events = [event("c"), event("a"), event("b")]
    catalog = MarketCatalog(StubHTTP(seed_responses(events)), "https://example.test")
    await catalog.seed()
    assert [row["id"] for row in catalog.scanner_markets(2)] == ["a", "b"]
    assert [row["id"] for row in catalog.scanner_markets(2)] == ["a", "b"]
    assert catalog.scanner_markets(0) == []
    assert catalog.summary()["scannerSelection"]["selectedTotal"] == 0


@pytest.mark.asyncio
async def test_runtime_applies_thresholds_before_filling_scanner_budget(tmp_path: Any) -> None:
    runtime = ScannerRuntime(
        Settings(
            enable_live_scanner=False,
            database_url=f"sqlite:///{tmp_path / 'catalog-runtime.db'}",
            max_markets=5,
            minimum_liquidity="1000",
            minimum_volume="100",
        )
    )
    runtime.database.initialize()
    events = [
        event("low-liquidity", liquidityNum="100", volume24hr="100000"),
        event("low-volume", "weather", volumeNum="1", volume24hr="100000"),
        *[event(f"good-{category}", category) for category in CATEGORIES],
    ]
    runtime.catalog.http = StubHTTP(seed_responses(events))
    try:
        await runtime.catalog.seed()
        await runtime.refresh_markets()
        assert len(runtime.markets) == 5
        assert all(key.startswith("good-") for key in runtime.markets)
        assert len({market.category for market in runtime.markets.values()}) == 5
        assert runtime.catalog.summary()["scannerSelection"]["excluded"]["belowVolume"] == 1
        assert runtime.status.binary_market_count == 5
    finally:
        await runtime.stop()
