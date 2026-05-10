# AGENTS.md — Generic Agent Guidance for Memory Bridge

This file provides guidance that applies to **all agents** working with the Memory Bridge framework. Each agent also has its own auto-loaded instruction file (`.claude/CLAUDE.md`, `.cursorrules`, `.codex/CODEX.md`, etc.) with agent-specific conventions.

---

## Core Philosophy

1. **Save at the end of every substantive session.** If you discussed something worth remembering, save it.
2. **Boot at the start of every session.** Sync before you start to avoid working on stale state.
3. **Index daily.** The index is the query engine — keep it fresh.
4. **No user confirmation for saves.** The save is append-only and reversible via git. Just do it.

---

## Detection

Before any operation, verify you are in the Memory Bridge repo:

Check ANY of:
1. `.cross-agent-memory` file exists in repo root
2. `SKILL.md` with `skill: memory-bridge` in frontmatter
3. Git remote URL contains `memory-bridge`

If not detected: "I don't detect the memory-bridge repo. Navigate to it first."

---

## The Six Skills (Universal Triggers)

| Skill | Trigger | What You Do |
|-------|---------|-------------|
| **memory-bridge** | User says "save to memory bridge", "save this conversation", "save session", "archive this" | Generate timestamp, write structured markdown, git commit + push |
| **memory-bridge-boot** | User says `/memory-bridge-boot` or "boot memory bridge" | `git pull`, count files, check skill installation, report status |
| **memory-bridge-index** | User says `/memory-bridge-index` or "rebuild memory index" | Scan all conversations, write `INDEX.md`, commit + push |
| **memory-bridge-digest** | User says `/memory-bridge-digest {topic}` or "memory digest {topic}" | Search `INDEX.md`, deep-read matches, output timeline + open items |
| **memory-bridge-import** | User says `/memory-bridge-import` or "import conversations" | Read external exports, sanitize, convert format, write to `conversations/` |
| **llm-wiki-compile** | User says `/llm-wiki-compile {topic}` or "compile wiki" | Synthesize `raw/{topic}/` into `wiki/{topic}/article.md` |

---

## Save Workflow (All Agents)

### 1. Generate Timestamp

Use the local timezone (default: Asia/Kolkata IST, UTC+5:30):
```bash
TZ=Asia/Kolkata date +"%Y%m%d-%H%M%S"
```

### 2. Create Directory Structure

```bash
mkdir -p conversations/YYYY/MM/DD/
```

### 3. Filename Convention

```
YYYYMMDD-HHMMSS-{agent_id}.md
```

Examples: `20260510-143022-cursor.md`, `20260510-143022-hermes.md`

### 4. Content Format

Every conversation file MUST have YAML frontmatter followed by markdown sections:

```yaml
---
timestamp: "YYYY-MM-DDTHH:MM:SS+05:30"
agent_id: "{your_agent_id}"
agent_name: "{Your Agent Name}"
session_id: "optional-session-identifier"
user: "<YOUR_NAME>"
duration_minutes: 0
topics: ["topic1", "topic2"]
related_repos: []
related_sessions: []
artifacts: []  # Optional
# keywords: []            # optional
# learnings: []           # optional
# references: []          # optional
---
```

### 5. Required Sections

```markdown
## Context
[2-3 sentences: where this happened, what triggered it]

## Key Discussion Points
1. Point one
2. Point two

## Decisions Made
- [x] Decision finalized
- [ ] Decision pending

## Action Items
- [ ] Task description

## Code/Config References
- File paths, repos, commands

## Next Steps / Follow-up
[What happens next]
```

### 6. Git Workflow

```bash
git add {filepath}
git commit -m "memory({agent_id}): {YYYYMMDD-HHMMSS} - {brief-topic}"
git push origin main
```

**With artifact embedded:**
```bash
git commit -m "memory({agent_id}): {YYYYMMDD-HHMMSS} - {topic} [+artifact: {filename}]"
```

---

## Artifact Embedding

When a session produces substantial output (research brief, analysis, decision doc >1,500 words):

