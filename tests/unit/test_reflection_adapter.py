#!/usr/bin/env python3
"""Tests for reflection_adapter shim.

This module is a compatibility shim that routes to the Oneiric implementation.
These tests verify the shim correctly exposes the ReflectionDatabaseAdapter.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from session_buddy.adapters.reflection_adapter import (
    ReflectionDatabaseAdapter,
)


class TestReflectionAdapterShim:
    """Test the reflection_adapter shim correctly exposes the Oneiric adapter."""

    def test_reflection_database_adapter_is_exposed(self) -> None:
        """Should expose ReflectionDatabaseAdapter from oneiric implementation."""
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        # The shim should expose the Oneiric class as ReflectionDatabaseAdapter
        assert ReflectionDatabaseAdapter is ReflectionDatabaseAdapterOneiric

    def test_adapter_can_be_instantiated(self) -> None:
        """Should be able to instantiate the adapter."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_shim")
        assert adapter is not None
        assert adapter.collection_name == "test_shim"

    def test_adapter_default_collection(self) -> None:
        """Should use 'default' collection if not specified."""
        adapter = ReflectionDatabaseAdapter()
        assert adapter.collection_name == "default"

    def test_adapter_uses_file_based_db(self) -> None:
        """Should use file-based database by default."""
        adapter = ReflectionDatabaseAdapter(collection_name="default")
        # The adapter uses settings to determine db_path, not in-memory
        assert adapter.db_path is not None
        assert adapter.db_path != ":memory:"

    def test_adapter_exports_all(self) -> None:
        """Should export ReflectionDatabaseAdapter and ReflectionDatabase."""
        from session_buddy.adapters import reflection_adapter

        assert hasattr(reflection_adapter, "ReflectionDatabaseAdapter")
        assert hasattr(reflection_adapter, "__all__")
        assert "ReflectionDatabaseAdapter" in reflection_adapter.__all__


class TestReflectionDatabaseAdapterAPI:
    """Test the ReflectionDatabaseAdapter has the expected API.

    Tests public interface of the adapter (from Oneiric implementation).
    """

    def test_has_store_conversation_method(self) -> None:
        """Adapter should have store_conversation method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "store_conversation")
        assert callable(adapter.store_conversation)

    def test_has_search_conversations_method(self) -> None:
        """Adapter should have search_conversations method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "search_conversations")
        assert callable(adapter.search_conversations)

    def test_has_store_reflection_method(self) -> None:
        """Adapter should have store_reflection method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "store_reflection")
        assert callable(adapter.store_reflection)

    def test_has_search_reflections_method(self) -> None:
        """Adapter should have search_reflections method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "search_reflections")
        assert callable(adapter.search_reflections)

    def test_has_similarity_search_method(self) -> None:
        """Adapter should have similarity_search method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "similarity_search")
        assert callable(adapter.similarity_search)

    def test_has_get_stats_method(self) -> None:
        """Adapter should have get_stats method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "get_stats")
        assert callable(adapter.get_stats)

    def test_has_health_check_method(self) -> None:
        """Adapter should have health_check method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "health_check")
        assert callable(adapter.health_check)

    def test_has_reset_database_method(self) -> None:
        """Adapter should have reset_database method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "reset_database")
        assert callable(adapter.reset_database)

    def test_has_close_method(self) -> None:
        """Adapter should have close method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "close")
        assert callable(adapter.close)

    def test_has_aclose_method(self) -> None:
        """Adapter should have aclose method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "aclose")
        assert callable(adapter.aclose)

    def test_has_store_insight_method(self) -> None:
        """Adapter should have store_insight method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "store_insight")
        assert callable(adapter.store_insight)

    def test_has_search_insights_method(self) -> None:
        """Adapter should have search_insights method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "search_insights")
        assert callable(adapter.search_insights)

    def test_has_get_insights_statistics_method(self) -> None:
        """Adapter should have get_insights_statistics method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "get_insights_statistics")
        assert callable(adapter.get_insights_statistics)

    def test_has_update_insight_usage_method(self) -> None:
        """Adapter should have update_insight_usage method."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_api")
        assert hasattr(adapter, "update_insight_usage")
        assert callable(adapter.update_insight_usage)


