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
                "error": f"Query rewriting failed: {str(e)}",
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
            return json.dumps(
                {
                    "success": False,
                    "error": "Query rewriter not initialized. Start a session first.",
                },
                indent=2,
            )

        # Get statistics
        stats = rewriter.get_stats()

        # Add interpretation
        cache_hit_rate = stats["cache_hit_rate"] if stats["total_rewrites"] > 0 else 0.0

        return json.dumps(
            {
                "success": True,
                "stats": stats,
                "health": {
                    "cache_hit_rate_category": "Excellent"
                    if cache_hit_rate > 0.7
                    else "Good"
                    if cache_hit_rate > 0.5
                    else "Needs warming",
                    "llm_reliability": "Good"
                    if stats["llm_failures"] == 0
                    else "Some failures"
                    if stats["llm_failures"] < 10
                    else "High failure rate",
                    "avg_latency_category": "Excellent"
                    if stats["avg_latency_ms"] < 100
                    else "Good"
                    if stats["avg_latency_ms"] < 200
                    else "Slow",
                    "total_rewrites": stats["total_rewrites"],
                },
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to retrieve rewrite stats: {str(e)}",
            },
            indent=2,
        )
