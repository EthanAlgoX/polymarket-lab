from __future__ import annotations

from decimal import Decimal

from app.models import DepthResult, Market


def is_valid_opportunity(
    market: Market,
    result: DepthResult,
    *,
    min_quantity: Decimal,
    min_profit: Decimal,
    min_roi: Decimal,
    max_quote_age: Decimal,
) -> tuple[bool, str]:
    if not market.active or market.closed or not market.accepting_orders:
        return False, "市场不可交易"
    if result.status != "VALID":
        return False, result.status
    if result.quote_age > max_quote_age:
        return False, "行情过期"
    if result.executable_quantity < min_quantity:
        return False, "共同可成交数量不足"
    if result.net_profit is None or result.net_profit <= 0 or result.net_profit < min_profit:
        return False, "低于最低预计净利润"
    if result.net_roi is None or result.net_roi < min_roi:
        return False, "低于最低预计净收益率"
    return True, "有效机会"
