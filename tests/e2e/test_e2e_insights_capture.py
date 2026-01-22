#!/usr/bin/env python3
"""
End-to-end test for multi-point insight capture with deduplication.

This test validates:
1. Checkpoint captures insights from conversation
2. Session_end captures additional insights
3. Deduplication prevents duplicate captures
4. Database stores unique insights correctly
"""

import asyncio
from pathlib import Path

from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.adapters.reflection_adapter_oneiric import ReflectionDatabase
from session_buddy.adapters.settings import ReflectionAdapterSettings


async def test_multi_point_capture_with_deduplication(tmp_path, mock_settings):
    """Test multi-point capture workflow end-to-end.

    Uses the mock_settings fixture from conftest.py which provides a unique
    database path per test via pytest's tmp_path fixture.
    """

    print("🧪 Starting end-to-end multi-point capture test...\n")

    # Enable debug logging to see what's happening
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Get database path from the mock_settings fixture
    db_path = mock_settings.database_path

    # Initialize session manager (will use the mocked settings)
    manager = SessionLifecycleManager()

    # Simulate a conversation with insights
    conversation_with_insights = [
        {
            "role": "user",
            "content": "How should I handle database operations?",
        },
        {
            "role": "assistant",
            "content": """
You should use async/await patterns for database operations.

`★ Insight ─────────────────────────────────────`
Always use async/await for database operations to prevent blocking the event loop and maintain responsiveness
`─────────────────────────────────────────────────`

This pattern ensures your application remains responsive during I/O operations.
            """,
        },
        {
            "role": "user",
            "content": "What about type hints?",
        },
        {
            "role": "assistant",
            "content": """
Type hints improve code clarity and enable better IDE support.

`★ Insight ─────────────────────────────────────`
Use type hints for all function parameters and return values to improve code documentation and catch type errors early
`─────────────────────────────────────────────────`

This is especially important in larger codebases.
            """,
        },
    ]

    # Set up session context
    manager.session_context = {
        "conversation_id": "test-conv-123",
        "conversation_history": conversation_with_insights,
        "working_directory": str(tmp_path),
    }
    manager.current_project = "test-project"

    # Track captured hashes across operations
    initial_hashes = set()

    # === TEST 1: Checkpoint Extraction ===
    print("📍 Step 1: Testing checkpoint extraction...")
    checkpoint_result = await manager.checkpoint_session(working_directory=str(tmp_path))

    # Extract hashes after checkpoint
    checkpoint_hashes = manager._captured_insight_hashes.copy()
    print(f"   ✓ Checkpoint captured {len(checkpoint_hashes)} unique insights")
    assert len(checkpoint_hashes) == 2, "Checkpoint should capture 2 insights"
    assert checkpoint_result["insights_extracted"] == 2, "Checkpoint result should show 2 insights extracted"

    # Verify insights in database (using same db_path as mock settings)
    async with ReflectionDatabase(
        collection_name="default",
        settings=ReflectionAdapterSettings(
            database_path=db_path,
            collection_name="default",
        ),
    ) as db:
        all_insights = await db.search_insights("*", limit=100)
        print(f"   ✓ Database has {len(all_insights)} insights after checkpoint")
        assert len(all_insights) == 2, "Database should have 2 insights"

        # Verify content
        insights_content = [insight["content"] for insight in all_insights]
        assert any("async/await" in c for c in insights_content), "Should capture async/await insight"
        assert any("type hints" in c for c in insights_content), "Should capture type hints insight"

    # === TEST 2: Session End Extraction (with same insights - should be deduplicated) ===
    print("\n📍 Step 2: Testing session_end extraction (with deduplication)...")
    session_end_result = await manager.end_session(working_directory=str(tmp_path))

    # Extract hashes after session_end
    session_end_hashes = manager._captured_insight_hashes.copy()
    print(f"   ✓ Session end tracked {len(session_end_hashes)} total hashes")
    assert len(session_end_hashes) == 2, "Should still have only 2 unique insights (no duplicates)"
    assert session_end_result["summary"]["insights_extracted"] == 0, "Session end should capture 0 new insights (all duplicates)"

    # Verify database still has only 2 insights (no duplicates)
    async with ReflectionDatabase(
        collection_name="default",
        settings=ReflectionAdapterSettings(
            database_path=db_path,
            collection_name="default",
        ),
    ) as db:
        all_insights = await db.search_insights("*", limit=100)
        print(f"   ✓ Database still has {len(all_insights)} insights (no duplicates stored)")
        assert len(all_insights) == 2, "Database should still have only 2 insights"

    # === TEST 3: Session End with NEW insights ===
    print("\n📍 Step 3: Testing session_end with NEW insights...")

    # Create new session manager with NEW conversation
    manager2 = SessionLifecycleManager()
    manager2.session_context = {
        "conversation_id": "test-conv-456",
        "conversation_history": [
            {
                "role": "user",
                "content": "How do I handle errors?",
            },
            {
                "role": "assistant",
                "content": """
You should use try-except blocks for proper error handling.

`★ Insight ─────────────────────────────────────`
Always wrap I/O operations in try-except blocks to handle potential failures gracefully and provide meaningful error messages
`─────────────────────────────────────────────────`

This prevents unexpected crashes.
                """,
            },
            {
                "role": "user",
                "content": "What about the previous insights?",  # This might trigger duplicate capture
            },
            {
                "role": "assistant",
                "content": """
As mentioned before:
- Use async/await for database operations
- Use type hints for better code clarity

`★ Insight ─────────────────────────────────────`
Always validate user input to prevent security vulnerabilities and ensure data integrity
`─────────────────────────────────────────────────`

This is critical for web applications.
                """,
            },
        ],
        "working_directory": str(tmp_path),
    }
    manager2.current_project = "test-project"

    # Track that we're starting fresh
    initial_hashes = set()

    # End session (should capture 2 new insights, skip 2 duplicates from previous session)
    session_end_result2 = await manager2.end_session(working_directory=str(tmp_path))

    print(f"   ✓ Session end captured {session_end_result2['summary']['insights_extracted']} new insights")
    assert session_end_result2["summary"]["insights_extracted"] == 2, "Should capture 2 new insights"

    # Verify database now has 4 unique insights total
    async with ReflectionDatabase(
        collection_name="default",
        settings=ReflectionAdapterSettings(
            database_path=db_path,
            collection_name="default",
        ),
    ) as db:
        all_insights = await db.search_insights("*", limit=100)
        print(f"   ✓ Database now has {len(all_insights)} total insights (2 from checkpoint + 2 new)")
        assert len(all_insights) == 4, "Database should have 4 unique insights total"

        # Verify no duplicates in content
        insights_content = [insight["content"] for insight in all_insights]
        unique_content = set(insights_content)
        print(f"   ✓ All {len(unique_content)} insights are unique (no duplicates)")
        assert len(unique_content) == 4, "All insights should be unique"

        # Verify specific insights
        assert any("async/await" in c for c in insights_content), "Should have async/await insight"
        assert any("type hints" in c for c in insights_content), "Should have type hints insight"
        assert any("try-except" in c for c in insights_content), "Should have try-except insight"
        assert any("validate user input" in c for c in insights_content), "Should have validation insight"

    print("\n✅ All end-to-end tests passed!")
    print("\n📊 Test Summary:")
    print("   ✓ Checkpoint captured insights correctly")
    print("   ✓ Session end deduplicated previously captured insights")
    print("   ✓ Session end captured new insights")
    print("   ✓ Database stored all unique insights without duplicates")
    print("   ✓ Multi-point capture with deduplication working correctly")


if __name__ == "__main__":
    asyncio.run(test_multi_point_capture_with_deduplication())
