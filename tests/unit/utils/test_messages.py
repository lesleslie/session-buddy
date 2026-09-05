"""Unit tests for ``session_buddy.utils.messages`` (ToolMessages)."""

from __future__ import annotations

from datetime import datetime

from session_buddy.utils.messages import ToolMessages


class TestNotAvailable:
    """Verify ``not_available`` formatting."""

    def test_without_install_hint(self) -> None:
        result = ToolMessages.not_available("Database")
        assert result == "❌ Database not available"

    def test_with_install_hint_default_prefix(self) -> None:
        result = ToolMessages.not_available(
            "Database", "uv sync --extra embeddings"
        )
        assert result == (
            "❌ Database not available. Install: uv sync --extra embeddings"
        )

    def test_with_install_hint_already_prefixed(self) -> None:
        result = ToolMessages.not_available("Database", "Install via pip")
        assert result == "❌ Database not available. Install via pip"

    def test_with_empty_install_hint(self) -> None:
        result = ToolMessages.not_available("Database", "")
        assert result == "❌ Database not available"


class TestOperationFailed:
    """Verify ``operation_failed`` formatting."""

    def test_with_string_error(self) -> None:
        result = ToolMessages.operation_failed("Search", "Bad input")
        assert result == "❌ Search failed: Bad input"

    def test_with_exception(self) -> None:
        result = ToolMessages.operation_failed("Search", ValueError("Bad input"))
        assert result == "❌ Search failed: Bad input"

    def test_with_exception_str_has_no_error_suffix(self) -> None:
        result = ToolMessages.operation_failed("Parse", Exception("oops"))
        assert result == "❌ Parse failed: oops"

    def test_with_exception_str_has_colon_but_no_error_suffix(self) -> None:
        # Splits on the FIRST ": " only when left-hand side ends with "Error".
        result = ToolMessages.operation_failed("Op", RuntimeError("note: oops"))
        assert result == "❌ Op failed: note: oops"

    def test_with_exception_str_starts_with_error(self) -> None:
        # Left side ends with "Error" -> the prefix is stripped.
        result = ToolMessages.operation_failed("Op", ValueError("ValueError: bad"))
        assert result == "❌ Op failed: bad"

    def test_exception_not_custom_error_class(self) -> None:
        # When the left-of-colon does NOT end with "Error", the string is kept.
        result = ToolMessages.operation_failed("Op", Exception("INFO: hi"))
        assert result == "❌ Op failed: INFO: hi"


class TestSuccess:
    """Verify ``success`` formatting."""

    def test_without_details(self) -> None:
        result = ToolMessages.success("Stored")
        assert result == "✅ Stored"

    def test_with_empty_details_dict(self) -> None:
        # Empty dict is falsy -> no detail lines appended.
        result = ToolMessages.success("Stored", {})
        assert result == "✅ Stored"

    def test_with_details(self) -> None:
        result = ToolMessages.success("Stored", {"items": 5, "time": "1.2s"})
        assert result == "✅ Stored\n  • items: 5\n  • time: 1.2s"

    def test_with_none_details(self) -> None:
        result = ToolMessages.success("Stored", None)
        assert result == "✅ Stored"


class TestValidationError:
    """Verify ``validation_error`` formatting."""

    def test_basic(self) -> None:
        result = ToolMessages.validation_error("email", "Invalid format")
        assert result == "❌ Validation error: email - Invalid format"

    def test_empty_field(self) -> None:
        result = ToolMessages.validation_error("", "missing")
        assert result == "❌ Validation error:  - missing"

    def test_empty_message(self) -> None:
        result = ToolMessages.validation_error("name", "")
        assert result == "❌ Validation error: name - "


class TestEmptyResults:
    """Verify ``empty_results`` formatting."""

    def test_without_suggestion(self) -> None:
        result = ToolMessages.empty_results("Search")
        assert result == "ℹ️ No results found for Search"

    def test_with_suggestion(self) -> None:
        result = ToolMessages.empty_results("Search", "Try broader terms")
        assert result == "ℹ️ No results found for Search. Try broader terms"

    def test_with_empty_suggestion(self) -> None:
        result = ToolMessages.empty_results("Search", "")
        assert result == "ℹ️ No results found for Search"


