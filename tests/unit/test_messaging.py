#!/usr/bin/env python3
"""Test suite for ToolMessages messaging utility.

This module tests the message formatting utilities used across MCP tools,
ensuring consistent formatting, error handling, and edge case coverage.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from session_buddy.utils.messages import ToolMessages


class TestToolMessagesBasicFormatting:
    """Test basic message formatting methods."""

    def test_not_available_without_install_hint(self):
        """Test not_available message without installation hint."""
        result = ToolMessages.not_available("FeatureName")
        assert result == "❌ FeatureName not available"

    def test_not_available_with_install_hint(self):
        """Test not_available message with installation hint."""
        result = ToolMessages.not_available("Database", "uv sync --extra embeddings")
        expected = "❌ Database not available. Install: uv sync --extra embeddings"
        assert result == expected

    def test_not_available_with_install_hint_prefix(self):
        """Test not_available when install hint already has 'Install' prefix."""
        result = ToolMessages.not_available("Feature", "Install via pip")
        expected = "❌ Feature not available. Install via pip"
        assert result == expected

    def test_operation_failed_with_exception(self):
        """Test operation_failed with Exception object."""
        error = ValueError("Invalid input value")
        result = ToolMessages.operation_failed("Search", error)
        assert result == "❌ Search failed: Invalid input value"

    def test_operation_failed_with_string_error(self):
        """Test operation_failed with string error message."""
        result = ToolMessages.operation_failed("Save", "File not found")
        assert result == "❌ Save failed: File not found"

    def test_operation_failed_strips_exception_prefix(self):
        """Test that operation_failed strips 'Exception:' prefix from errors."""
        error_msg = "ValueError: Invalid input"
        result = ToolMessages.operation_failed("Process", error_msg)
        # Should strip the "ValueError:" part
        assert result == "❌ Process failed: Invalid input"

    def test_operation_failed_non_error_exception(self):
        """Test operation_failed with MyError that also gets stripped."""
        # The implementation strips any error ending with 'Error', including 'MyError'
        error_msg = "MyError: Something went wrong"
        result = ToolMessages.operation_failed("Task", error_msg)
        # MyError ends with 'Error', so it gets stripped
        assert result == "❌ Task failed: Something went wrong"

    def test_success_without_details(self):
        """Test success message without details."""
        result = ToolMessages.success("Operation completed")
        assert result == "✅ Operation completed"

    def test_success_with_details(self):
        """Test success message with details dictionary."""
        details = {"items": 5, "time": "1.2s", "errors": 0}
        result = ToolMessages.success("Stored", details)

        lines = result.split("\n")
        assert len(lines) == 4
        assert lines[0] == "✅ Stored"
        assert "  • items: 5" in lines
        assert "  • time: 1.2s" in lines
        assert "  • errors: 0" in lines

    def test_success_with_empty_details(self):
        """Test success message with empty details dict."""
        result = ToolMessages.success("Done", {})
        assert result == "✅ Done"

    def test_validation_error(self):
        """Test validation error formatting."""
        result = ToolMessages.validation_error("email", "Invalid format")
        expected = "❌ Validation error: email - Invalid format"
        assert result == expected

    def test_empty_results_without_suggestion(self):
        """Test empty_results message without suggestion."""
        result = ToolMessages.empty_results("Search")
        assert result == "ℹ️ No results found for Search"

    def test_empty_results_with_suggestion(self):
        """Test empty_results message with suggestion."""
        result = ToolMessages.empty_results("Search", "Try broader terms")
        expected = "ℹ️ No results found for Search. Try broader terms"
        assert result == expected


class TestToolMessagesFormattingHelpers:
    """Test helper formatting methods."""

    def test_format_list_item(self):
        """Test format_list_item with emoji, label, and value."""
        result = ToolMessages.format_list_item("📝", "Content", "Hello world")
        assert result == "📝 Content: Hello world"

    def test_format_list_item_numeric_value(self):
        """Test format_list_item with numeric value."""
        result = ToolMessages.format_list_item("🔢", "Count", 42)
        assert result == "🔢 Count: 42"

    def test_format_timestamp_default(self):
        """Test format_timestamp with default (current) time."""
        result = ToolMessages.format_timestamp()
        # Should match format: YYYY-MM-DD HH:MM:SS
        assert len(result) == 19
        assert result[4] == "-"
        assert result[7] == "-"
        assert result[10] == " "
        assert result[13] == ":"
        assert result[16] == ":"

    def test_format_timestamp_specific_datetime(self):
        """Test format_timestamp with specific datetime."""
        dt = datetime(2025, 1, 15, 14, 30, 45)
        result = ToolMessages.format_timestamp(dt)
        assert result == "2025-01-15 14:30:45"

    def test_format_count_singular(self):
        """Test format_count with singular form (count=1)."""
        result = ToolMessages.format_count(1, "result")
        assert result == "1 result"

    def test_format_count_plural_default(self):
        """Test format_count with default plural (count > 1)."""
        result = ToolMessages.format_count(5, "result")
        assert result == "5 results"

    def test_format_count_plural_custom(self):
        """Test format_count with custom plural form."""
        result = ToolMessages.format_count(3, "match", "matches")
        assert result == "3 matches"

    def test_format_count_zero(self):
        """Test format_count with zero."""
        result = ToolMessages.format_count(0, "item")
        assert result == "0 items"

    def test_format_progress_without_operation(self):
        """Test format_progress without operation name."""
        result = ToolMessages.format_progress(5, 10)
        assert result == "5/10 (50%)"

    def test_format_progress_with_operation(self):
        """Test format_progress with operation name."""
        result = ToolMessages.format_progress(3, 10, "Processing")
        assert result == "Processing: 3/10 (30%)"

    def test_format_progress_zero_total(self):
        """Test format_progress with zero total (edge case)."""
        result = ToolMessages.format_progress(5, 0, "Loading")
        assert result == "Loading: 5/0 (0%)"

    def test_format_progress_complete(self):
        """Test format_progress when complete."""
        result = ToolMessages.format_progress(10, 10, "Download")
        assert result == "Download: 10/10 (100%)"

    def test_format_duration_seconds_only(self):
        """Test format_duration with seconds only."""
        result = ToolMessages.format_duration(3.2)
        assert result == "3.2s"

    def test_format_duration_minutes_and_seconds(self):
        """Test format_duration with minutes and seconds."""
        result = ToolMessages.format_duration(65.5)
        assert result == "1m 5.5s"

    def test_format_duration_hours(self):
        """Test format_duration with hours (large value)."""
        result = ToolMessages.format_duration(3665.0)
        assert result == "61m 5.0s"

    def test_format_duration_rounding(self):
        """Test format_duration rounding behavior."""
        result = ToolMessages.format_duration(59.999)
        # Implementation rounds to 1 decimal place
        assert result == "60.0s"

        result = ToolMessages.format_duration(60.001)
        assert result == "1m 0.0s"

    def test_format_bytes_bytes(self):
        """Test format_bytes with byte values."""
        result = ToolMessages.format_bytes(500)
        assert result == "500.0 B"

        result = ToolMessages.format_bytes(1023)
        assert result == "1023.0 B"

    def test_format_bytes_kilobytes(self):
        """Test format_bytes with kilobyte values."""
        result = ToolMessages.format_bytes(1500)
        assert result == "1.5 KB"

        result = ToolMessages.format_bytes(1024)
        assert result == "1.0 KB"

    def test_format_bytes_megabytes(self):
        """Test format_bytes with megabyte values."""
        result = ToolMessages.format_bytes(1_500_000)
        assert result == "1.4 MB"

        result = ToolMessages.format_bytes(1_048_576)  # Exactly 1 MB
        assert result == "1.0 MB"

    def test_format_bytes_gigabytes(self):
        """Test format_bytes with gigabyte values."""
        result = ToolMessages.format_bytes(1_500_000_000)
        assert result == "1.4 GB"

    def test_format_bytes_terabytes(self):
        """Test format_bytes with terabyte values."""
        result = ToolMessages.format_bytes(1_500_000_000_000)
        assert result == "1.4 TB"

    def test_truncate_text_not_truncated(self):
        """Test truncate_text when text is short enough."""
        result = ToolMessages.truncate_text("Hello world", 20)
        assert result == "Hello world"

    def test_truncate_text_exact_length(self):
        """Test truncate_text when text is exactly max_length."""
        result = ToolMessages.truncate_text("Hello", 5)
        assert result == "Hello"

    def test_truncate_text_needs_truncation(self):
        """Test truncate_text when text needs truncation."""
        result = ToolMessages.truncate_text("Hello world this is long", 15)
        assert result == "Hello world ..."

    def test_truncate_text_custom_suffix(self):
        """Test truncate_text with custom suffix."""
        result = ToolMessages.truncate_text("Hello world this is long", 15, ">>")
        # Implementation calculates: max_length - suffix_length = 15 - 2 = 13
        # Takes first 13 chars: "Hello world t" then adds ">>"
        assert result == "Hello world t>>"

    def test_truncate_text_empty_string(self):
        """Test truncate_text with empty string."""
        result = ToolMessages.truncate_text("", 10)
        assert result == ""


class TestToolMessagesResultSummary:
    """Test result summary formatting."""

    def test_format_result_summary_empty(self):
        """Test format_result_summary with empty results."""
        results = []
        result = ToolMessages.format_result_summary(results, "Search")
        assert result == "ℹ️ No results found for Search"

    def test_format_result_summary_single_item(self):
        """Test format_result_summary with single result."""
        results = ["item1"]
        result = ToolMessages.format_result_summary(results, "Search")
        assert result == "✅ Search complete: 1 result\n  1. item1"

    def test_format_result_summary_multiple_items(self):
        """Test format_result_summary with multiple results."""
        results = ["a", "b", "c"]
        result = ToolMessages.format_result_summary(results, "Search")
        lines = result.split("\n")
        assert "✅ Search complete: 3 results" in lines[0]
        assert "  1. a" in lines[1]
        assert "  2. b" in lines[2]
        assert "  3. c" in lines[3]

    def test_format_result_summary_with_max_display(self):
        """Test format_result_summary with max_display limit."""
        results = ["a", "b", "c", "d", "e", "f", "g"]
        result = ToolMessages.format_result_summary(results, "Search", max_display=3)
        lines = result.split("\n")
        assert "  1. a" in lines[1]
        assert "  2. b" in lines[2]
        assert "  3. c" in lines[3]
        assert "  ... and 4 more" in lines[4]

    def test_format_result_summary_no_count(self):
        """Test format_result_summary without showing count."""
        results = ["a", "b"]
        result = ToolMessages.format_result_summary(results, "Process", show_count=False)
        lines = result.split("\n")
        assert lines[0] == "✅ Process complete"

    def test_format_result_summary_numeric_values(self):
        """Test format_result_summary with numeric values."""
        results = [10, 20, 30]
        result = ToolMessages.format_result_summary(results, "Calculate")
        lines = result.split("\n")
        assert "  1. 10" in lines[1]
        assert "  2. 20" in lines[2]
        assert "  3. 30" in lines[3]

    def test_format_result_summary_boolean_values(self):
        """Test format_result_summary with boolean values."""
        results = [True, False, True]
        result = ToolMessages.format_result_summary(results, "Check")
        lines = result.split("\n")
        assert "  1. True" in lines[1]
        assert "  2. False" in lines[2]
        assert "  3. True" in lines[3]

    def test_format_result_summary_complex_objects(self):
        """Test format_result_summary doesn't display complex objects."""
        results = [{"key": "value"}, [1, 2, 3], object()]
        result = ToolMessages.format_result_summary(results, "Query")
        # Complex objects shouldn't be displayed in detail
        lines = result.split("\n")
        assert len(lines) == 1  # Only the summary line

    def test_format_result_summary_max_display_zero(self):
        """Test format_result_summary with max_display=0."""
        results = ["a", "b", "c"]
        result = ToolMessages.format_result_summary(results, "Search", max_display=0)
        # With max_display=0, it shows summary and "and 3 more"
        lines = result.split("\n")
        assert "✅ Search complete: 3 results" in lines[0]
        assert "  ... and 3 more" in lines[1]


