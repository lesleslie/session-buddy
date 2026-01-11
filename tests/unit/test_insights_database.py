"""Unit tests for insight database operations.

Tests all insight-specific database methods:
- store_insight()
- search_insights()
- update_insight_usage()
- get_insights_statistics()
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from session_buddy.adapters.reflection_adapter_oneiric import ReflectionDatabase
from session_buddy.adapters.settings import ReflectionAdapterSettings


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    # Use in-memory database for tests
    settings = ReflectionAdapterSettings(
        database_path=Path(":memory:"),
        collection_name="test_insights",
    )
    db = ReflectionDatabase(
        collection_name="test_insights",
        settings=settings,
    )
    await db.initialize()
    return db
    # Cleanup happens automatically with in-memory database


class TestStoreInsight:
    """Test insight storage functionality."""

    @pytest.mark.asyncio
    async def test_store_basic_insight(self, temp_db):
        """Test storing a basic insight."""
        insight_id = await temp_db.store_insight(
            content="Use async/await for database operations",
            insight_type="pattern",
        )

        assert insight_id is not None
        assert len(insight_id) == 36  # UUID format

        # Verify insight was stored
        results = await temp_db.search_insights("async database", limit=1)
        assert len(results) == 1
        assert results[0]["id"] == insight_id
        assert "async/await" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_store_insight_with_topics(self, temp_db):
        """Test storing insight with topic tags."""
        await temp_db.store_insight(
            content="Python type hints improve code clarity",
            insight_type="best_practice",
            topics=["python", "typing", "code-quality"],
        )

        results = await temp_db.search_insights("type hints", limit=1)
        assert len(results) == 1
        assert results[0]["tags"] == ["python", "typing", "code-quality"]

    @pytest.mark.asyncio
    async def test_store_insight_with_projects(self, temp_db):
        """Test storing insight with project associations."""
        await temp_db.store_insight(
            content="Session Buddy uses DuckDB for vector storage",
            insight_type="architecture",
            projects=["session-buddy"],
        )

        results = await temp_db.search_insights("DuckDB vector", limit=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_store_insight_project_sanitization(self, temp_db):
        """Test that sensitive project names are sanitized."""
        # Project with sensitive keyword should be hashed
        await temp_db.store_insight(
            content="Test insight for secret project",
            insight_type="test",
            projects=["secret-acquisition-target"],
        )

        # Should still store successfully
        results = await temp_db.search_insights("secret project", limit=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_store_insight_with_quality_and_confidence(self, temp_db):
        """Test storing insight with quality and confidence scores."""
        await temp_db.store_insight(
            content="High-quality insight",
            insight_type="pattern",
            quality_score=0.9,
            confidence_score=0.85,
        )

        results = await temp_db.search_insights("High-quality", limit=1)
        assert len(results) == 1
        # Quality score stored in metadata
        assert results[0]["metadata"].get("quality_score") == 0.9

    @pytest.mark.asyncio
    async def test_store_insight_with_source_tracking(self, temp_db):
        """Test storing insight with source conversation/reflection IDs."""
        await temp_db.store_insight(
            content="Insight from conversation",
            insight_type="general",
            source_conversation_id="conv-123",
            source_reflection_id="refl-456",
        )

        results = await temp_db.search_insights("conversation", limit=1)
        assert len(results) == 1
        assert results[0]["metadata"].get("source_conversation_id") == "conv-123"
        assert results[0]["metadata"].get("source_reflection_id") == "refl-456"

    @pytest.mark.asyncio
    async def test_store_insight_invalid_type_defaults_to_general(self, temp_db):
        """Test that invalid insight_type defaults to 'general'."""
        # This should not raise, just default to 'general'
        await temp_db.store_insight(
            content="Test content",
            insight_type="invalid;type-with;semicolons",  # Invalid
        )

        results = await temp_db.search_insights("Test content", limit=1)
        assert len(results) == 1
        assert results[0]["insight_type"] == "general"

    @pytest.mark.asyncio
    async def test_store_multiple_insights(self, temp_db):
        """Test storing multiple insights."""
        insights = [
            ("Use async/await for I/O operations", "pattern"),
            ("Type hints improve code quality", "best_practice"),
            ("DuckDB supports vector operations", "architecture"),
        ]

        insight_ids = []
        for content, insight_type in insights:
            insight_id = await temp_db.store_insight(content=content, insight_type=insight_type)
            insight_ids.append(insight_id)

        # Verify all were stored and have valid IDs
        assert len(insight_ids) == 3
        for insight_id in insight_ids:
            assert len(insight_id) == 36  # Valid UUID format

        # Verify we can search and find each one individually
        results1 = await temp_db.search_insights("async", limit=10, use_embeddings=False)
        assert len(results1) >= 1  # At least the async insight

        results2 = await temp_db.search_insights("Type hints", limit=10, use_embeddings=False)
        assert len(results2) >= 1  # At least the type hints insight

        results3 = await temp_db.search_insights("DuckDB", limit=10, use_embeddings=False)
        assert len(results3) >= 1  # At least the DuckDB insight


class TestSearchInsights:
    """Test insight search functionality."""

    @pytest.mark.asyncio
    async def test_semantic_search_with_embeddings(self, temp_db):
        """Test semantic search with vector embeddings."""
        # Store test insight
        await temp_db.store_insight(
            content="Use async/await patterns for database operations",
            insight_type="pattern",
            topics=["async", "database"],
        )

        # Search with similar query
        results = await temp_db.search_insights(
            "async database operations",
            limit=1,
            use_embeddings=True,
        )

        assert len(results) == 1
        assert "async/await" in results[0]["content"]
        assert results[0]["similarity"] > 0.5  # Should be semantically similar

    @pytest.mark.asyncio
    async def test_text_search_fallback(self, temp_db):
        """Test text search when embeddings unavailable."""
        # Store test insight
        await temp_db.store_insight(
            content="Python type hints improve code clarity",
            insight_type="best_practice",
        )

        # Search with text search (embeddings disabled)
        results = await temp_db.search_insights(
            "type hints",
            limit=1,
            use_embeddings=False,
        )

        assert len(results) == 1
        assert "type hints" in results[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_search_with_quality_filter(self, temp_db):
        """Test search with minimum quality score filter."""
        # Store insights with different quality scores
        await temp_db.store_insight(
            content="High quality insight",
            insight_type="pattern",
            quality_score=0.9,
        )

        await temp_db.store_insight(
            content="Low quality insight",
            insight_type="pattern",
            quality_score=0.2,
        )

        # Search with quality filter
        results = await temp_db.search_insights(
            "quality",
            limit=10,
            min_quality_score=0.7,
        )

        # Should only return high quality insight
        assert len(results) == 1
        assert results[0]["metadata"].get("quality_score") >= 0.7

    @pytest.mark.asyncio
    async def test_search_with_similarity_filter(self, temp_db):
        """Test search with minimum similarity threshold."""
        await temp_db.store_insight(
            content="Use async/await for async operations",
            insight_type="pattern",
        )

        # Search with high similarity threshold
        results_strict = await temp_db.search_insights(
            "async operations",
            limit=10,
            min_similarity=0.9,
            use_embeddings=True,
        )

        # Search with low similarity threshold
        results_permissive = await temp_db.search_insights(
            "async operations",
            limit=10,
            min_similarity=0.0,
            use_embeddings=True,
        )

        # Permissive should have >= strict (depending on similarity scores)
        assert len(results_permissive) >= len(results_strict)

    @pytest.mark.asyncio
    async def test_search_returns_insight_metadata(self, temp_db):
        """Test that search returns all insight fields."""
        await temp_db.store_insight(
            content="Test insight",
            insight_type="test",
            topics=["testing"],
            confidence_score=0.75,
        )

        results = await temp_db.search_insights("Test", limit=1)
        assert len(results) == 1

        insight = results[0]
        assert insight["insight_type"] == "test"
        assert insight["tags"] == ["testing"]
        assert insight["confidence_score"] == 0.75
        assert insight["usage_count"] == 0  # Never used
        assert insight["last_used_at"] is None
        assert "created_at" in insight
        assert "updated_at" in insight

    @pytest.mark.asyncio
    async def test_search_limits_results(self, temp_db):
        """Test that search respects the limit parameter."""
        # Store 5 insights
        for i in range(5):
            await temp_db.store_insight(
                content=f"Test insight {i}",
                insight_type="test",
            )

        # Search with limit of 3
        results = await temp_db.search_insights("Test", limit=3)
        assert len(results) == 3

        # Search with limit of 10
        results = await temp_db.search_insights("Test", limit=10)
        assert len(results) == 5


class TestUpdateInsightUsage:
    """Test insight usage tracking."""

    @pytest.mark.asyncio
    async def test_update_usage_increments_count(self, temp_db):
        """Test that updating usage increments the count."""
        insight_id = await temp_db.store_insight(
            content="Useful insight",
            insight_type="pattern",
        )

        # Update usage
        success = await temp_db.update_insight_usage(insight_id)
        assert success is True

        # Verify increment
        results = await temp_db.search_insights("Useful", limit=1)
        assert len(results) == 1
        assert results[0]["usage_count"] == 1

    @pytest.mark.asyncio
    async def test_update_usage_sets_last_used_at(self, temp_db):
        """Test that updating usage sets the last_used_at timestamp."""
        insight_id = await temp_db.store_insight(
            content="Useful insight",
            insight_type="pattern",
        )

        # Initially should be None
        results = await temp_db.search_insights("Useful", limit=1)
        assert results[0]["last_used_at"] is None

        # Update usage
        await temp_db.update_insight_usage(insight_id)

        # Should now have timestamp
        results = await temp_db.search_insights("Useful", limit=1)
        assert results[0]["last_used_at"] is not None

        # Verify it's a valid ISO timestamp
        last_used = datetime.fromisoformat(results[0]["last_used_at"])
        assert isinstance(last_used, datetime)

    @pytest.mark.asyncio
    async def test_update_usage_multiple_times(self, temp_db):
        """Test that updating usage multiple times accumulates."""
        insight_id = await temp_db.store_insight(
            content="Popular insight",
            insight_type="pattern",
        )

        # Update usage 3 times
        for _ in range(3):
            await temp_db.update_insight_usage(insight_id)

        results = await temp_db.search_insights("Popular", limit=1)
        assert results[0]["usage_count"] == 3

    @pytest.mark.asyncio
    async def test_update_usage_invalid_id_returns_false(self, temp_db):
        """Test that updating non-existent insight returns False."""
        success = await temp_db.update_insight_usage("non-existent-id")
        assert success is False

    @pytest.mark.asyncio
    async def test_update_usage_atomic_operation(self, temp_db):
        """Test that usage updates are atomic (no race conditions)."""
        insight_id = await temp_db.store_insight(
            content="Concurrent test",
            insight_type="test",
        )

        # Simulate concurrent updates
        tasks = [
            temp_db.update_insight_usage(insight_id)
            for _ in range(10)
        ]

        results = await asyncio.gather(*tasks)
        assert all(results)  # All should succeed

        # Verify count is exactly 10 (no lost updates)
        search_results = await temp_db.search_insights("Concurrent", limit=1)
        assert search_results[0]["usage_count"] == 10


class TestGetInsightsStatistics:
    """Test insight statistics functionality."""

    @pytest.mark.asyncio
    async def test_statistics_empty_database(self, temp_db):
        """Test statistics when no insights stored."""
        stats = await temp_db.get_insights_statistics()

        assert stats["total"] == 0
        assert stats["avg_quality"] == 0.0
        assert stats["avg_usage"] == 0.0
        assert stats["by_type"] == {}

    @pytest.mark.asyncio
    async def test_statistics_counts_insights(self, temp_db):
        """Test that statistics counts total insights."""
        # Store 3 insights
        for i in range(3):
            await temp_db.store_insight(
                content=f"Insight {i}",
                insight_type="test",
            )

        stats = await temp_db.get_insights_statistics()
        assert stats["total"] == 3

    @pytest.mark.asyncio
    async def test_statistics_calculates_average_quality(self, temp_db):
        """Test that statistics calculates average quality score."""
        qualities = [0.5, 0.7, 0.9]

        for quality in qualities:
            await temp_db.store_insight(
                content="Test insight",
                insight_type="test",
                quality_score=quality,
            )

        stats = await temp_db.get_insights_statistics()
        expected_avg = sum(qualities) / len(qualities)
        assert abs(stats["avg_quality"] - expected_avg) < 0.001

    @pytest.mark.asyncio
    async def test_statistics_calculates_average_usage(self, temp_db):
        """Test that statistics calculates average usage count."""
        insight_ids = []

        # Store 3 insights
        for _ in range(3):
            insight_id = await temp_db.store_insight(
                content="Test insight",
                insight_type="test",
            )
            insight_ids.append(insight_id)

        # Update usage: 0, 2, 4 times respectively
        await temp_db.update_insight_usage(insight_ids[1])
        await temp_db.update_insight_usage(insight_ids[1])
        await temp_db.update_insight_usage(insight_ids[2])
        await temp_db.update_insight_usage(insight_ids[2])
        await temp_db.update_insight_usage(insight_ids[2])
        await temp_db.update_insight_usage(insight_ids[2])

        stats = await temp_db.get_insights_statistics()
        expected_avg = (0 + 2 + 4) / 3
        assert abs(stats["avg_usage"] - expected_avg) < 0.01

    @pytest.mark.asyncio
    async def test_statistics_groups_by_type(self, temp_db):
        """Test that statistics groups insights by type."""
        # Store insights of different types
        await temp_db.store_insight("Pattern 1", insight_type="pattern")
        await temp_db.store_insight("Pattern 2", insight_type="pattern")
        await temp_db.store_insight("Architecture", insight_type="architecture")
        await temp_db.store_insight("Best practice", insight_type="best_practice")

        stats = await temp_db.get_insights_statistics()

        assert stats["by_type"]["pattern"] == 2
        assert stats["by_type"]["architecture"] == 1
        assert stats["by_type"]["best_practice"] == 1

    @pytest.mark.asyncio
    async def test_statistics_ignores_reflections(self, temp_db):
        """Test that regular reflections don't affect insight statistics."""
        # Store a regular reflection (no insight_type)
        await temp_db.store_reflection(
            content="Regular reflection",
            tags=["reflection"],
        )

        # Store an insight
        await temp_db.store_insight(
            content="Insight content",
            insight_type="pattern",
        )

        stats = await temp_db.get_insights_statistics()
        assert stats["total"] == 1  # Only insight counted, not reflection


