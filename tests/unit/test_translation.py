from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.services.translation import MODEL, DeepSeekTranslator, TranslationFailure, TranslationService, source_chunks


def response_json(output: dict[str, str], finish: str = "stop") -> dict:
    return {"choices": [{"finish_reason": finish, "message": {"content": json.dumps(output)}}]}


async def test_provider_uses_requested_model_and_server_only_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == MODEL == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        assert "test-key" not in str(body)
        return httpx.Response(200, json=response_json({"0": "比特币会突破 $100,000 吗?"}))

    provider = DeepSeekTranslator("test-key", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        assert await provider.translate(["Will Bitcoin exceed $100,000?"]) == ["比特币会突破 $100,000 吗?"]
    finally:
        await provider.close()


async def test_numeric_formatting_is_allowed_without_changing_values() -> None:
    provider = DeepSeekTranslator(
        "test-key",
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json=response_json({"0": "2026年比特币会突破 $100000 吗?", "1": "价格会达到 $0.5 吗?"})
                )
            )
        ),
    )
    try:
        translated = await provider.translate(["Will Bitcoin exceed $100,000 in 2026?", "Will price reach $0.50?"])
        assert all(isinstance(value, str) for value in translated)
    finally:
        await provider.close()


async def test_bad_single_item_does_not_discard_good_translations(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        sources = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.extend(sources.values())
        return httpx.Response(
            200,
            json=response_json(
                {k: "比特币会突破 $100,000 吗?" if "Bitcoin" in v else "价格会达到吗?" for k, v in sources.items()}
            ),
        )

    provider = DeepSeekTranslator("test-key", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    service = TranslationService(tmp_path / "translations.db", provider)
    await service.start()
    try:
        sources = ["Will Bitcoin exceed $100,000?", "Will price reach $0.50?"]
        service.register({"question": sources})
        service.resolve(sources)
        await asyncio.wait_for(service.queue.join(), 2)
        items = service.resolve(sources)["items"]
        assert items[0]["status"] == "ready"
        assert items[1]["status"] == "error"
        assert service.cached(sources[0]) is not None
        assert service.cached(sources[1]) is None
        assert calls.count(sources[0]) == 1
        assert calls.count(sources[1]) == 2
    finally:
        await service.close()


async def test_configured_official_v1_base_is_used() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=response_json({"0": "公开市场?"}))

    provider = DeepSeekTranslator(
        "test-key", httpx.AsyncClient(transport=httpx.MockTransport(handler)), api_base="https://api.deepseek.com/v1"
    )
    try:
        await provider.translate(["Public market?"])
        assert calls == ["https://api.deepseek.com/v1/chat/completions"]
    finally:
        await provider.close()


@pytest.mark.parametrize(
    ("output", "finish"),
    [
        ({"0": "比特币会突破吗?"}, "stop"),
        ({"wrong": "比特币会突破 $100,000 吗?"}, "stop"),
        ({"0": "比特币会突破 $100,000 吗?"}, "length"),
        ({"0": ""}, "stop"),
    ],
)
async def test_incomplete_or_corrupted_output_never_becomes_a_translation(output: dict, finish: str) -> None:
    provider = DeepSeekTranslator(
        "test-key",
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response_json(output, finish)))
        ),
    )
    try:
        with pytest.raises(TranslationFailure):
            await provider.translate(["Will Bitcoin exceed $100,000?"])
    finally:
        await provider.close()


