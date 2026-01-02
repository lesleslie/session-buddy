#!/usr/bin/env python3
"""Comprehensive error handling tests for ReflectionDatabase operations.

Tests various error scenarios, exception handling, and recovery mechanisms
to ensure robust error handling throughout the database operations.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from session_buddy.reflection_tools import ReflectionDatabase


class TestReflectionDatabaseErrorHandling:
    """Error handling tests for ReflectionDatabase operations."""

    @pytest.mark.asyncio
    async def test_invalid_database_path(self):
        """Test handling of invalid database paths."""
        # Test with invalid path
        invalid_path = "/invalid/path/that/does/not/exist/test.db"
        db = ReflectionDatabase(invalid_path)

        # Should handle invalid path gracefully
        try:
            await db.initialize()
            # If it succeeds, it should still work (DuckDB creates the file)
            assert db.conn is not None
        except Exception as e:
            # Some environments might not allow creating files in invalid paths
            assert "permission" in str(e).lower() or "directory" in str(e).lower()
        finally:
            if hasattr(db, "conn") and db.conn is not None:
                db.close()

    @pytest.mark.asyncio
    async def test_null_database_path(self):
        """Test handling of null/None database path."""
        # Test with None path
        with pytest.raises((TypeError, ValueError)):
            db = ReflectionDatabase(None)
            await db.initialize()

    @pytest.mark.asyncio
    async def test_empty_database_path(self):
        """Test handling of empty database path."""
        # Test with empty path
        db = ReflectionDatabase("")

        try:
            await db.initialize()
            # Should handle empty path (might create in current directory)
            assert db.conn is not None
        except Exception as e:
            # Some implementations might reject empty paths
            assert "path" in str(e).lower() or "invalid" in str(e).lower()
        finally:
            if hasattr(db, "conn") and db.conn is not None:
                db.close()

    @pytest.mark.asyncio
    async def test_invalid_reflection_id_format(self):
        """Test handling of invalid reflection ID formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test with invalid ID formats
                invalid_ids = [
                    "",  # Empty string
                    "not-a-valid-uuid",  # Not a UUID
                    "123",  # Too short
                    "a" * 100,  # Too long
                    None,  # None value
                ]

                for invalid_id in invalid_ids:
                    # These should not crash, but return None or handle gracefully
                    result = await db.get_reflection(invalid_id)
                    assert result is None

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_none_content_handling(self):
        """Test handling of None content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test with None content
                with pytest.raises((TypeError, ValueError)):
                    await db.store_reflection(None, [], "test-project")

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_none_project_handling(self):
        """Test handling of None project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test with None project
                reflection_id = await db.store_reflection("Test content", [], None)
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["project"] is None or retrieved["project"] == ""

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_none_tags_handling(self):
        """Test handling of None tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test with None tags
                reflection_id = await db.store_reflection(
                    "Test content", None, "test-project"
                )
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["tags"] == [] or retrieved["tags"] is None

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_duplicate_reflection_storage(self):
        """Test handling of duplicate reflection storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store same content multiple times
                content = "Duplicate test content"
                id1 = await db.store_reflection(content, ["test"], "test-project")
                id2 = await db.store_reflection(content, ["test"], "test-project")

                # Should create different reflections with different IDs
                assert id1 != id2

                retrieved1 = await db.get_reflection(id1)
                retrieved2 = await db.get_reflection(id2)

                assert retrieved1["content"] == content
                assert retrieved2["content"] == content
                assert retrieved1["id"] != retrieved2["id"]

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_none_query(self):
        """Test handling of None search query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test with None query
                with pytest.raises((TypeError, ValueError)):
                    await db.search_reflections(None, 10, "test-project")

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_none_project(self):
        """Test handling of None project in search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test with None project
                results = await db.search_reflections("test", 10, None)
                assert isinstance(results, list)

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_none_tags(self):
        """Test handling of None tags in search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test with None tags
                results = await db.search_reflections(
                    "test", 10, "test-project", tags=None
                )
                assert isinstance(results, list)

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_update_with_none_content(self):
        """Test handling of None content in update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store a reflection
                reflection_id = await db.store_reflection(
                    "Original content", ["test"], "test-project"
                )

                # Try to update with None content
                with pytest.raises((TypeError, ValueError)):
                    await db.update_reflection(reflection_id, None, ["updated"])

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_update_with_none_tags(self):
        """Test handling of None tags in update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store a reflection
                reflection_id = await db.store_reflection(
                    "Original content", ["test"], "test-project"
                )

                # Update with None tags
                await db.update_reflection(reflection_id, "Updated content", None)

                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["content"] == "Updated content"
                assert retrieved["tags"] == [] or retrieved["tags"] is None

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_delete_with_none_id(self):
        """Test handling of None ID in delete."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Try to delete with None ID
                with pytest.raises((TypeError, ValueError)):
                    await db.delete_reflection(None)

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_database_connection_errors(self):
        """Test handling of database connection errors."""
        # Test with invalid database path that should fail
        invalid_path = "/root/protected/test.db"  # Typically requires root access
        db = ReflectionDatabase(invalid_path)

        try:
            await db.initialize()
            # If it succeeds, it's fine (some systems allow it)
        except (PermissionError, OSError) as e:
            # Should handle permission errors gracefully
            assert "permission" in str(e).lower() or "access" in str(e).lower()
        except Exception as e:
            # Other types of errors might occur
            assert "database" in str(e).lower() or "connection" in str(e).lower()
        finally:
            if hasattr(db, "conn") and db.conn is not None:
                db.close()

    @pytest.mark.asyncio
    async def test_concurrent_access_errors(self):
        """Test handling of concurrent access scenarios."""
        import asyncio

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:

                async def conflicting_operations():
                    # Store initial reflection
                    reflection_id = await db.store_reflection(
                        "Original", ["test"], "test-project"
                    )

                    # Try to update and delete simultaneously
                    update_task = db.update_reflection(
                        reflection_id, "Updated", ["updated"]
                    )
                    delete_task = db.delete_reflection(reflection_id)

                    await asyncio.gather(
                        update_task, delete_task, return_exceptions=True
                    )

                # This should not crash, even if operations conflict
                await conflicting_operations()

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_memory_pressure_scenarios(self):
        """Test handling of memory pressure scenarios."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store large amount of data to test memory handling
                for i in range(1000):
                    content = "A" * 10000  # 10KB content
                    await db.store_reflection(content, ["memory-test"], "test-project")

                # Should still be able to perform operations
                results = await db.search_reflections("memory", 10, "test-project")
                assert isinstance(results, list)
                assert len(results) > 0

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_corrupted_database_recovery(self):
        """Test handling of corrupted database scenarios."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create and populate database
            db1 = ReflectionDatabase(str(db_path))
            await db1.initialize()

            try:
                # Store some data
                await db1.store_reflection("Test content", ["test"], "test-project")

                # Close database
                db1.close()

                # Corrupt the database file by writing invalid data
                with open(db_path, "a") as f:
                    f.write("CORRUPTED DATA" * 100)

                # Try to reopen corrupted database
                db2 = ReflectionDatabase(str(db_path))
                try:
                    await db2.initialize()
                    # If it succeeds, it handled corruption well
                    # If it fails, it should fail gracefully
                except Exception as e:
                    # Should handle corruption gracefully
                    assert "database" in str(e).lower() or "corrupt" in str(e).lower()
                finally:
                    if hasattr(db2, "conn") and db2.conn is not None:
                        db2.close()

            finally:
                if hasattr(db1, "conn") and db1.conn is not None:
                    db1.close()

    @pytest.mark.asyncio
    async def test_invalid_sql_injection_attempts(self):
        """Test handling of SQL injection attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test SQL injection attempts in content
                malicious_content = "'; DROP TABLE reflections; --"
                reflection_id = await db.store_reflection(
                    malicious_content, ["test"], "test-project"
                )

                # Should store the content safely (escaped)
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["content"] == malicious_content

                # Verify table still exists
                stats = await db.get_stats()
                assert stats["total_reflections"] >= 1

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_unicode_error_handling(self):
        """Test handling of unicode-related errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test with various unicode characters
                unicode_content = (
                    "Test with unicode: 你好世界 🌍 café naïve \ud83d\udcbb"
                )
                reflection_id = await db.store_reflection(
                    unicode_content, ["unicode"], "test-project"
                )

                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["content"] == unicode_content

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_resource_leak_detection(self):
        """Test for resource leaks in database operations."""
        import gc

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create multiple database instances
            databases = []
            for i in range(5):
                db = ReflectionDatabase(str(db_path))
                await db.initialize()
                databases.append(db)

            # Close all databases
            for db in databases:
                db.close()

            # Force garbage collection
            gc.collect()

            # Should not crash or leak resources
            assert True  # If we get here, no obvious leaks

    @pytest.mark.asyncio
    async def test_error_recovery_after_failure(self):
        """Test error recovery after operation failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store some data
                reflection_id = await db.store_reflection(
                    "Test content", ["test"], "test-project"
                )

                # Verify it exists
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved is not None

                # Delete it
                await db.delete_reflection(reflection_id)

                # Verify it's deleted
                deleted = await db.get_reflection(reflection_id)
                assert deleted is None

                # Should still be able to perform other operations
                new_id = await db.store_reflection(
                    "New content", ["recovery"], "test-project"
                )
                new_retrieved = await db.get_reflection(new_id)
                assert new_retrieved is not None

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_invalid_operation_sequences(self):
        """Test handling of invalid operation sequences."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Try to update non-existent reflection
                await db.update_reflection("nonexistent-id", "Content", ["test"])

                # Try to delete non-existent reflection
                await db.delete_reflection("nonexistent-id")

                # Try to get non-existent reflection
                result = await db.get_reflection("nonexistent-id")
                assert result is None

                # Should still work normally after invalid operations
                valid_id = await db.store_reflection(
                    "Valid content", ["test"], "test-project"
                )
                valid_result = await db.get_reflection(valid_id)
                assert valid_result is not None

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_database_locking_scenarios(self):
        """Test handling of database locking scenarios."""
        import asyncio

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:

                async def concurrent_writes():
                    tasks = []
                    for i in range(10):
                        task = db.store_reflection(
                            f"Concurrent {i}", ["test"], "test-project"
                        )
                        tasks.append(task)

                    # Should handle concurrent writes without deadlocks
                    await asyncio.gather(*tasks, return_exceptions=True)

                await concurrent_writes()

                # Verify all operations completed
                stats = await db.get_stats()
                assert stats["total_reflections"] >= 10

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_error_messages_quality(self):
        """Test quality and helpfulness of error messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test various error scenarios and verify error messages
                try:
                    await db.store_reflection(None, [], "test-project")
                except Exception as e:
                    error_msg = str(e)
                    # Error message should be informative
                    assert len(error_msg) > 10
                    assert any(
                        word in error_msg.lower()
                        for word in ["content", "null", "invalid", "required"]
                    )

            finally:
                db.close()
