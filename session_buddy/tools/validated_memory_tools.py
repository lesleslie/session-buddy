#!/usr/bin/env python3
"""Example integration of parameter validation models with MCP tools.

This module demonstrates how to integrate Pydantic parameter validation
models with existing MCP tools for improved type safety and error handling.

Following crackerjack patterns:
- EVERY LINE IS A LIABILITY: Clean, focused tool implementations
- DRY: Reusable validation across all tools
- KISS: Simple integration without over-engineering

Refactored to use utility modules for reduced code duplication.
"""

from __future__ import annotations

# ============================================================================
# Helper Functions
# ============================================================================
from contextlib import suppress
from datetime import datetime
from typing import Any

from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter
from session_buddy.parameter_models import (
    ConceptSearchParams,
    FileSearchParams,
    ReflectionStoreParams,
    SearchQueryParams,
    validate_mcp_params,
)
from session_buddy.reflection_tools import ReflectionDatabase
from session_buddy.utils.error_handlers import ValidationError, _get_logger

# Define type alias for backward compatibility during migration
# NOTE: With 'from __future__ import annotations', we use the actual types, not strings
ReflectionDatabaseType = ReflectionDatabaseAdapter | ReflectionDatabase


async def _get_reflection_database() -> ReflectionDatabaseType:
    """Get reflection database instance with cached availability semantics."""
    db = await _get_reflection_database_async()
    if db is None:
        msg = "Reflection tools not available"
        raise ImportError(msg)
    return db


def _format_result_item(res: dict[str, Any], index: int) -> list[str]:
    """Format a single search result item."""
    lines = [f"\n{index}. 📝 {res['content'][:200]}..."]
    if res.get("project"):
        lines.append(f"   📁 Project: {res['project']}")
    if res.get("score") is not None:
        lines.append(f"   ⭐ Relevance: {res['score']:.2f}")
    if res.get("timestamp"):
        lines.append(f"   📅 Date: {res['timestamp']}")
    return lines


def _format_search_results(results: list[dict[str, Any]]) -> list[str]:
    """Format search results with common structure."""
    if not results:
        return [
            "🔍 No conversations found about this file",
            "💡 The file might not have been discussed in previous sessions",
        ]

    lines = [f"📈 Found {len(results)} relevant conversations:"]
    for i, res in enumerate(results, 1):
        lines.extend(_format_result_item(res, i))
    return lines


def _format_concept_results(
    results: list[dict[str, Any]], include_files: bool
) -> list[str]:
    """Format concept search results with optional file information."""
    if not results:
        return [
            "🔍 No conversations found about this concept",
            "💡 Try related terms or broader concepts",
        ]

    lines = [f"📈 Found {len(results)} related conversations:"]
    for i, res in enumerate(results, 1):
        item_lines = [f"\n{i}. 📝 {res['content'][:250]}..."]
        if res.get("project"):
            item_lines.append(f"   📁 Project: {res['project']}")
        if res.get("score") is not None:
            item_lines.append(f"   ⭐ Relevance: {res['score']:.2f}")
        if res.get("timestamp"):
            item_lines.append(f"   📅 Date: {res['timestamp']}")
        if include_files and res.get("files"):
            files = res["files"][:3]
            if files:
                item_lines.append(f"   📄 Files: {', '.join(files)}")
        lines.extend(item_lines)
    return lines


# ============================================================================
# Validated Tool Implementations
# ============================================================================


def _validate_reflection_params(**params: Any) -> ReflectionStoreParams | str:
    """Validate reflection store parameters.

    Args:
        **params: Raw parameters from MCP call

    Returns:
        Validated params object or error message string

    """
    from typing import cast

    try:
        validated = validate_mcp_params(ReflectionStoreParams, **params)
        if not validated.is_valid:
            return f"Parameter validation error: {validated.errors}"
        return cast("ReflectionStoreParams", validated.params)
    except ValidationError as e:
        return f"Parameter validation error: {e}"


async def _execute_store_reflection(
    params_obj: ReflectionStoreParams, db: Any
) -> dict[str, Any]:
    """Execute the reflection storage operation.

    Args:
        params_obj: Validated parameters
        db: Database instance

    Returns:
        Operation result dictionary

    """
    reflection_id = await db.store_reflection(
        params_obj.content,
        tags=params_obj.tags or [],
    )

    return {
        "success": reflection_id not in (None, False),
        "id": reflection_id,
        "content": params_obj.content,
        "tags": params_obj.tags or [],
        "timestamp": datetime.now().isoformat(),
    }


