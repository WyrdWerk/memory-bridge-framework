# Query examples (deterministic)

## Freshness

```bash
./bin/memory-bridge check
./bin/memory-bridge index check --json
```

## Search broad terms

```bash
./bin/memory-bridge search memory bridge workflow --limit 10
```

## Digest-style focused topic

```bash
./bin/memory-bridge digest claude codex skill --limit 5
```

## Find a filename fragment

```bash
./bin/memory-bridge show 20260501-
```

## After importing or saving many files

```bash
git pull origin main   # optional, your workflow
./bin/memory-bridge index rebuild
./bin/memory-bridge check
```

Agents doing “memory digest {topic)” without the CLI should: verify `INDEX.md` exists → freshness check → pick candidates via lexical + alias expansion → deep-read top N (cap 10).