class TestToolMessagesEdgeCases:
    """Test edge cases and error conditions."""

    def test_success_with_non_string_values(self):
        """Test success with various value types in details."""
        details = {
            "string": "text",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
        }
        result = ToolMessages.success("Data", details)
        lines = result.split("\n")
        assert len(lines) == 6
        assert "  • string: text" in lines
        assert "  • int: 42" in lines
        assert "  • float: 3.14" in lines
        assert "  • bool: True" in lines
        assert "  • none: None" in lines

    def test_format_list_item_special_characters(self):
        """Test format_list_item with special characters."""
        result = ToolMessages.format_list_item("🔥", "Status", "✓ Complete")
        assert result == "🔥 Status: ✓ Complete"

    def test_validation_error_empty_fields(self):
        """Test validation_error with empty field/message."""
        result = ToolMessages.validation_error("", "")
        assert result == "❌ Validation error:  - "

    def test_operation_failed_with_nested_exception(self):
        """Test operation_failed with nested exception message."""
        error = RuntimeError("Outer error: Inner error")
        result = ToolMessages.operation_failed("Task", error)
        # Should handle the nested colons properly
        assert "Task failed" in result

    def test_format_bytes_zero(self):
        """Test format_bytes with zero bytes."""
        result = ToolMessages.format_bytes(0)
        assert result == "0.0 B"

    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15
    def test_truncate_text_unicode(self):
        """Test truncate_text with unicode characters."""
        text = "Hello 世界 🌍 This is long"
        result = ToolMessages.truncate_text(text, 15)
        # Implementation takes max_length - suffix_length = 15 - 3 = 12 chars
        assert result == "Hello 世界 🌍 T..."
        assert len(result) == 15

    def test_truncate_very_short_max_length(self):
        """Test truncate_text with very short max_length."""
        result = ToolMessages.truncate_text("Hello", 2, "!")
        # Takes 2-1=1 char + "!" = "H!"
        assert result == "H!"


