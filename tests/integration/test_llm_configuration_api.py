from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def local_client():
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 51000)) as client:
        yield client


def configuration(key: str = "fixture-private-key", **overrides: str) -> dict[str, str]:
    return {
        "provider": "deepseek",
        "api_base": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "api_key": key,
        **overrides,
    }


def test_configuration_save_is_private_hot_and_no_paid_connection_test(local_client, monkeypatch, caplog) -> None:
    calls = []

    async def no_paid_calls(*args, **kwargs):
        calls.append(1)
        pytest.fail("Saving credentials must not spend API credits")

    monkeypatch.setattr("app.services.translation.DeepSeekTranslator.translate", no_paid_calls)
    initial = local_client.get("/api/llm/config").json()
    assert initial["configured"] is False
    assert initial["source"] == "none"
    translations = app.state.translations
    translations.register({"question": "A public market?"})
    workers = list(translations.tasks)
    response = local_client.put(
        "/api/llm/config",
        json=configuration(),
        headers={"origin": "http://127.0.0.1:8000", "sec-fetch-site": "same-origin"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["configured"] is True
    assert result["source"] == "local"
    assert result["revision"] != initial["revision"]
    assert app.state.translations is translations
    assert translations.provider.api_key == "fixture-private-key"
    assert "A public market?" in translations.registered
    assert all(worker.done() for worker in workers)
    assert local_client.get("/api/llm/config").json() == result
    assert "fixture-private-key" not in response.text
    assert "fixture-private-key" not in caplog.text
    assert "fixture-private-key" not in json.dumps(local_client.get("/api/settings").json())
    assert stat.S_IMODE(app.state.llm_config.path.stat().st_mode) == 0o600
    assert not calls


def test_remove_saved_configuration_returns_to_english_and_never_returns_cached_chinese(local_client) -> None:
    local_client.put("/api/llm/config", json=configuration()).raise_for_status()
    service = app.state.translations
    source = "A public market?"
    service.register({"question": source})

    # Cache population happens through the same application portal thread that owns SQLite.
    async def seed():
        service.database.execute(
            "INSERT OR REPLACE INTO translations VALUES (?, ?, ?, ?)",
            (service.cache_key(source), source, "公开市场?", 1),
        )
        service.database.commit()

    local_client.portal.call(seed)
    assert local_client.post("/api/translations", json={"texts": [source]}).json()["items"][0]["text"] == "公开市场?"
    removal = local_client.delete("/api/llm/config")
    assert removal.status_code == 200
    assert removal.json()["configured"] is False
    assert removal.json()["source"] == "none"
    assert not app.state.llm_config.path.exists()
    translated = local_client.post("/api/translations", json={"texts": [source, "Yes", "No"]}).json()
    assert translated["available"] is False
    assert [item["text"] for item in translated["items"]] == [source, "Yes", "No"]
    assert not service.pending


def test_removal_honestly_falls_back_to_existing_environment_key(local_client, monkeypatch) -> None:
    local_client.put("/api/llm/config", json=configuration()).raise_for_status()
    # The environment reader is kept as a callback so DELETE observes changes, without a restart.
    app.state.llm_config.env_key = lambda: "environment-private-key"
    response = local_client.delete("/api/llm/config")
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["source"] == "environment"
    assert app.state.translations.provider.api_key == "environment-private-key"
    assert "environment-private-key" not in response.text


def test_empty_key_preserves_only_identical_destination_and_keeps_invalid_input_private(local_client) -> None:
    local_client.put("/api/llm/config", json=configuration()).raise_for_status()
    updated = local_client.put("/api/llm/config", json=configuration("", model="explicit-model"))
    assert updated.status_code == 200
    assert updated.json()["model"] == "explicit-model"
    assert app.state.translations.provider.api_key == "fixture-private-key"
    failure = local_client.put(
        "/api/llm/config", json=configuration("", provider="openai-compatible", api_base="https://api.example.com/v1")
    )
    assert failure.status_code == 422
    assert "new API key" in failure.json()["detail"]
    for payload in (configuration(api_key=["private-invalid-key"]), configuration(api_base="https://secret@invalid")):
        failed = local_client.put("/api/llm/config", json=payload)
        assert failed.status_code == 422
        assert "private-invalid-key" not in failed.text
        assert "secret" not in failed.text
        assert "input" not in failed.text
    assert local_client.get("/api/llm/config").json()["model"] == "explicit-model"
    assert (
        local_client.put(
            "/api/llm/config", content="invalid-private-key", headers={"content-type": "application/json"}
        ).status_code
        == 422
    )
    assert (
        local_client.put(
            "/api/llm/config", content="x" * 8193, headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
    assert local_client.put("/api/llm/config", data=configuration()).status_code == 415


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "https://attacker.example"},
        {"origin": "http://127.0.0.1:9999"},
        {"sec-fetch-site": "cross-site"},
        {"origin": "null"},
    ],
)
def test_cross_origin_configuration_is_rejected_without_changing_store(local_client, headers) -> None:
    for method in ("get", "put", "delete"):
        kwargs = {"headers": headers}
        if method == "put":
            kwargs["json"] = configuration()
        response = getattr(local_client, method)("/api/llm/config", **kwargs)
        assert response.status_code == 403
        assert "fixture-private-key" not in response.text
    assert not app.state.llm_config.path.exists()


def test_nonlocal_hosts_and_clients_cannot_configure(monkeypatch) -> None:
    for base_url, peer in (("http://attacker.example:8000", "127.0.0.1"), ("http://127.0.0.1:8000", "192.168.1.2")):
        with TestClient(app, base_url=base_url, client=(peer, 50000)) as client:
            # Non-secret metadata is readable through a Docker bridge or LAN deployment.
            assert client.get("/api/llm/config").status_code == 200
            assert client.put("/api/llm/config", json=configuration()).status_code == 403


def test_saved_provider_survives_application_restart(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.main.LLM_CONFIG_PATH", tmp_path / "llm-config.json")
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 50000)) as client:
        client.put("/api/llm/config", json=configuration()).raise_for_status()
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 50000)) as client:
        result = client.get("/api/llm/config").json()
        assert result["source"] == "local"
        assert result["configured"] is True
        assert app.state.translations.provider.api_key == "fixture-private-key"


