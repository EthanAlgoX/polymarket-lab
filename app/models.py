from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeeStatus(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "FEE_UNKNOWN"


class PriceLevel(BaseModel):
    model_config = ConfigDict(frozen=True)
    price: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    size: Decimal = Field(gt=0, allow_inf_nan=False)


class OrderBook(BaseModel):
    asset_id: str
    market: str = ""
    timestamp: str = ""
    bids: list[PriceLevel] = Field(default_factory=list)
    asks: list[PriceLevel] = Field(default_factory=list)
    tick_size: Decimal | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    min_order_size: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    last_trade_price: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    book_hash: str = ""

    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0].price if self.asks else None


class Market(BaseModel):
    market_id: str
    event_id: str = ""
    condition_id: str
    question: str
    slug: str = ""
    category: str = ""
    description: str = ""
    end_date: str | None = None
    active: bool = False
    closed: bool = False
    accepting_orders: bool = False
    enable_order_book: bool = False
    neg_risk: bool = False
    outcomes: list[str]
    token_ids: list[str]
    yes_token_id: str
    no_token_id: str
    liquidity: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    volume: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    fees_enabled: bool | None = None
    fee_rate: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    raw: dict[str, object] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="after")
    def validate_binary_tokens(self) -> Market:
        labels = [label.strip().casefold() for label in self.outcomes]
        if len(labels) != 2 or set(labels) != {"yes", "no"} or len(self.token_ids) != 2:
            raise ValueError("a scanner market requires exactly two Yes/No outcomes and tokens")
        if any(not token.strip() for token in self.token_ids) or len(set(self.token_ids)) != 2:
            raise ValueError("outcome tokens must be distinct and nonempty")
        if (
            self.yes_token_id != self.token_ids[labels.index("yes")]
            or self.no_token_id != self.token_ids[labels.index("no")]
        ):
            raise ValueError("Yes/No token mapping must preserve the original outcome order")
        if not self.market_id.strip() or not self.condition_id.strip():
            raise ValueError("market and condition identifiers must be nonempty")
        return self


class FeeQuote(BaseModel):
    status: FeeStatus
    base_fee_bps: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    reason: str | None = None

    @model_validator(mode="after")
    def require_rate_for_known_fee(self) -> FeeQuote:
        if self.status is FeeStatus.KNOWN and self.base_fee_bps is None:
            self.status = FeeStatus.UNKNOWN
            self.reason = self.reason or "fee rate absent"
        return self


class DepthResult(BaseModel):
    status: str
    target_quantity: Decimal
    executable_quantity: Decimal
    yes_executable_quantity: Decimal
    no_executable_quantity: Decimal
    yes_average_price: Decimal | None
    no_average_price: Decimal | None
    yes_cost: Decimal
    no_cost: Decimal
    total_cost: Decimal
    settlement_value: Decimal
    gross_profit: Decimal
    estimated_fees: Decimal | None
    slippage_buffer: Decimal
    safety_buffer: Decimal
    extra_cost: Decimal = Decimal("0")
    net_profit: Decimal | None
    net_roi: Decimal | None
    yes_depth_shortfall: Decimal
    no_depth_shortfall: Decimal
    partial_fill: bool
    quote_age: Decimal
    fee_status: FeeStatus
    snapshot_fingerprint: str


class RuntimeStatus(BaseModel):
    started_at: datetime
    gamma_status: str = "未检查"
    clob_status: str = "未检查"
    websocket_status: str = "未连接"
    geoblock_status: str = "未检查"
    geoblock_checked_at: datetime | None = None
    last_market_refresh: datetime | None = None
    last_orderbook_refresh: datetime | None = None
    last_websocket_message: datetime | None = None
    active_market_count: int = 0
    binary_market_count: int = 0
    subscribed_tokens: int = 0
    opportunity_count: int = 0
    websocket_messages: int = 0
    websocket_errors: int = 0
    websocket_reconnects: int = 0
    recent_error: str | None = None
