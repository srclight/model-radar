# model-radar → ironmcp Migration Plan (estate template)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Migrate model-radar from the vendored v1 `StrictArgsMCP` (FastMCP, `mcp<2`) to **`ironmcp` on `mcp>=2`** (`strict_server` / `MCPServer`), keeping all 27 tools and both transports working, and adding a conformance test. This is the **template** proven here first, then rolled to zhcorpus → conductor → srclight → (caneslight LAST, it runs the live lattice).

**Architecture:** `StrictArgsMCP("model-radar", …)` becomes `strict_server(name="model-radar", …)`; `@mcp.tool()` becomes `@app.tool()`; the vendored `src/model_radar/_mcpkit.py` is deleted (replaced by `pip install ironmcp`). Tool *bodies* don't change — the risk is v1→v2 SDK semantics (tool return types, any `Context` injection, `stateless_http`, transport `run`).

**Current state (surveyed 2026-08-31):** `src/model_radar/server.py:162` `mcp = StrictArgsMCP("model-radar", instructions=MCP_INSTRUCTIONS, stateless_http=True)`; 27 `@mcp.tool()`; `src/model_radar/cli.py:55` `server.run(transport=transport)` (stdio | sse, port 8743). Floor `mcp>=1.26,<2`.

## Global Constraints

- **v2-only**, floor `mcp>=2,<3`, add `ironmcp` as a dependency. Delete the vendored `_mcpkit.py`.
- **All 27 tools must still work** — advertise==runtime, and each returns what it did before. The Task 5 smoke + the existing test suite are the gate.
- Keep model-radar's own `reconnect_hint` behaviour if it set one (it uses the generic default today — pass `reconnect_hint="check provider_status and reconnect"` or similar, its revision surface).
- No Claude attribution; create commits, don't amend; never `git add -A`. Work on a `feature/ironmcp` branch (git-flow).

---

### Task 0: SPIKE — verify the v1→v2 tool/transport deltas (do FIRST)

Convert ONE tool and run it before touching the other 26. Record deltas in `docs/ironmcp-migration-notes.md`.

- [ ] **Step 1** Fresh venv on `mcp>=2` + `ironmcp`; `python -c "from ironmcp import strict_server; from mcp.server.mcpserver import MCPServer; print('ok')"`.
- [ ] **Step 2** Confirm the tool decorator + registration: does `@app.tool()` accept the same signature style model-radar uses (typed args, defaults, docstrings as descriptions)? Register one real tool (e.g. `still_free`) on a `strict_server` and list it through a session (reuse ironmcp's harness pattern). Confirm its `input_schema` + that a good call returns the same shape.
- [ ] **Step 3** Confirm **return-type handling**: model-radar tools return dicts/strings/pydantic — does MCPServer serialize them as FastMCP did? Note any tool that returned a bare dict/list and how v2 wraps it. **If any return type needs adapting, record the rule here before converting the rest.**
- [ ] **Step 4** Confirm **`stateless_http`** and **transport**: is there an `MCPServer` equivalent of `stateless_http=True`? (Check the `MCPServer.__init__` params + `streamable_http_app`/`run`.) Confirm `app.run(transport="stdio")` and `"sse"` both start. Record the exact replacement for `server.run(transport=…)`.
- [ ] **Step 5** Confirm **`Context`/DI**: grep the 27 tools for a `Context` parameter or `mcp.`-attribute use inside bodies; if any inject context, record the v2 equivalent.
- [ ] **Step 6** Commit `docs/ironmcp-migration-notes.md`. **If Step 3/4/5 reveal a blocking incompatibility, STOP and resolve the pattern before the mechanical conversion.**

---

### Task 1: pyproject + dependency

- [ ] **Step 1** `mcp>=1.26.0,<2` → `mcp>=2,<3`; add `ironmcp` to dependencies; drop any `mcpkit` reference.
- [ ] **Step 2** `pip install -e .` in the v2 venv — resolves clean.
- [ ] **Step 3** Commit.

---

### Task 2: convert `server.py`

- [ ] **Step 1** Replace `from ._mcpkit import StrictArgsMCP` → `from ironmcp import strict_server`.
- [ ] **Step 2** Replace the constructor: `mcp = StrictArgsMCP("model-radar", instructions=MCP_INSTRUCTIONS, stateless_http=True)` → `app = strict_server(name="model-radar", instructions=MCP_INSTRUCTIONS, reconnect_hint=<model-radar's revision hint>, **<stateless_http replacement from Task 0>)`. Keep the variable name `mcp` if less churn (alias), or rename to `app` consistently.
- [ ] **Step 3** `@mcp.tool()` → `@app.tool()` for all 27 (sed, then eyeball). Apply any return-type/Context adaptations Task 0 recorded.
- [ ] **Step 4** `git rm src/model_radar/_mcpkit.py`.
- [ ] **Step 5** `python -c "import model_radar.server"` imports clean; commit.

---

### Task 3: transport / cli

- [ ] **Step 1** Update `cli.py` `server.run(transport=transport)` per Task 0's recorded run API (likely unchanged: `app.run(transport=transport)`).
- [ ] **Step 2** Start both: `model-radar serve --transport stdio` (Ctrl-C after banner) and `--transport sse --port 8743` — both come up. Commit.

---

### Task 4: conformance test

- [ ] **Step 1** Add `tests/test_conformance.py`: build the model-radar `app`, `await aassert_enforces_v2(app)` passes (every one of the 27 tools: advertise==runtime). Import the app without starting a transport.
- [ ] **Step 2** Run it; commit.

---

### Task 5: verify ALL 27 tools work (the real gate)

- [ ] **Step 1** Run model-radar's existing test suite on the v2 venv — green.
- [ ] **Step 2** Live smoke over a session (ironmcp harness or `mcp` client): call ~3 representative tools (`still_free`, `get_fastest`, `list_models`) — correct results; and one with a typo'd arg — **refused** (proves ironmcp is live).
- [ ] **Step 3** Confirm the MCP port registry entry still holds (8743) and `provider_status`/revision surface reports correctly.

---

### Task 6: release (git-flow)

- [ ] **Step 1** Full suite green; version bump (minor); CHANGELOG note "migrated to ironmcp (mcp v2)".
- [ ] **Step 2** Merge `feature/ironmcp` → develop → master, tag; push. **Do NOT publish to PyPI unless model-radar is a published package** (confirm; it publishes via OIDC — a release tag may trigger it, so gate on Tim).
- [ ] **Step 3** Land a caneslight grain: model-radar migrated, deltas recorded in `docs/ironmcp-migration-notes.md` (the estate template), remaining servers queued (zhcorpus → conductor → srclight → caneslight last).

## Self-Review

- The one real risk is **v1→v2 tool semantics** (return types, Context, `stateless_http`) — Task 0 fences it by converting one tool and recording deltas before the mechanical 27-tool sweep.
- The migration notes (`docs/ironmcp-migration-notes.md`) become the **reusable estate playbook**; each subsequent server is faster.
- `caneslight` is deliberately last (live lattice) — migrate it only once the pattern is boring.
