"""Parse hub conversation markdown: SKILL.md-compatible frontmatter + checklists."""

from __future__ import annotations

import re
from ast import literal_eval
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedConversation:
    rel_path: str
    agent_id: str | None = None
    timestamp: str | None = None
    session_label: str | None = None
    frontmatter: dict[str, Any] = field(default_factory=dict)
    open_actions: list[str] = field(default_factory=list)
    open_decisions: list[str] = field(default_factory=list)
    closed_actions: list[str] = field(default_factory=list)
    closed_decisions: list[str] = field(default_factory=list)
    body_text: str = ""
    warnings: list[str] = field(default_factory=list)


def agent_from_filename(rel_path: str) -> str | None:
    stem = Path(rel_path).stem
    if "-" not in stem:
        return None
    return stem.rsplit("-", 1)[-1]


def session_label_from_path(rel_path: str) -> str:
    return Path(rel_path).stem


def _parse_inline_list(blob: str) -> list[Any]:
    blob = blob.strip()
    try:
        v = literal_eval(blob)
        if isinstance(v, list):
            return v
    except (SyntaxError, ValueError):
        pass
    return []


def _parse_fm_value(rest: str) -> Any:
    rest = rest.strip()
    if not rest:
        return None
    if rest.startswith("[") and rest.endswith("]"):
        return _parse_inline_list(rest)
    if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in {'"', "'"}:
        return rest[1:-1]
    if rest.isdigit():
        return int(rest)
    return rest


def parse_simple_frontmatter(fm_lines: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Handles key: value, inline lists [...], and block-style YAML lists (- item per line)."""
    warns: list[str] = []
    fm: dict[str, Any] = {}
    pending_list_key: str | None = None
    for ln in fm_lines:
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Block-style list continuation: "  - value" or "- value"
        if pending_list_key is not None and stripped.startswith("- "):
            val = stripped[2:].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
                val = val[1:-1]
            fm[pending_list_key].append(val)
            continue
        pending_list_key = None
        if ":" not in stripped:
            warns.append(f"Skipping unparsed fm line: {stripped[:100]}")
            continue
        k, _, rv = stripped.partition(":")
        k = k.strip()
        rv = rv.strip()
        if rv == "":
            fm[k] = []
            pending_list_key = k
            continue
        fm[k] = _parse_fm_value(rv)

    return fm, warns


def split_frontmatter(text: str) -> tuple[list[str], str]:
    """Return (frontmatter inner lines without delimiters, body). Empty fm if none."""
    t = text.replace("\r\n", "\n")
    if not t.startswith("---\n"):
        return [], t

    end = t.find("\n---\n", 4)
    if end == -1:
        return [], t

    inner = t[4:end].strip("\n").split("\n")
    body = t[end + len("\n---\n") :]
    return inner, body


def glob_conversations(repo_root: Path) -> list[str]:
    conversations = repo_root / "conversations"
    paths: list[str] = []

    def walk(d: Path) -> None:
        for p in sorted(d.iterdir()):
            if p.name.startswith("."):
                continue
            if p.is_dir():
                walk(p)
            elif p.suffix.lower() == ".md":
                paths.append(p.relative_to(repo_root).as_posix())

    if conversations.is_dir():
        walk(conversations)

    return sorted(paths)


def parse_conversation(repo_root: Path, rel_path: str) -> ParsedConversation:
    full_path = repo_root / rel_path
    text = full_path.read_text(encoding="utf-8", errors="replace")
    fm_lines, body = split_frontmatter(text)

    warns: list[str] = []
    fm: dict[str, Any] = {}
    if fm_lines:
        fm, w2 = parse_simple_frontmatter(fm_lines)
        warns.extend(w2)
    else:
        warns.append("missing_frontmatter_fence")

    ai = fm.get("agent_id")
    pc = ParsedConversation(
        rel_path=rel_path,
        frontmatter=dict(fm),
        warnings=warns,
        body_text=body,
    )

    pc.agent_id = ai.strip() if isinstance(ai, str) else agent_from_filename(rel_path)
    ts = fm.get("timestamp")
    pc.timestamp = ts.strip() if isinstance(ts, str) else None
    sid = fm.get("session_id")
    pc.session_label = sid.strip() if isinstance(sid, str) else session_label_from_path(rel_path)

    in_fence = False
    sect_lower = ""

    for raw_line in body.split("\n"):
        trimmed = raw_line.strip()
        if trimmed.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        lower = trimmed.lower()
        if trimmed.startswith("#"):
            sect_lower = lower
            continue

        m_chk = re.match(r"^\s*-\s*\[([ xX])\]\s*(.*)$", raw_line)
        if not m_chk:
            continue
        done_flag = (m_chk.group(1).strip().lower() == "x")
        item_text = (m_chk.group(2) or "").strip()
        decisions_section = ("decisions made" in sect_lower)

        bucket_open = pc.open_decisions if decisions_section else pc.open_actions
        bucket_closed = pc.closed_decisions if decisions_section else pc.closed_actions
        if done_flag:
            bucket_closed.append(item_text)
        else:
            bucket_open.append(item_text)

    return pc
