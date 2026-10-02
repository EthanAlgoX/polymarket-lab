from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

DEEPSEEK_MODEL = "deepseek-flash"
DEEPSEEK_BASE = "https://api.deepseek.com"
PROVIDERS = {"deepseek", "openai-compatible"}


class ConfigurationFailure(Exception):
    """A bounded message that never includes input values or credentials."""


def public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast and not address.is_reserved


def normalize_api_base(provider: str, value: str) -> str:
    try:
        endpoint = urlsplit(value.strip().rstrip("/"))
        host = endpoint.hostname
        if (
            provider not in PROVIDERS
            or endpoint.scheme != "https"
            or not host
            or endpoint.port not in {None, 443}
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
            or len(value) > 512
            or "\\" in value
            or any(char.isspace() for char in value)
        ):
            raise ValueError
        if provider == "deepseek":
            if host != "api.deepseek.com" or endpoint.path not in {"", "/v1"}:
                raise ConfigurationFailure("DeepSeek requires its official HTTPS API base URL.")
        else:
            if not re.fullmatch(r"[a-zA-Z0-9.-]+", host) or "." not in host or host.endswith("."):
                raise ValueError
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and not public_address(host):
                raise ValueError
            if not re.fullmatch(r"(?:/[a-zA-Z0-9._~-]+)*", endpoint.path):
                raise ValueError
            if endpoint.path.lower().endswith(("/chat/completions", "/models")):
                raise ConfigurationFailure("Enter the API base URL, without /chat/completions or /models.")
        return urlunsplit(("https", host, endpoint.path, "", ""))
    except (ValueError, TypeError):
        raise ConfigurationFailure(
            "Use a public HTTPS API base URL on port 443, without credentials or query parameters."
        ) from None


async def validate_public_endpoint(provider: str, value: str) -> str:
    base = normalize_api_base(provider, value)
    if provider == "deepseek":
        # The official provider is restricted to this exact host, never a user-selected destination.
        return base
    try:
        addresses = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, urlsplit(base).hostname, 443, type=socket.SOCK_STREAM), timeout=5
        )
        if not addresses or any(not public_address(str(row[4][0])) for row in addresses):
            raise ValueError
    except (OSError, ValueError, TimeoutError):
        raise ConfigurationFailure("The API host must resolve exclusively to public internet addresses.") from None
    return base


@dataclass(frozen=True)
class LLMConfiguration:
    provider: str = "deepseek"
    api_base: str = DEEPSEEK_BASE
    model: str = DEEPSEEK_MODEL
    api_key: str = field(default="", repr=False)
    source: str = "none"
    revision: str = field(default_factory=lambda: uuid.uuid4().hex)

    def public(self) -> dict[str, Any]:
        return {
            "configured": bool(self.api_key),
            "provider": self.provider,
            "api_base": self.api_base,
            "model": self.model,
            "source": self.source,
            "revision": self.revision,
        }


class LLMConfigStore:
    """A local, ignored credential file; no credential enters application settings or responses."""

    def __init__(self, path: Path, *, env_key: Callable[[], str], env_base: Callable[[], str]) -> None:
        self.path = path
        self.env_key = env_key
        self.env_base = env_base
        self.lock = asyncio.Lock()
        self.current = self._load()

    def _environment(self) -> LLMConfiguration:
        key = self.env_key()
        try:
            base = normalize_api_base("deepseek", self.env_base())
        except ConfigurationFailure:
            # Invalid environment destinations must never receive an existing credential.
            return LLMConfiguration()
        source = "environment" if key else "none"
        revision = hashlib.sha256(f"deepseek|{base}|{DEEPSEEK_MODEL}|{source}".encode()).hexdigest()
        return LLMConfiguration(api_base=base, api_key=key, source=source, revision=revision)

    def _load(self) -> LLMConfiguration:
        try:
            if self.path.is_symlink():
                raise ConfigurationFailure("The local API configuration file must not be a symbolic link.")
            if not self.path.exists():
                return self._environment()
            if self.path.stat().st_size > 8192:
                raise ConfigurationFailure("The local API configuration file is invalid.")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            revision = data.pop("revision", None) if isinstance(data, dict) else None
            if revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{64}", revision)):
                raise ConfigurationFailure("The local API configuration file is invalid.")
            configuration = self.prepare(data, previous=LLMConfiguration())
            if revision is not None:
                configuration = replace(configuration, revision=revision)
            os.chmod(self.path, 0o600)
            return configuration
        except (OSError, ValueError, TypeError, ConfigurationFailure):
            # Do not log corrupt file content or silently send environment credentials to its destination.
            return self._environment()

    @staticmethod
    def prepare(data: Any, *, previous: LLMConfiguration) -> LLMConfiguration:
        if not isinstance(data, dict) or set(data) != {"provider", "api_base", "model", "api_key"}:
            raise ConfigurationFailure("Provide provider, api_base, model and api_key as JSON fields.")
        if any(not isinstance(data[key], str) for key in data):
            raise ConfigurationFailure("API configuration fields must be strings.")
        provider = data["provider"]
        if provider not in PROVIDERS:
            raise ConfigurationFailure("Choose DeepSeek or an OpenAI-compatible provider.")
        base = normalize_api_base(provider, data["api_base"])
        model = data["model"].strip()
        if not model or len(model) > 160 or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/@+-]*", model):
            raise ConfigurationFailure("Enter a valid model ID, up to 160 characters.")
        key = data["api_key"].strip()
        if len(key) > 2048 or any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise ConfigurationFailure("Enter a valid API key without whitespace, up to 2048 characters.")
        if not key:
            if provider != previous.provider or base != previous.api_base or not previous.api_key:
                raise ConfigurationFailure("Enter a new API key when changing provider or API base URL.")
            key = previous.api_key
        revision = hashlib.sha256(f"{provider}|{base}|{model}|local|{uuid.uuid4().hex}".encode()).hexdigest()
        return LLMConfiguration(
            provider=provider, api_base=base, model=model, api_key=key, source="local", revision=revision
        )

    def save(self, configuration: LLMConfiguration) -> None:
        descriptor: int | None = None
        temporary: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_symlink():
                raise ConfigurationFailure("The local API configuration file must not be a symbolic link.")
            descriptor, temporary = tempfile.mkstemp(prefix=".llm-config-", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                descriptor = None  # The file object owns and closes the descriptor from this point.
                if hasattr(os, "fchmod"):
                    os.fchmod(output.fileno(), 0o600)
                else:
                    os.chmod(temporary, 0o600)
                json.dump(
                    {
                        "provider": configuration.provider,
                        "api_base": configuration.api_base,
                        "model": configuration.model,
                        "api_key": configuration.api_key,
                        "revision": configuration.revision,
                    },
                    output,
                )
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise ConfigurationFailure("The local API configuration could not be saved.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

    def remove(self) -> LLMConfiguration:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise ConfigurationFailure("The local API configuration could not be removed.") from None
        return self._environment()
