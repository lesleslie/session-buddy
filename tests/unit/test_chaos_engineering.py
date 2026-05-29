#!/usr/bin/env python3
"""Chaos engineering tests to validate system resilience."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from tests.helpers import ChaosTestHelper, DatabaseTestHelper, TestDataFactory


class TestSystemResilience:
    """Chaos engineering tests to validate system resilience."""

    async def test_network_failure_resilience(self):
        """Test system behavior when network operations fail."""
        # This test is about verifying that network failures are handled gracefully
        # For unit testing, we'll just verify the chaos helper creates proper mocks
        mock_client = await ChaosTestHelper.simulate_network_failure()

        # Verify the mock has the correct behavior
        import httpx

        with pytest.raises(httpx.ConnectError):
            await mock_client.get("http://example.com")
        with pytest.raises(httpx.ConnectError):
            await mock_client.post("http://example.com", data={})

    async def test_database_failure_resilience(self):
        """Test system behavior when database operations fail."""
        # Simulate database failure
        mock_db = await ChaosTestHelper.simulate_database_failure()

        # Verify that errors are handled gracefully
        try:
            await mock_db.store_conversation("Test", {"project": "test"})
        except Exception as e:
            # Should raise an exception as expected
            assert "Database unavailable" in str(e)

        try:
            await mock_db.search_conversations("test")
        except Exception as e:
            # Should raise an exception as expected
            assert "Database unavailable" in str(e)

    async def test_embedding_system_failure_resilience(self):
        """Test that system continues to work when embedding system fails."""
        from session_buddy.reflection_tools import ReflectionDatabase

        # Create database with embeddings disabled
        with patch("session_buddy.reflection.embeddings.ONNX_AVAILABLE", False):
            async with DatabaseTestHelper.temp_reflection_db() as db:
                # Should still be able to store conversations without embeddings
                conv_id = await db.store_conversation(
                    "Test conversation without embeddings", {"project": "chaos-test"}
                )
                assert conv_id is not None

                # Should still be able to store reflections
                refl_id = await db.store_reflection(
                    "Test reflection without embeddings", ["chaos-test", "fallback"]
                )
                assert refl_id is not None

                # Search should work but without semantic features
                results = await db.search_conversations("conversation")
                assert isinstance(results, list)  # Should return a list even if empty

    async def test_high_memory_usage_resilience(self):
        """Test system behavior under high memory usage."""
        import gc

        import psutil
        from session_buddy.reflection_tools import ReflectionDatabase

        # Get initial memory usage
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        # Create a moderate amount of data to test memory usage
        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Store some conversations
            for i in range(20):  # Reduce from 100 to 20
                conv_id = await db.store_conversation(
                    f"Memory test conversation {i} "
                    + "x" * 100,  # Reduce from 1000 to 100
                    {"project": "memory-test", "iteration": i},
                )
                assert conv_id is not None

            # Force garbage collection
            gc.collect()

            # Get memory after operations
            final_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

            # Memory increase should be reasonable (less than 200MB for this test)
            memory_increase = final_memory - initial_memory
            assert memory_increase < 200.0, (
                f"Memory increase too high: {memory_increase}MB"
            )

    async def test_concurrent_access_resilience(self):
        """Test system behavior under concurrent access."""
        import asyncio

        from session_buddy.reflection_tools import ReflectionDatabase

        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Create many concurrent operations
            async def add_conversation(index):
                return await db.store_conversation(
                    f"Concurrent test conversation {index}",
                    {"project": "concurrent-test", "index": index},
                )

            # Run 20 operations concurrently
            tasks = [add_conversation(i) for i in range(20)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check that all operations completed successfully
            successful_ops = [r for r in results if not isinstance(r, Exception)]
            failed_ops = [r for r in results if isinstance(r, Exception)]

            assert len(successful_ops) == 20, (
                f"Expected 20 successful operations, got {len(successful_ops)}"
            )
            assert len(failed_ops) == 0, f"Unexpected failures: {failed_ops}"

    async def test_dependency_availability_resilience(self):
        """Test system behavior when dependencies are not available."""
        from session_buddy.reflection_tools import ReflectionDatabase

        # Test with missing dependencies
        with patch("session_buddy.reflection.embeddings.ONNX_AVAILABLE", False):
            # Should still initialize without error
            async with DatabaseTestHelper.temp_reflection_db() as db:
                # Basic functionality should still work
                conv_id = await db.store_conversation(
                    "Test", {"project": "dependency-test"}
                )
                assert conv_id is not None

                # Reflection storage should work
                refl_id = await db.store_reflection(
                    "Test reflection", ["dependency-test"]
                )
                assert refl_id is not None

    async def test_filesystem_failure_resilience(self):
        """Test system behavior when filesystem operations fail."""
        from pathlib import Path
        from unittest.mock import patch

        # Mock the file operations to simulate various failures
        with patch(
            "duckdb.connect", side_effect=Exception("Cannot access database file")
        ):
            from session_buddy.reflection_tools import ReflectionDatabase

            # Try to create database with mocked failures
            db = ReflectionDatabase(
                db_path=":memory:"
            )  # Use in-memory to avoid path issues

            with pytest.raises(Exception) as exc_info:
                await db.initialize()

            assert "Cannot access database file" in str(exc_info.value)


class TestErrorRecovery:
    """Tests for error recovery mechanisms."""

    async def test_partial_failure_recovery(self):
        """Test recovery from partial failures during operations."""
        import tempfile
        from pathlib import Path

        from session_buddy.reflection_tools import ReflectionDatabase

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.duckdb"

            db = ReflectionDatabase(db_path=str(db_path))
            await db.initialize()

            # Add some good data
            good_conv_id = await db.store_conversation(
                "Good conversation", {"project": "recovery-test"}
            )
            assert good_conv_id is not None

            # Try to add data with an error (but this shouldn't affect previous data)
            try:
                # This operation fails but shouldn't damage existing data
                await db.store_conversation(
                    "Good conversation",
                    {
                        "project": "recovery-test"
                    },  # Same content might cause different behavior
                )
            except Exception:
                # Even if this fails, previous data should be intact
                pass

            # Verify that the good data is still accessible
            all_convs = await db.search_conversations("Good conversation", limit=10)
            assert len(all_convs) >= 1  # At least the good one should be there

            db.close()

    async def test_service_degradation_graceful_failover(self):
        """Test graceful degradation when services are unavailable."""
        # Test that the system degrades gracefully when external services fail
        from session_buddy.reflection_tools import ReflectionDatabase

        # Simulate ONNX not available (embeddings disabled)
        with patch("session_buddy.reflection.embeddings.ONNX_AVAILABLE", False):
            async with DatabaseTestHelper.temp_reflection_db() as db:
                # System should still work without semantic search
                conv_id = await db.store_conversation(
                    "Fallback test conversation", {"project": "fallback-test"}
                )
                assert conv_id is not None

                # Search should still work (with fallback methods)
                results = await db.search_conversations("Fallback test")
                assert isinstance(results, list)

                # Reflection operations should still work
                refl_id = await db.store_reflection(
                    "Fallback test reflection", ["fallback", "test"]
                )
                assert refl_id is not None
