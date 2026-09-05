#!/usr/bin/env python3
# ruff: noqa: EXE001
"""Message formatting utilities for MCP tools.

This module provides consistent message formatting across all tool implementations,
eliminating duplication and ensuring uniform user experience.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from session_buddy.utils.time import utc_now


class ToolMessages:
    """Centralized tool message formatting.

    This class provides static methods for formatting common tool messages
    with consistent styling and structure.
    """

    @staticmethod
    def not_available(feature: str, install_hint: str = "") -> str:
        """Format feature unavailable message.

        Args:
            feature: Name of the unavailable feature
            install_hint: Optional installation instructions

        Returns:
            Formatted error message

        Example:
            >>> ToolMessages.not_available("Database", "uv sync --extra embeddings")
            '❌ Database not available. Install: uv sync --extra embeddings'

        """
        msg = f"❌ {feature} not available"
        if install_hint:
            if not install_hint.startswith("Install"):
                msg += f". Install: {install_hint}"
            else:
                msg += f". {install_hint}"
        return msg

    @staticmethod
    def operation_failed(operation: str, error: Exception | str) -> str:
        """Format operation failure message.

        Args:
            operation: Name of the failed operation
            error: Exception or error message

        Returns:
            Formatted error message

        Example:
            >>> ToolMessages.operation_failed("Search", ValueError("Bad input"))
            '❌ Search failed: Bad input'

        """
        error_str = str(error)
        # Remove "Exception: " prefix if present
        if ": " in error_str and error_str.split(": ", maxsplit=1)[0].endswith("Error"):
            error_str = ": ".join(error_str.split(": ")[1:])
        return f"❌ {operation} failed: {error_str}"

    @staticmethod
    def success(message: str, details: dict[str, Any] | None = None) -> str:
        """Format success message with optional details.

        Args:
            message: Main success message
            details: Optional dictionary of details to display

        Returns:
            Formatted success message with details

        Example:
            >>> ToolMessages.success("Stored", {"items": 5, "time": "1.2s"})
            '✅ Stored
              • items: 5
              • time: 1.2s'

        """
        lines = [f"✅ {message}"]
        if details:
            for key, value in details.items():
                lines.append(f"  • {key}: {value}")
        return "\n".join(lines)

    @staticmethod
    def validation_error(field: str, message: str) -> str:
        """Format input validation error.

        Args:
            field: Name of the invalid field
            message: Validation error description

        Returns:
            Formatted validation error

        Example:
            >>> ToolMessages.validation_error("email", "Invalid format")
            '❌ Validation error: email - Invalid format'

        """
        return f"❌ Validation error: {field} - {message}"

    @staticmethod
    def empty_results(operation: str, suggestion: str = "") -> str:
        """Format message for empty results.

        Args:
            operation: Operation that returned no results
            suggestion: Optional suggestion for the user

        Returns:
            Formatted empty results message

        Example:
            >>> ToolMessages.empty_results("Search", "Try broader terms")
            'i️ No results found for Search. Try broader terms'

        """
        msg = f"ℹ️ No results found for {operation}"
        if suggestion:
            msg += f". {suggestion}"
        return msg

    @staticmethod
    def format_list_item(emoji: str, label: str, value: Any) -> str:
        """Format a single list item with emoji and label.

        Args:
            emoji: Emoji to use for the item
            label: Label for the item
            value: Value to display

        Returns:
            Formatted list item

        Example:
            >>> ToolMessages.format_list_item("📝", "Content", "Hello world")
            '📝 Content: Hello world'

        """
        return f"{emoji} {label}: {value}"

    @staticmethod
    def format_timestamp(dt: datetime | None = None) -> str:
        """Format a timestamp consistently.

        Args:
            dt: Datetime to format (defaults to now)

        Returns:
            Formatted timestamp string

        Example:
            >>> ToolMessages.format_timestamp()
            '2025-01-12 14:30:45'

        """
        if dt is None:
            dt = utc_now()
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def format_count(count: int, singular: str, plural: str | None = None) -> str:
        """Format a count with appropriate singular/plural form.

        Args:
            count: Number to format
            singular: Singular form of the noun
            plural: Plural form (defaults to singular + 's')

        Returns:
            Formatted count string

        Example:
            >>> ToolMessages.format_count(1, "result")
            '1 result'
            >>> ToolMessages.format_count(5, "match", "matches")
            '5 matches'

        """
        if plural is None:
            plural = f"{singular}s"
        word = singular if count == 1 else plural
        return f"{count} {word}"

    @staticmethod
    def format_progress(current: int, total: int, operation: str = "") -> str:
        """Format a progress indicator.

        Args:
            current: Current progress
            total: Total items
            operation: Optional operation description

        Returns:
            Formatted progress string

        Example:
            >>> ToolMessages.format_progress(5, 10, "Processing")
            'Processing: 5/10 (50%)'

        """
        percentage = int((current / total) * 100) if total > 0 else 0
        base = f"{current}/{total} ({percentage}%)"
        if operation:
            return f"{operation}: {base}"
        return base

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format a duration in seconds to human-readable form.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string

        Example:
            >>> ToolMessages.format_duration(65.5)
            '1m 5.5s'
            >>> ToolMessages.format_duration(3.2)
            '3.2s'

        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds:.1f}s"

    @staticmethod
    def format_bytes(bytes_count: int) -> str:
        """Format byte count to human-readable form.

        Args:
            bytes_count: Number of bytes

        Returns:
            Formatted byte string with appropriate unit

        Example:
            >>> ToolMessages.format_bytes(1500)
            '1.5 KB'
            >>> ToolMessages.format_bytes(1_500_000)
            '1.4 MB'

        """
        bytes_float = float(bytes_count)
        for unit in ("B", "KB", "MB", "GB"):
            if bytes_float < 1024.0:
                return f"{bytes_float:.1f} {unit}"
            bytes_float /= 1024.0
        return f"{bytes_float:.1f} TB"

    @staticmethod
    def format_result_summary(
        results: list[Any],
        operation: str,
        show_count: bool = True,
        max_display: int = 5,
    ) -> str:
        """Format a summary of results from an operation.

        Args:
            results: List of results
            operation: Operation that produced results
            show_count: Whether to show result count
            max_display: Maximum number of results to show details for

        Returns:
            Formatted result summary

        Example:
            >>> results = ["a", "b", "c"]
            >>> ToolMessages.format_result_summary(results, "Search")
            '✅ Search complete: 3 results'

        """
        count = len(results)

        if count == 0:
            return ToolMessages.empty_results(operation)

        lines = []
        if show_count:
            count_str = ToolMessages.format_count(count, "result")
            lines.append(f"✅ {operation} complete: {count_str}")
        else:
            lines.append(f"✅ {operation} complete")

        # Show summary of first few results if they're simple types.
        # Use a manual counter so non-primitive entries (e.g. dicts) don't
        # leave gaps in the displayed numbering.
        if max_display > 0 and results:
            sample = results[:max_display]
            i = 0
            for result in sample:
                if isinstance(result, (str, int, float, bool)):
                    i += 1
                    lines.append(f"  {i}. {result}")

        if count > max_display:
            lines.append(f"  ... and {count - max_display} more")

        return "\n".join(lines)

    @staticmethod
    def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
        """Truncate text to maximum length with suffix.

        Args:
            text: Text to truncate
            max_length: Maximum length before truncation
            suffix: Suffix to add when truncated

        Returns:
            Truncated text with suffix if needed

        Example:
            >>> ToolMessages.truncate_text("Hello world this is long", 15)
            'Hello world ...'

        """
        if len(text) <= max_length:
            return text
        return text[: max_length - len(suffix)] + suffix
