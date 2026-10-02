from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.exceptions import ExternalAPIError

logger = logging.getLogger(__name__)


class PublicHTTPClient:
    def __init__(self, timeout: float, user_agent: str, max_concurrency: int) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=max_concurrency, max_keepalive_connections=max_concurrency),
        )
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def close(self) -> None:
        await self._client.aclose()

    async def request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            started = time.perf_counter()
            try:
                async with self._semaphore:
                    response = await self._client.request(method, url, **kwargs)
                duration = (time.perf_counter() - started) * 1000
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "retryable upstream response", request=response.request, response=response
                    )
                if 400 <= response.status_code < 500:
                    raise ExternalAPIError(f"{response.status_code} {url}: {response.text[:160]}")
                response.raise_for_status()
                logger.info("public request succeeded", extra={"event": "rest_ok", "duration_ms": round(duration, 2)})
                return response.json()
            except ExternalAPIError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise ExternalAPIError(f"public endpoint failed after retries: {type(last_error).__name__}")