1. Add to frontmatter: `artifacts: [{"name": "Artifact Name", "file": "path", "type": "research-brief"}]`
2. Insert `## Embedded Artifact: {Name}` section before `## Next Steps / Follow-up`
3. Include metadata header: File, Type, Word Count, Status
4. Copy artifact content (abridge if >3,000 words, note "abridged")

**Do NOT embed:** Simple code/config references, terminal logs, drafts being iterated on separately.

---

## Boot Workflow

Run at the start of every session:

1. `git pull origin main` — sync with remote
2. Count conversation files (filenames only, no content reading)
3. Check if memory-bridge skill is installed for this agent
4. If MCP is configured, run a lightweight probe
5. Report: repo status, conversation count, skill presence, index freshness

---

## Index Workflow

Run once per day or before any digest query:

1. `git pull origin main` — sync
2. Scan all conversation frontmatter for metadata
3. Scan all conversation bodies for open item counts
4. Write `INDEX.md` to repo root (full rewrite)
5. Commit and push

Check freshness without rebuilding: `./bin/memory-bridge check`

---

## Digest Workflow

Run when you need context on a topic:

1. Verify `INDEX.md` exists (run index skill first if missing)
2. Check index freshness (disk count vs index entries)
3. Filter index entries by topic (lexical matching + alias expansion via `config/topic_aliases.json`)
4. Deep-read only matching conversations (max 10)
5. Output: timeline, open items, cross-references, pending verdict

---

## MCP Cross-Repo Operation

When the MCP server is configured, agents can operate on the Memory Bridge **from any project directory**:

| Tool | Purpose | Cross-repo? |
|------|---------|-------------|
| `save_conversation` | Save current session | ✅ Yes |
| `search_conversations` | Lexical search with scoring | ✅ Yes |
| `digest_conversations` | Topic digest generation | ✅ Yes |
| `list_conversations` | List with pagination | ✅ Yes |
| `show_conversation` | Retrieve full conversation | ✅ Yes |
| `get_status` | Repo status + index freshness | ✅ Yes |
| `rebuild_index` | Full index rebuild | ✅ Yes |
| `check_index` | Quick freshness check | ✅ Yes |
| `import_conversations` | External import | ✅ Yes |
| `sync_skills` | Skill parity sync | ✅ Yes |

**How it works:** The agent connects to the MCP server over HTTP. The server operates on its configured repo path. The agent doesn't need the repo checked out locally.

---

## Error Handling

| Problem | Response |
|---------|----------|
| Not in memory-bridge repo | "I don't detect the memory-bridge repo. Navigate to it first." |
| Git not initialized | Initialize git, create initial commit |
| Push fails | Stage locally, notify user to sync manually |
| Index missing | "Run `/memory-bridge-index` first to build the index." |
| MCP connection refused | Check server status, verify transport type and URL |

---

## Agent Identity Reference

| Agent | agent_id | Config File | Commit Prefix |
|-------|----------|-------------|---------------|
| OpenCode | `opencode` | `.opencode/OPENCODE.md` | `memory(opencode):` |
| Claude Code | `claude` | `.claude/CLAUDE.md` | `memory(claude):` |
| Cursor | `cursor` | `.cursorrules` | `memory(cursor):` |
| Codex | `codex` | `.codex/CODEX.md` | `memory(codex):` |
| Pi | `pi` | `.pi/PI.md` | `memory(pi):` |
| Hermes | `hermes` | `.hermes/HERMES.md` | `memory(hermes):` |
| Droid | `droid` | `.droid/DROID.md` | `memory(droid):` |

---

## Key Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Canonical specification (schema, format, detection) |
| `INDEX.md` | Machine-generated conversation index (do not edit) |
| `README.md` | Framework overview and quick start |
| `SETUP.md` | Step-by-step installation guide |
| `AGENTS.md` | This file — generic agent guidance |
| `templates/conversation.md` | Conversation file template |
| `config/topic_aliases.json` | Semantic topic expansion |
| `skills/` | Distributed skill definitions |
| `bin/memory-bridge` | Deterministic CLI |