def _format_reflection_result(result: dict[str, Any]) -> str:
    """Format reflection storage result for user display.

    Args:
        result: Operation result dictionary

    Returns:
        Formatted string message

    """
    lines = [
        "💾 Reflection stored successfully!",
        f"🆔 ID: {result['id']}",
        f"📝 Content: {result['content'][:100]}...",
    ]
    if result["tags"]:
        lines.append(f"🏷️  Tags: {', '.join(result['tags'])}")
    lines.append(f"📅 Stored: {result['timestamp']}")

    _get_logger().info(
        f"Validated reflection stored | Context: {{'reflection_id': '{result['id']}', 'content_length': {len(result['content'])}, 'tags_count': {len(result['tags']) if result['tags'] else 0}}}"
    )
    return "\n".join(lines)


async def _store_reflection_validated_impl(**params: Any) -> str:
    """Implementation for store_reflection tool with parameter validation."""
    # Check if tools are available
    if not _check_reflection_tools_available():
        return "❌ Reflection tools not available. Install with: `uv sync --extra embeddings`\n💡 This enables conversation memory and semantic search capabilities."

    # Validate parameters
    params_validation = _validate_reflection_params(**params)
    if isinstance(params_validation, str):
        return params_validation
    params_obj = params_validation

    try:
        # Get database instance
        db = await _get_reflection_database_async()
        if not db:
            return "❌ Failed to connect to reflection database"

        # Execute storage operation
        result = await _execute_store_reflection(params_obj, db)
        if not result["success"]:
            error_msg = f"Failed to store reflection: {result['id']}"
            _get_logger().error(error_msg)
            return error_msg

        return _format_reflection_result(result)

    except ValidationError as e:
        return f"Parameter validation failed: {e}"
    except ImportError:
        error_msg = "Failed to connect to reflection database: Import error"
        _get_logger().error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Failed to store reflection: {e}"
        _get_logger().error(error_msg)
        return error_msg


async def _quick_search_validated_impl(**params: Any) -> str:
    """Implementation for quick_search tool with parameter validation."""
    from typing import cast

    # Validate parameters
    try:
        validated = validate_mcp_params(SearchQueryParams, **params)
        if not validated.is_valid:
            return f"Parameter validation error: {validated.errors}"
        params_obj = cast("SearchQueryParams", validated.params)
    except ValidationError as e:
        return f"Parameter validation error: {e}"

    async def operation(db: Any) -> dict[str, Any]:
        """Quick search operation."""
        results = await db.search_reflections(
            params_obj.query,
            limit=1,
            min_score=params_obj.min_score,
        )

        return {
            "query": params_obj.query,
            "results": results,
            "total_count": len(results),
        }

    def formatter(result: dict[str, Any]) -> str:
        """Format quick search results."""
        lines = [f"🔍 Quick search for: '{result['query']}'"]

        if not result["results"]:
            lines.extend(
                [
                    "🔍 No results found",
                    "💡 Try adjusting your search terms or lowering min_score",
                ]
            )
        else:
            lines.extend(_format_top_result(result["results"][0]))

        _get_logger().info(
            f"Validated quick search executed | Context: {{'query': '{result['query']}', 'results_count': {result['total_count']}}}"
        )
        return "\n".join(lines)

    # Check if tools are available
    if not _check_reflection_tools_available():
        return "❌ Reflection tools not available. Install with: `uv sync --extra embeddings`\n💡 This enables conversation memory and semantic search capabilities."

    try:
        # Get database instance and execute operation
        db = await _get_reflection_database_async()
        if not db:
            return "❌ Failed to connect to reflection database"

        result = await operation(db)
        return formatter(result)
    except ValidationError as e:
        # Return validation errors as strings instead of raising
        return f"Parameter validation failed: {e}"
    except ImportError:
        # Handle import errors from database initialization
        error_msg = "Failed to connect to reflection database: Import error"
        _get_logger().error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Failed to perform quick search: {e}"
        _get_logger().error(error_msg)
        return error_msg


def _format_top_result(top_result: dict[str, Any]) -> list[str]:
    """Format the top search result."""
    lines = [
        "📊 Found results (showing top 1)",
        f"📝 {top_result['content'][:150]}...",
    ]
    if top_result.get("project"):
        lines.append(f"📁 Project: {top_result['project']}")
    if top_result.get("score") is not None:
        lines.append(f"⭐ Relevance: {top_result['score']:.2f}")
    if top_result.get("timestamp"):
        lines.append(f"📅 Date: {top_result['timestamp']}")

    return lines


