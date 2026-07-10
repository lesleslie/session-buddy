"""Comprehensive pytest unit tests for session_buddy/mcp/tools/infrastructure/hook_parser.py.

Tests all public functions, classes, and edge cases:
- HookResult namedtuple structure
- ParseError exception
- _validate_line helper
- _extract_parts helper
- _validate_status_marker helper
- _extract_hook_name helper
- parse_hook_line (public)
- parse_hook_output (public)
- extract_failed_hooks (public)
- Status marker definitions (_PASS_MARKERS, _FAIL_MARKERS, _ALL_MARKERS)
- Edge cases (empty lines, multi-line, malformed inputs, etc.)

Requirements:
1. Cover all 57 statements in the module
2. Lazy imports inside test functions to avoid top-level module loading
3. Aim for 95%+ coverage of the module
4. Descriptive test names: test_<function>_<scenario>
"""

from __future__ import annotations

from typing import Any

import pytest


# =====================================
# Test Classes - Grouped by Function/Feature
# =====================================


class TestHookResult:
    """Tests for the HookResult namedtuple."""

    def test_hook_result_construction(self) -> None:
        """Should construct a HookResult with name and passed flag."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import HookResult

        result = HookResult(hook_name="my_hook", passed=True)
        assert result.hook_name == "my_hook"
        assert result.passed is True

    def test_hook_result_failed_status(self) -> None:
        """Should construct a HookResult for failed status."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import HookResult

        result = HookResult(hook_name="my_hook", passed=False)
        assert result.hook_name == "my_hook"
        assert result.passed is False

    def test_hook_result_is_namedtuple(self) -> None:
        """HookResult should support tuple unpacking and indexing."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import HookResult

        result = HookResult(hook_name="my_hook", passed=True)
        # Tuple-style access
        assert result[0] == "my_hook"
        assert result[1] is True
        # Unpacking
        name, passed = result
        assert name == "my_hook"
        assert passed is True

    def test_hook_result_equality(self) -> None:
        """Two HookResults with the same fields should be equal."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import HookResult

        a = HookResult(hook_name="h", passed=True)
        b = HookResult(hook_name="h", passed=True)
        assert a == b

    def test_hook_result_repr(self) -> None:
        """Should have a useful repr for debugging."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import HookResult

        result = HookResult(hook_name="h", passed=True)
        text = repr(result)
        assert "HookResult" in text
        assert "h" in text


class TestParseError:
    """Tests for the ParseError exception."""

    def test_parse_error_is_value_error(self) -> None:
        """ParseError should be a subclass of ValueError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import ParseError

        err = ParseError("bad line")
        assert isinstance(err, ValueError)
        assert str(err) == "bad line"

    def test_parse_error_can_be_raised(self) -> None:
        """ParseError should be raisable and catchable."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import ParseError

        with pytest.raises(ParseError, match="custom message"):
            raise ParseError("custom message")


class TestStatusMarkerConstants:
    """Tests for status marker definitions."""

    def test_pass_markers_contains_unicode_check(self) -> None:
        """PASS markers should include the green checkmark."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _PASS_MARKERS

        assert "✅" in _PASS_MARKERS

    def test_pass_markers_contains_word(self) -> None:
        """PASS markers should include the word 'Passed'."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _PASS_MARKERS

        assert "Passed" in _PASS_MARKERS

    def test_fail_markers_contains_unicode_cross(self) -> None:
        """FAIL markers should include the red cross."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _FAIL_MARKERS

        assert "❌" in _FAIL_MARKERS

    def test_fail_markers_contains_word(self) -> None:
        """FAIL markers should include the word 'Failed'."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _FAIL_MARKERS

        assert "Failed" in _FAIL_MARKERS

    def test_all_markers_is_union(self) -> None:
        """_ALL_MARKERS should be the union of pass and fail markers."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            _ALL_MARKERS,
            _FAIL_MARKERS,
            _PASS_MARKERS,
        )

        assert _ALL_MARKERS == _PASS_MARKERS | _FAIL_MARKERS

    def test_markers_are_frozenset(self) -> None:
        """Marker sets should be frozensets (immutable)."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            _ALL_MARKERS,
            _FAIL_MARKERS,
            _PASS_MARKERS,
        )

        assert isinstance(_PASS_MARKERS, frozenset)
        assert isinstance(_FAIL_MARKERS, frozenset)
        assert isinstance(_ALL_MARKERS, frozenset)

    def test_pass_and_fail_are_disjoint(self) -> None:
        """Pass and fail markers should not overlap."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            _FAIL_MARKERS,
            _PASS_MARKERS,
        )

        assert _PASS_MARKERS & _FAIL_MARKERS == set()


