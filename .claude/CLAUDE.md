# Memory Bridge — Claude Code Agent Instructions

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

When user says "save to memory bridge", "save this conversation", "archive this", or "save session":

1. **Detect repo** — check for `.cross-agent-memory` marker or git remote containing "memory-bridge"
2. **Generate timestamp** — use your local timezone (default: Asia/Kolkata IST)
3. **Create directory** — `conversations/YYYY/MM/DD/` (auto-create if missing)
4. **Write file** — `YYYYMMDD-HHMMSS-claude.md`
5. **Content** — structured markdown with YAML frontmatter per `SKILL.md` and `templates/conversation.md`
6. **Git workflow** — auto-commit and push:
   ```bash
   git add {filepath}
   git commit -m "memory(claude): {timestamp} - {brief-topic}"
   git push origin main
   ```
   
   **If artifact embedded:**
   ```bash
   git commit -m "memory(claude): {timestamp} - {topic} [+artifact: {filename}]"
   ```
7. **Confirm** — "Saved to memory bridge: {filename}"

No user confirmation needed for commit.

### Content Schema

```yaml
---
timestamp: "YYYY-MM-DDTHH:MM:SS+05:30"
agent_id: "claude"
agent_name: "Claude Code"
session_id: "optional-session-identifier"
user: "<YOUR_NAME>"
duration_minutes: 0
topics: ["topic1", "topic2"]
related_repos: []
related_sessions: []
artifacts: []  # Optional: list embedded artifacts
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

## MCP Server Connection

The Memory Bridge MCP server can run centrally for all agents. Claude Code connects via SSE or Streamable HTTP.

### MCP Configuration

Add to your Claude Code MCP config (`~/.claude/mcp_servers.json`):

**Streamable HTTP (recommended):**
```json
{
  "mcpServers": {
    "memory-bridge": {
      "type": "http",
      "url": "http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp"
    }
  }
}
```

**SSE (legacy fallback):**
```json
{
  "mcpServers": {
    "memory-bridge": {
      "url": "http://<YOUR_VPS_TAILSCALE_IP>:8080/sse"
    }
  }
}
```

### Verification

After configuring, restart Claude Code and verify connection:
```bash
./bin/memory-bridge mcp-check --transport streamable-http --url http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp
```

## Agent Identity

- agent_id: `claude`
- Filename: `YYYYMMDD-HHMMSS-claude.md`
- Auto-loads: This file (`.claude/CLAUDE.md`) is read automatically when you `cd` into this repo
