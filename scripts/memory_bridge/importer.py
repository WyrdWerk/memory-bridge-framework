"""Normalize exported chat blobs into canonical conversation Markdown (stdlib only)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .parsers import (
    ChatGPTJsonParser,
    Conversation,
    CursorSQLiteParser,
    GenericMdParser,
    PerplexityMdParser,
    detect_format,
)

IST = timezone(timedelta(hours=5, minutes=30))


def sanitize_agent_id(agent_id: str) -> str:
    slug = "".join(ch for ch in agent_id.strip() if ch.isalnum() or ch in "-_").lower()
    allowed = {"hermes", "cursor", "claude", "codex", "opencode", "pi", "import"}
    if slug in allowed:
        return slug
    return slug[:48] if slug else "import"


def _format_ist_timestamp(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _normalize_timestamp(value: str | None, fallback: datetime) -> str:
    if not value:
        return _format_ist_timestamp(fallback)
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return _format_ist_timestamp(fallback)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _format_ist_timestamp(parsed)


def _format_metadata_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def _role_label(role: str) -> str:
    role_key = (role or "").strip().lower()
    if role_key == "user":
        return "**User**"
    if role_key == "assistant":
        return "**Assistant**"
    if role_key == "system":
        return "**System**"
    return f"**{role_key.title() or 'Message'}**"


def _source_agent_surface(source: str) -> str:
    mapping = {
        "chatgpt": "chatgpt-export",
        "cursor": "cursor-export",
        "perplexity": "perplexity-export",
        "generic": "generic-md-export",
    }
    return mapping.get(source, f"{source}-export")


def _safe_code_fence(content: str) -> tuple[str, str]:
    """Return (opening_fence, closing_fence) that won't break on internal backticks."""
    if "```" not in content:
        return "```", "```"
    n = 3
    while "`" * n in content:
        n += 1
    fence = "`" * n
    return fence, fence


def format_conversation_to_markdown(
    conv: Conversation,
    *,
    agent_id: str,
    import_source: str,
    source_format: str,
    output_dt: datetime,
    hub_user: str = "<YOUR_NAME>",
) -> tuple[Path, str]:
    """Convert a parsed conversation into a canonical Memory Bridge document."""
    aid = sanitize_agent_id(agent_id)
    output_dt_ist = output_dt.astimezone(IST)
    stamp = output_dt_ist.strftime("%Y%m%d-%H%M%S")
    y, m, d = output_dt_ist.strftime("%Y"), output_dt_ist.strftime("%m"), output_dt_ist.strftime("%d")
    out_rel = Path("conversations") / y / m / d / f"{stamp}-{aid}.md"

    import_source_safe = (import_source.strip() or "(unknown)").replace('"', "'")
    iso_ts = _normalize_timestamp(conv.created_at, output_dt)

    message_lines = []
    for msg in conv.messages:
        role_label = _role_label(msg.role)
        if msg.model:
            role_label += f" ({msg.model})"
        open_fence, close_fence = _safe_code_fence(msg.content)
        message_lines.append(role_label + ":")
        message_lines.append(open_fence)
        message_lines.append(msg.content)
        message_lines.append(close_fence)
        message_lines.append("")
    if not message_lines:
        message_lines.extend(
            [
                "**System**:",
                "```",
                "(No message content could be extracted from the source export.)",
                "```",
                "",
            ]
        )

    topics = [conv.source, "conversation-import"]
    title_lower = conv.title.lower()
    topic_keywords = {
        "research": "research",
        "code": "coding",
        "bug": "debugging",
        "debug": "debugging",
        "plan": "planning",
        "design": "design",
        "review": "review",
        "test": "testing",
    }
    for keyword, topic in topic_keywords.items():
        if keyword in title_lower and topic not in topics:
            topics.append(topic)

    metadata_summary = [
        f"- {key}: `{_format_metadata_value(value)}`"
        for key, value in conv.metadata.items()
    ]

    sections = "\n".join(
        [
            "## Context",
            f"Imported from `{conv.source}`: {conv.title}",
            "",
            "## Imported source",
            "",
            f"- Source platform: `{conv.source}`",
            f"- Import source: `{import_source_safe}`",
            f"- Original ID: `{conv.id}`",
            f"- Messages extracted: {len(conv.messages)}",
            *metadata_summary,
            "",
            "## Key Discussion Points",
            "1. (Imported conversation — review and extract key points.)",
            "",
            "## Decisions Made",
            "- [ ] Review imported conversation and extract decisions.",
            "",
            "## Action Items",
            "- [ ] Review imported conversation.",
            f"- [ ] Normalize topics (current: {', '.join(topics)}).",
            "",
            "## Code/Config References",
            f"- Import source: `{import_source_safe}`",
            "",
            "## Conversation",
            "",
            *message_lines,
            "## Next Steps / Follow-up",
            "- Re-run `memory-bridge index rebuild` after editing.",
            "",
        ]
    )

    fm = "\n".join(
        [
            "---",
            f'timestamp: "{iso_ts}"',
            f'agent_id: "{aid}"',
            f'agent_name: "Imported ({aid})"',
            f'session_id: "import-{stamp}-{conv.id[:16]}"',
            f'user: "{hub_user}"',
            "duration_minutes: 0",
            f'topics: {json.dumps(topics)}',
            "keywords: []",
            "related_repos: []",
            "related_sessions: []",
            f'import_source: "{import_source_safe}"',
            f'imported_at: "{_format_ist_timestamp(output_dt)}"',
            f'source_format: "{source_format}"',
            'saved_by: "memory-bridge-import"',
            f'source_agent_surface: "{_source_agent_surface(conv.source)}"',
            "---",
            "",
            sections,
        ]
    )

    return out_rel, fm + "\n"


