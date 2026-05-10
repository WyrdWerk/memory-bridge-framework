# Conversation schema (canonical)

Hub conversation files live under `conversations/YYYY/MM/DD/*.md`.

## Required YAML frontmatter

| Field | Type | Notes |
|-------|------|--------|
| `timestamp` | string | IST offset, e.g. `2026-05-03T14:02:00+05:30` |
| `agent_id` | string | One of: `cursor`, `claude`, `codex`, `opencode`, , `pi`, `hermes`, `import` |
| `agent_name` | string | Human label for the agent surface |
| `user` | string | Owner of the hub (`<YOUR_NAME>` in your repo) |
| `duration_minutes` | int | Estimated session length |
| `topics` | list of strings | Stable topic tags |
| `related_repos` | list of strings | Repo slugs referenced |
| `related_sessions` | list of strings | Other session filenames (stem or full id) |

`session_id` is **recommended** whenever the exporting surface exposes a durable id.

## Optional YAML (recommended for search & imports)

| Field | Type | Purpose |
|-------|------|--------|
|| `keywords` | list of strings | Extra lexical hooks for index/search beyond `topics` |
|| `learnings` | list of strings | Concise takeaways for coding agents (max 5-7 items) |
|| `references` | list of strings | URLs or external refs (comma-safe strings) |
| `status` | string | e.g. `draft`, `final` — purely informational |
| `source_agent_surface` | string | Provenance: `cursor`, `chatgpt-export`, etc. |
| `imported_at` | string | When this file was ingested (IST ISO string) |
| `import_source` | string | Path or label of the source export |
| `saved_by` | string | Importer/writer label for provenance consistency |

## Body sections (required headings)

Use the headings in `templates/conversation.md`:

- `## Context`
- `## Key Discussion Points`
- `## Decisions Made`
- `## Action Items`
- `## Code/Config References`
- `## Next Steps / Follow-up`

Checklist lines `- [ ]` / `- [x]` **outside** fenced code blocks are parsed for open-item counts in `INDEX.md`.

## Import-only headings

Imported conversations may include these additional headings:

- `## Imported source`
- `## Imported verbatim`
- `## Conversation`

## Validation

- Malformed or missing frontmatter: index build logs a warning and skips the file (see `scripts/memory_bridge/parse_conv.py`).
- Filename must end with `-{agent_id}.md` and match directory date when possible.
