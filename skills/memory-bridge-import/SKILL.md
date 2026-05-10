---
name: memory-bridge-import
description: Import conversations from AI platform exports into the Agentic Memory Hub. Supports ChatGPT JSON, Cursor SQLite, Perplexity Markdown, and generic Markdown with auto-detection.
---

# memory-bridge-import — Conversation Import Skill

**Purpose:** Import conversation exports from external AI platforms into the Agentic Memory Hub's canonical format. Auto-detects the source format and produces structured Markdown files with proper provenance, ready for indexing and cross-agent visibility.

**When to use:** User says "import conversations", "import ChatGPT export", "import from Cursor", "import Perplexity thread", or provides an export file/directory to ingest.

---

## SUPPORTED FORMATS

| Format | Detection | Source | Notes |
|--------|-----------|--------|-------|
| **ChatGPT JSON** | `.json` with `"mapping"` key | OpenAI data export ZIP | Follows active branch, extracts model info |
| **Cursor SQLite** | `.vscdb`, `.db`, `.sqlite` | `state.vscdb` in workspace storage | Reads chat tabs + composer sessions |
| **Perplexity Markdown** | `.md` with `**Question:**` markers | Native export button | Q&A pair extraction |
| **Generic Markdown** | `.md`, `.markdown`, `.txt` | Browser extensions (YourAIScroll, etc.) | Role detection from heading patterns |
| **Raw text fallback** | Any text file | Anything else | Verbatim import, no structure |

---

## EXECUTION SEQUENCE

### Step 1: Verify Repo Detection

Confirm you are in the Agentic Memory Hub repo by checking ANY of:
- File `.cross-agent-memory` exists in repo root
- `SKILL.md` with `skill: memory-bridge` in its frontmatter
- Git remote URL contains `agentic-memory-hub`

If not detected: "I don't detect the memory-bridge repo. Are you in the right directory?" Stop.

### Step 2: Identify the Export Format

If the user specifies the format explicitly, use it. Otherwise, auto-detect:

| Signal | Detected Format |
|--------|----------------|
| `.json` file containing `"mapping"` | `chatgpt-json` |
| `.vscdb` / `.db` / `.sqlite` file | `cursor-sqlite` |
| `.md` file with `**Question:**` or `**Answer:**` | `perplexity-md` |
| `.md` / `.markdown` / `.txt` file | `generic-md` |
| Unrecognized | raw text fallback |

### Step 3: Dry Run First

**Always** run a dry run before writing files:

```bash
./bin/memory-bridge import {path} --dry-run --agent-id import
```

If the CLI is not available, simulate: list the files that would be created without writing them.

Show the user what will be imported:
- Number of conversations detected
- Format detected
- Output filenames
- Any warnings (empty conversations, parse errors)

### Step 4: Import

```bash
./bin/memory-bridge import {path} --agent-id import
```

**Agent ID choices:**
- `import` — default for third-party exports (ChatGPT, Perplexity, generic)
- `cursor` — for Cursor SQLite exports (these are native Memory Bridge agent data)

Format flag (optional, overrides auto-detection):
```bash
./bin/memory-bridge import {path} --format chatgpt-json --agent-id import
./bin/memory-bridge import {path} --format cursor-sqlite --agent-id cursor
./bin/memory-bridge import {path} --format perplexity-md --agent-id import
./bin/memory-bridge import {path} --format generic --agent-id import
```

### Step 5: Post-Import Workflow

After files are written:

1. **Rebuild the index:**
   ```bash
   ./bin/memory-bridge index rebuild
   ```

2. **Commit and push:**
   ```bash
   git add conversations/ INDEX.md
   git commit -m "memory(import): {N} conversations from {format}"
   git push origin main
   ```

3. **Report results:**
   ```
   ✅ IMPORT COMPLETE
   - Source: {path}
   - Format: {detected_format}
   - Conversations imported: {N}
   - Files written: {list}
   - Index rebuilt: yes
   ```

---

## PLATFORM-SPECIFIC NOTES

### ChatGPT (OpenAI)

1. Export from https://chat.openai.com/settings → "Export data" (takes ~24h via email)
2. Unzip the export, locate `conversations.json`
3. Import:
   ```bash
   ./bin/memory-bridge import ./conversations.json --format chatgpt-json --agent-id import
   ```

