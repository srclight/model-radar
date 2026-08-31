"""Lane A still_free sweep — one cheap ping per host."""

from unittest.mock import AsyncMock, patch

import pytest

from model_radar.cooldown import CooldownBook
from model_radar.providers import Model
from model_radar.scanner import PingResult
from model_radar.sweep import _pick_probe_model, _probe_candidates, still_free


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


def test_probe_candidates_skip_ollama_cloud():
    cloud = _m("ollama", "minimax-m2.5:cloud")
    local = _m("ollama", "gemma3:27b")
    cands = _probe_candidates("ollama", [cloud, local])
    assert [m.model_id for m in cands] == ["gemma3:27b"]


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
    assert report["hosts"][0]["model_ids"] == [
        "deepseek-ai/deepseek-v4-flash-0731",
        "01-ai/yi-large",
    ]


@pytest.mark.asyncio
async def test_listed_includes_up_to_three_ids():
    models = [
        _m("nvidia", "nvidia/aaa", tier="S+"),
        _m("nvidia", "nvidia/bbb", tier="S"),
        _m("nvidia", "nvidia/ccc", tier="A"),
        _m("nvidia", "nvidia/ddd", tier="B"),
    ]
    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"nvidia": "n"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "nvidia"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=models),
        patch("model_radar.sweep._ping_one", new_callable=AsyncMock) as ping,
    ):
        report = await still_free(ping=False)
    ping.assert_not_called()
    assert report["hosts"][0]["model_ids"] == ["nvidia/aaa", "nvidia/bbb", "nvidia/ccc"]


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
    assert [m["model_id"] for m in host["models"]] == ["aaa/dead-chat", "zzz/live-chat"]
    assert host["models"][0]["status"] == "not_found"
    assert host["models"][1]["status"] == "up"


@pytest.mark.asyncio
async def test_overloaded_host_is_still_marked_overloaded():
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

    assert report["completion_calls"] == 2
    assert set(calls) == {"aaa/busy", "zzz/other"}
    assert report["hosts"][0]["status"] == "overloaded"


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
    assert len(report["hosts"][0]["models"]) == 3


@pytest.mark.asyncio
async def test_pings_up_to_three_chat_models_per_host():
    models = [
        _m("nvidia", "nvidia/aaa", tier="S+"),
        _m("nvidia", "nvidia/bbb", tier="S"),
        _m("nvidia", "nvidia/ccc", tier="A"),
        _m("nvidia", "nvidia/ddd", tier="B"),
    ]
    calls: list[str] = []

    async def ping(client, model, cfg):
        calls.append(model.model_id)
        return PingResult(model=model, status="up", latency_ms=10.0)

    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"nvidia": "n"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "nvidia"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=models),
        patch("model_radar.sweep._ping_one", new=ping),
    ):
        report = await still_free()

    assert report["completion_calls"] == 3
    assert calls == ["nvidia/aaa", "nvidia/bbb", "nvidia/ccc"]
    host = report["hosts"][0]
    assert host["status"] == "up"
    assert host["model_id"] == "nvidia/aaa"
    assert [m["model_id"] for m in host["models"]] == calls
    assert all(m["status"] == "up" for m in host["models"])


@pytest.mark.asyncio
async def test_http_400_still_tries_next_to_fill_set():
    first = _m("googleai", "gemini-2.5-pro", tier="S+")
    second = _m("googleai", "gemini-2.5-flash", tier="S")
    third = _m("googleai", "gemini-2.5-flash-lite", tier="A+")
    calls: list[str] = []

    async def ping(client, model, cfg):
        calls.append(model.model_id)
        if "pro" in model.model_id:
            return PingResult(model=model, status="error", error_detail="HTTP 400")
        return PingResult(model=model, status="up", latency_ms=15.0)

    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"googleai": "g"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "googleai"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=[first, second, third]),
        patch("model_radar.sweep._ping_one", new=ping),
    ):
        report = await still_free()

    assert report["completion_calls"] == 3
    assert calls == [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]
    host = report["hosts"][0]
    assert host["status"] == "up"
    assert host["model_id"] == "gemini-2.5-flash"
    assert host["models"][0]["status"] == "error"


def test_ollama_probe_prefers_9b_over_27b_flash():
    flash = _m("ollama", "glm-4.7-flash:latest", tier="C")
    nine = _m("ollama", "qwen3.5:9b", tier="C")
    big = _m("ollama", "gemma3:27b", tier="C")
    cands = _probe_candidates("ollama", [flash, nine, big], speed="fast")
    assert [m.model_id for m in cands] == [
        "qwen3.5:9b",
        "gemma3:27b",
        "glm-4.7-flash:latest",
    ]