def make_import_document(
    source_text: str,
    *,
    agent_id: str,
    imported_from: str,
    source_format_hint: str,
    saved_by_note: str = "memory-bridge-import",
    hub_user: str = "<YOUR_NAME>",
) -> tuple[Path, str]:
    """Legacy import for raw text (no structured parsing)."""
    dt = datetime.now(tz=IST)
    y, m, d = dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")
    stamp = dt.strftime("%Y%m%d-%H%M%S")
    aid = sanitize_agent_id(agent_id)

    out_rel = Path("conversations") / y / m / d / f"{stamp}-{aid}.md"
    iso = dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")

    src = (imported_from.strip() or "(unknown)").replace('"', "'")
    fmt = (source_format_hint.strip() or "unspecified").replace('"', "'")
    by = saved_by_note.replace('"', "'")

    body = source_text.replace("\r\n", "\n").strip("\n")

    fenced = "```\n" + body + ("\n" if body else "") + "```"

    sections = "\n".join(
        [
            "## Context",
            "Imported via `memory-bridge import`. Topics and structure need human review.",
            "",
            "## Imported source",
            "",
            f"- Imported from: `{src}`",
            f"- Source format: `{fmt}`",
            f"- Saved-by note: `{by}`",
            "",
            "## Key Discussion Points",
            "1. (Edit after import — replace with extracted bullets.)",
            "",
            "## Decisions Made",
            "- [ ] (none inferred)",
            "",
            "## Action Items",
            "- [ ] Review and normalize this imported conversation.",
            "",
            "## Code/Config References",
            f"- Source path: `{src}`",
            "",
            "## Next Steps / Follow-up",
            "- Re-run `memory-bridge index rebuild` after editing.",
            "",
            "## Imported verbatim",
            "",
            fenced,
            "",
        ]
    )

    fm = "\n".join(
        [
            "---",
            f'timestamp: "{iso}"',
            f'agent_id: "{aid}"',
            f'agent_name: "Imported ({aid})"',
            f'session_id: "import-{stamp}-{aid}"',
            f'user: "{hub_user}"',
            "duration_minutes: 0",
            'topics: ["import", "conversation-import"]',
            "keywords: []",
            "related_repos: []",
            "related_sessions: []",
            f'import_source: "{src}"',
            f'imported_at: "{iso}"',
            f'source_format: "{fmt}"',
            f'saved_by: "{by}"',
            'source_agent_surface: "import-cli"',
            "---",
            "",
            sections,
        ]
    )

    return out_rel, fm


def import_with_format_detection(
    path: Path,
    agent_id: str,
    format_hint: str | None = None,
    base_dt: datetime | None = None,
    hub_user: str = "<YOUR_NAME>",
) -> Iterator[tuple[Path, str]]:
    """Import file with automatic format detection and parsing."""
    fmt = format_hint or detect_format(path)
    base_dt = base_dt or datetime.now(tz=IST)

    if fmt == "chatgpt-json":
        parser = ChatGPTJsonParser()
        conversations = parser.parse(path)
    elif fmt == "cursor-sqlite":
        parser = CursorSQLiteParser()
        conversations = parser.parse(path)
    elif fmt == "perplexity-md":
        parser = PerplexityMdParser()
        conversations = iter([parser.parse(path)])
    elif fmt in ("generic", "generic-md", "unknown"):
        parser = GenericMdParser()
        conversations = iter([parser.parse(path)])
    else:
        content = path.read_text(encoding="utf-8", errors="replace")
        yield make_import_document(
            content,
            agent_id=agent_id,
            imported_from=str(path.resolve()),
            source_format_hint=fmt,
            hub_user=hub_user,
        )
        return

    import_source = str(path.resolve())
    for idx, conv in enumerate(conversations):
        yield format_conversation_to_markdown(
            conv,
            agent_id=agent_id,
            import_source=import_source,
            source_format=fmt,
            output_dt=base_dt + timedelta(seconds=idx),
            hub_user=hub_user,
        )
