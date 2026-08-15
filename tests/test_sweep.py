"""Lane A still_free sweep — one cheap ping per host."""

from unittest.mock import AsyncMock, patch

import pytest

from model_radar.cooldown import CooldownBook
from model_radar.providers import Model
from model_radar.scanner import PingResult
from model_radar.sweep import _pick_probe_model, still_free


def _m(provider, model_id, *, tier="A", **kw):
    return Model(
        model_id=model_id,
        label=model_id,
        tier=tier,
        swe_score="40%",
        context="128k",
        provider=provider,
        **kw,
    )


def test_pick_prefers_better_tier_chat_not_first_catalog_row():
    dead = _m("nvidia", "01-ai/yi-large", tier="C")
    embed = _m("nvidia", "nvidia/nv-embedqa-e5-v5", tier="A")
    live = _m("nvidia", "deepseek-ai/deepseek-v4-flash-0731", tier="A")
    picked = _pick_probe_model("nvidia", [dead, embed, live])
    assert picked is not None
    assert picked.model_id == "deepseek-ai/deepseek-v4-flash-0731"


def test_pick_returns_none_when_only_embeddings():
    embed = _m("nvidia", "baai/bge-m3")
    assert _pick_probe_model("nvidia", [embed]) is None


@pytest.mark.asyncio
async def test_one_completion_per_lane_a_host():
    groq = _m("groq", "llama-fast")
    nvidia = _m("nvidia", "nvidia/foo")
    cerebras = _m("cerebras", "paid-id")  # Lane C — must not ping
    book = CooldownBook()

    async def ping(client, model, cfg):
        return PingResult(model=model, status="up", latency_ms=11.0)

    cfg = {"api_keys": {"groq": "g", "nvidia": "n", "cerebras": "c"}, "providers": {}}
    with (
        patch("model_radar.sweep.load_config", return_value=cfg),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k in ("groq", "nvidia")),
        patch("model_radar.sweep.get_models_for_discovery", return_value=[groq, nvidia, cerebras]),
        patch("model_radar.sweep.COOLDOWNS", book),
        patch("model_radar.sweep._ping_one", new=ping),
    ):
        report = await still_free()

    assert report["completion_calls"] == 2
    providers = {h["provider"]: h for h in report["hosts"]}
    assert providers["groq"]["status"] == "up"
    assert providers["nvidia"]["status"] == "up"
    assert "cerebras" not in providers


@pytest.mark.asyncio
async def test_openrouter_without_free_id_is_skipped():
    paid = _m("openrouter", "openai/gpt-4")
    cfg = {"api_keys": {"openrouter": "k"}, "providers": {}}
    with (
        patch("model_radar.sweep.load_config", return_value=cfg),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "openrouter"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=[paid]),
        patch("model_radar.sweep._ping_one", new_callable=AsyncMock) as ping,
    ):
        report = await still_free()
    ping.assert_not_called()
    assert report["completion_calls"] == 0
    assert report["hosts"][0]["status"] == "skipped"
    assert ":free" in report["hosts"][0]["reason"]


@pytest.mark.asyncio
async def test_cooled_host_is_not_pinged():
    groq = _m("groq", "llama-fast")
    book = CooldownBook()
    book.record("groq", "429")
    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"groq": "g"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "groq"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=[groq]),
        patch("model_radar.sweep.COOLDOWNS", book),
        patch("model_radar.sweep._ping_one", new_callable=AsyncMock) as ping,
    ):
        report = await still_free()
    ping.assert_not_called()
    assert report["completion_calls"] == 0
    assert report["hosts"][0]["status"] == "cooled"
    assert report["hosts"][0]["reason"] == "429"


@pytest.mark.asyncio
async def test_no_ping_mode_uses_zero_completions():
    groq = _m("groq", "llama-fast")
    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"groq": "g"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "groq"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=[groq]),
        patch("model_radar.sweep._ping_one", new_callable=AsyncMock) as ping,
    ):
        report = await still_free(ping=False)
    ping.assert_not_called()
    assert report["completion_calls"] == 0
    assert report["hosts"][0]["status"] == "listed"


@pytest.mark.asyncio
async def test_listed_uses_best_tier_not_first_row():
    dead = _m("nvidia", "01-ai/yi-large", tier="C")
    live = _m("nvidia", "deepseek-ai/deepseek-v4-flash-0731", tier="A")
    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"nvidia": "n"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "nvidia"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=[dead, live]),
        patch("model_radar.sweep._ping_one", new_callable=AsyncMock) as ping,
    ):
        report = await still_free(ping=False)
    ping.assert_not_called()
    assert report["hosts"][0]["model_id"] == "deepseek-ai/deepseek-v4-flash-0731"


@pytest.mark.asyncio
async def test_not_found_tries_next_chat_model():
    first = _m("nvidia", "aaa/dead-chat")
    second = _m("nvidia", "zzz/live-chat")
    calls: list[str] = []

    async def ping(client, model, cfg):
        calls.append(model.model_id)
        if model.model_id.startswith("aaa"):
            return PingResult(model=model, status="not_found", error_detail="HTTP 404")
        return PingResult(model=model, status="up", latency_ms=20.0)

    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"nvidia": "n"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "nvidia"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=[first, second]),
        patch("model_radar.sweep._ping_one", new=ping),
    ):
        report = await still_free()

    assert report["completion_calls"] == 2
    assert calls == ["aaa/dead-chat", "zzz/live-chat"]
    host = report["hosts"][0]
    assert host["status"] == "up"
    assert host["model_id"] == "zzz/live-chat"
    assert host["skipped_ids"] == ["aaa/dead-chat"]


@pytest.mark.asyncio
async def test_overloaded_does_not_retry_next_model():
    first = _m("nvidia", "aaa/busy")
    second = _m("nvidia", "zzz/other")
    calls: list[str] = []

    async def ping(client, model, cfg):
        calls.append(model.model_id)
        return PingResult(model=model, status="overloaded", error_detail="HTTP 429")

    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"nvidia": "n"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "nvidia"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=[first, second]),
        patch("model_radar.sweep._ping_one", new=ping),
    ):
        report = await still_free()

    assert report["completion_calls"] == 1
    assert calls == ["aaa/busy"]
    assert report["hosts"][0]["status"] == "overloaded"
    assert report["hosts"][0]["model_id"] == "aaa/busy"


@pytest.mark.asyncio
async def test_not_found_caps_at_three_tries():
    models = [_m("nvidia", f"m{i}/chat") for i in range(5)]
    calls: list[str] = []

    async def ping(client, model, cfg):
        calls.append(model.model_id)
        return PingResult(model=model, status="not_found", error_detail="HTTP 404")

    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"nvidia": "n"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "nvidia"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=models),
        patch("model_radar.sweep._ping_one", new=ping),
    ):
        report = await still_free()

    assert report["completion_calls"] == 3
    assert len(calls) == 3
    assert report["hosts"][0]["status"] == "not_found"
