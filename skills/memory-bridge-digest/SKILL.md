---
name: memory-bridge-digest
description: Topic-based query across all conversations in the Agentic Memory Hub. Uses INDEX.md for fast filtering, then deep-reads only matching conversations for open items, decisions, and cross-references.
---

# memory-bridge-digest — Topic Query Engine

**Purpose:** Query all conversations in the Agentic Memory Hub by topic. Uses the pre-built INDEX.md for fast filtering, then deep-reads only matching conversations to extract open items, decisions, and cross-references.

**When to use:** User says `/memory-bridge-digest {topic}` or "memory digest {topic}" or "what's the status on {topic} across agents" or "show me pending items about {topic}"

---

## EXECUTION SEQUENCE

### Step 1: Check INDEX.md Exists

Read `INDEX.md` from the repo root.

If not found:
```
⚠️ No INDEX.md found. Run /memory-bridge-index to build it first.
```
Stop here. Do not fall back to scanning all conversations.

### Step 2: Freshness Check

```
🔍 VERIFYING — Index freshness
```

1. Count conversation files on disk: glob `conversations/**/*.md`
2. Count entries in INDEX.md (from the summary table or `Total conversations` header)
3. Compare:

- **Equal** → Fresh. Proceed.
- **Disk > Index** → Stale. Warn: "⚠️ Index is stale — {N} conversations not indexed. Results may be incomplete. Run /memory-bridge-index for a full rebuild." Proceed with available data.
- **Disk < Index** → Anomaly. Warn: "⚠️ Index has more entries than files on disk. Files may have been deleted." Proceed anyway.

### Step 3: Candidate selection (deterministic lexical + aliases)

This step must remain **offline and reproducible**:

1. Stem/tokenize the user’s topic fragments (mirror the lexical assumptions documented in `docs/cli.md` / `./bin/memory-bridge`).
2. Load `config/topic_aliases.json` (if missing, skip). Each alias key injects its list values as bonus match stems (deterministic synonym expansion — **not** neural similarity).
3. Score INDEX.md conversations using their `topics`, optional `Keywords` column, related repo names surfaced in excerpts, filenames, checklist counts (for prioritisation only), plus the textual `Excerpt:` lines inside `## Entries`.
4. **Tie-breakers:** Higher lexical score wins; if tied, prefer more recent timestamps (`Date`).
5. **`./bin/memory-bridge digest …`** emits the authoritative ranked ordering when shells are available — interactive agents SHOULD match its ordering whenever users care about reproducibility.

**Forbidden:** embeddings APIs, latent “semantic search,” or nondeterministic model calls solely to rank candidates.

**If zero matches:**
```
📭 No conversations found matching "{topic}".
- Try broader or different keywords
- Check INDEX.md topics for available terms
- Run /memory-bridge-index if the index might be stale
```
Stop.

**If more than 10 matches:**
```
⚠️ {N} conversations match "{topic}". Deep-reading the top 10 by lexical rank (Step 3). Narrow your topic for focused results.
```
Proceed with only the highest scoring 10 candidates from Step 3.

### Step 4: Deep-Read Matching Conversations

```
🔍 READING — {N} matching conversations
```

Read the full contents of each matching conversation file. Extract:
- **Open items:** Every `- [ ]` action item and pending decision
- **Completed items:** Every `- [x]` (for context on what's already done)
- **Cross-session references:** Any `related_sessions` values — check if those session files exist on disk
- **Key discussion points:** Brief extraction of what was discussed

### Step 5: Output Structured Digest

```
📋 DIGEST — "{topic}"
```

#### Matching Conversations
| # | Date | Agent | Open Items |
|---|------|-------|------------|
| 1 | 2026-05-01 | claude | 4 |
| ... | ... | ... | ... |

#### Open Items
Every incomplete action item and pending decision from matching conversations, grouped by conversation:

**Conversation: {date} — {agent} — {topics}**
- [ ] Item one
- [ ] Item two
- [x] Item completed (for context)

**Conversation: {date} — {agent} — {topics}**
- [ ] Item one
...

#### Cross-Session References
| Reference | Source | Found? |
|-----------|--------|--------|
| 20260501-181916-hermes | 20260501-182836-hermes | ✓ / ✗ |

#### Pending Verdict
One-line summary of what's still unresolved on this topic across all matching conversations.

---

## ANTI-BLOAT RULES

- Never read more than 10 conversations in a single digest. Cap it.
- If zero matches, stop. Don't scan everything.
- Output focuses on open items and pending decisions. Not a full re-rendering of conversation contents.
- Keep the pending verdict to one line. If you can't summarize in one line, the topic is too broad.
- Cross-session reference checks are lightweight — just verify the file exists, don't read it.

---

## ERROR HANDLING

| Situation | Response |
|-----------|----------|
| INDEX.md not found | Tell user to run /memory-bridge-index first. Stop. |
| Index is stale | Warn, proceed with available data. Don't auto-rebuild. |
| Zero topic matches | Suggest broader keywords. Stop. |
| >10 matches | Cap at 10. Warn user to narrow topic. |
| Conversation file missing from disk | Skip it. Flag in cross-references as "file missing". |
| Conversation file has no open items | Still include in matching conversations table. Note "0 open items". |

---

## RELATIONSHIP TO OTHER SKILLS

- **memory-bridge-index** (build): This skill depends on INDEX.md. Run index build at least once before using digest.
- **memory-bridge** (save): Writes the conversation files that digest queries. No direct interaction.
- **memory-bridge-boot**: Lightweight readiness check. Doesn't check index. If user wants topic details after boot, they run this skill.
