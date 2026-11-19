# Changelog

## 0.15.1 — 2026-11-18

- **Fixed:** outbound requests sent a `User-Agent` with a stale version (0.5 to 0.13, depending on the call). Every request now sends the installed package version.
- **Fixed:** the MCP handshake reported an empty server version. `serverInfo.version` now carries the package version.
- Docs: the README opening describes what the server does today (free and paid providers, run, compare, judge).

## 0.15.0 — 2026-11-18

- **`MODEL_RADAR_CONFIG`** names the config file to use in place of `~/.model-radar/config.json`, so keys can live on an encrypted or removable volume. Only that file is read and written. If it is missing, model-radar loads no keys from disk and reports the problem; it never falls back to the home directory and never creates the path.
- **Changed:** a `config.json` in the working directory is no longer read. It let whatever directory the server started in supply the keys. To keep the old behaviour, set `MODEL_RADAR_CONFIG=./config.json`.
- **Changed:** a failed save is now an error. `configure_key`, `set_profile` and the CLI used to report success when the file could not be written. A config file that does not parse is never overwritten.
- The config file is created with mode 0o600 from the start, where it was previously written and then restricted.
- `list_providers()` returns a `config` block (path, source, ok, error) and `/healthz` returns `config_ok`. Neither contains key material.
- Tests no longer read the developer's real config file.
- Docs: removed machine-specific paths from the design notes under `docs/superpowers/`.
- Docs: the README gains a Keys and security section, an environment variable table, and the five tools it had not listed (`profile`, `set_profile`, `credits`, `setup_workflow`, `host_swap_instructions`). The architecture doc covers every module and the config rules. The argument-validation notes now describe `ironmcp`, which replaced the vendored guard in 0.13.0.
- `still_free` is listed in the server's tool guide. `server.json` carries a current description.

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


