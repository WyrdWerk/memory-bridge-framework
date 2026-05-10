# Memory Bridge — Pi Agent Instructions

## What This Repo Is

Cross-agent conversation persistence. Every AI conversation with <YOUR_NAME> saved as structured markdown in a shared Git repo. Any agent can see what happened in any other agent's session. See `README.md` for full documentation.

---

## MCP Server Connection

The Memory Bridge MCP server can run centrally for all agents. Pi connects via SSE transport.

### MCP Configuration

Add to your Pi MCP config (`~/.pi/agent/mcp.json`):

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

### Available MCP Tools

When connected, the following tools are available:
- `save_conversation` — Save current conversation to repo
- `update_conversation` — Update any field of an existing conversation (preserves unmodified fields)
- `search_conversations` — Lexical search with scoring
- `digest_conversations` — Topic digest generation
- `list_conversations` — List with pagination
- `show_conversation` — Retrieve full conversation
- `get_status` — Repo status + index freshness
- `rebuild_index` — Full index rebuild
- `check_index` — Quick freshness check
- `import_conversations` — External import
- `sync_skills` — Skill parity sync

### Verification

After configuring, restart Pi and verify connection:
```bash
./bin/memory-bridge mcp-check --transport sse --url http://<YOUR_VPS_TAILSCALE_IP>:8080/sse
```

## Agent Identity

- **agent_id:** `pi`
- **agent_name:** `Pi`
- **Filename format:** `YYYYMMDD-HHMMSS-pi.md`
- **Timestamp generation:** use your local timezone

---

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

**Local tooling:** `./bin/memory-bridge` wraps the stdlib Python CLI (`docs/cli.md`) for deterministic index rebuild (`index rebuild`), freshness (`check`), lexical `search` / `digest`, and `import --dry-run`. No embeddings/API keys required.

---

## Saving Conversations

When user says "save to memory bridge", "memory-bridge save", "save this conversation", or "save session":

### Step 1: Detect Repo
Check for `.cross-agent-memory` marker or git remote containing "memory-bridge"

### Step 2: Generate Timestamp
Use your local timezone

### Step 3: Create Directory
`conversations/YYYY/MM/DD/` (auto-create if missing)

### Step 4: Write File
`YYYYMMDD-HHMMSS-pi.md`

### Step 4.5: Check for Artifacts to Embed

**Check:** Did this session produce substantial research outputs, briefs, or documents?

**Embed if ANY true:**
- [ ] Research brief/report >1,500 words with narrative structure
- [ ] Analysis with data tables or structured findings
- [ ] Decision document with scenarios/options
- [ ] User explicitly says "embed this" or "include the brief"

**Do NOT embed if:**
- Simple code/config references (link the file path instead)
- Transient outputs (terminal logs, temporary results)
- Drafts the user wants to iterate on separately

**Action if embedding:**
1. Add artifact metadata to frontmatter `artifacts:` array
2. Insert `## Embedded Artifact: {Name}` section immediately before `## Next Steps / Follow-up`
3. Include artifact metadata header: File path, word count, status
4. Copy artifact content (condense if >3,000 words, noting "abridged")
5. Use clear section headers for scannability

### Embedded Artifact Format

```markdown
---

## Embedded Artifact: {Artifact Name}

**File:** `path/to/original.md`  
**Type:** {research-brief|analysis|decision-doc}  
**Word Count:** {count}  
**Status:** {draft/final/review}

### {Full artifact content here}

{Executive summary, sections, data tables, conclusions}

---
```

### Content Schema

```yaml
---
timestamp: "YYYY-MM-DDTHH:MM:SS+05:30"
agent_id: "pi"
agent_name: "Pi"
session_id: "optional-session-identifier"
user: "<YOUR_NAME>"
duration_minutes: 0
topics: ["topic1", "topic2"]
related_repos: []
related_sessions: []
artifacts: []  # Optional: list embedded artifacts
# keywords: []            # optional
# references: []         # optional
---

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

### Step 5: Git Workflow
Auto-commit and push:
```bash
git add {filepath}
git commit -m "memory(pi): {timestamp} - {brief-topic}"
git push origin main
```

**If artifact embedded:**
```bash
git add {filepath}
git commit -m "memory(pi): {timestamp} - {topic} [+artifact: {filename}]"
git push origin main
```

### Step 6: Confirm
"Saved to memory bridge: {filename}"

**No user confirmation needed for commit.**

---

## Boot Section

At session start, run `/memory-bridge-boot` or say "boot memory bridge":

1. Pulls latest from remote (`git pull origin main`)
2. Counts conversation files on disk (filenames only, no content reading)
3. Checks if memory-bridge skill is installed for this agent
4. Outputs readiness status

---

## Index Section

Run `/memory-bridge-index` or `./bin/memory-bridge index rebuild` ("rebuild memory index") once/day:

1. Pulls latest from remote
2. Scans all conversation frontmatter + bodies for open items
3. Writes `INDEX.md` to repo root (full rewrite)
4. Commits and pushes

Check freshness without rebuilding: `./bin/memory-bridge check`, `/memory-bridge-index check`, or "check memory index"

`INDEX.md` is machine-generated. Do not edit manually.

---

## Query Section

Run `/memory-bridge-digest {topic}` or "memory digest {topic}":

1. Checks `INDEX.md` exists (if not, run `/memory-bridge-index` first)
2. Checks index freshness (file count vs index entries)
3. Filters index entries by topic (**deterministic lexical + alias expansion**, `config/topic_aliases.json`; optional `./bin/memory-bridge digest` for the reference ranker)
4. Deep-reads only matching conversations (max 10)
5. Outputs: timeline, open items, cross-references, pending verdict

---

## Repo Reference

| File | Purpose |
|------|---------|
| `SKILL.md` | Canonical specification (schema, format, detection) |
| `INDEX.md` | Machine-generated conversation index (do not edit) |
| `bin/memory-bridge` | Deterministic CLI (search/index/import) |
| `docs/schema.md` | Required vs optional frontmatter |
| `docs/` | Index format + CLI/query/import/ops/agent contracts |
| `README.md` | Full documentation for humans and agents |
| `skills/` | Canonical skill definitions (install from here) |
| `templates/conversation.md` | Conversation file template |

---

## Auto-Load Note

This file (`.pi/PI.md`) should be read automatically when Pi Agent operates within the memory-bridge repository.