class TestToolMessagesIdempotency:
    """Test that formatting methods are idempotent and consistent."""

    def test_format_timestamp_consistency(self):
        """Test that format_timestamp produces consistent results."""
        dt = datetime(2025, 1, 15, 14, 30, 45)
        result1 = ToolMessages.format_timestamp(dt)
        result2 = ToolMessages.format_timestamp(dt)
        assert result1 == result2

    def test_format_count_round_trip(self):
        """Test format_count behavior is deterministic."""
        for count in [0, 1, 5, 100]:
            result = ToolMessages.format_count(count, "item")
            assert str(count) in result
            assert "item" in result.lower()

    def test_format_progress_rounding_consistency(self):
        """Test that progress percentage rounding is consistent."""
        result1 = ToolMessages.format_progress(1, 3)
        result2 = ToolMessages.format_progress(1, 3)
        assert result1 == result2

    def test_format_bytes_boundary_values(self):
        """Test format_bytes at unit boundaries."""
        # At 1024 bytes, should show 1.0 KB
        result = ToolMessages.format_bytes(1024)
        assert result == "1.0 KB"

        # Just below 1024 bytes
        result = ToolMessages.format_bytes(1023)
        assert result == "1023.0 B"


if __name__ == "__main__":
    pytest.main([__file__])
