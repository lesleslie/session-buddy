"""Caching layer for history analysis to improve performance.

This module uses native Python caching with TTL support for improved
performance and lifecycle management while maintaining backwards-compatible API.
"""

from datetime import datetime
from typing import Any, TypeVar

T = TypeVar("T")


def _ttl_hash() -> str:
    """Generate hash based on current time (for TTL tracking)."""
    return datetime.now().isoformat()


class HistoryAnalysisCache:
    """Native cache for history analysis (replaces deprecated ACB)."""

    def __init__(self, ttl: float = 300.0):
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._ttl = ttl
        self._created_at = datetime.now()

    def get(self, key: str, default: T | None = None) -> Any | None:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return default

        value, timestamp = self._cache[key]
        age = (datetime.now() - timestamp).total_seconds()

        if age > self._ttl:
            del self._cache[key]
            return default

        return value

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp."""
        self._cache[key] = (value, datetime.now())

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

    def is_expired(self, key: str) -> bool:
        """Check if cached item is expired."""
        if key not in self._cache:
            return True

        value, timestamp = self._cache[key]
        age = (datetime.now() - timestamp).total_seconds()
        return age > self._ttl


# Global cache instance
_global_cache: HistoryAnalysisCache | None = None


def get_cache(ttl: float = 300.0) -> HistoryAnalysisCache:
    """Get or create global cache instance.

    Args:
        ttl: Time-to-live in seconds (default: 5 minutes)

    Returns:
        Global cache instance with native implementation

    """
    global _global_cache
    if _global_cache is None:
        _global_cache = HistoryAnalysisCache(ttl=ttl)
    return _global_cache


async def reset_cache() -> None:
    """Reset global cache instance.

    Useful for testing or clearing all cached data.
    """
    global _global_cache
    if _global_cache:
        _global_cache.clear()
    _global_cache = None


# Backwards-compatible alias
ACBHistoryCache = HistoryAnalysisCache
