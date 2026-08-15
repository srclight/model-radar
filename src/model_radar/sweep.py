"""Lane A sweep: a small live set per in-default-pool host."""

from __future__ import annotations

import asyncio
import re

import httpx

from .config import in_default_pool, load_config
from .cooldown import COOLDOWNS
from .cost import is_chat_model, is_cloud_route, param_billions
from .db import get_models_for_discovery
from .lanes import lane_for, provider_lane
from .providers import PROVIDERS, TIER_ORDER, Model
from .scanner import _ping_one

# How many chat models to show per host. The 3 ids on a host are pinged together.
# Ollama is one GPU — one id, or we fight ourselves on load.
MODELS_PER_HOST = 3
OLLAMA_MODELS_PER_HOST = 1
SPEEDS = ("quality", "fast")
# Do not use bare "mini" — it matches "gemini".
_FAST_HINTS = ("flash", "lite", "nano", "micro")
_MINI_RE = re.compile(r"(?:^|[-_/:])mini(?:$|[-_/:.\d])")
_SLOW_HINTS = ("thinking", "reason", "qwq", "r1-", "-r1")
# Local GPU: 9B-class is the still_free probe. 27B flash needs a cold load.
_OLLAMA_SWEET_B = 9.0


def _is_openrouter_free(model_id: str) -> bool:
    mid = (model_id or "").lower()
    return ":free" in mid or "-free" in mid


def _speed_key(model: Model) -> tuple:
    mid = (model.model_id or "").lower()
    bump = 0
    if any(tok in mid for tok in _FAST_HINTS) or _MINI_RE.search(mid):
        bump -= 8
    if any(tok in mid for tok in _SLOW_HINTS):
        bump += 20
    size = param_billions(model.model_id)
    return (bump, size if size is not None else 40.0, TIER_ORDER.get(model.tier, 99), mid)


def _ollama_key(model: Model) -> tuple:
    size = param_billions(model.model_id)
    if size is None:
        size = 40.0
    return (abs(size - _OLLAMA_SWEET_B), (model.model_id or "").lower())


def _probe_candidates(
    provider: str,
    models: list[Model],
    *,
    speed: str = "quality",
) -> list[Model]:
    """Chat models for this host. Embeddings never qualify."""
    mine = [m for m in models if m.provider == provider]
    chats = [m for m in mine if is_chat_model(m.model_id) and not is_cloud_route(m.model_id)]
    if provider == "openrouter":
        chats = [
            m for m in chats
            if _is_openrouter_free(m.model_id) and lane_for(provider, m.model_id) == "A"
        ]
    if provider == "ollama":
        chats.sort(key=_ollama_key)
    elif speed == "fast":
        chats.sort(key=_speed_key)
    else:
        chats.sort(key=lambda m: (TIER_ORDER.get(m.tier, 99), (m.model_id or "").lower()))
    return chats


def _n_for_host(provider: str) -> int:
    return OLLAMA_MODELS_PER_HOST if provider == "ollama" else MODELS_PER_HOST


def _pick_probe_model(
    provider: str,
    models: list[Model],
    *,
    speed: str = "quality",
) -> Model | None:
    cands = _probe_candidates(provider, models, speed=speed)
    return cands[0] if cands else None


def _model_row(model: Model, result) -> dict:
    row = {
        "model_id": model.model_id,
        "status": result.status,
        "latency_ms": result.latency_ms,
    }
    if result.error_detail:
        row["reason"] = result.error_detail
        if result.error_detail.startswith("HTTP "):
            try:
                row["http"] = int(result.error_detail.split()[1])
            except (IndexError, ValueError):
                pass
    return row


def _host_status(model_rows: list[dict]) -> str:
    statuses = [r["status"] for r in model_rows]
    if "up" in statuses:
        return "up"
    if "overloaded" in statuses:
        return "overloaded"
    return statuses[0] if statuses else "skipped"


def _summarize_host(key: str, model_rows: list[dict]) -> dict:
    status = _host_status(model_rows)
    first_up = next((r for r in model_rows if r["status"] == "up"), None)
    primary = first_up or (model_rows[0] if model_rows else {})
    row = {
        "provider": key,
        "lane": provider_lane(key),
        "status": status,
        "model_id": primary.get("model_id"),
        "models": model_rows,
    }
    if first_up and first_up.get("latency_ms") is not None:
        row["latency_ms"] = first_up["latency_ms"]
    elif primary.get("latency_ms") is not None:
        row["latency_ms"] = primary["latency_ms"]
    if status != "up":
        if primary.get("reason"):
            row["reason"] = primary["reason"]
        if "http" in primary:
            row["http"] = primary["http"]
    if status == "overloaded" and COOLDOWNS.is_cooled(key):
        row["cooled_s"] = round(COOLDOWNS.remaining(key), 1)
    return row


async def still_free(*, ping: bool = True, speed: str = "quality") -> dict:
    """A small live set per Lane A / mixed host in the default pool.

    speed=quality ranks by tier (S+ first). speed=fast ranks by size /
    flash-lite hints so a 20B answers before a 120B times out.

    Pings up to MODELS_PER_HOST (3) chat models per host in parallel.
    Cooled hosts are reported, not pinged. OpenRouter only pings :free
    ids. Does not touch Lane B/C.
    """
    if speed not in SPEEDS:
        speed = "quality"
    cfg = load_config()
    catalog = get_models_for_discovery()
    hosts: list[dict] = []
    completion_calls = 0
    skipped = 0

    candidates = []
    for key, prov in PROVIDERS.items():
        if getattr(prov, "kind", "https") == "cli":
            continue
        lane = provider_lane(key)
        if lane not in ("A", "mixed"):
            continue
        if not in_default_pool(cfg, key):
            continue
        candidates.append(key)

    ping_jobs: list[tuple[str, list[Model]]] = []
    for key in candidates:
        row: dict = {"provider": key, "lane": provider_lane(key)}
        if COOLDOWNS.is_cooled(key):
            row["status"] = "cooled"
            row["reason"] = COOLDOWNS.reason(key)
            row["retry_s"] = round(COOLDOWNS.remaining(key), 1)
            hosts.append(row)
            skipped += 1
            continue
        cands = _probe_candidates(key, catalog, speed=speed)
        if key == "openrouter" and not cands:
            row["status"] = "skipped"
            row["reason"] = "no :free model in catalog"
            hosts.append(row)
            skipped += 1
            continue
        if not cands:
            row["status"] = "skipped"
            row["reason"] = "no chat model in catalog"
            hosts.append(row)
            skipped += 1
            continue
        if not ping:
            picked = cands[:_n_for_host(key)]
            row["status"] = "listed"
            row["model_id"] = picked[0].model_id
            row["model_ids"] = [m.model_id for m in picked]
            hosts.append(row)
            continue
        ping_jobs.append((key, cands[:_n_for_host(key)]))

    if ping and ping_jobs:
        async with httpx.AsyncClient() as client:
            async def _ping_host(key: str, picked: list[Model]):
                results = await asyncio.gather(
                    *[_ping_one(client, cand, cfg) for cand in picked]
                )
                rows = [_model_row(cand, result) for cand, result in zip(picked, results)]
                return _summarize_host(key, rows)

            host_rows = await asyncio.gather(
                *[_ping_host(key, picked) for key, picked in ping_jobs]
            )
            completion_calls = sum(len(job[1]) for job in ping_jobs)
            hosts.extend(host_rows)

    return {
        "speed": speed,
        "completion_calls": completion_calls,
        "skipped": skipped,
        "hosts": hosts,
    }
