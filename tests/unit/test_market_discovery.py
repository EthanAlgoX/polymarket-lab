from __future__ import annotations

import pytest

from app.exceptions import InvalidMarketError
from app.services.market_discovery import normalize_market, parse_bool, parse_decimal, parse_list


def raw_market(**updates: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "id": "1",
        "conditionId": "condition",
        "question": "Question?",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": ["yes-token", "no-token"],
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "liquidityNum": "2000.50",
    }
    raw.update(updates)
    return raw


@pytest.mark.parametrize(
    ("value", "expected"),
    [(["Yes", "No"], ["Yes", "No"]), ('["Yes","No"]', ["Yes", "No"]), (None, []), ("bad", [])],
)
def test_parse_list(value: object, expected: list[str]) -> None:
    assert parse_list(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [(True, True), ("true", True), ("FALSE", False), (1, True), (None, False)]
)
def test_parse_bool(value: object, expected: bool) -> None:
    assert parse_bool(value) is expected


def test_maps_yes_no_by_position() -> None:
    market = normalize_market(raw_market(feesEnabled=True, feeSchedule={"rate": "0.05"}))
    assert market.yes_token_id == "yes-token"
    assert market.no_token_id == "no-token"
    assert market.fee_rate == parse_decimal("0.05")


def test_maps_reversed_outcome_order() -> None:
    market = normalize_market(raw_market(outcomes='["No","Yes"]', clobTokenIds='["no-token","yes-token"]'))
    assert market.yes_token_id == "yes-token"
    assert market.no_token_id == "no-token"


def test_maps_case_insensitively() -> None:
    market = normalize_market(raw_market(outcomes=["YES", "no"]))
    assert market.yes_token_id == "yes-token"


@pytest.mark.parametrize(
    "updates",
    [
        {"outcomes": ["Up", "Down"]},
        {"outcomes": ["Yes", "No", "Other"], "clobTokenIds": ["1", "2", "3"]},
        {"active": False},
        {"closed": True},
        {"acceptingOrders": False},
        {"enableOrderBook": False},
        {"conditionId": ""},
    ],
)
def test_invalid_market_is_skipped(updates: dict[str, object]) -> None:
    with pytest.raises(InvalidMarketError):
        normalize_market(raw_market(**updates))


@pytest.mark.parametrize(("value", "expected"), [("1.25", "1.25"), ("", "0"), (None, "0"), ("NaN", "0")])
def test_decimal_parsing(value: object, expected: str) -> None:
    assert parse_decimal(value) == parse_decimal(expected)
