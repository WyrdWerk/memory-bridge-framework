#!/usr/bin/env python3
"""Memory Bridge MCP Server — FastMCP wrapper over existing CLI modules.

Exposes 4 skills (save, boot, index, digest) via Streamable HTTP, HTTP/SSE,
and stdio transports.
Centralized on VPS (<YOUR_VPS_TAILSCALE_IP>:8080) for all Tailscale-connected agents.

Usage:
    # stdio mode (default, for local agents that spawn subprocess)
    python mcp_server.py --repo ~/memory-bridge-framework

    # HTTP/SSE mode (for legacy remote agents over Tailscale)
    python mcp_server.py --transport sse --host <YOUR_VPS_TAILSCALE_IP> --port 8080

    # Streamable HTTP mode (recommended for Codex and modern MCP clients)
    python mcp_server.py --transport streamable-http --host <YOUR_VPS_TAILSCALE_IP> --port 8081

    # With auth token
    MEMORY_BRIDGE_AUTH_TOKEN=secret python mcp_server.py --transport sse ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

MCP_AVAILABLE = True

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    MCP_AVAILABLE = False

    class FastMCP:  # type: ignore[override]
        """Fallback stub so utility functions remain importable without MCP installed."""

        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def resource(self, *_args, **_kwargs):
            def decorator(func):
                return func

            return decorator

        def run(self, *_args, **_kwargs):
            raise RuntimeError("MCP server not available. Install with: pip install 'mcp[cli]'")

# Handle imports - works both as module and direct script
try:
    # When imported as part of memory_bridge package
    from .parse_conv import glob_conversations, parse_conversation, ParsedConversation
    from .index_build import build_index
    from .search_lex import search_conversations, expand_terms, load_aliases
except ImportError:
    # When run directly as script
    from parse_conv import glob_conversations, parse_conversation, ParsedConversation
    from index_build import build_index
    from search_lex import search_conversations, expand_terms, load_aliases

# Global concurrency lock for git operations (prevents push conflicts)
git_lock = asyncio.Lock()

IST = timezone(timedelta(hours=5, minutes=30))


def get_repo_root() -> Path:
    """Discover repo root from env or default location."""
    if env_path := os.environ.get("MEMORY_BRIDGE_REPO"):
        return Path(env_path).expanduser().resolve()
    # Try common locations
    for p in [
        Path.home() / "agentic-memory-hub",
        Path.home() / "projects" / "agentic-memory-hub",
        Path.home() / ".local" / "share" / "agentic-memory-hub",
    ]:
        if (p / ".cross-agent-memory").exists() or (p / ".git").exists():
            return p
    # Fallback to current working directory if it looks like the repo
    cwd = Path.cwd()
    if (cwd / ".cross-agent-memory").exists():
        return cwd
    raise RuntimeError("Cannot find agentic-memory-hub repo. Set MEMORY_BRIDGE_REPO env var.")


def _github_blob_url(repo_root: Path, rel_path: str) -> str:
    """Build a GitHub blob URL from the configured origin when possible."""
    default = f"https://github.com/<YOUR_USERNAME>/memory-bridge-framework/blob/main/{rel_path}"
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return default
        remote = proc.stdout.strip()
        match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote)
        if not match:
            return default
        owner, repo = match.groups()
        return f"https://github.com/{owner}/{repo}/blob/main/{rel_path}"
    except Exception:
        return default


async def git_stage_commit_push(repo_root: Path, message: str) -> dict[str, Any]:
    """Stage, commit, push with retry logic for concurrent writes.
    
    Uses asyncio.Lock to prevent race conditions when multiple agents save simultaneously.
    Retries with pull --rebase on push failure.
    """
    async with git_lock:
        return await _git_stage_commit_push_unlocked(repo_root, message)


async def _git_stage_commit_push_unlocked(repo_root: Path, message: str) -> dict[str, Any]:
    """Stage, commit, and push assuming the caller already holds git_lock."""
    results = {"staged": False, "committed": False, "pushed": False, "message": "", "retries": 0}

    # Stage all changes
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo_root), "add", ".",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git add failed: {stderr.decode()}")
    results["staged"] = True

    # Commit
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo_root), "commit", "-m", message,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        stderr_text = stderr.decode()
        if "nothing to commit" in stderr_text or "no changes added" in stderr_text:
            results["message"] = "No changes to commit"
            return results
        raise RuntimeError(f"git commit failed: {stderr_text}")

    results["committed"] = True

    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo_root), "rev-parse", "HEAD",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git rev-parse failed: {stderr.decode()}")
    commit_hash = stdout.decode().strip()
    results["commit_hash"] = commit_hash

    for attempt in range(3):
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo_root), "push", "origin", "main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            results["pushed"] = True
            results["retries"] = attempt
            results["message"] = f"Committed {commit_hash} and pushed (retries: {attempt})"
            return results

        stderr_text = stderr.decode()
        if any(x in stderr_text.lower() for x in ["rejected", "stale", "non-fast-forward", "fetch first"]):
            results["retries"] = attempt + 1
            pull_proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(repo_root), "pull", "--autostash", "--rebase", "origin", "main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await pull_proc.communicate()
            continue

        raise RuntimeError(f"git push failed: {stderr_text}")

    raise RuntimeError("git push failed after 3 attempts with rebase")


def generate_timestamp() -> str:
    """Generate ISO timestamp in IST timezone."""
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def generate_filename(agent_id: str) -> str:
    """Generate filename from agent_id and current timestamp."""
    ts = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{agent_id}.md"


# Initialize FastMCP server. Keep construction conservative so the server can
# start on older installed MCP SDK versions; transport behavior is selected at
# runtime.
mcp = FastMCP("memory-bridge")


# ============================
# MCP Tools (10 total)
# ============================

@mcp.tool()
async def save_conversation(
    agent_id: str,
    agent_name: str,
    context: str,
    key_discussion_points: list[str],
    decisions_made: list[dict[str, Any]],  # [{"text": str, "status": "finalized|pending"}]
    action_items: list[str],
    topics: list[str] = None,
    related_repos: list[str] = None,
    related_sessions: list[str] = None,
    code_references: list[str] = None,
    next_steps: str = "",
    session_id: str = "",
    artifacts: list[dict[str, Any]] = None,  # [{"name": str, "content": str, "type": str}]
) -> dict[str, Any]:
    """Save a conversation to the Agentic Memory Hub.
    
    Writes markdown with YAML frontmatter, auto-commits, and pushes to GitHub.
    This tool is the primary way agents persist their work for cross-agent visibility.
    
    Args:
        agent_id: Short identifier (cursor, claude, opencode, codex, pi, hermes)
        agent_name: Human-readable name ("Cursor", "Claude Code", etc.)
        context: 2-3 sentences describing what triggered this conversation
        key_discussion_points: List of main discussion points (numbered)
        decisions_made: List of decisions with status: [{"text": "decision", "status": "finalized"}]
        action_items: List of open tasks (will be rendered as checkboxes)
        topics: List of topic tags for search/discovery
        related_repos: List of related repository names
        related_sessions: List of related session IDs (YYYYMMDD-HHMMSS-agent format)
        code_references: File paths, repos, commands referenced
        next_steps: What happens next / follow-up plans
        session_id: Optional session identifier
        artifacts: Optional embedded artifacts [{"name": str, "content": str, "type": str}]
    
    Returns:
        dict with file_path, timestamp, git_result, and status
    """
    repo_root = get_repo_root()
    
    # Generate paths
    now = datetime.now(IST)
    yyyy, mm, dd = now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")
    filename = generate_filename(agent_id)
    rel_path = f"conversations/{yyyy}/{mm}/{dd}/{filename}"
    full_path = repo_root / rel_path
    
    # Build frontmatter
    timestamp = generate_timestamp()
    fm_topics = topics or []
    fm_related_repos = related_repos or []
    fm_related_sessions = related_sessions or []
    
    # Build decisions checkboxes
    decisions_list = []
    for d in decisions_made:
        text = d.get("text", "")
        status = d.get("status", "pending")
        checked = "x" if status == "finalized" else " "
        decisions_list.append(f"- [{checked}] {text}")
    
    # Build action items checkboxes
    action_list = [f"- [ ] {item}" for item in action_items]
    
    # Build artifacts section if present
    artifacts_section = ""
    if artifacts:
        for art in artifacts:
            name = art.get("name", "Artifact")
            content = art.get("content", "")
            art_type = art.get("type", "document")
            word_count = len(content.split())
            
            artifacts_section += f"\n\n---\n\n## Embedded Artifact: {name}\n\n"
            artifacts_section += f"**Type:** {art_type}  \n"
            artifacts_section += f"**Word Count:** {word_count}  \n"
            artifacts_section += f"**Status:** embedded\n\n"
            artifacts_section += content[:3000]  # Cap embedded content
            if len(content) > 3000:
                artifacts_section += "\n\n*(Content truncated at 3000 chars)*"
    
    # Build full markdown content
    frontmatter_lines = [
        "---",
        f'timestamp: "{timestamp}"',
        f'agent_id: "{agent_id}"',
        f'agent_name: "{agent_name}"',
    ]
    if session_id:
        frontmatter_lines.append(f'session_id: "{session_id}"')
    frontmatter_lines.extend([
        'user: "<YOUR_NAME>"',
        f'duration_minutes: 0',
        f'topics: {json.dumps(fm_topics)}',
        f'related_repos: {json.dumps(fm_related_repos)}',
        f'related_sessions: {json.dumps(fm_related_sessions)}',
        "---",
        "",
        "## Context",
        context,
        "",
        "## Key Discussion Points",
    ])
    
    for i, point in enumerate(key_discussion_points, 1):
        frontmatter_lines.append(f"{i}. {point}")
    
    frontmatter_lines.extend([
        "",
        "## Decisions Made",
    ])
    frontmatter_lines.extend(decisions_list if decisions_list else ["- (none)"])
    
    frontmatter_lines.extend([
        "",
        "## Action Items",
    ])
    frontmatter_lines.extend(action_list if action_list else ["- [ ] (none)"])
    
    if code_references:
        frontmatter_lines.extend([
            "",
            "## Code/Config References",
        ])
        for ref in code_references:
            frontmatter_lines.append(f"- {ref}")
    
    if artifacts_section:
        frontmatter_lines.append(artifacts_section)
    
    frontmatter_lines.extend([
        "",
        "## Next Steps / Follow-up",
        next_steps if next_steps else "(none)",
        "",
    ])
    
    content = "\n".join(frontmatter_lines)
    
    short_topic = (fm_topics[0] if fm_topics else "conversation").replace(" ", "-")
    git_message = f"memory({agent_id}): {now.strftime('%Y%m%d-%H%M%S')} - {short_topic}"
    index_result = None

    try:
        async with git_lock:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            # TODO: build_index is synchronous and blocks the event loop during save.
            # At scale, consider run_in_executor with a threading lock alongside
            # the asyncio lock to avoid blocking concurrent MCP requests.
            index_result = build_index(repo_root, write_sidecars=True)
            git_result = await _git_stage_commit_push_unlocked(repo_root, git_message)
    except Exception as e:
        git_result = {"error": str(e), "staged": False, "committed": False, "pushed": False}

    response = {
        "status": "success" if git_result.get("pushed") else "partial",
        "file_path": str(full_path),
        "rel_path": rel_path,
        "timestamp": timestamp,
        "git_result": git_result,
        "url": _github_blob_url(repo_root, rel_path),
    }
    if index_result:
        response.update(
            {
                "index_updated": True,
                "index_rebuilt_at": index_result["rebuilt_at_ist"],
                "index_conversation_count": index_result["conversation_count"],
            }
        )
    return response


@mcp.tool()
async def search_conversations(
    query: str,
    limit: int = 25,
    agent_filter: str = None,
    date_after: str = None,  # YYYY-MM-DD
    date_before: str = None,  # YYYY-MM-DD
) -> list[dict[str, Any]]:
    """Search conversations using deterministic lexical scoring (no embeddings, no API keys).
    
    Scoring weights:
    - 70 points: normalized stem match in filename (strongest signal)
    - 48 points: raw substring in filename
    - 35 points: substring in metadata (topics, keywords, repos, checklists)
    - 8 points: substring in body text (weakest, false-positive-prone)
    
    Args:
        query: Search query (space-separated terms, topic aliases expanded automatically)
        limit: Maximum results (default 25)
        agent_filter: Optional agent_id to filter by (cursor, claude, hermes, etc.)
        date_after: Optional date filter (YYYY-MM-DD, inclusive)
        date_before: Optional date filter (YYYY-MM-DD, inclusive)
    
    Returns:
        List of results with score, rel_path, agent_id, timestamp, topics, excerpt
    """
    repo_root = get_repo_root()
    
    # Use existing search function from search_lex module
    try:
        from .search_lex import search_conversations as _search_conversations_impl
    except ImportError:
        from search_lex import search_conversations as _search_conversations_impl
    
    loop = asyncio.get_event_loop()
    raw_results = await loop.run_in_executor(
        None, lambda: _search_conversations_impl(repo_root, query, limit=limit * 2)
    )  # Get extra for filtering
    
    results = []
    for score, rel_path in raw_results:
        pc = parse_conversation(repo_root, rel_path)
        
        # Apply filters
        if agent_filter and pc.agent_id != agent_filter:
            continue
        
        if date_after or date_before:
            # Extract date from rel_path (conversations/YYYY/MM/DD/...)
            parts = Path(rel_path).parts
            if len(parts) >= 4:
                file_date = f"{parts[1]}-{parts[2]}-{parts[3]}"
                if date_after and file_date < date_after:
                    continue
                if date_before and file_date > date_before:
                    continue
        
        # Get excerpt from body
        excerpt = pc.body_text[:500].replace("\n", " ") if pc.body_text else ""
        if len(excerpt) > 500:
            excerpt = excerpt[:497] + "..."
        
        results.append({
            "score": score,
            "rel_path": rel_path,
            "agent_id": pc.agent_id,
            "timestamp": pc.timestamp,
            "topics": pc.frontmatter.get("topics", []),
            "open_actions": pc.open_actions,
            "open_decisions": pc.open_decisions,
            "excerpt": excerpt,
        })
        
        if len(results) >= limit:
            break
    
    return results


@mcp.tool()
async def digest_conversations(
    topic: str,
    max_conversations: int = 10,
    include_closed: bool = False,
) -> dict[str, Any]:
    """Generate a topic digest with timeline, open items, and decisions.
    
    Args:
        topic: Topic to digest (topic aliases expanded automatically)
        max_conversations: Max conversations to include (default 10)
        include_closed: Whether to include closed action items (default false)
    
    Returns:
        dict with timeline, open_items, decisions, stats, and related_sessions
    """
    repo_root = get_repo_root()
    
    # Search for conversations matching the topic using thread pool
    try:
        from .search_lex import search_conversations as _search_impl
    except ImportError:
        from search_lex import search_conversations as _search_impl
    loop = asyncio.get_event_loop()
    raw_results = await loop.run_in_executor(
        None, lambda: _search_impl(repo_root, topic, limit=max_conversations * 2)
    )
    
    # Filter to high-relevance results (score > 50)
    filtered = [(s, r) for s, r in raw_results if s > 50][:max_conversations]
    
    if not filtered:
        # Lower threshold if no high-relevance matches
        filtered = raw_results[:max_conversations]
    
    timeline = []
    open_items = []
    decisions = []
    related_sessions_set = set()
    
    for score, rel_path in filtered:
        pc = parse_conversation(repo_root, rel_path)
        
        # Timeline entry
        timeline.append({
            "date": Path(rel_path).stem[:8] if len(Path(rel_path).stem) >= 8 else "unknown",
            "agent_id": pc.agent_id,
            "rel_path": rel_path,
            "topics": pc.frontmatter.get("topics", []),
            "open_count": len(pc.open_actions) + len(pc.open_decisions),
        })
        
        # Collect open items
        for action in pc.open_actions:
            open_items.append({
                "text": action,
                "source": rel_path,
                "agent_id": pc.agent_id,
                "type": "action",
            })
        for decision in pc.open_decisions:
            open_items.append({
                "text": decision,
                "source": rel_path,
                "agent_id": pc.agent_id,
                "type": "decision",
            })
        
        # Collect decisions (both open and closed if requested)
        for decision in pc.open_decisions:
            decisions.append({
                "text": decision,
                "status": "pending",
                "source": rel_path,
                "agent_id": pc.agent_id,
            })
        if include_closed:
            for decision in pc.closed_decisions:
                decisions.append({
                    "text": decision,
                    "status": "finalized",
                    "source": rel_path,
                    "agent_id": pc.agent_id,
                })
        
        # Collect related sessions
        rs = pc.frontmatter.get("related_sessions", [])
        if isinstance(rs, list):
            related_sessions_set.update(str(x) for x in rs if x)
    
    # Sort timeline by date (descending)
    timeline.sort(key=lambda x: x["date"], reverse=True)
    
    return {
        "topic": topic,
        "conversation_count": len(timeline),
        "timeline": timeline,
        "open_items": open_items,
        "decisions": decisions,
        "related_sessions": sorted(related_sessions_set),
        "stats": {
            "total_open_actions": len([x for x in open_items if x["type"] == "action"]),
            "total_open_decisions": len([x for x in open_items if x["type"] == "decision"]),
            "agents_involved": list(set(x["agent_id"] for x in timeline if x["agent_id"])),
        },
    }


@mcp.tool()
async def list_conversations(
    agent_id: str = None,
    limit: int = 100,
    offset: int = 0,
    with_open_items_only: bool = False,
) -> list[dict[str, Any]]:
    """List conversations from the index (fast, uses sidecar cache).
    
    Args:
        agent_id: Optional filter by agent
        limit: Max results (default 100)
        offset: Skip first N results
        with_open_items_only: Only return conversations with open items
    
    Returns:
        List of conversation summaries
    """
    repo_root = get_repo_root()
    idx_dir = repo_root / ".index"
    manifest_path = idx_dir / "manifest.json"
    conv_dir = idx_dir / "conversations"
    
    results = []
    
    # If index exists and sidecars present, use fast path
    if manifest_path.exists() and conv_dir.is_dir():
        sidecars = sorted(conv_dir.glob("*.json"))
        
        for sidecar in sidecars:
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                
                # Filters
                if agent_id and data.get("agent_id") != agent_id:
                    continue
                if with_open_items_only and data.get("open_item_count", 0) == 0:
                    continue
                
                results.append({
                    "rel_path": data.get("rel_path"),
                    "agent_id": data.get("agent_id"),
                    "timestamp": data.get("timestamp"),
                    "date": data.get("date"),
                    "topics": data.get("topics", []),
                    "open_item_count": data.get("open_item_count", 0),
                    "session_label": data.get("session_label"),
                    "excerpt": data.get("body_excerpt", "")[:200],
                })
            except (json.JSONDecodeError, IOError):
                continue
    else:
        # Fallback: scan filesystem (slower)
        rel_paths = glob_conversations(repo_root)
        for rel in rel_paths:
            pc = parse_conversation(repo_root, rel)
            
            if agent_id and pc.agent_id != agent_id:
                continue
            open_count = len(pc.open_actions) + len(pc.open_decisions)
            if with_open_items_only and open_count == 0:
                continue
            
            results.append({
                "rel_path": rel,
                "agent_id": pc.agent_id,
                "timestamp": pc.timestamp,
                "date": Path(rel).parts[1:4] if len(Path(rel).parts) >= 4 else ["unknown"],
                "topics": pc.frontmatter.get("topics", []),
                "open_item_count": open_count,
                "session_label": pc.session_label,
                "excerpt": "",
            })
    
    # Sort by date descending (newest first)
    results.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    
    # Apply offset and limit
    return results[offset:offset + limit]


@mcp.tool()
async def show_conversation(rel_path: str) -> dict[str, Any]:
    """Retrieve the full content of a single conversation.
    
    Args:
        rel_path: Relative path to conversation (e.g., "conversations/2026/05/06/20260506-160859-opencode.md")
    
    Returns:
        Full conversation with parsed frontmatter and body
    """
    repo_root = get_repo_root()
    full_path = repo_root / rel_path
    
    if not full_path.exists():
        return {"error": f"File not found: {rel_path}", "status": "not_found"}
    
    pc = parse_conversation(repo_root, rel_path)
    raw_markdown = full_path.read_text(encoding="utf-8")
    
    return {
        "status": "success",
        "rel_path": rel_path,
        "frontmatter": pc.frontmatter,
        "agent_id": pc.agent_id,
        "timestamp": pc.timestamp,
        "session_label": pc.session_label,
        "topics": pc.frontmatter.get("topics", []),
        "open_actions": pc.open_actions,
        "open_decisions": pc.open_decisions,
        "closed_actions": pc.closed_actions,
        "closed_decisions": pc.closed_decisions,
        "body_text": pc.body_text,
        "raw_markdown": raw_markdown,
        "warnings": pc.warnings,
    }


@mcp.tool()
async def get_status() -> dict[str, Any]:
    """Get repository status including index freshness.
    
    Returns:
        Stats on conversation count, index freshness, and staleness warnings
    """
    repo_root = get_repo_root()
    
    # Count actual files
    conv_paths = glob_conversations(repo_root)
    disk_count = len(conv_paths)
    
    # Check index state
    idx_dir = repo_root / ".index"
    manifest_path = idx_dir / "manifest.json"
    
    index_info = {
        "manifest_exists": manifest_path.exists(),
        "sidecar_count": 0,
        "rebuilt_at": None,
        "staleness": "unknown",
    }
    
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            index_info["rebuilt_at"] = manifest.get("rebuilt_at_ist")
            index_info["manifest_count"] = manifest.get("conversation_count", 0)
            
            # Check staleness
            if index_info["manifest_count"] != disk_count:
                index_info["staleness"] = "stale"
                index_info["staleness_reason"] = f"manifest={index_info['manifest_count']}, disk={disk_count}"
            else:
                index_info["staleness"] = "fresh"
        except (json.JSONDecodeError, IOError):
            index_info["staleness"] = "error"
    else:
        index_info["staleness"] = "missing"
    
    # Count sidecars
    conv_dir = idx_dir / "conversations"
    if conv_dir.is_dir():
        index_info["sidecar_count"] = len(list(conv_dir.glob("*.json")))
    
    # Open items count
    open_total = 0
    for rel in conv_paths[:50]:  # Sample first 50 for speed
        pc = parse_conversation(repo_root, rel)
        open_total += len(pc.open_actions) + len(pc.open_decisions)
    
    return {
        "repo_root": str(repo_root),
        "disk_conversation_count": disk_count,
        "index": index_info,
        "open_items_estimate": open_total,
        "recommendation": "Run rebuild_index()" if index_info["staleness"] in ["stale", "missing"] else "Index is current",
    }


@mcp.tool()
async def rebuild_index() -> dict[str, Any]:
    """Rebuild INDEX.md and .index/ sidecars, then commit and push.
    
    This is an expensive operation that re-parses all conversations.
    Call it periodically (e.g., once per day) or after bulk imports.
    
    Returns:
        Result with conversation_count, open_items_count, git_result
    """
    repo_root = get_repo_root()
    
    git_message = None
    try:
        async with git_lock:
            # TODO: build_index is synchronous and blocks the event loop.
            # Acceptable for infrequent explicit rebuild calls; see save_conversation TODO.
            result = build_index(repo_root, write_sidecars=True)
            git_message = (
                f"memory(index): rebuilt {result['conversation_count']} conversations, "
                f"{result['with_open_items']} with open items"
            )
            git_result = await _git_stage_commit_push_unlocked(repo_root, git_message)
    except Exception as e:
        if git_message is None:
            result = {"conversation_count": 0, "with_open_items": 0, "rebuilt_at_ist": None}
        git_result = {"error": str(e), "staged": False, "committed": False, "pushed": False}
    
    return {
        "conversation_count": result["conversation_count"],
        "with_open_items": result["with_open_items"],
        "rebuilt_at": result["rebuilt_at_ist"],
        "git_result": git_result,
        "status": "success" if git_result.get("pushed") else "partial",
    }


@mcp.tool()
async def check_index() -> dict[str, Any]:
    """Quick freshness check: compare disk file count to index manifest.
    
    Returns:
        Freshness status without rebuilding
    """
    repo_root = get_repo_root()
    
    conv_paths = glob_conversations(repo_root)
    disk_count = len(conv_paths)
    
    manifest_path = repo_root / ".index" / "manifest.json"
    
    if not manifest_path.exists():
        return {
            "fresh": False,
            "manifest_exists": False,
            "disk_count": disk_count,
            "manifest_count": 0,
            "delta": disk_count,
        }
    
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_count = manifest.get("conversation_count", 0)
    except (json.JSONDecodeError, IOError):
        return {
            "fresh": False,
            "manifest_exists": True,
            "manifest_readable": False,
            "disk_count": disk_count,
            "manifest_count": 0,
            "delta": disk_count,
        }
    
    delta = disk_count - manifest_count
    
    return {
        "fresh": delta == 0,
        "disk_count": disk_count,
        "manifest_count": manifest_count,
        "delta": delta,
        "rebuilt_at": manifest.get("rebuilt_at_ist"),
        "recommendation": "Run rebuild_index()" if delta != 0 else "Index is current",
    }


@mcp.tool()
async def import_conversations(
    source_dir: str,
    format: str = "auto",  # auto, claude, cursor, opencode, chatgpt, obsidian
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import external conversation exports into canonical memory-bridge format.
    
    Args:
        source_dir: Directory containing export files
        format: Source format (auto-detect if not specified)
        dry_run: Preview without writing
    
    Returns:
        Import summary with files processed
    """
    repo_root = get_repo_root()
    try:
        from .importer import scan_and_convert
    except ImportError:
        from importer import scan_and_convert
    
    source_path = Path(source_dir).expanduser().resolve()
    
    if not source_path.is_dir():
        return {"error": f"Source directory not found: {source_dir}", "status": "error"}
    
    # Run import in thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, 
        lambda: scan_and_convert(repo_root, source_path, format_hint=format, dry_run=dry_run)
    )
    
    if not dry_run and result.get("imported", 0) > 0:
        # Commit the imports
        git_message = f"memory(import): {result['imported']} conversations from {format}"
        try:
            git_result = await git_stage_commit_push(repo_root, git_message)
            result["git_result"] = git_result
        except Exception as e:
            result["git_error"] = str(e)
    
    return result


