"""Test embedding cache performance and correctness.

Tests that the embedding cache:
1. Correctly caches embeddings
2. Returns cached values on subsequent calls
3. Tracks cache statistics accurately
4. Achieves <5ms performance for cached queries
"""

from __future__ import annotations

import asyncio
import time

import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
    ReflectionAdapterSettings,
)


@pytest.fixture
async def db(tmp_path) -> ReflectionDatabaseAdapterOneiric:
    """Create test database with cache enabled."""
    from pathlib import Path

    test_db_path = tmp_path / "test_cache.duckdb"
    settings = ReflectionAdapterSettings(database_path=test_db_path)
    adapter = ReflectionDatabaseAdapterOneiric(
        collection_name="test_cache", settings=settings
    )
    await adapter.initialize()
    yield adapter
    await adapter.aclose()


class TestEmbeddingCache:
    """Test embedding cache functionality."""

    @pytest.mark.asyncio
    async def test_cache_miss_on_first_call(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that first call generates embedding (cache miss)."""
        query = "test query for cache miss"

        # First call should be a cache miss
        result = await db._generate_embedding(query)

        assert result is not None, "Should generate embedding"
        assert len(result) == 384, "Should return 384-dimensional vector"
        assert db._cache_misses == 1, "Should have 1 cache miss"
        assert db._cache_hits == 0, "Should have 0 cache hits"

    @pytest.mark.asyncio
    async def test_cache_hit_on_second_call(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that second call uses cached embedding (cache hit)."""
        query = "test query for cache hit"

        # First call - cache miss
        result1 = await db._generate_embedding(query)
        assert db._cache_misses == 1

        # Second call - cache hit
        result2 = await db._generate_embedding(query)

        assert result2 is not None, "Should return cached embedding"
        assert result2 == result1, "Cached result should match first result"
        assert db._cache_hits == 1, "Should have 1 cache hit"
        assert db._cache_misses == 1, "Should still have only 1 cache miss"

    @pytest.mark.asyncio
    async def test_cache_independent_per_query(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that different queries generate different embeddings."""
        query1 = "first unique query"
        query2 = "second unique query"

        result1 = await db._generate_embedding(query1)
        result2 = await db._generate_embedding(query2)

        assert result1 != result2, "Different queries should have different embeddings"
        assert db._cache_misses == 2, "Should have 2 cache misses"
        assert db._cache_hits == 0, "Should have 0 cache hits"

    @pytest.mark.asyncio
    async def test_cache_performance_improvement(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that cached queries are significantly faster (<5ms target)."""
        query = "performance test query"

        # First call - measure time without cache
        start = time.perf_counter()
        await db._generate_embedding(query)
        first_call_time = (time.perf_counter() - start) * 1000  # Convert to ms

        # Second call - measure time with cache
        start = time.perf_counter()
        await db._generate_embedding(query)
        second_call_time = (time.perf_counter() - start) * 1000  # Convert to ms

        print(f"\nFirst call (no cache): {first_call_time:.2f}ms")
        print(f"Second call (cached): {second_call_time:.2f}ms")
        print(f"Performance improvement: {first_call_time / second_call_time:.1f}x")

        # Cached call should be much faster
        assert second_call_time < 5.0, f"Cached call should be <5ms, got {second_call_time:.2f}ms"
        assert (
            second_call_time < first_call_time
        ), "Cached call should be faster than first call"

    @pytest.mark.asyncio
    async def test_cache_statistics_in_get_stats(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that cache statistics are included in get_stats()."""
        # Generate some cache activity
        query1 = "stats test query 1"
        query2 = "stats test query 2"

        await db._generate_embedding(query1)  # Cache miss
        await db._generate_embedding(query1)  # Cache hit
        await db._generate_embedding(query2)  # Cache miss

        stats = await db.get_stats()

        assert "embedding_cache" in stats, "Should include cache stats"
        cache_stats = stats["embedding_cache"]

        assert cache_stats["size"] == 2, "Should have 2 cached embeddings"
        assert cache_stats["hits"] == 1, "Should have 1 cache hit"
        assert cache_stats["misses"] == 2, "Should have 2 cache misses"
        assert cache_stats["hit_rate"] == 0.3333333333333333, "Hit rate should be 1/3"

    @pytest.mark.asyncio
    async def test_cache_cleared_on_aclose(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that cache is cleared when adapter is closed."""
        query = "cache clear test"

        # Generate and cache embedding
        await db._generate_embedding(query)
        assert len(db._embedding_cache) == 1, "Should have 1 cached embedding"
        assert db._cache_hits == 0
        assert db._cache_misses == 1

        # Close adapter
        await db.aclose()

        # Cache should be cleared
        assert len(db._embedding_cache) == 0, "Cache should be empty after close"
        assert db._cache_hits == 0, "Hits should be reset"
        assert db._cache_misses == 0, "Misses should be reset"

    @pytest.mark.asyncio
    async def test_cache_handles_empty_text(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test that cache handles empty text gracefully."""
        # Empty string should be handled
        result = await db._generate_embedding("")
        # May return None or a valid embedding depending on tokenizer behavior
        # Either is acceptable, just shouldn't crash

    @pytest.mark.asyncio
    async def test_cache_hit_rate_calculation(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test accurate cache hit rate calculation."""
        query = "hit rate test query"

        # Generate 3 calls: 1 miss, 2 hits
        await db._generate_embedding(query)  # Miss
        await db._generate_embedding(query)  # Hit
        await db._generate_embedding(query)  # Hit

        stats = await db.get_stats()
        cache_stats = stats["embedding_cache"]

        assert cache_stats["hits"] == 2, "Should have 2 hits"
        assert cache_stats["misses"] == 1, "Should have 1 miss"
        assert cache_stats["hit_rate"] == 0.6666666666666666, "Hit rate should be 2/3"

    @pytest.mark.asyncio
    async def test_cache_with_large_dataset(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Test cache effectiveness with repeated queries (simulating real usage)."""
        # Simulate common search queries
        common_queries = [
            "error handling",
            "authentication",
            "database",
            "API design",
            "testing",
        ]

        # First pass - all cache misses
        for query in common_queries:
            await db._generate_embedding(query)

        initial_misses = db._cache_misses
        assert initial_misses == len(common_queries), "All should be misses"

        # Second pass - all cache hits
        start = time.perf_counter()
        for query in common_queries:
            await db._generate_embedding(query)
        cached_time = (time.perf_counter() - start) * 1000  # Convert to ms

        assert db._cache_hits == len(common_queries), "All should be hits"
        assert (
            cached_time / len(common_queries) < 1.0
        ), f"Average cached query time should be <1ms, got {cached_time / len(common_queries):.2f}ms"

        print(f"\nTotal cached queries: {len(common_queries)}")
        print(f"Total time for {len(common_queries)} cached queries: {cached_time:.2f}ms")
        print(f"Average time per cached query: {cached_time / len(common_queries):.3f}ms")
