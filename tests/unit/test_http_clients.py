from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from decimal import Decimal
from email.utils import formatdate
from types import SimpleNamespace

import httpx
import pytest

from app.clients.clob_client import ClobClient
from app.clients.gamma_client import GammaClient
from app.clients.http import PublicHTTPClient
from app.exceptions import ExternalAPIError
from app.models import FeeStatus


class StubHTTP:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = payloads
        self.calls = 0

    async def request_json(self, *args: object, **kwargs: object) -> object:
        payload = self.payloads[self.calls]
        self.calls += 1
        if isinstance(payload, Exception):
            raise payload
        return payload


@pytest.mark.asyncio
async def test_gamma_keyset_pagination() -> None:
    http = StubHTTP([{"markets": [{"id": "1"}], "next_cursor": "next"}, {"markets": [{"id": "2"}]}])
    client = GammaClient(http, "https://example.test")  # type: ignore[arg-type]
    result = await client.fetch_markets(101)
    assert [item["id"] for item in result] == ["1", "2"]
    assert http.calls == 2


@pytest.mark.asyncio
async def test_clob_books_and_fee_states() -> None:
    http = StubHTTP([[{"asset_id": "t", "asks": [{"price": "0.5", "size": "2"}]}], {"fd": {"r": "0.03"}}])
    client = ClobClient(http, "https://example.test")  # type: ignore[arg-type]
    books = await client.fetch_books(["t"])
    assert books["t"].best_ask == Decimal("0.5")
    quote = await client.fetch_fee("condition", True)
    assert quote.status is FeeStatus.KNOWN
    assert quote.base_fee_bps == Decimal("30.00")


@pytest.mark.asyncio
async def test_fee_false_is_known_zero() -> None:
    client = ClobClient(StubHTTP([]), "https://example.test")  # type: ignore[arg-type]
    quote = await client.fetch_fee("condition", False)
    assert quote.base_fee_bps == Decimal("0")


@pytest.mark.asyncio
async def test_fee_error_is_unknown() -> None:
    client = ClobClient(StubHTTP([httpx.TimeoutException("timeout")]), "https://example.test")  # type: ignore[arg-type]
    quote = await client.fetch_fee("condition", True)
    assert quote.status is FeeStatus.UNKNOWN


