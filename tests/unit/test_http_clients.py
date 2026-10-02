from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.clients.clob_client import ClobClient
from app.clients.gamma_client import GammaClient
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
