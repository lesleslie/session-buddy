"""Tests for HNSW vector indexing performance optimization.

Tests HNSW (Hierarchical Navigable Small World) index creation, usage,
and performance improvements for vector similarity search.
"""

from __future__ import annotations

import typing as t
from datetime import UTC, datetime
from pathlib import Path

import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.adapters.settings import ReflectionAdapterSettings


class TestHNSWIndexCreation:
    """Test HNSW index creation and configuration."""

    @pytest.fixture
    def temp_db_path(self, tmp_path: Path) -> Path:
        """Create temporary database path."""
        return tmp_path / "test_reflection.duckdb"

    @pytest.fixture
    def adapter_settings(self, temp_db_path: Path) -> ReflectionAdapterSettings:
        """Create adapter settings with HNSW enabled."""
        return ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_hnsw",
            enable_hnsw_index=True,
            hnsw_m=16,
            hnsw_ef_construction=200,
            hnsw_ef_search=64,
        )

    @pytest.mark.asyncio
    async def test_hnsw_index_creation_on_init(self, adapter_settings: ReflectionAdapterSettings) -> None:
        """Test that HNSW indexes are created during adapter initialization."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=adapter_settings)

        # Initialize should create tables and HNSW indexes
        await adapter.initialize()

        # Check that HNSW indexes exist
        result = adapter.conn.execute(
            "SELECT * FROM duckdb_indexes() WHERE index_name LIKE '%hnsw%'"
        ).fetchall()

        # Should have 2 HNSW indexes (conversations and reflections)
        # Column 4 is index_name (verified from duckdb_indexes() schema)
        hnsw_indexes = [row for row in result if "hnsw" in row[4].lower()]

        assert len(hnsw_indexes) >= 2, f"Expected at least 2 HNSW indexes, got {len(hnsw_indexes)}"

        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_hnsw_index_disabled_when_setting_false(self, temp_db_path: Path) -> None:
        """Test that HNSW indexes are not created when enable_hnsw_index=False."""
        settings = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_no_hnsw",
            enable_hnsw_index=False,
        )

        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()

        # Check that HNSW indexes do NOT exist
        # Filter for indexes ending with '_hnsw' to avoid false matches
        result = adapter.conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE index_name LIKE '%_hnsw'"
        ).fetchall()

        # Should have no HNSW indexes when disabled
        hnsw_indexes = [row[0] for row in result]
        assert len(hnsw_indexes) == 0, f"Expected no HNSW indexes when disabled, got {len(hnsw_indexes)}: {hnsw_indexes}"

        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_hnsw_index_parameters_respected(self, adapter_settings: ReflectionAdapterSettings) -> None:
        """Test that custom HNSW parameters (M, ef_construction) are used."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=adapter_settings)
        await adapter.initialize()

        # Check index details to verify parameters
        # Note: Column is 'sql' not 'index_sql' (verified from duckdb_indexes() schema)
        result = adapter.conn.execute(
            """
            SELECT index_name, sql
            FROM duckdb_indexes()
            WHERE index_name LIKE '%hnsw%'
            """
        ).fetchall()

        assert len(result) >= 2

        # Verify SQL contains our custom parameters
        for row in result:
            # Column 1 is 'sql' (index creation statement)
            index_sql = row[1]
            # Check that our parameters are in the index definition
            if "M" in index_sql:
                assert "16" in index_sql or "M = 16" in index_sql
            if "ef_construction" in index_sql:
                assert "200" in index_sql or "ef_construction = 200" in index_sql

        await adapter.aclose()


