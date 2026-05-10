# Import workflows

Goal: turn arbitrary exports into **canonical conversation files** using `./bin/memory-bridge import`.

## Common flags

- `--agent-id` — stored in YAML and filename suffix (`-codex.md`, etc.).
- `--format generic` — raw markdown or plain text blob into `## Context` (default).
- `--dry-run` — print document only.

## Claude / Cursor / Codex / OpenCode

Usually already markdown-ish: paste or save as `.md`, then:

```bash
./bin/memory-bridge import ./exports/session.md --agent-id claude --dry-run
```

Review frontmatter (`source_agent_surface`, `imported_at`) then drop `--dry-run`.

## ChatGPT web exports

Save the HTML-as-text or copy transcript to `.txt` / `.md`. Use `import`; body lands under Context. Manually split **Action Items** / **Decisions** into checklist sections afterward if the export lacked structure.

```bash
```

## Manual markdown

Hand-authored notes: prefer filling `topics` / `keywords` in frontmatter before `index rebuild` so lexical search catches them.

## After import

```bash
./bin/memory-bridge index rebuild
git add conversations/ INDEX.md
git commit -m "memory(import): …"
git push origin main
```

See `importers/spec.md` for filename and field conventions.
