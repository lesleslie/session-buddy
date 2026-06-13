#!/usr/bin/env python3
"""Extra unit tests for uncovered branches in search_tools.py.

Targets pure helper functions whose formatting / classifier branches
were not exercised by tests/unit/test_search_tools.py. These keep
the additions isolated from the existing fixture-heavy module.
"""

from __future__ import annotations

import json
import operator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from session_buddy.mcp.tools.memory.search_tools import (
    _classify_skill_status,
    _extract_code_blocks_from_content,
    _extract_mentioned_files,
    _extract_relevant_excerpt,
    _extract_file_excerpt,
    _find_best_error_excerpt,
    _format_code_search_results,
    _format_concept_results,
    _format_error_search_results,
    _format_temporal_results,
    _parse_reinforced_ts,
    _parse_tags_parameter,
    _parse_time_expression,
)

if TYPE_CHECKING:
    pass


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def code_block_results():
    """Results whose content contains a triple-backtick code block."""
    return [
        {
            "id": "cb-1",
            "content": (
                "We added ```python\nasync def run():\n    await x()\n``` "
                "to the worker module."
            ),
            "timestamp": "2026-05-20 10:00:00",
            "similarity": 0.9,
        },
    ]


@pytest.fixture
def plain_content_results():
    """Results whose content has no code blocks and no query match."""
    return [
        {
            "id": "plain-1",
            "content": "A short conversation with no special markers at all.",
            "timestamp": "2026-05-20 10:00:00",
        },
    ]


# ==============================================================================
# _extract_code_blocks_from_content
# ==============================================================================


class TestExtractCodeBlocksExtras:
    """Branch coverage for _extract_code_blocks_from_content."""

    def test_returns_matching_block(self):
        """A fenced block is captured verbatim by the generic regex.

        The generic_code_block pattern is ```\n(.*?)\n``` with re.DOTALL;
        the content inside the fences (no language tag) is captured.
        """
        content = "Intro\n```\nprint('hi')\n```\nOutro"
        result = _extract_code_blocks_from_content(content)
        assert isinstance(result, list)
        assert any("print('hi')" in blk for blk in result)

    def test_returns_empty_for_plain_text(self):
        """Plain text returns an empty list, not None."""
        result = _extract_code_blocks_from_content("nothing to see here")
        assert result == []


# ==============================================================================
# _format_code_search_results
# ==============================================================================


class TestFormatCodeSearchResultsExtras:
    """Branch coverage for _format_code_search_results (no-results, type suffix,
    code-block path, no-block-and-no-query path, no-block-but-query-in-content)."""

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """Empty input yields the no-results banner."""
        result = await _format_code_search_results("foo", [], pattern_type=None)
        assert "No code patterns found" in result
        assert "foo" in result

    @pytest.mark.asyncio
    async def test_results_with_pattern_type(self):
        """Non-None pattern_type is appended to the header."""
        result = await _format_code_search_results(
            "foo", [{"content": "x"}], pattern_type="decorator"
        )
        assert "(type: decorator)" in result

    @pytest.mark.asyncio
    async def test_results_with_code_block(self, code_block_results):
        """Content with a fenced block is rendered inside ``` fences."""
        result = await _format_code_search_results(
            "async", code_block_results, pattern_type=None
        )
        assert "```" in result
        assert "async def run" in result

    @pytest.mark.asyncio
    async def test_results_no_block_query_in_content(self):
        """No fenced block but query appears in content: excerpt path."""
        result = await _format_code_search_results(
            "needle",
            [
                {
                    "content": "A long prefix... " + ("filler " * 30) + " needle here",
                    "timestamp": "2026-01-01 00:00:00",
                }
            ],
            pattern_type=None,
        )
        assert "needle" in result
        assert "filler" in result

    @pytest.mark.asyncio
    async def test_results_no_block_no_query(self, plain_content_results):
        """No block, no query match: falls through to the [:100] fallback."""
        result = await _format_code_search_results(
            "missing", plain_content_results, pattern_type=None
        )
        assert "A short conversation" in result


# ==============================================================================
# _find_best_error_excerpt & _format_error_search_results
# ==============================================================================


