from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.clients.http import PublicHTTPClient
from app.models import FeeQuote, FeeStatus, OrderBook
from app.services.orderbooks import normalize_orderbook


class ClobClient:
    def __init__(self, http: PublicHTTPClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    async def fetch_books(self, token_ids: list[str]) -> dict[str, OrderBook]:
        result: dict[str, OrderBook] = {}
        for offset in range(0, len(token_ids), 500):
            body = [{"token_id": token} for token in token_ids[offset : offset + 500]]
            payload = await self.http.request_json("POST", f"{self.base_url}/books", json=body)
            if not isinstance(payload, list):
                raise ValueError("unexpected CLOB books response")
            for item in payload:
                if isinstance(item, dict):
                    book = normalize_orderbook(item)
                    if book.asset_id:
                        result[book.asset_id] = book
        return result

    async def fetch_fee(self, condition_id: str, fees_enabled: bool | None) -> FeeQuote:
        if fees_enabled is False:
            return FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0"))
        try:
            payload = await self.http.request_json("GET", f"{self.base_url}/markets/{condition_id}")
        except Exception as exc:
            return FeeQuote(status=FeeStatus.UNKNOWN, reason=type(exc).__name__)
        if not isinstance(payload, dict):
            return FeeQuote(status=FeeStatus.UNKNOWN, reason="invalid market fee response")
        fee_data = payload.get("fd")
        value: object = fee_data.get("r") if isinstance(fee_data, dict) else None
        if value is None:
            if fees_enabled is False:
                value = 0
            else:
                return FeeQuote(status=FeeStatus.UNKNOWN, reason="fee rate absent")
        try:
            rate = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return FeeQuote(status=FeeStatus.UNKNOWN, reason="invalid fee rate")
        if not rate.is_finite() or rate < 0:
            return FeeQuote(status=FeeStatus.UNKNOWN, reason="invalid fee rate")
        return FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=rate * Decimal("1000"))
