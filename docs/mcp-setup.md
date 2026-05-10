# Memory Bridge MCP Server Setup

Centralized MCP hub for cross-agent conversation persistence.

---

## What the MCP Server Enables

The MCP server is the key enabler for **cross-repo operation**. Without it, an agent must have the memory-bridge repo checked out locally to save or query conversations. With the MCP server:

- **Save conversations** while working in `~/projects/my-app`, `~/work/website`, or any directory
- **Search past conversations** without leaving the current project
- **Rebuild the index** or query topics from anywhere
- **All agents share one canonical repo** regardless of which machine or project they're on

**Architecture:**
```
Agent working in ~/projects/my-app
    ↓ MCP protocol (HTTP/SSE or Streamable HTTP)
MCP Server (running on VPS or localhost)
    ↓ reads/writes
Git repository (~/memory-bridge/conversations/, INDEX.md)
```

The server only exposes operations on the conversation store — no shell execution, no filesystem access outside the repo.

---

## Architecture

- **Server Location:** Your VPS or local machine (`<YOUR_VPS_TAILSCALE_IP>:8080` for SSE, `:8081` for Streamable HTTP)
- **Primary Transport:** Streamable HTTP (recommended for modern clients)
- **Legacy Compatibility:** HTTP/SSE
- **Auth:** Bearer token (defense in depth even on private networks)
- **Repo:** Single canonical clone, all agents access remotely

---

## Verified Transport Matrix

This matrix reflects **actual verified configurations** across the agent fleet:

| Agent | Verified Transport | Endpoint | Config Location | Status |
|-------|-------------------|----------|-----------------|--------|
| **Codex** | Streamable HTTP | `http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp` | `~/.codex/config.toml` | ✅ Verified |
| **Cursor** | Streamable HTTP | `http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp` | `~/.cursor/mcp.json` | ✅ Verified |
| **Claude Code** | Streamable HTTP | `http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp` | `~/.claude/mcp_servers.json` | ✅ Verified |
| **OpenCode** | SSE | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` | `~/.config/opencode/mcp_servers.json` | ✅ Verified |
| **Pi** | SSE | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` | `~/.pi/agent/mcp.json` | ✅ Verified |
| **Droid** | SSE | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` | `~/.droid/mcp.json` | ✅ Verified |
| **Hermes** | Runs the server | — | — | Server operator |

**Important transport rules:**
- **Codex must use Streamable HTTP (`:8081/mcp`)**. Pointing Codex at `/sse` returns `405 Method Not Allowed` because Codex's MCP client sends POST requests that SSE endpoints reject.
- **Droid must use `"type": "sse"`** in its MCP config. Using `"type": "http"` with an SSE URL fails.
- **Most agents** (OpenCode, Pi, Droid, Claude Code) work with SSE on `:8080/sse`.
- **Streamable HTTP (`:8081/mcp`)** is the modern standard and works with Codex, Cursor, and Claude Code.

---

## Server Status

```bash
# Check if legacy SSE server is reachable
curl http://<YOUR_VPS_TAILSCALE_IP>:8080/sse

# Check if Streamable HTTP server is reachable
curl -X POST http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'

# View logs
journalctl --user -u memory-bridge-mcp-sse -f
journalctl --user -u memory-bridge-mcp-streamable -f
```

---

## Agent Configuration

### Claude Code

```bash
claude mcp add memory-bridge \
  --url http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp \
  --bearer-token <YOUR_AUTH_TOKEN>
```

Or edit `~/.claude/mcp_servers.json`:

```json
{
  "mcpServers": {
    "memory-bridge": {
      "type": "http",
      "url": "http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_AUTH_TOKEN>"
      }
    }
  }
}
```

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "memory-bridge": {
      "url": "http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp"
    }
  }
}
```

### Codex

Add to `~/.codex/config.toml`:

```toml
[[mcp_servers]]
name = "memory-bridge"
command = "http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp"
```

### OpenCode

Add to `~/.config/opencode/mcp_servers.json`:

```json
{
  "mcpServers": {
    "memory-bridge": {
      "type": "sse",
      "url": "http://<YOUR_VPS_TAILSCALE_IP>:8080/sse"
    }
  }
}
```

### Pi

Add to `~/.pi/agent/mcp.json`:

```json
{
  "mcpServers": {
    "memory-bridge": {
      "type": "sse",
      "url": "http://<YOUR_VPS_TAILSCALE_IP>:8080/sse"
    }
  }
}
```

### Droid

Add to `~/.droid/mcp.json`:

```json
{
  "mcpServers": {
    "memory-bridge": {
      "type": "sse",
      "url": "http://<YOUR_VPS_TAILSCALE_IP>:8080/sse"
    }
  }
}
```

---

## Verification

After configuring, restart your agent and verify connection:

```bash
# Using the framework CLI
./bin/memory-bridge mcp-check --transport streamable-http --url http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp
```

Or manually:

```bash
curl -s -X POST http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

---

## Security Notes

- Run behind a private network (Tailscale, WireGuard, or VPC)
- Use bearer token authentication even on private networks (defense in depth)
- The server only exposes read/query and save operations to the conversation store — no shell execution, no filesystem access outside the repo
- Restrict `allowed_hosts` in the server code to your specific Tailscale IP range if desired