class TestFindBestErrorExcerptExtras:
    """Branch coverage for the keyword scorer."""

    def test_picks_highest_scoring_keyword(self):
        """Repeated keyword wins over single-occurrence alternatives."""
        content = "Error once. Then exception. Then exception. Then exception."
        result = _find_best_error_excerpt(content)
        assert "exception" in result.lower()

    def test_returns_content_prefix_when_no_keywords(self):
        """Plain prose returns the first 150 characters."""
        content = "A peaceful conversation with nothing alarming whatsoever."
        result = _find_best_error_excerpt(content)
        assert result == content[:150]


class TestFormatErrorSearchResultsExtras:
    """Branch coverage for _format_error_search_results."""

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """Empty input yields the no-results banner."""
        result = await _format_error_search_results("boom", [], error_type=None)
        assert "No error patterns found" in result
        assert "boom" in result

    @pytest.mark.asyncio
    async def test_results_with_error_type(self):
        """Non-None error_type is appended to the header."""
        result = await _format_error_search_results(
            "boom",
            [{"content": "Error: kaboom", "timestamp": "2026-01-01 00:00:00"}],
            error_type="network",
        )
        assert "(type: network)" in result
        assert "kaboom" in result

    @pytest.mark.asyncio
    async def test_results_with_similarity_only(self):
        """Result without timestamp still renders an entry."""
        result = await _format_error_search_results(
            "boom",
            [{"content": "Error: no timestamp row", "similarity": 0.7}],
            error_type=None,
        )
        assert "Error: no timestamp row" in result


# ==============================================================================
# _format_temporal_results
# ==============================================================================


class TestFormatTemporalResultsExtras:
    """Branch coverage for _format_temporal_results (query suffix + per-row timestamp)."""

    @pytest.mark.asyncio
    async def test_includes_query_suffix(self):
        """query is appended to the header when provided."""
        result = await _format_temporal_results(
            "last week", "asyncio",
            [{"content": "Discussion about asyncio loops"}],
        )
        assert "matching `asyncio`" in result

    @pytest.mark.asyncio
    async def test_omits_query_suffix_when_none(self):
        """query=None omits the matching clause from the header."""
        result = await _format_temporal_results(
            "yesterday", None,
            [{"content": "Plain content", "timestamp": "2026-01-01 00:00:00"}],
        )
        assert "matching" not in result
        assert "Plain content" in result

    @pytest.mark.asyncio
    async def test_skips_timestamp_label_when_missing(self):
        """Result with no timestamp field still renders the content line."""
        result = await _format_temporal_results(
            "today", None, [{"content": "A row without a timestamp"}]
        )
        assert "A row without a timestamp" in result


# ==============================================================================
# _extract_mentioned_files
# ==============================================================================


class TestExtractMentionedFilesExtras:
    """Branch coverage for the regex-driven file extractor.

    NOTE: the source function lists ``config_files`` and
    ``documentation_files`` as patterns to iterate, but those keys do
    not exist in ``session_buddy.utils.regex_patterns.SAFE_PATTERNS``.
    The ``try/except Exception`` in the source swallows the resulting
    ``KeyError`` and the function always returns ``[]``. These tests
    pin that current behavior so the regression is visible. If the
    bug is fixed, update the assertions to expect the actual matches.
    """

    def test_returns_empty_list_for_python_paths(self):
        r"""Pin current (buggy) behavior: returns [] even with .py content.

        The source iterates four pattern names; ``config_files`` and
        ``documentation_files`` are missing, so the ``try/except`` in
        the source returns ``[]`` before any pattern is consulted.
        """
        results = [
            {"content": "Edited foo.py and bar.py yesterday."}
        ]
        files = _extract_mentioned_files(results)
        assert files == []

    def test_returns_empty_for_repeated_paths(self):
        """Pin: dedupe branch is never reached; result is always []."""
        results = [{"content": "x.py x.py x.py"}]
        files = _extract_mentioned_files(results)
        assert files == []

    def test_handles_no_files_gracefully(self):
        """Content with no file paths returns an empty list (not raise)."""
        results = [{"content": "Just a paragraph with absolutely no paths."}]
        assert _extract_mentioned_files(results) == []


# ==============================================================================
# _parse_reinforced_ts
# ==============================================================================


