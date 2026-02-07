#!/usr/bin/env python3
"""Tool wrapper utilities for MCP tools.

This module provides high-level wrappers that combine error handling, database resolution,
and message formatting to eliminate repetitive patterns in tool implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from session_buddy.utils.database_tools import (
    require_reflection_database,
)
from session_buddy.utils.error_management import (
    DatabaseUnavailableError,
    ValidationError,
    _get_logger,
)
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

T = TypeVar("T")


async def execute_database_tool(
    operation: Callable[[ReflectionDatabaseAdapter], Awaitable[T]],
    formatter: Callable[[T], str],
    operation_name: str,
    validator: Callable[[], None] | None = None,
) -> str:
    """Generic wrapper for database-dependent tools.

    This is the most comprehensive wrapper that combines:
    - Input validation
    - Database resolution
    - Operation execution
    - Result formatting
    - Error handling

    Eliminates the common pattern of:
    1. Validate inputs
    2. Get database
    3. Check if available
    4. Execute operation
    5. Format result
    6. Handle errors

    Args:
        operation: Async function that takes database and returns result
        formatter: Function to format the result as string
        operation_name: Name of operation for error messages
        validator: Optional function to validate inputs (raises ValidationError)

    Returns:
        Formatted string result or error message

    Example:
        >>> async def search_op(db):
        ...     return await db.search_reflections("test")
        >>> def format_results(results):
        ...     return f"Found {len(results)} results"
        >>> result = await execute_database_tool(
        ...     search_op, format_results, "Search reflections"
        ... )

    """
    try:
        # 1. Validate inputs if validator provided
        if validator:
            validator()

        # 2. Get database
        db = await require_reflection_database()

        # 3. Execute operation
        result = await operation(db)

        # 4. Format result
        return formatter(result)

    except ValidationError as e:
        return ToolMessages.validation_error(operation_name, str(e))
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available(operation_name, str(e))
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


async def execute_simple_database_tool(
    operation: Callable[[ReflectionDatabaseAdapter], Awaitable[str]],
    operation_name: str,
) -> str:
    """Simplified wrapper for database tools that return strings.

    Use this when your operation already returns a formatted string.
    Simpler than execute_database_tool when you don't need a separate formatter.

    Args:
        operation: Async function that takes database and returns string result
        operation_name: Name of operation for error messages

    Returns:
        String result from operation or error message

    Example:
        >>> async def search_op(db):
        ...     results = await db.search_reflections("test")
        ...     return f"Found {len(results)} results"
        >>> result = await execute_simple_database_tool(search_op, "Search")

    """
    try:
        db = await require_reflection_database()
        return await operation(db)
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available(operation_name, str(e))
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


async def execute_database_tool_with_dict(
    operation: Callable[[ReflectionDatabaseAdapter], Awaitable[dict[str, Any]]],
    operation_name: str,
    validator: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Wrapper for database tools that return structured dictionaries.

    Use this for tools that need to return structured data (success/error/data).

    Args:
        operation: Async function that takes database and returns dict
        operation_name: Name of operation for error messages
        validator: Optional function to validate inputs

    Returns:
        Dictionary with success/error fields

    Example:
        >>> async def search_op(db):
        ...     results = await db.search_reflections("test")
        ...     return {"results": results, "count": len(results)}
        >>> result = await execute_database_tool_with_dict(search_op, "Search")
        >>> if result.get("success"):
        ...     print(result["data"]["count"])

    """
    try:
        if validator:
            validator()

        db = await require_reflection_database()
        data = await operation(db)

        return {"success": True, "data": data}

    except ValidationError as e:
        return {
            "success": False,
            "error": f"{operation_name} validation failed: {e!s}",
        }
    except DatabaseUnavailableError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return {"success": False, "error": f"{operation_name} failed: {e!s}"}


async def execute_no_database_tool(
    operation: Callable[..., Awaitable[T]],
    formatter: Callable[[T], str],
    operation_name: str,
    *args: Any,
    **kwargs: Any,
) -> str:
    """Wrapper for tools that don't need database access.

    Provides error handling and logging for operations that don't require
    database connectivity.

    Args:
        operation: Async function to execute
        formatter: Function to format result as string
        operation_name: Name of operation for error messages
        *args: Arguments to pass to operation
        **kwargs: Keyword arguments to pass to operation

    Returns:
        Formatted string result or error message

    Example:
        >>> async def validate_config():
        ...     return {"valid": True, "version": "1.0"}
        >>> def format_config(data):
        ...     return f"Config valid: {data['version']}"
        >>> result = await execute_no_database_tool(
        ...     validate_config, format_config, "Validate configuration"
        ... )

    """
    try:
        result = await operation(*args, **kwargs)
        return formatter(result)
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


