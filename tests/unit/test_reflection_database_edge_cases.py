#!/usr/bin/env python3
"""Edge case tests for ReflectionDatabase operations.

Tests boundary conditions, error scenarios, and unusual inputs to ensure
robustness and proper error handling.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from session_buddy.reflection_tools import ReflectionDatabase


class TestReflectionDatabaseEdgeCases:
    """Edge case tests for ReflectionDatabase operations."""

    @pytest.mark.asyncio
    async def test_empty_content_handling(self):
        """Test handling of empty content in reflections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test empty string content
                reflection_id = await db.store_reflection("", [], "test-project")
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["content"] == ""

                # Test whitespace-only content
                reflection_id2 = await db.store_reflection("   ", [], "test-project")
                retrieved2 = await db.get_reflection(reflection_id2)
                assert retrieved2["content"] == "   "

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_very_long_content(self):
        """Test handling of very long content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test very long content (10KB)
                long_content = "A" * 10000
                reflection_id = await db.store_reflection(
                    long_content, [], "test-project"
                )
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["content"] == long_content
                assert len(retrieved["content"]) == 10000

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self):
        """Test handling of special characters in content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test content with special characters
                special_content = (
                    "Test with \"quotes\", 'apostrophes', and \n newlines\t tabs"
                )
                reflection_id = await db.store_reflection(
                    special_content, [], "test-project"
                )
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["content"] == special_content

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_unicode_content(self):
        """Test handling of unicode content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test unicode content
                unicode_content = "Test with unicode: 你好世界 🌍 café naïve"
                reflection_id = await db.store_reflection(
                    unicode_content, [], "test-project"
                )
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["content"] == unicode_content

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_empty_project_name(self):
        """Test handling of empty project names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test empty project name
                reflection_id = await db.store_reflection("Test content", [], "")
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["project"] == ""

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_very_long_project_name(self):
        """Test handling of very long project names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test very long project name
                long_project = "A" * 200
                reflection_id = await db.store_reflection(
                    "Test content", [], long_project
                )
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["project"] == long_project

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_empty_tags(self):
        """Test handling of empty tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test empty tags list
                reflection_id = await db.store_reflection(
                    "Test content", [], "test-project"
                )
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved["tags"] == []

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_many_tags(self):
        """Test handling of many tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test many tags
                many_tags = [f"tag_{i}" for i in range(50)]
                reflection_id = await db.store_reflection(
                    "Test content", many_tags, "test-project"
                )
                retrieved = await db.get_reflection(reflection_id)
                assert len(retrieved["tags"]) == 50
                assert set(retrieved["tags"]) == set(many_tags)

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_duplicate_tags(self):
        """Test handling of duplicate tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Test duplicate tags
                duplicate_tags = ["tag1", "tag2", "tag1", "tag3", "tag2"]
                reflection_id = await db.store_reflection(
                    "Test content", duplicate_tags, "test-project"
                )
                retrieved = await db.get_reflection(reflection_id)
                # Should preserve duplicates as they were provided
                assert len(retrieved["tags"]) == 5

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_empty_query(self):
        """Test search with empty query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store some test data
                await db.store_reflection("Test content 1", [], "test-project")
                await db.store_reflection("Test content 2", [], "test-project")

                # Search with empty query
                results = await db.search_reflections("", 10, "test-project")
                assert isinstance(results, list)
                # Empty query should return all reflections
                assert len(results) >= 2

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_very_long_query(self):
        """Test search with very long query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store test data
                await db.store_reflection("Test content", [], "test-project")

                # Search with very long query
                long_query = "A" * 1000
                results = await db.search_reflections(long_query, 10, "test-project")
                assert isinstance(results, list)

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_special_characters(self):
        """Test search with special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store test data
                await db.store_reflection(
                    "Test content with special chars: !@#$%^&*()", [], "test-project"
                )

                # Search with special characters
                results = await db.search_reflections("!@#$%^&*()", 10, "test-project")
                assert isinstance(results, list)

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_zero_limit(self):
        """Test search with zero limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store test data
                await db.store_reflection("Test content", [], "test-project")

                # Search with zero limit
                results = await db.search_reflections("content", 0, "test-project")
                assert isinstance(results, list)
                assert len(results) == 0

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_negative_limit(self):
        """Test search with negative limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store test data
                await db.store_reflection("Test content", [], "test-project")

                # Search with negative limit (should be treated as 0 or positive)
                results = await db.search_reflections("content", -1, "test-project")
                assert isinstance(results, list)

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_search_with_very_large_limit(self):
        """Test search with very large limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store test data
                for i in range(10):
                    await db.store_reflection(f"Test content {i}", [], "test-project")

                # Search with very large limit
                results = await db.search_reflections("content", 1000, "test-project")
                assert isinstance(results, list)
                assert len(results) <= 10  # Should not exceed available results

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_update_nonexistent_reflection(self):
        """Test updating a non-existent reflection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Try to update non-existent reflection
                fake_id = "nonexistent-id-12345"
                # This should not raise an exception, but should not affect anything
                await db.update_reflection(fake_id, "Updated content", ["updated"])

                # Verify no reflection exists with that ID
                retrieved = await db.get_reflection(fake_id)
                assert retrieved is None

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_reflection(self):
        """Test deleting a non-existent reflection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Try to delete non-existent reflection
                fake_id = "nonexistent-id-12345"
                # This should not raise an exception
                await db.delete_reflection(fake_id)

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent database operations."""
        import asyncio

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:

                async def store_reflection(i):
                    content = f"Concurrent test content {i}"
                    return await db.store_reflection(
                        content, ["concurrent"], "test-project"
                    )

                # Run multiple operations concurrently
                tasks = [store_reflection(i) for i in range(10)]
                reflection_ids = await asyncio.gather(*tasks)

                # Verify all reflections were stored
                assert len(reflection_ids) == 10

                # Verify all can be retrieved
                for reflection_id in reflection_ids:
                    retrieved = await db.get_reflection(reflection_id)
                    assert retrieved is not None

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_database_recovery_after_crash(self):
        """Test database recovery after simulated crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create and populate database
            db1 = ReflectionDatabase(str(db_path))
            await db1.initialize()

            try:
                # Store some data
                for i in range(5):
                    await db1.store_reflection(
                        f"Test content {i}", ["test"], "test-project"
                    )

                # Close database (simulate crash)
                db1.close()

                # Reopen database
                db2 = ReflectionDatabase(str(db_path))
                await db2.initialize()

                try:
                    # Verify data is still there
                    stats = await db2.get_stats()
                    assert stats["total_reflections"] >= 5

                    # Verify reflections can be retrieved
                    results = await db2.search_reflections(
                        "content", 10, "test-project"
                    )
                    assert len(results) >= 5

                finally:
                    db2.close()

            finally:
                # Clean up first database if it wasn't closed properly
                if hasattr(db1, "conn") and db1.conn is not None:
                    db1.close()

    @pytest.mark.asyncio
    async def test_multiple_projects_with_same_content(self):
        """Test multiple projects with same content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store same content in different projects
                content = "Identical content"
                project1 = "project-1"
                project2 = "project-2"

                id1 = await db.store_reflection(content, ["test"], project1)
                id2 = await db.store_reflection(content, ["test"], project2)

                # Verify both exist and are separate
                retrieved1 = await db.get_reflection(id1)
                retrieved2 = await db.get_reflection(id2)

                assert retrieved1 is not None
                assert retrieved2 is not None
                assert retrieved1["id"] != retrieved2["id"]
                assert retrieved1["project"] == project1
                assert retrieved2["project"] == project2
                assert retrieved1["content"] == retrieved2["content"]

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_empty_search_results(self):
        """Test handling of empty search results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Search in empty database
                results = await db.search_reflections("nonexistent", 10, "test-project")
                assert isinstance(results, list)
                assert len(results) == 0

            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_stats_with_empty_database(self):
        """Test statistics with empty database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Get stats from empty database
                stats = await db.get_stats()
                assert stats["total_reflections"] == 0
                assert stats["total_projects"] == 0
                assert isinstance(stats["projects"], list)

            finally:
                db.close()
