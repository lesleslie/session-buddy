"""Query rewriting MCP tools for Session Buddy (Phase 2).

This module provides MCP tools for manual query rewriting and statistics,
useful for testing and debugging the query rewriting system.

Tools:
    - rewrite_query: Manually rewrite a query (testing/debugging)
    - query_rewrite_stats: View rewriting performance statistics

Usage:
    >>> from session_buddy.tools import rewriting_tools
    >>> await rewriting_tools.rewrite_query(ctx, "what did I learn?")
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import Context

from session_buddy.rewriting.query_rewriter import QueryRewriter, RewriteContext


async def rewrite_query(
    ctx: Context,
    query: str,
    project: str | None = None,
    recent_conversations: list[dict[str, Any]] | None = None,
    recent_files: list[str] | None = None,
    force_rewrite: bool = False,
) -> str:
    """Manually rewrite a query with context expansion (testing/debugging tool).

    This tool allows you to manually test the query rewriting system with
    specific queries and context. Useful for:
    - Debugging why a query was or wasn't rewritten
    - Testing query rewriting with custom context
    - Understanding how the rewriter interprets ambiguous queries
    - Verifying LLM prompt effectiveness

    Args:
        query: The query string to rewrite
        project: Optional project filter for query context
        recent_conversations: Optional list of recent conversations for context
        recent_files: Optional list of recent files for context
        force_rewrite: Force rewrite even if cached version exists

    Returns:
        JSON-formatted string with rewrite result including:
        - original_query: The input query
        - rewritten_query: The expanded query (or original if not ambiguous)
        - was_rewritten: Whether the query was rewritten
        - confidence: Confidence score (0.0-1.0)
        - llm_provider: LLM provider used (or None)
        - latency_ms: Time taken to rewrite
        - cache_hit: Whether result was retrieved from cache

    Example:
        >>> await rewrite_query(ctx, "what did I learn about async?")
    """
    try:
        # Get or create rewriter
        from session_buddy.di import depends

        rewriter = depends.get_sync("QueryRewriter")
        if not rewriter:
            rewriter = QueryRewriter()
            # Store in DI container for reuse
            # Note: This is a simple singleton pattern for the session

        # Build context
        rewrite_context = RewriteContext(
            query=query,
            recent_conversations=recent_conversations or [],
            project=project,
            recent_files=recent_files or [],
            session_context={"session_id": getattr(ctx, "session_id", "manual")},
        )

        # Rewrite query
        result = await rewriter.rewrite_query(
            query=query,
            context=rewrite_context,
            force_rewrite=force_rewrite,
        )

        # Format result
        return json.dumps(
            {
                "success": True,
                "result": {
                    "original_query": result.original_query,
                    "rewritten_query": result.rewritten_query,
                    "was_rewritten": result.was_rewritten,
                    "confidence": result.confidence,
                    "llm_provider": result.llm_provider,
                    "latency_ms": result.latency_ms,
                    "context_used": result.context_used,
                    "cache_hit": result.cache_hit,
                },
                "interpretation": {
                    "query_type": "ambiguous" if result.was_rewritten else "clear",
                    "rewriting_quality": "high"
                    if result.confidence > 0.8
                    else "medium"
                    if result.confidence > 0.5
                    else "low",
                    "cache_efficiency": "cache hit"
                    if result.cache_hit
                    else "new rewrite",
                },
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Query rewriting failed: {e}",
                "query": query,
            },
            indent=2,
        )


async def query_rewrite_stats(
    ctx: Context,
) -> str:
    """View query rewriting performance statistics.

    Returns comprehensive statistics about query rewriting performance including:
    - Total rewrites performed
    - Cache hit rate (percentage of rewrites served from cache)
    - LLM failures count
    - Average latency for rewrites
    - Current cache size

    Use this tool to:
    - Monitor query rewriting effectiveness
    - Identify LLM performance issues
    - Track cache efficiency
    - Debug rewriting system health

    Returns:
        JSON-formatted string with rewriting statistics and health metrics
    """
    try:
        from session_buddy.di import depends

        rewriter = depends.get_sync("QueryRewriter")
        if not rewriter:
            return _format_error_response(
                "Query rewriter not initialized. Start a session first."
            )

        stats = rewriter.get_stats()
        health = _calculate_rewrite_health(stats)

        return json.dumps(
            {
                "success": True,
                "stats": stats,
                "health": health,
            },
            indent=2,
        )

    except Exception as e:
        return _format_error_response(f"Failed to retrieve rewrite stats: {e}")


def _format_error_response(error_message: str) -> str:
    """Format an error response as JSON.

    Args:
        error_message: The error message

    Returns:
        JSON-formatted error response

    """
    return json.dumps(
        {
            "success": False,
            "error": error_message,
        },
        indent=2,
    )


def _calculate_rewrite_health(stats: dict[str, Any]) -> dict[str, Any]:
    """Calculate health metrics from rewrite statistics.

    Args:
        stats: Statistics dictionary from QueryRewriter

    Returns:
        Health assessment with categories

    """
    cache_hit_rate = stats["cache_hit_rate"] if stats["total_rewrites"] > 0 else 0.0

    return {
        "cache_hit_rate_category": _categorize_cache_hit_rate(cache_hit_rate),
        "llm_reliability": _categorize_llm_reliability(stats["llm_failures"]),
        "avg_latency_category": _categorize_latency(stats["avg_latency_ms"]),
        "total_rewrites": stats["total_rewrites"],
    }


def _categorize_cache_hit_rate(rate: float) -> str:
    """Categorize cache hit rate.

    Args:
        rate: Cache hit rate (0.0 to 1.0)

    Returns:
        Category string

    """
    if rate > 0.7:
        return "Excellent"
    if rate > 0.5:
        return "Good"
    return "Needs warming"


def _categorize_llm_reliability(failures: int) -> str:
    """Categorize LLM reliability based on failure count.

    Args:
        failures: Number of LLM failures

    Returns:
        Category string

    """
    if failures == 0:
        return "Good"
    if failures < 10:
        return "Some failures"
    return "High failure rate"


def _categorize_latency(latency_ms: float) -> str:
    """Categorize latency.

    Args:
        latency_ms: Average latency in milliseconds

    Returns:
        Category string

    """
    if latency_ms < 100:
        return "Excellent"
    if latency_ms < 200:
        return "Good"
    return "Slow"