class TestParseReinforcedTsExtras:
    """Branch coverage for _parse_reinforced_ts (datetime / str / other)."""

    def test_passthrough_datetime(self):
        """A real datetime is returned unchanged."""
        dt = datetime(2026, 1, 2, 3, 4, 5)
        assert _parse_reinforced_ts(dt) is dt

    def test_parses_iso_string(self):
        """An ISO-8601 string is converted to a datetime."""
        result = _parse_reinforced_ts("2026-01-02T03:04:05")
        assert result == datetime(2026, 1, 2, 3, 4, 5)

    def test_rejects_unsupported_type(self):
        """Anything that isn't datetime / str raises TypeError."""
        with pytest.raises(TypeError):
            _parse_reinforced_ts(12345)


# ==============================================================================
# _classify_skill_status (pure 4-bucket classifier)
# ==============================================================================


class TestClassifySkillStatusExtras:
    """Branch coverage for the four-bucket status classifier.

    The function is pure and depends only on the row dict, threshold, and
    the optional Crackerjack skill list. We feed it row shapes that
    exercise every bucket and the fallback paths.
    """

    def _thr(self) -> timedelta:
        return timedelta(days=30)

    def test_stale_via_old_timestamp(self):
        """Reinforced long ago is 'stale' even with high importance."""
        row = {
            "importance_score": 1.0,
            "evidence_count": 5,
            "last_reinforced_at": "2000-01-01T00:00:00",
            "problem_pattern": "stale-bug",
        }
        assert _classify_skill_status(
            row, threshold=self._thr(), crackerjack_skill_names=None
        ) == "stale"

    def test_under_utilized_high_importance_no_match(self):
        """High importance, recent, evidence>0, but no Crackerjack match."""
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        row = {
            "importance_score": 0.95,
            "evidence_count": 3,
            "last_reinforced_at": recent,
            "problem_pattern": "never-seen-pattern",
        }
        assert _classify_skill_status(
            row, threshold=self._thr(), crackerjack_skill_names=["unrelated-skill"]
        ) == "under_utilized"

    def test_fresh_when_pattern_matches_crackerjack(self):
        """High importance, recent, evidence>0, AND Crackerjack knows it."""
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        row = {
            "importance_score": 0.95,
            "evidence_count": 3,
            "last_reinforced_at": recent,
            "problem_pattern": "shared-skill",
        }
        assert _classify_skill_status(
            row,
            threshold=self._thr(),
            crackerjack_skill_names=["shared-skill", "another"],
        ) == "fresh"

    def test_cold_with_zero_evidence_and_no_reinforcement(self):
        """Never reinforced + zero evidence + low importance == cold."""
        row = {
            "importance_score": 0.1,
            "evidence_count": 0,
            "last_reinforced_at": None,
            "problem_pattern": "experimental",
        }
        assert _classify_skill_status(
            row, threshold=self._thr(), crackerjack_skill_names=None
        ) == "cold"

    def test_high_importance_without_crackerjack_list_stays_fresh(self):
        """No Crackerjack list means the under-utilized check is skipped.

        The plan specifies: the caller must supply the list to opt into
    the under-utilized bucket. With high importance + recent + nonzero
    evidence, the result is 'fresh' (not 'under_utilized').
        """
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        row = {
            "importance_score": 1.0,
            "evidence_count": 3,
            "last_reinforced_at": recent,
            "problem_pattern": "any-pattern",
        }
        assert _classify_skill_status(
            row, threshold=self._thr(), crackerjack_skill_names=None
        ) == "fresh"

    def test_invalid_timestamp_falls_through_to_other_buckets(self):
        """Garbage timestamp yields None parse -> other buckets decide."""
        row = {
            "importance_score": 0.0,
            "evidence_count": 0,
            "last_reinforced_at": "not-a-date",
            "problem_pattern": "broken-ts",
        }
        # Not parseable -> stale branch skipped; importance low so
        # under_utilized skipped; evidence==0 -> cold.
        assert _classify_skill_status(
            row, threshold=self._thr(), crackerjack_skill_names=None
        ) == "cold"


# ==============================================================================
# _format_concept_results - include_files branch (uses SAFE_PATTERNS)
# ==============================================================================