class TestValidateLine:
    """Tests for the _validate_line helper."""

    def test_validate_line_raises_on_empty(self) -> None:
        """_validate_line should raise ParseError on empty input."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            _validate_line,
        )

        with pytest.raises(ParseError, match="Cannot parse empty line"):
            _validate_line("", "")

    def test_validate_line_raises_on_whitespace_only(self) -> None:
        """_validate_line expects a stripped value - whitespace passes when not stripped.

        Note: ``_validate_line`` is called with an already-stripped string. The
        whitespace-stripping happens in ``parse_hook_line`` before delegating.
        This test documents that contract.
        """
        from session_buddy.mcp.tools.infrastructure.hook_parser import _validate_line

        # When given a whitespace-only "stripped" value (which shouldn't happen
        # in practice because the caller strips), _validate_line does NOT
        # raise because the string is non-empty.
        result = _validate_line("   \t  ", "   \t  ")
        assert result is None

    def test_validate_line_passes_on_valid(self) -> None:
        """_validate_line should return None on valid input."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _validate_line

        # Should not raise
        result = _validate_line("hook ✅", "hook ✅")
        assert result is None


class TestExtractParts:
    """Tests for the _extract_parts helper."""

    def test_extract_parts_unicode_marker(self) -> None:
        """Should split a line with the unicode pass marker."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_parts

        left, marker = _extract_parts("refurb... ✅", "refurb... ✅")
        assert left == "refurb..."
        assert marker == "✅"

    def test_extract_parts_word_marker(self) -> None:
        """Should split a line with the word pass marker."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_parts

        left, marker = _extract_parts("hook.name Passed", "hook.name Passed")
        assert left == "hook.name"
        assert marker == "Passed"

    def test_extract_parts_fail_marker(self) -> None:
        """Should split a line with the fail marker."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_parts

        left, marker = _extract_parts("refurb... ❌", "refurb... ❌")
        assert left == "refurb..."
        assert marker == "❌"

    def test_extract_parts_failed_word(self) -> None:
        """Should split a line with the word fail marker."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_parts

        left, marker = _extract_parts("hook.name Failed", "hook.name Failed")
        assert left == "hook.name"
        assert marker == "Failed"

    def test_extract_parts_only_marker_raises(self) -> None:
        """Should raise when only a marker is present (no hook name)."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            _extract_parts,
        )

        with pytest.raises(ParseError, match="No hook name"):
            _extract_parts("✅", "✅")

    def test_extract_parts_only_word_marker_raises(self) -> None:
        """Should raise when only the word marker is present."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            _extract_parts,
        )

        with pytest.raises(ParseError, match="No hook name"):
            _extract_parts("Passed", "Passed")

    def test_extract_parts_no_marker_raises(self) -> None:
        """Should raise when line has no space-separated marker."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            _extract_parts,
        )

        with pytest.raises(ParseError, match="no space-separated status marker"):
            _extract_parts("hook_name", "hook_name")

    def test_extract_parts_preserves_dots_in_name(self) -> None:
        """Dots in the hook name should be preserved in the left part."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_parts

        left, _ = _extract_parts("a.b.c.d... ✅", "a.b.c.d... ✅")
        assert left == "a.b.c.d..."

    def test_extract_parts_uses_rsplit(self) -> None:
        """Multi-space scenarios should still find the last marker."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_parts

        # Two markers in one line - the last is the status marker
        left, marker = _extract_parts("hook ✅ ✅", "hook ✅ ✅")
        assert left == "hook ✅"
        assert marker == "✅"


class TestValidateStatusMarker:
    """Tests for the _validate_status_marker helper."""

    def test_validate_unicode_pass(self) -> None:
        """Unicode pass marker should return True."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            _validate_status_marker,
        )

        assert _validate_status_marker("✅") is True

    def test_validate_word_pass(self) -> None:
        """Word 'Passed' should return True."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            _validate_status_marker,
        )

        assert _validate_status_marker("Passed") is True

    def test_validate_unicode_fail(self) -> None:
        """Unicode fail marker should return False."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            _validate_status_marker,
        )

        assert _validate_status_marker("❌") is False

    def test_validate_word_fail(self) -> None:
        """Word 'Failed' should return False."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            _validate_status_marker,
        )

        assert _validate_status_marker("Failed") is False

    def test_validate_unknown_marker_raises(self) -> None:
        """Unknown marker should raise ParseError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            _validate_status_marker,
        )

        with pytest.raises(ParseError, match="Unknown status marker"):
            _validate_status_marker("???")

    def test_validate_empty_marker_raises(self) -> None:
        """Empty marker should raise ParseError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            _validate_status_marker,
        )

        with pytest.raises(ParseError, match="Unknown status marker"):
            _validate_status_marker("")


class TestExtractHookName:
    """Tests for the _extract_hook_name helper."""

    def test_extract_strips_trailing_dots(self) -> None:
        """Should strip padding dots from the end of the name."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_hook_name

        assert _extract_hook_name("refurb...") == "refurb"

    def test_extract_handles_no_padding(self) -> None:
        """Should return name unchanged if no padding dots."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_hook_name

        assert _extract_hook_name("refurb") == "refurb"

    def test_extract_handles_dotted_name(self) -> None:
        """Should preserve dots that are part of the name."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_hook_name

        assert _extract_hook_name("a.b.c.....") == "a.b.c"

    def test_extract_empty_raises(self) -> None:
        """Empty left part should raise."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            _extract_hook_name,
        )

        with pytest.raises(ParseError, match="No hook name"):
            _extract_hook_name("")

    def test_extract_only_dots_raises(self) -> None:
        """A string of only dots should raise."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            _extract_hook_name,
        )

        with pytest.raises(ParseError, match="entirely of dots"):
            _extract_hook_name(".....")

    def test_extract_single_char_name(self) -> None:
        """Single character names should be preserved."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import _extract_hook_name

        assert _extract_hook_name("x.") == "x"


class TestParseHookLine:
    """Tests for the public parse_hook_line function."""

    def test_parse_simple_pass(self) -> None:
        """Should parse a simple pass line."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            HookResult,
            parse_hook_line,
        )

        result = parse_hook_line("refurb ❌")
        assert result == HookResult(hook_name="refurb", passed=False)

    def test_parse_simple_pass_word(self) -> None:
        """Should parse a simple pass line with 'Passed' word."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_line

        result = parse_hook_line("refurb Passed")
        assert result.hook_name == "refurb"
        assert result.passed is True

    def test_parse_padded_dots(self) -> None:
        """Should parse a line with padding dots."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_line

        result = parse_hook_line(
            "refurb................................................................ ❌",
        )
        assert result.hook_name == "refurb"
        assert result.passed is False

    def test_parse_dotted_hook_name(self) -> None:
        """Should parse a hook name that contains dots."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_line

        result = parse_hook_line(
            "my...custom...hook.................................................... ✅",
        )
        assert result.hook_name == "my...custom...hook"
        assert result.passed is True

    def test_parse_integration_test(self) -> None:
        """Should parse an integration test style line."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_line

        result = parse_hook_line(
            "test.integration.api.................................................. Passed",
        )
        assert result.hook_name == "test.integration.api"
        assert result.passed is True

    def test_parse_with_surrounding_whitespace(self) -> None:
        """Surrounding whitespace should be stripped."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_line

        result = parse_hook_line("  refurb ❌  ")
        assert result.hook_name == "refurb"
        assert result.passed is False

    def test_parse_empty_line_raises(self) -> None:
        """Empty line should raise ParseError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_line,
        )

        with pytest.raises(ParseError, match="empty line"):
            parse_hook_line("")

    def test_parse_whitespace_only_raises(self) -> None:
        """Whitespace-only line should raise ParseError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_line,
        )

        with pytest.raises(ParseError, match="empty line"):
            parse_hook_line("    \t  ")

    def test_parse_no_marker_raises(self) -> None:
        """Line with no marker should raise ParseError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_line,
        )

        with pytest.raises(ParseError, match="no space-separated status marker"):
            parse_hook_line("refurb")

    def test_parse_only_marker_raises(self) -> None:
        """Line with only marker (no name) should raise ParseError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_line,
        )

        with pytest.raises(ParseError, match="No hook name"):
            parse_hook_line("✅")

    def test_parse_unknown_marker_raises(self) -> None:
        """Unknown marker should raise ParseError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_line,
        )

        with pytest.raises(ParseError, match="Unknown status marker"):
            parse_hook_line("refurb ???")

    def test_parse_only_dots_raises(self) -> None:
        """Line of only dots before marker should raise."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_line,
        )

        with pytest.raises(ParseError, match="entirely of dots"):
            parse_hook_line(".... ✅")


class TestParseHookOutput:
    """Tests for the public parse_hook_output function."""

    def test_parse_empty_output(self) -> None:
        """Empty input should return empty list."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        assert parse_hook_output("") == []

    def test_parse_single_line_pass(self) -> None:
        """Single pass line should yield a single result."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        results = parse_hook_output("refurb... ✅")
        assert len(results) == 1
        assert results[0].hook_name == "refurb"
        assert results[0].passed is True

    def test_parse_single_line_fail(self) -> None:
        """Single fail line should yield a single result with passed=False."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        results = parse_hook_output("refurb... ❌")
        assert len(results) == 1
        assert results[0].hook_name == "refurb"
        assert results[0].passed is False

    def test_parse_multiple_lines(self) -> None:
        """Multiple lines should yield multiple results in order."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = (
            "refurb... ✅\n"
            "complexity... ❌\n"
            "coverage... Passed\n"
            "security... Failed"
        )
        results = parse_hook_output(output)
        assert len(results) == 4
        assert results[0] == ("refurb", True)
        assert results[1] == ("complexity", False)
        assert results[2] == ("coverage", True)
        assert results[3] == ("security", False)

    def test_parse_skips_empty_lines(self) -> None:
        """Empty lines should be skipped silently."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = (
            "\n"
            "refurb... ✅\n"
            "\n"
            "coverage... ❌\n"
            "   \n"
            "complexity... Passed\n"
        )
        results = parse_hook_output(output)
        assert len(results) == 3
        assert [r.hook_name for r in results] == ["refurb", "coverage", "complexity"]

    def test_parse_skips_whitespace_only_lines(self) -> None:
        """Whitespace-only lines should be skipped silently."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = "refurb ✅\n\t\t\n   \ncomplexity ❌"
        results = parse_hook_output(output)
        assert len(results) == 2

    def test_parse_invalid_line_raises_with_line_number(self) -> None:
        """ParseError should include the line number in the message."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_output,
        )

        output = "refurb ✅\nbroken\ncomplexity ❌"
        with pytest.raises(ParseError, match="Line 2:"):
            parse_hook_output(output)

    def test_parse_invalid_line_preserves_chain(self) -> None:
        """ParseError should chain the original exception via 'from'."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_output,
        )

        output = "refurb ???"  # invalid marker
        with pytest.raises(ParseError) as exc_info:
            parse_hook_output(output)
        # The original ParseError should be the cause
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ParseError)

    def test_parse_first_line_invalid_raises(self) -> None:
        """Invalid first line should raise."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_output,
        )

        with pytest.raises(ParseError, match="Line 1:"):
            parse_hook_output("no_marker")

    def test_parse_last_line_invalid_raises(self) -> None:
        """Invalid last line should raise with correct line number."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            parse_hook_output,
        )

        output = "refurb ✅\ncoverage ❌\nbroken"
        with pytest.raises(ParseError, match="Line 3:"):
            parse_hook_output(output)

    def test_parse_mixed_passes_and_fails(self) -> None:
        """Mix of pass and fail lines should each get correct status."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = (
            "ruff ✅\n"
            "black ❌\n"
            "mypy Passed\n"
            "bandit Failed\n"
            "complexity ✅\n"
            "coverage ❌"
        )
        results = parse_hook_output(output)
        assert len(results) == 6
        statuses = [r.passed for r in results]
        assert statuses == [True, False, True, False, True, False]

    def test_parse_preserves_dotted_names(self) -> None:
        """Hook names with internal dots should be preserved exactly."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = "test.unit.module ✅\ncoverage.py ❌"
        results = parse_hook_output(output)
        assert [r.hook_name for r in results] == ["test.unit.module", "coverage.py"]


class TestExtractFailedHooks:
    """Tests for the public extract_failed_hooks function."""

    def test_extract_no_failures(self) -> None:
        """All-pass output should return an empty list."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            extract_failed_hooks,
        )

        output = "ruff ✅\ncoverage Passed\ncomplexity ✅"
        assert extract_failed_hooks(output) == []

    def test_extract_single_failure(self) -> None:
        """Single failure should be returned in the list."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            extract_failed_hooks,
        )

        output = "ruff ✅\ncomplexity ❌\ncoverage Passed"
        assert extract_failed_hooks(output) == ["complexity"]

    def test_extract_multiple_failures(self) -> None:
        """All failed hook names should be returned in order."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            extract_failed_hooks,
        )

        output = (
            "ruff ✅\n"
            "black ❌\n"
            "mypy ✅\n"
            "coverage Failed\n"
            "complexity ❌"
        )
        assert extract_failed_hooks(output) == ["black", "coverage", "complexity"]

    def test_extract_empty_output(self) -> None:
        """Empty output should return empty list."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            extract_failed_hooks,
        )

        assert extract_failed_hooks("") == []

    def test_extract_with_skipped_lines(self) -> None:
        """Empty lines should be skipped before extracting failures."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            extract_failed_hooks,
        )

        output = "\nruff ✅\n\nblack ❌\n   \ncomplexity Passed\n"
        assert extract_failed_hooks(output) == ["black"]

    def test_extract_propagates_parse_error(self) -> None:
        """Invalid lines should still raise ParseError."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            ParseError,
            extract_failed_hooks,
        )

        with pytest.raises(ParseError):
            extract_failed_hooks("no_marker")


class TestIntegrationScenarios:
    """End-to-end integration tests combining multiple features."""

    def test_real_world_crackerjack_output(self) -> None:
        """Should parse realistic crackerjack output."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = """
