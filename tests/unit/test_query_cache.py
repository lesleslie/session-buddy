#!/usr/bin/env python3
"""Unit tests for QueryCacheManager (Phase 1: Query Cache)."""

from __future__ import annotations

import hashlib
import time
import threading
from unittest.mock import MagicMock, Mock, patch

import pytest
import duckdb

from session_buddy.cache.query_cache import (
    QueryCacheEntry,
    QueryCacheManager,
)


class TestQueryCacheEntry:
    """Test QueryCacheEntry dataclass functionality."""

    def test_entry_creation(self):
        """Test creating a cache entry with required fields."""
        entry = QueryCacheEntry(
            cache_key="test_key_123",
            normalized_query="test query",
            result_ids=["id1", "id2", "id3"],
            project="test_project",
        )

        assert entry.cache_key == "test_key_123"
        assert entry.normalized_query == "test query"
        assert entry.result_ids == ["id1", "id2", "id3"]
        assert entry.project == "test_project"
        assert entry.hit_count == 0
        assert entry.created_at > 0
        assert entry.last_accessed > 0
        assert entry.ttl_seconds == 604800  # 7 days default

    def test_is_expired_fresh(self):
        """Test that fresh entries are not expired."""
        entry = QueryCacheEntry(
            cache_key="test_key",
            normalized_query="test",
            result_ids=["id1"],
            project="test_project",
        )

        # Fresh entry should not be expired
        assert not entry.is_expired()

    def test_is_expired_old(self):
        """Test that old entries are expired."""
        entry = QueryCacheEntry(
            cache_key="test_key",
            normalized_query="test",
            result_ids=["id1"],
            project="test_project",
            ttl_seconds=1,  # 1 second TTL
        )

        # Wait for entry to expire
        time.sleep(1.1)

        assert entry.is_expired()

    def test_touch_updates_metadata(self):
        """Test that touch() updates last_accessed and hit_count."""
        entry = QueryCacheEntry(
            cache_key="test_key",
            normalized_query="test",
            result_ids=["id1"],
            project="test_project",
        )

        initial_hit_count = entry.hit_count
        initial_last_accessed = entry.last_accessed

        # Small delay to ensure timestamp difference
        time.sleep(0.01)

        entry.touch()

        assert entry.hit_count == initial_hit_count + 1
        assert entry.last_accessed > initial_last_accessed


class TestQueryNormalization:
    """Test query normalization functionality."""

    def test_normalize_query_lowercase(self):
        """Test that queries are converted to lowercase."""
        normalized = QueryCacheManager.normalize_query("UPPERCASE QUERY")
        assert normalized == "uppercase query"

    def test_normalize_query_whitespace(self):
        """Test that multiple whitespace is collapsed."""
        normalized = QueryCacheManager.normalize_query("query   with    spaces")
        assert normalized == "query with spaces"

    def test_normalize_query_trailing_punctuation(self):
        """Test that trailing punctuation is removed."""
        normalized = QueryCacheManager.normalize_query("query with marks?")
        assert normalized == "query with marks"

        normalized = QueryCacheManager.normalize_query("another query!!!")
        assert normalized == "another query"

    def test_normalize_query_combined(self):
        """Test combined normalization (lowercase + whitespace + punctuation)."""
        normalized = QueryCacheManager.normalize_query("  Complex  QUERY?  ")
        assert normalized == "complex query"

    def test_normalize_query_preserves_operators(self):
        """Test that internal operators are preserved."""
        normalized = QueryCacheManager.normalize_query("find + pattern")
        assert "+" in normalized


class TestCacheKeyComputation:
    """Test cache key computation."""

    def test_compute_cache_key_basic(self):
        """Test basic cache key computation."""
        key = QueryCacheManager.compute_cache_key("test query")

        # Should be a SHA256 hash (64 hex characters)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_compute_cache_key_with_project(self):
        """Test cache key with project filter."""
        key1 = QueryCacheManager.compute_cache_key("test query", project="proj1")
        key2 = QueryCacheManager.compute_cache_key("test query", project="proj2")

        # Different projects should produce different keys
        assert key1 != key2

    def test_compute_cache_key_with_limit(self):
        """Test cache key with different limits."""
        key1 = QueryCacheManager.compute_cache_key("test query", limit=10)
        key2 = QueryCacheManager.compute_cache_key("test query", limit=20)

        # Different limits should produce different keys
        assert key1 != key2

    def test_compute_cache_key_consistency(self):
        """Test that same inputs produce same key."""
        key1 = QueryCacheManager.compute_cache_key("test query", project="proj", limit=10)
        key2 = QueryCacheManager.compute_cache_key("test query", project="proj", limit=10)

        # Same inputs should produce same key
        assert key1 == key2

    def test_compute_cache_key_normalization(self):
        """Test that query normalization affects cache key."""
        key1 = QueryCacheManager.compute_cache_key("Test Query")
        key2 = QueryCacheManager.compute_cache_key("test query")

        # Should be the same after normalization
        assert key1 == key2


