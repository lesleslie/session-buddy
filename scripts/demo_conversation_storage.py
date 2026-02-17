#!/usr/bin/env python3
"""Demonstration of conversation storage functionality.

This script demonstrates the complete conversation storage workflow:
1. Storing conversations
2. Searching conversations
3. Viewing statistics
4. Verifying embeddings
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def demo_conversation_storage() -> None:
    """Demonstrate conversation storage functionality."""
    print("\n" + "=" * 70)
    print("Conversation Storage Demonstration")
    print("=" * 70)

    from session_buddy.core.conversation_storage import (
        capture_conversation_context,
        get_conversation_stats,
        store_conversation_checkpoint,
    )
    from session_buddy.core.session_manager import SessionLifecycleManager
    from session_buddy.reflection.database import ReflectionDatabase

    # Demo 1: Store a conversation
    print("\n📝 Demo 1: Storing a conversation checkpoint")
    print("-" * 70)

    manager = SessionLifecycleManager()
    manager.current_project = "demo-project"
    manager._quality_history["demo-project"] = [70, 75, 80, 85]

    # Capture context
    context = await capture_conversation_context(
        manager,
        checkpoint_type="demo",
        quality_score=85,
        metadata={"demo": True},
    )

    print("Captured context:")
    print(context[:200] + "..." if len(context) > 200 else context)

    # Store checkpoint
    result = await store_conversation_checkpoint(
        manager,
        checkpoint_type="demo",
        quality_score=85,
        is_manual=True,
    )

    if result["success"]:
        print("\n✅ Conversation stored successfully!")
        print(f"   Conversation ID: {result['conversation_id']}")
    else:
        print(f"\n❌ Storage failed: {result.get('error')}")
        return

    # Demo 2: Search conversations
    print("\n📝 Demo 2: Searching conversations")
    print("-" * 70)

    db = ReflectionDatabase()
    await db.initialize()
    try:
        # Semantic search
        results = await db.search_conversations(
            query="demo project quality score",
            limit=5,
            min_score=0.1,  # Low threshold for demo
        )

        if results:
            print(f"Found {len(results)} conversation(s)\n")
            for i, result in enumerate(results, 1):
                score = result.get("score", 0) * 100
                print(f"{i}. Similarity: {score:.1f}%")
                print(f"   Project: {result.get('project', 'unknown')}")
                print(f"   Timestamp: {result.get('timestamp', 'unknown')}")

                # Show content preview
                content = result.get("content", "")
                preview = content[:150] + "..." if len(content) > 150 else content
                print(f"   Preview: {preview}\n")
        else:
            print("No conversations found")

    finally:
        db.close()

    # Demo 3: Statistics
    print("\n📝 Demo 3: Conversation statistics")
    print("-" * 70)

    stats = await get_conversation_stats()

    print(f"Total conversations: {stats['total_conversations']}")
    print(f"With embeddings: {stats['with_embeddings']}")
    print(f"Embedding coverage: {stats['embedding_coverage']:.1f}%")
    print(f"Recent (7 days): {stats['recent_conversations']}")

    if stats["projects"]:
        print("\nProjects with conversations:")
        for project in sorted(stats["projects"]):
            print(f"   • {project}")

    # Demo 4: Recent conversations
    print("\n📝 Demo 4: Recent conversations")
    print("-" * 70)

    db = ReflectionDatabase()
    await db.initialize()
    try:
        results = await db._execute_query(
            """SELECT id, project, timestamp
            FROM conversations
            ORDER BY timestamp DESC
            LIMIT 5"""
        )

        print(f"Showing last {len(results)} conversation(s):\n")
        for i, row in enumerate(results, 1):
            conv_id, project, timestamp = row
            print(f"{i}. {conv_id[:12]}...")
            print(f"   Project: {project}")
            print(f"   Time: {timestamp}")
            print()

    finally:
        db.close()

    print("=" * 70)
    print("✅ Demonstration complete!")
    print("=" * 70)

    print("\n💡 Tips:")
    print("   - Use /checkpoint to automatically store conversations")
    print("   - Use search_conversations MCP tool for semantic search")
    print("   - Configure settings to control automatic storage")
    print("   - View statistics with get_conversation_statistics MCP tool")


async def main() -> int:
    """Run the demonstration."""
    try:
        await demo_conversation_storage()
        return 0
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