pre-commit-commitmsg............................................... ✅
ruff-check......................................................... ❌
ruff-format....................................................... ✅
complexity-check.................................................. ❌
coverage-check.................................................... ✅
"""
        results = parse_hook_output(output)
        assert len(results) == 5
        names = [r.hook_name for r in results]
        assert "ruff-check" in names
        assert "complexity-check" in names

    def test_pass_and_fail_in_same_output(self) -> None:
        """Should distinguish pass from fail correctly in same output."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            extract_failed_hooks,
        )

        output = (
            "hook_a... ✅\n"
            "hook_b... ❌\n"
            "hook_c... Passed\n"
            "hook_d... Failed"
        )
        failed = extract_failed_hooks(output)
        assert failed == ["hook_b", "hook_d"]

    def test_unicode_only_markers_acceptable(self) -> None:
        """Unicode markers should be acceptable throughout."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = "alpha ✅\nbeta ❌\ngamma ✅\ndelta ❌"
        results = parse_hook_output(output)
        assert [r.passed for r in results] == [True, False, True, False]

    def test_word_only_markers_acceptable(self) -> None:
        """Word markers should be acceptable throughout."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = "alpha Passed\nbeta Failed\ngamma Passed"
        results = parse_hook_output(output)
        assert [r.passed for r in results] == [True, False, True]

    def test_mixed_markers_acceptable(self) -> None:
        """Mixing unicode and word markers in same output should work."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import parse_hook_output

        output = "alpha ✅\nbeta Failed\ngamma Passed\ndelta ❌"
        results = parse_hook_output(output)
        assert [r.passed for r in results] == [True, False, True, False]


class TestModuleSurface:
    """Tests for module-level surface (imports, exports)."""

    def test_module_imports_successfully(self) -> None:
        """The module should import without side effects beyond defining symbols."""
        import importlib

        module = importlib.import_module(
            "session_buddy.mcp.tools.infrastructure.hook_parser",
        )
        assert module is not None

    def test_module_has_expected_exports(self) -> None:
        """Module should expose the documented public symbols."""
        import importlib

        module = importlib.import_module(
            "session_buddy.mcp.tools.infrastructure.hook_parser",
        )
        # Public API surface
        assert hasattr(module, "HookResult")
        assert hasattr(module, "ParseError")
        assert hasattr(module, "parse_hook_line")
        assert hasattr(module, "parse_hook_output")
        assert hasattr(module, "extract_failed_hooks")
        # Private helpers (also exposed at module level)
        assert hasattr(module, "_validate_line")
        assert hasattr(module, "_extract_parts")
        assert hasattr(module, "_validate_status_marker")
        assert hasattr(module, "_extract_hook_name")
        assert hasattr(module, "_PASS_MARKERS")
        assert hasattr(module, "_FAIL_MARKERS")
        assert hasattr(module, "_ALL_MARKERS")

    def test_marker_constants_immutable(self) -> None:
        """Marker constants should not be modifiable."""
        from session_buddy.mcp.tools.infrastructure.hook_parser import (
            _ALL_MARKERS,
            _FAIL_MARKERS,
            _PASS_MARKERS,
        )

        # frozensets raise on mutation
        for marker_set in (_PASS_MARKERS, _FAIL_MARKERS, _ALL_MARKERS):
            with pytest.raises(AttributeError):
                marker_set.add("new_marker")  # type: ignore[attr-defined]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov", "--tb=short"])