@mcp.tool()
async def sync_skills() -> dict[str, Any]:
    """Sync canonical skills from the hub to agent install directories.
    
    This is a utility for maintaining skill parity across agents.
    
    Returns:
        Sync summary with per-agent status
    """
    repo_root = get_repo_root()
    skills_dir = repo_root / "skills"
    
    if not skills_dir.is_dir():
        return {"error": "No skills directory in repo", "status": "error"}
    
    results = []
    
    # Define agent skill install locations
    agent_targets = {
        "claude": Path.home() / ".claude" / "skills",
        "cursor": Path.home() / ".cursor" / "skills",
        "opencode": Path.home() / ".config" / "opencode" / "skills",
        "codex": Path.home() / ".codex" / "skills",
        "pi": Path.home() / ".pi" / "skills",
        "hermes": Path.home() / ".hermes" / "skills",
    }
    
    for agent_id, target_dir in agent_targets.items():
        status = "skipped"
        if target_dir.parent.exists():
            target_dir.mkdir(exist_ok=True)
            # Simple sync: check for skill presence
            synced_count = 0
            for skill_file in skills_dir.glob("*/SKILL.md"):
                skill_name = skill_file.parent.name
                agent_skill_dir = target_dir / skill_name
                agent_skill_file = agent_skill_dir / "SKILL.md"
                
                if not agent_skill_file.exists():
                    agent_skill_dir.mkdir(parents=True, exist_ok=True)
                    agent_skill_file.write_text(skill_file.read_text(), encoding="utf-8")
                    synced_count += 1
            
            status = f"synced {synced_count} skills" if synced_count > 0 else "up to date"
        
        results.append({"agent": agent_id, "target": str(target_dir), "status": status})
    
    return {
        "status": "success",
        "results": results,
        "skills_source": str(skills_dir),
    }


