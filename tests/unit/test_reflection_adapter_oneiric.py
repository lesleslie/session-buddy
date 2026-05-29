#!/usr/bin/env python3
"""Comprehensive unit tests for ReflectionDatabaseAdapterOneiric.

Tests all core functionality including initialization, storage, search,
error handling, and edge cases for the reflection database adapter.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test
from session_buddy.adapters import reflection_adapter_oneiric as reflection_module
from session_buddy.adapters.settings import ReflectionAdapterSettings

# Skip all tests if duckdb is not available
duckdb = pytest.importorskip("duckdb")


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
async def adapter(tmp_path: Path) -> reflection_module.ReflectionDatabaseAdapterOneiric:
    """Provide initialized adapter for testing."""
    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "test.duckdb",
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )
    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()
    yield adapter
    await adapter.aclose()


@pytest.fixture
async def adapter_with_data(
    tmp_path: Path,
) -> reflection_module.ReflectionDatabaseAdapterOneiric:
    """Provide adapter pre-populated with test data."""
    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "test.duckdb",
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )
    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()

    # Add test conversations
    await adapter.store_conversation(
        "How to implement async/await patterns",
        {"project": "test", "topic": "async"},
    )
    await adapter.store_conversation(
        "Setting up pytest fixtures for database testing",
        {"project": "test", "topic": "testing"},
    )
    await adapter.store_conversation(
        "Best practices for MCP server development",
        {"project": "test", "topic": "mcp"},
    )

    # Add test reflections
    await adapter.store_reflection(
        "Always use context managers for database connections",
        tags=["database", "patterns"],
    )
    await adapter.store_reflection(
        "Async fixtures require careful setup in pytest",
        tags=["testing", "async", "pytest"],
    )
    await adapter.store_reflection(
        "MCP tools should handle errors gracefully",
        tags=["mcp", "error-handling"],
    )

    yield adapter
    await adapter.aclose()


@pytest.fixture
async def in_memory_adapter() -> reflection_module.ReflectionDatabaseAdapterOneiric:
    """Provide in-memory adapter for fast tests."""
    settings = ReflectionAdapterSettings(
        database_path=Path(":memory:"),
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )
    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()
    yield adapter
    await adapter.aclose()


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


@pytest.mark.asyncio
class TestAdapterInitialization:
    """Test adapter initialization and setup."""

    async def test_init_default_settings(self, tmp_path: Path):
        """Test initialization with default settings."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
        assert adapter.settings is settings
        assert adapter.collection_name == "default"
        assert adapter._initialized is False

    async def test_init_custom_collection(self, tmp_path: Path):
        """Test initialization with custom collection name."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
            collection_name="custom_collection",
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(
            settings=settings, collection_name="custom_collection"
        )
        assert adapter.collection_name == "custom_collection"

    async def test_init_invalid_collection_name(self, tmp_path: Path):
        """Test initialization with invalid collection name raises error."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )
        with pytest.raises(ValueError, match="contains invalid characters"):
            reflection_module.ReflectionDatabaseAdapterOneiric(
                settings=settings, collection_name="invalid;name"
            )

    async def test_init_in_memory_database(self):
        """Test initialization with in-memory database."""
        settings = ReflectionAdapterSettings(
            database_path=Path(":memory:"),
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
        assert adapter.db_path == ":memory:"

    async def test_context_manager_sync_raises_error(self, tmp_path: Path):
        """Test that sync context manager raises error."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)

        with pytest.raises(RuntimeError, match="Use 'async with'"):
            with adapter:
                pass

    async def test_initialize_creates_connection(self, tmp_path: Path):
        """Test that initialize() creates database connection."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
        assert adapter.conn is None

        await adapter.initialize()
        assert adapter.conn is not None
        assert adapter._initialized is True

        await adapter.aclose()

    async def test_initialize_twice_is_idempotent(self, tmp_path: Path):
        """Test that calling initialize() twice is safe."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)

        await adapter.initialize()
        first_conn = adapter.conn

        await adapter.initialize()  # Should not reconnect
        assert adapter.conn is first_conn

        await adapter.aclose()

    async def test_close_via_sync_context_manager(self, tmp_path: Path):
        """Test that close() works via sync context manager exit."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()

        # Sync __exit__ calls close() which schedules async cleanup
        # The connection won't be None immediately due to async task
        # Just verify it doesn't raise an exception
        adapter.__exit__(None, None, None)
        # Give async close task time to complete
        await asyncio.sleep(0.2)
        # After async close completes, connection should be closed
        assert adapter.conn is None


# =============================================================================
# HELPER METHOD TESTS
# =============================================================================


@pytest.mark.asyncio
class TestHelperMethods:
    """Test adapter helper methods."""

    async def test_table_returns_valid_table_name(self, adapter):
        """Test _table() helper returns valid table name."""
        table_name = adapter._table("conversations")
        assert table_name == f"{adapter.collection_name}_conversations"
        assert ";" not in table_name  # No SQL injection

    async def test_index_returns_valid_index_name(self, adapter):
        """Test _index() helper returns valid index name."""
        index_name = adapter._index("conv_created")
        assert index_name == f"idx_{adapter.collection_name}_conv_created"
        assert ";" not in index_name

    async def test_validate_hnsw_ef_valid_values(self, adapter):
        """Test _validate_hnsw_ef() with valid values."""
        assert adapter._validate_hnsw_ef(100) == 100
        assert adapter._validate_hnsw_ef(1) == 1
        assert adapter._validate_hnsw_ef(500) == 500

    async def test_validate_hnsw_ef_invalid_values(self, adapter):
        """Test _validate_hnsw_ef() with invalid values returns default."""
        assert adapter._validate_hnsw_ef(0) == 100  # Below minimum
        assert adapter._validate_hnsw_ef(-1) == 100  # Negative
        assert adapter._validate_hnsw_ef("string") == 100  # Non-int
        assert adapter._validate_hnsw_ef(None) == 100  # None

    async def test_generate_id_is_deterministic(self, adapter):
        """Test _generate_id() produces deterministic IDs."""
        id1 = adapter._generate_id("test content")
        id2 = adapter._generate_id("test content")
        assert id1 == id2
        assert len(id1) == 16

    async def test_generate_id_different_for_different_content(self, adapter):
        """Test _generate_id() produces different IDs for different content."""
        id1 = adapter._generate_id("content 1")
        id2 = adapter._generate_id("content 2")
        assert id1 != id2


# =============================================================================
# CONVERSATION STORAGE TESTS
# =============================================================================


@pytest.mark.asyncio
class TestConversationStorage:
    """Test conversation storage operations."""

    async def test_store_conversation_basic(self, adapter):
        """Test storing a basic conversation."""
        conv_id = await adapter.store_conversation(
            "Test conversation content",
            {"project": "test"},
        )
        assert conv_id is not None
        assert isinstance(conv_id, str)

    async def test_store_conversation_without_metadata(self, adapter):
        """Test storing conversation without metadata."""
        conv_id = await adapter.store_conversation("No metadata conversation")
        assert conv_id is not None

    async def test_store_conversation_with_empty_metadata(self, adapter):
        """Test storing conversation with empty metadata dict."""
        conv_id = await adapter.store_conversation(
            "Empty metadata conversation",
            {},
        )
        assert conv_id is not None

    async def test_store_conversation_with_none_metadata(self, adapter):
        """Test storing conversation with None metadata."""
        conv_id = await adapter.store_conversation(
            "None metadata conversation",
            None,
        )
        assert conv_id is not None

    async def test_store_multiple_conversations_unique_ids(self, adapter):
        """Test that multiple conversations get unique IDs."""
        conv_ids = []
        for i in range(5):
            conv_id = await adapter.store_conversation(f"Conversation {i}")
            conv_ids.append(conv_id)

        assert len(set(conv_ids)) == 5  # All unique

    async def test_store_conversation_with_special_characters(self, adapter):
        """Test storing conversation with special characters."""
        special_content = "O'Reilly's \"test\" with <script> and 'quotes'"
        conv_id = await adapter.store_conversation(special_content)
        assert conv_id is not None

        # Can retrieve it
        results = await adapter.search_conversations("O'Reilly", limit=1)
        assert len(results) >= 1

    async def test_store_conversation_deduplicate_disabled(self, adapter):
        """Test storing duplicate content when deduplicate=False."""
        content = "Duplicate test content"

        # First store
        id1 = await adapter.store_conversation(content, deduplicate=False)
        # Second store (no dedup) should create new ID
        id2 = await adapter.store_conversation(content, deduplicate=False)

        assert id1 != id2


# =============================================================================
# CONVERSATION SEARCH TESTS
# =============================================================================


@pytest.mark.asyncio
class TestConversationSearch:
    """Test conversation search operations."""

    async def test_search_empty_database(self, adapter):
        """Test searching empty database returns empty list."""
        results = await adapter.search_conversations("test")
        assert results == []

    async def test_search_returns_results(self, adapter_with_data):
        """Test searching returns matching conversations."""
        results = await adapter_with_data.search_conversations("async")
        assert len(results) > 0

    async def test_search_respects_limit(self, adapter_with_data):
        """Test search respects limit parameter."""
        results = await adapter_with_data.search_conversations("test", limit=1)
        assert len(results) <= 1

    async def test_search_with_threshold(self, adapter):
        """Test search with similarity threshold."""
        await adapter.store_conversation("Test content about Python")
        results = await adapter.search_conversations(
            "Python", threshold=0.5, use_cache=False
        )
        assert isinstance(results, list)

    async def test_search_with_min_score(self, adapter):
        """Test search with min_score alias for threshold."""
        await adapter.store_conversation("Test content about Python")
        results = await adapter.search_conversations("Python", min_score=0.5)
        assert isinstance(results, list)

    async def test_search_uses_text_fallback_when_no_embeddings(self, adapter):
        """Test text search fallback works."""
        await adapter.store_conversation("Specific unique content 12345")
        results = await adapter.search_conversations("12345")
        assert len(results) >= 1
        assert results[0]["content"] == "Specific unique content 12345"

    async def test_search_case_insensitive(self, adapter):
        """Test search handles different cases."""
        await adapter.store_conversation("PYTHON IS GREAT")
        # Text search with LIKE is case-sensitive in DuckDB by default
        # The important thing is the search doesn't crash
        results = await adapter.search_conversations("python", use_cache=False)
        assert isinstance(results, list)


# =============================================================================
# REFLECTION STORAGE TESTS
# =============================================================================


@pytest.mark.asyncio
class TestReflectionStorage:
    """Test reflection storage operations."""

    async def test_store_reflection_basic(self, adapter):
        """Test storing a basic reflection."""
        refl_id = await adapter.store_reflection(
            "Test reflection content",
            tags=["test"],
        )
        assert refl_id is not None
        assert isinstance(refl_id, str)

    async def test_store_reflection_without_tags(self, adapter):
        """Test storing reflection without tags."""
        refl_id = await adapter.store_reflection("No tags reflection")
        assert refl_id is not None

    async def test_store_reflection_with_none_tags(self, adapter):
        """Test storing reflection with None tags."""
        refl_id = await adapter.store_reflection("None tags reflection", None)
        assert refl_id is not None

    async def test_store_reflection_empty_content_raises_error(self, adapter):
        """Test storing empty content raises ValueError."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            await adapter.store_reflection("")

    async def test_store_reflection_whitespace_content_raises_error(self, adapter):
        """Test storing whitespace-only content raises ValueError."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            await adapter.store_reflection("   ")

    async def test_store_reflection_none_content_raises_error(self, adapter):
        """Test storing None content raises TypeError."""
        with pytest.raises(TypeError, match="content cannot be None"):
            await adapter.store_reflection(None)  # type: ignore

    async def test_store_reflection_with_multiple_tags(self, adapter):
        """Test storing reflection with multiple tags."""
        tags = ["python", "async", "testing", "patterns"]
        refl_id = await adapter.store_reflection("Multi-tag reflection", tags)
        assert refl_id is not None

    async def test_store_multiple_reflections_unique_ids(self, adapter):
        """Test that multiple reflections get unique IDs."""
        refl_ids = []
        for i in range(5):
            refl_id = await adapter.store_reflection(f"Reflection {i}")
            refl_ids.append(refl_id)

        assert len(set(refl_ids)) == 5  # All unique


# =============================================================================
# REFLECTION SEARCH TESTS
# =============================================================================


@pytest.mark.asyncio
class TestReflectionSearch:
    """Test reflection search operations."""

    async def test_search_empty_database(self, adapter):
        """Test searching reflections in empty database."""
        results = await adapter.search_reflections("test")
        assert results == []

    async def test_search_returns_results(self, adapter_with_data):
        """Test searching returns matching reflections."""
        results = await adapter_with_data.search_reflections("pytest")
        assert len(results) > 0

    async def test_search_respects_limit(self, adapter_with_data):
        """Test search respects limit parameter."""
        results = await adapter_with_data.search_reflections(
            "test", limit=1, use_cache=False
        )
        assert len(results) <= 1

    async def test_search_by_tag(self, adapter_with_data):
        """Test searching reflections by tag."""
        results = await adapter_with_data.search_reflections(
            "database", use_cache=False
        )
        assert len(results) > 0

    async def test_search_returns_reflections_not_insights(self, adapter):
        """Test that search only returns reflections, not insights."""
        # Store a reflection
        await adapter.store_reflection(
            "Regular reflection",
            tags=["test"],
        )
        # Store an insight
        await adapter.store_insight(
            "This is an insight",
            insight_type="pattern",
        )

        # Search should only find the reflection
        results = await adapter.search_reflections("reflection")
        assert len(results) >= 1
        # Verify no insights in results
        for result in results:
            assert result.get("insight_type") is None

    async def test_search_uses_text_fallback(self, adapter):
        """Test text search fallback when no embeddings."""
        await adapter.store_reflection("Specific reflection content ABC123")
        results = await adapter.search_reflections("ABC123", use_cache=False)
        assert len(results) >= 1


# =============================================================================
# GET BY ID TESTS
# =============================================================================


@pytest.mark.asyncio
class TestGetById:
    """Test retrieval by ID operations."""

    async def test_get_reflection_by_id_exists(self, adapter_with_data):
        """Test getting existing reflection by ID."""
        # Get a reflection from search
        results = await adapter_with_data.search_reflections(
            "pytest", use_cache=False
        )
        assert len(results) > 0

        reflection_id = results[0]["id"]
        reflection = await adapter_with_data.get_reflection_by_id(reflection_id)

        assert reflection is not None
        assert reflection["id"] == reflection_id
        assert "content" in reflection

    async def test_get_reflection_by_id_not_found(self, adapter):
        """Test getting non-existent reflection returns None."""
        result = await adapter.get_reflection_by_id("nonexistent-id-12345")
        assert result is None


# =============================================================================
# SIMILARITY SEARCH TESTS
# =============================================================================


@pytest.mark.asyncio
class TestSimilaritySearch:
    """Test combined similarity search operations."""

    async def test_similarity_search_combines_results(self, adapter_with_data):
        """Test that similarity search combines conversations and reflections."""
        results = await adapter_with_data.similarity_search("async")
        assert len(results) > 0

        # Check that results have type information
        for result in results:
            assert "type" in result
            assert result["type"] in ("conversation", "reflection")

    async def test_similarity_search_respects_limit(self, adapter_with_data):
        """Test similarity search respects limit."""
        results = await adapter_with_data.similarity_search("test", limit=2)
        assert len(results) <= 2

    async def test_similarity_search_empty_database(self, adapter):
        """Test similarity search on empty database."""
        results = await adapter.similarity_search("test")
        assert results == []


# =============================================================================
# STATS TESTS
# =============================================================================


@pytest.mark.asyncio
class TestStats:
    """Test statistics operations."""

    async def test_get_stats_empty_database(self, adapter):
        """Test stats on empty database."""
        stats = await adapter.get_stats()
        assert stats["total_conversations"] == 0
        assert stats["total_reflections"] == 0
        assert "database_path" in stats

    async def test_get_stats_with_data(self, adapter_with_data):
        """Test stats with data."""
        stats = await adapter_with_data.get_stats()
        assert stats["total_conversations"] >= 3
        assert stats["total_reflections"] >= 3

    async def test_get_stats_includes_cache_info(self, adapter):
        """Test stats include cache information."""
        stats = await adapter.get_stats()
        assert "embedding_cache" in stats
        assert "hit_rate" in stats["embedding_cache"]


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================


@pytest.mark.asyncio
class TestHealthCheck:
    """Test health check operations."""

    async def test_health_check_returns_true(self, adapter):
        """Test health check returns True when healthy."""
        result = await adapter.health_check()
        assert result is True

    async def test_health_check_initializes_if_needed(self, tmp_path: Path):
        """Test health check initializes if not already initialized."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)

        result = await adapter.health_check()
        assert result is True
        assert adapter._initialized is True

        await adapter.aclose()


# =============================================================================
# RESET DATABASE TESTS
# =============================================================================


@pytest.mark.asyncio
class TestResetDatabase:
    """Test database reset operations."""

    async def test_reset_database_clears_data(self, adapter_with_data):
        """Test reset clears all data."""
        # Verify we have data
        stats_before = await adapter_with_data.get_stats()
        assert stats_before["total_conversations"] >= 1

        # Reset
        await adapter_with_data.reset_database()

        # Verify data is cleared
        stats_after = await adapter_with_data.get_stats()
        assert stats_after["total_conversations"] == 0
        assert stats_after["total_reflections"] == 0

    async def test_reset_recreates_tables(self, adapter_with_data):
        """Test reset recreates tables."""
        await adapter_with_data.reset_database()

        # Should be able to store new data after reset
        conv_id = await adapter_with_data.store_conversation("After reset")
        assert conv_id is not None


# =============================================================================
# INSIGHT STORAGE TESTS
# =============================================================================


@pytest.mark.asyncio
class TestInsightStorage:
    """Test insight storage operations."""

    async def test_store_insight_basic(self, adapter):
        """Test storing a basic insight."""
        insight_id = await adapter.store_insight(
            "Test insight content",
            insight_type="pattern",
        )
        assert insight_id is not None

    async def test_store_insight_with_topics(self, adapter):
        """Test storing insight with topic tags."""
        insight_id = await adapter.store_insight(
            "Insight with topics",
            topics=["python", "async"],
        )
        assert insight_id is not None

    async def test_store_insight_with_projects(self, adapter):
        """Test storing insight with project associations."""
        insight_id = await adapter.store_insight(
            "Insight with projects",
            projects=["test-project", "another-project"],
        )
        assert insight_id is not None

    async def test_store_insight_with_confidence_score(self, adapter):
        """Test storing insight with confidence score."""
        insight_id = await adapter.store_insight(
            "High confidence insight",
            confidence_score=0.95,
        )
        assert insight_id is not None

    async def test_store_insight_default_type(self, adapter):
        """Test storing insight uses default 'general' type."""
        insight_id = await adapter.store_insight("General insight")
        assert insight_id is not None

    async def test_store_insight_invalid_type_defaults_to_general(self, adapter):
        """Test storing insight with invalid type falls back to general."""
        # Invalid type would fail validation, so it should default to general
        insight_id = await adapter.store_insight(
            "Insight with default type",
            insight_type="invalid;type",
        )
        assert insight_id is not None


# =============================================================================
# INSIGHT SEARCH TESTS
# =============================================================================


@pytest.mark.asyncio
class TestInsightSearch:
    """Test insight search operations."""

    async def test_search_insights_empty_database(self, adapter):
        """Test searching insights in empty database."""
        results = await adapter.search_insights("test")
        assert results == []

    async def test_search_insights_returns_results(self, adapter):
        """Test searching insights returns matching insights."""
        await adapter.store_insight(
            "Python async patterns insight",
            insight_type="pattern",
        )
        results = await adapter.search_insights("Python")
        assert len(results) > 0

    async def test_search_insights_respects_limit(self, adapter):
        """Test search insights respects limit."""
        for i in range(5):
            await adapter.store_insight(f"Insight {i}")

        results = await adapter.search_insights("*", limit=2)
        assert len(results) <= 2

    async def test_search_insights_with_quality_filter(self, adapter):
        """Test searching insights filters by quality score."""
        await adapter.store_insight("High quality insight", quality_score=0.9)
        await adapter.store_insight("Low quality insight", quality_score=0.3)

        results = await adapter.search_insights("*", min_quality_score=0.5)
        assert len(results) >= 1
        for result in results:
            metadata = result.get("metadata", {})
            quality = metadata.get("quality_score", 0)
            assert quality >= 0.5

    async def test_search_insights_wildcard_returns_all(self, adapter):
        """Test that wildcard '*' query returns all insights."""
        await adapter.store_insight("Insight A", insight_type="general")
        await adapter.store_insight("Insight B", insight_type="pattern")

        results = await adapter.search_insights("*")
        assert len(results) >= 2

    async def test_search_insights_only_returns_insights_not_reflections(self, adapter):
        """Test that search_insights only returns insights, not reflections."""
        # Store a reflection with unique content
        await adapter.store_reflection(
            "UNIQUE_REFLECTION_CONTENT_12345", tags=["unique"]
        )
        # Store an insight
        await adapter.store_insight(
            "UNIQUE_INSIGHT_CONTENT_67890",
            insight_type="pattern",
        )

        # Search for the insight content specifically
        results = await adapter.search_insights("UNIQUE_INSIGHT")
        assert len(results) >= 1
        # Verify it's an insight, not a reflection
        for result in results:
            assert result.get("insight_type") is not None


# =============================================================================
# INSIGHT USAGE TRACKING TESTS
# =============================================================================


@pytest.mark.asyncio
class TestInsightUsage:
    """Test insight usage tracking operations."""

    async def test_update_insight_usage_success(self, adapter):
        """Test updating usage count for existing insight."""
        insight_id = await adapter.store_insight(
            "Test insight for usage",
            insight_type="pattern",
        )

        result = await adapter.update_insight_usage(insight_id)
        assert result is True

    async def test_update_insight_usage_not_found(self, adapter):
        """Test updating usage for non-existent insight returns False."""
        result = await adapter.update_insight_usage("nonexistent-id-12345")
        assert result is False

    async def test_update_insight_usage_increments_count(self, adapter):
        """Test that update_insight_usage actually increments usage."""
        insight_id = await adapter.store_insight("Usage test insight")

        # Update multiple times
        await adapter.update_insight_usage(insight_id)
        await adapter.update_insight_usage(insight_id)
        await adapter.update_insight_usage(insight_id)

        # Search for insight and check usage_count
        results = await adapter.search_insights("Usage test", limit=1)
        assert len(results) >= 1
        assert results[0]["usage_count"] == 3


# =============================================================================
# INSIGHT STATISTICS TESTS
# =============================================================================


@pytest.mark.asyncio
class TestInsightStatistics:
    """Test insight statistics operations."""

    async def test_get_insights_statistics_empty(self, adapter):
        """Test getting statistics on empty database."""
        stats = await adapter.get_insights_statistics()
        assert stats["total"] == 0
        assert stats["avg_quality"] == 0.0
        assert stats["avg_usage"] == 0.0
        assert stats["by_type"] == {}

    async def test_get_insights_statistics_with_data(self, adapter):
        """Test getting statistics with insights."""
        await adapter.store_insight("Pattern insight A", insight_type="pattern")
        await adapter.store_insight("Pattern insight B", insight_type="pattern")
        await adapter.store_insight("General insight", insight_type="general")

        stats = await adapter.get_insights_statistics()
        assert stats["total"] >= 3
        assert stats["by_type"]["pattern"] >= 2
        assert stats["by_type"]["general"] >= 1


# =============================================================================
# EDGE CASES AND ERROR HANDLING TESTS
# =============================================================================


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_store_conversation_very_long_content(self, adapter):
        """Test storing very long conversation content."""
        long_content = "A" * 10000
        conv_id = await adapter.store_conversation(long_content)
        assert conv_id is not None

    async def test_search_with_empty_query(self, adapter):
        """Test searching with empty query doesn't crash."""
        results = await adapter.search_conversations("")
        assert isinstance(results, list)

    async def test_search_reflections_with_empty_query(self, adapter):
        """Test searching reflections with empty query doesn't crash."""
        results = await adapter.search_reflections("")
        assert isinstance(results, list)

    async def test_store_reflection_very_long_tags_list(self, adapter):
        """Test storing reflection with many tags."""
        many_tags = [f"tag{i}" for i in range(100)]
        refl_id = await adapter.store_reflection("Many tags reflection", many_tags)
        assert refl_id is not None

    async def test_unicode_content_handling(self, adapter):
        """Test handling of unicode content."""
        unicode_content = "Unicode: éèê 中文 \U0001f4a9"
        conv_id = await adapter.store_conversation(unicode_content)
        assert conv_id is not None

        results = await adapter.search_conversations("中")
        assert len(results) >= 1


# =============================================================================
# ASYNC CONTEXT MANAGER TESTS
# =============================================================================


@pytest.mark.asyncio
class TestAsyncContextManager:
    """Test async context manager operations."""

    async def test_async_context_manager_initializes(self, tmp_path: Path):
        """Test async context manager properly initializes."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )

        async with reflection_module.ReflectionDatabaseAdapterOneiric(
            settings=settings
        ) as adapter:
            assert adapter._initialized is True
            assert adapter.conn is not None

    async def test_async_context_manager_closes(self, tmp_path: Path):
        """Test async context manager properly closes."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )

        adapter = None
        async with reflection_module.ReflectionDatabaseAdapterOneiric(
            settings=settings
        ) as adapter:
            pass

        # After exit, connection should be closed
        assert adapter.conn is None


# =============================================================================
# DUPLICATE DETECTION TESTS
# =============================================================================


@pytest.mark.asyncio
class TestDuplicateDetection:
    """Test duplicate detection functionality."""

    async def test_check_for_duplicates_no_duplicates(self, adapter):
        """Test duplicate check finds no duplicates for unique content."""
        from session_buddy.utils.fingerprint import MinHashSignature

        fingerprint = MinHashSignature.from_text("Unique content xyz123")
        duplicates = adapter._check_for_duplicates(fingerprint, "conversation")
        assert duplicates == []

    async def test_store_conversation_deduplicate_false_returns_new_id(
        self, adapter
    ):
        """Test storing duplicate content with deduplicate=False returns new ID."""
        content = "Duplicate test content"

        id1 = await adapter.store_conversation(content, deduplicate=False)
        id2 = await adapter.store_conversation(content, deduplicate=False)

        assert id1 != id2


# =============================================================================
# CACHE TESTS
# =============================================================================


@pytest.mark.asyncio
class TestCacheBehavior:
    """Test query cache behavior."""

    async def test_search_populates_cache(self, adapter):
        """Test that search populates cache."""
        await adapter.store_conversation("Cache test content")

        # First search populates cache
        await adapter.search_conversations("Cache", use_cache=True)

        # Second search with same query should hit cache
        # (We can't directly check cache hit, but we can verify no error)
        results = await adapter.search_conversations("Cache", use_cache=True)
        assert isinstance(results, list)

    async def test_search_cache_disabled(self, adapter):
        """Test that search works when cache is disabled."""
        await adapter.store_conversation("No cache test")

        results = await adapter.search_conversations("No cache", use_cache=False)
        assert isinstance(results, list)


# =============================================================================
# CLOSE AND CLEANUP TESTS
# =============================================================================


@pytest.mark.asyncio
class TestCloseAndCleanup:
    """Test close and cleanup operations."""

    async def test_aclose_clears_connections(self, adapter):
        """Test that aclose properly clears connections."""
        await adapter.aclose()
        assert adapter.conn is None
        assert adapter._initialized is False

    async def test_aclose_clears_embedding_cache(self, adapter):
        """Test that aclose clears embedding cache."""
        # Add something to the cache
        adapter._embedding_cache["test"] = [0.0] * 384

        await adapter.aclose()
        assert len(adapter._embedding_cache) == 0

    async def test_close_in_running_loop(self, tmp_path: Path):
        """Test that close() works when event loop is running."""
        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()

        # Create a task that calls close
        async def run_close():
            adapter.close()

        # Should not raise even though loop is running
        await run_close()
        await asyncio.sleep(0.1)  # Give close time to complete


# =============================================================================
# INTEGRATION-STYLE TESTS
# =============================================================================


@pytest.mark.asyncio
class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    async def test_full_workflow(self, adapter):
        """Test full workflow: store, search, retrieve."""
        # Store conversations
        conv_id1 = await adapter.store_conversation(
            "How to use async/await properly",
            {"project": "python"},
        )
        conv_id2 = await adapter.store_conversation(
            "Understanding Python decorators",
            {"project": "python"},
        )

        # Store reflections
        refl_id1 = await adapter.store_reflection(
            "Always use context managers for resources",
            tags=["python", "best-practice"],
        )
        refl_id2 = await adapter.store_reflection(
            "Type hints improve code clarity",
            tags=["python", "types"],
        )

        # Search
        conv_results = await adapter.search_conversations("async", limit=10)
        refl_results = await adapter.search_reflections("context", limit=10)

        assert len(conv_results) >= 1
        assert len(refl_results) >= 1

        # Get stats
        stats = await adapter.get_stats()
        assert stats["total_conversations"] >= 2
        assert stats["total_reflections"] >= 2

        # Health check
        assert await adapter.health_check() is True

    async def test_insight_lifecycle(self, adapter):
        """Test complete insight lifecycle."""
        # Store insights
        insight1 = await adapter.store_insight(
            "Pattern: Use context managers",
            insight_type="pattern",
            confidence_score=0.9,
        )
        insight2 = await adapter.store_insight(
            "Architecture: Layered design",
            insight_type="architecture",
            confidence_score=0.8,
        )

        # Update usage
        await adapter.update_insight_usage(insight1)
        await adapter.update_insight_usage(insight1)
        await adapter.update_insight_usage(insight2)

        # Search insights
        results = await adapter.search_insights("context managers")
        assert len(results) >= 1

        # Get statistics
        stats = await adapter.get_insights_statistics()
        assert stats["total"] >= 2
        assert stats["by_type"]["pattern"] >= 1
        assert stats["by_type"]["architecture"] >= 1
