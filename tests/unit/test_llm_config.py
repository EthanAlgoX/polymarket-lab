from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from app.services.llm_config import (
    ConfigurationFailure,
    LLMConfigStore,
    LLMConfiguration,
    normalize_api_base,
    validate_public_endpoint,
)


def store(path: Path, key: str = "") -> LLMConfigStore:
    return LLMConfigStore(path, env_key=lambda: key, env_base=lambda: "https://api.deepseek.com")


def payload(key: str = "fixture-key", **overrides: str) -> dict[str, str]:
    return {
        "provider": "deepseek",
        "api_base": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "api_key": key,
        **overrides,
    }


def test_private_key_is_not_in_configuration_repr_or_public_response() -> None:
    configuration = LLMConfiguration(api_key="fixture-private-key", source="environment")
    assert "fixture-private-key" not in repr(configuration)
    assert configuration.public()["configured"] is True
    assert set(configuration.public()) == {"configured", "provider", "api_base", "model", "source", "revision"}
    assert "fixture-private-key" not in json.dumps(configuration.public())


def test_atomic_local_configuration_survives_restart_and_removal_falls_back(tmp_path: Path) -> None:
    location = tmp_path / "data/llm-config.json"
    configuration_store = store(location, "environment-key")
    assert configuration_store.current.source == "environment"
    configuration = configuration_store.prepare(payload(), previous=configuration_store.current)
    configuration_store.save(configuration)
    assert stat.S_IMODE(location.stat().st_mode) == 0o600
    assert list(location.parent.iterdir()) == [location]
    assert store(location, "environment-key").current.api_key == "fixture-key"
    assert store(location, "environment-key").current.revision == configuration.revision
    assert store(location).current.source == "local"
    restored = configuration_store.remove()
    assert restored.source == "environment"
    assert restored.api_key == "environment-key"
    assert not location.exists()


def test_blank_key_keeps_only_the_same_normalized_destination(tmp_path: Path) -> None:
    previous = store(tmp_path / "config", "environment-key").current
    unchanged = LLMConfigStore.prepare(
        payload("", api_base="https://api.deepseek.com:443/", model="chosen-model"), previous=previous
    )
    assert unchanged.api_key == "environment-key"
    assert unchanged.model == "chosen-model"
    for overrides in (
        {"api_base": "https://api.deepseek.com/v1"},
        {"provider": "openai-compatible", "api_base": "https://api.example.com/v1"},
    ):
        with pytest.raises(ConfigurationFailure, match="new API key"):
            LLMConfigStore.prepare(payload("", **overrides), previous=previous)
    with pytest.raises(ConfigurationFailure, match="new API key"):
        LLMConfigStore.prepare(payload(""), previous=LLMConfiguration())


@pytest.mark.parametrize(
    "base",
    [
        "http://api.example.com/v1",
        "https://api.example.com:8000/v1",
        "https://user:secret@api.example.com/v1",
        "https://api.example.com/v1?key=secret",
        "https://api.example.com/v1#secret",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://10.1.2.3/v1",
        "https://169.254.169.254/v1",
        "https://224.0.0.1/v1",
        "https://api.example.com./v1",
        "https://api.example.com/v1\\secret",
        "https://api.example.com:secret/v1",
    ],
)
def test_invalid_endpoints_are_sanitized(base: str) -> None:
    with pytest.raises(ConfigurationFailure) as exc:
        normalize_api_base("openai-compatible", base)
    assert base not in str(exc.value)
    assert "secret" not in str(exc.value)


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["8.8.8.8", "10.0.0.1"], ["::1"], [], ["224.0.0.1"]])
async def test_custom_provider_dns_cannot_point_to_private_or_mixed_addresses(monkeypatch, addresses) -> None:
    monkeypatch.setattr(
        "app.services.llm_config.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", (address, 443)) for address in addresses],
    )
    with pytest.raises(ConfigurationFailure, match="public internet"):
        await validate_public_endpoint("openai-compatible", "https://api.example.com/v1")


async def test_public_https_compatible_endpoint_is_normalized(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.llm_config.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("8.8.8.8", 443))]
    )
    assert await validate_public_endpoint("openai-compatible", "https://api.example.com:443/api/v1/") == (
        "https://api.example.com/api/v1"
    )
    assert await validate_public_endpoint("deepseek", "https://api.deepseek.com/v1/") == "https://api.deepseek.com/v1"
    with pytest.raises(ConfigurationFailure, match="official HTTPS"):
        normalize_api_base("deepseek", "https://other.example.com")
    for full_resource in ("https://api.example.com/v1/chat/completions", "https://api.example.com/v1/models"):
        with pytest.raises(ConfigurationFailure, match="API base URL"):
            normalize_api_base("openai-compatible", full_resource)


@pytest.mark.parametrize(
    "values",
    [
        {"api_key": ["secret"]},
        {"api_key": "contains whitespace secret"},
        {"provider": "unsupported-secret"},
        {"model": "secret model"},
        {"model": ""},
        {"api_key": "a" * 2049},
        {"extra": "secret"},
    ],
)
def test_invalid_configuration_does_not_echo_values(values) -> None:
    with pytest.raises(ConfigurationFailure) as exc:
        LLMConfigStore.prepare({**payload(), **values}, previous=LLMConfiguration())
    assert "secret" not in str(exc.value)


def test_corrupt_or_symlink_configuration_does_not_load_its_destination(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text(json.dumps(payload("private-key")))
    link = tmp_path / "linked.json"
    link.symlink_to(target)
    configuration_store = store(link, "environment-key")
    assert configuration_store.current.source == "environment"
    with pytest.raises(ConfigurationFailure, match="symbolic link"):
        configuration_store.save(LLMConfiguration(api_key="other-key"))
    target.write_text('{"api_key":"private-key"}')
    assert store(target, "environment-key").current.source == "environment"
