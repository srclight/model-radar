"""Tests for OpenAI-compatible endpoint helpers."""

import pytest

from model_radar.endpoints import get_base_url, get_auth_style, get_openai_endpoint_for_model
from model_radar.providers import get_all_models


def test_get_base_url_openai_compatible():
    """Groq and NVIDIA use standard /v1/chat/completions; base_url strips path."""
    assert "api.groq.com" in get_base_url("groq")
    assert "/openai/v1" in get_base_url("groq")
    assert "chat/completions" not in (get_base_url("groq") or "")
    assert "integrate.api.nvidia.com" in (get_base_url("nvidia") or "")


def test_get_base_url_replicate():
    """Replicate is not OpenAI-compatible; base_url is None."""
    assert get_base_url("replicate") is None


def test_get_auth_style():
    """Google uses query_key; others use bearer."""
    assert get_auth_style("googleai")["type"] == "query_key"
    assert get_auth_style("groq")["type"] == "bearer"
    assert get_auth_style("groq")["env_var"] == "GROQ_API_KEY"


def test_get_openai_endpoint_for_model():
    """Returns base_url, model_id, auth_type for a model."""
    models = [m for m in get_all_models() if m.provider == "groq" and m.model_id == "llama-3.3-70b-versatile"]
    assert len(models) == 1
    out = get_openai_endpoint_for_model(models[0])
    assert out["openai_compatible"] is True
    assert out["model_id"] == "llama-3.3-70b-versatile"
    assert "base_url" in out and out["base_url"]
    assert out["auth_type"] == "bearer"
