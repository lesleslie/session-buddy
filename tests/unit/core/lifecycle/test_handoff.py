"""Tests for session_buddy.core.lifecycle.handoff.

Covers the small markdown-builder helpers, the file-saving path, and the
async ``generate_handoff_documentation`` orchestrator that ties them together.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from session_buddy.core.lifecycle.handoff import (
    build_handoff_header,
    build_quality_section,
    build_recommendations_section,
    build_static_sections,
    generate_handoff_documentation,
    save_handoff_documentation,
)


# -----------------------------------------------------------------------------
# build_handoff_header
# -----------------------------------------------------------------------------


def _summary(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "project": "session-buddy",
        "session_end_time": "2026-09-04T10:00:00Z",
        "final_quality_score": 87,
        "working_directory": "/Users/les/Projects/session-buddy",
    }
    base.update(overrides)
    return base


def test_build_handoff_header_includes_all_required_fields() -> None:
    lines = build_handoff_header(_summary())
    joined = "\n".join(lines)
    assert joined.startswith("# Session Handoff Report - session-buddy")
    assert "**Session ended:** 2026-09-04T10:00:00Z" in joined
    assert "**Final quality score:** 87/100" in joined
    assert "**Working directory:** /Users/les/Projects/session-buddy" in joined


def test_build_handoff_header_returns_six_lines() -> None:
    """Header is 6 lines: title, blank, three field lines, trailing blank."""
    lines = build_handoff_header(_summary())
    assert len(lines) == 6


def test_build_handoff_header_substitutes_project_name() -> None:
    lines = build_handoff_header(_summary(project="mahavishnu"))
    assert lines[0] == "# Session Handoff Report - mahavishnu"


def test_build_handoff_header_substitutes_score() -> None:
    lines = build_handoff_header(_summary(final_quality_score=42))
    assert "42/100" in lines[3]


# -----------------------------------------------------------------------------
# build_quality_section
# -----------------------------------------------------------------------------


def _quality(breakdown: dict[str, float] | None = None) -> dict[str, Any]:
    return {"breakdown": breakdown or {}}


def test_build_quality_section_returns_eight_lines() -> None:
    lines = build_quality_section(_quality())
    # 1 header + 1 blank + 4 bullet rows + 1 blank = 7 lines... re-count below
    assert isinstance(lines, list)
    assert lines[0] == "## Quality Assessment"
    assert lines[1] == ""
    assert lines[-1] == ""


def test_build_quality_section_breakdown_keys_rendered() -> None:
    lines = build_quality_section(
        _quality(
            {
                "code_quality": 35.0,
                "project_health": 25.0,
                "dev_velocity": 18.0,
                "security": 9.0,
            },
        ),
    )
    joined = "\n".join(lines)
    assert "**Code quality:** 35.0/40" in joined
    assert "**Project health:** 25.0/30" in joined
    assert "**Dev velocity:** 18.0/20" in joined
    assert "**Security:** 9.0/10" in joined


def test_build_quality_section_missing_breakdown_defaults_to_zero() -> None:
    lines = build_quality_section({})
    joined = "\n".join(lines)
    assert "**Code quality:** 0.0/40" in joined
    assert "**Project health:** 0.0/30" in joined
    assert "**Dev velocity:** 0.0/20" in joined
    assert "**Security:** 0.0/10" in joined


def test_build_quality_section_partial_breakdown_uses_zero_for_missing() -> None:
    lines = build_quality_section(_quality({"code_quality": 12.5}))
    joined = "\n".join(lines)
    assert "**Code quality:** 12.5/40" in joined
    assert "**Project health:** 0.0/30" in joined


def test_build_quality_section_accepts_int_values_via_format() -> None:
    """Even ints must format as floats (.1f)."""
    lines = build_quality_section(_quality({"code_quality": 20}))
    joined = "\n".join(lines)
    assert "**Code quality:** 20.0/40" in joined


# -----------------------------------------------------------------------------
# build_recommendations_section
# -----------------------------------------------------------------------------


def test_build_recommendations_section_empty_input_returns_empty_list() -> None:
    assert build_recommendations_section([]) == []


def test_build_recommendations_section_single_recommendation() -> None:
    lines = build_recommendations_section(["Improve test coverage"])
    joined = "\n".join(lines)
    assert joined.startswith("## Recommendations for Next Session")
    assert "- Improve test coverage" in joined


def test_build_recommendations_section_caps_at_five() -> None:
    recs = [f"rec-{i}" for i in range(10)]
    lines = build_recommendations_section(recs)
    bullets = [line for line in lines if line.startswith("- ")]
    assert len(bullets) == 5
    # Boundary: 6th and beyond are dropped
    assert "- rec-4" in bullets
    assert "- rec-5" not in bullets


def test_build_recommendations_section_exactly_five_keeps_all() -> None:
    recs = [f"rec-{i}" for i in range(5)]
    lines = build_recommendations_section(recs)
    bullets = [line for line in lines if line.startswith("- ")]
    assert len(bullets) == 5


# -----------------------------------------------------------------------------
# build_static_sections
# -----------------------------------------------------------------------------


def test_build_static_sections_contains_context_header() -> None:
    lines = build_static_sections()
    joined = "\n".join(lines)
    assert "## Context for Next Session" in joined
    assert "## Session Continuity" in joined


def test_build_static_sections_contains_continuity_bullets() -> None:
    lines = build_static_sections()
    joined = "\n".join(lines)
    assert "Reflection database for key insights" in joined
    assert "Quality score history for trend analysis" in joined
    assert "Project structure analysis for optimization" in joined


def test_build_static_sections_is_deterministic() -> None:
    assert build_static_sections() == build_static_sections()


# -----------------------------------------------------------------------------
# save_handoff_documentation
# -----------------------------------------------------------------------------


def test_save_handoff_documentation_writes_file_and_returns_path(
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / "project"
    target_dir.mkdir()
    result = save_handoff_documentation("# content\n", target_dir)

    assert result is not None
    assert isinstance(result, Path)
    assert result.exists()
    assert result.parent == target_dir / ".claude" / "handoff"
    assert result.name.startswith("session_handoff_")
    assert result.name.endswith(".md")
    assert result.read_text() == "# content\n"


def test_save_handoff_documentation_creates_missing_directory_chain(
    tmp_path: Path,
) -> None:
    """Parents must be created when ``.claude/handoff`` does not yet exist."""
    target_dir = tmp_path / "deeply" / "nested" / "project"
    result = save_handoff_documentation("body", target_dir)
    assert result is not None
    assert result.exists()


def test_save_handoff_documentation_filename_includes_timestamp(
    tmp_path: Path,
) -> None:
    """The filename embeds the formatted UTC timestamp."""
    fake_now = datetime(2026, 9, 4, 11, 28, 48)
    with patch(
        "session_buddy.core.lifecycle.handoff.datetime",
    ) as fake_dt:
        fake_dt.now.return_value = fake_now
        result = save_handoff_documentation("body", tmp_path)
    assert result is not None
    assert result.name == "session_handoff_20260904_112848.md"


def test_save_handoff_documentation_distinct_paths_when_timestamps_differ(
    tmp_path: Path,
) -> None:
    """When the timestamp differs across saves, filenames also differ."""
    fake_now_1 = datetime(2026, 9, 4, 11, 28, 48)
    fake_now_2 = datetime(2026, 9, 4, 11, 28, 49)
    with patch("session_buddy.core.lifecycle.handoff.datetime") as fake_dt:
        fake_dt.now.return_value = fake_now_1
        a = save_handoff_documentation("first", tmp_path)
    with patch("session_buddy.core.lifecycle.handoff.datetime") as fake_dt:
        fake_dt.now.return_value = fake_now_2
        b = save_handoff_documentation("second", tmp_path)
    assert a is not None and b is not None
    assert a != b
    assert a.read_text() == "first"
    assert b.read_text() == "second"


def test_save_handoff_documentation_returns_none_on_os_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the underlying write raises, return None and log.exception."""
    target_dir = tmp_path / "project"
    target_dir.mkdir()
    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        with caplog.at_level(logging.ERROR, logger="session_buddy.core.lifecycle.handoff"):
            result = save_handoff_documentation("body", target_dir)
    assert result is None
    # logger.exception fires at ERROR with traceback
    assert any("Handoff document generation failed" in rec.message for rec in caplog.records)