**Behavior:** Each conversation becomes a separate file. The parser follows the `current_node` branch (not the full mapping tree), so you get the active conversation thread, not all branches. Model info (e.g., `gpt-4o`) is preserved.

### Cursor IDE

1. Locate the database:
   ```bash
   # Linux
   find ~/.config/Cursor/User/workspaceStorage -name "state.vscdb"
   ```
2. Import:
   ```bash
   ./bin/memory-bridge import ./state.vscdb --format cursor-sqlite --agent-id cursor
   ```

**Behavior:** Reads chat tabs and composer sessions. Empty composer shells are skipped. Close Cursor before importing to avoid database locks.

### Perplexity

1. Export from any thread → "Export" → Markdown
2. Import:
   ```bash
   ./bin/memory-bridge import ./thread-export.md --format perplexity-md --agent-id import
   ```

### Browser Extensions

1. Export from YourAIScroll, AI Exporter, etc.
2. Import:
   ```bash
   ./bin/memory-bridge import ./export.md --format generic --agent-id import
   ```

---

## IMPORT OUTPUT FORMAT

All imports produce canonical Memory Bridge files:

```yaml
---
timestamp: "2026-05-04T12:00:00+05:30"
agent_id: "import"
agent_name: "Imported (import)"
session_id: "import-20260504-120000-abc123"
user: "<YOUR_NAME>"
duration_minutes: 0
topics: ["chatgpt", "conversation-import"]
keywords: []
related_repos: []
related_sessions: []
import_source: "/path/to/export.json"
imported_at: "2026-05-04T12:00:00+05:30"
source_format: "chatgpt-json"
saved_by: "memory-bridge-import"
source_agent_surface: "chatgpt-export"
---

## Context
Imported from `chatgpt`: Conversation title

## Imported source
- Source platform: `chatgpt`
- Import source: `/path/to/export.json`
- Original ID: `conv-abc123`
- Messages extracted: 5

## Key Discussion Points
1. (Imported conversation — review and extract key points.)

## Decisions Made
- [ ] Review imported conversation and extract decisions.

## Action Items
- [ ] Review imported conversation.
- [ ] Normalize topics (current: chatgpt, conversation-import).

## Code/Config References
- Import source: `/path/to/export.json`

## Conversation

**User**:
```
Message content here
```

**Assistant** (gpt-4o):
```
Response content here
```

## Next Steps / Follow-up
- Re-run `memory-bridge index rebuild` after editing.
```

---

## ERROR HANDLING

| Situation | Response |
|-----------|----------|
| Not in repo | "I don't detect the memory-bridge repo. Are you in the right directory?" |
| File not found | "Source file not found: {path}" |
| Parse error on binary file | Report error, skip file, set exit code 1 |
| Parse error on text file | Fall back to raw text import |
| Cursor DB locked | "Close Cursor before importing to avoid database locks." |
| Empty export | "No conversations found in {path}." |
| Bulk import with partial failures | Report per-file status, continue with remaining files |

---

## BULK IMPORT

For multiple files:

```bash
# All JSON exports
for f in ~/Downloads/exports/*.json; do
  ./bin/memory-bridge import "$f" --format chatgpt-json --agent-id import
done

# All Cursor workspaces
for db in ~/.config/Cursor/User/workspaceStorage/*/state.vscdb; do
  ./bin/memory-bridge import "$db" --format cursor-sqlite --agent-id cursor
done
```

After bulk import, run a single index rebuild:
```bash
./bin/memory-bridge index rebuild
```

---

## ANTI-BLOAT RULES

- Always dry-run first. Show what will be created before writing.
- Message content uses fenced code blocks. If a message contains triple backticks, the fence is automatically widened (4+ backticks) to prevent malformed output.
- Imported conversations include placeholder checklists (`- [ ] Review imported conversation`). Agents or humans should normalize these after import.
- Do not import the same file twice. Check existing conversations before importing to avoid duplicates.

---

## RELATIONSHIP TO OTHER SKILLS

- **memory-bridge** (save): Writes live conversation summaries. This skill writes imported conversations from external sources.
- **memory-bridge-index**: Must run after import to update INDEX.md with the new conversations.
- **memory-bridge-boot**: Verifies repo readiness before import. Run if unsure about repo state.
- **memory-bridge-digest**: Query imported conversations by topic after the index is rebuilt.
