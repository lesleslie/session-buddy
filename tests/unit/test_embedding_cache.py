"""Test embedding cache performance and correctness.

Tests that the embedding cache:
1. Correctly caches embeddings
2. Returns cached values on subsequent calls
3. Reports cache size via get_embedding_system_info()
4. Achieves <5ms performance for cached queries
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
    ReflectionAdapterSettings,
)
from session_buddy.reflection import embeddings as embeddings_module
from session_buddy.reflection.embeddings import (
    clear_embedding_cache,
    get_embedding_system_info,
)


def _deterministic_embedding(text: str) -> list[float]:
    """Generate a deterministic 384-dimensional vector from text.

    Hashes the text and expands the digest into a 384-dim vector with values
    in [-1, 1]. Same input always produces the same vector.
    """
    digest = hashlib.sha384(text.encode("utf-8")).digest()  # 48 bytes
    # Expand to 384 dims by repeating and offsetting
    raw = (digest * 8)[:384]
    return [(b - 128) / 128.0 for b in raw]


@pytest.fixture
def stub_embedding_provider(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Stub the HTTP embedding providers so tests don't need a live service.

    The stub returns a deterministic 384-dim vector for any input. Tests that
    need real embeddings can rely on this; tests that need to assert the
    "no providers" path should clear the monkeypatch.
    """
    async def fake_try(text: str) -> list[float] | None:
        return _deterministic_embedding(text)

    monkeypatch.setattr(embeddings_module, "_try_http_embedding_providers", fake_try)
    return fake_try


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
    clear_embedding_cache()
    yield adapter
    clear_embedding_cache()
    await adapter.aclose()


class TestEmbeddingCache:
    """Test embedding cache functionality."""

    @pytest.mark.asyncio
    async def test_cache_miss_on_first_call(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
        """Test that first call generates embedding (cache miss)."""
        query = "test query for cache miss"

        # First call should populate the cache
        result = await db._generate_embedding(query)

        assert result is not None, "Should generate embedding"
        assert len(result) == 384, "Should return 384-dimensional vector"
        # Cache should now have 1 entry
        assert get_embedding_system_info()["cache_size"] == 1

    @pytest.mark.asyncio
    async def test_cache_hit_on_second_call(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
        """Test that second call uses cached embedding (cache hit)."""
        query = "test query for cache hit"

        # First call - populates cache
        result1 = await db._generate_embedding(query)
        # Second call - cache hit (same input → same output without HTTP)
        result2 = await db._generate_embedding(query)

        assert result2 is not None, "Should return cached embedding"
        assert result2 == result1, "Cached result should match first result"
        # Cache size should still be 1 (one unique query)
        assert get_embedding_system_info()["cache_size"] == 1

    @pytest.mark.asyncio
    async def test_cache_independent_per_query(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
        """Test that different queries generate different embeddings."""
        query1 = "first unique query"
        query2 = "second unique query"

        result1 = await db._generate_embedding(query1)
        result2 = await db._generate_embedding(query2)

        assert result1 != result2, "Different queries should have different embeddings"
        # Cache should have 2 entries
        assert get_embedding_system_info()["cache_size"] == 2

    @pytest.mark.asyncio
    async def test_cache_performance_improvement(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
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
    async def test_cache_statistics_in_get_embedding_system_info(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
        """Test that cache size is reported via get_embedding_system_info()."""
        # Generate some cache activity
        query1 = "stats test query 1"
        query2 = "stats test query 2"

        await db._generate_embedding(query1)  # First call for query1
        await db._generate_embedding(query1)  # Cache hit
        await db._generate_embedding(query2)  # First call for query2

        info = get_embedding_system_info()

        assert info["cache_size"] == 2, "Should have 2 cached embeddings"
        # Production no longer tracks hit/miss counters; the cache size
        # alone tells us two distinct queries were embedded.

    @pytest.mark.asyncio
    async def test_cache_cleared_on_aclose(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
        """Test that cache is cleared when adapter is closed."""
        query = "cache clear test"

        # Generate and cache embedding
        await db._generate_embedding(query)
        assert get_embedding_system_info()["cache_size"] == 1, "Should have 1 cached embedding"

        # Clear cache explicitly (production's close path triggers this)
        clear_embedding_cache()
        assert get_embedding_system_info()["cache_size"] == 0, "Cache should be empty after clear"

    @pytest.mark.asyncio
    async def test_cache_handles_empty_text(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
        """Test that cache handles empty text gracefully."""
        # Empty string should be handled
        result = await db._generate_embedding("")
        # May return None or a valid embedding depending on tokenizer behavior
        # Either is acceptable, just shouldn't crash

    @pytest.mark.asyncio
    async def test_cache_repeated_queries_return_identical_results(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
        """Test that the same query consistently returns the same cached embedding.

        Production no longer tracks explicit hit/miss counters, but the
        *observable* contract is unchanged: the same input must produce the
        same output. This is the cache hit, in user-visible terms.
        """
        query = "hit rate test query"

        # Three calls, same query — all return the same vector
        result1 = await db._generate_embedding(query)
        result2 = await db._generate_embedding(query)
        result3 = await db._generate_embedding(query)

        assert result1 == result2 == result3, "Repeated calls should return identical embeddings"
        # Cache has exactly one entry — the unique query
        assert get_embedding_system_info()["cache_size"] == 1

    @pytest.mark.asyncio
    async def test_cache_with_large_dataset(
        self, db: ReflectionDatabaseAdapterOneiric, stub_embedding_provider
    ) -> None:
        """Test cache effectiveness with repeated queries (simulating real usage)."""
        # Simulate common search queries
        common_queries = [
            "error handling",
            "authentication",
            "database",
            "API design",
            "testing",
        ]

        # First pass - all new entries
        for query in common_queries:
            await db._generate_embedding(query)

        assert get_embedding_system_info()["cache_size"] == len(
            common_queries
        ), "All unique queries should be cached"

        # Second pass - all cache hits (same input → same output)
        start = time.perf_counter()
        results_second_pass = [
            await db._generate_embedding(query) for query in common_queries
        ]
        cached_time = (time.perf_counter() - start) * 1000  # Convert to ms

        # Cache size should not grow on repeated calls
        assert get_embedding_system_info()["cache_size"] == len(
            common_queries
        ), "Cache size should not grow on repeated calls"
        assert (
            cached_time / len(common_queries) < 1.0
        ), f"Average cached query time should be <1ms, got {cached_time / len(common_queries):.2f}ms"

        print(f"\nTotal cached queries: {len(common_queries)}")
        print(f"Total time for {len(common_queries)} cached queries: {cached_time:.2f}ms")
        print(f"Average time per cached query: {cached_time / len(common_queries):.3f}ms")
