"""Lane classification and selection scope."""

from model_radar.lanes import lane_for, model_in_scope, provider_lane


def test_lane_a_hosts():
    assert lane_for("nvidia") == "A"
    assert lane_for("groq", "llama-3.3-70b-versatile") == "A"
    assert lane_for("googleai", "gemini-2.5-flash") == "A"
    assert lane_for("ollama", "hy-mt-1.8b:latest") == "A"
    assert lane_for("codestral", "codestral-latest") == "A"
    assert lane_for("sealion") == "A"


def test_lane_b_subscriptions():
    assert lane_for("grok", "grok-4.6") == "B"
    assert lane_for("claude", "sonnet") == "B"
    assert lane_for("gemini", "gemini-3.1-pro") == "B"
    assert lane_for("codex", "gpt-5.6-terra") == "B"


def test_lane_c_money_hosts():
    assert lane_for("cerebras", "gpt-oss-120b") == "C"
    assert lane_for("minimax", "MiniMax-M3") == "C"
    assert lane_for("sambanova") == "C"
    assert lane_for("together") == "C"
    assert lane_for("hyperbolic") == "C"
    assert lane_for("xai") == "C"


def test_openrouter_free_vs_paid():
    assert lane_for("openrouter", "google/gemma-4-31b-it:free") == "A"
    assert lane_for("openrouter", "anthropic/claude-sonnet-4") == "C"
    assert provider_lane("openrouter") == "mixed"


def test_cloudflare_frontier_is_lane_c():
    assert lane_for("cloudflare", "@cf/meta/llama-3.3-70b-instruct-fp8-fast") == "A"
    assert lane_for("cloudflare", "@cf/moonshotai/kimi-k2.6") == "C"
    assert lane_for("cloudflare", "@cf/zai-org/glm-5.2") == "C"


def test_scope_lane_a_always_in():
    cfg = {"providers": {}}
    assert model_in_scope("nvidia", "openai/gpt-oss-120b", cfg) is True
    assert model_in_scope("nvidia", "openai/gpt-oss-120b", cfg, free_only=True) is True


def test_scope_lane_b_opt_in():
    cfg = {"providers": {}}
    assert model_in_scope("grok", "grok-4.6", cfg) is False
    assert model_in_scope("grok", "grok-4.6", cfg, include_subscriptions=True) is True
    assert model_in_scope(
        "grok", "grok-4.6", cfg, include_subscriptions=True, free_only=True,
    ) is False


def test_scope_lane_c_needs_funded_and_opt_in():
    cfg = {"providers": {"cerebras": {"spend_ok": False, "funded": True}}}
    assert model_in_scope("cerebras", "gpt-oss-120b", cfg) is False
    assert model_in_scope("cerebras", "gpt-oss-120b", cfg, include_paid=True) is True
    assert model_in_scope("cerebras", "gpt-oss-120b", cfg, free_only=True) is False

    cfg["providers"]["cerebras"]["spend_ok"] = True
    assert model_in_scope("cerebras", "gpt-oss-120b", cfg) is True


def test_scope_lane_c_unfunded_never():
    cfg = {"providers": {"together": {"spend_ok": False, "funded": False}}}
    assert model_in_scope("together", "openai/gpt-oss-120b", cfg, include_paid=True) is False

    cfg = {"providers": {}}  # funded unknown
    assert model_in_scope("minimax", "MiniMax-M3", cfg, include_paid=True) is False