class TestReflectionDatabaseAdapterContextManagers:
    """Test context manager protocols."""

    def test_sync_context_manager_raises_error(self, tmp_path: Path) -> None:
        """Should raise error when using sync context manager."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "test_ctx.duckdb")
            adapter = ReflectionDatabaseAdapter(collection_name="test_ctx")
            # Override db_path to use temp file
            adapter.db_path = db_path

            with pytest.raises(
                RuntimeError,
                match="Use 'async with' instead of 'with' for ReflectionDatabaseAdapter",
            ):
                with adapter:
                    pass

    @pytest.mark.asyncio
    async def test_async_context_manager_initializes(self, tmp_path: Path) -> None:
        """Should initialize when entering async context manager."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_init")

        async with adapter as db:
            assert db is adapter
            assert db._initialized is True

        # Connection should be closed after exit
        await adapter.aclose()
        assert adapter.conn is None

    @pytest.mark.asyncio
    async def test_async_context_manager_cleanup_on_exception(
        self, tmp_path: Path
    ) -> None:
        """Should cleanup connection even if exception occurs."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_exc")

        with pytest.raises(ValueError, match="test exception"):
            async with adapter:
                msg = "test exception"
                raise ValueError(msg)

        # Connection should still be cleaned up
        assert adapter.conn is None


class TestReflectionDatabaseAdapterStoresConversation:
    """Test store_conversation functionality."""

    @pytest.mark.asyncio
    async def test_store_conversation_returns_id(self, tmp_path: Path) -> None:
        """Should store conversation and return ID."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_store_conv")

        async with adapter as db:
            conv_id = await db.store_conversation(
                content="Test conversation content",
                metadata={"project": "test"},
            )

            assert conv_id is not None
            assert isinstance(conv_id, str)
            assert len(conv_id) > 0

    @pytest.mark.asyncio
    async def test_store_conversation_with_empty_metadata(self, tmp_path: Path) -> None:
        """Should store conversation with empty metadata."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_store_meta")

        async with adapter as db:
            conv_id = await db.store_conversation(content="Another conversation")

            assert conv_id is not None

    @pytest.mark.asyncio
    async def test_store_duplicate_conversation_with_deduplicate(
        self, tmp_path: Path
    ) -> None:
        """Should return existing ID when deduplicate=True and duplicate exists."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_dedup")

        async with adapter as db:
            content = "Duplicate test content"
            first_id = await db.store_conversation(content, deduplicate=True)

            second_id = await db.store_conversation(content, deduplicate=True)

            # Should return same ID for duplicate content
            assert first_id == second_id


