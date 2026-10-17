"""Cache management MCP tools for Session Buddy query cache.

Substrate-adoption cleanup: the legacy two-tier cache wrapper
(``QueryCacheManager``) was deleted; the substrate's
``MemoryCacheAdapter`` is used inside the ``TrackedCacheAdapter``
shim, which adds the hit-rate metrics surface operators depended
on from the prior wrapper. The L1/L2 distinction is gone, so the
tools no longer expose ``cache_level``-based clearing — those
features depended on a two-tier cache that no longer exists. The
``optimize_cache`` tool is preserved as a no-op-cleanup-plus-stats
report (the substrate's TTL-on-write model has nothing to lazy-evict).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp_common.fastmcp import Context

from session_buddy.cache.query_cache import (
    MemoryCacheAdapter,
    compute_cache_key,
)
from session_buddy.di import depends

logger = logging.getLogger(__name__)


def _resolve_db() -> Any:
    """Return the registered reflection database adapter, or None if missing.

    Tries the Oneiric-backed adapter first, then the legacy adapter. Returns
    whichever instance is currently registered in the DI container without
    attempting to initialise one, so callers can surface a clear "not
    initialised" error.
    """
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric as ReflectionDatabaseAdapter,
        )
    except ImportError:
        try:
            from session_buddy.adapters.reflection_adapter import (
                ReflectionDatabaseAdapter,
            )
        except ImportError:
            return None

    try:
        return depends.get_sync(ReflectionDatabaseAdapter)
    except Exception:  # noqa: BLE001 - sentinel: missing adapter means no caching, not a crash
        return None


def register_cache_tools(mcp: Any) -> None:
    """Register all cache management tools with the MCP server.

    Args:
        mcp: FastMCP instance to register tools with
    """
    mcp.tool()(query_cache_stats)
    mcp.tool()(clear_query_cache)
    mcp.tool()(warm_cache)
    mcp.tool()(invalidate_cache)
    mcp.tool()(optimize_cache)


async def query_cache_stats(
    ctx: Context,
) -> str:
    """View query cache configuration, current size, and hit-rate metrics.

    Returns the substrate adapter's configured limits (max entries,
    default TTL), the live entry count from the in-process store, and
    the hit-rate metrics (``hits``, ``misses``, ``hit_rate``) tracked by
    the ``TrackedCacheAdapter`` shim. The hit-rate surface replaces the
    L1/L2 reporting that ``QueryCacheManager`` used to provide.
    """
    try:
        db = _resolve_db()
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        cache = db._query_cache
        # Use the shim's get_stats() when available (substrate-shaped
        # stats + hit-rate fields); fall back to bare attribute reads
        # for tests that substitute a fake that doesn't expose the
        # shim surface.
        if hasattr(cache, "get_stats") and callable(cache.get_stats):
            stats = cache.get_stats()
        else:
            store_size = len(getattr(cache, "_store", {}) or {})
            stats = {
                "max_entries": cache._settings.max_entries,
                "default_ttl_seconds": cache._settings.default_ttl,
                "current_entries": store_size,
                "backend": "oneiric.MemoryCacheAdapter",
            }

        return json.dumps(
            {
                "success": True,
                "stats": stats,
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Failed to retrieve cache stats")
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to retrieve cache stats: {e}",
            },
            indent=2,
        )


async def clear_query_cache(
    ctx: Context,
) -> str:
    """Clear the entire query cache.

    The substrate adapter stores every entry in a single OrderedDict,
    so there is no L1/L2 distinction to honour — ``cache_level`` is
    accepted as a no-op positional argument kept for compatibility
    with older MCP clients that still pass it.

    Use this tool to:
    - Force cache refresh when data has changed significantly
    - Free memory when the cache grows large
    - Troubleshoot cache-related issues
    """
    try:
        db = _resolve_db()
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        await db._query_cache.clear()

        return json.dumps(
            {
                "success": True,
                "message": "Cache cleared successfully",
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Failed to clear cache")
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to clear cache: {e}",
            },
            indent=2,
        )


async def warm_cache(
    ctx: Context,
    queries: list[str],
) -> str:
    """Preload cache with common queries for faster access.

    Args:
        queries: List of common queries to preload

    Warms the cache by executing searches for common queries. The
    search path itself populates the cache on each hit, so this
    tool simply forces the work to happen up front.

    Example queries to warm:
    - ["async patterns", "error handling", "authentication", "database optimization"]
    """
    if not queries:
        return json.dumps(
            {
                "success": False,
                "error": "No queries provided. Provide queries to warm cache.",
            },
            indent=2,
        )

    try:
        db = _resolve_db()
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        results = []
        for query in queries:
            try:
                search_results = await db.search_reflections(
                    query, limit=10, use_cache=True
                )
                results.append(
                    {
                        "query": query,
                        "results_count": len(search_results),
                        "success": True,
                    }
                )
            except Exception as e:
                logger.exception(f"Failed to warm cache for query: {query}")
                results.append(
                    {
                        "query": query,
                        "error": str(e),
                        "success": False,
                    }
                )

        return json.dumps(
            {
                "success": True,
                "message": f"Warmed cache with {len(queries)} queries",
                "results": results,
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Failed to warm cache")
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to warm cache: {e}",
            },
            indent=2,
        )


async def invalidate_cache(
    ctx: Context,
    query: str,
    project: str | None = None,
) -> str:
    """Invalidate specific cache entry by query.

    Args:
        query: Query string to invalidate from cache
        project: Optional project filter to match

    Removes the cache entry keyed by the computed hash so the next
    search will refetch. Useful when:
    - Underlying data has changed significantly
    - Cache entry is stale or incorrect
    - Testing different query variations
    """
    try:
        db = _resolve_db()
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        cache_key = compute_cache_key(
            query=query,
            project=project,
            limit=10,  # Default limit
        )
        await db._query_cache.delete(cache_key)

        return json.dumps(
            {
                "success": True,
                "message": f"Cache entry invalidated for query: '{query}'",
                "cache_key": cache_key,
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Failed to invalidate cache entry")
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to invalidate cache entry: {e}",
            },
            indent=2,
        )


__all__ = [
    "MemoryCacheAdapter",
    "register_cache_tools",
    "query_cache_stats",
    "clear_query_cache",
    "warm_cache",
    "invalidate_cache",
    "optimize_cache",
]


async def optimize_cache(
    ctx: Context,
) -> str:
    """Run a no-op cleanup pass and report current cache health.

    Pre-substrate this tool ran a lazy-eviction sweep over the L1/L2
    tiers of ``QueryCacheManager``. The substrate's
    ``MemoryCacheAdapter`` uses TTL-on-write, so there is nothing to
    lazily evict. The tool is preserved as a "is the cache healthy"
    probe — it surfaces the current stats (max_entries,
    current_entries, hits, misses, hit_rate) without trying to
    recreate the L1/L2 lazy-eviction semantic. Returns the same
    envelope as :func:`query_cache_stats` for tool symmetry, plus
    ``entries_cleaned`` (always 0) for legacy clients that expect it.
    """
    try:
        db = _resolve_db()
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        cache = db._query_cache
        # Shim path: TrackedCacheAdapter exposes cleanup_expired().
        # Fallback for fake caches: 0 (no-op).
        entries_cleaned = (
            cache.cleanup_expired()
            if hasattr(cache, "cleanup_expired") and callable(cache.cleanup_expired)
            else 0
        )
        if hasattr(cache, "get_stats") and callable(cache.get_stats):
            stats = cache.get_stats()
        else:
            store_size = len(getattr(cache, "_store", {}) or {})
            stats = {
                "max_entries": cache._settings.max_entries,
                "default_ttl_seconds": cache._settings.default_ttl,
                "current_entries": store_size,
                "backend": "oneiric.MemoryCacheAdapter",
            }

        return json.dumps(
            {
                "success": True,
                "entries_cleaned": entries_cleaned,
                "stats": stats,
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Failed to optimize cache")
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to optimize cache: {e}",
            },
            indent=2,
        )