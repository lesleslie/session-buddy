"""Async-native, ACB-backed cache adapters for session-mgmt-mcp.

This module provides fully asynchronous cache adapters using aiocache,
leveraging ACB's underlying cache for optimized serialization and
lifecycle management.
"""

import hashlib
import typing as t
from contextlib import suppress
from dataclasses import dataclass

if t.TYPE_CHECKING:
    from session_buddy.adapters.settings import CacheAdapterSettings

try:
    from aiocache import SimpleMemoryCache
    from aiocache.serializers import PickleSerializer

    AIOCACHE_AVAILABLE = True
except ImportError:
    AIOCACHE_AVAILABLE = False
    # Type stubs for when aiocache is not installed
    SimpleMemoryCache: t.Any = object  # type: ignore[no-redef]
    PickleSerializer: t.Any = object  # type: ignore[no-redef]


@dataclass
class CacheStats:
    """Cache statistics for monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_entries: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    def to_dict(self) -> dict[str, t.Any]:
        """Convert stats to dictionary for reporting."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_entries": self.total_entries,
            "hit_rate_percent": round(self.hit_rate, 2),
        }


class ACBChunkCache:
    """Async-native, ACB-backed chunk cache for the token optimizer."""

    def __init__(self, ttl: int = 3600) -> None:
        """Initialize chunk cache.

        Args:
            ttl: Default time-to-live in seconds (default: 1 hour)

        """
        if AIOCACHE_AVAILABLE:
            self._cache = SimpleMemoryCache(
                serializer=PickleSerializer(),
                namespace="session_mgmt:chunks:",
            )
            self._cache.timeout = 0.0  # No operation timeout
        else:
            # Fallback when aiocache is not available
            self._cache = None
        self._ttl = ttl
        self.stats = CacheStats()

    async def set(self, key: str, value: t.Any, ttl: int | None = None) -> None:
        """Store chunk data in cache asynchronously.

        Args:
            key: Cache key
            value: Value to cache (ChunkResult)
            ttl: Optional TTL override in seconds

        """
        if self._cache is None:
            # Fallback when aiocache is not available
            return
        effective_ttl = ttl or self._ttl
        await self._cache.set(key, value, ttl=effective_ttl)
        self.stats.total_entries += 1

    async def get(self, key: str) -> t.Any | None:
        """Retrieve chunk data from cache asynchronously.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired

        """
        if self._cache is None:
            # Fallback when aiocache is not available
            self.stats.misses += 1
            return None
        result = await self._cache.get(key)
        if result is None:
            self.stats.misses += 1
        else:
            self.stats.hits += 1
        return result

    async def delete(self, key: str) -> None:
        """Delete chunk data from cache asynchronously.

        Args:
            key: Cache key to delete

        """
        if self._cache is not None:
            await self._cache.delete(key)
        self.stats.evictions += 1

    async def clear(self) -> None:
        """Clear all cached chunk data asynchronously."""
        if self._cache is not None:
            await self._cache.clear()
        self.stats = CacheStats()

    async def __contains__(self, key: str) -> bool:
        """Check if key exists in cache asynchronously.

        Args:
            key: Cache key to check

        Returns:
            True if key exists and is not expired

        """
        if self._cache is None:
            return False
        result = await self._cache.exists(key)
        return bool(result)

    async def __getitem__(self, key: str) -> t.Any:
        """Get item using dict syntax asynchronously.

        Args:
            key: Cache key

        Returns:
            Cached value

        Raises:
            KeyError: If key not found in cache

        """
        result = await self.get(key)
        if result is None:
            raise KeyError(key)
        return result

    async def __setitem__(self, key: str, value: t.Any) -> None:
        """Set item using dict syntax asynchronously.

        Args:
            key: Cache key
            value: Value to cache

        """
        await self.set(key, value)

    async def __delitem__(self, key: str) -> None:
        """Delete item using dict syntax asynchronously.

        Args:
            key: Cache key to delete

        """
        await self.delete(key)

    async def keys(self) -> list[str]:
        """Get all cache keys (not efficiently supported by SimpleMemoryCache)."""
        return []

    def get_stats(self) -> dict[str, t.Any]:
        """Get cache statistics."""
        return {"chunk_cache": self.stats.to_dict()}


