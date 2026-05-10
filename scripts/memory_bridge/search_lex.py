"""Deterministic lexical search over conversations — no embeddings."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .parse_conv import glob_conversations, parse_conversation


def load_aliases(repo_root: Path) -> dict[str, list[str]]:
    p = repo_root / "config" / "topic_aliases.json"
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        if str(k).startswith("_"):
            continue
        kk = str(k).strip().lower()
        out[kk] = [str(x) for x in v] if isinstance(v, list) else [str(v)]
    return out


def expand_terms(query: str, aliases: dict[str, list[str]]) -> set[str]:
    q_raw = query.lower().replace(",", " ")
    base: set[str] = set()
    for chunk in re.split(r"\s+", q_raw.strip()):
        w = re.sub(r"[^a-z0-9_-]", "", chunk)
        if len(w) >= 2:
            base.add(w)
    terms = set(base)
    ql = query.lower()
    for alias_key, synonyms in aliases.items():
        if alias_key in ql:
            terms.add(alias_key)
            terms.update(str(s).lower() for s in synonyms)
    for tok in list(base):
        if tok in aliases:
            terms.update(str(s).lower() for s in aliases[tok])
    return {t for t in terms if len(t) >= 2}


def search_conversations(repo_root: Path, query: str, limit: int = 25) -> list[tuple[float, str]]:
    terms = sorted(expand_terms(query, load_aliases(repo_root)), key=len, reverse=True)
    # Scoring rationale (deterministic, no embeddings):
    #   70  — normalized stem in filename (strongest signal: agent/date match)
    #   48  — raw substring in filename
    #   35  — substring in metadata (topics/keywords/repos/checklists)
    #    8  — substring in body text (weakest: false-positive-prone)
    ranked: list[tuple[float, str]] = []
    for rel in sorted(glob_conversations(repo_root)):
        pc = parse_conversation(repo_root, rel)
        stem_lc = Path(rel).stem.lower()
        meta_parts = [stem_lc]
        for key in ("topics", "keywords", "related_repos"):
            lst = pc.frontmatter.get(key)
            if isinstance(lst, list):
                meta_parts.extend(str(x).lower() for x in lst)
        meta_parts.extend(x.lower() for x in pc.open_actions)
        meta_parts.extend(x.lower() for x in pc.open_decisions)
        meta_blob = "\n".join(meta_parts)
        body_lc = (pc.body_text or "").lower()
        score = 0.0
        for nt in terms:
            plain_nt = nt.replace("-", "").replace("_", "")
            stem_plain = stem_lc.replace("-", "").replace("_", "")
            if plain_nt and plain_nt in stem_plain:
                score += 70
            elif nt in stem_lc:
                score += 48
            if nt in meta_blob:
                score += 35
            if nt in body_lc:
                score += 8
        ranked.append((score, rel))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [(s, rel) for s, rel in ranked if s > 0][:limit]
