"""Typed evaluation models through Vercel AI Gateway (TypeSafe Jev and kin).

These models never generate text. A request carries shared ``state`` and a map
of named ``questions``; each answer is a probability (boolean), a chosen option
with its distribution (choice), or a position on ordered levels (score).

Wire format is the AI SDK gateway's evaluation-model protocol (spec v4), read
from ``@ai-sdk/gateway`` 4.0.85: POST {base}/evaluation-model with the model id
in the ``ai-model-id`` header.

Question shapes (``criteria`` describes the options or levels):
  boolean: {"type": "boolean", "instructions": "...", "criteria"?: {"true": ..., "false": ...}}
  choice:  {"type": "choice",  "instructions": "...", "criteria": {"A": "desc", "B": "desc"}}
  score:   {"type": "score",   "instructions": "...", "criteria": ["low desc", "mid desc", "high desc"]}
"""

from __future__ import annotations

import time

import httpx

from .config import get_api_key, load_config

GATEWAY_EVALUATION_URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
DEFAULT_EVALUATION_MODEL = "typesafe-ai/jev"
QUESTION_TYPES = ("boolean", "choice", "score")


def validate_questions(questions: dict) -> str | None:
    """Return an error message, or None when the question map is well formed."""
    if not isinstance(questions, dict) or not questions:
        return "questions must be a non-empty map of name -> question"
    for name, q in questions.items():
        if not isinstance(q, dict):
            return f"question {name!r} must be an object"
        qtype = q.get("type")
        if qtype not in QUESTION_TYPES:
            return f"question {name!r}: type must be one of {', '.join(QUESTION_TYPES)}"
        if q.get("instructions") in (None, ""):
            return f"question {name!r}: instructions are required"
        criteria = q.get("criteria")
        if qtype == "choice" and (not isinstance(criteria, dict) or not criteria):
            return f"question {name!r}: choice criteria must be a non-empty option map"
        if qtype == "score" and (not isinstance(criteria, list) or len(criteria) < 2):
            return f"question {name!r}: score criteria must list at least two ordered levels"
        if qtype == "boolean" and criteria is not None and (
            not isinstance(criteria, dict) or set(criteria) - {"true", "false"}
        ):
            return f"question {name!r}: boolean criteria may only describe true and false"
    return None


async def evaluate(
    state: str | dict | list,
    questions: dict,
    model_id: str = DEFAULT_EVALUATION_MODEL,
    timeout: float = 30.0,
    cfg: dict | None = None,
) -> dict:
    """Run one evaluation request. Never raises for HTTP or validation errors."""
    err = validate_questions(questions)
    if err:
        return {"ok": False, "error": err}
    cfg = cfg if cfg is not None else load_config()
    api_key = get_api_key(cfg, "vercel")
    if not api_key:
        return {"ok": False, "error": "no Vercel AI Gateway key (AI_GATEWAY_API_KEY or configure_key('vercel', ...))"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "ai-gateway-protocol-version": "0.0.1",
        "ai-gateway-auth-method": "api-key",
        "ai-evaluation-model-specification-version": "4",
        "ai-model-id": model_id,
    }
    body = {"state": state, "questions": questions}
    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(GATEWAY_EVALUATION_URL, headers=headers, json=body, timeout=timeout)
        except httpx.HTTPError as e:
            return {"ok": False, "model_id": model_id, "error": f"{type(e).__name__}: {e}"}
    latency_ms = round((time.monotonic() - t0) * 1000)

    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code != 200:
        error = data.get("error") if isinstance(data, dict) else None
        out = {"ok": False, "model_id": model_id, "http": resp.status_code, "latency_ms": latency_ms}
        if isinstance(error, dict):
            out["error"] = error.get("message") or str(error)
            out["error_type"] = error.get("type")
        else:
            out["error"] = error or resp.text[:300]
        return out

    return {
        "ok": True,
        "model_id": model_id,
        "latency_ms": latency_ms,
        "answers": data.get("answers", {}),
        "usage": data.get("usage"),
        "rounding": data.get("rounding"),
        "warnings": data.get("warnings") or [],
    }
