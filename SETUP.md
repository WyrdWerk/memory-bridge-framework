# Memory Bridge Setup Guide

Step-by-step installation and configuration.

---

## Prerequisites

- Git
- Python 3.10+ (for MCP server and CLI tools)
- One or more AI coding agents (Cursor, Claude Code, Codex, OpenCode, Pi, Hermes, Droid)

---

## Step 1: Create Your Private Repository

This framework is a template. You create your own private repo from it.

### Option A: Fork on GitHub (Recommended)

1. Fork `github.com/WyrdWerk/memory-bridge-framework` to your own account
2. Make the fork **private**
3. Clone your private fork:
   ```bash
   git clone https://github.com/<YOUR_USERNAME>/<YOUR_PRIVATE_REPO>.git ~/memory-bridge
   cd ~/memory-bridge
   ```

### Option B: Manual Copy

```bash
# Clone the framework
git clone https://github.com/WyrdWerk/memory-bridge-framework.git /tmp/framework-template
cp -r /tmp/framework-template ~/memory-bridge
cd ~/memory-bridge
rm -rf .git
git init
git add .
git commit -m "init: memory bridge framework"
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_PRIVATE_REPO>.git
git push -u origin main
```

---

## Step 2: Install Skills for Your Agents

Each agent needs the skill definition copied to its local directory.

### Hermes Agent

```bash
cp -r skills/memory-bridge ~/.hermes/skills/
cp -r skills/memory-bridge-boot ~/.hermes/skills/
cp -r skills/memory-bridge-index ~/.hermes/skills/
cp -r skills/memory-bridge-digest ~/.hermes/skills/
cp -r skills/memory-bridge-import ~/.hermes/skills/
cp -r skills/llm-wiki-compile ~/.hermes/skills/
```

### Cursor

Cursor reads skills from `~/.cursor/skills/` or project `.cursorrules`.

```bash
mkdir -p ~/.cursor/skills
cp -r skills/* ~/.cursor/skills/
```

Or add to your project's `.cursorrules`:
```
Load skill: memory-bridge
```

### Claude Code

```bash
mkdir -p ~/.claude/skills
cp -r skills/* ~/.claude/skills/
```

### Codex

```bash
mkdir -p ~/.codex/skills
cp -r skills/* ~/.codex/skills/
```

### OpenCode

```bash
mkdir -p ~/.config/opencode/skills
cp -r skills/* ~/.config/opencode/skills/
```

### Pi

```bash
mkdir -p ~/.pi/agent/skills
cp -r skills/* ~/.pi/agent/skills/
```

### Droid

```bash
mkdir -p ~/.droid/skills
cp -r skills/* ~/.droid/skills/
```

---

## Step 3: Configure the MCP Server (Optional but Recommended)

The MCP server enables agents to call Memory Bridge tools programmatically from **any project directory** — not just when working inside the memory-bridge repo.

### Why MCP Matters

Without MCP, an agent can only save conversations when it has the memory-bridge repo open. With MCP:
- Save conversations while coding in `~/projects/my-app`
- Search past conversations from any directory
- Query topics and rebuild the index without switching repos

### Deploy the Server

#### On a VPS (Recommended for Multi-Agent Setup)

```bash
# Install dependencies
pip install 'mcp[cli]' fastapi uvicorn

# Start Streamable HTTP server (recommended)
python scripts/memory_bridge/mcp_server.py \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8081 \
  --repo <REPO_PATH>

# Or start HTTP/SSE server (legacy compatibility)
python scripts/memory_bridge/mcp_server.py \
  --transport sse \
  --host 0.0.0.0 \
  --port 8080 \
  --repo <REPO_PATH>
```

#### As a Systemd Service

Create `~/.config/systemd/user/memory-bridge-mcp.service`:

```ini
[Unit]
Description=Memory Bridge MCP Server
After=network.target

[Service]
Type=simple
WorkingDirectory=<REPO_PATH>
Environment=PYTHONPATH=<REPO_PATH>/scripts
Environment=MEMORY_BRIDGE_REPO=<REPO_PATH>
ExecStart=<PYTHON_PATH> -m memory_bridge.mcp_server \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8081 \
  --repo <REPO_PATH>
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable memory-bridge-mcp
systemctl --user start memory-bridge-mcp
```

### Configure Agents to Use MCP

See [docs/mcp-setup.md](docs/mcp-setup.md) for per-agent transport and configuration.

---

## Step 4: Verify Everything Works

### Boot Check

In any agent session, run:
```
/memory-bridge-boot
```

Expected output:
```
Memory Bridge Boot -- COMPLETE
Repo sync: Ready
Conversations on disk: 0 files
Skills installed: All present
Ready for operations.
```

### Save Test

Say in any agent session:
```
save to memory bridge
```

Expected:
- File created in `conversations/YYYY/MM/DD/`
- Auto-committed and pushed to your private repo

### Index Test

```
/memory-bridge-index
```

Expected:
- `INDEX.md` generated at repo root
- Committed and pushed

### MCP Cross-Repo Test

With MCP configured, open a different project and try:
```
/memory-bridge-digest mcp
```

The agent should query the memory hub without needing the repo open locally.

---

## Step 5: Customize

### Topic Aliases

Edit `config/topic_aliases.json` to add synonyms for your domain:

```json
{
  "deploy": ["deployment", "deploying", "deployed", "release", "ship"],
  "mcp": ["model-context-protocol", "mcp-server", "fastmcp"]
}
```

### Timezone

Default timestamps use Asia/Kolkata (UTC+5:30). Change in skill definitions or keep as-is.

### Agent Identity

Update `agent_id` and `agent_name` in each agent's instruction file (`.claude/CLAUDE.md`, `.cursorrules`, etc.) if you use different names.

---

## Troubleshooting

### "I don't detect the memory-bridge repo"

The agent is not in the repo directory. Navigate to `~/memory-bridge` first, or ensure `.cross-agent-memory` marker is present.

### Skills not found

Check that the skill directory matches your agent's expected path. Each agent has different conventions.

### Git push fails

Ensure your private repo has write access configured. The save skill auto-commits and pushes — no manual git needed, but SSH keys or HTTPS tokens must be configured.

### MCP connection refused

- Check the server is running: `systemctl --user status memory-bridge-mcp`
- Verify network connectivity (Tailscale, VPN, or local network)
- Check firewall rules on the VPS
- Ensure the correct transport type: SSE for port 8080, Streamable HTTP for port 8081

### "405 Method Not Allowed" on MCP

Your agent is using the wrong transport type. Codex needs Streamable HTTP (`:8081/mcp`), not SSE (`:8080/sse`).

---

## Next Steps

- Read [SKILL.md](SKILL.md) for the full format specification
- Read [AGENTS.md](AGENTS.md) for generic agent guidance
- Explore [docs/](docs/) for detailed guides
- Save your first real conversation and build your index
- Set up automated index rebuilds (daily cron recommended)
