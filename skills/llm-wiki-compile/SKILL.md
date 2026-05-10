---
name: llm-wiki-compile
description: Compile conversations into LLM Wiki synthesis articles. Topic-based knowledge compilation with automatic change detection.
---

# llm-wiki-compile — LLM Wiki Compilation Engine

**Purpose:** Compile selected conversations from `raw/` sources into synthesized `wiki/` articles. Supports both manual topic-specific compilation and automatic multi-topic detection.

**When to use:**
- `/llm-wiki-compile {topic}` — Compile specific topic immediately
- `/llm-wiki-compile --auto` — Auto-detect and compile all topics with new material
- User says: "compile wiki", "update wiki", "ingest conversations into wiki"

---

## COMPILATION MODES

### Mode 1: Manual Topic Compilation

```
/llm-wiki-compile mcp
/llm-wiki-compile vps
/llm-wiki-compile privacy
```

**Use when:** You want a specific topic compiled immediately, regardless of thresholds.

### Mode 2: Automatic Multi-Topic Detection

```
/llm-wiki-compile --auto
```

**Use when:** Running via cron or scheduled task. Skill decides what needs updating.

**Detection logic:**
1. Read `wiki/.registry.yaml` (tracks last compile state per topic)
2. Scan `conversations/` for files matching each topic's keywords
3. Compare source hashes against registry
4. Compile topics where: `new_sources >= threshold` (default: 2)

---

## TOPIC REGISTRY

**File:** `wiki/.registry.yaml` (git-tracked)

```yaml
# LLM Wiki Topic Registry
# Auto-updated by llm-wiki-compile skill

version: "1.0"
last_auto_compile: "2026-05-08T15:30:00+05:30"

topics:
  mcp:
    name: "Model Context Protocol"
    keywords: ["mcp", "mcp-server", "fastmcp", "model-context-protocol"]
    threshold: 2
    raw_dir: "raw/mcp"
    wiki_dir: "wiki/mcp"
    last_compile: "2026-05-08T14:40:59+05:30"
    sources_since_last_compile:
      - conversations/2026/05/06/20260506-160859-opencode.md
      - conversations/2026/05/06/20260506-172115-hermes.md
      - conversations/2026/05/06/20260506-205647-codex.md
    status: "compiled"
    wiki_article: "wiki/mcp/memory-bridge-mcp-server.md"

  vps:
    name: "VPS Deployment Patterns"
    keywords: ["vps", "deployment", "ubuntu", "systemd", "tailscale"]
    threshold: 3
    raw_dir: "raw/vps"
    wiki_dir: "wiki/vps"
    last_compile: null
    sources_since_last_compile: []
    status: "pending_sources"
    wiki_article: null

  privacy:
    name: "Privacy & Security Evaluations"
    keywords: ["privacy", "security", "data-retention", "compliance", "audit"]
    threshold: 2
    raw_dir: "raw/privacy"
    wiki_dir: "wiki/privacy"
    last_compile: null
    sources_since_last_compile: []
    status: "pending_sources"
    wiki_article: null
```

**Status values:**
- `pending_sources` — Not enough conversations yet (threshold not met)
- `ready_to_compile` — Threshold met, awaiting compilation
- `compiled` — Successfully compiled
- `stale` — New sources available since last compile

---

## EXECUTION SEQUENCE

### Step 1: Detect Mode

```python
if user_input contains "--auto":
    mode = "auto"
else:
    mode = "manual"
    topic = user_input.split()[0]  # First word is topic
```

### Step 2: Verify Repository

Check for Agentic Memory Hub repo:
- `.cross-agent-memory` exists
- `skills/llm-wiki-compile/SKILL.md` exists (this file)
- `raw/` and `wiki/` directories exist

If missing: Create directories or abort with instructions.

### Step 3: Load or Initialize Registry

```bash
if [ -f wiki/.registry.yaml ]; then
    load_registry()
else:
    create_default_registry()
```

### Step 4: Source Detection (Auto Mode)

For each topic in registry:

```bash
# Find conversations matching topic keywords
matching_convs=$(grep -l -E "$(keywords_joined_by_pipe)" conversations/**/*.md)

# Check which are newer than last_compile
for conv in $matching_convs; do
    conv_timestamp=$(extract_from_frontmatter timestamp)
    if conv_timestamp > topic.last_compile:
        topic.sources_since_last_compile.append(conv)
done

# Update status
if len(topic.sources_since_last_compile) >= topic.threshold:
    topic.status = "ready_to_compile"
```

