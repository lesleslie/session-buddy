#!/usr/bin/env python3
"""Memory and reflection management MCP tools.

This module provides tools for storing, searching, and managing reflections and conversation memories.

Refactored to use utility modules for reduced code duplication.
"""

from __future__ import annotations

import asyncio
import operator
import typing as t
from datetime import datetime
from typing import TYPE_CHECKING, Any

from session_buddy.utils.database_helpers import require_reflection_database
from session_buddy.utils.error_handlers import (
    DatabaseUnavailableError,
    ValidationError,
    _get_logger,
    validate_required,
)
from session_buddy.utils.messages import ToolMessages
from session_buddy.utils.tool_wrapper import format_reflection_result

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


_reflection_tools_available: bool | None = None
_reflection_db: ReflectionDatabaseAdapter | None = None


def _check_reflection_tools_available() -> bool:
    """Check if reflection tools are available, cached for reuse."""
    global _reflection_tools_available
    if _reflection_tools_available is not None:
        return _reflection_tools_available
    try:
        import importlib.util

        _reflection_tools_available = importlib.util.find_spec("duckdb") is not None
    except (ImportError, AttributeError):
        _reflection_tools_available = False
    return _reflection_tools_available


async def _get_reflection_database() -> ReflectionDatabaseAdapter:
    """Get reflection database instance (patchable for tests)."""
    global _reflection_db
    if _reflection_db is not None:
        return _reflection_db
    _reflection_db = await require_reflection_database()
    return _reflection_db


async def _execute_database_tool(
    operation: t.Callable[[ReflectionDatabaseAdapter], t.Awaitable[t.Any]],
    formatter: t.Callable[[t.Any], str],
    operation_name: str,
    validator: t.Callable[[], None] | None = None,
) -> str:
    try:
        if validator:
            validator()

        db = await _get_reflection_database()
        result = await operation(db)
        return formatter(result)
    except ValidationError as e:
        return ToolMessages.validation_error(operation_name, str(e))
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available(operation_name, str(e))
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


async def _execute_simple_database_tool(
    operation: t.Callable[[ReflectionDatabaseAdapter], t.Awaitable[str]],
    operation_name: str,
) -> str:
    try:
        db = await _get_reflection_database()
        return await operation(db)
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available(operation_name, str(e))
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


def _format_score(score: float) -> str:
    """Format a score as a percentage or relevance indicator."""
    return f"{score:.2f}"


# ============================================================================
# Store Reflection Tool
# ============================================================================


