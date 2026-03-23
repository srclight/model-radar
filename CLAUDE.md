# CLAUDE.md -- Model Radar

## What Is This

MCP server that pings 219+ free coding LLM models across 21 providers, ranks by real-time latency, and helps AI agents pick the fastest model. Python 3.11+, built on FastMCP + httpx + click.

## Commands

```sh
pip install -e .                                    # dev install
pip install -e ".[dev]"                             # with test/lint deps
python -m pytest tests/ -v                          # run tests (167 tests)
ruff check src/ tests/                              # lint
model-radar serve                                   # MCP server (stdio)
model-radar serve --transport sse --port 8765       # SSE + Streamable HTTP
model-radar serve --transport sse --port 8765 --web # SSE + web dashboard
model-radar scan --min-tier S --limit 5             # CLI scan
model-radar providers                               # list providers
```

## Key Modules

| Module | Purpose |
|--------|---------|
| `server.py` | FastMCP server, all 19 MCP tool definitions |
| `providers.py` | Provider/model catalog, tier system (S+ through C) |
| `scanner.py` | Async ping engine, parallel scanning, adaptive rate limiting |
| `runner.py` | Prompt execution, automatic fallback, batch execution |
| `judge.py` | LLM-as-judge: rate, compare, batch evaluate |
| `config.py` | Config management (~/.model-radar/config.json) |
| `db.py` | SQLite persistence for model catalog and ping results |

Full architecture: `docs/architecture.md`

## MCP Tools (19 total)

**Read-only (no side effects):**
list_providers, list_models, scan, get_fastest, get_workers, provider_status, server_stats

**Execution (runs prompts on external LLMs):**
run, ask, batch_run, judge, compare, batch_judge, backtranslate_eval, benchmark

**Write (modifies local config/state):**
configure_key, refresh_models, setup_workflow, restart_server

**Informational (returns text guidance):**
setup_guide, host_swap_instructions

## Version Bumps

Update BOTH files together:
- `pyproject.toml` -> `version = "X.Y.Z"`
- `src/model_radar/__init__.py` -> `__version__ = "X.Y.Z"`

## Release Process

```sh
# All work on develop or feature branches
git checkout develop && git checkout -b feature/xxx
# ... work, commit ...
git checkout develop && git merge --no-ff feature/xxx

# Release: develop -> master, tag
git checkout master && git merge develop --no-ff -m "release: vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z description"
git checkout develop
git push origin master develop --tags
```

Publishing is automated: GitHub Actions runs on `release: [published]` to push to PyPI (OIDC) and MCP Registry.

## Do

- Keep the dependency footprint minimal (httpx + mcp + click)
- Use `docs/` for detailed playbooks; keep this file concise
- Test with `python -m pytest tests/ -v` before committing
- Use provider diversity in judge/worker selection

## Don't

- Commit API keys or config.json (keys live in ~/.model-radar/config.json with 0o600)
- Add heavy dependencies without discussion
- Remove provider definitions without checking if they're still active
- Skip the two-file version bump (pyproject.toml + __init__.py)
- Commit directly to master -- always work on develop or feature branches

## Docs

- `docs/architecture.md` -- module map, data flow, transport, rate limiting
- `docs/mcp-transport.md` -- transport options, stateless HTTP, client config
- `docs/playbook-translation-pipeline.md` -- batch translation patterns
- `docs/playbook-llm-as-judge.md` -- evaluation patterns and judge selection

## Skills

- `.claude/skills/release/` -- Version bump + PyPI publish + MCP registry workflow
- `.claude/skills/provider-setup/` -- Add a new provider end-to-end
- `.claude/skills/benchmarking/` -- Run quality benchmarks and interpret results
