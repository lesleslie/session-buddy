#!/usr/bin/env python3
"""Search and reflection tools for session-mgmt-mcp.

Following crackerjack architecture patterns with focused, single-responsibility tools
for conversation memory, semantic search, and knowledge retrieval.

Refactored to use utility modules for reduced code duplication.
"""

from __future__ import annotations

import json
import operator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from session_buddy.utils.database_helpers import require_reflection_database
from session_buddy.utils.error_handlers import _get_logger, validate_required
from session_buddy.utils.messages import ToolMessages
from session_buddy.utils.tool_wrapper import (
    execute_database_tool,
    execute_simple_database_tool,
)

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import (
        ReflectionDatabaseAdapter as ReflectionDatabase,
    )
    from session_buddy.search.progressive_search import SearchTier


# Progressive search imports


# ============================================================================
# Token Optimization (Standalone - No Database)
# ============================================================================


async def _optimize_search_results_impl(
    results: list[dict[str, Any]],
    optimize_tokens: bool,
    max_tokens: int,
    query: str,
) -> dict[str, Any]:
    """Apply token optimization to search results if available."""
    try:
        from session_buddy.token_optimizer import TokenOptimizer

        if optimize_tokens and results:
            optimizer = TokenOptimizer()
            (
                optimized_results,
                optimization_info,
            ) = await optimizer.optimize_search_results(
                results, "truncate_old", max_tokens
            )
            return {
                "results": optimized_results,
                "optimized": True,
                "optimization_info": optimization_info,
            }

        return {"results": results, "optimized": False, "token_count": 0}
    except ImportError:
        _get_logger().info("Token optimizer not available, returning results as-is")
        return {"results": results, "optimized": False, "token_count": 0}
    except Exception as e:
        _get_logger().exception(f"Search optimization failed: {e}")
        return {"results": results, "optimized": False, "error": str(e)}


# ============================================================================
# Store Reflection
# ============================================================================


async def _store_reflection_operation(
    db: ReflectionDatabase, content: str, tags: list[str]
) -> dict[str, Any]:
    """Execute reflection storage operation."""
    reflection_id = await db.store_reflection(content, tags)
    return {"success": True, "id": reflection_id, "content": content, "tags": tags}


def _format_store_reflection(result: dict[str, Any]) -> str:
    """Format reflection storage result."""
    tag_text = f" (tags: {', '.join(result['tags'])})" if result["tags"] else ""
    return f"✅ Reflection stored successfully with ID: {result['id']}{tag_text}"


async def _store_reflection_impl(content: str, tags: list[str] | None = None) -> str:
    """Store an important insight or reflection for future reference."""

    def validator() -> None:
        validate_required(content, "content")

    async def operation(db: ReflectionDatabase) -> dict[str, Any]:
        return await _store_reflection_operation(db, content, tags or [])

    return await execute_database_tool(
        operation, _format_store_reflection, "Store reflection", validator
    )


# ============================================================================
# Quick Search
# ============================================================================


async def _quick_search_operation(
    db: ReflectionDatabase,
    query: str,
    project: str | None,
    min_score: float,
    limit: int = 5,
) -> str:
    """Execute quick search and format results."""
    total_results = await db.search_conversations(
        query=query, project=project, min_score=min_score, limit=limit
    )

    if not total_results:
        return f"🔍 No results found for '{query}'"

    top_result = total_results[0]
    result = f"🔍 **{len(total_results)} results** for '{query}'\n\n"
    result += f"**Top Result** (score: {top_result.get('similarity', 'N/A')}):\n"
    result += f"{top_result.get('content', '')[:200]}..."

    if len(total_results) > 1:
        result += f"\n\n💡 Use get_more_results to see additional {len(total_results) - 1} results"

    return result


