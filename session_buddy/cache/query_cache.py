"""Query cache utilities for Session Buddy.

The substrate (``oneiric.adapters.cache.memory.MemoryCacheAdapter``)
provides the cache primitive directly. This module re-exports it,
ships two module-level helpers (``normalize_query``,
``compute_cache_key``) that callers use to derive cache keys, and
provides a thin ``TrackedCacheAdapter`` wrapper that adds hit-rate
metrics and a no-op ``cleanup_expired`` for API compatibility with
the legacy ``QueryCacheManager`` (which was deleted in the
substrate-adoption cleanup wave — pre-1.0, callers should adopt the
shim rather than re-introducing the L1/L2 two-tier semantics).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from oneiric.adapters.cache.memory import (
    MemoryCacheAdapter,
    MemoryCacheSettings,
)

__all__ = [
    "MemoryCacheAdapter",
    "MemoryCacheSettings",
    "TrackedCacheAdapter",
    "compute_cache_key",
    "normalize_query",
]


def normalize_query(query: str) -> str:
    """Normalize query string for consistent cache keys.

    Normalization steps:
        1. Convert to lowercase
        2. Collapse multiple whitespace to single space
        3. Strip leading/trailing whitespace
        4. Remove trailing punctuation (but keep internal operators)

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
    normalized = query.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[?!.;,]+$", "", normalized)
    return normalized


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
    """
    normalized = normalize_query(query)

    components: dict[str, Any] = {
        "query": normalized,
        "project": project or "",
        "limit": limit,
    }

    if kwargs:
        sorted_kwargs = json.dumps(kwargs, sort_keys=True)
        components["kwargs"] = sorted_kwargs

    key_string = json.dumps(components, sort_keys=True)
    return hashlib.sha256(key_string.encode()).hexdigest()


class TrackedCacheAdapter:
    """Thin metrics wrapper around ``MemoryCacheAdapter``.

    The substrate's ``MemoryCacheAdapter`` is the actual cache primitive
    (an in-process dict with TTL-on-write). This shim adds the
    observability surface that operators depended on from the legacy
    ``QueryCacheManager``:

      * hit / miss counters, exposed via :meth:`get_stats` as ``hits``,
        ``misses``, and ``hit_rate`` (a float in [0.0, 1.0]);
      * a no-op :meth:`cleanup_expired` for API compatibility with the
        prior L1/L2 wrapper (the substrate's TTL-on-write model has
        nothing to lazy-clean — returns 0 for the prior ``entries
        cleaned`` semantic);
      * a :meth:`invalidate` alias for ``clear`` preserved from the
        pre-substrate ``QueryCacheManager.invalidate`` method, so the
        shutdown path in ``reflection_adapter_oneiric.py`` keeps
        working unchanged.

    Everything else is delegation. The shim is a metrics surface, not
    a re-implementation of caching. Per
    ``feedback-no-backwards-compat-pre-1.0.md`` pre-1.0 we add the
    shim (observability is a real operator need) rather than telling
    callers to read substrate state directly.
    """

    def __init__(self, settings: MemoryCacheSettings) -> None:
        self._adapter = MemoryCacheAdapter(settings)
        self._settings = settings
        self._hits = 0
        self._misses = 0

    @property
    def _store(self) -> dict:
        """Live in-process entry dict (exposed for ``query_cache_stats``)."""
        return self._adapter._store

    async def get(self, key: str) -> Any | None:
        result = await self._adapter.get(key)
        if result is None:
            self._misses += 1
        else:
            self._hits += 1
        return result

    async def set(self, key: str, value: Any) -> None:
        await self._adapter.set(key, value)

    async def delete(self, key: str) -> None:
        await self._adapter.delete(key)

    async def clear(self) -> None:
        await self._adapter.clear()

    async def invalidate(self) -> None:
        """Alias for :meth:`clear` — preserved from the pre-substrate API."""
        await self._adapter.clear()

    def get_stats(self) -> dict[str, Any]:
        """Return the substrate-shaped stats dict with hit-rate fields added.

        Mirrors the substrate's own surface (``max_entries``,
        ``default_ttl_seconds``, ``current_entries``, ``backend``) and
        adds the legacy hit-rate fields (``hits``, ``misses``,
        ``hit_rate``) that ``QueryCacheManager`` previously surfaced.
        """
        total = self._hits + self._misses
        return {
            "max_entries": self._settings.max_entries,
            "default_ttl_seconds": self._settings.default_ttl,
            "current_entries": len(self._adapter._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
            "backend": "oneiric.MemoryCacheAdapter",
        }

    def cleanup_expired(self) -> int:
        """No-op for the substrate's TTL-on-write model.

        Returns 0 (entries cleaned) for API compatibility with the
        prior L1/L2 ``QueryCacheManager.cleanup_expired``. The
        ``optimize_cache`` MCP tool uses this as a "is the cache
        healthy" probe — it surfaces the current stats without
        trying to recreate L1/L2 lazy-eviction semantics.
        """
        return 0