async def _search_by_file_validated_impl(**params: Any) -> str:
    """Implementation for search_by_file tool with parameter validation."""
    from typing import cast

    # Validate parameters
    try:
        validated = validate_mcp_params(FileSearchParams, **params)
        if not validated.is_valid:
            return f"Parameter validation error: {validated.errors}"
        params_obj = cast("FileSearchParams", validated.params)
    except ValidationError as e:
        return f"Parameter validation error: {e}"

    async def operation(db: Any) -> dict[str, Any]:
        """File search operation."""
        results = await db.search_reflections(
            params_obj.file_path,
            limit=params_obj.limit,
            min_score=params_obj.min_score,
        )

        return {
            "file_path": params_obj.file_path,
            "results": results,
        }

    def formatter(result: dict[str, Any]) -> str:
        """Format file search results."""
        file_path = result["file_path"]
        results = result["results"]

        lines = [f"📁 Searching conversations about: {file_path}", "=" * 50]
        lines.extend(_format_search_results(results))

        _get_logger().info(
            f"Validated file search executed | Context: {{'file_path': '{file_path}', 'results_count': {len(results)}}}"
        )
        return "\n".join(lines)

    # Check if tools are available
    if not _check_reflection_tools_available():
        return "❌ Reflection tools not available. Install with: `uv sync --extra embeddings`\n💡 This enables conversation memory and semantic search capabilities."

    try:
        # Get database instance and execute operation
        db = await _get_reflection_database_async()
        if not db:
            return "❌ Failed to connect to reflection database"

        result = await operation(db)
        return formatter(result)
    except ValidationError as e:
        # Return validation errors as strings instead of raising
        return f"Parameter validation failed: {e}"
    except ImportError:
        # Handle import errors from database initialization
        error_msg = "Failed to connect to reflection database: Import error"
        _get_logger().error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Failed to perform file search: {e}"
        _get_logger().error(error_msg)
        return error_msg


async def _search_by_concept_validated_impl(**params: Any) -> str:
    """Implementation for search_by_concept tool with parameter validation."""
    from typing import cast

    # Validate parameters
    try:
        validated = validate_mcp_params(ConceptSearchParams, **params)
        if not validated.is_valid:
            return f"Parameter validation error: {validated.errors}"
        params_obj = cast("ConceptSearchParams", validated.params)
    except ValidationError as e:
        return f"Parameter validation error: {e}"

    async def operation(db: Any) -> dict[str, Any]:
        """Concept search operation."""
        results = await db.search_reflections(
            params_obj.concept,
            limit=params_obj.limit,
            min_score=params_obj.min_score,
        )

        return {
            "concept": params_obj.concept,
            "include_files": params_obj.include_files,
            "results": results,
        }

    def formatter(result: dict[str, Any]) -> str:
        """Format concept search results."""
        concept = result["concept"]
        results = result["results"]

        lines = [f"🧠 Searching for concept: '{concept}'", "=" * 50]
        lines.extend(_format_concept_results(results, result["include_files"]))

        _get_logger().info(
            f"Validated concept search executed | Context: {{'concept': '{concept}', 'results_count': {len(results)}}}"
        )
        return "\n".join(lines)

    # Check if tools are available
    if not _check_reflection_tools_available():
        return "❌ Reflection tools not available. Install with: `uv sync --extra embeddings`\n💡 This enables conversation memory and semantic search capabilities."

    try:
        # Get database instance and execute operation
        db = await _get_reflection_database_async()
        if not db:
            return "❌ Failed to connect to reflection database"

        result = await operation(db)
        return formatter(result)
    except ValidationError as e:
        # Return validation errors as strings instead of raising
        return f"Parameter validation failed: {e}"
    except ImportError:
        # Handle import errors from database initialization
        error_msg = "Failed to connect to reflection database: Import error"
        _get_logger().error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Failed to perform concept search: {e}"
        _get_logger().error(error_msg)
        return error_msg


def _format_file_search_header(file_path: str) -> list[str]:
    """Format header for file search results."""
    return [
        f"📁 Searching conversations about: {file_path}",
        "=" * 50,
    ]


def _format_file_search_result(res: dict[str, Any], index: int) -> list[str]:
    """Format individual file search result."""
    lines = [
        f"{index}. 📝 {res['content'][:200]}...",
    ]

    if res.get("timestamp"):
        lines.append(f"   📅 Date: {res['timestamp']}")

    if res.get("project"):
        lines.append(f"   📁 Project: {res['project']}")

    if res.get("score") is not None:
        lines.append(f"   ⭐ Relevance: {res['score']:.2f}")

    return lines


def _format_file_search_results(results: list[dict[str, Any]], query: str) -> list[str]:
    """Format all file search results."""
    if not results:
        return [
            "No conversations found about this file",
            f"🔍 No conversations found discussing '{query}'",
            "💡 The file might not have been discussed in previous sessions",
        ]

    lines = [
        f"📁 Searching conversations about: {query}",
        "=" * 50,
        f"📈 Found {len(results)} relevant conversations:",
    ]

    for i, res in enumerate(results, 1):
        result_lines = _format_file_search_result(res, i)
        if isinstance(result_lines, list):
            lines.extend(result_lines)
        else:
            lines.append(str(result_lines))

    return lines


