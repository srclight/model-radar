"""Vercel AI Gateway: chat catalog filter, credits, and the Jev evaluate path."""

from unittest.mock import MagicMock, patch

import pytest

from model_radar.cost import cost_class, default_is_free
from model_radar.credits import fetch_credits
from model_radar.evaluate import (
    DEFAULT_EVALUATION_MODEL,
    GATEWAY_EVALUATION_URL,
    evaluate,
    validate_questions,
)
from model_radar.guides import get_setup_guide
from model_radar.lanes import lane_for
from model_radar.provider_sync import fetch_vercel_models
from model_radar.providers import PROVIDERS

CFG = {"api_keys": {"vercel": "vck_test"}}


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)


def test_provider_registered():
    p = PROVIDERS["vercel"]
    assert p.url == "https://ai-gateway.vercel.sh/v1/chat/completions"
    assert p.env_vars == ("AI_GATEWAY_API_KEY",)
    assert all(m[0] != DEFAULT_EVALUATION_MODEL for m in p.models)


def test_vercel_is_paid_lane_c():
    assert lane_for("vercel", "openai/gpt-oss-120b") == "C"
    assert default_is_free("vercel") is False
    assert cost_class("vercel", "openai/gpt-oss-120b") == "paid"


def test_setup_guide_has_vercel():
    guide = get_setup_guide("vercel")
    assert "AI_GATEWAY_API_KEY" in str(guide)


class _FakeClient:
    def __init__(self, resp, calls):
        self._resp, self._calls = resp, calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, timeout=None):
        self._calls.append({"url": url, "headers": headers})
        return self._resp

    async def post(self, url, headers=None, json=None, timeout=None):
        self._calls.append({"url": url, "headers": headers, "json": json})
        return self._resp


def _resp(status, body):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    r.text = str(body)
    return r


async def test_fetch_keeps_only_language_models():
    body = {"data": [
        {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B", "type": "language", "context_window": 131072},
        {"id": "typesafe-ai/jev", "name": "Jev", "type": "evaluation", "context_window": 0},
        {"id": "openai/text-embedding-3-small", "type": "embedding"},
        {"id": "google/imagen-4", "type": "image"},
    ]}
    calls = []
    with patch("httpx.AsyncClient", return_value=_FakeClient(_resp(200, body), calls)):
        models = await fetch_vercel_models(api_key="vck_test")
    assert [m.model_id for m in models] == ["openai/gpt-oss-120b"]
    assert models[0].provider == "vercel"
    assert models[0].context_length == 131072
    assert calls[0]["url"] == "https://ai-gateway.vercel.sh/v1/models"


async def test_fetch_without_key_is_empty():
    assert await fetch_vercel_models(api_key=None) == []


def test_credits_reports_balance():
    with patch("model_radar.credits.httpx.get", return_value=_resp(200, {"balance": "4.25", "total_used": "0.75"})):
        out = fetch_credits("vercel", cfg=CFG)
    row = out["results"][0]
    assert row == {"provider": "vercel", "ok": True, "kind": "prepaid_usd", "remaining": 4.25, "used": 0.75}


@pytest.mark.parametrize("questions, fragment", [
    ({}, "non-empty"),
    ({"q": {"type": "essay", "instructions": "x"}}, "type must be"),
    ({"q": {"type": "boolean"}}, "instructions"),
    ({"q": {"type": "choice", "instructions": "x"}}, "option map"),
    ({"q": {"type": "score", "instructions": "x", "criteria": ["only one"]}}, "two ordered levels"),
    ({"q": {"type": "boolean", "instructions": "x", "criteria": {"maybe": "?"}}}, "true and false"),
])
def test_validate_questions_rejects(questions, fragment):
    assert fragment in validate_questions(questions)


def test_validate_questions_accepts_all_types():
    assert validate_questions({
        "b": {"type": "boolean", "instructions": "Refunded?"},
        "c": {"type": "choice", "instructions": "Tone?", "criteria": {"calm": "", "angry": ""}},
        "s": {"type": "score", "instructions": "Clear?", "criteria": ["no", "partly", "yes"]},
    }) is None


async def test_evaluate_sends_gateway_protocol():
    questions = {"refunded": {"type": "boolean", "instructions": "Was a refund issued?"}}
    body = {"answers": {"refunded": {"type": "boolean", "probability": 0.97}},
            "usage": {"inputTokens": 21, "outputTokens": 0}}
    calls = []
    with patch("httpx.AsyncClient", return_value=_FakeClient(_resp(200, body), calls)):
        out = await evaluate("A full refund was issued.", questions, cfg=CFG)
    assert out["ok"] is True
    assert out["answers"]["refunded"]["probability"] == 0.97
    sent = calls[0]
    assert sent["url"] == GATEWAY_EVALUATION_URL
    assert sent["headers"]["ai-model-id"] == "typesafe-ai/jev"
    assert sent["headers"]["ai-evaluation-model-specification-version"] == "4"
    assert sent["headers"]["Authorization"] == "Bearer vck_test"
    assert sent["json"] == {"state": "A full refund was issued.", "questions": questions}


async def test_evaluate_surfaces_card_gate():
    err = {"error": {"message": "AI Gateway requires a valid credit card on file",
                     "type": "customer_verification_required"}}
    with patch("httpx.AsyncClient", return_value=_FakeClient(_resp(403, err), [])):
        out = await evaluate("x", {"q": {"type": "boolean", "instructions": "y"}}, cfg=CFG)
    assert out["ok"] is False
    assert out["http"] == 403
    assert out["error_type"] == "customer_verification_required"


async def test_evaluate_needs_key():
    out = await evaluate("x", {"q": {"type": "boolean", "instructions": "y"}}, cfg={"api_keys": {}})
    assert out["ok"] is False
    assert "key" in out["error"]
