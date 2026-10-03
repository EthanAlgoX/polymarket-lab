from __future__ import annotations

import pytest

from app.config import Settings


@pytest.mark.parametrize("origin", ["", "https://myaistock.top", "https://dashboard.example.com:8443"])
def test_explicit_configuration_origin_is_canonical_https(origin: str) -> None:
    assert Settings(_env_file=None, configuration_origin=origin).configuration_origin == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://myaistock.top",
        "https://myaistock.top/",
        "https://myaistock.top/polymarket-lab",
        "https://myaistock.top?",
        "https://myaistock.top#",
        "https://myaistock.top?q=1",
        "https://myaistock.top#settings",
        "https://private-key@myaistock.top",
        "https://myaistock.top:443",
        "https://myaistock.top:0",
        "https://myaistock.top:65536",
        "https://MYAISTOCK.TOP",
        "https://localhost",
        "https://myai\nstock.top",
        "https://myaistock.top\\attacker.example",
        " https://myaistock.top",
    ],
)
def test_configuration_origin_rejects_ambiguous_or_insecure_values(origin: str) -> None:
    with pytest.raises(ValueError, match="canonical HTTPS origin"):
        Settings(_env_file=None, configuration_origin=origin)