class TestFormatListItem:
    """Verify ``format_list_item`` formatting."""

    def test_basic(self) -> None:
        result = ToolMessages.format_list_item("📝", "Content", "Hello world")
        assert result == "📝 Content: Hello world"

    def test_with_numeric_value(self) -> None:
        result = ToolMessages.format_list_item("🔢", "Count", 42)
        assert result == "🔢 Count: 42"

    def test_with_none_value(self) -> None:
        result = ToolMessages.format_list_item("⚠️", "Status", None)
        assert result == "⚠️ Status: None"


class TestFormatTimestamp:
    """Verify ``format_timestamp`` formatting."""

    def test_with_provided_datetime(self) -> None:
        dt = datetime(2025, 1, 12, 14, 30, 45)
        result = ToolMessages.format_timestamp(dt)
        assert result == "2025-01-12 14:30:45"

    def test_with_none_defaults_to_now(self) -> None:
        before = ToolMessages.format_timestamp()
        # Format should match YYYY-MM-DD HH:MM:SS exactly.
        assert len(before) == 19
        assert before[4] == "-"
        assert before[7] == "-"
        assert before[10] == " "
        assert before[13] == ":"
        assert before[16] == ":"


class TestFormatCount:
    """Verify ``format_count`` formatting."""

    def test_singular_count_one(self) -> None:
        result = ToolMessages.format_count(1, "result")
        assert result == "1 result"

    def test_plural_default(self) -> None:
        # plural defaults to singular + "s".
        result = ToolMessages.format_count(5, "result")
        assert result == "5 results"

    def test_plural_explicit(self) -> None:
        result = ToolMessages.format_count(5, "match", "matches")
        assert result == "5 matches"

    def test_zero_uses_plural(self) -> None:
        result = ToolMessages.format_count(0, "item")
        assert result == "0 items"

    def test_irregular_plural_irrelevant_for_one(self) -> None:
        # When count is 1 the explicit plural is ignored.
        result = ToolMessages.format_count(1, "child", "children")
        assert result == "1 child"


class TestFormatProgress:
    """Verify ``format_progress`` formatting."""

    def test_without_operation(self) -> None:
        result = ToolMessages.format_progress(5, 10)
        assert result == "5/10 (50%)"

    def test_with_operation(self) -> None:
        result = ToolMessages.format_progress(5, 10, "Processing")
        assert result == "Processing: 5/10 (50%)"

    def test_rounds_down_to_int_percent(self) -> None:
        result = ToolMessages.format_progress(1, 3)
        # 1/3 = 33.33... -> int() truncates to 33.
        assert result == "1/3 (33%)"

    def test_zero_total_returns_zero_percent(self) -> None:
        result = ToolMessages.format_progress(5, 0)
        assert result == "5/0 (0%)"

    def test_zero_total_with_operation(self) -> None:
        result = ToolMessages.format_progress(5, 0, "Loading")
        assert result == "Loading: 5/0 (0%)"

    def test_full_completion(self) -> None:
        result = ToolMessages.format_progress(10, 10)
        assert result == "10/10 (100%)"


class TestFormatDuration:
    """Verify ``format_duration`` formatting."""

    def test_under_minute(self) -> None:
        result = ToolMessages.format_duration(3.2)
        assert result == "3.2s"

    def test_just_under_minute(self) -> None:
        result = ToolMessages.format_duration(59.9)
        assert result == "59.9s"

    def test_one_minute(self) -> None:
        result = ToolMessages.format_duration(60.0)
        assert result == "1m 0.0s"

    def test_over_minute(self) -> None:
        result = ToolMessages.format_duration(65.5)
        assert result == "1m 5.5s"

    def test_zero(self) -> None:
        result = ToolMessages.format_duration(0)
        assert result == "0.0s"


class TestFormatBytes:
    """Verify ``format_bytes`` formatting."""

    def test_bytes(self) -> None:
        result = ToolMessages.format_bytes(500)
        assert result == "500.0 B"

    def test_kilobytes(self) -> None:
        result = ToolMessages.format_bytes(1500)
        assert result == "1.5 KB"

    def test_megabytes(self) -> None:
        result = ToolMessages.format_bytes(1_500_000)
        assert result == "1.4 MB"

    def test_gigabytes(self) -> None:
        result = ToolMessages.format_bytes(2_000_000_000)
        assert result == "1.9 GB"

    def test_terabytes(self) -> None:
        # 1.5e15 / 1024^4 ≈ 1364.2 TB.
        result = ToolMessages.format_bytes(1_500_000_000_000_000)
        assert result == "1364.2 TB"

    def test_zero_bytes(self) -> None:
        result = ToolMessages.format_bytes(0)
        assert result == "0.0 B"