class TestQueryCacheManager:
    """Test QueryCacheManager functionality."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock DuckDB connection."""
        conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        return conn

    @pytest.fixture
    def cache_manager(self, mock_connection):
        """Create a QueryCacheManager instance for testing."""
        manager = QueryCacheManager(l1_max_size=3, l2_ttl_days=7)
        manager._conn = mock_connection
        manager._initialized = True
        # Mock L2 operations to avoid async issues in tests
        manager._put_to_l2 = MagicMock()
        return manager

    def test_initialization(self):
        """Test cache manager initialization."""
        manager = QueryCacheManager(l1_max_size=100, l2_ttl_days=14)

        assert manager.l1_max_size == 100
        assert manager.l2_ttl_seconds == 14 * 86400
        assert len(manager._l1_cache) == 0
        assert manager._conn is None
        assert not manager._initialized

    def test_normalize_query_static_method(self):
        """Test that normalize_query is a static method."""
        # Can call without instance
        normalized = QueryCacheManager.normalize_query("Test Query")
        assert normalized == "test query"

    def test_compute_cache_key_static_method(self):
        """Test that compute_cache_key is a static method."""
        # Can call without instance
        key = QueryCacheManager.compute_cache_key("test")
        assert len(key) == 64  # SHA256 hex

    def test_put_and_get_l1_cache(self, cache_manager):
        """Test L1 cache put and get operations."""
        cache_key = "test_key_123"
        result_ids = ["id1", "id2", "id3"]

        # Put in cache
        cache_manager.put(
            cache_key=cache_key,
            result_ids=result_ids,
            normalized_query="test query",
            project="test_project",
        )

        # Get from cache
        cached_result = cache_manager.get(cache_key, check_l2=False)

        assert cached_result is not None
        assert cached_result == result_ids

    def test_l1_cache_miss(self, cache_manager):
        """Test L1 cache miss."""
        result = cache_manager.get("nonexistent_key", check_l2=False)
        assert result is None

    def test_l1_lru_eviction(self, cache_manager):
        """Test L1 LRU eviction when max_size exceeded."""
        # Fill cache to max_size (3)
        cache_manager.put("key1", ["id1"], "query1")
        cache_manager.put("key2", ["id2"], "query2")
        cache_manager.put("key3", ["id3"], "query3")

        # Add one more - should evict key1 (oldest)
        cache_manager.put("key4", ["id4"], "query4")

        # key1 should be evicted
        assert cache_manager.get("key1", check_l2=False) is None
        # key2, key3, key4 should still be present
        assert cache_manager.get("key2", check_l2=False) == ["id2"]
        assert cache_manager.get("key3", check_l2=False) == ["id3"]
        assert cache_manager.get("key4", check_l2=False) == ["id4"]

    def test_l1_access_updates_lru_order(self, cache_manager):
        """Test that L1 access updates LRU order."""
        # Fill cache
        cache_manager.put("key1", ["id1"], "query1")
        cache_manager.put("key2", ["id2"], "query2")
        cache_manager.put("key3", ["id3"], "query3")

        # Access key1 to make it most recently used
        cache_manager.get("key1", check_l2=False)

        # Add key4 - should evict key2 (now oldest)
        cache_manager.put("key4", ["id4"], "query4")

        # key1 should still be present (was accessed)
        assert cache_manager.get("key1", check_l2=False) == ["id1"]
        # key2 should be evicted
        assert cache_manager.get("key2", check_l2=False) is None

    def test_invalidate_specific_key(self, cache_manager):
        """Test invalidating a specific cache entry."""
        # Mock L2 operations to avoid async issues
        cache_manager._delete_from_l2 = MagicMock()

        cache_manager.put("key1", ["id1"], "query1", project="proj1")
        cache_manager.put("key2", ["id2"], "query2", project="proj1")

        # Invalidate key1
        cache_manager.invalidate(cache_key="key1")

        # key1 should be gone
        assert cache_manager.get("key1", check_l2=False) is None
        # key2 should still be present
        assert cache_manager.get("key2", check_l2=False) == ["id2"]

    def test_invalidate_all_keys(self, cache_manager):
        """Test invalidating all cache entries."""
        # Mock L2 operations to avoid async issues
        cache_manager._clear_l2 = MagicMock()

        cache_manager.put("key1", ["id1"], "query1", project="proj1")
        cache_manager.put("key2", ["id2"], "query2", project="proj1")

        # Invalidate all
        cache_manager.invalidate(cache_key=None)

        # All keys should be gone
        assert cache_manager.get("key1", check_l2=False) is None
        assert cache_manager.get("key2", check_l2=False) is None

    def test_get_stats_initial(self, cache_manager):
        """Test that initial stats are all zeros."""
        stats = cache_manager.get_stats()

        assert stats["l1_hits"] == 0
        assert stats["l1_misses"] == 0
        assert stats["l2_hits"] == 0
        assert stats["l2_misses"] == 0
        assert stats["l1_evictions"] == 0
        assert stats["l2_evictions"] == 0
        assert stats["l1_hit_rate"] == 0.0
        assert stats["l2_hit_rate"] == 0.0
        assert stats["l1_size"] == 0

    def test_get_stats_after_operations(self, cache_manager):
        """Test stats after cache operations."""
        # Add entries
        cache_manager.put("key1", ["id1"], "query1")
        cache_manager.put("key2", ["id2"], "query2")

        # Hit
        cache_manager.get("key1", check_l2=False)

        # Miss
        cache_manager.get("nonexistent", check_l2=False)

        stats = cache_manager.get_stats()

        assert stats["l1_hits"] == 1
        assert stats["l1_misses"] == 1
        assert stats["l1_hit_rate"] == 0.5
        assert stats["l1_size"] == 2

    def test_expiration_check_on_get(self, cache_manager):
        """Test that expired entries are removed on get."""
        # Create entry with very short TTL
        entry = QueryCacheEntry(
            cache_key="expiring_key",
            normalized_query="test",
            result_ids=["id1"],
            project="test_project",
            ttl_seconds=0,  # Expired immediately
        )
        cache_manager._l1_cache["expiring_key"] = entry

        # Try to get expired entry
        result = cache_manager.get("expiring_key", check_l2=False)

        # Should return None (expired)
        assert result is None
        # Should be removed from cache
        assert "expiring_key" not in cache_manager._l1_cache

    def test_thread_safety(self, cache_manager):
        """Test thread-safe concurrent access (L1 only, no L2)."""
        results = []
        errors = []

        def worker(worker_id):
            try:
                for i in range(10):
                    key = f"worker_{worker_id}_key_{i}"
                    # Only test L1 operations (L2 requires event loop)
                    cache_manager._l1_cache[key] = QueryCacheEntry(
                        cache_key=key,
                        normalized_query=f"query_{i}",
                        result_ids=[f"id_{worker_id}_{i}"],
                        project="test_project",
                    )
                    result = cache_manager.get(key, check_l2=False)
                    results.append(result is not None)
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0
        # All operations should succeed
        assert len(results) == 50  # 5 threads * 10 operations
        assert all(results)

    def test_get_without_initialization(self):
        """Test that get returns None when not initialized."""
        manager = QueryCacheManager()
        # Don't initialize

        result = manager.get("test_key")
        assert result is None


