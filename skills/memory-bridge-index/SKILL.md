---
name: memory-bridge-index
description: Build or check the Memory Bridge conversation index. Rebuild scans all conversations and writes INDEX.md. Check mode verifies freshness without modifying anything.
---

# memory-bridge-index — Conversation Index Builder

**Purpose:** Build or verify a searchable index of all conversations in the Agentic Memory Hub. The index enables topic-based querying without reading every conversation file on every query.

**When to use:**
- `/memory-bridge-index` or `/memory-bridge-index rebuild` or "rebuild memory index" — full rebuild
- `/memory-bridge-index check` or "check memory index" — freshness check only

---

## REBUILD MODE

### Step 0: Repo Detection

Confirm you are in the Memory Bridge repo by checking ANY of:
- File `.cross-agent-memory` exists in repo root
- `SKILL.md` with `skill: memory-bridge` in its frontmatter
- Git remote URL contains `memory-bridge`

**If detected:** Proceed to Step 1 (local index path).

**If not detected:** Proceed to Step 0B (MCP index path).

---

### Step 0B: MCP Index Path (Cross-Repo Rebuild)

If the repo is not local, check if your agent has the `memory-bridge` MCP server configured.

**If MCP is available:**
- For full rebuild: Call `rebuild_index`. The server rebuilds `INDEX.md` and commits/pushes automatically.
- For freshness check only: Call `check_index`. Returns disk count vs index entries.

No local file operations needed.

**If neither repo nor MCP available:** "I don't detect the memory-bridge repo and no MCP server is configured. Navigate to the repo or configure MCP per `AGENTS.md`."

Stop.

---

### Step 1: Sync with Remote

```bash
git pull origin main
```

If no remote configured:
```bash
git remote add origin https://github.com/<YOUR_USERNAME>/memory-bridge-framework.git
git pull origin main
```

Verify on `main` branch and up to date.

### Step 2: Scan All Conversations

```
🔍 INDEXING — Scanning conversations
```

Glob for `conversations/**/*.md`. For each file:

1. Read the YAML frontmatter (everything between the `---` delimiters). Extract:
   - `timestamp`
   - `agent_id`
   - `topics`
   - `related_sessions`
   - `duration_minutes`

2. Scan the body (everything after the closing `---`) for open items. Count lines matching:
   - `- [ ]` (incomplete action items)
   - `- [ ]` in Decisions Made sections
   - Do NOT count `[ ]` inside code blocks or inline code.

3. If frontmatter is missing or malformed: log a warning, skip the entry, continue.

**Deterministic CLI (preferred path):** When the repo provides `./bin/memory-bridge`, run `./bin/memory-bridge index rebuild` immediately after syncing. That command regenerates tracked `INDEX.md` and optionally refreshes gitignored `.index/` manifests + per-conversation sidecars without external services.

Agents that cannot execute shell SHOULD still emulate the scan rules below when manually rebuilding.

### Step 3: Generate INDEX.md

Write `INDEX.md` to the repo root with this human-facing layout (tracked in Git):

```markdown
# Memory Bridge Index

Last rebuilt: {ISO 8601 IST timestamp}
Total conversations: N
Conversations with open items: M

| # | Date | Agent | Topics | Keywords | Open | File |
|---|------|-------|--------|----------|------|------|
| 1 | 2026-05-01 | hermes | cross-agent-memory, repo-design | memory-bridge, docs | 3 | conversations/2026/05/01/20260501-181916-hermes.md |

## Entries

### 1. 2026-05-01 — hermes — cross-agent-memory, repo-design
- File: `conversations/2026/05/01/20260501-181916-hermes.md`
- Topics: cross-agent-memory, repo-design, memory-bridge
- Keywords: memory-bridge, docs
- Open items: 3
- Related sessions: (none)
- Excerpt: First lines from the `## Context` section ...

### 2. ...
```

Emit optional `.index/manifest.json` + `.index/conversations/*.json` ONLY when tooling needs offline hashes/metadata. `.index/` SHOULD remain gitignored to avoid noisy commits.

**Rules for INDEX.md:**
- Summary table at top listing every conversation (`Keywords` column echoes optional `keywords` YAML).
- `## Entries` repeats metadata + Context excerpt snippet (still not full body storage).
- Sorted chronologically ascending (mirror builder output).
- Full rewrite — never incremental.
- Paths relative to repo root.

### Step 4: Commit and Push

```bash
git add INDEX.md
git commit -m "index: rebuild — {N} conversations indexed, {M} with open items"
git push origin main
```

If push fails: report error, index is saved locally.

### Step 5: Report

```
✅ INDEX REBUILT
- Conversations indexed: {N}
- With open items: {M}
- INDEX.md pushed to main
```

---

## CHECK MODE

### Step 1: Check INDEX.md Exists

If `INDEX.md` not found in repo root:
```
⚠️ No INDEX.md found. Run /memory-bridge-index to build it.
```
Stop.

### Step 2: Count Conversations on Disk

Glob for `conversations/**/*.md` and count files.

### Step 3: Count Entries in INDEX.md

Read INDEX.md. Count entries in the summary table.

### Step 4: Compare and Report

```
📊 INDEX STATUS
- Conversations on disk: {disk_count}
- Conversations in index: {index_count}
- Status: {FRESH / STALE}
- Missing from index: {diff_count}
- Last rebuilt: {timestamp from INDEX.md header}
```

If `disk_count > index_count`:
```
⚠️ STALE — {diff_count} conversations not in index. Run /memory-bridge-index to rebuild.
```

If `disk_count == index_count`:
```
✅ FRESH — Index matches disk. No rebuild needed.
```

If `disk_count < index_count`:
```
⚠️ ANOMALY — Index has more entries than files on disk. Files may have been deleted. Run /memory-bridge-index to rebuild.
```

No files modified. No commits. No pushes.

**Optional precision path:** `./bin/memory-bridge index check --json` compares manifest hashes stored under gitignored `.index/` (when present) against current blobs whenever you need cryptographic certainty beyond row counts.

---

## ERROR HANDLING

| Situation | Response |
|-----------|----------|
| Not in memory-bridge repo, no MCP | "I don't detect the memory-bridge repo and no MCP server is configured. Navigate to the repo or configure MCP per AGENTS.md." |
| Not in repo, MCP available | Use MCP index path (Step 0B) |
| Git pull fails | Report error. Continue with local state. |
| Conversation file has no frontmatter | Log warning, skip entry, continue. |
| Conversation file has malformed frontmatter | Log warning, skip entry, continue. |
| Push fails | Report error. Index saved locally. User can push manually. |
| Zero conversations found | "No conversations found. INDEX.md created with 0 entries." |

---

## RELATIONSHIP TO OTHER SKILLS

- **memory-bridge** (save): Writes conversation files. Does NOT update INDEX.md. That's intentional — the index is rebuilt periodically, not incrementally.
- **memory-bridge-boot**: Lightweight readiness check. Optionally run `./bin/memory-bridge check` after boot when you need deterministic freshness telemetry.
- **memory-bridge-digest**: Queries INDEX.md for topic-based filtering. Depends on this skill having been run at least once.

---

## ANTI-BLOAT RULES

- Full rewrite every time. No incremental updates.
- Index stores metadata + **short Context excerpts** (not full bodies) + open item counts.
- Open item text is NOT stored inline in INDEX.md rows; pull verbatim `- [ ]` lines only when deep-reading the conversation for digest/output.
- Keep INDEX.md shape stable — digest/search skills parse the predictable headers.
