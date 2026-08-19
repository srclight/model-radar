# Playbook: Local MCP ops

How to run, restart, and compare models on a machine that already has `model-radar.service`.

## The live process

On this host the MCP that agents talk to is the **systemd user unit**, not a stray `nohup`:

```
~/.config/systemd/user/model-radar.service
ExecStart=…/.venv/bin/model-radar serve --transport sse --port 8743
```

It binds `127.0.0.1:8743` (`/mcp` Streamable HTTP, `/sse` legacy). `Restart=always`.

**Always restart the unit after code or catalog-path changes.** A stale process is how `ask(model_ids=…)` silently runs yesterday’s code. Restarting a *Grok/Cursor chat* does **not** reload the server — the client just reconnects to the same PID.

After **commit + push**, always bounce the unit. Ask the human to exit the Grok/Cursor session **only when the tool list changed** (new MCP commands). Behavior-only changes load on the next tool call.

1. **Unit** (new Python): `./scripts/restart-mcp.sh` — always
2. **Agent session** (new tool *list*): quit/reopen Grok or Cursor — only if `/healthz` shows new command names

```sh
# After git pull / merge on develop:
git -C ~/repos/srclight/model-radar pull
# editable venv — no pip install needed unless deps changed
./scripts/restart-mcp.sh
# script prints old/new pid, package version, and GET /healthz
# (has_still_free, tool names). Exit this Grok session only if tools were added.
```

```sh
# Equivalent
systemctl --user restart model-radar.service
curl -sS http://127.0.0.1:8743/healthz
```

Do **not** `kill` + `nohup` a second copy. The unit will respawn and you will fight bind errors (`address already in use`) and half-started refresh tasks.

`restart_server()` from MCP is fine when the unit is the process manager (it exits 0, systemd starts a new one). The *client* still needs a new session to see new tools.

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
still_free(speed="fast")                   # Lane A set, 3 chats/host (Ollama: one 9B)
recommend(job="dict")                      # Paper B lineup; then pin still_free-up ids
recommend(job="review", include_subscriptions=True)
quality_probe(job="dict", count=3)         # five headwords (China/Taiwan + COVID)
quality_probe(job="rewrite", model_ids=["groq/openai/gpt-oss-120b"])
judge(..., exclude_providers=["minimax"])  # pin 120B-class; skip <27B
```

Jobs: `translate` (EN→ZH), `rewrite` (lemma-study sentence), `review` (bare `return` bug), `dict` (Paper B five headwords). CLI: `model-radar still-free --speed fast` and `model-radar probe -j dict -n 3`.

## Pinning models (do not auto-spend subscriptions)

`get_fastest()` / default `ask()` never pick CLI providers. Pin them:

```
ask(prompt="…", providers=["grok", "gemini", "codex"])
ask(prompt="…", model_ids=["minimax/MiniMax-M3", "cerebras/gpt-oss-120b", "grok-4.6"])
```

Use `provider/id` when the same slug exists on more than one host.

## Compare / translation timing notes

- **Ollama is one GPU.** `still_free` pings **one** ~9B id (`qwen3.5:9b`) with a **90s** timeout. Do not fan out locals. Cold load after a 27B can take ~70s; a warm 9B is ~14s. Runner completions stay at 300s.
- **Remotes are parallel.** Subscription CLIs (Grok / `agy` / Codex) and Cerebras/MiniMax finish in seconds; local 3B–20B can take 1–5 minutes each.
- **`still_free(speed="fast")`** — small/flash/lite first. `speed="quality"` is tier. Google OpenAI-compat is **Bearer** (not `?key=`); 2.5-flash 404s for new users, 3.6-flash works.
- **Reasoning models** (Qwen3.5, GLM-4.7, Cerebras `zai-glm-4.7`, MiniMax M3) spend the budget inside `<think>` or `message.reasoning`. Use `max_tokens` ≥ 512 for a one-line translation. Runner strips `<think>` and will use `reasoning` when `content` is empty.
- **Stale ids 404.** If Cerebras/NVIDIA/OpenRouter reject a name, refresh first — do not retry the corpse.

## After pull / edit

```sh
.venv/bin/python -m pytest -q
./scripts/restart-mcp.sh
```
