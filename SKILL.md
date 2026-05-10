---
skill: memory-bridge
version: 1.0.0
description: Cross-agent conversation persistence system
author: <YOUR_NAME>
---

## Purpose

Save conversation summaries to a shared Git repository so all AI agents have
visibility into what <YOUR_NAME> is working on across platforms.

## Supported Agents

- hermes (Hermes Agent)
- cursor (Cursor IDE)
- claude (Claude Code CLI)
- codex (OpenAI Codex CLI)
- opencode (OpenCode CLI)
- 
- pi (Pi Agent)
- droid (Factory Droid) — Config in `.factory/DROID.md`, skills in `.factory/skills/`, MCP in `.factory/mcp.json`

## Detection Methods

Agents MUST detect this repo via ANY of:
1. Git remote URL contains "agentic-memory-hub"
2. File `.cross-agent-memory` exists in repo root
3. Parent directory contains `SKILL.md` with `skill: memory-bridge`

## Trigger Command

User says ANY of:
- "save to memory bridge"
- "memory-bridge save"
- "save this conversation"
- "save session"
- "archive this"

## File Structure

```
conversations/{YYYY}/{MM}/{DD}/{YYYYMMDD-HHMMSS}-{agent-id}.md
```

- Timezone: IST (UTC+5:30) — all agents use this
- `agent-id`: hermes, cursor, claude, codex, opencode, pi
- Auto-create folder structure if missing

## Content Format

```yaml
---
timestamp: "2025-05-01T17:55:30+05:30"
agent_id: "hermes"
agent_name: "Hermes Agent"
session_id: "discord-1499747716165664828"
user: "<YOUR_NAME>"
duration_minutes: 45
topics: ["repo-design", "cross-agent-memory", "skill-architecture"]
related_repos: ["signal-gestalt-kb", "silverbullet-vault"]
related_sessions: ["20250501-143022-cursor"]
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
- [ ] Task for Yash
- [ ] Task for agent X

## Code/Config References
- File paths discussed
- Repos referenced

## Next Steps / Follow-up
[What happens next]
```

### Optional YAML (for lexical search)

These fields improve deterministic retrieval (still **no embeddings**):

- `keywords` — extra tags beyond `topics`
- `learnings` — concise takeaways for coding agents (e.g., `["Skill sync requires full directory tree", "Verify with diff -r not just md5sum"]`)
- `references` — URLs / external identifiers (short strings)
- `status`, `source_agent_surface`, `import_source`, `imported_at` — provenance metadata (especially imports)

See `docs/schema.md` for the full canonical list.

### Index regeneration

Prefer `./bin/memory-bridge index rebuild` (writes tracked `INDEX.md`; optional `.index/` cache is gitignored by default — see `docs/index-format.md`).

## Workflow

1. User triggers: "save to memory bridge"
2. Agent analyzes conversation context (available history)
3. Generates structured summary per template above
4. Determines filename from current IST timestamp + agent_id
5. Creates directory structure if needed
6. Writes markdown file
7. Stages file: `git add {filepath}`
8. Commits: `git commit -m "memory({agent}): {YYYYMMDD-HHMMSS} - {brief_topic}"`
9. Pushes: `git push origin main` (if remote configured)

## Auto-Commit Rules

- [x] Commit automatically (these are context conversations, not code)
- [x] Push to origin if remote configured
- [x] No user confirmation needed for commit (but show what was saved)

## Error Handling

- If not in repo: "I don't detect the memory-bridge repo. Are you in the right directory?"
- If git not initialized: Initialize git, create initial commit
- If push fails: Stage locally, notify user to sync manually