def test_hosted_https_configuration_requires_explicit_origin_and_keeps_key_private(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.configuration_origin", "https://myaistock.top")
    with TestClient(app, base_url="https://myaistock.top", client=("192.0.2.10", 50000)) as client:
        assert client.get("/api/llm/config").status_code == 200
        headers = {"origin": "https://myaistock.top", "sec-fetch-site": "same-origin"}
        saved = client.put("/api/llm/config", json=configuration(), headers=headers)
        assert saved.status_code == 200
        assert saved.json()["configured"] is True
        assert "fixture-private-key" not in saved.text
        assert stat.S_IMODE(app.state.llm_config.path.stat().st_mode) == 0o600
        removed = client.delete("/api/llm/config", headers=headers)
        assert removed.status_code == 200
        assert removed.json()["configured"] is False


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"origin": "null"},
        {"origin": "https://attacker.example"},
        {"origin": "https://myaistock.top/"},
        {"origin": "https://myaistock.top", "sec-fetch-site": "same-site"},
        {"origin": "https://myaistock.top", "sec-fetch-site": "cross-site"},
    ],
)
def test_hosted_configuration_rejects_cross_site_or_missing_origin(monkeypatch, headers) -> None:
    monkeypatch.setattr("app.main.settings.configuration_origin", "https://myaistock.top")
    with TestClient(app, base_url="https://myaistock.top", client=("192.0.2.10", 50000)) as client:
        assert client.put("/api/llm/config", json=configuration(), headers=headers).status_code == 403
        assert client.delete("/api/llm/config", headers=headers).status_code == 403
        assert not app.state.llm_config.path.exists()
        if headers:
            assert client.get("/api/llm/config", headers=headers).status_code == 403


@pytest.mark.parametrize(
    "base_url",
    ["http://myaistock.top", "https://attacker.example", "http://127.0.0.1:8011", "https://localhost:8011"],
)
def test_hosted_configuration_has_no_loopback_or_forwarded_header_bypass(monkeypatch, base_url: str) -> None:
    monkeypatch.setattr("app.main.settings.configuration_origin", "https://myaistock.top")
    with TestClient(app, base_url=base_url, client=("127.0.0.1", 50000)) as client:
        headers = {
            "origin": "https://myaistock.top",
            "sec-fetch-site": "same-origin",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "myaistock.top",
        }
        assert client.get("/api/llm/config", headers=headers).status_code == 403
        assert client.put("/api/llm/config", json=configuration(), headers=headers).status_code == 403
        assert client.delete("/api/llm/config", headers=headers).status_code == 403
        assert not app.state.llm_config.path.exists()