@pytest.mark.asyncio
async def test_listed_ollama_is_one_model():
    models = [
        _m("ollama", "qwen3.5:9b"),
        _m("ollama", "gemma3:27b"),
        _m("ollama", "glm-4.7-flash:latest"),
    ]
    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "ollama"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=models),
        patch("model_radar.sweep._ping_one", new_callable=AsyncMock) as ping,
    ):
        report = await still_free(ping=False)
    ping.assert_not_called()
    assert report["hosts"][0]["model_id"] == "qwen3.5:9b"
    assert report["hosts"][0]["model_ids"] == ["qwen3.5:9b"]


def test_fast_does_not_treat_gemini_as_mini():
    pro = _m("googleai", "gemini-2.5-pro", tier="S+")
    flash = _m("googleai", "gemini-3.6-flash", tier="S")
    cands = _probe_candidates("googleai", [pro, flash], speed="fast")
    assert [m.model_id for m in cands] == [
        "gemini-3.6-flash",
        "gemini-2.5-pro",
    ]


def test_fast_ranks_small_cloudflare_ahead_of_120b():
    big = _m("cloudflare", "@cf/openai/gpt-oss-120b", tier="S")
    mid = _m("cloudflare", "@cf/openai/gpt-oss-20b", tier="A")
    tiny = _m("cloudflare", "@cf/meta/llama-3.2-3b-instruct", tier="C")
    quality = _probe_candidates("cloudflare", [big, mid, tiny], speed="quality")
    fast = _probe_candidates("cloudflare", [big, mid, tiny], speed="fast")
    assert [m.model_id for m in quality[:3]] == [
        "@cf/openai/gpt-oss-120b",
        "@cf/openai/gpt-oss-20b",
        "@cf/meta/llama-3.2-3b-instruct",
    ]
    assert [m.model_id for m in fast[:3]] == [
        "@cf/meta/llama-3.2-3b-instruct",
        "@cf/openai/gpt-oss-20b",
        "@cf/openai/gpt-oss-120b",
    ]


@pytest.mark.asyncio
async def test_listed_fast_puts_small_models_first():
    models = [
        _m("cloudflare", "@cf/openai/gpt-oss-120b", tier="S"),
        _m("cloudflare", "@cf/openai/gpt-oss-20b", tier="A"),
        _m("cloudflare", "@cf/zai-org/glm-4.7-flash", tier="B+"),
    ]
    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"cloudflare": "t"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "cloudflare"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=models),
        patch("model_radar.sweep._ping_one", new_callable=AsyncMock) as ping,
    ):
        report = await still_free(ping=False, speed="fast")
    ping.assert_not_called()
    assert report["speed"] == "fast"
    ids = report["hosts"][0]["model_ids"]
    assert ids[0] in ("@cf/zai-org/glm-4.7-flash", "@cf/openai/gpt-oss-20b")
    assert ids[-1] == "@cf/openai/gpt-oss-120b" or "@cf/openai/gpt-oss-120b" not in ids[:1]


@pytest.mark.asyncio
async def test_timeout_on_one_model_still_returns_the_others():
    """Parallel pings: a 10s 120B must not hide the 20B that already answered."""
    import asyncio
    import time

    models = [
        _m("cloudflare", "@cf/openai/gpt-oss-120b", tier="S"),
        _m("cloudflare", "@cf/openai/gpt-oss-20b", tier="A"),
        _m("cloudflare", "@cf/meta/llama-3.2-3b-instruct", tier="C"),
    ]

    async def ping(client, model, cfg):
        if "120b" in model.model_id:
            await asyncio.sleep(0.05)
            return PingResult(model=model, status="timeout", latency_ms=10000.0)
        return PingResult(model=model, status="up", latency_ms=30.0)

    t0 = time.monotonic()
    with (
        patch("model_radar.sweep.load_config", return_value={"api_keys": {"cloudflare": "t"}, "providers": {}}),
        patch("model_radar.sweep.in_default_pool", side_effect=lambda c, k: k == "cloudflare"),
        patch("model_radar.sweep.get_models_for_discovery", return_value=models),
        patch("model_radar.sweep._ping_one", new=ping),
    ):
        report = await still_free()
    elapsed = time.monotonic() - t0

    assert report["completion_calls"] == 3
    assert elapsed < 0.15
    host = report["hosts"][0]
    assert host["status"] == "up"
    assert host["model_id"] == "@cf/openai/gpt-oss-20b"
    by_id = {m["model_id"]: m["status"] for m in host["models"]}
    assert by_id["@cf/openai/gpt-oss-120b"] == "timeout"
    assert by_id["@cf/openai/gpt-oss-20b"] == "up"
    assert by_id["@cf/meta/llama-3.2-3b-instruct"] == "up"