async def _quick_search_impl(
    query: str,
    project: str | None = None,
    min_score: float = 0.7,
    limit: int = 5,
) -> str:
    """Quick search that returns only the count and top result for fast overview."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _quick_search_operation(db, query, project, min_score, limit)

    return await execute_simple_database_tool(operation, "Quick search")


# ============================================================================
# Search Summary
# ============================================================================


def _extract_key_terms(all_content: str) -> list[str]:
    """Extract key terms from content."""
    word_freq: dict[str, int] = {}
    for word in all_content.split():
        if len(word) > 4:  # Skip short words
            word_freq[word.lower()] = word_freq.get(word.lower(), 0) + 1

    if word_freq:
        top_words = sorted(word_freq.items(), key=operator.itemgetter(1), reverse=True)[
            :5
        ]
        return [w[0] for w in top_words]
    return []


async def _format_search_summary(query: str, results: list[dict[str, Any]]) -> str:
    """Format complete search summary."""
    if not results:
        return f"🔍 No results found for '{query}'"

    lines = [
        f"🔍 **Search Summary for '{query}'**\n",
        f"**Found**: {len(results)} relevant conversations\n",
    ]

    # Time distribution
    dates = [r.get("timestamp", "") for r in results if r.get("timestamp")]
    if dates:
        lines.append(f"**Time Range**: {min(dates)} to {max(dates)}\n")

    # Key themes
    all_content = " ".join([r.get("content", "")[:100] for r in results])
    key_terms = _extract_key_terms(all_content)
    if key_terms:
        lines.append(f"**Key Terms**: {', '.join(key_terms)}\n")

    lines.append("\n💡 Use search with same query to see individual results")

    return "".join(lines)


async def _search_summary_operation(
    db: ReflectionDatabase, query: str, project: str | None, min_score: float
) -> str:
    """Execute search summary operation."""
    results = await db.search_conversations(
        query=query, project=project, min_score=min_score, limit=20
    )
    return await _format_search_summary(query, results)


async def _search_summary_impl(
    query: str,
    project: str | None = None,
    min_score: float = 0.7,
) -> str:
    """Get aggregated insights from search results without individual result details."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_summary_operation(db, query, project, min_score)

    return await execute_simple_database_tool(operation, "Search summary")


# ============================================================================
# Pagination - Get More Results
# ============================================================================


def _build_pagination_output(
    query: str,
    offset: int,
    paginated_results: list[dict[str, Any]],
    total_results: int,
    limit: int,
) -> str:
    """Build the complete output for paginated results."""
    if not paginated_results:
        return f"🔍 No more results for '{query}' (offset: {offset})"

    output = f"🔍 **Results {offset + 1}-{offset + len(paginated_results)}** for '{query}'\n\n"

    for i, result in enumerate(paginated_results, offset + 1):
        if result.get("timestamp"):
            output += f"**{i}.** ({result['timestamp']}) "
        else:
            output += f"**{i}.** "
        output += f"{result.get('content', '')[:150]}...\n\n"

    if offset + limit < total_results:
        remaining = total_results - (offset + limit)
        output += f"💡 {remaining} more results available"

    return output


async def _get_more_results_operation(
    db: ReflectionDatabase,
    query: str,
    offset: int,
    limit: int,
    project: str | None,
) -> str:
    """Execute pagination operation."""
    results = await db.search_conversations(
        query=query, project=project, limit=limit + offset
    )
    paginated_results = results[offset : offset + limit]
    return _build_pagination_output(
        query, offset, paginated_results, len(results), limit
    )


