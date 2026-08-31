# Estate migration playbook: FastMCP (v1) → ironmcp (mcp v2)

Verified on model-radar (Task 0 spike, 2026-08-31, mcp 2.1.1 + ironmcp 0.3.0). Reuse for
zhcorpus → conductor → srclight → caneslight (last, live lattice).

## The deltas (this is the whole migration for a str-tool server)

| v1 (FastMCP / vendored StrictArgsMCP) | v2 (ironmcp) |
|---|---|
| `from ._mcpkit import StrictArgsMCP` | `from ironmcp import strict_server` (+ `pip install ironmcp`) |
| `mcp = StrictArgsMCP("name", instructions=…, stateless_http=True)` | `app = strict_server(name="name", instructions=…, version=…)` — **drop `stateless_http` from the constructor** |
| `stateless_http=True` on the server | moves to the HTTP transport: `app.streamable_http_app(stateless_http=True)`, or pass via `run(transport="streamable-http", stateless_http=True)` |
| `@mcp.tool()` | `@app.tool()` — unchanged; **`-> str` returns work as-is** |
| `mcp.custom_route("/healthz", ["GET"])(fn)` | `app.custom_route("/healthz", ["GET"])(fn)` — **identical signature** |
| `mcp._tool_manager.list_tools()` (health helper) | `app._tool_manager.list_tools()` — same internal API |
| `server.run(transport="stdio"|"sse")` | `app.run(transport="stdio")` works; prefer `"streamable-http"` for HTTP (sse is legacy) |
| vendored `src/<pkg>/_mcpkit.py` | delete it |
| floor `mcp>=1.x,<2` | `mcp>=2,<3` + `ironmcp` dependency |

## Verified facts
- Tool return types: model-radar's 27 tools all return `-> str` → MCPServer wraps them cleanly. No adaptation.
- No `Context`/DI injection in any tool body (grepped). If a server DOES inject Context, record its v2 form before converting.
- `advertisement == runtime` holds through a live session (schema stamped `additionalProperties:false`, unknown arg refused).

## Gotchas to watch per server
- Anything reading `mcp.` internals (like a health helper) — repoint to `app` / `app._tool_manager`.
- If a server injects `Context` or returns non-str (dict/pydantic), spike that ONE tool first (this playbook only proves the str path).
- Statelessness + HTTP: confirm the transport call passes `stateless_http` where the server needs it.