@pytest.fixture
def retry_clock(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    clock = SimpleNamespace(monotonic=1000.0, wall=1700000000.0, sleeps=[])

    async def sleep(seconds: float) -> None:
        clock.sleeps.append(seconds)
        clock.monotonic += seconds

    monkeypatch.setattr(
        "app.clients.http.time",
        SimpleNamespace(monotonic=lambda: clock.monotonic, time=lambda: clock.wall, perf_counter=time.perf_counter),
    )
    monkeypatch.setattr("app.clients.http.asyncio.sleep", sleep)
    monkeypatch.setattr("app.clients.http.random.uniform", lambda _lower, _upper: 0.0)
    return clock


async def mock_public_client(handler: Callable[[httpx.Request], httpx.Response]) -> PublicHTTPClient:
    client = PublicHTTPClient(timeout=1, user_agent="test", max_concurrency=1)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.asyncio
async def test_public_http_429_honors_cooldown_and_exposes_metrics(retry_clock: SimpleNamespace) -> None:
    responses = [httpx.Response(429, headers={"Retry-After": "4"}), httpx.Response(200, json={"ok": True})]
    client = await mock_public_client(lambda _: responses.pop(0))
    try:
        assert await client.request_json("GET", "https://example.test/events") == {"ok": True}
        assert retry_clock.sleeps == [4.0]
        assert client.metrics() == {
            "calls": 1,
            "attempts": 2,
            "retries": 1,
            "rate_limited": 1,
            "last_status": 200,
            "last_retry_delay": 4.0,
        }
        snapshot = client.metrics()
        snapshot["calls"] = 100
        assert client.metrics()["calls"] == 1
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("header", "expected"),
    [("date", 8.0), ("nonsense", 0.5), ("-10", 0.5), ("NaN", 0.5), ("Inf", 0.5), ("3600", 30.0)],
)
async def test_public_http_retry_after_date_invalid_and_capped(
    retry_clock: SimpleNamespace, header: str, expected: float
) -> None:
    retry_after = formatdate(retry_clock.wall + 8, usegmt=True) if header == "date" else header
    responses = [httpx.Response(429, headers={"Retry-After": retry_after}), httpx.Response(200, json=[])]
    client = await mock_public_client(lambda _: responses.pop(0))
    try:
        assert await client.request_json("GET", "https://example.test/events") == []
        assert retry_clock.sleeps == [expected]
        assert client.metrics()["last_retry_delay"] == expected
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_http_4xx_is_not_retried_or_leaked(
    retry_clock: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    client = await mock_public_client(lambda _: httpx.Response(400, text="secret response value"))
    try:
        with pytest.raises(ExternalAPIError) as caught:
            await client.request_json("GET", "https://user:password@example.test/events?key=secret-query")
        assert caught.value.status_code == 400
        assert caught.value.attempts == 1
        assert retry_clock.sleeps == []
        assert client.metrics()["attempts"] == 1
        visible = str(caught.value) + repr(caught.value) + caplog.text
        assert all(secret not in visible for secret in ["password", "secret-query", "secret response value"])
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_http_final_error_preserves_status_and_three_attempts(retry_clock: SimpleNamespace) -> None:
    client = await mock_public_client(lambda _: httpx.Response(503, text="upstream internal details"))
    try:
        with pytest.raises(ExternalAPIError) as caught:
            await client.request_json("GET", "https://example.test/events")
        assert caught.value.status_code == 503
        assert caught.value.attempts == 3
        assert caught.value.kind == "http"
        assert retry_clock.sleeps == [0.5, 1.0]
        assert "upstream internal details" not in str(caught.value)
        assert client.metrics()["retries"] == 2
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_http_network_failure_is_sanitized_and_retried(retry_clock: SimpleNamespace) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret network details", request=request)

    client = await mock_public_client(handler)
    try:
        with pytest.raises(ExternalAPIError) as caught:
            await client.request_json("GET", "https://example.test/events?key=secret")
        assert caught.value.status_code is None
        assert caught.value.attempts == 3
        assert caught.value.kind == "transport"
        assert retry_clock.sleeps == [0.5, 1.0]
        assert "secret" not in str(caught.value)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_http_read_only_post_retry_scope(retry_clock: SimpleNamespace) -> None:
    responses = [httpx.Response(500), httpx.Response(200, json=[{"asset_id": "1"}]), httpx.Response(500)]
    client = await mock_public_client(lambda _: responses.pop(0))
    try:
        assert await client.request_json("POST", "https://example.test/books", json=[]) == [{"asset_id": "1"}]
        with pytest.raises(ExternalAPIError) as caught:
            await client.request_json("POST", "https://example.test/unknown", json={})
        assert caught.value.attempts == 1
        assert retry_clock.sleeps == [0.5]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_http_cancellation_during_cooldown_propagates_and_releases_slot(
    retry_clock: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = await mock_public_client(lambda _: httpx.Response(429, headers={"Retry-After": "4"}))

    async def canceled_sleep(_: float) -> None:
        assert not client._semaphore.locked()
        raise asyncio.CancelledError

    monkeypatch.setattr("app.clients.http.asyncio.sleep", canceled_sleep)
    try:
        with pytest.raises(asyncio.CancelledError):
            await client.request_json("GET", "https://example.test/events")
        assert client.metrics()["attempts"] == 1
        assert client.metrics()["retries"] == 0
        assert not client._semaphore.locked()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_http_origin_cooldown_survives_exhaustion_and_is_independent(
    retry_clock: SimpleNamespace,
) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host)
        if len(requests) <= 3:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"ok": True})

    client = await mock_public_client(handler)
    try:
        with pytest.raises(ExternalAPIError):
            await client.request_json("GET", "https://example.test/events")
        assert retry_clock.sleeps == [2.0, 2.0]
        # A new caller to another service proceeds; the exhausted call leaves
        # a cooldown that the next caller to the original origin must respect.
        assert await client.request_json("GET", "https://other.test/events") == {"ok": True}
        assert retry_clock.sleeps == [2.0, 2.0]
        assert await client.request_json("GET", "https://example.test/markets") == {"ok": True}
        assert retry_clock.sleeps == [2.0, 2.0, 2.0]
        assert client.metrics()["calls"] == 3
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_http_concurrent_callers_share_cooldown_without_blocking_another_origin(
    retry_clock: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[str] = []
    first_waiter, both_waiters, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"ok": True})

    client = await mock_public_client(handler)

    async def controlled_sleep(seconds: float) -> None:
        assert not client._semaphore.locked()
        waits.append(seconds)
        first_waiter.set()
        if len(waits) == 2:
            both_waiters.set()
        await release.wait()
        retry_clock.monotonic += seconds

    jitter = iter([0.0, 0.05, 0.1])
    monkeypatch.setattr("app.clients.http.asyncio.sleep", controlled_sleep)
    monkeypatch.setattr("app.clients.http.random.uniform", lambda _lower, _upper: next(jitter))
    first = asyncio.create_task(client.request_json("GET", "https://example.test/events"))
    second: asyncio.Task[object] | None = None
    try:
        await asyncio.wait_for(first_waiter.wait(), timeout=1)
        second = asyncio.create_task(client.request_json("GET", "https://example.test/markets"))
        await asyncio.wait_for(both_waiters.wait(), timeout=1)
        assert await client.request_json("GET", "https://other.test/events") == {"ok": True}
        assert requests == ["example.test", "other.test"]
        assert waits == [2.05, 2.1]
        release.set()
        assert await asyncio.gather(first, second) == [{"ok": True}, {"ok": True}]
        assert requests.count("example.test") == 3
        assert client.metrics()["attempts"] == 4
    finally:
        release.set()
        first.cancel()
        if second is not None:
            second.cancel()
        await client.close()
