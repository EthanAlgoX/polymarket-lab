from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PMS_", env_file=".env", extra="ignore")

    app_name: str = "Polymarket Market Scanner"
    version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8000
    gamma_url: str = "https://gamma-api.polymarket.com"
    clob_url: str = "https://clob.polymarket.com"
    websocket_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    geoblock_url: str = "https://polymarket.com/api/geoblock"
    request_timeout: float = Field(default=15.0, ge=1, le=60)
    max_concurrency: int = Field(default=10, ge=1, le=50)
    market_refresh_seconds: int = Field(default=60, ge=15, le=3600)
    rest_refresh_seconds: int = Field(default=5, ge=2, le=300)
    max_quote_age_seconds: int = Field(default=5, ge=1, le=300)
    minimum_liquidity: str = "1000"
    minimum_volume: str = "0"
    default_quantity: str = "10"
    minimum_executable_quantity: str = "1"
    minimum_net_profit: str = "0.10"
    minimum_net_roi: str = "0.002"
    slippage_rate: str = "0.001"
    safety_rate: str = "0.001"
    extra_cost: str = "0.05"
    database_url: str = "sqlite:///data/scanner.db"
    log_level: str = "INFO"
    user_agent: str = "PolymarketMarketScanner/0.1.0 (public-read-only-research)"
    enable_live_scanner: bool = True
    max_markets: int = Field(default=40, ge=5, le=500)

    @property
    def database_relative_path(self) -> str:
        return self.database_url.removeprefix("sqlite:///")

    def ensure_directories(self) -> None:
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