def _format_validated_concept_result(
    res: dict[str, Any], index: int, include_files: bool = True
) -> list[str]:
    """Format individual concept search result."""
    lines = [
        f"{index}. 🧠 Concept: {res['content'][:200]}...",
    ]

    if res.get("timestamp"):
        lines.append(f"   📅 Date: {res['timestamp']}")

    if res.get("project"):
        lines.append(f"   📁 Project: {res['project']}")

    if res.get("score") is not None:
        lines.append(f"   ⭐ Relevance: {res['score']:.2f}")

    if include_files and res.get("files"):
        files = res["files"][:5]  # Limit to 5 files
        lines.append(f"   📄 Files: {', '.join(files)}")

    return lines


# Define missing classes for backward compatibility
class ValidationExamples:
    """Placeholder class for validation examples."""

    def example_valid_calls(self) -> list[dict[str, Any]]:
        """Get examples of valid calls."""
        return [{"query": "test query", "limit": 5}]

    def example_validation_errors(self) -> list[dict[str, str]]:
        """Get examples of validation errors."""
        return [{"field": "query", "error": "Field required"}]


class MigrationGuide:
    """Placeholder class for migration guide."""

    @staticmethod
    def before_migration() -> str:
        """Get before migration instructions."""
        return "Before migrating, backup your data."

    @staticmethod
    def after_migration() -> str:
        """Get after migration instructions."""
        return "After migrating, verify your configurations."


# Global variable to cache reflection tools availability
_reflection_tools_available: bool | None = None


def _check_reflection_tools_available() -> bool:
    """Check if reflection tools are available and properly installed."""
    global _reflection_tools_available

    if _reflection_tools_available is not None:
        return _reflection_tools_available

    try:
        # Check if reflection database module can be imported
        import importlib.util

        spec = importlib.util.find_spec("session_buddy.reflection_tools")
        available = spec is not None
        _reflection_tools_available = available
        return available
    except Exception:
        _reflection_tools_available = False
        return False


async def resolve_reflection_database() -> ReflectionDatabaseType | None:
    """Resolve the reflection database instance using dependency injection or fallback."""
    # Try to get from DI container
    with suppress(Exception):
        from typing import cast

        from session_buddy.di.container import depends
        from session_buddy.reflection_tools import ReflectionDatabase

        db = depends.get_sync(ReflectionDatabase)
        if db:
            return cast("ReflectionDatabase", db)

    # Fallback - get a direct instance
    with suppress(Exception):
        from session_buddy.reflection_tools import get_reflection_database

        return await get_reflection_database()

    return None


async def _get_reflection_database_async() -> ReflectionDatabaseType | None:
    """Get reflection database instance with lazy initialization."""
    if not _check_reflection_tools_available():
        msg = "Reflection tools not available"
        raise ImportError(msg)

    try:
        db = await resolve_reflection_database()
        if db is None:
            msg = "Reflection tools not available"
            raise ImportError(msg)
        return db
    except ImportError:
        # Re-raise import errors as they indicate unavailability
        raise
    except Exception:
        # For any other exception, treat as unavailable
        msg = "Reflection tools not available"
        raise ImportError(msg)


# ============================================================================
# MCP Tool Registration
# ============================================================================


def register_validated_memory_tools(mcp_server: Any) -> None:
    """Register all validated memory tools with the MCP server.

    These tools demonstrate parameter validation using Pydantic models
    while using the same utility-based refactoring patterns as other tools.
    """

    @mcp_server.tool()  # type: ignore[misc]
    async def store_reflection_validated(**params: Any) -> str:
        """Store a reflection with validated parameters.

        This demonstrates how to integrate Pydantic parameter validation
        with MCP tools for improved type safety.
        """
        return await _store_reflection_validated_impl(**params)

    @mcp_server.tool()  # type: ignore[misc]
    async def quick_search_validated(**params: Any) -> str:
        """Quick search with validated parameters."""
        return await _quick_search_validated_impl(**params)

    @mcp_server.tool()  # type: ignore[misc]
    async def search_by_file_validated(**params: Any) -> str:
        """Search by file with validated parameters."""
        return await _search_by_file_validated_impl(**params)

    @mcp_server.tool()  # type: ignore[misc]
    async def search_by_concept_validated(**params: Any) -> str:
        """Search by concept with validated parameters."""
        return await _search_by_concept_validated_impl(**params)
