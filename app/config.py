from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EditableScannerParameters(BaseModel):
    minimum_net_profit: Decimal = Field(ge=0, le=1000)
    minimum_net_roi: Decimal = Field(ge=0, le=1)
    default_quantity: Decimal = Field(gt=0, le=100000)
    slippage_rate: Decimal = Field(ge=0, le=0.25)
    safety_rate: Decimal = Field(ge=0, le=0.25)


EDITABLE_SETTING_KEYS = tuple(EditableScannerParameters.model_fields)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PMS_", env_file=".env", extra="ignore")

    app_name: str = "Polymarket Market Scanner"
    version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
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

    @field_validator(
        "minimum_liquidity",
        "minimum_volume",
        "default_quantity",
        "minimum_executable_quantity",
        "minimum_net_profit",
        "minimum_net_roi",
        "slippage_rate",
        "safety_rate",
        "extra_cost",
    )
    @classmethod
    def finite_financial_setting(cls, value: str, info: object) -> str:
        try:
            number = Decimal(value)
            if not number.is_finite() or number < 0:
                raise ValueError("扫描参数必须是非负有限数值")
            name = getattr(info, "field_name", "")
            if name == "default_quantity" and not Decimal("0") < number <= Decimal("100000"):
                raise ValueError("每腿目标数量必须大于零且不超过 100000")
            limits = {
                "minimum_net_profit": "1000",
                "minimum_net_roi": "1",
                "slippage_rate": "0.25",
                "safety_rate": "0.25",
                "extra_cost": "10000",
            }
            if name in limits and number > Decimal(limits[name]):
                raise ValueError("扫描参数超过支持的范围")
        except InvalidOperation:
            raise ValueError("扫描参数必须是非负有限数值") from None
        return str(number)

    @property
    def database_relative_path(self) -> str:
        return self.database_url.removeprefix("sqlite:///")

    def ensure_directories(self) -> None:
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validated_scanner_parameters(settings: Settings, stored: Mapping[str, str]) -> dict[str, str]:
    values = {key: stored.get(key, getattr(settings, key)) for key in EDITABLE_SETTING_KEYS}
    try:
        validated = EditableScannerParameters.model_validate(values)
    except ValueError:
        raise ValueError("保存的扫描参数未通过校验") from None
    return {key: str(value) for key, value in validated.model_dump().items()}
