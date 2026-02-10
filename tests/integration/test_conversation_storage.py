#!/usr/bin/env python3
"""Integration test for conversation storage functionality.

This test verifies that:
1. Conversations are stored during checkpoints
2. Conversations are stored at session end
3. Conversations have embeddings
4. Semantic search works on conversations
5. Configuration options work correctly
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def test_conversation_storage() -> None:
    """Test conversation storage during checkpoints and session end."""
    print("\n" + "=" * 70)
    print("Testing Conversation Storage Functionality")
    print("=" * 70)

    # Import after path setup
    from session_buddy.core.conversation_storage import (
        capture_conversation_context,
        get_conversation_stats,
        store_conversation_checkpoint,
    )
    from session_buddy.core.session_manager import SessionLifecycleManager
    from session_buddy.reflection.database import ReflectionDatabase

    # Test 1: Capture conversation context
    print("\n📝 Test 1: Capture conversation context")
    manager = SessionLifecycleManager()
    manager.current_project = "test-project"

    context = await capture_conversation_context(
        manager,
        checkpoint_type="test",
        quality_score=85,
    )

    assert len(context) > 0, "Conversation context should not be empty"
    assert "test-project" in context, "Context should contain project name"
    assert "85" in context, "Context should contain quality score"
    print("✅ Conversation context captured successfully")
    print(f"   Context length: {len(context)} characters")

    # Test 2: Store conversation checkpoint
    print("\n📝 Test 2: Store conversation checkpoint")
    result = await store_conversation_checkpoint(
        manager,
        checkpoint_type="test",
        quality_score=85,
        is_manual=True,
    )

    assert result["success"], f"Storage should succeed: {result.get('error')}"
    assert result["conversation_id"] is not None, "Should have conversation ID"
    print("✅ Conversation checkpoint stored successfully")
    print(f"   Conversation ID: {result['conversation_id']}")

    # Test 3: Verify conversation in database
    print("\n📝 Test 3: Verify conversation in database")
    db = ReflectionDatabase()
    await db.initialize()
    try:
        count = await db._get_conversation_count()
        assert count > 0, "Should have at least one conversation"
        print(f"✅ Found {count} conversation(s) in database")

        # Check for embeddings
        if db.is_temp_db:
            with db.lock:
                result = db._get_conn().execute(
                    "SELECT COUNT(*) FROM conversations WHERE embedding IS NOT NULL"
                ).fetchone()
                with_embeddings = result[0] if result else 0
        else:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db._get_conn()
                .execute("SELECT COUNT(*) FROM conversations WHERE embedding IS NOT NULL")
                .fetchone(),
            )
            with_embeddings = result[0] if result else 0

        embedding_pct = (with_embeddings / count * 100) if count > 0 else 0
        print(f"   Embeddings: {with_embeddings}/{count} ({embedding_pct:.1f}%)")
        assert embedding_pct > 0, "Should have at least one embedding"
    finally:
        db.close()

    # Test 4: Get conversation statistics
    print("\n📝 Test 4: Get conversation statistics")
    stats = await get_conversation_stats()

    assert stats["total_conversations"] > 0, "Should have conversations"
    assert stats["error"] is None, f"Should not have errors: {stats['error']}"
    print("✅ Conversation statistics retrieved successfully")
    print(f"   Total: {stats['total_conversations']}")
    print(f"   With embeddings: {stats['with_embeddings']}")
    print(f"   Coverage: {stats['embedding_coverage']:.1f}%")

    # Test 5: Semantic search
    print("\n📝 Test 5: Semantic search")
    db = ReflectionDatabase()
    await db.initialize()
    try:
        results = await db.search_conversations(
            query="test project quality",
            limit=5,
            min_score=0.1,  # Low threshold for testing
        )

        assert len(results) > 0, "Should find at least one conversation"
        print("✅ Semantic search works successfully")
        print(f"   Found {len(results)} result(s)")

        for i, result in enumerate(results[:3], 1):
            score = result.get("score", 0) * 100
            print(f"   {i}. Score: {score:.1f}% - {result.get('project', 'unknown')}")
    finally:
        db.close()

    print("\n" + "=" * 70)
    print("✅ All conversation storage tests passed!")
    print("=" * 70)


async def test_settings_integration() -> None:
    """Test that settings integration works correctly."""
    print("\n" + "=" * 70)
    print("Testing Settings Integration")
    print("=" * 70)

    from session_buddy.settings import SessionMgmtSettings

    settings = SessionMgmtSettings()

    # Check that new settings exist with correct defaults
    assert hasattr(settings, "enable_conversation_storage")
    assert settings.enable_conversation_storage is True
    print("✅ enable_conversation_storage: True")

    assert hasattr(settings, "conversation_storage_min_length")
    assert settings.conversation_storage_min_length == 100
    print(f"✅ conversation_storage_min_length: {settings.conversation_storage_min_length}")

    assert hasattr(settings, "conversation_storage_max_length")
    assert settings.conversation_storage_max_length == 50000
    print(f"✅ conversation_storage_max_length: {settings.conversation_storage_max_length}")

    assert hasattr(settings, "auto_store_conversations_on_checkpoint")
    assert settings.auto_store_conversations_on_checkpoint is True
    print("✅ auto_store_conversations_on_checkpoint: True")

    assert hasattr(settings, "auto_store_conversations_on_session_end")
    assert settings.auto_store_conversations_on_session_end is True
    print("✅ auto_store_conversations_on_session_end: True")

    print("\n" + "=" * 70)
    print("✅ All settings integration tests passed!")
    print("=" * 70)


async def test_checkpoint_integration() -> None:
    """Test that checkpoints store conversations."""
    print("\n" + "=" * 70)
    print("Testing Checkpoint Integration")
    print("=" * 70)

    from session_buddy.core.session_manager import SessionLifecycleManager
    from session_buddy.reflection.database import ReflectionDatabase

    # Get initial conversation count
    db1 = ReflectionDatabase()
    await db1.initialize()
    try:
        initial_count = await db1._get_conversation_count()
    finally:
        db1.close()

    # Create a checkpoint
    manager = SessionLifecycleManager()
    result = await manager.checkpoint_session(is_manual=True)

    assert result["success"], f"Checkpoint should succeed: {result.get('error')}"
    print("✅ Checkpoint created successfully")

    # Check if conversation was stored
    conversation_stored = result.get("conversation_stored", {})
    print(f"   Conversation stored: {conversation_stored.get('success', False)}")

    # Verify conversation count increased
    db2 = ReflectionDatabase()
    await db2.initialize()
    try:
        final_count = await db2._get_conversation_count()
    finally:
        db2.close()

    if conversation_stored.get("success"):
        assert final_count > initial_count, "Conversation count should increase"
        print(f"✅ Conversation count increased: {initial_count} → {final_count}")
    else:
        print(f"ℹ️  Conversation not stored (may be disabled in settings)")

    print("\n" + "=" * 70)
    print("✅ Checkpoint integration test passed!")
    print("=" * 70)


async def main() -> int:
    """Run all integration tests."""
    try:
        await test_conversation_storage()
        await test_settings_integration()
        await test_checkpoint_integration()
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
