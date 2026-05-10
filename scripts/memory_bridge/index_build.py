"""Build INDEX.md plus machine-readable `.index/` manifests from conversations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .parse_conv import glob_conversations, parse_conversation

IST = timezone(timedelta(hours=5, minutes=30))
SCHEMA_VERSION = 1


def _topics_line(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(x) for x in val if x is not None)
    return "" if val is None else str(val)


def _date_row(ts_val: str | None, rel_path: str) -> str:
    if isinstance(ts_val, str) and len(ts_val) >= 10:
        chunk = ts_val[:10]
        try:
            datetime.strptime(chunk, "%Y-%m-%d")
            return chunk
        except ValueError:
            pass
    parts = Path(rel_path).parts
    if len(parts) >= 4:
        yyyy, mm, dd = parts[1], parts[2], parts[3]
        try:
            datetime.strptime(f"{yyyy}-{mm}-{dd}", "%Y-%m-%d")
            return f"{yyyy}-{mm}-{dd}"
        except ValueError:
            pass
    return "unknown"


def _context_excerpt(markdown_body: str, max_chars: int = 380) -> str:
    text = markdown_body.replace("\r\n", "\n")
    capture = False
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip().lower()
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            if title == "context":
                capture = True
                lines = []
            else:
                capture = False
            continue
        if capture and stripped:
            lines.append(line.strip())
    full = " ".join(lines).strip()
    return (full[: max_chars - 3] + "...") if len(full) > max_chars else full


def build_index(repo_root: Path, *, write_sidecars: bool = True) -> dict:
    rebuilt = datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")
    rel_paths = sorted(glob_conversations(repo_root))
    idx_dir = repo_root / ".index"
    idx_conv = idx_dir / "conversations"

    hashes: dict[str, str] = {}

    rows: list[dict] = []

    if write_sidecars:
        idx_dir.mkdir(parents=True, exist_ok=True)
        idx_conv.mkdir(parents=True, exist_ok=True)
        for stale in idx_conv.glob("*.json"):
            stale.unlink()

    for rel in rel_paths:
        blob = (repo_root / rel).read_bytes()
        hashes[rel] = hashlib.sha256(blob).hexdigest()
        pc = parse_conversation(repo_root, rel)
        date_disp = _date_row(pc.timestamp, rel)

        topics = pc.frontmatter.get("topics") if isinstance(pc.frontmatter.get("topics"), list) else []
        keywords = pc.frontmatter.get("keywords") if isinstance(pc.frontmatter.get("keywords"), list) else []
        related_repos = (
            pc.frontmatter.get("related_repos") if isinstance(pc.frontmatter.get("related_repos"), list) else []
        )
        related_sessions = (
            pc.frontmatter.get("related_sessions") if isinstance(pc.frontmatter.get("related_sessions"), list) else []
        )
        references = (
            pc.frontmatter.get("references") if isinstance(pc.frontmatter.get("references"), list) else []
        )

        tl = _topics_line(topics)
        kl = _topics_line(keywords)
        excerpt = _context_excerpt(pc.body_text)
        open_items = len(pc.open_actions) + len(pc.open_decisions)

        side = {
            "schema_version": SCHEMA_VERSION,
            "rel_path": rel,
            "sha256_hex_full": hashes[rel],
            "agent_id": pc.agent_id,
            "session_label": pc.session_label,
            "timestamp": pc.timestamp,
            "date": date_disp,
            "topics": topics,
            "topics_line": tl,
            "keywords": keywords,
            "keywords_line": kl,
            "related_repos": related_repos,
            "related_sessions": related_sessions,
            "references": references,
            "status": pc.frontmatter.get("status"),
            "source_agent_surface": pc.frontmatter.get("source_agent_surface"),
            "open_item_count": open_items,
            "open_actions_text": pc.open_actions,
            "open_decisions_text": pc.open_decisions,
            "warnings": pc.warnings,
            "body_excerpt": excerpt,
            "parsed_frontmatter": dict(pc.frontmatter),
        }

        if write_sidecars:
            fname = "__".join(Path(rel).as_posix().split("/"))
            if fname.endswith(".md"):
                fname = fname[:-3] + ".json"
            else:
                fname += ".json"
            (idx_conv / fname).write_text(
                json.dumps(side, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

        rows.append(
            {
                "parsed": pc,
                "date_disp": date_disp,
                "topics_line": tl,
                "keywords_line": kl,
                "open_items_count": open_items,
                "body_excerpt": excerpt,
            }
        )

    open_cnt = sum(1 for rr in rows if rr["open_items_count"] > 0)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "rebuilt_at_ist": rebuilt,
        "conversation_count": len(rows),
        "conversations_with_open_items": open_cnt,
        "content_sha256_by_rel_path": hashes,
    }
    if write_sidecars:
        (idx_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    outs: list[str] = []
    outs += [
        "# Memory Bridge Index",
        "",
        f"Last rebuilt: {rebuilt}",
        f"Total conversations: {len(rows)}",
        f"Conversations with open items: {open_cnt}",
        "",
        "| # | Date | Agent | Topics | Keywords | Open | File |",
        "|---|------|-------|--------|----------|------|------|",
    ]
    for i, row in enumerate(rows, start=1):
        pc = row["parsed"]
        agent = pc.agent_id or "unknown"
        topics_cell = row["topics_line"].replace("|", "\\|")
        kw_cell = row["keywords_line"].replace("|", "\\|")
        outs.append(
            f"| {i} | {row['date_disp']} | {agent} | {topics_cell} | {kw_cell} | "
            f"{row['open_items_count']} | {pc.rel_path} |"
        )

    outs += ["", "## Entries", ""]
    for i, row in enumerate(rows, start=1):
        pc = row["parsed"]
        head_topics = row["topics_line"] or "(no topics)"
        outs.append(f"### {i}. {row['date_disp']} — {pc.agent_id or 'unknown'} — {head_topics}")
        outs.append(f"- File: `{pc.rel_path}`")
        outs.append(f"- Topics: {row['topics_line'] or '(none)'}")
        outs.append(f"- Keywords: {row['keywords_line'] or '(none)'}")
        outs.append(f"- Open items: {row['open_items_count']}")

        rs = pc.frontmatter.get("related_sessions")
        if isinstance(rs, list) and rs:
            outs.append("- Related sessions: " + ", ".join(str(x) for x in rs))
        else:
            outs.append("- Related sessions: (none)")
        excerpt = row["body_excerpt"]
        outs.append(f"- Excerpt: {excerpt}" if excerpt else "- Excerpt: (none)")
        outs.append("")

    (repo_root / "INDEX.md").write_text("\n".join(outs).rstrip() + "\n", encoding="utf-8")

    return {
        "rebuilt_at_ist": rebuilt,
        "conversation_count": len(rows),
        "with_open_items": open_cnt,
    }