class TestFormatResultSummary:
    """Verify ``format_result_summary`` formatting."""

    def test_empty_results(self) -> None:
        result = ToolMessages.format_result_summary([], "Search")
        assert result == "ℹ️ No results found for Search"

    def test_basic_with_count(self) -> None:
        results = ["a", "b", "c"]
        result = ToolMessages.format_result_summary(results, "Search")
        assert "✅ Search complete: 3 results" in result

    def test_basic_without_count(self) -> None:
        results = ["a", "b"]
        result = ToolMessages.format_result_summary(
            results, "Search", show_count=False
        )
        # show_count=False suppresses the count line, but per-item lines are
        # still appended under the default max_display=5.
        assert result == "✅ Search complete\n  1. a\n  2. b"

    def test_with_max_display(self) -> None:
        results = ["a", "b", "c", "d", "e", "f", "g"]
        result = ToolMessages.format_result_summary(
            results, "Search", max_display=5
        )
        # All 5 displayed in order.
        assert "1. a" in result
        assert "5. e" in result
        # Two more truncated.
        assert "... and 2 more" in result

    def test_max_display_zero_skips_details(self) -> None:
        results = ["a", "b", "c"]
        result = ToolMessages.format_result_summary(
            results, "Search", max_display=0
        )
        # With max_display=0 no per-item lines are shown, but the
        # count > max_display branch still appends "... and N more".
        assert "1. a" not in result
        assert "2. b" not in result
        assert "3. c" not in result
        assert "... and 3 more" in result

    def test_mixed_results_only_shows_primitives(self) -> None:
        results = ["a", {"complex": "dict"}, 1, 2.5]
        result = ToolMessages.format_result_summary(results, "Search")
        # Strings, ints, floats display; dicts are skipped. The displayed
        # indices are contiguous (1, 2, 3) — non-primitive slots are NOT
        # numbered, they just don't appear.
        assert "1. a" in result
        assert "2. 1" in result
        assert "3. 2.5" in result
        assert "complex" not in result
        assert "4. " not in result  # no fourth entry — the dict is skipped

    def test_no_truncation_message_when_at_limit(self) -> None:
        results = ["a", "b", "c"]
        result = ToolMessages.format_result_summary(
            results, "Search", max_display=3
        )
        # Exactly at the limit -> no truncation line.
        assert "... and" not in result

    def test_empty_results_with_suggestion_in_empty_results(self) -> None:
        # format_result_summary delegates to empty_results for empty input;
        # empty_results with no suggestion has no period.
        result = ToolMessages.format_result_summary([], "Search")
        assert result.endswith("Search")


class TestTruncateText:
    """Verify ``truncate_text`` formatting."""

    def test_shorter_than_max_returns_unchanged(self) -> None:
        result = ToolMessages.truncate_text("Hello", 10)
        assert result == "Hello"

    def test_exactly_max_returns_unchanged(self) -> None:
        # len("Hello") == 5, max == 5 -> no truncation.
        result = ToolMessages.truncate_text("Hello", 5)
        assert result == "Hello"

    def test_default_max_length(self) -> None:
        # 100-char default, text shorter than 100 -> unchanged.
        result = ToolMessages.truncate_text("short text")
        assert result == "short text"

    def test_truncates_with_default_suffix(self) -> None:
        # max_length=15, suffix="..." (len 3) -> keep first 12 chars + "...".
        result = ToolMessages.truncate_text("Hello world this is long", 15)
        assert result == "Hello world ..."

    def test_custom_suffix(self) -> None:
        result = ToolMessages.truncate_text("Hello world this is long", 13, "…")
        # len("…") == 1 -> keep first 12 chars + "…".
        assert result == "Hello world …"

    def test_max_length_equals_suffix_length(self) -> None:
        # max_length=3, suffix="..." (len 3) -> text[:0] + "..." = "...".
        result = ToolMessages.truncate_text("abcdef", 3, "...")
        assert result == "..."

    def test_empty_text_returns_empty(self) -> None:
        result = ToolMessages.truncate_text("", 10)
        assert result == ""