class ACBHistoryCache:
    """Async-native, ACB-backed history cache for analysis results."""

    def __init__(self, ttl: float = 300.0) -> None:
        """Initialize history cache.

        Args:
            ttl: Time-to-live in seconds (default: 5 minutes)

        """
        if AIOCACHE_AVAILABLE:
            self._cache = SimpleMemoryCache(
                serializer=PickleSerializer(),
                namespace="session_mgmt:history:",
            )
            self._cache.timeout = 0.0
        else:
            # Fallback when aiocache is not available
            self._cache = None
        self._ttl = int(ttl)
        self.stats = CacheStats()

    def _generate_key(self, project: str, days: int) -> str:
        """Generate cache key from parameters."""
        params = f"{project}:{days}"
        return hashlib.md5(params.encode(), usedforsecurity=False).hexdigest()

    async def get(self, project: str, days: int) -> dict[str, t.Any] | None:
        """Retrieve cached analysis result asynchronously.

        Args:
            project: Project name
            days: Number of days analyzed

        Returns:
            Cached analysis dict or None if not found/expired

        """
        if self._cache is None:
            # Fallback when aiocache is not available
            self.stats.misses += 1
            return None
        key = self._generate_key(project, days)
        result: dict[str, t.Any] | None = await self._cache.get(key)
        if result is None:
            self.stats.misses += 1
        else:
            self.stats.hits += 1
        return result

    async def set(self, project: str, days: int, data: dict[str, t.Any]) -> None:
        """Store analysis result in cache asynchronously.

        Args:
            project: Project name
            days: Number of days analyzed
            data: Analysis result dictionary

        """
        if self._cache is not None:
            key = self._generate_key(project, days)
            await self._cache.set(key, data, ttl=self._ttl)
        self.stats.total_entries += 1

    async def invalidate(self, project: str | None = None) -> None:
        """Invalidate cache entries asynchronously.

        Args:
            project: Optional project name (if None, clears entire cache)

        """
        if project is None:
            if self._cache is not None:
                await self._cache.clear()
            self.stats = CacheStats()
        else:
            import warnings

            warnings.warn(
                "ACB cache doesn't support selective invalidation by project. "
                "Use invalidate(None) to clear all cached data.",
                stacklevel=2,
            )

    async def size(self) -> int:
        """Get number of cached entries (approximate)."""
        return self.stats.total_entries

    def get_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {
            "total_entries": self.stats.total_entries,
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "expired_entries": 0,
            "active_entries": self.stats.total_entries,
        }


# Global cache instances
_chunk_cache: ACBChunkCache | None = None
_history_cache: ACBHistoryCache | None = None


def _resolve_cache_settings() -> "CacheAdapterSettings":
    from session_buddy.adapters.settings import CacheAdapterSettings
    from session_buddy.di.container import depends

    with suppress(Exception):
        settings = depends.get_sync(CacheAdapterSettings)
        if isinstance(settings, CacheAdapterSettings):
            return settings
    return CacheAdapterSettings()


def get_chunk_cache(ttl: int | None = None) -> ACBChunkCache:
    """Get or create global async chunk cache instance."""
    global _chunk_cache
    settings = _resolve_cache_settings()
    effective_ttl = ttl if ttl is not None else settings.chunk_cache_ttl_seconds
    if _chunk_cache is None:
        _chunk_cache = ACBChunkCache(ttl=effective_ttl)
    return _chunk_cache


def get_history_cache(ttl: float | None = None) -> ACBHistoryCache:
    """Get or create global async history cache instance."""
    global _history_cache
    settings = _resolve_cache_settings()
    effective_ttl = ttl if ttl is not None else settings.history_cache_ttl_seconds
    if _history_cache is None:
        _history_cache = ACBHistoryCache(ttl=effective_ttl)
    return _history_cache


async def reset_caches() -> None:
    """Reset global cache instances asynchronously."""
    global _chunk_cache, _history_cache
    if _chunk_cache:
        await _chunk_cache.clear()
    if _history_cache:
        await _history_cache.invalidate()
    _chunk_cache = None
    _history_cache = None
