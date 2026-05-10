#!/usr/bin/env python3
"""Memory Bridge REST API Server

Exposes Memory Bridge and LLM Wiki operations via simple HTTP endpoints.
Runs alongside the MCP server (port 8081). Production default port is 3333 (see systemd unit).

Usage:
    PYTHONPATH=.../scripts python -m memory_bridge.rest_server --host 0.0.0.0 --port 3333

Endpoints:
    # Health & Status
    GET  /health                  -> Health check
    GET  /status                  -> Repo stats, index freshness
    
    # Memory Bridge
    GET  /conversations           -> List conversations
    GET  /conversations/{path}    -> Get specific conversation
    POST /conversations          -> Save new conversation
    GET  /search                 -> Search conversations (q param)
    POST /index/rebuild          -> Rebuild INDEX.md
    GET  /index/check            -> Check index freshness
    
    # LLM Wiki
    GET  /wiki/status            -> Wiki registry status
    GET  /wiki/topics            -> List all topics
    GET  /wiki/topics/{topic}    -> Get topic info + pending sources
    POST /wiki/compile/{topic}   -> Compile topic to wiki
    POST /wiki/compile/auto      -> Auto-compile stale topics
    GET  /wiki/articles          -> List all wiki articles
    GET  /wiki/articles/{topic}  -> Read wiki article
    GET  /wiki/search            -> Search wiki (q param)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from contextlib import asynccontextmanager

# FastAPI imports
try:
    from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
    from fastapi.responses import JSONResponse, PlainTextResponse
    from pydantic import BaseModel
except ImportError:
    print("Error: FastAPI not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

import uvicorn

# Handle imports - works both as module and direct script
try:
    from .parse_conv import glob_conversations, parse_conversation
    from .index_build import build_index
    from .search_lex import search_conversations, load_aliases
except ImportError:
    from parse_conv import glob_conversations, parse_conversation
    from index_build import build_index
    from search_lex import search_conversations, load_aliases

# Global concurrency lock for git operations
git_lock = asyncio.Lock()
IST = timezone(timedelta(hours=5, minutes=30))

def get_repo_root() -> Path:
    """Discover repo root from env or default location."""
    if env_path := os.environ.get("MEMORY_BRIDGE_REPO"):
        return Path(env_path).expanduser().resolve()
    for p in [
        Path.home() / "agentic-memory-hub",
        Path.home() / "projects" / "agentic-memory-hub",
    ]:
        if (p / ".cross-agent-memory").exists() or (p / ".git").exists():
            return p
    cwd = Path.cwd()
    if (cwd / ".cross-agent-memory").exists():
        return cwd
    raise RuntimeError("Cannot find agentic-memory-hub repo. Set MEMORY_BRIDGE_REPO env var.")

# Pydantic models
class SaveConversationRequest(BaseModel):
    content: str
    agent_id: Optional[str] = None
    topics: Optional[list[str]] = None

class CompileTopicRequest(BaseModel):
    topic: Optional[str] = None  # For auto mode, topic is optional

# FastAPI app
app = FastAPI(
    title="Memory Bridge REST API",
    description="HTTP API for Memory Bridge conversation persistence and LLM Wiki compilation",
    version="2.0.0"
)

# ============ HEALTH & STATUS ============

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(IST).isoformat(),
        "service": "memory-bridge-rest"
    }

@app.get("/status")
async def get_status():
    """Get repository status and index freshness."""
    try:
        repo_root = get_repo_root()
        
        # Count conversations on disk
        disk_count = len(list((repo_root / "conversations").rglob("*.md")))
        
        # Check index
        index_path = repo_root / "INDEX.md"
        index_exists = index_path.exists()
        
        # Parse INDEX.md header for stats
        manifest_count = 0
        staleness = "unknown"
        if index_exists:
            content = index_path.read_text()
            # Count entries in table (simple heuristic)
            lines = content.split('\n')
            for line in lines:
                if line.startswith('|') and not line.startswith('|---') and ' conversations ' in line.lower():
                    # Try to extract count
                    parts = line.split('|')
                    if len(parts) >= 3:
                        try:
                            manifest_count = int(parts[2].strip().split()[0])
                        except:
                            pass
            staleness = "fresh" if manifest_count == disk_count else "stale"
        
        return {
            "repo_root": str(repo_root),
            "disk_conversation_count": disk_count,
            "index": {
                "exists": index_exists,
                "staleness": staleness,
                "manifest_count": manifest_count,
                "delta": disk_count - manifest_count if manifest_count else disk_count
            },
            "timestamp": datetime.now(IST).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ CONVERSATIONS ============

@app.get("/conversations")
async def list_conversations(
    limit: int = Query(100, ge=1, le=500),
    agent: Optional[str] = Query(None),
    topic: Optional[str] = Query(None)
):
    """List conversations with optional filters."""
    try:
        repo_root = get_repo_root()
        # glob_conversations expects Path object
        from pathlib import Path
        conv_path = repo_root / "conversations"
        conv_files = glob_conversations(conv_path)
        
        results = []
        for filepath in conv_files[:limit]:
            try:
                # parse_conversation expects string path
                parsed = parse_conversation(filepath)
                if parsed:
                    # Apply filters
                    if agent and parsed.agent_id != agent:
                        continue
                    if topic and not any(topic.lower() in t.lower() for t in (parsed.topics or [])):
                        continue
                    
                    results.append({
                        "path": parsed.rel_path,
                        "timestamp": parsed.timestamp,
                        "agent_id": parsed.agent_id,
                        "agent_name": parsed.agent_name,
                        "topics": parsed.topics,
                        "title": parsed.title or "Untitled",
                        "word_count": len(parsed.body_text.split()) if parsed.body_text else 0
                    })
            except Exception:
                continue
        
        return {
            "conversations": results,
            "count": len(results),
            "total_available": len(conv_files)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations/{path:path}")
async def get_conversation(path: str):
    """Get a specific conversation by path."""
    try:
        repo_root = get_repo_root()
        full_path = repo_root / path
        
        # Security check - ensure within repo
        try:
            full_path.relative_to(repo_root)
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        content = full_path.read_text()
        
        return {
            "path": path,
            "content": content,
            "size_bytes": len(content.encode('utf-8'))
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversations")
async def save_conversation(request: SaveConversationRequest, background_tasks: BackgroundTasks):
    """Save a new conversation."""
    try:
        repo_root = get_repo_root()
        
        # Generate timestamp
        now = datetime.now(IST)
        timestamp_str = now.strftime("%Y%m%d-%H%M%S")
        
        # Determine agent_id
        agent_id = request.agent_id or "unknown"
        
        # Create directory
        conv_dir = repo_root / "conversations" / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
        conv_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        filename = f"{timestamp_str}-{agent_id}.md"
        filepath = conv_dir / filename
        
        # Write file
        filepath.write_text(request.content)
        
        # Git operations in background
        background_tasks.add_task(git_stage_commit_push_async, repo_root, f"memory({agent_id}): {timestamp_str}")
        
        return {
            "success": True,
            "path": str(filepath.relative_to(repo_root)),
            "timestamp": now.isoformat(),
            "message": "Conversation saved, git push in background"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def git_stage_commit_push_async(repo_root: Path, message: str):
    """Async background git operations."""
    async with git_lock:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(repo_root), "add", ".",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(repo_root), "commit", "-m", message,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(repo_root), "push", "origin", "main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception as e:
            print(f"Git error: {e}", file=sys.stderr)

# ============ SEARCH ============

@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    """Search conversations."""
    try:
        repo_root = get_repo_root()
        results = search_conversations(q, str(repo_root))
        
        return {
            "query": q,
            "results": results[:20],
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ INDEX ============

@app.post("/index/rebuild")
async def rebuild_index(background_tasks: BackgroundTasks):
    """Rebuild INDEX.md."""
    try:
        repo_root = get_repo_root()
        
        # Run in background since it can take time
        background_tasks.add_task(rebuild_index_async, repo_root)
        
        return {
            "success": True,
            "message": "Index rebuild started in background"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def rebuild_index_async(repo_root: Path):
    """Async index rebuild."""
    async with git_lock:
        try:
            # Use subprocess to run the CLI
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "memory_bridge",
                "index", "rebuild",
                "--repo", str(repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            # Git commit
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(repo_root), "add", "INDEX.md",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            
            timestamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(repo_root), "commit", "-m", f"index: rebuild via REST API {timestamp}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(repo_root), "push", "origin", "main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception as e:
            print(f"Index rebuild error: {e}", file=sys.stderr)

@app.get("/index/check")
async def check_index():
    """Check index freshness."""
    try:
        repo_root = get_repo_root()
        disk_count = len(list((repo_root / "conversations").rglob("*.md")))
        
        index_path = repo_root / "INDEX.md"
        if not index_path.exists():
            return {"fresh": False, "disk_count": disk_count, "manifest_count": 0}
        
        content = index_path.read_text()
        lines = content.split('\n')
        manifest_count = 0
        for line in lines:
            if 'Total conversations:' in line:
                try:
                    manifest_count = int(line.split(':')[1].strip())
                except:
                    pass
        
        return {
            "fresh": disk_count == manifest_count,
            "disk_count": disk_count,
            "manifest_count": manifest_count,
            "delta": disk_count - manifest_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ WIKI ============

@app.get("/wiki/status")
async def wiki_status():
    """Get wiki registry status."""
    try:
        repo_root = get_repo_root()
        registry_path = repo_root / "wiki" / ".registry.yaml"
        
        if not registry_path.exists():
            return {"error": "Registry not found"}
        
        import yaml
        registry = yaml.safe_load(registry_path.read_text())
        
        topics = []
        for slug, info in registry.get('topics', {}).items():
            topics.append({
                "slug": slug,
                "name": info.get('name'),
                "status": info.get('status'),
                "last_compile": info.get('last_compile'),
                "pending_sources": len(info.get('sources_since_last_compile', [])),
                "threshold": info.get('threshold')
            })
        
        return {
            "last_auto_compile": registry.get('last_auto_compile'),
            "topics": topics,
            "topic_count": len(topics)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wiki/topics")
async def list_wiki_topics():
    """List all wiki topics."""
    try:
        repo_root = get_repo_root()
        registry_path = repo_root / "wiki" / ".registry.yaml"
        
        if not registry_path.exists():
            return {"topics": []}
        
        import yaml
        registry = yaml.safe_load(registry_path.read_text())
        
        return {
            "topics": [
                {
                    "slug": slug,
                    "name": info.get('name'),
                    "keywords": info.get('keywords', []),
                    "status": info.get('status'),
                    "article": info.get('wiki_article')
                }
                for slug, info in registry.get('topics', {}).items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wiki/topics/{topic}")
async def get_wiki_topic(topic: str):
    """Get specific topic info and pending sources."""
    try:
        repo_root = get_repo_root()
        registry_path = repo_root / "wiki" / ".registry.yaml"
        
        if not registry_path.exists():
            raise HTTPException(status_code=404, detail="Registry not found")
        
        import yaml
        registry = yaml.safe_load(registry_path.read_text())
        
        if topic not in registry.get('topics', {}):
            raise HTTPException(status_code=404, detail="Topic not found")
        
        info = registry['topics'][topic]
        
        return {
            "slug": topic,
            "name": info.get('name'),
            "keywords": info.get('keywords', []),
            "threshold": info.get('threshold'),
            "status": info.get('status'),
            "last_compile": info.get('last_compile'),
            "wiki_article": info.get('wiki_article'),
            "pending_sources": info.get('sources_since_last_compile', []),
            "raw_dir": info.get('raw_dir'),
            "wiki_dir": info.get('wiki_dir')
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/wiki/compile/{topic}")
async def compile_wiki_topic(topic: str, background_tasks: BackgroundTasks):
    """Compile a topic to wiki (simplified - returns message)."""
    try:
        repo_root = get_repo_root()
        
        # For now, return info about what would be compiled
        # Full compilation requires more complex logic
        registry_path = repo_root / "wiki" / ".registry.yaml"
        import yaml
        registry = yaml.safe_load(registry_path.read_text())
        
        if topic not in registry.get('topics', {}):
            raise HTTPException(status_code=404, detail="Topic not found")
        
        info = registry['topics'][topic]
        pending = info.get('sources_since_last_compile', [])
        
        return {
            "message": f"Topic '{topic}' has {len(pending)} sources pending compilation",
            "topic": topic,
            "pending_sources": len(pending),
            "threshold": info.get('threshold'),
            "should_compile": len(pending) >= info.get('threshold', 2),
            "note": "Use llm-wiki-compile skill for full compilation"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/wiki/compile/auto")
async def auto_compile_wiki(background_tasks: BackgroundTasks):
    """Auto-compile stale topics (simplified)."""
    try:
        repo_root = get_repo_root()
        registry_path = repo_root / "wiki" / ".registry.yaml"
        
        import yaml
        registry = yaml.safe_load(registry_path.read_text())
        
        ready_topics = []
        for slug, info in registry.get('topics', {}).items():
            pending = len(info.get('sources_since_last_compile', []))
            if pending >= info.get('threshold', 2):
                ready_topics.append(slug)
        
        return {
            "message": f"{len(ready_topics)} topics ready for compilation",
            "ready_topics": ready_topics,
            "note": "Use llm-wiki-compile --auto for full compilation"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wiki/articles")
async def list_wiki_articles():
    """List all wiki articles."""
    try:
        repo_root = get_repo_root()
        wiki_dir = repo_root / "wiki"
        
        articles = []
        for topic_dir in wiki_dir.iterdir():
            if topic_dir.is_dir() and not topic_dir.name.startswith('.'):
                for article_file in topic_dir.glob("*.md"):
                    stat = article_file.stat()
                    articles.append({
                        "topic": topic_dir.name,
                        "file": article_file.name,
                        "path": str(article_file.relative_to(repo_root)),
                        "size_bytes": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, IST).isoformat()
                    })
        
        return {
            "articles": articles,
            "count": len(articles)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wiki/articles/{topic}")
async def get_wiki_article(topic: str, file: Optional[str] = None):
    """Get a wiki article."""
    try:
        repo_root = get_repo_root()
        wiki_dir = repo_root / "wiki" / topic
        
        if not wiki_dir.exists():
            raise HTTPException(status_code=404, detail="Topic directory not found")
        
        # If specific file requested
        if file:
            article_path = wiki_dir / file
        else:
            # Find the main article (first .md file)
            md_files = list(wiki_dir.glob("*.md"))
            if not md_files:
                raise HTTPException(status_code=404, detail="No articles found")
            article_path = md_files[0]
        
        if not article_path.exists():
            raise HTTPException(status_code=404, detail="Article not found")
        
        content = article_path.read_text()
        
        return {
            "topic": topic,
            "file": article_path.name,
            "path": str(article_path.relative_to(repo_root)),
            "content": content,
            "size_bytes": len(content.encode('utf-8'))
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wiki/search")
async def search_wiki(q: str = Query(..., min_length=1)):
    """Search wiki articles."""
    try:
        repo_root = get_repo_root()
        wiki_dir = repo_root / "wiki"
        
        results = []
        query_lower = q.lower()
        
        for topic_dir in wiki_dir.iterdir():
            if topic_dir.is_dir() and not topic_dir.name.startswith('.'):
                for article_file in topic_dir.glob("*.md"):
                    try:
                        content = article_file.read_text().lower()
                        if query_lower in content:
                            # Simple relevance scoring
                            score = content.count(query_lower)
                            results.append({
                                "topic": topic_dir.name,
                                "file": article_file.name,
                                "path": str(article_file.relative_to(repo_root)),
                                "relevance": score
                            })
                    except:
                        continue
        
        # Sort by relevance
        results.sort(key=lambda x: x['relevance'], reverse=True)
        
        return {
            "query": q,
            "results": results[:20],
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ MAIN ============

def main():
    parser = argparse.ArgumentParser(description="Memory Bridge REST API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=3000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    
    args = parser.parse_args()
    
    # Verify repo
    try:
        repo_root = get_repo_root()
        print(f"Memory Bridge REST API: {repo_root}", file=sys.stderr)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Run server
    uvicorn.run(
        "memory_bridge.rest_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )

if __name__ == "__main__":
    main()
