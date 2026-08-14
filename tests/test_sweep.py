"""Lane A still_free sweep — one cheap ping per host."""

from unittest.mock import AsyncMock, patch

import pytest

from model_radar.cooldown import CooldownBook
from model_radar.providers import Model
from model_radar.scanner import PingResult
from model_radar.sweep import still_free


def _m(provider, model_id, **kw):
    return Model(
        model_id=model_id,
        label=model_id,
        tier="A",
        swe_score="40%",
        context="128k",
        provider=provider,
        **kw,
    )


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
