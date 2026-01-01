#!/usr/bin/env python3
"""Error handling utilities for MCP tools.

This module provides reusable error handling patterns to eliminate code duplication
across tool implementations.
"""

from __future__ import annotations

import typing as t
from typing import Any, TypeVar

if t.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


def _get_logger() -> t.Any:
    """Lazy logger resolution using standard logging."""
    import logging

    return logging.getLogger(__name__)


class ToolError(Exception):
    """Base exception for tool errors."""


class DatabaseUnavailableError(ToolError):
    """Exception raised when database is not available."""


class ValidationError(ToolError):
    """Exception raised when input validation fails."""


async def handle_tool_errors[T](
    operation: Callable[..., Awaitable[T]],
    error_prefix: str = "Operation",
    *args: Any,
    **kwargs: Any,
) -> T | str:
    """Generic error handler for tool operations.

    This utility wraps async operations with consistent error handling and logging.
    Eliminates the need for repetitive try/except blocks in tool implementations.

    Args:
        operation: Async function to execute
        error_prefix: Description of the operation for error messages
        *args: Positional arguments to pass to operation
        **kwargs: Keyword arguments to pass to operation

    Returns:
        Result from operation, or error message string on failure

    Example:
        >>> async def my_operation(x: int) -> int:
        ...     return x * 2
        >>> result = await handle_tool_errors(my_operation, "Multiplication", 5)
        >>> print(result)
        10

    """
    try:
        return await operation(*args, **kwargs)
    except DatabaseUnavailableError as e:
        # Don't log database unavailable as exception - it's expected
        return f"❌ {e!s}"
    except ValidationError as e:
        # Don't log validation errors as exceptions - they're user errors
        return f"❌ {error_prefix} validation failed: {e!s}"
    except Exception as e:
        _get_logger().exception(f"Error in {error_prefix}: {e}")
        return f"❌ {error_prefix} failed: {e!s}"


async def handle_tool_errors_with_result[T](
    operation: Callable[..., Awaitable[T]],
    error_prefix: str = "Operation",
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generic error handler that returns structured result dictionary.

    Similar to handle_tool_errors but returns a dictionary with success/error fields
    instead of a string. Useful for tools that need structured responses.

    Args:
        operation: Async function to execute
        error_prefix: Description of the operation for error messages
        *args: Positional arguments to pass to operation
        **kwargs: Keyword arguments to pass to operation

    Returns:
        Dictionary with 'success' bool and either 'data' or 'error' field

    Example:
        >>> result = await handle_tool_errors_with_result(operation, "Test")
        >>> if result["success"]:
        ...     print(result["data"])
        ... else:
        ...     print(result["error"])

    """
    try:
        data = await operation(*args, **kwargs)
        return {"success": True, "data": data}
    except DatabaseUnavailableError as e:
        return {"success": False, "error": str(e)}
    except ValidationError as e:
        return {
            "success": False,
            "error": f"{error_prefix} validation failed: {e!s}",
        }
    except Exception as e:
        _get_logger().exception(f"Error in {error_prefix}: {e}")
        return {"success": False, "error": f"{error_prefix} failed: {e!s}"}


def validate_required(value: Any, field_name: str) -> None:
    """Validate that a required field is present and non-empty.

    Args:
        value: Value to validate
        field_name: Name of the field for error messages

    Raises:
        ValidationError: If value is None, empty string, or empty collection

    """
    if value is None:
        msg = f"{field_name} is required"
        raise ValidationError(msg)

    if isinstance(value, str) and not value.strip():
        msg = f"{field_name} cannot be empty"
        raise ValidationError(msg)

    if isinstance(value, (list, dict, set, tuple)) and not value:
        msg = f"{field_name} cannot be empty"
        raise ValidationError(msg)


def validate_type(value: Any, expected_type: type, field_name: str) -> None:
    """Validate that a field has the expected type.

    Args:
        value: Value to validate
        expected_type: Expected type for the value
        field_name: Name of the field for error messages

    Raises:
        ValidationError: If value is not of the expected type

    """
    if not isinstance(value, expected_type):
        msg = (
            f"{field_name} must be {expected_type.__name__}, got {type(value).__name__}"
        )
        raise ValidationError(msg)


def validate_range(
    value: float, min_val: float, max_val: float, field_name: str
) -> None:
    """Validate that a numeric value is within a specified range.

    Args:
        value: Value to validate
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)
        field_name: Name of the field for error messages

    Raises:
        ValidationError: If value is outside the specified range

    """
    if not isinstance(value, (int, float)):
        msg = f"{field_name} must be a number"
        raise ValidationError(msg)

    if value < min_val or value > max_val:
        msg = f"{field_name} must be between {min_val} and {max_val}, got {value}"
        raise ValidationError(msg)