async def test_new_text_is_queued_once_cached_and_survives_restart(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        sources = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(sources)
        return httpx.Response(200, json=response_json({k: "中文 " + v for k, v in sources.items()}))

    def provider() -> DeepSeekTranslator:
        return DeepSeekTranslator("test-key", httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    service = TranslationService(tmp_path / "translations.db", provider())
    await service.start()
    try:
        service.register({"question": "New public market?"})
        first = service.resolve(["New public market?", "New public market?"])
        assert first["items"][0]["status"] == "pending"
        assert "test-key" not in str(first)
        service.resolve(["New public market?"])
        await asyncio.wait_for(service.queue.join(), 2)
        assert len(calls) == 1
        assert service.resolve(["New public market?"])["items"][0]["text"] == "中文 New public market?"
        service.register({"question": "Changed public market?"})
        assert service.resolve(["Changed public market?"])["items"][0]["status"] == "pending"
        await asyncio.wait_for(service.queue.join(), 2)
        assert len(calls) == 2
    finally:
        await service.close()
    restarted = TranslationService(tmp_path / "translations.db", provider())
    await restarted.start()
    try:
        restarted.register({"question": "New public market?"})
        assert restarted.resolve(["New public market?"])["items"][0]["status"] == "ready"
        assert len(calls) == 2
    finally:
        await restarted.close()


async def test_only_served_public_fields_are_allowed_and_missing_key_is_honest(tmp_path: Path) -> None:
    service = TranslationService(tmp_path / "translations.db", DeepSeekTranslator(""))
    await service.start()
    try:
        service.register({"question": "New public market?", "tokens": ["private text"], "outcomes": ["Yes", "No"]})
        result = service.resolve(["New public market?", "private text", "Yes"])
        assert result["available"] is False
        assert result["items"][0]["status"] == "error"
        assert result["items"][0]["text"] == "New public market?"
        assert result["items"][1]["status"] == "error"
        assert result["items"][2]["text"] == "是"
        assert not service.pending
        long_rules = "Public rules 2026.\n" * 1200
        service.register({"description": long_rules})
        assert "后端" in service.resolve([source_chunks(long_rules)[0]])["items"][0]["reason"]
        assert "只能翻译" in service.resolve([long_rules[:18000]])["items"][0]["reason"]
        assert "只能翻译" in service.resolve(["unknown nonpublic source"])["items"][0]["reason"]
    finally:
        await service.close()


@pytest.mark.parametrize(
    ("source", "translation"),
    [
        ("Will Bitcoin exceed $100,000?", "比特币会在2026年超过 $100,000 吗?"),
        ("Will temperature be below -5°C?", "温度会低于5°C吗?"),
        ("Will return exceed 5%?", "收益会超过5吗?"),
        ("Will price be < $5?", "价格会 > $5 吗?"),
        ("Will price exceed $5?", "价格会超过 €5 吗?"),
        ("Source https://example.com/rules", "来源其他网站"),
    ],
)
async def test_changed_or_added_quantities_and_settlement_sources_are_rejected(source: str, translation: str) -> None:
    provider = DeepSeekTranslator(
        "test-key",
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response_json({"0": translation})))
        ),
    )
    try:
        with pytest.raises(TranslationFailure):
            await provider.translate([source])
    finally:
        await provider.close()


async def test_date_hyphens_and_chinese_adjacent_negative_temperature_are_valid() -> None:
    provider = DeepSeekTranslator(
        "test-key",
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=response_json({"0": "2026-10-03温度会低于-5°C吗?"}))
            )
        ),
    )
    try:
        assert await provider.translate(["Will temperature be below -5°C on 2026-10-03?"]) == [
            "2026-10-03温度会低于-5°C吗?"
        ]
    finally:
        await provider.close()


async def test_malformed_provider_port_is_sanitized_without_a_network_request() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid provider addresses must never receive the key")

    provider = DeepSeekTranslator(
        "test-key",
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        api_base="https://api.deepseek.com:secret-value",
    )
    try:
        with pytest.raises(TranslationFailure, match="官方 HTTPS") as exc:
            await provider.translate(["Public market?"])
        assert "secret-value" not in str(exc.value)
    finally:
        await provider.close()


async def test_rule_chunks_are_lossless_and_arbitrary_substrings_cannot_spend_credits(tmp_path: Path) -> None:
    service = TranslationService(tmp_path / "translations.db", DeepSeekTranslator(""))
    await service.start()
    try:
        source = "Source rules 2026. 😀\n" * 1600
        parts = source_chunks(source)
        assert len(parts) > 1
        assert "".join(parts) == source
        assert all(len(part.encode("utf-16-le")) <= 36002 for part in parts)
        service.register({"description": source})
        assert all("后端" in item["reason"] for item in service.resolve(parts)["items"])
        assert "只能翻译" in service.resolve(["Source rules 2026."])["items"][0]["reason"]
        assert not service.pending
    finally:
        await service.close()


async def test_provider_error_keeps_original_and_is_not_retried_in_a_loop(tmp_path: Path) -> None:
    calls = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": "provider text must not leak"})

    service = TranslationService(
        tmp_path / "translations.db",
        DeepSeekTranslator("test-key", httpx.AsyncClient(transport=httpx.MockTransport(handler))),
    )
    await service.start()
    try:
        service.register({"question": "A public market?"})
        service.resolve(["A public market?"])
        await asyncio.wait_for(service.queue.join(), 2)
        result = service.resolve(["A public market?"])
        assert result["items"][0]["status"] == "error"
        assert result["items"][0]["text"] == "A public market?"
        assert "provider text" not in str(result)
        assert "test-key" not in str(result)
        service.resolve(["A public market?"])
        assert len(calls) == 1
        assert service.cached("A public market?") is None
    finally:
        await service.close()
