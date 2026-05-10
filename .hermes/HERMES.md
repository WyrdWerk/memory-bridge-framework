# Memory Bridge — Hermes Agent Instructions

## What This Repo Is

Cross-agent conversation persistence. Every AI conversation with <YOUR_NAME> saved as structured markdown in a shared Git repo. Any agent can see what happened in any other agent's session. See `README.md` for full documentation.

## The Six Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| memory-bridge | "save to memory bridge" | Save a conversation to the repo |
| memory-bridge-boot | `/memory-bridge-boot` | Readiness check at session start |
| memory-bridge-index | `/memory-bridge-index` | Build or check the conversation index |
| memory-bridge-digest | `/memory-bridge-digest {topic}` | Query conversations by topic |
| memory-bridge-import | `/memory-bridge-import` | Import external conversations/transcripts |
| llm-wiki-compile | `/llm-wiki-compile {topic}` | Compile wiki articles from conversations |

Skill definitions live in `skills/` — that's the canonical source. Install from there.

## Saving Conversations

When user says "save to memory bridge", "memory-bridge save", "save this conversation", "save session", or "archive this":

### Detection

Check ANY of:
1. Git remote URL contains "memory-bridge"
2. File `.cross-agent-memory` exists in repo root
3. `SKILL.md` exists with `skill: memory-bridge`

If not detected: "I don't detect the memory-bridge repo. Navigate to it first."

### Action Steps

1. **Analyze conversation** — review available context/session history
2. **Generate timestamp** — use your local timezone
3. **Create directories** — `conversations/YYYY/MM/DD/` (auto-create if missing)
4. **Filename** — `YYYYMMDD-HHMMSS-hermes.md`
5. **Write structured content** — YAML frontmatter + sections per template below
6. **Git workflow** — auto-commit and push:
   ```bash
   git add conversations/YYYY/MM/DD/{filename}
   git commit -m "memory(hermes): {timestamp} - {brief-topic}"
   git push origin main
   ```
7. **Confirm** — "Saved to memory bridge: conversations/YYYY/MM/DD/{filename}"

No user confirmation needed for commit.

### Content Schema

```yaml
---
timestamp: "YYYY-MM-DDTHH:MM:SS+05:30"
agent_id: "hermes"
agent_name: "Hermes Agent"
session_id: "discord-{thread_id}"
user: "<YOUR_NAME>"
duration_minutes: 0
topics: ["topic1", "topic2", "topic3"]
related_repos: ["repo1", "repo2"]
related_sessions: ["YYYYMMDD-HHMMSS-agent"]
---

## Context
[2-3 sentences: where this happened, what triggered it]

## Key Discussion Points
1. Point one
2. Point two
3. Point three

## Decisions Made
- [x] Decision finalized
- [ ] Decision pending

## Action Items
- [ ] Task for user
- [ ] Task for agent

## Code/Config References
- File paths, repos, commands

## Next Steps / Follow-up
[What happens next]
```

### Error Handling

- **Not in repo**: "I don't detect the memory-bridge repo. Navigate to it first."
- **Git not initialized**: Initialize git, create initial commit
- **Push fails**: Stage locally, notify user to sync manually

## Booting

At session start, run `/memory-bridge-boot` or say "boot memory bridge":

1. Pulls latest from remote (`git pull origin main`)
2. Counts conversation files on disk (filenames only, no content reading)
3. Checks if memory-bridge skill is installed for this agent
4. Outputs readiness status

## Indexing

Run `/memory-bridge-index` or "rebuild memory index" once/day:

1. Pulls latest from remote
2. Scans all conversation frontmatter + bodies for open items
3. Writes `INDEX.md` to repo root (full rewrite)
4. Commits and pushes

Check freshness without rebuilding: `/memory-bridge-index check` or "check memory index"

`INDEX.md` is machine-generated. Do not edit manually.

## Querying by Topic

Run `/memory-bridge-digest {topic}` or "memory digest {topic}":

1. Checks `INDEX.md` exists (if not, run `/memory-bridge-index` first)
2. Checks index freshness (file count vs index entries)
3. Filters index entries by topic (semantic matching)
4. Deep-reads only matching conversations (max 10)
5. Outputs: timeline, open items, cross-references, pending verdict

## Repo Reference

| File | Purpose |
|------|---------|
| `SKILL.md` | Canonical specification (schema, format, detection) |
| `INDEX.md` | Machine-generated conversation index (do not edit) |
| `README.md` | Full documentation for humans and agents |
| `skills/` | Canonical skill definitions (install from here) |
| `templates/conversation.md` | Conversation file template |

## MCP Server Operation (VPS-Side)

Hermes on the VPS operates the **centralized Memory Bridge MCP server** for all Tailscale-connected agents.

### Dual-Port Architecture

| Port | Transport | For |
|------|-----------|-----|
| **8080** | SSE | Cursor, Claude, OpenCode, Pi, Droid |
| **8081** | Streamable HTTP | **Codex** |

### Starting the MCP Servers

```bash
# Terminal 1: Legacy SSE (for most agents)
export MEMORY_BRIDGE_REPO=<REPO_PATH>
./bin/memory-bridge mcp --transport sse --host 0.0.0.0 --port 8080

# Terminal 2: Streamable HTTP (for Codex)
export MEMORY_BRIDGE_REPO=<REPO_PATH>
./bin/memory-bridge mcp --transport streamable-http --host 0.0.0.0 --port 8081
```

### Health Checks

```bash
# Check SSE endpoint
./bin/memory-bridge mcp-check --transport sse --url http://<YOUR_VPS_TAILSCALE_IP>:8080/sse

# Check Streamable HTTP endpoint
./bin/memory-bridge mcp-check --transport streamable-http --url http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp
```

### Persistent Operation

For production, run under systemd or screen/tmux to survive disconnections.

### Agent Connection Matrix

| Agent | Transport | URL | Config Location |
|-------|-----------|-----|-----------------|
| Codex | Streamable HTTP | `http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp` | `~/.codex/config.toml` |
| Cursor | Streamable HTTP | `http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp` | `~/.cursor/mcp.json` |
| Claude | Streamable HTTP | `http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp` | `~/.claude/mcp_servers.json` |
| OpenCode | SSE | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` | `~/.config/opencode/mcp_servers.json` |
| Pi | SSE | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` | `~/.pi/agent/mcp.json` |
| Droid | SSE | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` | `~/.droid/mcp.json` |

Hermes itself does not connect as a client — it runs the server that other agents connect to.

## Agent Identity

- agent_id: `hermes`
- Filename: `YYYYMMDD-HHMMSS-hermes.md`
- Hermes detects this repo via `.cross-agent-memory` marker or `SKILL.md` presence