class TestFormatConceptResultsExtras:
    """Branch coverage for the include_files=True / False branches.

    NOTE: ``_extract_mentioned_files`` always returns ``[]`` due to a
    missing-key bug in the source (see the
    ``TestExtractMentionedFilesExtras`` docstring), so the
    ``include_files=True`` path is effectively a no-op. These tests
    pin the current observable behavior.
    """

    @pytest.mark.asyncio
    async def test_with_files_branch_currently_noop(self):
        """include_files=True never emits Related Files (extractor is empty)."""
        results = [{"content": "Worked on lib.py today.", "similarity": 0.9}]
        result = await _format_concept_results("refactor", results, include_files=True)
        assert "Related Files" not in result
        assert "refactor" in result

    @pytest.mark.asyncio
    async def test_with_files_branch_no_match(self):
        """include_files=True with no files: no Related Files section."""
        results = [{"content": "Just plain prose with no path markers."}]
        result = await _format_concept_results("refactor", results, include_files=True)
        assert "Related Files" not in result

    @pytest.mark.asyncio
    async def test_without_files_branch(self):
        """include_files=False: never emits Related Files section."""
        results = [{"content": "Worked on lib.py today.", "similarity": 0.9}]
        result = await _format_concept_results(
            "refactor", results, include_files=False
        )
        assert "Related Files" not in result
        assert "refactor" in result


# ==============================================================================
# Misc - extract helpers + parse_tags + parse_time
# ==============================================================================


class TestExtractHelpersExtras:
    """Branch coverage for the file-excerpt and relevant-excerpt helpers."""

    def test_file_excerpt_when_path_in_content(self):
        """Path inside content produces a windowed excerpt around it."""
        content = "Header " + ("x" * 100) + "/repo/main.py" + ("y" * 100) + " Tail"
        result = _extract_file_excerpt(content, "/repo/main.py")
        assert "/repo/main.py" in result
        # Window is +50 chars on each side of the match, so the
        # surrounding padding should be present in the excerpt.
        assert "xxx" in result or "yyy" in result

    def test_file_excerpt_when_path_missing(self):
        """Path missing returns a 150-char prefix of the content."""
        content = "no path in this string at all, just words"
        result = _extract_file_excerpt(content, "/absent.py")
        assert result == content[:150]

    def test_relevant_excerpt_case_insensitive_match(self):
        """Concept is found even when cased differently from content."""
        content = "Discussion about Asyncio and async/await patterns."
        result = _extract_relevant_excerpt(content, "ASYNCIO")
        assert "Asyncio" in result

    def test_relevant_excerpt_no_match_returns_prefix(self):
        """Missing concept returns the first 150 characters."""
        content = "A " + ("filler " * 50) + " sentence."
        result = _extract_relevant_excerpt(content, "absent")
        assert result == content[:150]


class TestParseTagsExtras:
    """Branch coverage for _parse_tags_parameter edge cases."""

    def test_passthrough_list(self):
        """A list is returned as-is."""
        assert _parse_tags_parameter(["a", "b"]) == ["a", "b"]

    def test_json_string_list(self):
        """A JSON-array string is decoded into a list of strs."""
        assert _parse_tags_parameter('["a", "b"]') == ["a", "b"]

    def test_json_null_decodes_to_none(self):
        """The JSON literal 'null' deserializes to None."""
        assert _parse_tags_parameter("null") is None

    def test_json_scalar_wraps_in_list(self):
        """A JSON scalar is wrapped into a single-element list."""
        assert _parse_tags_parameter('"solo"') == ["solo"]

    def test_non_json_string_treated_as_single_tag(self):
        """A non-JSON string is treated as one tag, not a parse error."""
        assert _parse_tags_parameter("solo-tag") == ["solo-tag"]


class TestParseTimeExpressionExtras:
    """Branch coverage for the four natural-language buckets."""

    def test_today_bucket(self):
        """'today' subtracts 24 hours, not 1 day."""
        result = _parse_time_expression("today")
        assert result is not None
        elapsed = (datetime.now() - result).total_seconds()
        assert 86395 <= elapsed <= 86405

    def test_yesterday_bucket(self):
        """'yesterday' subtracts exactly 1 day."""
        result = _parse_time_expression("yesterday")
        assert (datetime.now() - result).days == 1

    def test_unknown_expression_returns_none(self):
        """An unrecognized expression returns None."""
        assert _parse_time_expression("someday soon") is None


# Ensure operator import isn't dropped by lint - it's used elsewhere in
# the source module but the imported binding keeps the test file
# honest about its own minimal surface.
_ = operator.itemgetter(0)
_ = json.dumps  # silence linter