def _validate_required_field(key: str, value: Any) -> None:
    """Validate a required field."""
    from session_buddy.utils.error_management import validate_required

    field_name = key[9:]  # Remove "required_" prefix
    validate_required(value, field_name)


def _validate_type_field(key: str, value: Any) -> None:
    """Validate a type field."""
    from session_buddy.utils.error_management import validate_type

    parts = key.split("_")
    if len(parts) < 3:
        return

    field_name = "_".join(parts[1:-1])
    expected_type_name = parts[-1]
    type_map = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
    }
    expected_type = type_map.get(expected_type_name)

    if expected_type and isinstance(value, tuple) and len(value) == 2:
        validate_type(value[0], expected_type, field_name)


def _validate_range_field(key: str, value: Any) -> None:
    """Validate a range field."""
    from session_buddy.utils.error_management import validate_range

    field_name = key[6:]  # Remove "range_" prefix
    if isinstance(value, tuple) and len(value) == 3:
        validate_range(value[0], value[1], value[2], field_name)


def create_validator(**validations: Any) -> Callable[[], None]:
    """Create a validator function from validation rules.

    Helper to create validator functions for use with execute_database_tool.

    Args:
        **validations: Validation rules as keyword arguments
            - required_<name>: Value that must be non-empty
            - type_<name>_<type>: (value, type) tuple to validate type
            - range_<name>: (value, min, max) tuple to validate range

    Returns:
        Validator function that raises ValidationError if validation fails

    Example:
        >>> validator = create_validator(
        ...     required_query="",
        ...     type_limit_int=(limit, int),
        ...     range_limit=(limit, 1, 100),
        ... )
        >>> validator()  # Raises ValidationError if invalid

    """

    def validator() -> None:
        for key, value in validations.items():
            if key.startswith("required_"):
                _validate_required_field(key, value)
            elif key.startswith("type_"):
                _validate_type_field(key, value)
            elif key.startswith("range_"):
                _validate_range_field(key, value)

    return validator


def format_reflection_result(
    success: bool,
    content: str,
    tags: list[str] | None = None,
    timestamp: str | None = None,
) -> str:
    """Format a reflection storage result consistently.

    Args:
        success: Whether the operation succeeded
        content: Content that was stored
        tags: Tags that were applied
        timestamp: When it was stored

    Returns:
        Formatted result message

    Example:
        >>> format_reflection_result(
        ...     True,
        ...     "Important insight",
        ...     ["learning", "bug-fix"],
        ...     "2025-01-12 14:30:00",
        ... )

    """
    if not success:
        return ToolMessages.operation_failed("Store reflection", "Operation failed")

    lines = ["💾 Reflection stored successfully!"]
    lines.append(f"📝 Content: {ToolMessages.truncate_text(content, 100)}")

    if tags:
        lines.append(f"🏷️ Tags: {', '.join(tags)}")

    if timestamp:
        lines.append(f"📅 Stored: {timestamp}")

    return "\n".join(lines)


def format_search_results(
    results: list[dict[str, Any]],
    query: str,
    show_details: bool = True,
    max_results: int = 10,
) -> str:
    """Format search results consistently.

    Args:
        results: List of search result dictionaries
        query: Original search query
        show_details: Whether to show result details
        max_results: Maximum number of results to show

    Returns:
        Formatted search results

    Example:
        >>> results = [{"content": "test", "score": 0.95}]
        >>> format_search_results(results, "test query")

    """
    if not results:
        return ToolMessages.empty_results(
            f'Search for "{query}"', "Try different search terms"
        )

    count = len(results)
    lines = [
        f'🔍 Found {ToolMessages.format_count(count, "result")} for "{query}"',
    ]

    if show_details:
        display_count = min(count, max_results)
        for i, result in enumerate(results[:display_count], 1):
            lines.append(
                f"\n{i}. {ToolMessages.truncate_text(result.get('content', ''), 80)}"
            )
            if "score" in result:
                lines.append(f"   Relevance: {result['score']:.2f}")
            if "timestamp" in result:
                lines.append(f"   Time: {result['timestamp']}")

        if count > max_results:
            lines.append(f"\n... and {count - max_results} more results")

    return "\n".join(lines)
