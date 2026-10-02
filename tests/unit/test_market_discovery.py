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
    market = normalize_market(raw_market(feesEnabled=True, feeSchedule={"rate": "0.05", "exponent": 1}))
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


@pytest.mark.parametrize("tokens", [[None, "n"], [{"token": "y"}, "n"], [True, "n"], ["", "y", "n"]])
def test_malformed_token_arrays_do_not_stringify_or_delete_positions(tokens: list[object]) -> None:
    assert parse_list(tokens) == []
    with pytest.raises(InvalidMarketError):
        normalize_market(raw_market(clobTokenIds=tokens))


@pytest.mark.parametrize("value", [None, "", "  ", {}, [], True])
def test_missing_condition_identifiers_are_not_stringified(value: object) -> None:
    with pytest.raises(InvalidMarketError):
        normalize_market(raw_market(conditionId=value))


@pytest.mark.parametrize("value", [None, "unknown", 2, float("nan")])
def test_closed_flag_must_be_known_false_for_scanning(value: object) -> None:
    with pytest.raises(InvalidMarketError):
        normalize_market(raw_market(closed=value))


def test_negative_market_liquidity_and_volume_are_not_admitted() -> None:
    market = normalize_market(raw_market(liquidityNum="-1", volumeNum="-100"))
    assert market.liquidity == market.volume == 0


def test_unrepresentable_fee_scale_is_unknown_instead_of_crashing_market_refresh() -> None:
    assert normalize_market(raw_market(feeSchedule={"rate": "1e1000000", "exponent": 1})).fee_rate is None


@pytest.mark.parametrize("exponent", [None, "", "NaN", "Infinity", 0, 2])
def test_absent_or_unsupported_gamma_fee_exponent_is_unknown(exponent: object) -> None:
    assert (
        normalize_market(raw_market(feesEnabled=True, feeSchedule={"rate": "0.05", "exponent": exponent})).fee_rate
        is None
    )
