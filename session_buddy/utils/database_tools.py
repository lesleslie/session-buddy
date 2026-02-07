#!/usr/bin/env python3
"""Database resolution utilities for MCP tools.

This module provides reusable database resolution and operation patterns to eliminate
code duplication in tool implementations that depend on databases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from session_buddy.utils.error_management import DatabaseUnavailableError, _get_logger
from session_buddy.utils.instance_managers import (
    get_reflection_database as resolve_reflection_database,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

T = TypeVar("T")


async def require_reflection_database() -> ReflectionDatabaseAdapter:
    """Get reflection database or raise with helpful error.

    This utility consolidates the common pattern of:
    1. Resolving the database
    2. Checking if it's None
    3. Returning appropriate error message

    Returns:
        ReflectionDatabaseAdapter instance

    Raises:
        DatabaseUnavailableError: If database is not available

    Example:
        >>> db = await require_reflection_database()
        >>> # Use db knowing it's not None

    """
    db = await resolve_reflection_database()
    if not db:
        msg = "Reflection database not available. Install dependencies: uv sync --extra embeddings"
        raise DatabaseUnavailableError(msg)
    return db


async def safe_database_operation[T](
    operation: Callable[[ReflectionDatabaseAdapter], Awaitable[T]],
    error_message: str = "Database operation",
) -> T:
    """Execute database operation with automatic database resolution and error handling.

    This utility wraps database operations to eliminate the repetitive pattern of:
    1. Get database
    2. Check if available
    3. Execute operation
    4. Handle errors

    Args:
        operation: Async function that takes database and returns result
        error_message: Description of operation for error messages

    Returns:
        Result from the operation

    Raises:
        DatabaseUnavailableError: If database is not available
        Exception: Any exception from the operation (will be logged)

    Example:
        >>> async def my_query(db):
        ...     return await db.search_reflections("test")
        >>> results = await safe_database_operation(my_query, "Search reflections")

    """
    try:
        db = await require_reflection_database()
        return await operation(db)
    except DatabaseUnavailableError:
        # Re-raise database unavailable - caller should handle
        raise
    except Exception as e:
        _get_logger().exception(f"Error in {error_message}: {e}")
        raise


async def safe_database_operation_with_message[T](
    operation: Callable[[ReflectionDatabaseAdapter], Awaitable[T]],
    error_message: str = "Database operation",
) -> str:
    """Execute database operation and return formatted string result.

    Similar to safe_database_operation but catches all exceptions and returns
    error messages as strings instead of raising.

    Args:
        operation: Async function that takes database and returns result
        error_message: Description of operation for error messages

    Returns:
        String result from operation or error message

    Example:
        >>> async def my_query(db):
        ...     result = await db.search_reflections("test")
        ...     return f"Found {len(result)} results"
        >>> message = await safe_database_operation_with_message(my_query)
        >>> print(message)

    """
    try:
        db = await require_reflection_database()
        result = await operation(db)
        # If operation returns a string, return it directly
        if isinstance(result, str):
            return result
        # Otherwise, let caller handle the result
        return str(result)
    except DatabaseUnavailableError as e:
        return f"❌ {e!s}"
    except Exception as e:
        _get_logger().exception(f"Error in {error_message}: {e}")
        return f"❌ {error_message} failed: {e!s}"


async def batch_database_operation(
    items: list[T],
    operation: Callable[[ReflectionDatabaseAdapter, T], Awaitable[Any]],
    batch_size: int = 100,
) -> list[Any]:
    """Execute database operation in batches for better performance.

    Useful for bulk operations that need to be chunked to avoid overwhelming
    the database or memory.

    Args:
        items: List of items to process
        operation: Async function that takes (database, item) and returns result
        batch_size: Number of items to process per batch

    Returns:
        List of results in same order as input items

    Raises:
        DatabaseUnavailableError: If database is not available

    Example:
        >>> async def store_item(db, item):
        ...     return await db.store_reflection(item["content"], item["tags"])
        >>> items = [{"content": "a", "tags": ["t1"]}, ...]
        >>> results = await batch_database_operation(items, store_item)

    """
    db = await require_reflection_database()

    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        batch_results = []

        for item in batch:
            try:
                result = await operation(db, item)
                batch_results.append(result)
            except Exception as e:
                _get_logger().exception(f"Error processing item {item}: {e}")
                batch_results.append(None)

        results.extend(batch_results)

    return results


def check_database_available() -> bool:
    """Check if reflection database dependencies are available.

    This is a synchronous check that can be used before attempting async operations.

    Returns:
        True if database is available, False otherwise

    Example:
        >>> if check_database_available():
        ...     result = await some_database_operation()
        ... else:
        ...     print("Database not available")

    """
    try:
        import importlib.util

        spec = importlib.util.find_spec("session_buddy.reflection_tools")
        if spec is None:
            return False

        # Check for required dependencies
        spec = importlib.util.find_spec("duckdb")
        return spec is not None
    except ImportError:
        return False


async def get_database_stats() -> dict[str, Any]:
    """Get statistics about database health and availability.

    Returns:
        Dictionary with database statistics

    Example:
        >>> stats = await get_database_stats()
        >>> print(f"Total reflections: {stats['total_reflections']}")

    """
    try:
        db = await require_reflection_database()
        stats = await db.get_stats()
        stats["available"] = True
        return stats
    except DatabaseUnavailableError:
        return {
            "available": False,
            "error": "Database not available",
            "total_reflections": 0,
            "total_conversations": 0,
        }
    except Exception as e:
        _get_logger().exception(f"Error getting database stats: {e}")
        return {
            "available": False,
            "error": str(e),
            "total_reflections": 0,
            "total_conversations": 0,
        }
