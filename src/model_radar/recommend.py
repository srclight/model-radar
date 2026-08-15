"""Recommend a short, diverse live-chat lineup for a job.

Does not ping. Uses the catalog + cost_class + light name heuristics.
Subscription CLIs are opt-in (include_subscriptions=True).
"""

from __future__ import annotations

from .config import get_configured_providers, load_config
from .cost import is_chat_model, is_cloud_route, model_card
from .db import get_models_for_discovery
from .lanes import model_in_scope
from .providers import TIER_ORDER, Model

JOBS = ("translate", "rewrite", "review", "code", "dict")

# Name tokens that tend to work for each job. Live ids stay C after refresh,
# so we cannot rely on min_tier="A".
_JOB_HINTS: dict[str, tuple[str, ...]] = {
    "translate": (
        "hy-mt", "minimax", "qwen", "glm", "gemma", "gpt-oss",
        "nemotron", "kimi", "mistral",
    ),
    "dict": (
        "hy-mt", "minimax", "qwen", "glm", "gemma", "gpt-oss",
        "nemotron", "kimi", "mistral",
    ),
    "rewrite": (
        "minimax", "qwen", "glm", "kimi", "gemma", "gpt-oss",
        "claude", "grok", "gemini", "sonnet", "opus",
    ),
    "review": (
        "kimi", "glm", "deepseek", "qwen", "minimax", "grok",
        "claude", "sonnet", "opus", "codex", "gpt-5", "nemotron",
        "devstral",
    ),
    "code": (
        "kimi", "glm", "deepseek", "qwen", "coder", "codex",
        "devstral", "nemotron", "gpt-oss", "minimax",
    ),
}


# Prefer these hosts for a job (first-party / local / fast free-tier).
_JOB_PROVIDERS: dict[str, tuple[str, ...]] = {
    "translate": ("minimax", "ollama", "cerebras", "groq"),
    "dict": ("minimax", "ollama", "cerebras", "groq"),
    "rewrite": ("minimax", "googleai", "cerebras", "ollama"),
    "review": ("minimax", "cerebras", "groq", "nvidia"),
    "code": ("nvidia", "groq", "cerebras", "minimax"),
}


def _hint_score(model: Model, job: str) -> int:
    blob = f"{model.model_id} {model.label}".lower()
    score = sum(1 for tok in _JOB_HINTS.get(job, ()) if tok in blob)
    if model.provider in _JOB_PROVIDERS.get(job, ()):
        score += 2
    return score


def _sort_key(model: Model, job: str) -> tuple:
    blob = f"{model.model_id} {model.label}".lower()
    newer = 0 if any(
        tok in blob for tok in (
            "minimax-m3", "kimi-k3", "k3", "v4", "glm-5.2", "glm-5p2", "glm-5",
        )
    ) else 1
    giant = 0
    if job == "dict" and any(tok in blob for tok in ("ultra", "550b", "235b")):
        giant = 1
    tier = TIER_ORDER.get(model.tier, 99)
    return (
        giant,
        -_hint_score(model, job),
        newer,
        tier,
        0 if model.is_free else 1,
        model.provider,
        model.label.lower(),
    )


def recommend_models(
    job: str = "code",
    count: int = 6,
    include_subscriptions: bool = False,
    free_only: bool = False,
    include_paid: bool = False,
) -> list[Model]:
    """Pick up to `count` chat models, at most one per provider."""
    if job not in JOBS:
        job = "code"
    count = max(1, min(int(count), 12))
    cfg = load_config()
    configured = set(get_configured_providers(cfg))
    models = get_models_for_discovery()
    pool: list[Model] = []
    for m in models:
        if m.provider not in configured:
            continue
        if not is_chat_model(m.model_id) or is_cloud_route(m.model_id):
            continue
        if not model_in_scope(
            m.provider, m.model_id, cfg,
            free_only=free_only,
            include_subscriptions=include_subscriptions,
            include_paid=include_paid,
        ):
            continue
        pool.append(m)
    pool.sort(key=lambda m: _sort_key(m, job))
    seen: set[str] = set()
    picked: list[Model] = []
    for m in pool:
        if m.provider in seen:
            continue
        seen.add(m.provider)
        picked.append(m)
        if len(picked) >= count:
            break
    return picked


def recommend_payload(
    job: str = "code",
    count: int = 6,
    include_subscriptions: bool = False,
    free_only: bool = False,
    include_paid: bool = False,
) -> dict:
    models = recommend_models(
        job=job,
        count=count,
        include_subscriptions=include_subscriptions,
        free_only=free_only,
        include_paid=include_paid,
    )
    return {
        "job": job if job in JOBS else "code",
        "count": len(models),
        "include_subscriptions": include_subscriptions,
        "include_paid": include_paid,
        "models": [model_card(m) for m in models],
        "how_to_run": (
            "ask(prompt, model_ids=[m['ref'] for m in models]) "
            "or quality_probe(job=…, model_ids=[…])"
        ),
    }
