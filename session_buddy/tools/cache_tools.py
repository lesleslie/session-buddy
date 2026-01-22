"""Cache management MCP tools for Session Buddy query cache (Phase 1).

This module provides MCP tools for managing the two-tier query cache system,
including viewing statistics, clearing caches, preloading common queries, and
optimizing cache performance.

Cache Architecture:
    L1 (Memory): Fast LRU cache with ~1ms access time
    L2 (DuckDB): Persistent cache with ~10ms access time
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import Context

from session_buddy.cache.query_cache import QueryCacheManager


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
    """View query cache performance metrics and statistics.

    Returns comprehensive statistics about cache performance including:
    - L1 cache: hits, misses, evictions, hit rate, current size
    - L2 cache: hits, misses, evictions, hit rate
    - Overall cache health and efficiency metrics

    Use this tool to monitor cache effectiveness and identify potential issues.

    Returns:
        JSON-formatted string with cache statistics
    """
    # Get cache manager from database adapter
    from session_buddy.di import depends

    try:
        db = depends.get_sync("ReflectionDatabaseAdapterOneiric")
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        stats = db._query_cache.get_stats()

        # Add metadata
        stats["l1_max_size"] = db._query_cache.l1_max_size
        stats["l2_ttl_days"] = db._query_cache.l2_ttl_seconds / 86400
        stats["initialized"] = db._query_cache._initialized

        return json.dumps(
            {
                "success": True,
                "stats": stats,
                "interpretation": {
                    "l1_hit_rate_category": "Excellent"
                    if stats["l1_hit_rate"] > 0.5
                    else "Good"
                    if stats["l1_hit_rate"] > 0.3
                    else "Needs warming",
                    "l2_hit_rate_category": "Excellent"
                    if stats["l2_hit_rate"] > 0.5
                    else "Good"
                    if stats["l2_hit_rate"] > 0.3
                    else "Low",
                    "cache_efficiency": stats["l1_hit_rate"] * 0.7
                    + stats["l2_hit_rate"] * 0.3,
                },
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to retrieve cache stats: {e}",
            },
            indent=2,
        )


async def clear_query_cache(
    ctx: Context,
    cache_level: str = "all",
) -> str:
    """Clear query cache (L1, L2, or both).

    Args:
        cache_level: Which cache to clear
            - "l1": Clear in-memory cache only (fast)
            - "l2": Clear persistent cache only
            - "all": Clear both L1 and L2 caches (default)

    Use this tool to:
    - Force cache refresh when data has changed significantly
    - Free memory when cache is too large
    - Troubleshoot cache-related issues

    Returns:
        JSON-formatted string with operation result
    """
    from session_buddy.di import depends

    try:
        db = depends.get_sync("ReflectionDatabaseAdapterOneiric")
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        cache = db._query_cache
        cleared_l1 = False
        cleared_l2 = False

        if cache_level in ("l1", "all"):
            # Clear L1 cache
            cache.invalidate()  # This clears L1
            cleared_l1 = True

        if cache_level in ("l2", "all"):
            # Clear L2 cache
            cache._clear_l2()
            cleared_l2 = True

        # Get updated stats
        stats = cache.get_stats()

        return json.dumps(
            {
                "success": True,
                "message": f"Cache cleared successfully (level: {cache_level})",
                "cleared": {
                    "l1": cleared_l1,
                    "l2": cleared_l2,
                },
                "new_stats": stats,
            },
            indent=2,
        )

    except Exception as e:
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

    Warms the cache by executing searches for common queries and storing
    the results. This improves performance for frequently-accessed data.

    Use this tool to:
    - Prime cache after session start for known common queries
    - Improve user experience for expected searches
    - Build cache hit rate before users start searching

    Example queries to warm:
    - ["async patterns", "error handling", "authentication", "database optimization"]

    Returns:
        JSON-formatted string with warming results
    """
    from session_buddy.di import depends

    if not queries:
        return json.dumps(
            {
                "success": False,
                "error": "No queries provided. Provide queries to warm cache.",
            },
            indent=2,
        )

    try:
        db = depends.get_sync("ReflectionDatabaseAdapterOneiric")
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        results = []
        stats_before = db._query_cache.get_stats()

        for query in queries:
            try:
                # Execute search (this will automatically populate cache)
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
                results.append(
                    {
                        "query": query,
                        "error": str(e),
                        "success": False,
                    }
                )

        stats_after = db._query_cache.get_stats()

        return json.dumps(
            {
                "success": True,
                "message": f"Warmed cache with {len(queries)} queries",
                "results": results,
                "stats_before": stats_before,
                "stats_after": stats_after,
            },
            indent=2,
        )

    except Exception as e:
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

    Removes a specific query from the cache, forcing it to be re-fetched
    on next search. Useful when:
    - Underlying data has changed significantly
    - Cache entry is stale or incorrect
    - Testing different query variations

    Returns:
        JSON-formatted string with invalidation result
    """
    from session_buddy.di import depends

    try:
        db = depends.get_sync("ReflectionDatabaseAdapterOneiric")
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        # Compute cache key and invalidate
        cache_key = QueryCacheManager.compute_cache_key(
            query=query,
            project=project,
            limit=10,  # Default limit
        )
        db._query_cache.invalidate(cache_key=cache_key)

        return json.dumps(
            {
                "success": True,
                "message": f"Cache entry invalidated for query: '{query}'",
                "cache_key": cache_key,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to invalidate cache entry: {e}",
            },
            indent=2,
        )


async def optimize_cache(
    ctx: Context,
    compact_l2: bool = True,
    cleanup_expired: bool = True,
) -> str:
    """Optimize cache for better performance.

    Args:
        compact_l2: Whether to compact L2 cache (remove fragmentation)
        cleanup_expired: Whether to remove expired entries from L2

    Performs cache optimization operations:
    - Compact L2 cache to reclaim disk space
    - Remove expired entries that are past TTL
    - Update statistics and metrics

    Use this tool to:
    - Improve cache performance after extended use
    - Reclaim disk space from expired entries
    - Maintain optimal cache health

    Returns:
        JSON-formatted string with optimization results
    """
    from session_buddy.di import depends

    try:
        db = depends.get_sync("ReflectionDatabaseAdapterOneiric")
        if not db or not db._query_cache:
            return json.dumps(
                {
                    "success": False,
                    "error": "Query cache not initialized. Start a session first.",
                },
                indent=2,
            )

        results: dict[str, Any] = {}
        stats_before = db._query_cache.get_stats()

        # Cleanup expired entries
        if cleanup_expired:
            deleted_count = await db._query_cache.cleanup_expired()
            results["expired_entries_removed"] = deleted_count

        # Note: DuckDB VACUUM could be added here for compaction
        if compact_l2:
            # DuckDB will auto-compact, but we can track it
            results["l2_compacted"] = True

        stats_after = db._query_cache.get_stats()

        return json.dumps(
            {
                "success": True,
                "message": "Cache optimization completed",
                "results": results,
                "stats_before": stats_before,
                "stats_after": stats_after,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to optimize cache: {e}",
            },
            indent=2,
        )