async def _store_reflection_operation(
    db: ReflectionDatabaseAdapter, content: str, tags: list[str]
) -> dict[str, Any]:
    """Execute reflection storage operation."""
    success = await db.store_reflection(content, tags=tags)
    return {
        "success": success,
        "content": content,
        "tags": tags,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _format_store_reflection_result(result: dict[str, Any]) -> str:
    """Format reflection storage result."""
    return format_reflection_result(
        result["success"],
        result["content"],
        result.get("tags"),
        result.get("timestamp"),
    )


async def _store_reflection_impl(content: str, tags: list[str] | None = None) -> str:
    """Implementation for store_reflection tool."""
    if not _check_reflection_tools_available():
        return "Reflection tools not available. Install dependencies: uv sync --extra embeddings"

    try:
        validate_required(content, "content")
        db = await _get_reflection_database()
        result = await _store_reflection_operation(db, content, tags or [])
        return _format_store_reflection_result(result)
    except ValidationError as e:
        return ToolMessages.validation_error("Store reflection", str(e))
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available("Store reflection", str(e))
    except Exception as e:
        _get_logger().exception(f"Error storing reflection: {e}")
        return f"Error storing reflection: {e}"


# ============================================================================
# Quick Search Tool
# ============================================================================


async def _quick_search_operation(
    db: ReflectionDatabaseAdapter,
    query: str,
    project: str | None,
    min_score: float,
) -> str:
    """Execute quick search operation and format results."""
    results = await db.search_conversations(
        query=query,
        project=project,
        limit=1,
        min_score=min_score,
    )

    lines = [f"🔍 Quick search for: '{query}'"]

    if results:
        result = results[0]
        lines.extend(
            (
                "📊 Found results (showing top 1)",
                f"📝 {ToolMessages.truncate_text(result['content'], 150)}",
            )
        )
        if result.get("project"):
            lines.append(f"📁 Project: {result['project']}")
        if result.get("score") is not None:
            lines.append(f"⭐ Relevance: {_format_score(result['score'])}")
        lines.append(f"📅 Date: {result.get('timestamp', 'Unknown')}")
    else:
        lines.extend(
            (
                "🔍 No results found",
                "💡 Try adjusting your search terms or lowering min_score",
            )
        )

    return "\n".join(lines)


async def _quick_search_impl(
    query: str,
    min_score: float = 0.7,
    project: str | None = None,
) -> str:
    """Implementation for quick_search tool."""
    if not _check_reflection_tools_available():
        return "Reflection tools not available. Install dependencies: uv sync --extra embeddings"

    async def operation(db: ReflectionDatabaseAdapter) -> str:
        return await _quick_search_operation(db, query, project, min_score)

    return await _execute_simple_database_tool(operation, "Quick search")


# ============================================================================
# Search Summary Tool
# ============================================================================


async def _analyze_project_distribution(
    results: list[dict[str, Any]],
) -> dict[str, int]:
    """Analyze project distribution of search results."""
    projects: dict[str, int] = {}
    for result in results:
        proj = result.get("project", "Unknown")
        projects[proj] = projects.get(proj, 0) + 1
    return projects


async def _analyze_relevance_scores(
    results: list[dict[str, Any]],
) -> tuple[float, list[float]]:
    """Analyze relevance scores of search results."""
    scores = [r.get("score", 0.0) for r in results if r.get("score") is not None]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    return avg_score, scores


async def _extract_common_themes(
    results: list[dict[str, Any]],
) -> list[tuple[str, int]]:
    """Extract common themes from search results."""
    all_content = " ".join([r["content"] for r in results])
    words = all_content.lower().split()
    word_freq: dict[str, int] = {}

    for word in words:
        if len(word) > 4:  # Skip short words
            word_freq[word] = word_freq.get(word, 0) + 1

    if word_freq:
        return sorted(word_freq.items(), key=operator.itemgetter(1), reverse=True)[:5]
    return []


async def _format_search_summary(
    query: str,
    results: list[dict[str, Any]],
) -> str:
    """Format complete search summary."""
    lines = [
        f"📊 Search Summary for: '{query}'",
        "=" * 50,
    ]

    if not results:
        lines.extend(
            [
                "🔍 No results found",
                "💡 Try different search terms or lower the min_score threshold",
            ]
        )
        return "\n".join(lines)

    # Basic stats
    lines.append(f"📈 Total results: {len(results)}")

    # Project distribution
    projects = await _analyze_project_distribution(results)
    if len(projects) > 1:
        lines.append("📁 Project distribution:")
        for proj, count in sorted(
            projects.items(), key=operator.itemgetter(1), reverse=True
        ):
            lines.append(f"   • {proj}: {count} results")

    # Time distribution
    timestamps = [r.get("timestamp") for r in results if r.get("timestamp")]
    if timestamps:
        lines.append(f"📅 Time range: {len(timestamps)} results with dates")

    # Relevance scores
    avg_score, scores = await _analyze_relevance_scores(results)
    if scores:
        lines.append(f"⭐ Average relevance: {_format_score(avg_score)}")

    # Common themes
    top_words = await _extract_common_themes(results)
    if top_words:
        lines.append("🔤 Common themes:")
        for word, freq in top_words:
            lines.append(f"   • {word}: {freq} mentions")

    return "\n".join(lines)


async def _search_summary_operation(
    db: ReflectionDatabaseAdapter,
    query: str,
    project: str | None,
    min_score: float,
) -> str:
    """Execute search summary operation."""
    results = await db.search_conversations(
        query=query,
        project=project,
        limit=20,
        min_score=min_score,
    )
    return await _format_search_summary(query, results)


async def _search_summary_impl(
    query: str,
    min_score: float = 0.7,
    project: str | None = None,
) -> str:
    """Implementation for search_summary tool."""
    if not _check_reflection_tools_available():
        return "Reflection tools not available. Install dependencies: uv sync --extra embeddings"

    try:
        db = await _get_reflection_database()
        return await _search_summary_operation(db, query, project, min_score)
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available("Search summary", str(e))
    except Exception as e:
        _get_logger().exception(f"Search summary error: {e}")
        return f"Search summary error: {e}"


# ============================================================================
# Search by File Tool
# ============================================================================


async def _format_file_search_results(
    file_path: str,
    results: list[dict[str, Any]],
) -> str:
    """Format file search results."""
    lines = [
        f"📁 Searching conversations about: {file_path}",
        "=" * 50,
    ]

    if not results:
        lines.extend(
            [
                "🔍 No conversations found about this file",
                "💡 The file might not have been discussed in previous sessions",
            ]
        )
        return "\n".join(lines)

    lines.append(f"📈 Found {len(results)} relevant conversations:")

    for i, result in enumerate(results, 1):
        lines.append(
            f"\n{i}. 📝 {ToolMessages.truncate_text(result['content'], 200)}",
        )
        if result.get("project"):
            lines.append(f"   📁 Project: {result['project']}")
        if result.get("score") is not None:
            lines.append(f"   ⭐ Relevance: {_format_score(result['score'])}")
        if result.get("timestamp"):
            lines.append(f"   📅 Date: {result['timestamp']}")

    return "\n".join(lines)


async def _search_by_file_operation(
    db: ReflectionDatabaseAdapter,
    file_path: str,
    limit: int,
    project: str | None,
) -> str:
    """Execute file search operation."""
    results = await db.search_conversations(
        query=file_path,
        project=project,
        limit=limit,
    )
    return await _format_file_search_results(file_path, results)


async def _search_by_file_impl(
    file_path: str,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Implementation for search_by_file tool."""
    if not _check_reflection_tools_available():
        return "Reflection tools not available. Install dependencies: uv sync --extra embeddings"

    try:
        db = await _get_reflection_database()
        return await _search_by_file_operation(db, file_path, limit, project)
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available("Search by file", str(e))
    except Exception as e:
        _get_logger().exception(f"File search error: {e}")
        return f"File search error: {e}"


# ============================================================================
# Search by Concept Tool
# ============================================================================


async def _format_concept_search_results(
    concept: str,
    results: list[dict[str, Any]],
    include_files: bool,
) -> str:
    """Format concept search results."""
    lines = [
        f"🧠 Searching for concept: '{concept}'",
        "=" * 50,
    ]

    if not results:
        lines.extend(
            [
                "🔍 No conversations found about this concept",
                "💡 Try related terms or broader concepts",
            ]
        )
        return "\n".join(lines)

    lines.append(f"📈 Found {len(results)} related conversations:")

    for i, result in enumerate(results, 1):
        lines.append(
            f"\n{i}. 📝 {ToolMessages.truncate_text(result['content'], 250)}",
        )
        if result.get("project"):
            lines.append(f"   📁 Project: {result['project']}")
        if result.get("score") is not None:
            lines.append(f"   ⭐ Relevance: {_format_score(result['score'])}")
        if result.get("timestamp"):
            lines.append(f"   📅 Date: {result['timestamp']}")

        if include_files and result.get("files"):
            files = result["files"][:3]
            if files:
                lines.append(f"   📄 Files: {', '.join(files)}")

    return "\n".join(lines)


async def _search_by_concept_operation(
    db: ReflectionDatabaseAdapter,
    concept: str,
    include_files: bool,
    limit: int,
    project: str | None,
) -> str:
    """Execute concept search operation."""
    results = await db.search_conversations(
        query=concept,
        project=project,
        limit=limit,
    )
    return await _format_concept_search_results(concept, results, include_files)


async def _search_by_concept_impl(
    concept: str,
    include_files: bool = True,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Implementation for search_by_concept tool."""
    if not _check_reflection_tools_available():
        return "Reflection tools not available. Install dependencies: uv sync --extra embeddings"

    try:
        db = await _get_reflection_database()
        return await _search_by_concept_operation(
            db, concept, include_files, limit, project
        )
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available("Search by concept", str(e))
    except Exception as e:
        _get_logger().exception(f"Concept search error: {e}")
        return f"Concept search error: {e}"


# ============================================================================
# Reflection Stats Tool
# ============================================================================


def _format_stats_new(stats: dict[str, t.Any]) -> list[str]:
    """Format statistics in new format (conversations_count, reflections_count)."""
    conv_count = stats.get("conversations_count", 0)
    refl_count = stats.get("reflections_count", 0)
    provider = stats.get("embedding_provider", "unknown")

    return [
        f"📈 Total conversations: {conv_count}",
        f"💭 Total reflections: {refl_count}",
        f"🔧 Embedding provider: {provider}",
        f"\n🏥 Database health: {'✅ Healthy' if (conv_count + refl_count) > 0 else '⚠️ Empty'}",
    ]


def _format_new_stats(stats: dict[str, t.Any]) -> list[str]:
    """Backward-compatible alias for _format_stats_new."""
    return _format_stats_new(stats)


def _format_stats_old(stats: dict[str, t.Any]) -> list[str]:
    """Format statistics in old/test format (total_reflections, projects, date_range)."""
    output = [
        f"📈 Total reflections: {stats.get('total_reflections', 0)}",
        f"📁 Projects: {stats.get('projects', 0)}",
    ]

    # Add date range if present
    date_range = stats.get("date_range")
    if isinstance(date_range, dict):
        output.append(
            f"📅 Date range: {date_range.get('start')} to {date_range.get('end')}"
        )

    # Add recent activity if present
    recent_activity = stats.get("recent_activity", [])
    if recent_activity:
        output.append("\n🕐 Recent activity:")
        output.extend([f"   • {activity}" for activity in recent_activity[:5]])

    # Database health
    is_healthy = stats.get("total_reflections", 0) > 0
    output.append(f"\n🏥 Database health: {'✅ Healthy' if is_healthy else '⚠️ Empty'}")

    return output


def _format_old_stats(stats: dict[str, t.Any]) -> list[str]:
    """Backward-compatible alias for _format_stats_old."""
    return _format_stats_old(stats)


async def _reflection_stats_operation(db: ReflectionDatabaseAdapter) -> str:
    """Execute reflection stats operation."""
    stats = await db.get_stats()

    lines = ["📊 Reflection Database Statistics", "=" * 40]

    if stats and "error" not in stats:
        # Format based on stat structure
        if "conversations_count" in stats:
            lines.extend(_format_stats_new(stats))
        else:
            lines.extend(_format_stats_old(stats))
    else:
        lines.extend(
            [
                "📊 No statistics available",
                "💡 Database may be empty or inaccessible",
            ]
        )

    return "\n".join(lines)


async def _reflection_stats_impl() -> str:
    """Implementation for reflection_stats tool."""
    if not _check_reflection_tools_available():
        return "Reflection tools not available. Install dependencies: uv sync --extra embeddings"

    async def operation(db: ReflectionDatabaseAdapter) -> str:
        return await _reflection_stats_operation(db)

    return await _execute_simple_database_tool(operation, "Reflection stats")


# ============================================================================
# Reset Database Tool
# ============================================================================


async def _close_db_connection(conn: t.Any) -> None:
    """Close database connection, handling both async and sync cases."""
    close_method = getattr(conn, "close", None)
    if not callable(close_method):
        return

    result = close_method()
    if asyncio.iscoroutine(result):
        await result


async def _close_db_object(db_obj: t.Any) -> None:
    """Close database object using async or sync close method."""
    # Try async close first
    aclose_method = getattr(db_obj, "aclose", None)
    if callable(aclose_method):
        result = aclose_method()
        if asyncio.iscoroutine(result):
            await result
        return

    # Fallback to sync close
    close_method = getattr(db_obj, "close", None)
    if callable(close_method):
        close_method()


async def _close_reflection_db_safely(db_obj: t.Any) -> None:
    """Safely close reflection database and its connection.

    Handles both legacy and adapter-style DB objects.
    """
    # Close connection if it exists (legacy style)
    conn = getattr(db_obj, "conn", None)
    if conn:
        await _close_db_connection(conn)

    # Close the database object itself
    await _close_db_object(db_obj)


async def _reset_reflection_database_impl() -> str:
    """Implementation for reset_reflection_database tool."""
    if not _check_reflection_tools_available():
        return "Reflection tools not available. Install dependencies: uv sync --extra embeddings"

    global _reflection_db
    try:
        if _reflection_db:
            await _close_reflection_db_safely(_reflection_db)

        _reflection_db = None
        await _get_reflection_database()

        lines = [
            "🔄 Reflection database connection reset",
            "✅ New connection established successfully",
            "💡 Database locks should be resolved",
        ]
        return "\n".join(lines)

    except Exception as e:
        return ToolMessages.operation_failed("Reset database", e)


# ============================================================================
# MCP Tool Registration
# ============================================================================


def register_memory_tools(mcp_server: Any) -> None:
    """Register all memory management tools with the MCP server."""

    @mcp_server.tool()  # type: ignore[misc]
    async def store_reflection(content: str, tags: list[str] | None = None) -> str:
        """Store an important insight or reflection for future reference."""
        return await _store_reflection_impl(content, tags)

    @mcp_server.tool()  # type: ignore[misc]
    async def quick_search(
        query: str,
        min_score: float = 0.7,
        project: str | None = None,
    ) -> str:
        """Quick search that returns only the count and top result for fast overview."""
        return await _quick_search_impl(query, min_score, project)

    @mcp_server.tool()  # type: ignore[misc]
    async def search_summary(
        query: str,
        limit: int = 10,
        project: str | None = None,
        min_score: float = 0.7,
    ) -> str:
        """Get aggregated insights from search results without individual result details."""
        return await _search_summary_impl(query, min_score, project)

    @mcp_server.tool()  # type: ignore[misc]
    async def search_by_file(
        file_path: str,
        limit: int = 10,
        project: str | None = None,
        min_score: float = 0.7,
    ) -> str:
        """Search for conversations that analyzed a specific file."""
        return await _search_by_file_impl(file_path, limit, project)

    @mcp_server.tool()  # type: ignore[misc]
    async def search_by_concept(
        concept: str,
        include_files: bool = True,
        limit: int = 10,
        project: str | None = None,
        min_score: float = 0.7,
    ) -> str:
        """Search for conversations about a specific development concept."""
        return await _search_by_concept_impl(concept, include_files, limit, project)

    @mcp_server.tool()  # type: ignore[misc]
    async def reflection_stats(project: str | None = None) -> str:
        """Get statistics about the reflection database."""
        return await _reflection_stats_impl()

    @mcp_server.tool()  # type: ignore[misc]
    async def reset_reflection_database() -> str:
        """Reset the reflection database connection to fix lock issues."""
        return await _reset_reflection_database_impl()
