"""Unit tests for ``session_buddy.utils.tool_wrapper``.

Covers the seven public functions and the validator factory:
- ``execute_database_tool`` — generic DB wrapper with optional validator
- ``execute_simple_database_tool`` — simplified DB wrapper
- ``execute_database_tool_with_dict`` — DB wrapper returning structured dicts
- ``execute_no_database_tool`` — wrapper for DB-free operations
- ``create_validator`` — factory building validator functions
- ``format_reflection_result`` — reflection storage result formatter
- ``format_search_results`` — search result list formatter
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.utils.error_management import (
    DatabaseUnavailableError,
    ValidationError,
)
from session_buddy.utils.tool_wrapper import (
    create_validator,
    execute_database_tool,
    execute_database_tool_with_dict,
    execute_no_database_tool,
    execute_simple_database_tool,
    format_reflection_result,
    format_search_results,
)


# --- Test helpers ----------------------------------------------------------


def _mock_db() -> MagicMock:
    """Return a MagicMock standing in for a ReflectionDatabaseAdapter."""
    return MagicMock(name="ReflectionDatabaseAdapter")


class TestExecuteDatabaseTool:
    """Verify the comprehensive DB wrapper behaviour."""

    async def test_happy_path_no_validator(self) -> None:
        """Without a validator, the operation runs and the formatter is applied."""
        db = _mock_db()
        op = AsyncMock(return_value=["a", "b", "c"])
        fmt = lambda results: f"Found {len(results)} items"  # noqa: E731

        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(return_value=db),
        ):
            result = await execute_database_tool(op, fmt, "Search")

        assert result == "Found 3 items"
        op.assert_awaited_once_with(db)

    async def test_happy_path_with_validator(self) -> None:
        """Validator runs first; on success, the operation proceeds."""
        db = _mock_db()
        op = AsyncMock(return_value=42)
        fmt = lambda value: f"value={value}"  # noqa: E731
        validator = MagicMock(return_value=None)

        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(return_value=db),
        ):
            result = await execute_database_tool(
                op, fmt, "Compute", validator=validator
            )

        assert result == "value=42"
        validator.assert_called_once_with()
        op.assert_awaited_once_with(db)

    async def test_validation_error_returns_structured_string(self) -> None:
        """ValidationError produces a validation_error envelope."""
        validator = MagicMock(side_effect=ValidationError("query is required"))

        result = await execute_database_tool(
            AsyncMock(), lambda v: v, "Search", validator=validator
        )

        assert "validation error" in result.lower()
        assert "query is required" in result

    async def test_database_unavailable_returns_not_available(self) -> None:
        """DatabaseUnavailableError yields a not_available envelope."""
        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("missing dep")),
        ):
            result = await execute_database_tool(
                AsyncMock(), lambda v: v, "Search"
            )

        assert "not available" in result.lower()

    async def test_generic_exception_returns_operation_failed(self) -> None:
        """Any other exception yields an operation_failed envelope."""
        db = _mock_db()
        op = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(return_value=db),
        ):
            result = await execute_database_tool(op, lambda v: v, "Search")

        assert "failed" in result.lower()
        assert "boom" in result


class TestExecuteSimpleDatabaseTool:
    """Verify the simplified DB wrapper (no separate formatter)."""

    async def test_happy_path_returns_operation_string(self) -> None:
        db = _mock_db()
        op = AsyncMock(return_value="formatted output")

        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(return_value=db),
        ):
            result = await execute_simple_database_tool(op, "Search")

        assert result == "formatted output"
        op.assert_awaited_once_with(db)

    async def test_database_unavailable(self) -> None:
        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("nope")),
        ):
            result = await execute_simple_database_tool(AsyncMock(), "Search")

        assert "not available" in result.lower()

    async def test_generic_exception(self) -> None:
        db = _mock_db()

        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(return_value=db),
        ):
            result = await execute_simple_database_tool(
                AsyncMock(side_effect=ValueError("bad input")),
                "Search",
            )

        assert "failed" in result.lower()
        assert "bad input" in result


class TestExecuteDatabaseToolWithDict:
    """Verify the structured-dict wrapper."""

    async def test_happy_path_returns_success_dict(self) -> None:
        db = _mock_db()
        op = AsyncMock(return_value={"count": 7})

        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(return_value=db),
        ):
            result = await execute_database_tool_with_dict(op, "Search")

        assert result == {"success": True, "data": {"count": 7}}

    async def test_validator_runs_before_db(self) -> None:
        """Validator is invoked before the database is even resolved."""
        validator = MagicMock(return_value=None)
        db = _mock_db()
        op = AsyncMock(return_value={"x": 1})

        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(return_value=db),
        ):
            result = await execute_database_tool_with_dict(
                op, "Search", validator=validator
            )

        assert result["success"] is True
        validator.assert_called_once_with()
        op.assert_awaited_once_with(db)

    async def test_validation_error_envelope(self) -> None:
        validator = MagicMock(side_effect=ValidationError("bad"))
        result = await execute_database_tool_with_dict(
            AsyncMock(), "Search", validator=validator
        )

        assert result["success"] is False
        assert "Search" in result["error"]
        assert "validation" in result["error"].lower()

    async def test_database_unavailable_envelope(self) -> None:
        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("missing dep")),
        ):
            result = await execute_database_tool_with_dict(AsyncMock(), "Search")

        assert result["success"] is False
        assert "missing dep" in result["error"]

    async def test_generic_exception_envelope(self) -> None:
        db = _mock_db()
        op = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(
            "session_buddy.utils.tool_wrapper.require_reflection_database",
            AsyncMock(return_value=db),
        ):
            result = await execute_database_tool_with_dict(op, "Search")

        assert result == {"success": False, "error": "Search failed: boom"}


class TestExecuteNoDatabaseTool:
    """Verify the DB-free wrapper."""

    async def test_happy_path(self) -> None:
        async def op() -> str:
            return "ok"

        result = await execute_no_database_tool(op, lambda v: f"got: {v}", "Check")

        assert result == "got: ok"

    async def test_passes_positional_args(self) -> None:
        op = AsyncMock(return_value=6)
        result = await execute_no_database_tool(
            op, lambda v: f"v={v}", "Add", 2, 4
        )

        assert result == "v=6"
        op.assert_awaited_once_with(2, 4)

    async def test_passes_keyword_args(self) -> None:
        op = AsyncMock(return_value="hi")
        result = await execute_no_database_tool(
            op, lambda v: v, "Greet", name="world"
        )

        assert result == "hi"
        op.assert_awaited_once_with(name="world")

    async def test_exception_returns_operation_failed(self) -> None:
        async def op() -> None:
            raise RuntimeError("nope")

        result = await execute_no_database_tool(op, lambda v: v, "Boom")

        assert "failed" in result.lower()
        assert "nope" in result


class TestCreateValidator:
    """Verify the validator factory and its underlying helpers."""

    def test_required_field_passes_when_non_empty(self) -> None:
        validator = create_validator(required_query="hello")
        validator()  # should not raise

    def test_required_field_raises_on_none(self) -> None:
        validator = create_validator(required_query=None)

        with pytest.raises(ValidationError):
            validator()

    def test_required_field_raises_on_empty_string(self) -> None:
        validator = create_validator(required_query="")

        with pytest.raises(ValidationError):
            validator()

    def test_required_field_raises_on_empty_list(self) -> None:
        validator = create_validator(required_query=[])

        with pytest.raises(ValidationError):
            validator()

    def test_type_field_passes_on_correct_type(self) -> None:
        validator = create_validator(type_limit_int=(5, int))
        validator()

    def test_type_field_raises_on_mismatch(self) -> None:
        validator = create_validator(type_limit_int=("not-an-int", int))

        with pytest.raises(ValidationError):
            validator()

    def test_type_field_skips_unknown_type_name(self) -> None:
        """Unknown type tokens (e.g. ``type_x_unknown``) are silently ignored."""
        validator = create_validator(type_x_unknown=("anything", None))
        validator()  # no raise

    def test_type_field_skips_too_few_key_parts(self) -> None:
        """A ``type_`` key with fewer than 3 parts is silently ignored."""
        validator = create_validator(**{"type_single": ("x", str)})
        validator()  # no raise

    def test_type_field_skips_when_value_not_a_pair(self) -> None:
        """A type_ value that is not a 2-tuple is silently ignored."""
        validator = create_validator(type_x_str="not-a-tuple")
        validator()  # no raise

    def test_range_field_passes_within_bounds(self) -> None:
        validator = create_validator(range_limit=(5, 1, 10))
        validator()

    def test_range_field_raises_below_min(self) -> None:
        validator = create_validator(range_limit=(0, 1, 10))

        with pytest.raises(ValidationError):
            validator()

    def test_range_field_raises_above_max(self) -> None:
        validator = create_validator(range_limit=(11, 1, 10))

        with pytest.raises(ValidationError):
            validator()

    def test_range_field_skips_when_value_not_a_triple(self) -> None:
        """A ``range_`` value that is not a 3-tuple is silently ignored."""
        validator = create_validator(range_limit="not-a-triple")
        validator()  # no raise

    def test_combines_multiple_rules(self) -> None:
        """A validator can mix required_, type_, and range_ rules."""
        validator = create_validator(
            required_query="hello",
            type_limit_int=(5, int),
            range_limit=(5, 1, 10),
        )
        validator()  # no raise

    def test_combined_rules_first_failure_wins(self) -> None:
        """Iteration order means the first invalid rule is reported first."""
        validator = create_validator(
            required_query="",
            type_limit_int=("bad", int),
            range_limit=(99, 1, 10),
        )

        with pytest.raises(ValidationError) as exc_info:
            validator()

        # First iterated (required_query) raises first.
        assert "query" in str(exc_info.value).lower()

    def test_unknown_prefix_is_ignored(self) -> None:
        """Keys with no recognised prefix are silently ignored."""
        validator = create_validator(unknown_key="anything")
        validator()  # no raise


class TestFormatReflectionResult:
    """Verify the reflection storage result formatter."""

    def test_failure_returns_operation_failed(self) -> None:
        result = format_reflection_result(
            success=False, content="any content", tags=["x"], timestamp="now"
        )

        assert "failed" in result.lower()

    def test_success_with_all_fields(self) -> None:
        result = format_reflection_result(
            success=True,
            content="An important insight",
            tags=["learning", "bug-fix"],
            timestamp="2026-09-05 12:00:00",
        )

        assert "Reflection stored" in result
        assert "An important insight" in result
        assert "learning" in result
        assert "bug-fix" in result
        assert "2026-09-05 12:00:00" in result

    def test_success_without_tags_omits_tag_line(self) -> None:
        result = format_reflection_result(
            success=True, content="Hello", tags=None, timestamp="now"
        )

        assert "Reflection stored" in result
        assert "Tags" not in result

    def test_success_with_empty_tags_omits_tag_line(self) -> None:
        result = format_reflection_result(
            success=True, content="Hello", tags=[], timestamp="now"
        )

        assert "Reflection stored" in result
        assert "Tags" not in result

    def test_success_without_timestamp_omits_date_line(self) -> None:
        result = format_reflection_result(
            success=True, content="Hello", tags=["x"], timestamp=None
        )

        assert "Reflection stored" in result
        assert "Stored:" not in result


class TestFormatSearchResults:
    """Verify the search result list formatter."""

    def test_empty_results_returns_empty_message(self) -> None:
        result = format_search_results([], "my query")

        assert "no results" in result.lower()
        assert "my query" in result

    def test_with_results_shows_count_and_details(self) -> None:
        results = [
            {"content": "First match", "score": 0.95, "timestamp": "2026-09-01"},
            {"content": "Second match", "score": 0.80},
        ]

        result = format_search_results(results, "q", show_details=True)

        assert "Found 2 results" in result
        assert "First match" in result
        assert "Second match" in result
        assert "0.95" in result
        assert "2026-09-01" in result

    def test_with_results_no_details(self) -> None:
        results = [{"content": "x", "score": 0.5}]

        result = format_search_results(results, "q", show_details=False)

        assert "Found 1 result" in result
        # When show_details=False, individual results are not enumerated.
        assert "1. " not in result

    def test_truncates_at_max_results(self) -> None:
        results = [{"content": f"item {i}"} for i in range(15)]

        result = format_search_results(results, "q", max_results=3)

        assert "Found 15 results" in result
        assert "12 more results" in result
        # Only the first 3 should be displayed.
        assert "item 0" in result
        assert "item 2" in result

    def test_max_results_larger_than_results(self) -> None:
        """When fewer results than max_results, the 'more' line is omitted."""
        results = [{"content": "only one"}]

        result = format_search_results(results, "q", max_results=10)

        assert "more results" not in result
        assert "only one" in result

    def test_truncates_long_content(self) -> None:
        long_content = "x" * 200
        results = [{"content": long_content}]

        result = format_search_results(results, "q", max_results=10)

        # Content was truncated: the result line should end with the
        # "..." suffix and the original 200-x string is not in full.
        assert "..." in result
        assert long_content not in result
        # Truncation is bounded: no more than 80 x's appear in sequence.
        assert "x" * 81 not in result