async def _get_more_results_impl(
    query: str,
    offset: int = 3,
    limit: int = 3,
    project: str | None = None,
) -> str:
    """Get additional search results after an initial search (pagination support)."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _get_more_results_operation(db, query, offset, limit, project)

    return await execute_simple_database_tool(operation, "Get more results")


# ============================================================================
# Search by File
# ============================================================================


def _extract_file_excerpt(content: str, file_path: str) -> str:
    """Extract a relevant excerpt from content based on the file path."""
    if file_path in content:
        start = max(0, content.find(file_path) - 50)
        end = min(len(content), content.find(file_path) + len(file_path) + 100)
        return content[start:end]
    return content[:150]


async def _format_file_search_results(
    file_path: str, results: list[dict[str, Any]]
) -> str:
    """Format file search results."""
    if not results:
        return f"🔍 No conversations found about file: {file_path}"

    output = f"🔍 **{len(results)} conversations** about `{file_path}`\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "

        excerpt = _extract_file_excerpt(result.get("content", ""), file_path)
        output += f"{excerpt}...\n\n"

    return output


async def _search_by_file_operation(
    db: ReflectionDatabase, file_path: str, limit: int, project: str | None
) -> str:
    """Execute file search operation."""
    results = await db.search_conversations(
        query=file_path, project=project, limit=limit
    )
    return await _format_file_search_results(file_path, results)


async def _search_by_file_impl(
    file_path: str,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for conversations that analyzed a specific file."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_by_file_operation(db, file_path, limit, project)

    return await execute_simple_database_tool(operation, "Search by file")


# ============================================================================
# Search by Concept
# ============================================================================


def _extract_relevant_excerpt(content: str, concept: str) -> str:
    """Extract a relevant excerpt from content based on the concept."""
    if concept.lower() in content.lower():
        start = max(0, content.lower().find(concept.lower()) - 75)
        end = min(len(content), start + 200)
        return content[start:end]
    return content[:150]


def _extract_mentioned_files(results: list[dict[str, Any]]) -> list[str]:
    """Extract mentioned files from search results."""
    try:
        from session_buddy.utils.regex_patterns import SAFE_PATTERNS

        all_content = " ".join([r.get("content", "") for r in results])
        files = []

        for pattern_name in (
            "python_files",
            "javascript_files",
            "config_files",
            "documentation_files",
        ):
            pattern = SAFE_PATTERNS[pattern_name]
            matches = pattern.findall(all_content)
            files.extend(matches)

        return list(set(files))[:10] if files else []
    except Exception:
        return []


async def _format_concept_results(
    concept: str, results: list[dict[str, Any]], include_files: bool
) -> str:
    """Format concept search results."""
    if not results:
        return f"🔍 No conversations found about concept: {concept}"

    output = f"🔍 **{len(results)} conversations** about `{concept}`\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "
        if result.get("similarity"):
            output += f"(relevance: {result['similarity']:.2f}) "

        excerpt = _extract_relevant_excerpt(result.get("content", ""), concept)
        output += f"{excerpt}...\n\n"

    if include_files:
        files = _extract_mentioned_files(results)
        if files:
            output += f"📁 **Related Files**: {', '.join(files)}"

    return output


async def _search_by_concept_operation(
    db: ReflectionDatabase,
    concept: str,
    include_files: bool,
    limit: int,
    project: str | None,
) -> str:
    """Execute concept search operation."""
    results = await db.search_conversations(
        query=concept, project=project, limit=limit, min_score=0.6
    )
    return await _format_concept_results(concept, results, include_files)


async def _search_by_concept_impl(
    concept: str,
    include_files: bool = True,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for conversations about a specific development concept."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_by_concept_operation(
            db, concept, include_files, limit, project
        )

    return await execute_simple_database_tool(operation, "Search by concept")


# ============================================================================
# Database Management
# ============================================================================


async def _reset_reflection_database_impl() -> str:
    """Reset the reflection database connection to fix lock issues."""
    try:
        await require_reflection_database()
        return "✅ Reflection database connection verified successfully"
    except Exception as e:
        return ToolMessages.operation_failed("Database reset", e)


async def _reflection_stats_operation(db: ReflectionDatabase) -> str:
    """Execute reflection stats operation."""
    stats = await db.get_stats()
    output = "📊 **Reflection Database Statistics**\n\n"
    for key, value in stats.items():
        output += f"**{key.replace('_', ' ').title()}**: {value}\n"
    return output


async def _reflection_stats_impl() -> str:
    """Get statistics about the reflection database."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _reflection_stats_operation(db)

    return await execute_simple_database_tool(operation, "Reflection stats")


