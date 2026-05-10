---
name: memory-bridge
description: Save conversation summaries to the Agentic Memory Hub. Cross-agent conversation persistence.
---

# memory-bridge — Conversation Save Skill

**Purpose:** Save a structured conversation summary to the shared Agentic Memory Hub repository so all agents have visibility into what was discussed and decided.

**When to use:** User says "save to memory bridge", "memory-bridge save", "save this conversation", "save session", or "archive this".

---

## THE SIX DISTRIBUTED HUB SKILLS

| Skill | Trigger | Purpose |
|-------|---------|---------|
| **memory-bridge** (this skill) | "save to memory bridge" | Save a conversation to the repo |
| memory-bridge-boot | `/memory-bridge-boot` | Readiness check at session start |
| memory-bridge-index | `/memory-bridge-index` | Build or check the conversation index |
| memory-bridge-digest | `/memory-bridge-digest {topic}` | Query conversations by topic |
| memory-bridge-import | `/memory-bridge-import` | Import external conversations/transcripts |
| llm-wiki-compile | `/llm-wiki-compile {topic}` or `/llm-wiki-compile --auto` | Compile wiki synthesis articles |

All six distributed skills are defined in the repo's `skills/` directory — install from there.

---

## EXECUTION SEQUENCE

### Step 1: Verify Repo Detection

Confirm you are in the Agentic Memory Hub repo by checking ANY of:
- File `.cross-agent-memory` exists in repo root
- `SKILL.md` with `skill: memory-bridge` in its frontmatter
- Git remote URL contains `agentic-memory-hub`

If not detected: "I don't detect the memory-bridge repo. Are you in the right directory?" Stop.

### Step 2: Generate IST Timestamp

```bash
TZ=Asia/Kolkata date +"%Y%m%d-%H%M%S"
```

All agents use IST (UTC+5:30). No exceptions.

### Step 3: Create Directory Structure

```
conversations/YYYY/MM/DD/
```

Auto-create if missing.

### Step 4: Write Conversation File

Filename: `YYYYMMDD-HHMMSS-{agent_id}.md`

Replace `{agent_id}` with your agent identifier: opencode, claude, cursor, codex, pi, or hermes.

**Content format — YAML frontmatter + structured sections:**