### Step 5: Compilation (Both Modes)

For each topic to compile:

**Step 5a: Copy to raw/**
```bash
# Copy conversations to raw/{topic}/ with metadata headers
for source in topic.sources_since_last_compile:
    target="raw/{topic}/{date}-{slug}.md"
    add_metadata_header(source, target)
```

**Metadata header format:**
```yaml
---
source: conversations/YYYY/MM/DD/YYYYMMDD-HHMMSS-agent.md
collected: 2026-05-08T15:30:00+05:30
published: 2026-05-06
author: agent
topics: [t1, t2, t3]
---
```

**Step 5b: Synthesize wiki article**

Read all raw/ sources for topic, generate:

```markdown
---
title: {Topic Name}
created: {first_compile_date}
updated: {current_date}
topic: {topic_slug}
sources: |
  Source 1 (date); Source 2 (date); ...
raw: |
  ../../raw/{topic}/file1.md; ../../raw/{topic}/file2.md; ...
---

## Overview
[2-3 sentence synthesis of what this topic covers]

## Key Decisions
[Table: Decision | Context | Source]

## Implementation Details
[Technical specifics from sources]

## Action Items (Cross-Session)
[Aggregated - [ ] items from all sources]

## Related Sessions
[Table: Date | Agent | Topic | File]

## See Also
[Links to related wiki articles]

---
*Last compiled: {date} from {N} source conversations*
```

**Step 5c: Cascade Updates**

For each related topic (from See Also):
- Check if this new compilation affects their content
- If yes: Mark related topic as "stale" for next auto-compile

**Step 5d: Update wiki/index.md**

Add or update entry:
```markdown
| {topic} | [{article}]({path}) | {1-line summary} | {date} |
```

**Step 5e: Log operation**

Append to `wiki/log.md`:
```markdown
## [{date}] compile | {topic}/{article}

**Source:** {N} conversations
**Action:** Compiled new article / Updated existing
**Files created/modified:**
- raw/{topic}/*.md
- wiki/{topic}/*.md
- wiki/index.md

**Key decisions captured:**
- [Decision 1]
- [Decision 2]

**Cascade updates:** {none | list of related topics marked stale}
```

### Step 6: Update Registry

```yaml
# Mark as compiled
topics.{topic}.last_compile: {current_timestamp}
topics.{topic}.status: "compiled"
topics.{topic}.sources_since_last_compile: []  # Clear the queue
topics.{topic}.wiki_article: "wiki/{topic}/{slug}.md"

# If auto mode, update global timestamp
if mode == "auto":
    last_auto_compile: {current_timestamp}
```

### Step 7: Commit and Push

```bash
git add raw/ wiki/ wiki/.registry.yaml
git commit -m "wiki({topic}): compile {N} sources into {article}

- Ingest: {N} conversations
- Compile: wiki/{topic}/{article}.md
- Cascade: {updates or 'none'}
- Registry: updated"

git push origin main
```

### Step 8: Report

```
✅ WIKI COMPILE COMPLETE

Mode: {manual/auto}
Topic: {topic}
Sources compiled: {N}
Output: wiki/{topic}/{article}.md
Lines compressed: {source_lines} → {wiki_lines} ({pct}%)

Next steps:
- Related topics awaiting compilation: {list or 'none'}
- Registry updated: wiki/.registry.yaml
- Changes pushed: {commit_hash}
```

---

## ANTI-BLOAT RULES

- **No full conversation storage in wiki/** — Only synthesis + citations
- **No auto-compile on every save** — Batch by threshold or schedule
- **No manual raw/ edits** — Always copy from conversations with metadata
- **No orphan wiki articles** — Every article must have ≥2 raw sources

---

## RELATIONSHIP TO OTHER SKILLS

| Skill | This Skill Uses It | Uses This Skill |
|-------|-------------------|-----------------|
| memory-bridge | ✅ Reads conversations | ❌ No |
| memory-bridge-boot | ❌ No | ✅ Can trigger --auto mode |
| memory-bridge-index | ✅ Uses INDEX.md for topic search | ❌ No |
| memory-bridge-digest | ❌ No | ✅ Can use for topic discovery |

---

## REFERENCE FILES

- `references/topic-registry-schema.yaml` — Full registry schema
- `references/compilation-template.md` — Wiki article template
- `references/cascade-update-rules.md` — When to mark related topics stale

---

## VERSION

**Skill version:** 1.0.0
**Compatible with:** Agentic Memory Hub v2.0+
**Required repo structure:** raw/, wiki/, wiki/.registry.yaml