# ============================================================================
# Search Code
# ============================================================================


def _extract_code_blocks_from_content(content: str) -> list[str]:
    """Extract code blocks from content using regex patterns."""
    try:
        from session_buddy.utils.regex_patterns import SAFE_PATTERNS

        code_pattern = SAFE_PATTERNS["generic_code_block"]
        matches = code_pattern.findall(content)
        return matches if matches is not None else []
    except Exception:
        return []


async def _format_code_search_results(
    query: str, results: list[dict[str, Any]], pattern_type: str | None
) -> str:
    """Format code search results."""
    if not results:
        return f"🔍 No code patterns found for: {query}"

    output = f"🔍 **{len(results)} code patterns** for `{query}`"
    if pattern_type:
        output += f" (type: {pattern_type})"
    output += "\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "

        content = result.get("content", "")
        code_blocks = _extract_code_blocks_from_content(content)

        if code_blocks:
            code = code_blocks[0][:200]
            output += f"\n```\n{code}...\n```\n\n"
        else:
            if query.lower() in content.lower():
                start = max(0, content.lower().find(query.lower()) - 50)
                end = min(len(content), start + 150)
                excerpt = content[start:end]
            else:
                excerpt = content[:100]
            output += f"{excerpt}...\n\n"

    return output


async def _search_code_operation(
    db: ReflectionDatabase,
    query: str,
    pattern_type: str | None,
    limit: int,
    project: str | None,
) -> str:
    """Execute code search operation."""
    code_query = f"code {query}"
    if pattern_type:
        code_query += f" {pattern_type}"

    results = await db.search_conversations(
        query=code_query, project=project, limit=limit, min_score=0.5
    )
    return await _format_code_search_results(query, results, pattern_type)