```yaml
---
timestamp: "YYYY-MM-DDTHH:MM:SS+05:30"
agent_id: "{your_agent_id}"
agent_name: "{Your Agent Name}"
session_id: "{unique_session_identifier}"
user: "<YOUR_NAME>"
duration_minutes: {estimated}
topics: ["topic1", "topic2", "topic3"]
related_repos: ["repo1", "repo2"]
related_sessions: ["YYYYMMDD-HHMMSS-agent"]
artifacts: []  # Optional: list embedded artifacts
learnings: []  # Optional: 5-7 concise takeaways for coding agents (see below)
---

## Context
[2-3 sentences: where this happened, what triggered it, what was being worked on]

## Key Discussion Points
1. Point one
2. Point two
3. Point three

## Decisions Made
- [x] Decision finalized
- [ ] Decision pending

## Action Items
- [ ] Task description (with owner if not Yash)
- [x] Completed task (include for context)

## Code/Config References
- File paths discussed
- Repos referenced
- Commands or URLs relevant

## Next Steps / Follow-up
[What happens next, what to revisit, what to test]
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
4. Copy full artifact content (condense if >3,000 words, noting "abridged")
5. Use clear section headers for scannability

### Step 4.6: Add Learnings for Cross-Agent Visibility (Optional but Recommended)

**Purpose:** Distill the session's key takeaways into 5-7 concise items that coding agents can see at a glance in `INDEX.md` or frontmatter scans. Learnings capture _wisdom_ — what you learned the hard way so future agents don't have to.

**Categories of Learnings to Extract:**

| Category | Capture When... | Example |
|----------|-----------------|---------|
| **Introspection** | You recognized a pattern in your own behavior | "I tend to over-delegate rather than do direct work" |
| **Verification Failures** | You claimed something was checked but it wasn't | "Said 'verified' but only ran 1 test, not 3 required variations" |
| **Hallucination Prevention** | You asserted without evidence and were wrong | "Assumed MiniMax key was invalid after one failed model call" |
| **Tool/Method Gaps** | Your verification method was incomplete | "md5sum of single file missed subdirectory differences — need diff -r" |
| **User Correction Patterns** | User had to correct your approach | "User said 'TARGETED fixes only' — I was doing blanket changes" |
| **Fact-Discipline** | You learned importance of verification hierarchy | "Treat model knowledge as STALE until tool-verified" |
| **Process/Workflow** | Technique emerged that future sessions need | "Use browser-research BEFORE parallel-search per user preference" |
| **Anti-Pattern Recognition** | You identified something _not_ to do | "Never say 'it probably failed because...' without testing" |

**When to include:**
- [ ] Session produced genuine learning from any category above
- [ ] Mistake was made and lesson was extracted
- [ ] User explicitly wants future agents to know this without reading full body
- [ ] Technique emerged that future sessions would benefit from

**Do NOT include if:**
- Routine session with no new insights
- Information is already obvious from topics
- Just summarizing what was done (that's what body sections are for)
- Generic advice like "be careful" or "double check"

**Extraction Process:**
1. Review the conversation for moments where you were corrected, failed, or learned
2. Ask: "What would I tell a new agent to prevent this?"
3. Convert to concise, actionable statement
4. Limit to 5-7 — force prioritization

**Format:**
```yaml
learnings: [
  "Skill sync requires full directory tree, not just SKILL.md",
  "Verify with diff -r, not just md5sum, to catch missing files",
  "User challenges signal verification gaps - stop and re-verify"
]
```

**Style guidelines:**
- Concise (under 100 chars each)
- Actionable (future agent can apply immediately)
- Specific (not "be careful" but "check references/ subdirectory")
- Starts with verb when possible (Verify, Check, Ask, Never, Always)
- Max 5-7 items (force prioritization of what actually matters)

**Bad vs Good Examples:**

| Bad (too vague) | Good (specific, actionable) |
|-----------------|------------------------------|
| "Be more careful" | "Check subdirectories with ls -la before declaring sync complete" |
| "Verify things" | "When user challenges verification, re-run all checks fresh" |
| "Don't make mistakes" | "Parity check 'DRIFT' means investigate WHAT drifted before assuming content" |
| "Test more" | "Test 3+ model names before declaring API key failure" |

**Example from real session (verification failure):**
Session where I claimed skills were "identical" after md5sum but missed reference files:
```yaml
learnings: [
  "Skill sync requires full directory tree, not just SKILL.md",
  "Verify directory structure with diff -r or ls -la, not just md5sum",
  "User challenges signal verification gaps - stop and re-verify everything",
  "Parity check drift means investigate WHAT drifted: content vs missing files",
  "Reference files in subdirectories often missed during syncs"
]
```

### Step 5: Auto-Commit and Push

```bash
git add {filepath}
git commit -m "memory({agent_id}): {YYYYMMDD-HHMMSS} - {brief_topic}"
git push origin main
```

No user confirmation needed for commit. Show what was saved, including any embedded artifacts.

**Commit message format if artifact embedded:**
```bash
git commit -m "memory({agent_id}): {YYYYMMDD-HHMMSS} - {topic} [+artifact: {filename}]"
```

If push fails: stage locally, notify user to sync manually.

---

## AUTO-COMMIT RULES

- Auto-commit: enabled (these are context conversations, not code)
- Auto-push: enabled if remote configured
- No user confirmation needed for commit (but show what was saved)

---

## ERROR HANDLING

| Situation | Response |
|-----------|----------|
| Not in repo | "I don't detect the memory-bridge repo. Are you in the right directory?" |
| Git not initialized | Initialize git, create initial commit |
| Push fails | Stage locally, notify user to sync manually |
| Directory creation fails | Check permissions, report error |
| PR includes conversation file deletions/modifications | **STOP.** Review carefully. Use `references/clean-merge-pattern.md` to cherry-pick only code changes. Never merge deletions of conversation files. |

|---

## REFERENCES

- `references/artifact-embedding-pattern.md` — When and how to embed research artifacts directly in conversations for self-contained documentation.
- `references/learnings-field-pattern.md` — How to use the `learnings` frontmatter field for cross-agent visibility of distilled session takeaways.
- `references/mcp-server-architecture.md` — MCP server setup with dual-port configuration (SSE on :8080, Streamable HTTP on :8081) for Tailscale-connected agents.
- `references/clean-merge-pattern.md` — How to salvage good code from PRs that accidentally modify conversation files or mix unrelated changes.

---

## RELATIONSHIP TO OTHER SKILLS

- **memory-bridge-boot**: Lightweight readiness check at session start. Run before saving if you haven't booted yet. Includes MCP endpoint verification.
- **memory-bridge-index**: Builds the searchable index from saved conversations. Run after saving to update the index.
- **memory-bridge-digest**: Topic-based queries across saved conversations. Depends on the index being built.
- **memory-bridge-import**: Imports external conversation exports (Claude, ChatGPT, etc.) into Memory Bridge format.
