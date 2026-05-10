# Import spec

## Output shape

Every imported conversation produces one canonical file:

`conversations/YYYY/MM/DD/YYYYMMDD-HHMMSS-{agent_id}.md`

With YAML frontmatter per `docs/schema.md` and body sections from `templates/conversation.md`.

## Minimum viable body

Raw imports fill `## Context` with the source text. Structured imports may also add a `## Conversation` section with extracted messages. Human or agent SHOULD normalize checklists (`## Action Items`, `## Decisions Made`) after import.

## Provenance fields (optional YAML)

Use when transcribing exports:

```yaml
source_agent_surface: "chatgpt-export"
import_source: "path/or/label"
imported_at: "2026-05-03T…+05:30"
keywords: ["import", "migration"]
```

## Dry run

Always preview:

```bash
./bin/memory-bridge import ./path/to/export.txt --agent-id cursor --dry-run
```
