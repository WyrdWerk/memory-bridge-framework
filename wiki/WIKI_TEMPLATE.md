# LLM Wiki — Compilation Template

The LLM Wiki is an optional compounding knowledge layer built on top of the Memory Bridge conversation store. It synthesizes related conversations into structured articles.

## What Gets Compiled

The `llm-wiki-compile` skill:
1. Scans `raw/{topic}/` for source material (conversation excerpts, research notes)
2. Extracts concepts, decisions, and patterns
3. Generates a structured article in `wiki/{topic}/`
4. Updates `wiki/.registry.yaml` with compilation metadata

## Article Template

```markdown
---
title: "Topic Name"
created: YYYY-MM-DD
updated: YYYY-MM-DD
topic: topic-name
---

## Overview

One-paragraph summary of what this article covers.

**Key insight:** The single most important takeaway.

## Core Principles

| Principle | Implementation |
|-----------|----------------|
| ... | ... |

## Decisions Made

- [x] Decision finalized
- [ ] Decision pending

## References

- Source: `raw/topic/YYYY-MM-DD-source.md`
- Related conversations: `conversations/YYYY/MM/DD/YYYYMMDD-HHMMSS-agent.md`
```

## Workflow

```
1. Conversations saved to conversations/YYYY/MM/DD/
2. Raw excerpts compiled to raw/{topic}/
3. llm-wiki-compile {topic} synthesizes wiki/{topic}/article.md
4. .registry.yaml tracks compilation state
```

## Registry

Topic definitions live in `wiki/.registry.yaml`:

```yaml
version: "1.0"
topics:
  example-topic:
    name: "Example Topic"
    keywords: ["example", "topic"]
    threshold: 2
    raw_dir: "raw/example-topic"
    wiki_dir: "wiki/example-topic"
    status: "template"
```

To add a topic, edit `.registry.yaml`, create the `raw/` and `wiki/` directories, then run `/llm-wiki-compile {topic}`.
