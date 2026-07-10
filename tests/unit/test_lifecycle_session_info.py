"""Tests for session_buddy.core.lifecycle.session_info.

Covers SessionInfo dataclass, file discovery, parsing, recommendation
extraction, and the read_previous_session_info async helper.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from session_buddy.core.lifecycle.session_info import (
    SessionInfo,
    discover_session_files,
    extract_session_metadata,
    extract_session_recommendations,
    find_latest_handoff_file,
    parse_session_file,
    read_file_safely,
    read_previous_session_info,
)


# ---------------------------------------------------------------------------
# SessionInfo dataclass
# ---------------------------------------------------------------------------


class TestSessionInfo:
    """Verify the frozen SessionInfo dataclass behavior."""

    def test_default_values_are_empty_strings(self) -> None:
        info = SessionInfo()
        assert info.session_id == ""
        assert info.ended_at == ""
        assert info.quality_score == ""
        assert info.working_directory == ""
        assert info.top_recommendation == ""

    def test_empty_classmethod_returns_defaults(self) -> None:
        info = SessionInfo.empty()
        assert info == SessionInfo()
        assert info.is_complete() is False

    def test_is_complete_false_when_missing_field(self) -> None:
        # Missing ended_at
        info = SessionInfo(
            quality_score="85",
            working_directory="/tmp",
        )
        assert info.is_complete() is False

        # Missing quality_score
        info = SessionInfo(
            ended_at="2026-01-01",
            working_directory="/tmp",
        )
        assert info.is_complete() is False

        # Missing working_directory
        info = SessionInfo(
            ended_at="2026-01-01",
            quality_score="85",
        )
        assert info.is_complete() is False

    def test_is_complete_true_with_all_required_fields(self) -> None:
        info = SessionInfo(
            ended_at="2026-01-01",
            quality_score="85",
            working_directory="/tmp",
        )
        assert info.is_complete() is True

    def test_is_complete_treats_falsy_strings_as_missing(self) -> None:
        # Empty strings should make is_complete False (covered by bool() check)
        info = SessionInfo(
            ended_at="",
            quality_score="85",
            working_directory="/tmp",
        )
        assert info.is_complete() is False

    def test_from_dict_with_all_keys(self) -> None:
        data = {
            "session_id": "abc-123",
            "ended_at": "2026-05-01",
            "quality_score": "90",
            "working_directory": "/workspace",
            "top_recommendation": "Refactor module X",
        }
        info = SessionInfo.from_dict(data)
        assert info.session_id == "abc-123"
        assert info.ended_at == "2026-05-01"
        assert info.quality_score == "90"
        assert info.working_directory == "/workspace"
        assert info.top_recommendation == "Refactor module X"

    def test_from_dict_missing_keys_default_to_empty(self) -> None:
        info = SessionInfo.from_dict({})
        assert info.session_id == ""
        assert info.ended_at == ""
        assert info.quality_score == ""
        assert info.working_directory == ""
        assert info.top_recommendation == ""

    def test_from_dict_partial_keys(self) -> None:
        info = SessionInfo.from_dict({"session_id": "xyz", "quality_score": "70"})
        assert info.session_id == "xyz"
        assert info.quality_score == "70"
        assert info.ended_at == ""
        assert info.working_directory == ""
        assert info.top_recommendation == ""

    def test_from_dict_extra_keys_are_ignored(self) -> None:
        info = SessionInfo.from_dict(
            {"session_id": "abc", "extra_unused": "value", "another": 42},
        )
        assert info.session_id == "abc"

    def test_frozen_dataclass_rejects_mutation(self) -> None:
        info = SessionInfo(session_id="x")
        with pytest.raises((AttributeError, Exception)):
            info.session_id = "y"  # type: ignore[misc]

    def test_equality_via_dataclass(self) -> None:
        a = SessionInfo(session_id="abc", quality_score="90")
        b = SessionInfo(session_id="abc", quality_score="90")
        assert a == b

        c = SessionInfo(session_id="abc", quality_score="85")
        assert a != c


# ---------------------------------------------------------------------------
# extract_session_metadata
# ---------------------------------------------------------------------------


class TestExtractSessionMetadata:
    """Verify markdown header parsing into metadata dict."""

    def test_extracts_all_three_known_fields(self) -> None:
        lines = [
            "**Session ended:** 2026-05-25T09:00:00",
            "**Final quality score:** 87",
            "**Working directory:** /tmp/project",
        ]
        info = extract_session_metadata(lines)
        assert info == {
            "ended_at": "2026-05-25T09:00:00",
            "quality_score": "87",
            "working_directory": "/tmp/project",
        }

    def test_empty_lines_returns_empty_dict(self) -> None:
        assert extract_session_metadata([]) == {}

    def test_unrelated_lines_returns_empty_dict(self) -> None:
        assert extract_session_metadata(["# Heading", "Some text"]) == {}

    def test_partial_fields(self) -> None:
        lines = [
            "**Session ended:** 2026-05-25T09:00:00",
            "unrelated line",
        ]
        info = extract_session_metadata(lines)
        assert info == {"ended_at": "2026-05-25T09:00:00"}

    def test_strips_whitespace_around_values(self) -> None:
        lines = ["**Session ended:**   2026-05-25T09:00:00   "]
        info = extract_session_metadata(lines)
        assert info["ended_at"] == "2026-05-25T09:00:00"

    def test_handles_value_with_internal_colons(self) -> None:
        # Splitting on the field label string leaves "key: value" structure intact
        lines = ["**Working directory:** /tmp:project/sub"]
        info = extract_session_metadata(lines)
        assert info["working_directory"] == "/tmp:project/sub"

    def test_quality_score_with_decimals(self) -> None:
        lines = ["**Final quality score:** 87.5"]
        info = extract_session_metadata(lines)
        assert info["quality_score"] == "87.5"


# ---------------------------------------------------------------------------
# extract_session_recommendations
# ---------------------------------------------------------------------------


class TestExtractSessionRecommendations:
    """Verify the first-recommendation extractor."""

    def test_extracts_first_numbered_recommendation(self) -> None:
        info: dict[str, str] = {}
        lines = [
            "## Recommendations for Next Session",
            "",
            "1. Do the thing",
            "2. Also do this",
        ]
        extract_session_recommendations(lines, info)
        assert info["top_recommendation"] == "Do the thing"

    def test_no_recommendations_section_does_nothing(self) -> None:
        info: dict[str, str] = {}
        lines = ["## Other Section", "1. Not a recommendation"]
        extract_session_recommendations(lines, info)
        assert info == {}

    def test_stops_at_next_section_heading(self) -> None:
        info: dict[str, str] = {}
        lines = [
            "## Recommendations for Next Session",
            "",
            "## Context",  # No numbered list - just a heading
            "1. Should not be picked up",
        ]
        extract_session_recommendations(lines, info)
        assert "top_recommendation" not in info

    def test_recommendation_section_with_blank_line_before_numbered_item(self) -> None:
        info: dict[str, str] = {}
        lines = [
            "## Recommendations for Next Session",
            "",
            "1.   First item",
        ]
        extract_session_recommendations(lines, info)
        assert info["top_recommendation"] == "First item"

    def test_recommendation_with_leading_whitespace(self) -> None:
        # Implementation uses .strip().startswith("1."), so leading whitespace
        # in the line is tolerated
        info: dict[str, str] = {}
        lines = [
            "## Recommendations for Next Session",
            "",
            "  1. Indented first item",
        ]
        extract_session_recommendations(lines, info)
        assert info["top_recommendation"] == "Indented first item"

    def test_section_with_only_unnumbered_content(self) -> None:
        info: dict[str, str] = {}
        lines = [
            "## Recommendations for Next Session",
            "Some prose",
            "## End",
        ]
        extract_session_recommendations(lines, info)
        assert "top_recommendation" not in info

    def test_section_heading_inside_text_uses_first_match(self) -> None:
        info: dict[str, str] = {}
        lines = [
            "Some text ## Recommendations for Next Session embedded",
            "1. Not picked up — heading must be on its own line",
        ]
        extract_session_recommendations(lines, info)
        # Implementation checks if substring is in line; "in" returns True here
        # so it will treat this as entering the section, but then look for "1."
        # and find one. Document current behavior.
        assert info.get("top_recommendation") == (
            "Not picked up — heading must be on its own line"
        )


# ---------------------------------------------------------------------------
# find_latest_handoff_file
# ---------------------------------------------------------------------------


class TestFindLatestHandoffFile:
    """Verify discovery of the most recent handoff file."""

    def test_returns_none_for_missing_directory(self, tmp_path: Path) -> None:
        assert find_latest_handoff_file(tmp_path) is None

    def test_returns_none_when_no_handoff_files_exist(self, tmp_path: Path) -> None:
        # Create the .crackerjack handoff dir but leave it empty
        (tmp_path / ".crackerjack" / "session" / "handoff").mkdir(parents=True)
        assert find_latest_handoff_file(tmp_path) is None

    def test_returns_most_recent_from_filename(self, tmp_path: Path) -> None:
        handoff_dir = tmp_path / ".crackerjack" / "session" / "handoff"
        handoff_dir.mkdir(parents=True)
        older = handoff_dir / "session_handoff_20240524.md"
        newer = handoff_dir / "session_handoff_20240525.md"
        older.write_text("older", encoding="utf-8")
        newer.write_text("newer", encoding="utf-8")

        result = find_latest_handoff_file(tmp_path)
        # Filenames sort lexicographically — newer is later
        assert result == newer

    def test_falls_back_to_legacy_files_in_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os
        from datetime import datetime, timezone

        legacy_a = tmp_path / "session_handoff_20240523.md"
        legacy_b = tmp_path / "session_handoff_20240524.md"
        legacy_a.write_text("a", encoding="utf-8")
        legacy_b.write_text("b", encoding="utf-8")

        old_time = datetime(2024, 5, 23, tzinfo=timezone.utc).timestamp()
        new_time = datetime(2024, 5, 24, tzinfo=timezone.utc).timestamp()
        os.utime(legacy_a, (old_time, old_time))
        os.utime(legacy_b, (new_time, new_time))

        result = find_latest_handoff_file(tmp_path)
        # The legacy branch returns the most recently modified file
        assert result == legacy_b

    def test_prefers_canonical_dir_over_legacy(self, tmp_path: Path) -> None:
        # Both legacy root files AND canonical .crackerjack handoff exist
        handoff_dir = tmp_path / ".crackerjack" / "session" / "handoff"
        handoff_dir.mkdir(parents=True)
        canonical = handoff_dir / "session_handoff_20240525.md"
        canonical.write_text("canonical", encoding="utf-8")

        legacy = tmp_path / "session_handoff_20240524.md"
        legacy.write_text("legacy", encoding="utf-8")

        result = find_latest_handoff_file(tmp_path)
        assert result == canonical

    def test_handles_oserror_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Replace Path.exists with a raising version to exercise the except clause
        def _raise(self: Path) -> bool:  # type: ignore[no-redef]
            raise OSError("boom")

        monkeypatch.setattr(Path, "exists", _raise)
        assert find_latest_handoff_file(tmp_path) is None


# ---------------------------------------------------------------------------
# discover_session_files
# ---------------------------------------------------------------------------


class TestDiscoverSessionFiles:
    """Verify ordered candidate discovery."""

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        assert discover_session_files(tmp_path) == []

    def test_first_candidate_present_only(self, tmp_path: Path) -> None:
        (tmp_path / "session_handoff.md").write_text("a", encoding="utf-8")
        result = discover_session_files(tmp_path)
        assert result == [tmp_path / "session_handoff.md"]

    def test_second_candidate_present_only(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        target = tmp_path / ".claude" / "session_handoff.md"
        target.write_text("a", encoding="utf-8")
        result = discover_session_files(tmp_path)
        assert result == [target]

    def test_third_candidate_present_only(self, tmp_path: Path) -> None:
        target = tmp_path / "session_summary.md"
        target.write_text("a", encoding="utf-8")
        result = discover_session_files(tmp_path)
        assert result == [target]

    def test_multiple_candidates_returned_in_priority_order(
        self, tmp_path: Path
    ) -> None:
        first = tmp_path / "session_handoff.md"
        second = tmp_path / ".claude" / "session_handoff.md"
        third = tmp_path / "session_summary.md"
        first.write_text("a", encoding="utf-8")
        second.parent.mkdir(parents=True)
        second.write_text("b", encoding="utf-8")
        third.write_text("c", encoding="utf-8")
        result = discover_session_files(tmp_path)
        # Order is fixed: canonical, .claude variant, summary
        assert result == [first, second, third]


# ---------------------------------------------------------------------------
# read_file_safely (async)
# ---------------------------------------------------------------------------


class TestReadFileSafely:
    """Verify async file reading with error suppression."""

    async def test_reads_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "data.txt"
        target.write_text("hello world", encoding="utf-8")
        assert await read_file_safely(target) == "hello world"

    async def test_returns_empty_string_for_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "absent.txt"
        assert await read_file_safely(missing) == ""

    async def test_returns_empty_string_on_oserror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "data.txt"
        target.write_text("data", encoding="utf-8")

        def _boom_open(self: Path, *args: object, **kwargs: object):  # type: ignore[no-redef]
            raise OSError("disk error")

        monkeypatch.setattr(Path, "open", _boom_open)
        assert await read_file_safely(target) == ""


# ---------------------------------------------------------------------------
# parse_session_file (async)
# ---------------------------------------------------------------------------


class TestParseSessionFile:
    """Verify full handoff file parsing pipeline."""

    async def test_parses_complete_handoff(self, tmp_path: Path) -> None:
        handoff = tmp_path / "session_handoff_20260525.md"
        handoff.write_text(
            "\n".join(
                [
                    "# Session Handoff Report - demo",
                    "",
                    "**Session ended:** 2026-05-25T09:00:00",
                    "**Final quality score:** 87",
                    "**Working directory:** /tmp/project",
                    "",
                    "## Recommendations for Next Session",
                    "",
                    "1. Do the thing",
                ]
            ),
            encoding="utf-8",
        )

        info = await parse_session_file(handoff)
        assert info.ended_at == "2026-05-25T09:00:00"
        assert info.quality_score == "87"
        assert info.working_directory == "/tmp/project"
        assert info.top_recommendation == "Do the thing"
        assert info.is_complete() is True

    async def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "absent.md"
        info = await parse_session_file(missing)
        assert info == SessionInfo.empty()

    async def test_returns_empty_for_garbage_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.md"
        bad.write_text("completely unrelated content", encoding="utf-8")
        info = await parse_session_file(bad)
        assert info == SessionInfo.empty()

    async def test_returns_empty_when_metadata_extraction_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "data.md"
        target.write_text("**Session ended:** 2026-05-25T09:00:00", encoding="utf-8")

        def _boom(_lines: list[str]) -> dict[str, str]:
            raise ValueError("explode")

        monkeypatch.setattr(
            "session_buddy.core.lifecycle.session_info.extract_session_metadata",
            _boom,
        )
        info = await parse_session_file(target)
        assert info == SessionInfo.empty()


# ---------------------------------------------------------------------------
# read_previous_session_info (async)
# ---------------------------------------------------------------------------


class TestReadPreviousSessionInfo:
    """Verify the public async reader helper."""

    async def test_returns_dict_for_complete_handoff(self, tmp_path: Path) -> None:
        handoff = tmp_path / "session_handoff_20260525.md"
        handoff.write_text(
            "\n".join(
                [
                    "**Session ended:** 2026-05-25T09:00:00",
                    "**Final quality score:** 87",
                    "**Working directory:** /tmp/project",
                    "",
                    "## Recommendations for Next Session",
                    "",
                    "1. Do the thing",
                ]
            ),
            encoding="utf-8",
        )

        result = await read_previous_session_info(handoff)
        assert result == {
            "ended_at": "2026-05-25T09:00:00",
            "quality_score": "87",
            "working_directory": "/tmp/project",
            "top_recommendation": "Do the thing",
        }

    async def test_returns_none_for_incomplete_handoff(self, tmp_path: Path) -> None:
        handoff = tmp_path / "incomplete.md"
        handoff.write_text("not enough", encoding="utf-8")
        result = await read_previous_session_info(handoff)
        assert result is None

    async def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "absent.md"
        result = await read_previous_session_info(missing)
        assert result is None

    async def test_returns_none_when_parse_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "data.md"
        target.write_text("data", encoding="utf-8")

        async def _boom(_file_path: Path) -> SessionInfo:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(
            "session_buddy.core.lifecycle.session_info.parse_session_file",
            _boom,
        )
        assert await read_previous_session_info(target) is None


# ---------------------------------------------------------------------------
# Async bridge — exercises asyncio.run from synchronous test bodies
# ---------------------------------------------------------------------------


def test_async_helpers_are_coroutine_functions() -> None:
    """Sanity: each async helper is a coroutine function."""
    import inspect

    assert inspect.iscoroutinefunction(read_file_safely)
    assert inspect.iscoroutinefunction(parse_session_file)
    assert inspect.iscoroutinefunction(read_previous_session_info)


def test_sync_invocation_via_asyncio_run(tmp_path: Path) -> None:
    """Smoke test the async helpers when run from sync code paths."""
    handoff = tmp_path / "session_handoff_20260525.md"
    handoff.write_text(
        "\n".join(
            [
                "**Session ended:** 2026-05-25T09:00:00",
                "**Final quality score:** 87",
                "**Working directory:** /tmp/project",
            ]
        ),
        encoding="utf-8",
    )

    parsed = asyncio.run(parse_session_file(handoff))
    assert parsed.ended_at == "2026-05-25T09:00:00"
    assert parsed.is_complete() is True