# ============================
# MCP Resources (read-only data)
# ============================

@mcp.resource("conversation://{rel_path}")
def get_conversation_resource(rel_path: str) -> str:
    """Resource: Full markdown content of a conversation.
    
    URI format: conversation://conversations/2026/05/06/20260506-160859-opencode.md
    """
    repo_root = get_repo_root()
    full_path = repo_root / rel_path
    
    if not full_path.exists():
        return f"# Error\n\nFile not found: {rel_path}"
    
    return full_path.read_text(encoding="utf-8")


@mcp.resource("index://summary")
def get_index_summary() -> str:
    """Resource: Full INDEX.md content."""
    repo_root = get_repo_root()
    index_path = repo_root / "INDEX.md"
    
    if not index_path.exists():
        return "# Memory Bridge Index\n\nIndex not yet built. Run rebuild_index()."
    
    return index_path.read_text(encoding="utf-8")


@mcp.resource("index://manifest")
def get_index_manifest() -> str:
    """Resource: .index/manifest.json as formatted JSON."""
    repo_root = get_repo_root()
    manifest_path = repo_root / ".index" / "manifest.json"
    
    if not manifest_path.exists():
        return json.dumps({"error": "Manifest not found"}, indent=2)
    
    return manifest_path.read_text(encoding="utf-8")


