---
agent: droid
agent_id: droid
agent_name: Droid
version: 1.0.0
---

# Droid — Memory Bridge Configuration

**Purpose:** Droid agent configuration for the Memory Bridge framework. Provides awareness and MCP integration for cross-agent conversation persistence.

## Detection

Droid detects this repo via ANY of:
1. `.cross-agent-memory` file in repo root
2. `SKILL.md` with `skill: memory-bridge` in frontmatter
3. Git remote URL contains `memory-bridge`

## MCP Configuration

Droid connects to the Memory Bridge MCP server as a client:

| Transport | Endpoint | Use Case |
|-----------|----------|----------|
| SSE | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` | Standard MCP client connection |
| Streamable HTTP | `http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp` | Alternative for modern clients |

**Important:** Droid's MCP config must use `"type": "sse"` when connecting to the SSE endpoint (port 8080). Using `"type": "http"` with an SSE URL will fail.

**Bearer Token:** Set via `MEMORY_BRIDGE_BEARER_TOKEN` environment variable for authenticated access.

## Available Skills

| Skill | Command | Purpose |
|-------|---------|---------|
| `memory-bridge` | "save to memory bridge" | Save conversation to repo |
| `memory-bridge-boot` | `/memory-bridge-boot` | Session readiness check |
| `memory-bridge-index` | `/memory-bridge-index` | Build conversation index |
| `memory-bridge-digest` | `/memory-bridge-digest {topic}` | Query by topic |
| `memory-bridge-import` | `/memory-bridge-import` | Import external exports |
| `llm-wiki-compile` | `/llm-wiki-compile {topic}` | Compile wiki articles |

All skills are defined in `skills/` — install from there.

## Quick Start

```bash
# Boot and verify setup
/memory-bridge-boot

# Save current conversation
"save to memory bridge"

# Query a topic
/memory-bridge-digest mcp

# Rebuild the index
/memory-bridge-index
```

## File Locations

- Skills: `skills/{skill-name}/SKILL.md`
- References: `skills/{skill-name}/references/`
- MCP Config: `.droid/mcp.json` (or your agent's global MCP config)

## Agent Identity

- **Agent ID:** `droid`
- **Agent Name:** `Droid`
- **Conversation Filename:** `YYYYMMDD-HHMMSS-droid.md`
- **User:** `<YOUR_NAME>`
- **Timezone:** Your local timezone
