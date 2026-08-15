"""Lane A sweep: one cheap ping per in-default-pool host."""

from __future__ import annotations

import httpx

from .config import in_default_pool, load_config
from .cooldown import COOLDOWNS
from .cost import is_chat_model
from .db import get_models_for_discovery
from .lanes import lane_for, provider_lane
from .providers import PROVIDERS, TIER_ORDER, Model
from .scanner import _ping_one

# Bounded retries when the first catalog ids 404. 429/401/402 still stop.
MAX_PROBE_TRIES = 3


def _is_openrouter_free(model_id: str) -> bool:
    mid = (model_id or "").lower()
    return ":free" in mid or "-free" in mid


def _probe_candidates(provider: str, models: list[Model]) -> list[Model]:
    """Chat models for this host, better tier first. Embeddings never qualify."""
    mine = [m for m in models if m.provider == provider]
    chats = [m for m in mine if is_chat_model(m.model_id)]
    if provider == "openrouter":
        chats = [
            m for m in chats
            if _is_openrouter_free(m.model_id) and lane_for(provider, m.model_id) == "A"
        ]
    chats.sort(key=lambda m: (TIER_ORDER.get(m.tier, 99), (m.model_id or "").lower()))
    return chats


def _pick_probe_model(provider: str, models: list[Model]) -> Model | None:
    cands = _probe_candidates(provider, models)
    return cands[0] if cands else None


def _host_row(key: str, model: Model, result) -> dict:
    row = {
        "provider": key,
        "lane": provider_lane(key),
        "status": result.status,
        "model_id": model.model_id,
        "latency_ms": result.latency_ms,
    }
    if result.error_detail:
        row["reason"] = result.error_detail
        if result.error_detail.startswith("HTTP "):
            try:
                row["http"] = int(result.error_detail.split()[1])
            except (IndexError, ValueError):
                pass
    if result.status == "overloaded" and COOLDOWNS.is_cooled(key):
        row["cooled_s"] = round(COOLDOWNS.remaining(key), 1)
    return row


async def still_free(*, ping: bool = True) -> dict:
    """One cheap ping per Lane A / mixed host in the default pool.

    Picks a real chat model (better tier first). A 404 tries the next id,
    up to MAX_PROBE_TRIES. 401/402/429/529 still stop and cool. Does not
    touch Lane B/C. OpenRouter only pings a :free id. Cooled hosts are
    reported, not pinged.
    """
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
        cands = _probe_candidates(key, catalog)
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
            row["status"] = "listed"
            row["model_id"] = cands[0].model_id
            hosts.append(row)
            continue
        ping_jobs.append((key, cands))

    if ping and ping_jobs:
        async with httpx.AsyncClient() as client:
            for key, cands in ping_jobs:
                skipped_ids: list[str] = []
                result = None
                model = cands[0]
                for i, cand in enumerate(cands[:MAX_PROBE_TRIES]):
                    model = cand
                    result = await _ping_one(client, model, cfg)
                    completion_calls += 1
                    if result.status != "not_found":
                        break
                    if i + 1 < min(len(cands), MAX_PROBE_TRIES):
                        skipped_ids.append(cand.model_id)
                assert result is not None
                row = _host_row(key, model, result)
                if skipped_ids:
                    row["skipped_ids"] = skipped_ids
                hosts.append(row)

    return {
        "completion_calls": completion_calls,
        "skipped": skipped,
        "hosts": hosts,
    }