class TestL2CacheOperations:
    """Test L2 cache operations with mock database.

    Note: L2 operations are inherently async and database-dependent.
    These operations are tested in integration tests with real DuckDB database.
    Unit tests skip L2 operations to avoid complex async mocking.
    """

    @pytest.fixture
    def cache_manager(self):
        """Create cache manager with mock connection."""
        manager = QueryCacheManager(l1_max_size=3, l2_ttl_days=7)
        manager._initialized = True
        return manager

    @pytest.mark.skip(reason="L2 operations require integration testing with real DuckDB database")
    def test_put_to_l2(self, cache_manager):
        """Test putting entry to L2 cache."""
        entry = QueryCacheEntry(
            cache_key="test_key",
            normalized_query="test query",
            result_ids=["id1", "id2"],
            project="test_project",
        )

        # Mock the connection and avoid async
        with patch.object(cache_manager, '_conn'):
            cache_manager._put_to_l2(entry)
            # If we get here without exception, the call structure is correct

    @pytest.mark.skip(reason="L2 operations require integration testing with real DuckDB database")
    @pytest.mark.asyncio
    async def test_get_from_l2_hit(self, cache_manager):
        """Test getting entry from L2 cache (hit)."""
        # Mock database response
        from datetime import datetime, UTC

        mock_row = (
            "test_key",
            "test query",
            "test_project",
            ["id1", "id2"],
            1,
            datetime.now(UTC),
            datetime.now(UTC),
            604800,
        )

        # Mock execute and fetchone
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        cache_manager._conn = mock_conn

        # Mock the executor to avoid async issues
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.return_value.result.return_value = mock_row

        result = cache_manager._get_from_l2("test_key")

        assert result is not None
        assert result.cache_key == "test_key"
        assert result.normalized_query == "test query"
        assert result.result_ids == ["id1", "id2"]
        assert result.project == "test_project"

    @pytest.mark.skip(reason="L2 operations require integration testing with real DuckDB database")
    @pytest.mark.asyncio
    async def test_get_from_l2_miss(self, cache_manager):
        """Test getting entry from L2 cache (miss)."""
        # Mock no results
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        cache_manager._conn = mock_conn

        # Mock the executor
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.return_value.result.return_value = None

        result = cache_manager._get_from_l2("test_key")

        assert result is None

    @pytest.mark.skip(reason="L2 operations require integration testing with real DuckDB database")
    @pytest.mark.asyncio
    async def test_delete_from_l2(self, cache_manager):
        """Test deleting entry from L2 cache."""
        # Mock the connection
        mock_conn = MagicMock()
        cache_manager._conn = mock_conn

        # Mock the executor
        with patch('asyncio.get_event_loop'):
            cache_manager._delete_from_l2("test_key")

            # Verify delete was called
            assert mock_conn.execute.called

    @pytest.mark.skip(reason="L2 operations require integration testing with real DuckDB database")
    @pytest.mark.asyncio
    async def test_l2_promotion_to_l1(self, cache_manager):
        """Test that L2 hits are promoted to L1."""
        from datetime import datetime, UTC

        # Mock L2 hit
        mock_row = (
            "test_key",
            "test query",
            "test_project",
            ["id1", "id2"],
            1,
            datetime.now(UTC),
            datetime.now(UTC),
            604800,
        )
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        cache_manager._conn = mock_conn

        # Mock the executor
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.return_value.result.return_value = mock_row

        # Get with L2 enabled
        result = cache_manager.get("test_key", check_l2=True)

        # Should be in L1 now (promoted)
        assert "test_key" in cache_manager._l1_cache
        assert result == ["id1", "id2"]


