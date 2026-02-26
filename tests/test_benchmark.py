"""Tests for the benchmark module."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from model_radar.benchmark import (
    CHALLENGES,
    _check_exact_hello,
    _check_is_prime,
    _check_json_output,
    _check_list_comp,
    _check_math_5461,
    benchmark_model,
    benchmark_models,
)
from model_radar.providers import Model


def _model(provider="nvidia", model_id="test/model", label="Test Model",
           tier="A", swe="45.0%", ctx="128k"):
    return Model(model_id=model_id, label=label, tier=tier,
                 swe_score=swe, context=ctx, provider=provider)


# ---------------------------------------------------------------------------
# Validator unit tests
# ---------------------------------------------------------------------------

class TestValidators:
    def test_math_correct(self):
        ok, _ = _check_math_5461("The answer is 5461.")
        assert ok

    def test_math_wrong(self):
        ok, _ = _check_math_5461("5400")
        assert not ok

    def test_hello_correct(self):
        ok, _ = _check_exact_hello("HELLO WORLD")
        assert ok

    def test_hello_case_insensitive(self):
        ok, _ = _check_exact_hello("hello world")
        assert ok

    def test_hello_wrong(self):
        ok, _ = _check_exact_hello("HI THERE")
        assert not ok

    def test_is_prime_correct(self):
        code = """def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True"""
        ok, _ = _check_is_prime(code)
        assert ok

    def test_is_prime_missing(self):
        ok, _ = _check_is_prime("Here's a function that checks primality...")
        assert not ok

    def test_list_comp_correct(self):
        ok, _ = _check_list_comp("It prints [0, 1, 4, 9, 16]")
        assert ok

    def test_list_comp_no_spaces(self):
        ok, _ = _check_list_comp("[0,1,4,9,16]")
        assert ok

    def test_list_comp_wrong(self):
        ok, _ = _check_list_comp("[0, 1, 4, 9]")
        assert not ok

    def test_json_correct(self):
        ok, _ = _check_json_output('{"name": "test", "value": 42}')
        assert ok

    def test_json_with_code_fence(self):
        ok, _ = _check_json_output('```json\n{"name": "test", "value": 42}\n```')
        assert ok

    def test_json_wrong_values(self):
        ok, _ = _check_json_output('{"name": "wrong", "value": 0}')
        assert not ok

    def test_json_invalid(self):
        ok, _ = _check_json_output("This is not JSON at all")
        assert not ok


# ---------------------------------------------------------------------------
# benchmark_model tests
# ---------------------------------------------------------------------------

def _make_call_response(content: str) -> dict:
    """Build a fake _call_model response."""
    return {
        "content": content,
        "model_id": "test/model",
        "model_label": "Test Model",
        "provider": "NIM",
        "provider_key": "nvidia",
        "tier": "A",
        "latency_ms": 500.0,
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


# Responses that should pass all 5 challenges
PERFECT_RESPONSES = [
    "5461",                                    # math
    "HELLO WORLD",                             # instruction
    "def is_prime(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n**0.5)+1):\n        if n % i == 0:\n            return False\n    return True",  # code
    "[0, 1, 4, 9, 16]",                        # reasoning
    '{"name": "test", "value": 42}',           # json
]


@pytest.mark.asyncio
async def test_benchmark_model_perfect():
    """Model that passes all challenges scores 5/5."""
    m = _model()
    cfg = {"api_keys": {"nvidia": "test-key"}, "providers": {}}

    call_idx = 0
    async def mock_call(model, messages, cfg, max_tokens, temperature):
        nonlocal call_idx
        content = PERFECT_RESPONSES[call_idx]
        call_idx += 1
        return _make_call_response(content)

    with patch("model_radar.benchmark._call_model", side_effect=mock_call), \
         patch("model_radar.benchmark.load_config", return_value=cfg):
        result = await benchmark_model(m, cfg)

    assert result["passed"] == 5
    assert result["total"] == 5
    assert result["pct"] == 100
    assert result["score"] == "5/5"


@pytest.mark.asyncio
async def test_benchmark_model_all_fail():
    """Model that fails all challenges scores 0/5."""
    m = _model()
    cfg = {"api_keys": {"nvidia": "test-key"}, "providers": {}}

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        return _make_call_response("garbled nonsense أهلا สวัสดี")

    with patch("model_radar.benchmark._call_model", side_effect=mock_call), \
         patch("model_radar.benchmark.load_config", return_value=cfg):
        result = await benchmark_model(m, cfg)

    assert result["passed"] == 0
    assert result["pct"] == 0


@pytest.mark.asyncio
async def test_benchmark_model_api_error():
    """API errors count as failures."""
    m = _model()
    cfg = {"api_keys": {"nvidia": "test-key"}, "providers": {}}

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        return {"error": "HTTP 429", "detail": "rate limited"}

    with patch("model_radar.benchmark._call_model", side_effect=mock_call), \
         patch("model_radar.benchmark.load_config", return_value=cfg):
        result = await benchmark_model(m, cfg)

    assert result["passed"] == 0
    for r in result["results"]:
        assert "API error" in r["detail"]


@pytest.mark.asyncio
async def test_benchmark_models_no_models():
    """Should return error when no models available."""
    with patch("model_radar.benchmark.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.benchmark.scan_models", return_value=[]):
        results = await benchmark_models(min_tier="A", count=3)
    assert len(results) == 1
    assert "error" in results[0]


@pytest.mark.asyncio
async def test_benchmark_models_not_found():
    """Should return error for unknown model_id."""
    with patch("model_radar.benchmark.load_config", return_value={"api_keys": {}, "providers": {}}):
        results = await benchmark_models(model_id="nonexistent/model")
    assert len(results) == 1
    assert "error" in results[0]