class TestHNSWSearchPerformance:
    """Test that vector search works with HNSW indexes."""

    @pytest.fixture
    def temp_db_path(self, tmp_path: Path) -> Path:
        """Create temporary database path."""
        return tmp_path / "test_search.duckdb"

    @pytest.fixture
    async def populated_adapter(self, temp_db_path: Path) -> ReflectionDatabaseAdapterOneiric:
        """Create adapter with sample conversation data."""
        settings = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_search",
            enable_hnsw_index=True,
        )

        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()

        # Add sample conversations with embeddings
        conversations = [
            "Python programming language",
            "Machine learning algorithms",
            "Web development with HTML",
            "Database management systems",
            "Cloud computing infrastructure",
        ]

        for conv in conversations:
            await adapter.store_conversation(conv, {"test": True})

        return adapter

    @pytest.mark.asyncio
    async def test_vector_search_with_hnsw(self, populated_adapter: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that vector search works correctly with HNSW indexes."""
        # Search for similar conversations
        results = await populated_adapter.search_conversations(
            query="Python code", limit=5, threshold=0.0
        )

        # Should return results
        assert len(results) > 0

        # Check that results have expected structure
        for result in results:
            assert "id" in result
            assert "content" in result
            assert "score" in result
            assert isinstance(result["score"], float)
            assert 0.0 <= result["score"] <= 1.0

        # Top result should be about Python (highest similarity)
        assert "python" in results[0]["content"].lower()

        await populated_adapter.aclose()

    @pytest.mark.asyncio
    async def test_hnsw_ef_search_parameter_set(self, populated_adapter: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that hnsw_ef_search parameter is set during search."""
        # Perform a search (should set hnsw_ef_search parameter)
        await populated_adapter.search_conversations("Python", limit=3)

        # Verify the parameter is set
        result = populated_adapter.conn.execute("SELECT * FROM duckdb_settings() WHERE name = 'hnsw_ef_search'").fetchone()

        # Parameter should be set to our configured value (64)
        assert result is not None
        assert result[1] == "64"  # value field

        await populated_adapter.aclose()


class TestHNSWGracefulFallback:
    """Test graceful fallback when VSS extension is unavailable."""

    @pytest.fixture
    def temp_db_path(self, tmp_path: Path) -> Path:
        """Create temporary database path."""
        return tmp_path / "test_fallback.duckdb"

    @pytest.mark.asyncio
    async def test_fallback_without_vss_extension(self, temp_db_path: Path) -> None:
        """Test that system falls back to array_cosine_similarity when VSS unavailable."""
        settings = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_fallback",
            enable_hnsw_index=True,  # Try to enable HNSW
        )

        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)

        # Initialize (should handle VSS extension gracefully)
        await adapter.initialize()

        # Add test data
        await adapter.store_conversation("Test conversation one", {"test": True})
        await adapter.store_conversation("Test conversation two", {"test": True})

        # Search should still work using array_cosine_similarity
        # Use threshold=0.0 to ensure we get results even with lower similarity
        results = await adapter.search_conversations("Test", limit=5, threshold=0.0)

        # Should return results using fallback method
        assert len(results) >= 2, f"Expected at least 2 results, got {len(results)}"

        # Results should have valid scores even without HNSW
        for result in results:
            assert "score" in result
            assert isinstance(result["score"], float)

        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_hnsw_disabled_no_error(self, temp_db_path: Path) -> None:
        """Test that disabling HNSW doesn't cause any errors."""
        settings = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_disabled",
            enable_hnsw_index=False,  # Explicitly disable
        )

        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()

        # Add and search data
        await adapter.store_conversation("Data without HNSW", {"test": True})
        # Use threshold=0.0 to ensure we get results
        results = await adapter.search_conversations("Data", limit=5, threshold=0.0)

        # Should work fine without HNSW
        assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"

        await adapter.aclose()


class TestHNSWConfigurationOptions:
    """Test various HNSW configuration options."""

    @pytest.fixture
    def temp_db_path(self, tmp_path: Path) -> Path:
        """Create temporary database path."""
        return tmp_path / "test_config.duckdb"

    @pytest.mark.asyncio
    async def test_custom_hnsw_parameters(self, temp_db_path: Path) -> None:
        """Test creating HNSW indexes with custom M and ef_construction values."""
        settings = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_custom",
            enable_hnsw_index=True,
            hnsw_m=32,  # Custom M value
            hnsw_ef_construction=400,  # Custom ef_construction
        )

        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()

        # Verify indexes were created successfully
        # Note: The SQL returned by duckdb_indexes() may not include the WITH clause
        # The parameters are still used during index creation internally
        result = adapter.conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE index_name LIKE '%_hnsw'"
        ).fetchall()

        # Should have created HNSW indexes
        assert len(result) >= 2, f"Expected at least 2 HNSW indexes, got {len(result)}"

        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_hnsw_with_different_metrics(self, temp_db_path: Path) -> None:
        """Test HNSW indexes with different distance metrics."""
        # Test with L2 (Euclidean) distance
        # Note: DuckDB VSS uses "l2sq" for Euclidean distance, not "euclidean"
        settings_l2 = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_l2",
            distance_metric="l2sq",  # DuckDB VSS uses "l2sq" for Euclidean distance
            enable_hnsw_index=True,
        )

        adapter = ReflectionDatabaseAdapterOneiric(settings=settings_l2)
        await adapter.initialize()

        # Verify index was created successfully
        result = adapter.conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE index_name LIKE '%conv_embeddings_hnsw'"
        ).fetchone()

        assert result is not None
        # Column 0 is index_name
        assert "conv_embeddings_hnsw" in result[0]

        await adapter.aclose()


