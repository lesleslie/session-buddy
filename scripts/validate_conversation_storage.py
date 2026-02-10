#!/usr/bin/env python3
"""Quick validation script for conversation storage functionality.

This script demonstrates that conversation storage is working correctly
by:
1. Storing a test conversation
2. Verifying it in the database
3. Testing semantic search
4. Displaying statistics
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> int:
    """Validate conversation storage functionality."""
    print("\n" + "=" * 70)
    print("Conversation Storage Validation")
    print("=" * 70)

    from session_buddy.core.conversation_storage import (
        get_conversation_stats,
        store_conversation_checkpoint,
    )
    from session_buddy.core.session_manager import SessionLifecycleManager
    from session_buddy.reflection.database import ReflectionDatabase

    # Step 1: Store a test conversation
    print("\n📝 Step 1: Storing test conversation...")
    manager = SessionLifecycleManager()
    manager.current_project = "validation-test"

    result = await store_conversation_checkpoint(
        manager,
        checkpoint_type="validation",
        quality_score=75,
        is_manual=True,
    )

    if result["success"]:
        print(f"✅ Conversation stored: {result['conversation_id']}")
    else:
        print(f"❌ Storage failed: {result.get('error')}")
        return 1

    # Step 2: Verify in database
    print("\n📝 Step 2: Verifying in database...")
    db = ReflectionDatabase()
    await db.initialize()
    try:
        count = await db._get_conversation_count()
        print(f"✅ Total conversations: {count}")

        if count > 0:
            # Get recent conversations
            results = await db._execute_query(
                """SELECT id, project, timestamp
                FROM conversations
                ORDER BY timestamp DESC
                LIMIT 5"""
            )

            print("\n📋 Recent conversations:")
            for i, row in enumerate(results, 1):
                conv_id, project, timestamp = row
                print(f"   {i}. {conv_id[:8]}... - {project} - {timestamp}")

        # Step 3: Test semantic search
        print("\n📝 Step 3: Testing semantic search...")
        search_results = await db.search_conversations(
            query="validation test quality",
            limit=3,
            min_score=0.1,
        )

        if search_results:
            print(f"✅ Found {len(search_results)} result(s)")
            for i, result in enumerate(search_results, 1):
                score = result.get("score", 0) * 100
                print(f"   {i}. Score: {score:.1f}%")
        else:
            print("ℹ️  No search results (may need more data)")

    finally:
        db.close()

    # Step 4: Display statistics
    print("\n📝 Step 4: Conversation statistics...")
    stats = await get_conversation_stats()

    print(f"   Total conversations: {stats['total_conversations']}")
    print(f"   With embeddings: {stats['with_embeddings']}")
    print(f"   Coverage: {stats['embedding_coverage']:.1f}%")
    print(f"   Recent (7d): {stats['recent_conversations']}")

    if stats["projects"]:
        print(f"   Projects: {', '.join(stats['projects'][:5])}")

    # Final status
    print("\n" + "=" * 70)
    if stats["total_conversations"] > 0 and stats["embedding_coverage"] > 0:
        print("✅ Conversation storage is working correctly!")
        print("=" * 70)
        return 0
    else:
        print("❌ Conversation storage may have issues")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
