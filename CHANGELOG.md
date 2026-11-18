# Changelog

## 0.14.0 — 2026-11-18

- **Vercel AI Gateway** provider (`AI_GATEWAY_API_KEY`). The live catalog keeps only `type=language` models, `credits` reports the prepaid USD balance, and `setup_guide` covers signup. Requests return 403 `customer_verification_required` until a card is on file.
- **`evaluate(state, questions, model_id?)`** returns typed judgments from TypeSafe Jev (`typesafe-ai/jev`) through the gateway: P(yes) for boolean questions, a choice with probabilities, or a score on ordered levels.
- CLI providers: when `agy` in plan mode denies a tool call and returns no text, the error now names the denied actions instead of reporting "No recognizable response field". A non-SUCCESS status with no text also raises.
- CLI completion timeout default raised from 120 s to 300 s, overridable with `MODEL_RADAR_CLI_TIMEOUT`.
- Gemini seed models updated to `gemini-3.8-flash-high` and `gemini-3.8-flash-medium`.
- `__version__` now matches `pyproject.toml` (it had stayed at 0.12.0 through 0.12.1 to 0.13.0).
- Tests: the db sync tests accept a live-only provider with an empty seed (Ollama).

## 0.13.0 — 2026-08-31

- Migrated from the vendored v1 StrictArgsMCP (FastMCP) to **ironmcp** on mcp v2 (`strict_server`/`MCPServer`). All 27 tools verified working over a live session; `test_conformance.py` asserts advertise==runtime across the whole surface. Transport (streamable-http + sse + /healthz + web dashboard) migrated; `stateless_http` moved to the transport layer.


