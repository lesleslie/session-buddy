"""Tests for session_buddy.mcp.tools.infrastructure.hook_parser.

Covers the crackerjack hook output parser:
- ``HookResult`` named tuple shape
- ``parse_hook_line`` happy path, edge cases, and error paths
- ``parse_hook_output`` multi-line input, empty line skipping, line-number
  error context
- ``extract_failed_hooks`` convenience wrapper
- ``ParseError`` exception semantics
- ``_PASS_MARKERS`` / ``_FAIL_MARKERS`` frozensets
"""

from __future__ import annotations

import pytest

from session_buddy.mcp.tools.infrastructure.hook_parser import (
    HookResult,
    ParseError,
    _FAIL_MARKERS,
    _PASS_MARKERS,
    _extract_hook_name,
    _extract_parts,
    _validate_line,
    _validate_status_marker,
    extract_failed_hooks,
    parse_hook_line,
    parse_hook_output,
)


# ---------------------------------------------------------------------------
# Named tuple shape
# ---------------------------------------------------------------------------


class TestHookResult:
    def test_fields_present(self) -> None:
        result = HookResult(hook_name="refurb", passed=True)
        assert result.hook_name == "refurb"
        assert result.passed is True

    def test_unpacks_to_two(self) -> None:
        name, passed = HookResult(hook_name="x", passed=False)
        assert name == "x"
        assert passed is False

    def test_iterable(self) -> None:
        result = HookResult(hook_name="y", passed=True)
        assert tuple(result) == ("y", True)


# ---------------------------------------------------------------------------
# Marker definitions
# ---------------------------------------------------------------------------


class TestMarkerConstants:
    def test_pass_markers(self) -> None:
        # frozenset, contains unicode + ascii variants.
        assert "✅" in _PASS_MARKERS
        assert "Passed" in _PASS_MARKERS
        # Failed markers should NOT be in pass set.
        assert "❌" not in _PASS_MARKERS
        assert "Failed" not in _PASS_MARKERS

    def test_fail_markers(self) -> None:
        assert "❌" in _FAIL_MARKERS
        assert "Failed" in _FAIL_MARKERS
        assert "✅" not in _FAIL_MARKERS
        assert "Passed" not in _FAIL_MARKERS

    def test_disjoint(self) -> None:
        assert _PASS_MARKERS.isdisjoint(_FAIL_MARKERS)


# ---------------------------------------------------------------------------
# parse_hook_line — happy path
# ---------------------------------------------------------------------------


class TestParseHookLineHappyPath:
    def test_passed_unicode_marker(self) -> None:
        line = "refurb............................................................ ✅"
        result = parse_hook_line(line)
        assert result == HookResult(hook_name="refurb", passed=True)

    def test_failed_unicode_marker(self) -> None:
        line = "refurb............................................................ ❌"
        result = parse_hook_line(line)
        assert result == HookResult(hook_name="refurb", passed=False)

    def test_passed_ascii_marker(self) -> None:
        line = "refurb............................................................ Passed"
        result = parse_hook_line(line)
        assert result == HookResult(hook_name="refurb", passed=True)

    def test_failed_ascii_marker(self) -> None:
        line = "refurb............................................................ Failed"
        result = parse_hook_line(line)
        assert result == HookResult(hook_name="refurb", passed=False)

    def test_hook_name_with_internal_dots(self) -> None:
        line = "my...custom...hook.................................................... ✅"
        result = parse_hook_line(line)
        # rstrip(".") only removes trailing dots, so the name keeps internal dots.
        assert result.hook_name == "my...custom...hook"
        assert result.passed is True

    def test_hook_name_with_dashes_and_underscores(self) -> None:
        line = "test.integration.api.................................................. Passed"
        result = parse_hook_line(line)
        assert result.hook_name == "test.integration.api"
        assert result.passed is True

    def test_minimum_padding(self) -> None:
        line = "x. ✅"
        result = parse_hook_line(line)
        assert result.hook_name == "x"
        assert result.passed is True

    def test_leading_whitespace_stripped(self) -> None:
        line = "   refurb.......................... ❌"
        result = parse_hook_line(line)
        assert result.hook_name == "refurb"
        assert result.passed is False

    def test_trailing_whitespace_stripped(self) -> None:
        line = "refurb.......................... ❌   \n"
        result = parse_hook_line(line)
        assert result.hook_name == "refurb"


# ---------------------------------------------------------------------------
# parse_hook_line — error branches
# ---------------------------------------------------------------------------


class TestParseHookLineErrors:
    def test_empty_line_raises(self) -> None:
        with pytest.raises(ParseError, match="empty line"):
            parse_hook_line("")

    def test_whitespace_only_line_raises(self) -> None:
        with pytest.raises(ParseError, match="empty line"):
            parse_hook_line("   \t  ")

    def test_unknown_status_marker_raises(self) -> None:
        with pytest.raises(ParseError, match="Unknown status marker"):
            parse_hook_line("refurb.......................... 🤷")

    def test_line_with_no_space_raises(self) -> None:
        with pytest.raises(ParseError, match="no space-separated status marker"):
            parse_hook_line("refurb.❌")

    def test_only_status_marker_no_name_raises(self) -> None:
        # Single token that is itself a marker.
        with pytest.raises(ParseError, match="No hook name found before status marker"):
            parse_hook_line("❌")

    def test_only_status_marker_passed_raises(self) -> None:
        with pytest.raises(ParseError, match="No hook name found before status marker"):
            parse_hook_line("Passed")

    def test_name_only_dots_raises(self) -> None:
        with pytest.raises(ParseError, match="entirely of dots"):
            parse_hook_line("........... ✅")

    def test_empty_left_part_raises(self) -> None:
        # Right part is a marker; left part is empty.
        with pytest.raises(ParseError, match="No hook name found before status marker"):
            parse_hook_line(" ✅")