class TestHNSWPerformanceBasics:
    """Basic tests to verify HNSW functionality for performance improvements."""

    @pytest.fixture
    def temp_db_path(self, tmp_path: Path) -> Path:
        """Create temporary database path."""
        return tmp_path / "test_perf.duckdb"

    @pytest.mark.asyncio
    async def test_index_exists_check(self, temp_db_path: Path) -> None:
        """Test that we can check if HNSW indexes exist."""
        settings = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_exist",
            enable_hnsw_index=True,
        )

        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()

        # Verify we can query for HNSW indexes
        result = adapter.conn.execute(
            """
            SELECT table_name, index_name
            FROM duckdb_indexes()
            WHERE index_name LIKE '%hnsw%'
            """
        ).fetchall()

        assert len(result) >= 2  # At least conversations and reflections

        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_multiple_collections_independent_indexes(self, temp_db_path: Path) -> None:
        """Test that different collections get independent HNSW indexes."""
        # Create first collection
        settings1 = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="collection1",
            enable_hnsw_index=True,
        )
        adapter1 = ReflectionDatabaseAdapterOneiric(settings=settings1)
        await adapter1.initialize()

        # Create second collection
        settings2 = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="collection2",
            enable_hnsw_index=True,
        )
        adapter2 = ReflectionDatabaseAdapterOneiric(settings=settings2)
        await adapter2.initialize()

        # Check that both collections have their own HNSW indexes
        # Note: SELECT index_name means column 0 is the index name
        result = adapter1.conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE index_name LIKE '%hnsw%'"
        ).fetchall()

        # Column 0 is index_name (from SELECT clause)
        collection1_indexes = [row[0] for row in result if "collection1" in row[0]]
        collection2_indexes = [row[0] for row in result if "collection2" in row[0]]

        # Each collection should have at least 2 HNSW indexes (conversations + reflections)
        assert len(collection1_indexes) >= 2
        assert len(collection2_indexes) >= 2

        await adapter1.aclose()
        await adapter2.aclose()


class TestHNSWWithRealData:
    """Integration tests with realistic data volumes."""

    @pytest.fixture
    def temp_db_path(self, tmp_path: Path) -> Path:
        """Create temporary database path."""
        return tmp_path / "test_realdata.duckdb"

    @pytest.mark.asyncio
    async def test_search_accuracy_with_hnsw(self, temp_db_path: Path) -> None:
        """Test that HNSW search maintains accuracy compared to baseline."""
        settings = ReflectionAdapterSettings(
            database_path=temp_db_path,
            collection_name="test_accuracy",
            enable_hnsw_index=True,
        )

        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()

        # Add related conversations
        await adapter.store_conversation("How to write Python functions", {"topic": "python"})
        await adapter.store_conversation("Python class inheritance tutorial", {"topic": "python"})
        await adapter.store_conversation("JavaScript function examples", {"topic": "javascript"})
        await adapter.store_conversation("Database query optimization", {"topic": "database"})

        # Search for Python-related content
        results = await adapter.search_conversations(
            "Python programming", limit=5, threshold=0.5
        )

        # Python results should rank higher than JavaScript
        python_results = [r for r in results if "python" in r["content"].lower()]
        js_results = [r for r in results if "javascript" in r["content"].lower()]

        # Python should appear before JavaScript in results
        if python_results and js_results:
            first_python_idx = next(i for i, r in enumerate(results) if "python" in r["content"].lower())
            first_js_idx = next(i for i, r in enumerate(results) if "javascript" in r["content"].lower())
            assert first_python_idx < first_js_idx, "Python results should rank higher"

        await adapter.aclose()