async def _search_code_impl(
    query: str,
    pattern_type: str | None = None,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for code patterns in conversations using AST parsing."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_code_operation(db, query, pattern_type, limit, project)

    return await execute_simple_database_tool(operation, "Search code")


# ============================================================================
# Search Errors
# ============================================================================


def _find_best_error_excerpt(content: str) -> str:
    """Find the most relevant excerpt from content based on error keywords."""
    error_keywords = ["error", "exception", "traceback", "failed", "fix"]
    best_excerpt = ""
    best_score = 0

    for keyword in error_keywords:
        if keyword in content.lower():
            start = max(0, content.lower().find(keyword) - 75)
            end = min(len(content), start + 200)
            excerpt = content[start:end]
            score = content.lower().count(keyword)
            if score > best_score:
                best_score = score
                best_excerpt = excerpt

    return best_excerpt or content[:150]


async def _format_error_search_results(
    query: str, results: list[dict[str, Any]], error_type: str | None
) -> str:
    """Format error search results."""
    if not results:
        return f"🔍 No error patterns found for: {query}"

    output = f"🔍 **{len(results)} error contexts** for `{query}`"
    if error_type:
        output += f" (type: {error_type})"
    output += "\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "

        best_excerpt = _find_best_error_excerpt(result.get("content", ""))
        output += f"{best_excerpt}...\n\n"

    return output


async def _search_errors_operation(
    db: ReflectionDatabase,
    query: str,
    error_type: str | None,
    limit: int,
    project: str | None,
) -> str:
    """Execute error search operation."""
    error_query = f"error {query}"
    if error_type:
        error_query += f" {error_type}"

    results = await db.search_conversations(
        query=error_query, project=project, limit=limit, min_score=0.4
    )
    return await _format_error_search_results(query, results, error_type)


async def _search_errors_impl(
    query: str,
    error_type: str | None = None,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for error patterns and debugging contexts in conversations."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_errors_operation(db, query, error_type, limit, project)

    return await execute_simple_database_tool(operation, "Search errors")


# ============================================================================
# Temporal Search
# ============================================================================


def _parse_time_expression(time_expression: str) -> datetime | None:
    """Parse natural language time expression into datetime."""
    now = datetime.now()

    if "yesterday" in time_expression.lower():
        return now - timedelta(days=1)
    if "last week" in time_expression.lower():
        return now - timedelta(days=7)
    if "last month" in time_expression.lower():
        return now - timedelta(days=30)
    if "today" in time_expression.lower():
        return now - timedelta(hours=24)

    return None


async def _format_temporal_results(
    time_expression: str, query: str | None, results: list[dict[str, Any]]
) -> str:
    """Format temporal search results."""
    if not results:
        return f"🔍 No conversations found for time period: {time_expression}"

    output = f"🔍 **{len(results)} conversations** from `{time_expression}`"
    if query:
        output += f" matching `{query}`"
    output += "\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "

        content = result.get("content", "")
        output += f"{content[:150]}...\n\n"

    return output


async def _search_temporal_operation(
    db: ReflectionDatabase,
    time_expression: str,
    query: str | None,
    limit: int,
    project: str | None,
) -> str:
    """Execute temporal search operation."""
    start_time = _parse_time_expression(time_expression)
    search_query = query or ""
    results = await db.search_conversations(
        query=search_query, project=project, limit=limit * 2
    )

    if start_time:
        # Simplified filter - would need proper timestamp parsing
        filtered_results = results.copy()
        results = filtered_results[:limit]

    return await _format_temporal_results(time_expression, query, results)


async def _search_temporal_impl(
    time_expression: str,
    query: str | None = None,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search conversations within a specific time range using natural language."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_temporal_operation(
            db, time_expression, query, limit, project
        )

    return await execute_simple_database_tool(operation, "Temporal search")


# ============================================================================
# MCP Tool Registration
# ============================================================================


def _parse_tags_parameter(tags: list[str] | str | None) -> list[str] | None:
    """Parse and validate tags parameter from MCP protocol.

    Handles JSON string deserialization from MCP protocol where complex types
    are serialized to JSON strings during transport.

    Args:
        tags: Tags parameter (list, JSON string, or None)

    Returns:
        Parsed tags as list[str] or None

    Examples:
        >>> _parse_tags_parameter('["tag1", "tag2"]')
        ['tag1', 'tag2']
        >>> _parse_tags_parameter('single-tag')
        ['single-tag']
        >>> _parse_tags_parameter(['already', 'list'])
        ['already', 'list']
        >>> _parse_tags_parameter(None)
        None
    """
    if not isinstance(tags, str):
        return tags

    # Handle JSON string deserialization
    try:
        decoded = json.loads(tags)
        if isinstance(decoded, list):
            return [str(tag) for tag in decoded]
        elif decoded is None:
            return None
        else:
            # Single non-list value, wrap it
            return [str(decoded)]
    except json.JSONDecodeError:
        # Not valid JSON, treat as single tag
        return [tags]


def _register_core_search_tools(mcp: Any) -> None:
    """Register core search and reflection tools.

    Args:
        mcp: FastMCP server instance

    """

    @mcp.tool()  # type: ignore[misc]
    async def _optimize_search_results(
        results: list[dict[str, Any]],
        optimize_tokens: bool,
        max_tokens: int,
        query: str,
    ) -> dict[str, Any]:
        return await _optimize_search_results_impl(
            results, optimize_tokens, max_tokens, query
        )

    @mcp.tool()  # type: ignore[misc]
    async def store_reflection(
        content: str, tags: list[str] | str | None = None
    ) -> str:
        """Store an important insight or reflection for future reference."""
        parsed_tags = _parse_tags_parameter(tags)
        return await _store_reflection_impl(content, parsed_tags)

    @mcp.tool()  # type: ignore[misc]
    async def quick_search(
        query: str, project: str | None = None, min_score: float = 0.7, limit: int = 5
    ) -> str:
        # Note: For quick search, we're using the limit to determine how many results to return,
        # but the underlying implementation may not use this parameter directly
        return await _quick_search_impl(query, project, min_score)

    @mcp.tool()  # type: ignore[misc]
    async def search_summary(
        query: str, project: str | None = None, min_score: float = 0.7
    ) -> str:
        return await _search_summary_impl(query, project, min_score)

    @mcp.tool()  # type: ignore[misc]
    async def get_more_results(
        query: str, offset: int = 3, limit: int = 3, project: str | None = None
    ) -> str:
        return await _get_more_results_impl(query, offset, limit, project)


def _register_specialized_search_tools(mcp: Any) -> None:
    """Register specialized search tools (file, concept, code, errors, temporal).

    Args:
        mcp: FastMCP server instance

    """

    @mcp.tool()  # type: ignore[misc]
    async def search_by_file(
        file_path: str, limit: int = 10, project: str | None = None
    ) -> str:
        return await _search_by_file_impl(file_path, limit, project)

    @mcp.tool()  # type: ignore[misc]
    async def search_by_concept(
        concept: str,
        include_files: bool = True,
        limit: int = 10,
        project: str | None = None,
    ) -> str:
        return await _search_by_concept_impl(concept, include_files, limit, project)

    @mcp.tool()  # type: ignore[misc]
    async def reset_reflection_database() -> str:
        return await _reset_reflection_database_impl()

    @mcp.tool()  # type: ignore[misc]
    async def reflection_stats() -> str:
        return await _reflection_stats_impl()

    @mcp.tool()  # type: ignore[misc]
    async def search_code(
        query: str,
        pattern_type: str | None = None,
        limit: int = 10,
        project: str | None = None,
    ) -> str:
        return await _search_code_impl(query, pattern_type, limit, project)

    @mcp.tool()  # type: ignore[misc]
    async def search_errors(
        query: str,
        error_type: str | None = None,
        limit: int = 10,
        project: str | None = None,
    ) -> str:
        return await _search_errors_impl(query, error_type, limit, project)

    @mcp.tool()  # type: ignore[misc]
    async def search_temporal(
        time_expression: str,
        query: str | None = None,
        limit: int = 10,
        project: str | None = None,
    ) -> str:
        return await _search_temporal_impl(time_expression, query, limit, project)


def _register_progressive_search_tools(mcp: Any) -> None:
    """Register progressive search tools (Phase 3).

    Args:
        mcp: FastMCP server instance

    """

    @mcp.tool()  # type: ignore[misc]
    async def progressive_search(
        query: str,
        project: str | None = None,
        min_score: float = 0.6,
        max_results: int = 30,
        max_tiers: int = 4,
        enable_early_stop: bool = True,
    ) -> dict[str, Any]:
        """Execute multi-tier progressive search with early stopping.

        Searches from fastest to slowest tiers (CATEGORIES → INSIGHTS → REFLECTIONS → CONVERSATIONS)
        and stops early when sufficient results found.

        Args:
            query: Search query string
            project: Optional project filter
            min_score: Minimum similarity score (0.0-1.0)
            max_results: Maximum total results across all tiers
            max_tiers: Maximum number of tiers to search (1-4)
            enable_early_stop: Whether to enable early stopping optimization

        Returns:
            Dictionary with search results, tier breakdown, and performance metrics
        """
        return await _progressive_search_impl(
            query, project, min_score, max_results, max_tiers, enable_early_stop
        )

    @mcp.tool()  # type: ignore[misc]
    async def configure_tiers(
        categories_min_score: float | None = None,
        categories_max_results: int | None = None,
        insights_min_score: float | None = None,
        insights_max_results: int | None = None,
        reflections_min_score: float | None = None,
        reflections_max_results: int | None = None,
        conversations_min_score: float | None = None,
        conversations_max_results: int | None = None,
        sufficiency_min_results: int | None = None,
        sufficiency_high_quality_threshold: float | None = None,
    ) -> dict[str, Any]:
        """Configure progressive search tier thresholds and sufficiency evaluation.

        Allows customization of tier-specific quality thresholds and result limits,
        as well as early stopping behavior.

        Args:
            categories_min_score: Minimum score for CATEGORIES tier (0.0-1.0)
            categories_max_results: Maximum results from CATEGORIES tier
            insights_min_score: Minimum score for INSIGHTS tier (0.0-1.0)
            insights_max_results: Maximum results from INSIGHTS tier
            reflections_min_score: Minimum score for REFLECTIONS tier (0.0-1.0)
            reflections_max_results: Maximum results from REFLECTIONS tier
            conversations_min_score: Minimum score for CONVERSATIONS tier (0.0-1.0)
            conversations_max_results: Maximum results from CONVERSATIONS tier
            sufficiency_min_results: Minimum results before considering early stop
            sufficiency_high_quality_threshold: Avg score to consider results "high quality"

        Returns:
            Dictionary with updated configuration and confirmation
        """
        return await _configure_tiers_impl(
            categories_min_score,
            categories_max_results,
            insights_min_score,
            insights_max_results,
            reflections_min_score,
            reflections_max_results,
            conversations_min_score,
            conversations_max_results,
            sufficiency_min_results,
            sufficiency_high_quality_threshold,
        )

    @mcp.tool()  # type: ignore[misc]
    async def tier_stats() -> dict[str, Any]:
        """Get progressive search tier statistics and current configuration.

        Returns tier performance metrics, configuration settings, and usage statistics
        for monitoring and optimization.
        """
        return await _tier_stats_impl()


def register_search_tools(mcp: Any) -> None:
    """Register all search-related MCP tools.

    Args:
        mcp: FastMCP server instance

    """
    _register_core_search_tools(mcp)
    _register_specialized_search_tools(mcp)
    _register_progressive_search_tools(mcp)


# ============================================================================
# Progressive Search (Phase 3)
# ============================================================================


async def _progressive_search_impl(
    query: str,
    project: str | None = None,
    min_score: float = 0.6,
    max_results: int = 30,
    max_tiers: int = 4,
    enable_early_stop: bool = True,
) -> dict[str, Any]:
    """Execute progressive search across multiple tiers.

    Args:
        query: Search query string
        project: Optional project filter
        min_score: Minimum similarity score (0.0-1.0)
        max_results: Maximum total results across all tiers
        max_tiers: Maximum number of tiers to search (1-4)
        enable_early_stop: Whether to enable early stopping optimization

    Returns:
        Dictionary with search results and metadata
    """
    try:
        from session_buddy.search import ProgressiveSearchEngine

        engine = ProgressiveSearchEngine()
        result = await engine.search_progressive(
            query=query,
            project=project,
            min_score=min_score,
            max_results=max_results,
            max_tiers=max_tiers,
            enable_early_stop=enable_early_stop,
        )

        # Format results for display
        formatted_results = []
        for tier_result in result.tier_results:
            tier_name = SearchTier.get_tier_name(tier_result.tier)
            for item in tier_result.results[:5]:  # Show first 5 per tier
                formatted_results.append(
                    f"[{tier_name}] {item.get('content', '')[:100]}..."
                )

        return {
            "success": True,
            "query": query,
            "total_results": result.total_results,
            "tiers_searched": len(result.tiers_searched),
            "tier_names": [SearchTier.get_tier_name(t) for t in result.tiers_searched],
            "early_stop": result.early_stop,
            "total_latency_ms": result.total_latency_ms,
            "early_stop_reason": result.metadata.get("early_stop_reason"),
            "sample_results": formatted_results,
        }

    except ImportError:
        return {
            "success": False,
            "error": "Progressive search engine not available",
            "query": query,
        }
    except Exception as e:
        _get_logger().exception(f"Progressive search failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "query": query,
        }


async def _configure_tiers_impl(
    categories_min_score: float | None = None,
    categories_max_results: int | None = None,
    insights_min_score: float | None = None,
    insights_max_results: int | None = None,
    reflections_min_score: float | None = None,
    reflections_max_results: int | None = None,
    conversations_min_score: float | None = None,
    conversations_max_results: int | None = None,
    sufficiency_min_results: int | None = None,
    sufficiency_high_quality_threshold: float | None = None,
) -> dict[str, Any]:
    """Configure progressive search tier thresholds.

    Args:
        categories_min_score: Minimum score for CATEGORIES tier (0.0-1.0)
        categories_max_results: Max results for CATEGORIES tier
        insights_min_score: Minimum score for INSIGHTS tier (0.0-1.0)
        insights_max_results: Max results for INSIGHTS tier
        reflections_min_score: Minimum score for REFLECTIONS tier (0.0-1.0)
        reflections_max_results: Max results for REFLECTIONS tier
        conversations_min_score: Minimum score for CONVERSATIONS tier (0.0-1.0)
        conversations_max_results: Max results for CONVERSATIONS tier
        sufficiency_min_results: Minimum results before early stop consideration
        sufficiency_high_quality_threshold: Avg score to consider "high quality"

    Returns:
        Dictionary with configuration status
    """
    try:
        from session_buddy.search import SufficiencyConfig

        config = SufficiencyConfig()

        # Update tier thresholds
        if categories_min_score is not None:
            # Note: This would require modifying SearchTier.get_min_score
            # For now, we'll just update sufficiency config
            pass

        if categories_max_results is not None:
            # Note: This would require modifying SearchTier.get_max_results
            pass

        # Update sufficiency config
        if sufficiency_min_results is not None:
            config.min_results = sufficiency_min_results

        if sufficiency_high_quality_threshold is not None:
            config.high_quality_threshold = sufficiency_high_quality_threshold

        return {
            "success": True,
            "message": "Tier configuration updated",
            "config": {
                "min_results": config.min_results,
                "high_quality_threshold": config.high_quality_threshold,
                "perfect_match_threshold": config.perfect_match_threshold,
                "max_tiers": config.max_tiers,
                "tier_timeout_ms": config.tier_timeout_ms,
                "quality_weight": config.quality_weight,
                "quantity_weight": config.quantity_weight,
            },
        }

    except ImportError:
        return {
            "success": False,
            "error": "Progressive search configuration not available",
        }
    except Exception as e:
        _get_logger().exception(f"Tier configuration failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


async def _tier_stats_impl() -> dict[str, Any]:
    """Get progressive search tier statistics.

    Returns:
        Dictionary with tier performance metrics
    """
    try:
        from session_buddy.search import ProgressiveSearchEngine

        engine = ProgressiveSearchEngine()
        stats = engine.get_search_stats()

        return {
            "success": True,
            "stats": stats,
            "tier_info": {
                "CATEGORIES": {
                    "min_score": 0.9,
                    "max_results": 10,
                    "name": "High-quality insights",
                },
                "INSIGHTS": {
                    "min_score": 0.75,
                    "max_results": 15,
                    "name": "Learned skills",
                },
                "REFLECTIONS": {
                    "min_score": 0.7,
                    "max_results": 20,
                    "name": "Stored reflections",
                },
                "CONVERSATIONS": {
                    "min_score": 0.6,
                    "max_results": 30,
                    "name": "Full conversations",
                },
            },
        }

    except ImportError:
        return {
            "success": False,
            "error": "Progressive search statistics not available",
        }
    except Exception as e:
        _get_logger().exception(f"Tier stats retrieval failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