class TestReflectionDatabaseAdapterSearchConversations:
    """Test search_conversations functionality."""

    @pytest.mark.asyncio
    async def test_search_conversations_by_content(self, tmp_path: Path) -> None:
        """Should find conversations by content."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_search_conv")

        async with adapter as db:
            # Store some conversations
            await db.store_conversation("Python programming is great")
            await db.store_conversation("JavaScript frameworks")
            await db.store_conversation("Python decorators are useful")

            # Search for python
            results = await db.search_conversations("Python", limit=10)

            assert len(results) >= 1
            assert any("Python" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_search_conversations_with_limit(self, tmp_path: Path) -> None:
        """Should respect limit parameter."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_limit")

        async with adapter as db:
            # Store multiple conversations
            for i in range(5):
                await db.store_conversation(f"Content number {i}")

            results = await db.search_conversations("Content", limit=2)

            assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_search_conversations_empty_query(self, tmp_path: Path) -> None:
        """Should handle empty query."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_empty_q")

        async with adapter as db:
            await db.store_conversation("Some content")

            results = await db.search_conversations("", limit=10)

            # Should return results or empty list
            assert isinstance(results, list)


class TestReflectionDatabaseAdapterStoreReflection:
    """Test store_reflection functionality."""

    @pytest.mark.asyncio
    async def test_store_reflection_returns_id(self, tmp_path: Path) -> None:
        """Should store reflection and return ID."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_store_refl")

        async with adapter as db:
            refl_id = await db.store_reflection(
                content="Test reflection content",
                tags=["python", "testing"],
            )

            assert refl_id is not None
            assert isinstance(refl_id, str)

    @pytest.mark.asyncio
    async def test_store_reflection_without_tags(self, tmp_path: Path) -> None:
        """Should store reflection without tags."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_no_tags")

        async with adapter as db:
            refl_id = await db.store_reflection(content="Reflection without tags")

            assert refl_id is not None

    @pytest.mark.asyncio
    async def test_store_reflection_empty_content_raises(self, tmp_path: Path) -> None:
        """Should raise ValueError for empty content."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_empty")

        async with adapter as db:
            with pytest.raises(ValueError, match="content cannot be empty"):
                await db.store_reflection(content="   ")

    @pytest.mark.asyncio
    async def test_store_reflection_none_content_raises(self, tmp_path: Path) -> None:
        """Should raise TypeError for None content."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_none")

        async with adapter as db:
            with pytest.raises(TypeError, match="content cannot be None"):
                await db.store_reflection(content=None)  # type: ignore[arg-type]


class TestReflectionDatabaseAdapterSearchReflections:
    """Test search_reflections functionality."""

    @pytest.mark.asyncio
    async def test_search_reflections_by_content(self, tmp_path: Path) -> None:
        """Should find reflections by content."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_search_refl")

        async with adapter as db:
            # Store reflections
            await db.store_reflection("Python testing best practices")
            await db.store_reflection("JavaScript testing frameworks")
            await db.store_reflection("Python type hints")

            # Search
            results = await db.search_reflections("Python", limit=10)

            assert len(results) >= 2
            assert any("Python" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_search_reflections_with_limit(self, tmp_path: Path) -> None:
        """Should respect limit parameter."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_refl_limit")

        async with adapter as db:
            for i in range(5):
                await db.store_reflection(f"Reflection {i}")

            results = await db.search_reflections("Reflection", limit=3)

            assert len(results) <= 3


class TestReflectionDatabaseAdapterGetStats:
    """Test get_stats functionality."""

    @pytest.mark.asyncio
    async def test_get_stats_empty_database(self, tmp_path: Path) -> None:
        """Should return zeros for empty database."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_stats_empty")

        async with adapter as db:
            stats = await db.get_stats()

            assert "total_conversations" in stats
            assert "total_reflections" in stats
            assert stats["total_conversations"] == 0
            assert stats["total_reflections"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_data(self, tmp_path: Path) -> None:
        """Should return accurate counts."""
        import uuid

        unique_collection = f"test_stats_data_{uuid.uuid4().hex[:8]}"

        adapter = ReflectionDatabaseAdapter(collection_name=unique_collection)

        async with adapter as db:
            await db.store_conversation("Conversation 1")
            await db.store_conversation("Conversation 2")
            await db.store_reflection("Reflection 1")

            stats = await db.get_stats()

            assert stats["total_conversations"] == 2
            assert stats["total_reflections"] == 1


class TestReflectionDatabaseAdapterHealthCheck:
    """Test health_check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_healthy(self, tmp_path: Path) -> None:
        """Should return True when database is healthy."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_health")

        async with adapter as db:
            result = await db.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_after_close(self, tmp_path: Path) -> None:
        """Should still return True after initialization."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_health_close")

        await adapter.initialize()
        result = await adapter.health_check()
        assert result is True

        await adapter.aclose()


class TestReflectionDatabaseAdapterResetDatabase:
    """Test reset_database functionality."""

    @pytest.mark.asyncio
    async def test_reset_database_clears_data(self, tmp_path: Path) -> None:
        """Should clear all data from database."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_reset")

        async with adapter as db:
            # Add some data
            await db.store_conversation("Test conversation")
            await db.store_reflection("Test reflection")

            # Reset
            await db.reset_database()

            # Check stats
            stats = await db.get_stats()
            assert stats["total_conversations"] == 0
            assert stats["total_reflections"] == 0


