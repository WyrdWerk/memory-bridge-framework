# Memory Bridge Framework

I run a lot of coding agents. Cursor on the laptop, Claude Code on the VPS, Codex on the desktop, Hermes on Discord. They're all talking to me, making decisions, leaving tasks open — and none of them know what the others are doing.

This fixes that. One Git repo. One markdown format. Every agent reads and writes to the same store.

**Author:** [WyrdWerk](https://github.com/WyrdWerk)  
**License:** MIT

---

## Why I Built This

Seven agents, three machines, five interfaces. Conversations scattered across Cursor's local storage, Claude Code's session history, Discord threads. I'd finish a session with one agent, switch to another, and start explaining the same problem from scratch. No record of what was decided. No list of what's still pending. No cross-visibility.

The agents didn't know each other existed. I was the router. And I was losing state.

This framework makes the repo the router. Structured markdown with YAML frontmatter. Deterministic lexical search. No embeddings, no API keys, works offline. Just git.

**Key insight:** You don't need vector search when your format is rigid enough. YAML frontmatter + lexical scoring + topic aliases does the job.

**What changed:** Before this, I'd mention something like "that headless Obsidian container on the VPS" and get blank stares. The agent had no record of the three prior sessions where we'd set it up, debugged it, and documented the exact state. I'd burn a conversation just re-establishing operational reality. Now I point the agent at the saved conversation and it loads the full context — what's running, where, how it's configured. No re-explanation. No wasted sessions. The operational state transfers across agents and across time.

**This isn't theory. I've been running a private version of this for a week now.** Seven agents, 80+ conversations saved, and it's actually working. That private repo is what convinced me to clean it up, swap in placeholders, and publish the skeleton. The public repo you're looking at is the sanitized version — same markdown format, same index system, same MCP server, same git workflow. The only difference is this one won't accidentally leak my Tailscale IP.

---

## How It Works

```
Save     →  conversations/YYYY/MM/DD/file.md  →  git push  →  shared repo
                                                                    ↓
Index    →  scans all conversations           →  INDEX.md    ←  git pull
                                                                    ↓
Digest   →  queries INDEX.md by topic        →  deep-reads matches
                 ↓
          open items + pending decisions + cross-references
```

---

## The Six Distributed Skills

| Skill | Purpose | Trigger | When to use |
|-------|---------|---------|-------------|
| `memory-bridge` | Save a conversation | "save to memory bridge" | End of any substantive session |
| `memory-bridge-boot` | Readiness check | `/memory-bridge-boot` | Start of a session |
| `memory-bridge-index` | Build/check index | `/memory-bridge-index` | Once/day, or before querying |
| `memory-bridge-digest` | Topic-based query | `/memory-bridge-digest {topic}` | When you need context on a topic |
| `memory-bridge-import` | Import external transcripts | `/memory-bridge-import` | When importing from Claude, ChatGPT, etc. |
| `llm-wiki-compile` | Compile wiki articles | `/llm-wiki-compile {topic}` | When updating the knowledge layer |

---

## Supported Agents

| Agent | agent_id | Platform | Interface | Auto-Load Config |
|-------|----------|----------|-----------|-----------------|
| OpenCode | `opencode` | Cross-platform | CLI | `.opencode/OPENCODE.md` |
| Claude Code | `claude` | Cross-platform | CLI | `.claude/CLAUDE.md` |
| Cursor | `cursor` | Cross-platform | IDE, ACP editors | `.cursorrules` |
| Codex | `codex` | Cross-platform | CLI | `.codex/CODEX.md` |
| Pi Agent | `pi` | Cross-platform | CLI | `.pi/PI.md` |
| Hermes | `hermes` | VPS/Server | Discord, Slack | `.hermes/HERMES.md` |
| Droid | `droid` | Cross-platform | CLI | `.droid/DROID.md` |

Each agent has its own auto-loaded instruction file in the repo. When an agent opens this repository, it reads its respective config for save workflow, boot/index/digest triggers, MCP connection details, and agent-specific commit formats.

---

## Repository Structure

```
memory-bridge-framework/
├── README.md                    # This file
├── SETUP.md                     # Step-by-step installation guide
├── AGENTS.md                    # Generic agent guidance (all agents)
├── SKILL.md                     # Canonical specification (schema, format, detection)
├── .cross-agent-memory          # Detection marker for agents
├── .cursorrules                 # Cursor auto-loaded instructions
├── .claude/CLAUDE.md            # Claude Code instructions
├── .codex/CODEX.md              # Codex instructions
├── .cursor/CURSOR.md            # Cursor instructions (alternative)
├── .droid/DROID.md              # Droid instructions
├── .hermes/HERMES.md            # Hermes instructions
├── .opencode/OPENCODE.md        # OpenCode instructions
├── .pi/PI.md                    # Pi Agent instructions
├── templates/
│   └── conversation.md          # Conversation file template
├── skills/                      # Distributed skill definitions
│   ├── memory-bridge/
│   ├── memory-bridge-boot/
│   ├── memory-bridge-index/
│   ├── memory-bridge-digest/
│   ├── memory-bridge-import/
│   └── llm-wiki-compile/
├── bin/
│   └── memory-bridge            # Deterministic CLI tool
├── scripts/
│   └── memory_bridge/           # MCP server implementation
│       ├── mcp_server.py
│       ├── parse_conv.py
│       ├── index_build.py
│       └── search_lex.py
├── docs/                        # Full documentation
│   ├── schema.md                # Frontmatter specification
│   ├── cli.md                   # CLI usage guide
│   ├── mcp-setup.md             # MCP server setup (all agents)
│   ├── index-format.md          # Index structure
│   ├── query-examples.md        # Query examples
│   ├── agent-contracts.md       # Agent integration spec
│   └── import-workflows.md      # Import framework
├── importers/                   # Import adapters
│   ├── spec.md
│   ├── README.md
│   └── examples/
├── config/
│   └── topic_aliases.json       # Semantic topic expansion
├── wiki/                        # Compiled knowledge (optional)
│   ├── index.md
│   └── .registry.yaml
└── conversations/               # Your private conversation store
    └── YYYY/MM/DD/
```

---

## Quick Start

```bash
# 1. Clone this framework as your own private repo
git clone https://github.com/WyrdWerk/memory-bridge-framework.git ~/memory-bridge
cd ~/memory-bridge

# 2. Initialize your private repo (remove framework origin, add your own)
git remote remove origin
git remote add origin https://github.com/<YOUR_USERNAME>/your-private-hub.git

# 3. Install skills for your agents
cp -r skills/memory-bridge ~/.hermes/skills/       # Hermes
cp -r skills/memory-bridge ~/.cursor/skills/        # Cursor
cp -r skills/memory-bridge ~/.claude/skills/        # Claude Code
# ... etc for each agent (see SETUP.md for all)

# 4. Configure the MCP server (optional but recommended for cross-repo access)
# See docs/mcp-setup.md for per-agent transport and config

# 5. Save your first conversation
# In any agent session: say "save to memory bridge"
```

See [SETUP.md](SETUP.md) for detailed installation and configuration.

---

## Core Principles

| Principle | Implementation |
|-----------|----------------|
| **Git-backed** | Single source of truth, versioned history |
| **Deterministic** | No embeddings, no API keys, works offline |
| **Agent-agnostic** | Same format for all agent types |
| **Human-readable** | Plain markdown, inspectable, portable |
| **Self-contained** | Each skill works independently |
| **Cross-repo via MCP** | Agents can save/query from any project directory |

---

## MCP Server: Cross-Repo Operation

The MCP server is what makes this actually usable day-to-day. Without it, an agent needs the memory-bridge repo open locally to save anything. So you're coding in `~/projects/my-app`, want to save the session, and you have to switch repos first. Annoying.

With the MCP server, the agent connects to a centralized server (runs on your VPS or localhost) that operates on the memory-bridge repo. Now the agent can:

- Save conversations while working in **any** project directory
- Search past conversations without leaving the current project
- Rebuild the index or query topics from anywhere

**Verified transports per agent (see `docs/mcp-setup.md` for full matrix):**

| Agent | Verified Transport | Endpoint |
|-------|-------------------|----------|
| Codex | Streamable HTTP | `:8081/mcp` |
| Cursor | Streamable HTTP | `:8081/mcp` |
| Claude Code | Streamable HTTP | `:8081/mcp` |
| OpenCode | SSE | `:8080/sse` |
| Pi | SSE | `:8080/sse` |
| Droid | SSE | `:8080/sse` |
| Hermes | Runs the server | — |

The MCP server exposes 11 tools: `save_conversation`, `update_conversation`, `search_conversations`, `digest_conversations`, `list_conversations`, `show_conversation`, `get_status`, `rebuild_index`, `check_index`, `import_conversations`, `sync_skills`.

---

## Documentation

- [SETUP.md](SETUP.md) — Installation and configuration
- [AGENTS.md](AGENTS.md) — Generic guidance for all agents
- [SKILL.md](SKILL.md) — Canonical schema and format specification
- [docs/schema.md](docs/schema.md) — Frontmatter field reference
- [docs/cli.md](docs/cli.md) — CLI usage guide
- [docs/mcp-setup.md](docs/mcp-setup.md) — MCP server setup and verified transport matrix
- [docs/agent-contracts.md](docs/agent-contracts.md) — How agents integrate
- [docs/import-workflows.md](docs/import-workflows.md) — Importing external conversations

---

## Contributing

This is a framework template. Fork it, adapt it to your workflow, and improve it. The design is intentionally minimal so you can extend without fighting the system.

If you build improvements worth sharing back:
1. Keep the core philosophy (git-backed, deterministic, agent-agnostic)
2. Skills should be self-contained
3. Don't break the canonical format without versioning

---

## License

MIT. Use it, fork it, build on it.
