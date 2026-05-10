"""Format parsers for AI platform exports (stdlib only)."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str | None = None
    model: str | None = None


@dataclass
class Conversation:
    id: str
    title: str
    created_at: str | None
    messages: list[ChatMessage]
    source: str  # platform name
    metadata: dict


class ParseError(Exception):
    pass


class ChatGPTJsonParser:
    """Parse OpenAI ChatGPT JSON export format."""

    def parse(self, path: Path) -> Iterator[Conversation]:
        blob = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Invalid ChatGPT JSON export: {exc}") from exc

        if isinstance(data, list):
            conversations = data
        elif isinstance(data, dict) and isinstance(data.get("conversations"), list):
            conversations = data["conversations"]
        else:
            raise ParseError("Invalid ChatGPT export: expected conversation list")

        for conv in conversations:
            if not isinstance(conv, dict):
                continue
            yield self._parse_conversation(conv)

    def _parse_conversation(self, conv: dict) -> Conversation:
        title = conv.get("title", "Untitled")
        create_time = conv.get("create_time")
        mapping = conv.get("mapping", {})
        current_node = conv.get("current_node")

        messages = self._extract_messages(mapping, current_node)

        return Conversation(
            id=conv.get("id", "unknown"),
            title=title,
            created_at=self._timestamp_to_iso(create_time) if create_time else None,
            messages=messages,
            source="chatgpt",
            metadata={
                "conversation_id": conv.get("id"),
                "current_node": current_node,
            },
        )

    def _extract_messages(self, mapping: dict, current_node: str | None) -> list[ChatMessage]:
        ordered_nodes = self._ordered_nodes(mapping, current_node)
        messages: list[ChatMessage] = []
        for msg_data in ordered_nodes:
            msg = msg_data.get("message")
            if not msg:
                continue

            author = msg.get("author", {})
            role = author.get("role", "unknown")
            text = self._content_to_text(msg.get("content", {}))
            if not text.strip():
                continue

            ts = msg.get("create_time")
            ts_iso = self._timestamp_to_iso(ts) if ts else None

            messages.append(
                ChatMessage(
                    role=role,
                    content=text,
                    timestamp=ts_iso,
                    model=msg.get("metadata", {}).get("model_slug"),
                )
            )

        messages.sort(key=lambda m: m.timestamp or "")
        return messages

    def _ordered_nodes(self, mapping: dict, current_node: str | None) -> list[dict]:
        if current_node and current_node in mapping:
            node_chain: list[dict] = []
            seen: set[str] = set()
            node_id = current_node
            while node_id and node_id in mapping and node_id not in seen:
                seen.add(node_id)
                node = mapping[node_id]
                node_chain.append(node)
                parent = node.get("parent")
                node_id = parent if isinstance(parent, str) else None
            node_chain.reverse()
            return node_chain
        return list(mapping.values())

    def _content_to_text(self, content: object) -> str:
        if isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                text_parts = [str(part) for part in parts if part is not None]
                return "\n".join(text_parts).strip()
            text = content.get("text")
            if text is not None:
                return str(text).strip()
            return ""
        if isinstance(content, list):
            return "\n".join(str(part) for part in content if part is not None).strip()
        if content is None:
            return ""
        return str(content).strip()

    def _timestamp_to_iso(self, ts: float) -> str:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.isoformat()


class CursorSQLiteParser:
    """Parse Cursor IDE SQLite database (state.vscdb)."""

    def parse(self, path: Path) -> Iterator[Conversation]:
        conn: sqlite3.Connection | None = None

        # Get workspace name from path
        workspace = path.parent.name

        try:
            try:
                conn = sqlite3.connect(str(path))
                cursor = conn.cursor()
            except sqlite3.Error as exc:
                raise ParseError(f"Invalid Cursor SQLite export: {exc}") from exc

            # Query for chat/composer data
            try:
                cursor.execute(
                    "SELECT key, value FROM ItemTable WHERE key LIKE '%chat%' OR key LIKE '%composer%'"
                )
                rows = cursor.fetchall()
            except sqlite3.Error as exc:
                raise ParseError(f"Failed to read Cursor SQLite export: {exc}") from exc

            for key, value in rows:
                try:
                    data = json.loads(value)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "messages" in item:
                                yield self._parse_chat_tab(item, workspace, key)
                    elif isinstance(data, dict):
                        if "allComposers" in data:
                            for composer in data.get("allComposers", []):
                                parsed = self._parse_composer(composer, workspace)
                                if parsed is not None:
                                    yield parsed
                except (json.JSONDecodeError, ParseError):
                    continue

        finally:
            if conn is not None:
                conn.close()

    def _parse_chat_tab(self, tab: dict, workspace: str, key: str) -> Conversation:
        messages = []
        for msg in tab.get("messages", []):
            role = "assistant" if msg.get("role") == "assistant" else "user"
            content = msg.get("content", "")
            
            messages.append(ChatMessage(
                role=role,
                content=content,
                timestamp=None,
                model=msg.get("model")
            ))

        return Conversation(
            id=tab.get("id", key),
            title=tab.get("title", f"Chat {key}"),
            created_at=None,
            messages=messages,
            source="cursor",
            metadata={"workspace": workspace, "tab_id": key}
        )

    def _parse_composer(self, composer: dict, workspace: str) -> Conversation | None:
        messages = self._extract_composer_messages(composer)
        if not messages:
            return None
        return Conversation(
            id=composer.get("composerId", "unknown"),
            title=composer.get("name", "Composer Session"),
            created_at=self._ms_timestamp_to_iso(composer.get("createdAt")),
            messages=messages,
            source="cursor",
            metadata={
                "workspace": workspace,
                "type": "composer",
                "force_mode": composer.get("forceMode"),
            },
        )

    def _extract_composer_messages(self, composer: dict) -> list[ChatMessage]:
        raw_messages = composer.get("messages")
        if not isinstance(raw_messages, list):
            return []
        messages: list[ChatMessage] = []
        for msg in raw_messages:
            if not isinstance(msg, dict):
                continue
            role = "assistant" if msg.get("role") == "assistant" else "user"
            content = msg.get("content", "")
            if isinstance(content, list):
                text = "\n".join(str(part) for part in content if part is not None).strip()
            else:
                text = str(content).strip()
            if not text:
                continue
            messages.append(
                ChatMessage(
                    role=role,
                    content=text,
                    timestamp=self._ms_timestamp_to_iso(msg.get("timestamp")),
                    model=msg.get("model"),
                )
            )
        return messages

    def _ms_timestamp_to_iso(self, ts: int | None) -> str | None:
        if not ts:
            return None
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return dt.isoformat()


class PerplexityMdParser:
    """Parse Perplexity native Markdown export."""

    def parse(self, path: Path) -> Conversation:
        content = path.read_text(encoding="utf-8", errors="replace")
        
        # Extract title from first heading or filename
        title = path.stem
        lines = content.split("\n")
        
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # Parse Q&A pairs (Perplexity format: alternating user questions and AI answers)
        messages = []
        current_role: str | None = None
        current_content: list[str] = []

        for line in lines:
            # Detect question/answer boundaries
            if line.startswith("**Question:**") or line.startswith("Q:"):
                if current_role and current_content:
                    messages.append(ChatMessage(
                        role=current_role,
                        content="\n".join(current_content).strip()
                    ))
                current_role = "user"
                current_content = [line]
            elif line.startswith("**Answer:**") or line.startswith("A:"):
                if current_role and current_content:
                    messages.append(ChatMessage(
                        role=current_role,
                        content="\n".join(current_content).strip()
                    ))
                current_role = "assistant"
                current_content = [line]
            else:
                if current_role is not None:
                    current_content.append(line)

        if current_role and current_content:
            messages.append(ChatMessage(
                role=current_role,
                content="\n".join(current_content).strip()
            ))

        return Conversation(
            id=path.stem,
            title=title,
            created_at=None,
            messages=messages,
            source="perplexity",
            metadata={"original_file": str(path)}
        )


class GenericMdParser:
    """Parse generic Markdown exports from browser extensions."""

    ROLE_PATTERNS = [
        (r"^#{1,3}\s*(?:User|Human|You|Q:|Question):?\s*$", "user"),
        (r"^#{1,3}\s*(?:Assistant|AI|Bot|Claude|ChatGPT|A:|Answer):?\s*$", "assistant"),
    ]

    def parse(self, path: Path) -> Conversation:
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        title = path.stem
        for line in lines[:20]:  # Check first 20 lines for title
            if line.startswith("# ") and not line.startswith("# User"):
                title = line[2:].strip()
                break

        messages = self._extract_messages(lines)

        # If no structured messages found, treat entire file as single assistant message
        if not messages:
            messages = [ChatMessage(role="assistant", content=content)]

        return Conversation(
            id=path.stem,
            title=title,
            created_at=None,
            messages=messages,
            source="generic",
            metadata={"original_file": str(path), "parser": "generic-md"}
        )

    def _extract_messages(self, lines: list[str]) -> list[ChatMessage]:
        messages = []
        current_role = None
        current_content = []

        for line in lines:
            # Check for role markers
            new_role = None
            for pattern, role in self.ROLE_PATTERNS:
                if re.match(pattern, line, re.IGNORECASE):
                    new_role = role
                    break

            if new_role:
                if current_content and current_role:
                    messages.append(ChatMessage(
                        role=current_role,
                        content="\n".join(current_content).strip()
                    ))
                current_role = new_role
                current_content = []
            else:
                current_content.append(line)

        if current_content and current_role:
            messages.append(ChatMessage(
                role=current_role,
                content="\n".join(current_content).strip()
            ))

        return messages


def detect_format(path: Path) -> str:
    """Auto-detect export format from file."""
    ext = path.suffix.lower()
    
    if ext == ".json":
        content = path.read_text(encoding="utf-8", errors="replace")[:2000]
        if '"mapping"' in content and (content.lstrip().startswith("[") or '"conversations"' in content):
            return "chatgpt-json"
        return "unknown-json"
    
    if ext in (".vscdb", ".db", ".sqlite"):
        return "cursor-sqlite"
    
    if ext in (".md", ".markdown", ".txt"):
        content = path.read_text(encoding="utf-8", errors="replace")[:2000]
        
        # Check for Perplexity markers
        if "**Question:**" in content or "**Answer:**" in content:
            return "perplexity-md"
        
        # Check for extension export markers
        if any(marker in content for marker in ["ChatGPT", "Claude", "Perplexity"]):
            return "generic-md"
        
        return "generic-md"
    
    return "unknown"
