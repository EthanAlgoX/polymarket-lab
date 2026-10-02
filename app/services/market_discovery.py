from __future__ import annotations

import json
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.exceptions import InvalidMarketError
from app.models import Market


def parse_list(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    # Reject malformed entries without deleting positions: outcomes and token
    # arrays must remain aligned, even when an upstream field is incomplete.
    result: list[str] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            return []
        text = str(item).strip()
        if not text:
            return []
        result.append(text)
    return result


def parse_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value) if value in (0, 1) else default
    return default


def parse_decimal(value: object) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return result if result.is_finite() and result >= 0 else Decimal("0")


def normalize_market(raw: dict[str, Any], event_id: str = "") -> Market:
    outcomes = parse_list(raw.get("outcomes"))
    token_ids = parse_list(raw.get("clobTokenIds", raw.get("clob_token_ids")))
    if len(outcomes) != 2 or len(token_ids) != 2:
        raise InvalidMarketError("不是恰好两个结果的市场")
    lowered = [item.casefold() for item in outcomes]
    if "yes" not in lowered or "no" not in lowered:
        raise InvalidMarketError("无法识别 Yes/No 结果")
    yes_token = token_ids[lowered.index("yes")]
    no_token = token_ids[lowered.index("no")]
    if not yes_token or not no_token or yes_token == no_token:
        raise InvalidMarketError("结果 Token ID 缺失")
    active = parse_bool(raw.get("active"))
    closed = parse_bool(raw.get("closed"), default=True)
    accepting = parse_bool(raw.get("acceptingOrders", raw.get("accepting_orders")))
    enabled = parse_bool(raw.get("enableOrderBook", raw.get("enable_order_book")))
    if not active or closed or not accepting or not enabled:
        raise InvalidMarketError("市场当前不可扫描")
    market_value = raw.get("id", raw.get("market_id"))
    condition_value = raw.get("conditionId", raw.get("condition_id"))
    market_id = (
        str(market_value).strip() if isinstance(market_value, (str, int)) and not isinstance(market_value, bool) else ""
    )
    condition_id = condition_value.strip() if isinstance(condition_value, str) else ""
    if not market_id or not condition_id:
        raise InvalidMarketError("市场标识缺失")
    fee_schedule = raw.get("feeSchedule", raw.get("fee_schedule"))
    fee_rate = None
    if isinstance(fee_schedule, dict) and fee_schedule.get("rate") not in (None, ""):
        try:
            parsed_fee_rate = Decimal(str(fee_schedule.get("rate")))
            exponent = Decimal(str(fee_schedule.get("exponent")))
            if (
                parsed_fee_rate.is_finite()
                and parsed_fee_rate >= 0
                and exponent == 1
                and (parsed_fee_rate * Decimal("1000")).is_finite()
            ):
                fee_rate = parsed_fee_rate
        except (DecimalException, ValueError):
            pass
    try:
        return Market(
            market_id=market_id,
            event_id=event_id,
            condition_id=condition_id,
            question=str(raw.get("question", "未命名市场")),
            slug=str(raw.get("slug", "")),
            category=str(raw.get("category", "")),
            description=str(raw.get("description", "")),
            end_date=raw.get("endDate") or raw.get("end_date"),
            active=active,
            closed=closed,
            accepting_orders=accepting,
            enable_order_book=enabled,
            neg_risk=parse_bool(raw.get("negRisk", raw.get("neg_risk"))),
            outcomes=outcomes,
            token_ids=token_ids,
            yes_token_id=yes_token,
            no_token_id=no_token,
            liquidity=parse_decimal(raw.get("liquidityNum", raw.get("liquidity"))),
            volume=parse_decimal(raw.get("volumeNum", raw.get("volume"))),
            fees_enabled=(
                raw.get("feesEnabled", raw.get("fees_enabled"))
                if isinstance(raw.get("feesEnabled", raw.get("fees_enabled")), bool)
                else None
            ),
            fee_rate=fee_rate,
            raw=raw,
        )
    except ValidationError as exc:
        raise InvalidMarketError("市场字段无效") from exc