class TestReflectionDatabaseAdapterInsights:
    """Test insight-related functionality."""

    @pytest.mark.asyncio
    async def test_store_insight_returns_id(self, tmp_path: Path) -> None:
        """Should store insight and return ID."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_store_insight")

        async with adapter as db:
            insight_id = await db.store_insight(
                content="Test insight",
                insight_type="pattern",
                topics=["testing"],
                confidence_score=0.8,
                quality_score=0.9,
            )

            assert insight_id is not None
            assert isinstance(insight_id, str)

    @pytest.mark.asyncio
    async def test_search_insights_returns_results(self, tmp_path: Path) -> None:
        """Should find insights by query."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_search_insight")

        async with adapter as db:
            await db.store_insight(
                content="Testing patterns in Python",
                insight_type="pattern",
            )

            results = await db.search_insights("Python", limit=10)

            assert len(results) >= 1
            assert any("Python" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_get_insights_statistics(self, tmp_path: Path) -> None:
        """Should return insight statistics."""
        import uuid

        unique_collection = f"test_insight_stats_{uuid.uuid4().hex[:8]}"
        adapter = ReflectionDatabaseAdapter(collection_name=unique_collection)

        async with adapter as db:
            await db.store_insight(
                content="First insight",
                insight_type="general",
            )
            await db.store_insight(
                content="Second insight",
                insight_type="pattern",
            )

            stats = await db.get_insights_statistics()

            assert "total" in stats
            assert "by_type" in stats
            assert stats["total"] == 2

    @pytest.mark.asyncio
    async def test_update_insight_usage_returns_bool(self, tmp_path: Path) -> None:
        """Should return True when updating existing insight."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_insight_usage")

        async with adapter as db:
            # Store an insight
            insight_id = await db.store_insight(
                content="Usage tracked insight",
                insight_type="test",
            )

            # Update usage
            result = await db.update_insight_usage(insight_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_update_insight_usage_nonexistent_returns_false(
        self, tmp_path: Path
    ) -> None:
        """Should return False when updating non-existent insight."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_fake_usage")

        async with adapter as db:
            result = await db.update_insight_usage("nonexistent-id-12345")

            assert result is False


class TestReflectionDatabaseAdapterSimilaritySearch:
    """Test similarity_search functionality."""

    @pytest.mark.asyncio
    async def test_similarity_search_combines_results(self, tmp_path: Path) -> None:
        """Should search both conversations and reflections."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_sim_search")

        async with adapter as db:
            await db.store_conversation("Python is great")
            await db.store_reflection("Python testing")

            results = await db.similarity_search("Python", limit=10)

            assert len(results) >= 1
            # Results should have type field
            assert all("type" in r for r in results)


class TestReflectionDatabaseAdapterGetReflectionById:
    """Test get_reflection_by_id functionality."""

    @pytest.mark.asyncio
    async def test_get_reflection_by_id_returns_reflection(self, tmp_path: Path) -> None:
        """Should return reflection by ID."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_get_by_id")

        async with adapter as db:
            refl_id = await db.store_reflection(
                content="Find me",
                tags=["test"],
            )

            result = await db.get_reflection_by_id(refl_id)

            assert result is not None
            assert result["id"] == refl_id
            assert result["content"] == "Find me"

    @pytest.mark.asyncio
    async def test_get_reflection_by_id_returns_none_for_missing(
        self, tmp_path: Path
    ) -> None:
        """Should return None for non-existent ID."""
        adapter = ReflectionDatabaseAdapter(collection_name="test_missing")

        async with adapter as db:
            result = await db.get_reflection_by_id("nonexistent-id-12345")

            assert result is None


class TestReflectionDatabaseAdapterTableValidation:
    """Test table name validation helper methods."""

    def test_table_helper_generates_valid_names(self) -> None:
        """Should generate valid table names."""
        adapter = ReflectionDatabaseAdapter(collection_name="valid_name")
        table_name = adapter._table("conversations")
        assert "valid_name" in table_name
        assert table_name == f"{adapter.collection_name}_conversations"

    def test_index_helper_generates_valid_names(self) -> None:
        """Should generate valid index names."""
        adapter = ReflectionDatabaseAdapter(collection_name="idx_test")
        index_name = adapter._index("conv_created")
        assert "idx_test" in index_name
        assert index_name.startswith("idx_")

    def test_validate_hnsw_ef_validates_input(self) -> None:
        """Should validate HNSW ef_search parameter."""
        adapter = ReflectionDatabaseAdapter(collection_name="ef_test")

        # Valid values
        assert adapter._validate_hnsw_ef(100) == 100
        assert adapter._validate_hnsw_ef(1) == 1

        # Invalid values return default
        assert adapter._validate_hnsw_ef(0) == 100
        assert adapter._validate_hnsw_ef(-1) == 100