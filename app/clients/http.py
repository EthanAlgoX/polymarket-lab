from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.exceptions import ExternalAPIError

logger = logging.getLogger(__name__)
MAX_RETRY_DELAY = 30.0


def _retry_after(response: httpx.Response) -> float | None:
    """Read a bounded server cooldown without trusting arbitrary response text."""
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        seconds = float(header.strip())
    except ValueError:
        try:
            deadline = parsedate_to_datetime(header.strip())
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            seconds = max(0.0, math.ceil(deadline.timestamp() - time.time()))
        except (TypeError, ValueError, OverflowError):
            return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, MAX_RETRY_DELAY)


class PublicHTTPClient:
    def __init__(self, timeout: float, user_agent: str, max_concurrency: int) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=max_concurrency, max_keepalive_connections=max_concurrency),
        )
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._cooldowns: dict[str, float] = {}
        self._metrics: dict[str, int | float | None] = {
            "calls": 0,
            "attempts": 0,
            "retries": 0,
            "rate_limited": 0,
            "last_status": None,
            "last_retry_delay": None,
        }

    async def close(self) -> None:
        await self._client.aclose()

    def metrics(self) -> dict[str, int | float | None]:
        """Return counters without request URLs, response bodies, or credentials."""
        return dict(self._metrics)

    def _increment(self, key: str) -> None:
        self._metrics[key] = int(self._metrics[key] or 0) + 1

    async def _request(
        self, origin: str, method: str, url: str, *, is_retry: bool = False, **kwargs: Any
    ) -> httpx.Response:
        # Cooldown waits do not occupy a connection slot. Recheck after acquiring
        # it because another response may have extended this origin's cooldown.
        while True:
            remaining = self._cooldowns.get(origin, 0.0) - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(min(MAX_RETRY_DELAY, remaining + random.uniform(0.0, 0.25)))
            async with self._semaphore:
                if self._cooldowns.get(origin, 0.0) > time.monotonic():
                    continue
                self._increment("attempts")
                if is_retry:
                    self._increment("retries")
                return await self._client.request(method, url, **kwargs)

    async def request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        self._increment("calls")
        parsed_url = httpx.URL(url)
        origin = f"{parsed_url.scheme}://{parsed_url.host}:{parsed_url.port}"
        method = method.upper()
        # /books is a public batch read despite using POST. Never generalize
        # read retries to transaction or other state-changing POST endpoints.
        retry_allowed = method == "GET" or (method == "POST" and parsed_url.path.rstrip("/") == "/books")
        last_status: int | None = None
        last_delay: float | None = None
        last_kind = "transport"
        for attempt in range(3):
            started = time.perf_counter()
            server_delay: float | None = None
            try:
                response = await self._request(origin, method, url, is_retry=attempt > 0, **kwargs)
                last_status = response.status_code
                self._metrics["last_status"] = last_status
                duration = (time.perf_counter() - started) * 1000
                if response.is_success:
                    payload = response.json()
                    logger.info(
                        "public request succeeded",
                        extra={
                            "event": "rest_ok",
                            "origin": origin,
                            "status": last_status,
                            "duration_ms": round(duration, 2),
                        },
                    )
                    return payload
                if last_status == 429 or last_status >= 500:
                    last_kind = "rate_limit" if last_status == 429 else "http"
                    server_delay = _retry_after(response)
                    if last_status == 429:
                        self._increment("rate_limited")
                    # Even when this call exhausts its retries, other callers
                    # must respect the most recent upstream cooldown.
                    if server_delay is not None:
                        self._cooldowns[origin] = max(self._cooldowns.get(origin, 0.0), time.monotonic() + server_delay)
                else:
                    raise ExternalAPIError(
                        f"public endpoint returned HTTP {last_status}",
                        status_code=last_status,
                        attempts=attempt + 1,
                        kind="http",
                    )
            except httpx.TransportError:
                last_status, last_kind = None, "transport"
                self._metrics["last_status"] = None
            except ValueError:
                last_kind = "invalid_json"
            if attempt == 2 or not retry_allowed:
                break
            delay = min(
                MAX_RETRY_DELAY,
                max(0.5 * (2**attempt), server_delay or 0.0) + random.uniform(0.0, 0.25),
            )
            last_delay = delay
            self._metrics["last_retry_delay"] = round(delay, 3)
            logger.warning(
                "public request will retry",
                extra={
                    "event": "rest_retry",
                    "origin": origin,
                    "status": last_status,
                    "kind": last_kind,
                    "attempt": attempt + 1,
                    "retry_delay": round(delay, 3),
                },
            )
            if last_kind == "rate_limit" or server_delay is not None:
                self._cooldowns[origin] = max(self._cooldowns.get(origin, 0.0), time.monotonic() + delay)
            else:
                await asyncio.sleep(delay)
        logger.warning(
            "public request failed",
            extra={"event": "rest_failed", "origin": origin, "status": last_status, "kind": last_kind},
        )
        raise ExternalAPIError(
            (
                "public endpoint failed after retries (3 attempts)"
                if attempt == 2
                else f"public endpoint failed after {attempt + 1} attempt(s)"
            )
            + f": {last_kind}"
            + (f" (HTTP {last_status})" if last_status is not None else ""),
            status_code=last_status,
            retry_after=server_delay if server_delay is not None else last_delay,
            attempts=attempt + 1,
            kind=last_kind,
        ) from None
