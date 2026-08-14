"""Lane A sweep: one cheap ping per in-default-pool host."""

from __future__ import annotations

import httpx

from .config import in_default_pool, load_config
from .cooldown import COOLDOWNS
from .cost import is_chat_model
from .db import get_models_for_discovery
from .lanes import lane_for, provider_lane
from .providers import PROVIDERS, Model
from .scanner import _ping_one


def _is_openrouter_free(model_id: str) -> bool:
    mid = (model_id or "").lower()
    return ":free" in mid or "-free" in mid


def _pick_probe_model(provider: str, models: list[Model]) -> Model | None:
    mine = [m for m in models if m.provider == provider]
    chats = [m for m in mine if is_chat_model(m.model_id)] or mine
    if provider == "openrouter":
        free = [m for m in chats if _is_openrouter_free(m.model_id) and lane_for(provider, m.model_id) == "A"]
        return free[0] if free else None
    return chats[0] if chats else None


async def still_free(*, ping: bool = True) -> dict:
    """One cheap ping per Lane A / mixed host in the default pool.

    Does not fan out per model. Does not touch Lane B/C. OpenRouter only
    pings a :free id. Cooled hosts are reported, not pinged.
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

    ping_jobs: list[tuple[str, Model]] = []
    for key in candidates:
        row: dict = {"provider": key, "lane": provider_lane(key)}
        if COOLDOWNS.is_cooled(key):
            row["status"] = "cooled"
            row["reason"] = COOLDOWNS.reason(key)
            row["retry_s"] = round(COOLDOWNS.remaining(key), 1)
            hosts.append(row)
            skipped += 1
            continue
        model = _pick_probe_model(key, catalog)
        if key == "openrouter" and model is None:
            row["status"] = "skipped"
            row["reason"] = "no :free model in catalog"
            hosts.append(row)
            skipped += 1
            continue
        if model is None:
            row["status"] = "skipped"
            row["reason"] = "no chat model in catalog"
            hosts.append(row)
            skipped += 1
            continue
        if not ping:
            row["status"] = "listed"
            row["model_id"] = model.model_id
            hosts.append(row)
            continue
        ping_jobs.append((key, model))

    if ping and ping_jobs:
        async with httpx.AsyncClient() as client:
            for key, model in ping_jobs:
                result = await _ping_one(client, model, cfg)
                completion_calls += 1
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
                hosts.append(row)

    return {
        "completion_calls": completion_calls,
        "skipped": skipped,
        "hosts": hosts,
    }
