"""Tests for the scanner module."""

import pytest

from model_radar.cooldown import COOLDOWNS, CooldownBook


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    COOLDOWNS.clear()
    yield
    COOLDOWNS.clear()
from model_radar.providers import Model
from model_radar.scanner import (
    PingResult,
    ScanState,
    TIMEOUT_SECONDS,
    format_result,
    ping_status_for_http,
    should_cooldown,
    timeout_for,
)


def _model(provider="nvidia", model_id="test/model", label="Test Model",
           tier="A", swe="45.0%", ctx="128k"):
    return Model(model_id=model_id, label=label, tier=tier,
                 swe_score=swe, context=ctx, provider=provider)


def test_ollama_ping_gets_a_longer_timeout():
    assert timeout_for("ollama") >= 90.0
    assert timeout_for("groq") == TIMEOUT_SECONDS
    assert timeout_for("nvidia") == TIMEOUT_SECONDS


def test_scan_state_record():
    state = ScanState()
    state.record("nvidia/test", True, 150.0)
    state.record("nvidia/test", True, 250.0)
    state.record("nvidia/test", False, None)

    assert state.ping_counts["nvidia/test"] == 3
    assert state.success_counts["nvidia/test"] == 2
    assert state.avg_latency("nvidia/test") == 200.0
    assert state.uptime_pct("nvidia/test") == pytest.approx(66.67, abs=0.1)


def test_scan_state_empty():
    state = ScanState()
    assert state.avg_latency("nonexistent") is None
    assert state.uptime_pct("nonexistent") is None


def test_format_result_up():
    m = _model()
    r = PingResult(model=m, status="up", latency_ms=123.456)
    d = format_result(r)
    assert d["status"] == "UP"
    assert d["latency_ms"] == 123.5
    assert d["label"] == "Test Model"
    assert d["tier"] == "A"


def test_format_result_with_error():
    m = _model()
    r = PingResult(model=m, status="error", latency_ms=None, error_detail="connection refused")
    d = format_result(r)
    assert d["status"] == "ERROR"
    assert d["error"] == "connection refused"
    assert d["latency_ms"] is None


def test_format_result_with_state():
    m = _model()
    state = ScanState()
    state.record("nvidia/test/model", True, 100.0)
    state.record("nvidia/test/model", True, 200.0)

    r = PingResult(model=m, status="up", latency_ms=150.0)
    d = format_result(r, state)
    assert d["avg_latency_ms"] == 150.0
    assert d["uptime_pct"] == 100.0


def test_402_and_529_are_overloaded_and_cool():
    assert ping_status_for_http(402, has_key=True) == "overloaded"
    assert ping_status_for_http(529, has_key=True) == "overloaded"
    assert ping_status_for_http(429, has_key=True) == "overloaded"
    assert should_cooldown(402) == "402"
    assert should_cooldown(529) == "529"
    assert should_cooldown(429) == "429"


def test_401_cools_this_key_404_does_not():
    assert ping_status_for_http(401, has_key=True) == "error"
    assert should_cooldown(401) == "401"
    assert ping_status_for_http(404, has_key=True) == "not_found"
    assert should_cooldown(404) is None
    assert should_cooldown(403) is None
    assert should_cooldown(503) is None


@pytest.mark.asyncio
async def test_scan_skips_cooled_providers():
    from unittest.mock import AsyncMock, patch

    from model_radar.scanner import scan_models

    book = CooldownBook()
    book.record("nvidia", "529")
    groq = _model(provider="groq", model_id="g", label="G")
    nvidia = _model(provider="nvidia", model_id="n", label="N")

    async def _ping(client, model, cfg):
        return PingResult(model=model, status="up", latency_ms=10.0)

    with (
        patch("model_radar.scanner.COOLDOWNS", book),
        patch("model_radar.scanner.load_config", return_value={"api_keys": {"groq": "x", "nvidia": "y"}, "providers": {}}),
        patch("model_radar.scanner.get_models_for_discovery", return_value=[groq, nvidia]),
        patch("model_radar.scanner.get_configured_providers", return_value=["groq", "nvidia"]),
        patch("model_radar.scanner.model_in_scope", return_value=True),
        patch("model_radar.scanner._ping_one", new=_ping),
    ):
        results = await scan_models(configured_only=True)

    pinged = {r.model.provider for r in results if r.status == "up"}
    cooled = [r for r in results if r.status == "cooled"]
    assert pinged == {"groq"}
    assert len(cooled) == 1
    assert cooled[0].model.provider == "nvidia"


# --- ProviderThrottle tests ---

from model_radar.scanner import ProviderThrottle


def test_throttle_no_429s():
    t = ProviderThrottle()
    assert t.should_throttle("groq") == 0.0
    assert t.effective_concurrency("groq") == 5
    assert t.is_degraded("groq") is False


def test_throttle_records_429_and_backs_off():
    t = ProviderThrottle()
    t.record_429("groq")
    assert t.should_throttle("groq") >= 1.0
    assert t.effective_concurrency("groq") < 5
    assert t.is_degraded("groq") is False  # needs 2+

    t.record_429("groq")
    assert t.is_degraded("groq") is True
    assert t.effective_concurrency("groq") == 1


def test_throttle_recovers_on_success():
    t = ProviderThrottle()
    t.record_429("groq")
    t.record_429("groq")
    assert t.effective_concurrency("groq") == 1

    # 10 successes should start recovery
    for _ in range(12):
        t.record_success("groq")
    assert t.effective_concurrency("groq") > 1


def test_throttle_global_concurrency():
    t = ProviderThrottle()
    assert t.effective_concurrency() == 5
    t.record_429("groq")
    assert t.effective_concurrency() < 5


# --- CLI dispatch tests ---

import pytest
from unittest.mock import AsyncMock, patch

from model_radar.providers import PROVIDERS


@pytest.mark.asyncio
async def test_ping_one_dispatches_to_cli_provider():
    """When provider is kind='cli', ping() should call ping_cli_provider."""
    class FakeModel:
        model_id = "grok-4"
        provider = "grok"
        label = "Grok 4"
        tier = "S+"
        swe_score = "72.0%"
        context = "256k"

    # Save original provider to restore after test
    original_grok = PROVIDERS.get("grok")
    try:
        # Mark grok as CLI provider for the test
        if "grok" in PROVIDERS:
            PROVIDERS["grok"] = PROVIDERS["grok"].__class__(
                key=PROVIDERS["grok"].key, name=PROVIDERS["grok"].name,
                url=PROVIDERS["grok"].url, env_vars=PROVIDERS["grok"].env_vars,
                models=PROVIDERS["grok"].models, kind="cli",
                cmd="grok", cmd_args=(), prompt_via="arg", model_flag="-m",
            )

        from model_radar.scanner import _ping_one
        with patch("model_radar.scanner.get_api_key", return_value=None), \
             patch("model_radar.cli_provider.ping_cli_provider",
                   return_value=(True, 250.0)) as mock_ping:
            result = await _ping_one(
                AsyncMock(), FakeModel(), cfg={"api_keys": {}, "providers": {}}
            )
        assert result.status == "up"
        assert result.latency_ms == 250.0
        mock_ping.assert_called_once()
    finally:
        # Restore original provider
        if original_grok is not None:
            PROVIDERS["grok"] = original_grok