# ---------------------------------------------------------------------------
# parse_hook_output
# ---------------------------------------------------------------------------


class TestParseHookOutput:
    def test_multiple_lines(self) -> None:
        output = (
            "refurb............................................................ ✅\n"
            "mypy................................................................ ❌\n"
            "tests............................................................... Passed\n"
        )
        results = parse_hook_output(output)
        assert results == [
            HookResult(hook_name="refurb", passed=True),
            HookResult(hook_name="mypy", passed=False),
            HookResult(hook_name="tests", passed=True),
        ]

    def test_empty_lines_are_skipped(self) -> None:
        output = (
            "\n"
            "refurb.......................... ✅\n"
            "\n"
            "mypy............................ ❌\n"
            "\n"
        )
        results = parse_hook_output(output)
        assert [r.hook_name for r in results] == ["refurb", "mypy"]

    def test_empty_input_returns_empty(self) -> None:
        assert parse_hook_output("") == []

    def test_only_whitespace_lines_returns_empty(self) -> None:
        assert parse_hook_output("\n\n   \n\n") == []

    def test_invalid_line_raises_with_line_number(self) -> None:
        output = (
            "refurb.......................... ✅\n"  # line 1
            "mypy............................ 🤷\n"  # line 2 — invalid
        )
        with pytest.raises(ParseError, match=r"Line 2:") as exc:
            parse_hook_output(output)
        # And it should chain the original.
        assert isinstance(exc.value.__cause__, ParseError)

    def test_invalid_line_raises_on_first_bad_line(self) -> None:
        output = (
            "refurb.......................... 🤷\n"  # line 1 — invalid
            "mypy............................ ✅\n"
        )
        with pytest.raises(ParseError, match=r"Line 1:"):
            parse_hook_output(output)


# ---------------------------------------------------------------------------
# extract_failed_hooks
# ---------------------------------------------------------------------------


class TestExtractFailedHooks:
    def test_returns_only_failed_names(self) -> None:
        output = (
            "a.............................. ✅\n"
            "b.............................. ❌\n"
            "c.............................. Passed\n"
            "d.............................. Failed\n"
        )
        assert extract_failed_hooks(output) == ["b", "d"]

    def test_all_passed_returns_empty(self) -> None:
        output = (
            "a.............................. ✅\n"
            "b.............................. Passed\n"
        )
        assert extract_failed_hooks(output) == []

    def test_all_failed_returns_all(self) -> None:
        output = (
            "a.............................. ❌\n"
            "b.............................. Failed\n"
        )
        assert extract_failed_hooks(output) == ["a", "b"]

    def test_empty_output_returns_empty(self) -> None:
        assert extract_failed_hooks("") == []

    def test_propagates_parse_error(self) -> None:
        with pytest.raises(ParseError):
            extract_failed_hooks("refurb.......................... 🤷")


# ---------------------------------------------------------------------------
# Private helpers — direct unit coverage
# ---------------------------------------------------------------------------


class TestValidateLine:
    def test_non_empty_passes(self) -> None:
        # Should not raise.
        _validate_line("anything", "anything")

    def test_empty_raises(self) -> None:
        with pytest.raises(ParseError, match="empty line"):
            _validate_line("", "")


class TestExtractParts:
    def test_typical_line(self) -> None:
        left, marker = _extract_parts("refurb.......... ✅", "refurb.......... ✅")
        assert left == "refurb.........."
        assert marker == "✅"

    def test_single_token_no_marker_raises(self) -> None:
        with pytest.raises(ParseError, match="no space-separated status marker"):
            _extract_parts("hello", "hello")

    def test_single_token_with_marker_raises_no_name(self) -> None:
        with pytest.raises(ParseError, match="No hook name found"):
            _extract_parts("✅", "✅")


class TestValidateStatusMarker:
    def test_pass_marker_returns_true(self) -> None:
        assert _validate_status_marker("✅") is True
        assert _validate_status_marker("Passed") is True

    def test_fail_marker_returns_false(self) -> None:
        assert _validate_status_marker("❌") is False
        assert _validate_status_marker("Failed") is False

    def test_unknown_raises(self) -> None:
        with pytest.raises(ParseError, match="Unknown status marker"):
            _validate_status_marker("???")


class TestExtractHookName:
    def test_strips_trailing_dots(self) -> None:
        assert _extract_hook_name("name.....") == "name"

    def test_empty_input_raises(self) -> None:
        with pytest.raises(ParseError, match="No hook name found"):
            _extract_hook_name("")

    def test_only_dots_raises(self) -> None:
        with pytest.raises(ParseError, match="entirely of dots"):
            _extract_hook_name(".....")

    def test_no_trailing_dots(self) -> None:
        assert _extract_hook_name("plainname") == "plainname"

    def test_internal_dots_preserved(self) -> None:
        assert _extract_hook_name("a.b.c") == "a.b.c"
