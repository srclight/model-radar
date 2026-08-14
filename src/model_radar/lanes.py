"""Spend lanes: A never invoices, B is a monthly CLI, C can charge.

See Vault/Areas/Srclight/Model Radar/2026-08-14-provider-cost-lanes.md
"""

from __future__ import annotations

# Hosted APIs whose default call does not invoice (rate limits / $0 token).
LANE_A_PROVIDERS = frozenset({
    "nvidia", "groq", "googleai", "cloudflare", "sealion",
    "ollama", "codestral",
})

# Cloudflare frontier ids that need Workers Paid or prepaid credits.
_CLOUDFLARE_PAID_MARKERS = (
    "kimi-k2.6", "kimi-k2.7", "glm-5.2",
)


def provider_lane(provider_key: str) -> str:
    """Provider-level lane. OpenRouter is mixed (per-model)."""
    from .cli_provider import CLI_SPEC_BY_KEY

    if provider_key in CLI_SPEC_BY_KEY:
        return "B"
    if provider_key == "openrouter":
        return "mixed"
    if provider_key in LANE_A_PROVIDERS:
        return "A"
    return "C"


def lane_for(provider_key: str, model_id: str = "") -> str:
    """Lane for a specific model. OpenRouter :free and Cloudflare non-frontier stay A."""
    from .cli_provider import CLI_SPEC_BY_KEY

    if provider_key in CLI_SPEC_BY_KEY:
        return "B"
    mid = (model_id or "").lower()
    if provider_key == "openrouter":
        if ":free" in mid or "-free" in mid:
            return "A"
        return "C" if mid else "A"
    if provider_key == "cloudflare" and mid:
        if any(tok in mid for tok in _CLOUDFLARE_PAID_MARKERS):
            return "C"
        return "A"
    if provider_key in LANE_A_PROVIDERS:
        return "A"
    return "C"


def _flags(cfg: dict | None, provider_key: str) -> dict:
    raw = (cfg or {}).get("providers", {}).get(provider_key) or {}
    funded = raw.get("funded", None)
    if funded is not None:
        funded = bool(funded)
    return {
        "enabled": raw.get("enabled", True) is not False,
        "spend_ok": bool(raw.get("spend_ok", False)),
        "funded": funded,
    }


def model_in_scope(
    provider_key: str,
    model_id: str,
    cfg: dict | None,
    *,
    free_only: bool = False,
    include_subscriptions: bool = False,
    include_paid: bool = False,
) -> bool:
    """True if this model may be auto-selected under the given policy."""
    flags = _flags(cfg, provider_key)
    if not flags["enabled"]:
        return False
    lane = lane_for(provider_key, model_id)
    if lane == "A":
        return True
    if lane == "B":
        return include_subscriptions and not free_only
    if free_only:
        return False
    if flags["funded"] is not True:
        return False
    return include_paid or flags["spend_ok"]
