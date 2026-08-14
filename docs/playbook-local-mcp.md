# Playbook: Local MCP ops

How to run, restart, and compare models on a machine that already has `model-radar.service`.

## The live process

On this host the MCP that agents talk to is the **systemd user unit**, not a stray `nohup`:

```
~/.config/systemd/user/model-radar.service
ExecStart=…/.venv/bin/model-radar serve --transport sse --port 8743
```

It binds `127.0.0.1:8743` (`/mcp` Streamable HTTP, `/sse` legacy). `Restart=always`.

**Always restart the unit after code or catalog-path changes.** A stale process is how `ask(model_ids=…)` silently runs yesterday’s code.

```sh
# Preferred
./scripts/restart-mcp.sh

# Equivalent
systemctl --user restart model-radar.service
# wait until 127.0.0.1:8743 accepts connections, then:
#   list_providers() or server_stats()
```

Do **not** `kill` + `nohup` a second copy. The unit will respawn and you will fight bind errors (`address already in use`) and half-started refresh tasks.

`restart_server()` from MCP is fine when the unit is the process manager (it exits 0, systemd starts a new one).

## Keys

Stored in `~/.model-radar/config.json` (mode 600). Env vars override.

```sh
model-radar configure minimax "$MINIMAX_API_KEY"
# or MCP: configure_key(provider="minimax", api_key="…")
python scripts/catalog-report.py   # shows which keys are empty, never prints them
```

Do not put a MiniMax token in `ANTHROPIC_AUTH_TOKEN` globally — that hijacks Claude Code. MiniMax’s Anthropic shim (`https://api.minimax.io/anthropic`) is for a dedicated Claude Code profile only. model-radar uses `https://api.minimax.io/v1` with `MINIMAX_API_KEY`.

## Recommend + probe (agent loop)

```
recommend(job="translate")                 # 6 live chat models, no CLI
recommend(job="review", include_subscriptions=True)
quality_probe(job="translate", count=3)    # time + CJK check
quality_probe(job="rewrite", model_ids=["minimax/MiniMax-M3"])
quality_probe(job="review", providers=["minimax","cerebras"])
```

Jobs: `translate` (EN→ZH), `rewrite` (lemma-study sentence), `review` (bare `return` bug). CLI: `model-radar probe -j translate -n 3`.

## Pinning models (do not auto-spend subscriptions)

`get_fastest()` / default `ask()` never pick CLI providers. Pin them:

```
ask(prompt="…", providers=["grok", "gemini", "codex"])
ask(prompt="…", model_ids=["minimax/MiniMax-M3", "cerebras/gpt-oss-120b", "grok-4.6"])
```

Use `provider/id` when the same slug exists on more than one host.

## Compare / translation timing notes

- **Ollama is one GPU.** Run local models sequentially. Parallel Ollama + a 22B will time out (we use a 300s Ollama HTTP timeout and treat timeout as an error, not a cancelled gather).
- **Remotes are parallel.** Subscription CLIs (Grok / `agy` / Codex) and Cerebras/MiniMax finish in seconds; local 3B–20B can take 1–5 minutes each.
- **Reasoning models** (Qwen3.5, GLM-4.7, Cerebras `zai-glm-4.7`, MiniMax M3) spend the budget inside `<think>` or `message.reasoning`. Use `max_tokens` ≥ 512 for a one-line translation. Runner strips `<think>` and will use `reasoning` when `content` is empty.
- **Stale ids 404.** If Cerebras/NVIDIA/OpenRouter reject a name, refresh first — do not retry the corpse.

## After pull / edit

```sh
.venv/bin/python -m pytest -q
./scripts/restart-mcp.sh
```
