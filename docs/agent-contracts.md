# Agent contracts (deterministic hub)

## No hidden semantics

Core Memory Bridge behaviors **must not** rely on:

- Embedding APIs or remote LLMs for ranking/search
- Extra API keys for indexing or digest

Ranking is **lexical** (stem overlap + optional aliases in `config/topic_aliases.json`).

## Source of truth

| Artifact | Role |
|---------|------|
| `SKILL.md` | Canonical save schema & workflow |
| `templates/conversation.md` | Paste template |
| `INDEX.md` | Generated summary + entries |
| `.index/` | Optional local cache (gitignored default) |
| `bin/memory-bridge` | Reference implementation for index/search/check |

## Skills

- **memory-bridge-index**: Prefer `./bin/memory-bridge index rebuild` when available; otherwise mirror scan rules and write `INDEX.md` format in `docs/index-format.md`.
- **memory-bridge-digest**: Candidate selection uses **lexical + aliases**, not latent “semantic similarity.”
- **memory-bridge-boot**: Optional `./bin/memory-bridge check` after pull for fast freshness, plus read-only `skill-parity` and `mcp-check` when you need readiness verification.

## Imports

Preserve provenance via `source_agent_surface`, `import_source`, `imported_at` optional fields (`docs/schema.md`).
