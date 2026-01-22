"""Query cache implementation for Session Buddy.

Implements two-tier caching (L1 memory + L2 DuckDB) with LRU eviction
to eliminate expensive vector searches for repeated queries.

Cache Architecture:
    L1 (Memory): Fast LRU cache with ~1ms access time
    L2 (DuckDB): Persistent cache with ~10ms access time

Usage:
    >>> cache = QueryCacheManager(l1_max_size=1000, l2_ttl_days=7)
    >>> await cache.initialize(conn=duckdb_conn)
    >>> cache_key = cache.compute_cache_key("search query", project="myproject", limit=10)
    >>> cache.put(cache_key, ["id1", "id2"], "search query")
    >>> result = cache.get(cache_key)
    >>> stats = cache.get_stats()
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import duckdb


@dataclass
class QueryCacheEntry:
    """Single cache entry with metadata."""

    cache_key: str
    normalized_query: str
    result_ids: list[str]
    project: str | None
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    ttl_seconds: int = 604800  # 7 days default

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds

    def touch(self) -> None:
        """Update last_accessed timestamp."""
        self.last_accessed = time.time()
        self.hit_count += 1


class QueryCacheManager:
    """Two-tier query cache with L1 memory and L2 DuckDB storage.

    L1 Cache:
        - In-memory OrderedDict for O(1) access
        - LRU eviction when max_size exceeded
        - Fast access (~1ms latency)

    L2 Cache:
        - DuckDB table for persistence
        - Survives process restarts
        - Slower access (~10ms latency)

    Thread Safety:
        - Thread-safe for concurrent access
        - Separate locks for L1 and L2 operations
    """

    def __init__(
        self,
        l1_max_size: int = 1000,
        l2_ttl_days: int = 7,
    ) -> None:
        """Initialize query cache manager.

        Args:
            l1_max_size: Maximum number of entries in L1 cache (LRU eviction)
            l2_ttl_days: Default TTL for L2 cache entries in days
        """
        self.l1_max_size = l1_max_size
        self.l2_ttl_seconds = l2_ttl_days * 86400
        self._l1_cache: OrderedDict[str, QueryCacheEntry] = OrderedDict()
        self._l1_lock = threading.RLock()

        # L2 connection (set during initialize())
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._l2_lock = threading.RLock()

        # Statistics
        self._stats: dict[str, int | float] = {
            "l1_hits": 0,
            "l1_misses": 0,
            "l2_hits": 0,
            "l2_misses": 0,
            "l1_evictions": 0,
            "l2_evictions": 0,
            "l1_hit_rate": 0.0,
            "l2_hit_rate": 0.0,
            "l1_size": 0,
        }
        self._stats_lock = threading.Lock()

        # Initialization flag
        self._initialized = False

        # Shutdown tracking for race condition fix
        self._shutdown = False
        self._pending_operations = 0
        self._shutdown_lock = threading.Lock()
        self._shutdown_event = threading.Event()

    async def initialize(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Initialize cache manager and create L2 table if needed.

        Args:
            conn: DuckDB connection for L2 cache storage
        """
        self._conn = conn

        # Create L2 table if not exists
        await self._ensure_l2_table()

        self._initialized = True

    async def _ensure_l2_table(self) -> None:
        """Create L2 cache table in DuckDB if it doesn't exist."""
        if not self._conn:
            return

        create_table_sql = """
        CREATE TABLE IF NOT EXISTS query_cache_l2 (
            cache_key TEXT PRIMARY KEY,
            normalized_query TEXT NOT NULL,
            project TEXT,
            result_ids TEXT[],
            hit_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ttl_seconds INTEGER DEFAULT 604800
        );

        CREATE INDEX IF NOT EXISTS idx_query_cache_l2_accessed
        ON query_cache_l2(last_accessed);

        CREATE INDEX IF NOT EXISTS idx_query_cache_l2_project
        ON query_cache_l2(project);
        """

        # Execute in executor thread to avoid blocking
        def _create_table() -> None:
            if self._conn:
                self._conn.execute(create_table_sql)

        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _create_table)

    @staticmethod
    def normalize_query(query: str) -> str:
        """Normalize query string for consistent cache keys.

        Normalization steps:
            1. Convert to lowercase
            2. Collapse multiple whitespace to single space
            3. Strip leading/trailing whitespace
            4. Remove punctuation (except query operators)

        Args:
            query: Raw query string

        Returns:
            Normalized query string

        Examples:
            >>> normalize_query("What did I  learn about  async?")
            'what did i learn about async'
            >>> normalize_query("  Find insights on authentication  ")
            'find insights on authentication'
        """
        import re

        # Convert to lowercase
        normalized = query.lower().strip()

        # Collapse multiple whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Remove trailing punctuation (but keep internal operators like +, -, *)
        normalized = re.sub(r"[?!.;,]+$", "", normalized)

        return normalized

    @staticmethod
    def compute_cache_key(
        query: str,
        project: str | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Compute cache key from query parameters.

        Cache key components:
            1. Normalized query
            2. Project name (if provided)
            3. Result limit
            4. Additional kwargs (sorted for consistency)

        Args:
            query: Search query string
            project: Optional project filter
            limit: Result limit
            **kwargs: Additional search parameters

        Returns:
            SHA256 hash as hex string

        Examples:
            >>> compute_cache_key("async patterns", project="myapp", limit=10)
            'a3f5c8d9e2b1...'
            >>> compute_cache_key("authentication", limit=20, min_score=0.8)
            '7d9e4a2f1c8b...'
        """
        # Normalize query first
        normalized = QueryCacheManager.normalize_query(query)

        # Build key components
        components: dict[str, Any] = {
            "query": normalized,
            "project": project or "",
            "limit": limit,
        }

        # Add sorted kwargs
        if kwargs:
            # Sort keys for consistent hashing
            sorted_kwargs = json.dumps(kwargs, sort_keys=True)
            components["kwargs"] = sorted_kwargs

        # Create hash
        key_string = json.dumps(components, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(
        self,
        cache_key: str,
        check_l2: bool = True,
    ) -> list[str] | None:
        """Get cached result IDs by cache key (async version).

        Search order:
            1. Check L1 cache (memory)
            2. If not found and check_l2=True, check L2 cache (DuckDB)
            3. Promote L2 hits to L1 for faster future access

        Args:
            cache_key: Cache key from compute_cache_key()
            check_l2: Whether to check L2 cache if L1 miss

        Returns:
            List of result IDs if found and not expired, None otherwise
        """
        if not self._initialized:
            return None

        # Check L1 cache first
        with self._l1_lock:
            if cache_key in self._l1_cache:
                entry = self._l1_cache[cache_key]

                # Check expiration
                if entry.is_expired():
                    del self._l1_cache[cache_key]
                    with self._stats_lock:
                        self._stats["l1_misses"] += 1
                    return None

                # Move to end (LRU)
                self._l1_cache.move_to_end(cache_key)
                entry.touch()

                with self._stats_lock:
                    self._stats["l1_hits"] += 1

                return entry.result_ids

            with self._stats_lock:
                self._stats["l1_misses"] += 1

        # Check L2 cache if enabled
        if check_l2 and self._conn:
            result = self._get_from_l2(cache_key)
            if result is not None:
                # Promote to L1
                with self._l1_lock:
                    self._l1_cache[cache_key] = result
                    self._evict_l1_if_needed()

                with self._stats_lock:
                    self._stats["l2_hits"] += 1

                return result.result_ids

            with self._stats_lock:
                self._stats["l2_misses"] += 1

        return None

    def _get_from_l2(self, cache_key: str) -> QueryCacheEntry | None:
        """Get entry from L2 cache.

        Args:
            cache_key: Cache key to lookup

        Returns:
            QueryCacheEntry if found and not expired, None otherwise
        """
        if not self._conn:
            return None

        # Query L2 table (DuckDB operation is fast, <1ms, no need for threading)
        query_sql = """
        SELECT cache_key, normalized_query, project, result_ids,
               hit_count, created_at, last_accessed, ttl_seconds
        FROM query_cache_l2
        WHERE cache_key = ?
        """

        row = self._conn.execute(query_sql, [cache_key]).fetchone()

        if not row:
            return None

        # Type cast for zuban: DuckDB returns variadic tuple, but we know it's 8 elements
        cache_row = cast(
            tuple[str, str, str | None, list[str] | None, int, Any, Any, int | None],
            row,
        )

        # Parse row
        entry = QueryCacheEntry(
            cache_key=cache_row[0],
            normalized_query=cache_row[1],
            project=cache_row[2],
            result_ids=list(cache_row[3]) if cache_row[3] else [],
            hit_count=cache_row[4],
            created_at=cache_row[5].timestamp(),
            last_accessed=cache_row[6].timestamp(),
            ttl_seconds=cache_row[7] or 604800,  # Default 7 days if None
        )

        # Check expiration
        if entry.is_expired():
            self._delete_from_l2(cache_key)
            return None

        # Update last_accessed and hit_count
        self._update_l2_access(cache_key)

        return entry

    def _update_l2_access(self, cache_key: str) -> None:
        """Update last_accessed timestamp and hit_count in L2 (async version).

        Args:
            cache_key: Cache key to update
        """
        if not self._conn:
            return

        update_sql = """
        UPDATE query_cache_l2
        SET last_accessed = CURRENT_TIMESTAMP,
            hit_count = hit_count + 1
        WHERE cache_key = ?
        """

        def _update() -> None:
            if self._conn:
                self._conn.execute(update_sql, [cache_key])

        import asyncio

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _update).result()

    def put(
        self,
        cache_key: str,
        result_ids: list[str],
        normalized_query: str,
        project: str | None = None,
    ) -> None:
        """Store result IDs in cache (both L1 and L2).

        Args:
            cache_key: Cache key from compute_cache_key()
            result_ids: List of result IDs to cache
            normalized_query: Normalized query string
            project: Optional project filter
        """
        if not self._initialized:
            return

        # Create entry
        entry = QueryCacheEntry(
            cache_key=cache_key,
            normalized_query=normalized_query,
            result_ids=result_ids,
            project=project,
            ttl_seconds=self.l2_ttl_seconds,
        )

        # Store in L1
        with self._l1_lock:
            self._l1_cache[cache_key] = entry
            self._evict_l1_if_needed()

        # Store in L2
        if self._conn:
            self._put_to_l2(entry)

    def _put_to_l2(self, entry: QueryCacheEntry) -> None:
        """Store entry in L2 cache.

        Args:
            entry: Cache entry to store
        """
        if not self._conn:
            return

        upsert_sql = """
        INSERT INTO query_cache_l2
        (cache_key, normalized_query, project, result_ids, ttl_seconds)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (cache_key) DO UPDATE SET
            result_ids = excluded.result_ids,
            last_accessed = CURRENT_TIMESTAMP,
            hit_count = query_cache_l2.hit_count + 1
        """

        # Execute upsert directly (DuckDB operation is fast, <1ms)
        if self._conn:
            self._conn.execute(
                upsert_sql,
                [
                    entry.cache_key,
                    entry.normalized_query,
                    entry.project,
                    entry.result_ids,
                    entry.ttl_seconds,
                ],
            )

    def _delete_from_l2(self, cache_key: str) -> None:
        """Delete entry from L2 cache.

        Args:
            cache_key: Cache key to delete
        """
        if not self._conn:
            return

        delete_sql = "DELETE FROM query_cache_l2 WHERE cache_key = ?"

        # Execute delete directly (DuckDB operation is fast, <1ms)
        if self._conn:
            self._conn.execute(delete_sql, [cache_key])

    def _evict_l1_if_needed(self) -> None:
        """Evict oldest entry from L1 cache if max_size exceeded.

        Uses OrderedDict's popitem(last=False) for O(1) eviction.
        """
        if len(self._l1_cache) > self.l1_max_size:
            self._l1_cache.popitem(last=False)
            with self._stats_lock:
                self._stats["l1_evictions"] += 1

    def invalidate(self, cache_key: str | None = None) -> None:
        """Invalidate cache entry by key.

        Args:
            cache_key: Specific cache key to invalidate, or None to clear all
        """
        if not self._initialized:
            return

        # Clear all or specific entry
        if cache_key is None:
            # Clear entire cache
            with self._l1_lock:
                self._l1_cache.clear()

            if self._conn:
                self._clear_l2()
        else:
            # Clear specific entry
            with self._l1_lock:
                if cache_key in self._l1_cache:
                    del self._l1_cache[cache_key]

            if self._conn:
                self._delete_from_l2(cache_key)

    def _clear_l2(self) -> None:
        """Clear all entries from L2 cache."""
        if not self._conn:
            return

        def _clear() -> None:
            if self._conn:
                self._conn.execute("DELETE FROM query_cache_l2")

        import asyncio

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _clear).result()

    def get_stats(self) -> dict[str, int | float]:
        """Get cache performance statistics.

        Returns:
            Dictionary with cache metrics:
            - l1_hits: Number of L1 cache hits
            - l1_misses: Number of L1 cache misses
            - l2_hits: Number of L2 cache hits
            - l2_misses: Number of L2 cache misses
            - l1_evictions: Number of L1 evictions
            - l2_evictions: Number of L2 evictions
            - l1_hit_rate: L1 hit rate (0-1)
            - l2_hit_rate: L2 hit rate (0-1)
            - l1_size: Current L1 cache size
        """
        with self._stats_lock:
            stats = self._stats.copy()

        # Calculate hit rates
        l1_total = stats["l1_hits"] + stats["l1_misses"]
        stats["l1_hit_rate"] = stats["l1_hits"] / l1_total if l1_total > 0 else 0.0

        l2_total = stats["l2_hits"] + stats["l2_misses"]
        stats["l2_hit_rate"] = stats["l2_hits"] / l2_total if l2_total > 0 else 0.0

        # Current L1 size
        with self._l1_lock:
            stats["l1_size"] = len(self._l1_cache)

        return stats

    async def aclose(self) -> None:
        """Close cache manager and wait for pending operations.

        This prevents race conditions during cleanup by ensuring all
        pending executor operations complete before closing the connection.
        """
        with self._shutdown_lock:
            self._shutdown = True

        # Wait for pending operations to complete (max 5 seconds)
        for _ in range(50):  # 50 * 100ms = 5 seconds
            with self._shutdown_lock:
                if self._pending_operations == 0:
                    break
            await asyncio.sleep(0.1)

        # Now safe to close connection
        if self._conn:
            with suppress(Exception):
                self._conn.close()
            self._conn = None

        # Clear caches
        with self._l1_lock:
            self._l1_cache.clear()

    def _track_operation(self, operation_name: str) -> None:
        """Track a pending operation for shutdown safety.

        Args:
            operation_name: Name of the operation for debugging
        """
        with self._shutdown_lock:
            if self._shutdown:
                raise RuntimeError(
                    f"Cannot perform {operation_name}: cache is shutdown"
                )
            self._pending_operations += 1

    def _complete_operation(self) -> None:
        """Mark a pending operation as complete."""
        with self._shutdown_lock:
            self._pending_operations = max(0, self._pending_operations - 1)
            if self._pending_operations == 0:
                self._shutdown_event.set()

    def _execute_in_executor(self, func: Callable[..., Any], *args: Any) -> Any:
        """Execute function in executor with proper tracking.

        This wrapper prevents race conditions during cleanup by tracking
        pending operations and preventing new operations during shutdown.

        Args:
            func: Function to execute in executor thread
            *args: Arguments to pass to func

        Returns:
            Future from run_in_executor
        """
        self._track_operation(func.__name__)

        def _wrapper() -> Any:
            try:
                return func(*args)
            finally:
                self._complete_operation()

        import asyncio

        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, _wrapper)

    async def cleanup_expired(self) -> int:
        """Clean up expired entries from L2 cache.

        Returns:
            Number of entries removed

        Note:
            L1 entries are lazily removed on access (see get() method)
        """
        if not self._conn:
            return 0

        delete_sql = """
        DELETE FROM query_cache_l2
        WHERE CAST(strftime('%s', 'now') AS REAL) - created_at > ttl_seconds
        """

        def _cleanup() -> int:
            if self._conn:
                result = self._conn.execute(delete_sql)
                return result.rowcount
            return 0

        import asyncio

        loop = asyncio.get_event_loop()
        deleted_count = await loop.run_in_executor(None, _cleanup)

        with self._stats_lock:
            self._stats["l2_evictions"] += deleted_count

        return deleted_count