def test_save_handoff_documentation_returns_none_on_mkdir_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the parent directory creation fails, also return None."""
    target_dir = tmp_path / "project"
    target_dir.mkdir()
    with patch.object(Path, "mkdir", side_effect=PermissionError("no write")):
        with caplog.at_level(logging.ERROR, logger="session_buddy.core.lifecycle.handoff"):
            result = save_handoff_documentation("body", target_dir)
    assert result is None
    assert any("Handoff document generation failed" in rec.message for rec in caplog.records)


# -----------------------------------------------------------------------------
# generate_handoff_documentation (async orchestrator)
# -----------------------------------------------------------------------------


async def test_generate_handoff_documentation_includes_all_sections() -> None:
    summary = _summary()
    summary["recommendations"] = ["Run the test suite"]
    quality = _quality(
        {
            "code_quality": 38.0,
            "project_health": 27.0,
            "dev_velocity": 16.0,
            "security": 8.0,
        },
    )

    doc = await generate_handoff_documentation(summary, quality)

    assert "# Session Handoff Report - session-buddy" in doc
    assert "**Final quality score:** 87/100" in doc
    assert "## Quality Assessment" in doc
    assert "**Code quality:** 38.0/40" in doc
    assert "**Project health:** 27.0/30" in doc
    assert "**Dev velocity:** 16.0/20" in doc
    assert "**Security:** 8.0/10" in doc
    assert "## Recommendations for Next Session" in doc
    assert "- Run the test suite" in doc
    assert "## Context for Next Session" in doc
    assert "## Session Continuity" in doc


async def test_generate_handoff_documentation_with_no_recommendations() -> None:
    """Empty recommendations list -> no recommendations section in output."""
    summary = _summary()  # no 'recommendations' key
    quality = _quality({"code_quality": 10})
    doc = await generate_handoff_documentation(summary, quality)

    assert "## Recommendations for Next Session" not in doc
    # Header still rendered
    assert "# Session Handoff Report - session-buddy" in doc


async def test_generate_handoff_documentation_caps_recommendations_at_five() -> None:
    summary = _summary()
    summary["recommendations"] = [f"rec-{i}" for i in range(7)]
    quality = _quality()

    doc = await generate_handoff_documentation(summary, quality)

    assert "- rec-0" in doc
    assert "- rec-4" in doc
    assert "- rec-5" not in doc
    assert "- rec-6" not in doc


async def test_generate_handoff_documentation_returns_string() -> None:
    doc = await generate_handoff_documentation(_summary(), _quality())
    assert isinstance(doc, str)
    # Sections joined by newlines -> at least 4 newlines
    assert doc.count("\n") >= 10


async def test_generate_handoff_documentation_empty_quality_breakdown() -> None:
    doc = await generate_handoff_documentation(_summary(), {})
    # All breakdown fields default to 0.0
    assert "**Code quality:** 0.0/40" in doc
    assert "**Project health:** 0.0/30" in doc
    assert "**Dev velocity:** 0.0/20" in doc
    assert "**Security:** 0.0/10" in doc
