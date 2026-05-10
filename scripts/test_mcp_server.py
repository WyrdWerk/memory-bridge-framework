#!/usr/bin/env python3
"""Quick test for MCP server functionality."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from memory_bridge.mcp_server import (
    get_repo_root,
    check_index,
    get_status,
    list_conversations,
    search_conversations,
)

async def test():
    print("=" * 50)
    print("Memory Bridge MCP Server - Self Test")
    print("=" * 50)
    
    # Test repo discovery
    print("\n1. Repo discovery:")
    try:
        repo = get_repo_root()
        print(f"   ✓ Repo: {repo}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    # Test get_status
    print("\n2. Get status:")
    try:
        status = await get_status()
        print(f"   ✓ Disk count: {status['disk_conversation_count']}")
        print(f"   ✓ Index staleness: {status['index']['staleness']}")
        print(f"   ✓ Recommendation: {status['recommendation']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test check_index
    print("\n3. Check index:")
    try:
        check = await check_index()
        print(f"   ✓ Fresh: {check['fresh']}")
        print(f"   ✓ Disk: {check['disk_count']}, Manifest: {check['manifest_count']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test list_conversations
    print("\n4. List conversations (first 5):")
    try:
        convs = await list_conversations(limit=5)
        print(f"   ✓ Found {len(convs)} conversations")
        for c in convs[:3]:
            print(f"      - {c['rel_path']} ({c['agent_id']}, {c['open_item_count']} open)")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test search
    print("\n5. Search for 'mcp' (first 3):")
    try:
        results = await search_conversations("mcp", limit=3)
        print(f"   ✓ Found {len(results)} results")
        for r in results[:3]:
            print(f"      - {r['rel_path']} (score: {r['score']})")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print("\n" + "=" * 50)
    print("Test complete")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test())