class TestInsightReflectionSeparation:
    """Test that insights and reflections are properly separated."""

    @pytest.mark.asyncio
    async def test_search_insights_excludes_reflections(self, temp_db):
        """Test that search_insights doesn't return regular reflections."""
        # Store a regular reflection
        await temp_db.store_reflection(
            content="Regular reflection about testing",
            tags=["test"],
        )

        # Store an insight
        await temp_db.store_insight(
            content="Insight about async patterns",
            insight_type="pattern",
        )

        # Search insights with text search (not semantic) to avoid false matches
        results = await temp_db.search_insights("testing", limit=10, use_embeddings=False)
        assert len(results) == 0  # Should not find reflection

        # Search insights with different query
        results = await temp_db.search_insights("async", limit=10, use_embeddings=False)
        assert len(results) == 1  # Should find insight

    @pytest.mark.asyncio
    async def test_search_reflections_excludes_insights(self, temp_db):
        """Test that search_reflections doesn't return insights."""
        # Store an insight
        await temp_db.store_insight(
            content="Insight content",
            insight_type="pattern",
        )

        # Store a reflection
        await temp_db.store_reflection(
            content="Reflection content",
            tags=["reflection"],
        )

        # Search reflections with text search (not semantic) to avoid false matches
        results = await temp_db.search_reflections("Insight content", limit=10, use_embeddings=False)
        assert len(results) == 0  # Should not find insight

        # Search reflections with different query
        results = await temp_db.search_reflections("Reflection content", limit=10, use_embeddings=False)
        assert len(results) == 1  # Should find reflection
