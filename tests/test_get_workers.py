"""Smoke tests for get_workers: provider diversity, tier filtering, degraded handling."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from model_radar.providers import Model
from model_radar.scanner import PingResult


def _model(model_id: str, provider: str, tier: str = "S") -> Model:
    """Create a test model using a real provider key."""
    return Model(
        model_id=model_id,
        label=model_id,
        tier=tier,
        swe_score="60%",
        context="128k",
        provider=provider,
    )


def _ping(model: Model, latency_ms: float = 200.0) -> PingResult:
    return PingResult(model=model, status="up", latency_ms=latency_ms)


# Use real provider keys so format_result can look up PROVIDERS[key].name
P1, P2, P3, P4, P5 = "nvidia", "groq", "cerebras", "openrouter", "sambanova"


@pytest.mark.asyncio
async def test_get_workers_returns_provider_diverse_results():
    """get_workers returns exactly N models from N distinct providers."""
    from model_radar.server import get_workers

    models = [
        _ping(_model("model-a", P1, "S+"), 100),
        _ping(_model("model-a2", P1, "S"), 110),  # same provider, should be skipped
        _ping(_model("model-b", P2, "S"), 150),
        _ping(_model("model-c", P3, "A+"), 200),
        _ping(_model("model-d", P4, "A"), 250),
        _ping(_model("model-e", P5, "A"), 300),
    ]

    with patch("model_radar.server.scan_models", new_callable=AsyncMock, return_value=models):
        result = json.loads(await get_workers(count=4, min_tier="A", verified=False))

    assert result["count"] == 4
    assert result["distinct_providers"] == 4

    providers = [w["provider_key"] for w in result["workers"]]
    assert len(set(providers)) == 4, f"Expected 4 distinct providers, got {providers}"

    # Should pick one from each of the first 4 distinct providers (skipping model-a2)
    model_ids = [w["model_id"] for w in result["workers"]]
    assert model_ids == ["model-a", "model-b", "model-c", "model-d"]


@pytest.mark.asyncio
async def test_get_workers_respects_tier_filter():
    """All returned workers must meet the min_tier threshold."""
    from model_radar.server import get_workers

    # scan_models handles tier filtering upstream, so simulate pre-filtered results
    filtered = [
        _ping(_model("s-plus", P1, "S+"), 100),
        _ping(_model("s-tier", P2, "S"), 150),
        _ping(_model("a-tier", P3, "A"), 200),
    ]

    with patch("model_radar.server.scan_models", new_callable=AsyncMock, return_value=filtered):
        result = json.loads(await get_workers(count=4, min_tier="A", verified=False))

    for w in result["workers"]:
        assert w["tier"] in {"S+", "S", "A+", "A", "A-"}, f"Unexpected tier {w['tier']}"


@pytest.mark.asyncio
async def test_get_workers_skips_down_models():
    """Only UP models are included — down/error models are filtered out."""
    from model_radar.server import get_workers

    models = [
        _ping(_model("up-1", P1), 100),
        PingResult(model=_model("down-1", P2), status="error", latency_ms=None),
        PingResult(model=_model("timeout-1", P3), status="timeout", latency_ms=None),
        _ping(_model("up-2", P4), 200),
    ]

    with patch("model_radar.server.scan_models", new_callable=AsyncMock, return_value=models):
        result = json.loads(await get_workers(count=4, min_tier="A", verified=False))

    assert result["count"] == 2
    model_ids = [w["model_id"] for w in result["workers"]]
    assert model_ids == ["up-1", "up-2"]


@pytest.mark.asyncio
async def test_get_workers_graceful_when_fewer_providers_available():
    """When fewer providers are available than requested, returns what it can."""
    from model_radar.server import get_workers

    models = [
        _ping(_model("only-1", P1), 100),
        _ping(_model("only-2", P2), 200),
    ]

    with patch("model_radar.server.scan_models", new_callable=AsyncMock, return_value=models):
        result = json.loads(await get_workers(count=5, min_tier="A", verified=False))

    assert result["count"] == 2
    assert result["distinct_providers"] == 2


@pytest.mark.asyncio
async def test_get_workers_skips_degraded_then_relaxes():
    """Degraded providers are skipped initially but included if needed to fill count."""
    from model_radar.server import get_workers, _state

    models = [
        _ping(_model("fast", P1), 100),
        _ping(_model("degraded-model", P2), 150),
        _ping(_model("slow", P3), 300),
    ]

    # Mark P2 as degraded (need >=2 recent 429s)
    _state.throttle.record_429(P2)
    _state.throttle.record_429(P2)

    try:
        with patch("model_radar.server.scan_models", new_callable=AsyncMock, return_value=models):
            result = json.loads(await get_workers(count=3, min_tier="A", verified=False))

        assert result["count"] == 3
        # All 3 providers used (degraded one included in relaxation pass to fill count)
        providers = {w["provider_key"] for w in result["workers"]}
        assert len(providers) == 3
    finally:
        # Clean up throttle state
        _state.throttle._recent_429s.pop(P2, None)
        _state.throttle._recent_calls.pop(P2, None)
        _state.throttle._concurrency.pop(P2, None)