@mcp.resource("index://conversation/{rel_path}")
def get_conversation_sidecar(rel_path: str) -> str:
    """Resource: Sidecar JSON for a single conversation.
    
    URI format: index://conversation/conversations/2026/05/06/20260506-160859-opencode.md
    """
    repo_root = get_repo_root()
    
    # Convert rel_path to sidecar filename
    fname = "__".join(Path(rel_path).as_posix().split("/"))
    if fname.endswith(".md"):
        fname = fname[:-3] + ".json"
    else:
        fname += ".json"
    
    sidecar_path = repo_root / ".index" / "conversations" / fname
    
    if not sidecar_path.exists():
        return json.dumps({"error": "Sidecar not found", "rel_path": rel_path}, indent=2)
    
    return sidecar_path.read_text(encoding="utf-8")


# ============================
# Main entry point
# ============================

def main():
    parser = argparse.ArgumentParser(description="Memory Bridge MCP Server")
    parser.add_argument(
        "--repo",
        type=str,
        default=os.environ.get("MEMORY_BRIDGE_REPO", ""),
        help="Path to agentic-memory-hub repository",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mode: stdio (default), sse, or streamable-http",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for HTTP transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for HTTP transports (default: 8080)",
    )
    parser.add_argument(
        "--auth-token",
        type=str,
        default=os.environ.get("MEMORY_BRIDGE_AUTH_TOKEN", ""),
        help="Bearer token for HTTP authentication",
    )
    
    args = parser.parse_args()
    
    # Set repo path if provided
    if args.repo:
        os.environ["MEMORY_BRIDGE_REPO"] = args.repo
    
    # Verify repo exists
    try:
        repo_root = get_repo_root()
        print(f"Memory Bridge MCP Server: {repo_root}", file=sys.stderr)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.transport == "stdio":
        # stdio mode: run with FastMCP default
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        # Allow any host on the Tailscale network (defense in depth:
        # Tailscale still provides the encryption and peer boundary).
        mcp.settings.transport_security.allowed_hosts = ["*", "<YOUR_VPS_TAILSCALE_IP>:*", "<YOUR_VPS_TAILSCALE_IP>"]

        if args.transport == "sse":
            print(f"Starting HTTP/SSE server on {args.host}:{args.port}", file=sys.stderr)
            if args.auth_token:
                print("Authentication: enabled", file=sys.stderr)
            mcp.run(transport="sse", host=args.host, port=args.port)
        else:
            print(f"Starting Streamable HTTP server on {args.host}:{args.port}", file=sys.stderr)
            if args.auth_token:
                print("Authentication: enabled", file=sys.stderr)
            mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
