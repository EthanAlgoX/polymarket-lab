from __future__ import annotations

from decimal import Decimal

from app.models import DepthResult, FeeStatus, Market


def is_valid_opportunity(
    market: Market,
    result: DepthResult,
    *,
    min_quantity: Decimal,
    min_profit: Decimal,
    min_roi: Decimal,
    max_quote_age: Decimal,
) -> tuple[bool, str]:
    if not market.active or market.closed or not market.accepting_orders or not market.enable_order_book:
        return False, "市场不可交易"
    if any(not value.is_finite() or value < 0 for value in (min_quantity, min_profit, min_roi, max_quote_age)):
        return False, "扫描参数无效"
    if result.status != "VALID":
        return False, result.status
    if result.fee_status is not FeeStatus.KNOWN or result.estimated_fees is None:
        return False, "FEE_UNKNOWN"
    nonnegative = (
        result.quote_age,
        result.executable_quantity,
        result.total_cost,
        result.estimated_fees,
        result.slippage_buffer,
        result.safety_buffer,
        result.extra_cost,
    )
    if any(not value.is_finite() or value < 0 for value in nonnegative) or result.executable_quantity <= 0:
        return False, "计算字段无效"
    if result.partial_fill:
        return False, "PARTIAL"
    if result.quote_age > max_quote_age:
        return False, "行情过期"
    if result.executable_quantity < min_quantity:
        return False, "共同可成交数量不足"
    if (
        result.net_profit is None
        or not result.net_profit.is_finite()
        or result.net_profit <= 0
        or result.net_profit < min_profit
    ):
        return False, "低于最低预计净利润"
    if result.net_roi is None or not result.net_roi.is_finite() or result.net_roi < min_roi:
        return False, "低于最低预计净收益率"
    return True, "有效机会"