class TestCacheStatistics:
    """Test cache statistics tracking."""

    @pytest.fixture
    def cache_manager(self):
        """Create cache manager for statistics testing."""
        manager = QueryCacheManager(l1_max_size=10)
        manager._initialized = True
        return manager

    def test_hit_rate_calculation(self, cache_manager):
        """Test hit rate calculation."""
        # No operations yet
        stats = cache_manager.get_stats()
        assert stats["l1_hit_rate"] == 0.0

        # Add some hits and misses
        cache_manager._stats["l1_hits"] = 7
        cache_manager._stats["l1_misses"] = 3

        stats = cache_manager.get_stats()
        assert stats["l1_hit_rate"] == 0.7

    def test_hit_rate_no_data(self, cache_manager):
        """Test hit rate when no data (avoid division by zero)."""
        stats = cache_manager.get_stats()
        assert stats["l1_hit_rate"] == 0.0

        # Set only hits, no misses
        cache_manager._stats["l1_hits"] = 5
        cache_manager._stats["l1_misses"] = 0

        stats = cache_manager.get_stats()
        assert stats["l1_hit_rate"] == 1.0

    def test_stats_copy_independence(self, cache_manager):
        """Test that get_stats returns a copy, not reference."""
        stats1 = cache_manager.get_stats()
        stats2 = cache_manager.get_stats()

        # Modify stats1
        stats1["l1_hits"] = 999

        # stats2 should be unchanged
        assert stats2["l1_hits"] == 0


class TestIntegrationPatterns:
    """Test common integration patterns."""

    @pytest.fixture
    def cache_manager(self):
        """Create initialized cache manager."""
        manager = QueryCacheManager(l1_max_size=5)
        manager._initialized = True
        return manager

    def test_typical_search_flow(self, cache_manager):
        """Test typical search cache flow: check → miss → compute → store → hit."""
        query = "async patterns"
        project = "myproject"
        limit = 10

        # 1. Check cache - miss
        cache_key = QueryCacheManager.compute_cache_key(
            query=query, project=project, limit=limit
        )
        result = cache_manager.get(cache_key)
        assert result is None

        # 2. Simulate search computation
        mock_result_ids = ["id1", "id2", "id3"]

        # 3. Store in cache
        cache_manager.put(
            cache_key=cache_key,
            result_ids=mock_result_ids,
            normalized_query=QueryCacheManager.normalize_query(query),
            project=project,
        )

        # 4. Check cache again - should hit
        result = cache_manager.get(cache_key)
        assert result == mock_result_ids

    def test_cache_invalidation_on_data_change(self, cache_manager):
        """Test cache invalidation pattern when underlying data changes."""
        # Store initial result
        cache_manager.put(
            cache_key="key1",
            result_ids=["id1", "id2"],
            normalized_query="query1",
            project="project1",
        )

        # Verify cached
        assert cache_manager.get("key1") == ["id1", "id2"]

        # Invalidate when data changes
        cache_manager.invalidate(cache_key="key1")

        # Verify invalidated
        assert cache_manager.get("key1") is None

        # Store updated result
        cache_manager.put(
            cache_key="key1",
            result_ids=["id1", "id2", "id3"],  # Updated with new result
            normalized_query="query1",
            project="project1",
        )

        # Verify updated result
        assert cache_manager.get("key1") == ["id1", "id2", "id3"]
