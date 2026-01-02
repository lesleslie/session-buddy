#!/usr/bin/env python3
"""Property-based tests for ReflectionDatabase using Hypothesis.

Uses Hypothesis to generate randomized test cases for database operations,
ensuring robustness across a wide range of input scenarios.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from session_buddy.reflection_tools import ReflectionDatabase


class TestReflectionDatabasePropertyBased:
    """Property-based tests for ReflectionDatabase operations."""

    @pytest.mark.asyncio
    @given(
        content=st.text(min_size=1, max_size=1000),
        project=st.text(
            min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
        ),
        tags=st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5),
    )
    @settings(max_examples=50, deadline=None)
    async def test_store_and_retrieve_reflection_properties(
        self, content: str, project: str, tags: list[str]
    ):
        """Test that storing and retrieving reflections preserves content and structure.

        Property: Any valid reflection content should be stored and retrieved correctly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store reflection
                reflection_id = await db.store_reflection(content, tags)

                # Retrieve reflection
                retrieved = await db.get_reflection(reflection_id)

                # Verify properties
                assert retrieved is not None
                assert retrieved["content"] == content
                assert set(retrieved["tags"]) == set(tags)
                assert "timestamp" in retrieved

            finally:
                db.close()

    @pytest.mark.asyncio
    @given(
        search_query=st.text(min_size=1, max_size=100),
        project=st.text(
            min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
        ),
        limit=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=30, deadline=None)
    async def test_search_reflections_properties(
        self, search_query: str, project: str, limit: int
    ):
        """Test that search operations return consistent results.

        Property: Search results should be consistent and properly structured.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store some test data
                for i in range(5):
                    content = f"Test reflection {i} for {search_query}"
                    await db.store_reflection(content, ["test"], project)

                # Perform search
                results = await db.search_reflections(search_query, limit)

                # Verify properties
                assert isinstance(results, list)
                assert len(results) <= limit

                for result in results:
                    assert "content" in result
                    assert "score" in result
                    assert "timestamp" in result
                    assert 0.0 <= result["score"] <= 1.0

            finally:
                db.close()

    @pytest.mark.asyncio
    @given(
        content=st.text(min_size=1, max_size=1000),
        project=st.text(
            min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
        ),
        num_reflections=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20, deadline=None)
    async def test_bulk_operations_properties(
        self, content: str, project: str, num_reflections: int
    ):
        """Test that bulk operations maintain data integrity.

        Property: Bulk operations should preserve all data correctly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store multiple reflections
                reflection_ids = []
                for i in range(num_reflections):
                    reflection_content = f"{content} - item {i}"
                    reflection_id = await db.store_reflection(
                        reflection_content, ["bulk", "test"], project
                    )
                    reflection_ids.append(reflection_id)

                # Verify all reflections can be retrieved
                for reflection_id in reflection_ids:
                    retrieved = await db.get_reflection(reflection_id)
                    assert retrieved is not None
                    assert "content" in retrieved
                    assert "project" in retrieved
                    assert "tags" in retrieved

                # Verify count
                stats = await db.get_stats()
                assert stats["total_reflections"] >= num_reflections

            finally:
                db.close()

    @pytest.mark.asyncio
    @given(
        project=st.text(
            min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
        ),
        num_reflections=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=15, deadline=None)
    async def test_project_isolation_properties(
        self, project: str, num_reflections: int
    ):
        """Test that project isolation works correctly.

        Property: Reflections from different projects should be isolated.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store reflections in different projects
                project1 = f"{project}_1"
                project2 = f"{project}_2"

                for i in range(num_reflections):
                    await db.store_reflection(
                        f"Project 1 reflection {i}", ["test"], project1
                    )
                    await db.store_reflection(
                        f"Project 2 reflection {i}", ["test"], project2
                    )

                # Search in project1 should only return project1 reflections
                results1 = await db.search_reflections("reflection", 10, project1)
                assert all(r["project"] == project1 for r in results1)

                # Search in project2 should only return project2 reflections
                results2 = await db.search_reflections("reflection", 10, project2)
                assert all(r["project"] == project2 for r in results2)

            finally:
                db.close()

    @pytest.mark.asyncio
    @given(
        content=st.text(min_size=1, max_size=100),
        project=st.text(
            min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
        ),
        tags=st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3),
    )
    @settings(max_examples=25, deadline=None)
    async def test_tag_filtering_properties(
        self, content: str, project: str, tags: list[str]
    ):
        """Test that tag filtering works correctly.

        Property: Tag filtering should return only reflections with matching tags.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store reflections with different tags
                await db.store_reflection(content, tags, project)
                await db.store_reflection("Other content", ["other"], project)

                # Search with tag filter
                results = await db.search_reflections("content", 10, project, tags=tags)

                # Verify all results have the expected tags
                for result in results:
                    result_tags = result.get("tags", [])
                    assert any(tag in result_tags for tag in tags)

            finally:
                db.close()

    @pytest.mark.asyncio
    @given(
        content=st.text(min_size=1, max_size=1000),
        project=st.text(
            min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
        ),
        update_content=st.text(min_size=1, max_size=1000),
    )
    @settings(max_examples=20, deadline=None)
    async def test_update_reflection_properties(
        self, content: str, project: str, update_content: str
    ):
        """Test that reflection updates preserve data integrity.

        Property: Updating a reflection should preserve its ID and update content.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store initial reflection
                reflection_id = await db.store_reflection(content, ["test"], project)

                # Update reflection
                await db.update_reflection(reflection_id, update_content, ["updated"])

                # Verify update
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved is not None
                assert retrieved["content"] == update_content
                assert "updated" in retrieved["tags"]
                assert retrieved["id"] == reflection_id

            finally:
                db.close()

    @pytest.mark.asyncio
    @given(
        content=st.text(min_size=1, max_size=1000),
        project=st.text(
            min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
        ),
    )
    @settings(max_examples=15, deadline=None)
    async def test_delete_reflection_properties(self, content: str, project: str):
        """Test that reflection deletion works correctly.

        Property: Deleting a reflection should remove it from the database.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store reflection
                reflection_id = await db.store_reflection(content, ["test"], project)

                # Verify it exists
                retrieved = await db.get_reflection(reflection_id)
                assert retrieved is not None

                # Delete reflection
                await db.delete_reflection(reflection_id)

                # Verify it's deleted
                deleted = await db.get_reflection(reflection_id)
                assert deleted is None

            finally:
                db.close()

    @pytest.mark.asyncio
    @given(
        project=st.text(
            min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
        ),
        num_reflections=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=10, deadline=None)
    async def test_statistics_properties(self, project: str, num_reflections: int):
        """Test that database statistics are accurate.

        Property: Statistics should accurately reflect the database state.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store reflections
                for i in range(num_reflections):
                    await db.store_reflection(f"Test {i}", ["test"], project)

                # Get statistics
                stats = await db.get_stats()

                # Verify statistics
                assert stats["total_reflections"] >= num_reflections
                assert stats["total_projects"] >= 1
                assert project in stats["projects"]

            finally:
                db.close()
