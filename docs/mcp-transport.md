# MCP Transport Configuration

## Transport Options

Model Radar supports three MCP transports:

| Transport | Endpoint | Use Case |
|-----------|----------|----------|
| **Stdio** | N/A (stdin/stdout) | Default. Client starts and manages the server process. |
| **Streamable HTTP** | `/mcp` | Recommended for persistent servers. Stateless, restart-resilient. |
| **SSE** (legacy) | `/sse` + `/messages/` | Backward compatibility. Deprecated in MCP spec 2025-03-26. |

When running with `--transport sse`, the server serves **both** Streamable HTTP and SSE on the same port. Clients that support Streamable HTTP (e.g., Cursor) will use `/mcp` automatically.

## Stateless HTTP

Model Radar runs with `stateless_http=True`. This means:

- **No session tracking** — each request is independent
- **Restart-resilient** — server can restart without client errors
- **No reconnection needed** — clients don't need to re-establish sessions

This is the correct choice for model-radar because all tools are stateless request/response. There are no subscriptions, streaming state, or server-initiated notifications that would require sessions.

### The Problem Stateless Solves

Without `stateless_http=True`, FastMCP creates a server-side session per client. If the server restarts (code update, crash, `restart_server()` tool), those sessions are lost. Clients send their old session ID and get:

```
-32600: Session not found
```

The only fix is for the client to reconnect — which most MCP clients don't do automatically.

## Client Configuration

### Claude Code (`~/.claude/settings.json`)

```json
{
  "mcpServers": {
    "model-radar": {
      "command": "model-radar",
      "args": ["serve"]
    }
  }
}
```

### Cursor (`~/.cursor/mcp.json`)

Stdio (Cursor manages the process):
```json
{
  "mcpServers": {
    "model-radar": {
      "command": "model-radar",
      "args": ["serve"]
    }
  }
}
```

Streamable HTTP (persistent server):
```json
{
  "mcpServers": {
    "model-radar": {
      "url": "http://127.0.0.1:8743/mcp",
      "transportType": "streamable-http"
    }
  }
}
```

### OpenClaw (`~/.openclaw/config/mcporter.json`)

```json
{
  "mcpServers": {
    "model-radar": {
      "type": "http",
      "url": "http://127.0.0.1:8743/mcp"
    }
  }
}
```

## Running the Server

```sh
# Stdio (default — for Claude Code, Cursor stdio mode)
model-radar serve

# Streamable HTTP + SSE on port 8743
model-radar serve --transport sse --port 8743

# With web dashboard
model-radar serve --transport sse --port 8743 --web

# Auto-restart wrapper (for production)
while true; do model-radar serve --transport sse --port 8743; sleep 1; done
```

## Port Conventions

| Server | Port | Endpoint |
|--------|------|----------|
| srclight | 8742 | `http://127.0.0.1:8742/mcp` |
| model-radar | 8743 | `http://127.0.0.1:8743/mcp` |
| zhcorpus | 8744 | `http://127.0.0.1:8744/mcp` |
| conductor | 9999 | `http://127.0.0.1:9999/mcp` |

## Migrating from SSE to Streamable HTTP

1. Change URL from `/sse` to `/mcp`
2. Change `transportType` from `"sse"` to `"streamable-http"` (Cursor) or `"type": "http"` (OpenClaw)
3. No server-side changes needed — the server already serves both endpoints
