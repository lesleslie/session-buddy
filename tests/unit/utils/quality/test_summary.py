"""Tests for session_buddy.utils.quality.summary.

Targets the conversation summary helpers used by the quality subsystem.
Covers empty/seeded summaries, content-driven extractors, the async
reflection processor, fallback helpers, and the error-summary escape hatch.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.utils.quality.summary import (
    create_empty_summary,
    ensure_summary_defaults,
    extract_decisions_from_content,
    extract_next_steps_from_content,
    extract_topics_from_content,
    get_error_summary,
    get_fallback_summary,
    process_recent_reflections,
)


# ---------------------------------------------------------------------------
# create_empty_summary
# ---------------------------------------------------------------------------


class TestCreateEmptySummary:
    def test_returns_dict_with_expected_keys(self) -> None:
        summary = create_empty_summary()
        assert isinstance(summary, dict)
        assert set(summary.keys()) == {
            "key_topics",
            "decisions_made",
            "next_steps",
            "problems_solved",
            "code_changes",
        }

    def test_all_values_are_empty_lists(self) -> None:
        summary = create_empty_summary()
        for value in summary.values():
            assert value == []
            assert isinstance(value, list)

    def test_returns_independent_dict_each_call(self) -> None:
        """Each invocation should produce a fresh dict, not a shared reference."""
        first = create_empty_summary()
        first["key_topics"].append("x")
        second = create_empty_summary()
        assert second["key_topics"] == []


# ---------------------------------------------------------------------------
# extract_topics_from_content
# ---------------------------------------------------------------------------


class TestExtractTopicsFromContent:
    def test_returns_set_type(self) -> None:
        result = extract_topics_from_content("anything goes here")
        assert isinstance(result, set)

    def test_empty_content_yields_empty_set(self) -> None:
        assert extract_topics_from_content("") == set()

    def test_no_project_context_marker_yields_empty_set(self) -> None:
        content = "Some random text without the magic marker."
        assert extract_topics_from_content(content) == set()

    def test_extracts_single_topic_after_marker(self) -> None:
        content = "project context: testing."
        assert extract_topics_from_content(content) == {"testing"}

    def test_extracts_multiple_topics(self) -> None:
        content = "project context: alpha, beta, gamma."
        assert extract_topics_from_content(content) == {"alpha", "beta", "gamma"}

    def test_strips_whitespace_around_topics(self) -> None:
        content = "project context:  spaced  ,  tabs\t,\nnewlines  ."
        assert extract_topics_from_content(content) == {
            "spaced",
            "tabs",
            "newlines",
        }

    def test_takes_only_first_segment_after_marker(self) -> None:
        """Only the text before the next '.' after 'project context:' is parsed."""
        content = "project context: alpha, beta. Ignore: this part."
        assert extract_topics_from_content(content) == {"alpha", "beta"}

    def test_no_period_after_marker_yields_single_topic(self) -> None:
        content = "project context: alpha beta gamma"
        # The split('.') on the second clause yields one element which is the
        # full "alpha beta gamma" string; the set comprehension splits that
        # on commas (none) so a single topic named "alpha beta gamma" is
        # captured.
        assert extract_topics_from_content(content) == {"alpha beta gamma"}

    def test_topic_after_marker_with_only_period(self) -> None:
        """Marker followed by only a period — the parsed chunk is '' but
        ``set.update`` on an empty string still inserts it. This documents
        the (quirky) behavior of the helper."""
        content = "project context:."
        result = extract_topics_from_content(content)
        # Exactly one element and it is the empty string.
        assert len(result) == 1
        assert "" in result

    def test_uppercase_marker_does_not_match(self) -> None:
        """Marker lookup is case-sensitive — capitalized 'Project context:' doesn't trigger."""
        content = "Project context: testing."
        assert extract_topics_from_content(content) == set()


# ---------------------------------------------------------------------------
# extract_decisions_from_content
# ---------------------------------------------------------------------------


class TestExtractDecisionsFromContent:
    def test_returns_list_type(self) -> None:
        assert isinstance(extract_decisions_from_content("nothing here"), list)

    def test_no_keywords_yields_empty_list(self) -> None:
        assert extract_decisions_from_content("just some text") == []

    def test_excellent_keyword(self) -> None:
        result = extract_decisions_from_content("The session was excellent overall")
        assert result == ["Maintaining productive workflow patterns"]

    def test_attention_keyword(self) -> None:
        result = extract_decisions_from_content("Needs attention soon")
        assert result == ["Identified areas needing workflow optimization"]

    def test_good_progress_keyword(self) -> None:
        result = extract_decisions_from_content("Made good progress today")
        assert result == ["Steady development progress confirmed"]

    def test_case_sensitive_keyword_matching(self) -> None:
        """The keyword match is case-sensitive."""
        # 'Excellent' (capital) should NOT trigger the "excellent" branch.
        assert extract_decisions_from_content("Excellent work") == []

    def test_excellent_takes_precedence_over_attention(self) -> None:
        """The if/elif/elif chain means 'excellent' wins if both appear."""
        content = "This was excellent but needs attention too."
        result = extract_decisions_from_content(content)
        assert result == ["Maintaining productive workflow patterns"]

    def test_attention_takes_precedence_over_good_progress(self) -> None:
        content = "attention required. Also good progress was made."
        result = extract_decisions_from_content(content)
        assert result == ["Identified areas needing workflow optimization"]


# ---------------------------------------------------------------------------
# extract_next_steps_from_content
# ---------------------------------------------------------------------------


class TestExtractNextStepsFromContent:
    def test_returns_list_type(self) -> None:
        assert isinstance(extract_next_steps_from_content("nothing"), list)

    def test_no_priority_marker_yields_empty_list(self) -> None:
        assert extract_next_steps_from_content("nothing important here") == []

    def test_extracts_priority_text(self) -> None:
        content = "Follow-up: priority: write tests next."
        result = extract_next_steps_from_content(content)
        assert result == ["write tests next"]

    def test_strips_whitespace(self) -> None:
        content = "priority:    clean up code   ."
        assert extract_next_steps_from_content(content) == ["clean up code"]

    def test_empty_priority_after_marker_is_ignored(self) -> None:
        """If the priority text is just whitespace, nothing is appended."""
        content = "priority:    ."
        assert extract_next_steps_from_content(content) == []

    def test_no_period_after_priority(self) -> None:
        content = "priority: deploy now"
        assert extract_next_steps_from_content(content) == ["deploy now"]

    def test_period_only_after_priority(self) -> None:
        content = "priority: ."
        assert extract_next_steps_from_content(content) == []

    def test_priority_marker_with_only_whitespace(self) -> None:
        """Marker present but only whitespace → empty next_steps."""
        content = "priority: "
        assert extract_next_steps_from_content(content) == []


# ---------------------------------------------------------------------------
# process_recent_reflections
# ---------------------------------------------------------------------------


class _FakeReflection:
    """Minimal stand-in for reflection records used by process_recent_reflections."""

    def __init__(self, content: str) -> None:
        self._content = content

    def __getitem__(self, key: str) -> str:
        if key == "content":
            return self._content
        raise KeyError(key)


class TestProcessRecentReflections:
    async def test_returns_early_when_no_reflections(self) -> None:
        db = MagicMock()
        db.search_reflections = AsyncMock(return_value=[])
        summary: dict[str, Any] = create_empty_summary()
        await process_recent_reflections(db, summary)
        # Summary remains untouched.
        assert summary == create_empty_summary()

    async def test_populates_summary_from_reflections(self) -> None:
        reflections = [
            _FakeReflection("Project context: alpha, beta. priority: ship it."),
            _FakeReflection("Excellent session today."),
        ]
        db = MagicMock()
        db.search_reflections = AsyncMock(return_value=reflections)

        summary: dict[str, Any] = create_empty_summary()
        await process_recent_reflections(db, summary)

        assert "alpha" in summary["key_topics"]
        assert "beta" in summary["key_topics"]
        assert summary["decisions_made"] == ["Maintaining productive workflow patterns"]
        assert summary["next_steps"] == ["ship it"]

    async def test_caps_topics_to_five(self) -> None:
        # Stuff 8 topics into one reflection; only the first 5 (order is set
        # insertion order, since set preserves insertion order in CPython 3.7+)
        # survive.
        topics_csv = ", ".join(f"topic{i}" for i in range(8))
        reflections = [_FakeReflection(f"Project context: {topics_csv}.")]
        db = MagicMock()
        db.search_reflections = AsyncMock(return_value=reflections)

        summary: dict[str, Any] = create_empty_summary()
        await process_recent_reflections(db, summary)

        assert len(summary["key_topics"]) == 5
        assert len(set(summary["key_topics"])) == 5

    async def test_caps_decisions_to_three(self) -> None:
        reflections = [
            _FakeReflection("Excellent."),
            _FakeReflection("Excellent again."),
            _FakeReflection("Excellent."),
            _FakeReflection("Excellent."),
        ]
        db = MagicMock()
        db.search_reflections = AsyncMock(return_value=reflections)

        summary: dict[str, Any] = create_empty_summary()
        await process_recent_reflections(db, summary)

        # One decision per reflection, capped at 3.
        assert len(summary["decisions_made"]) == 3
        assert all(
            d == "Maintaining productive workflow patterns"
            for d in summary["decisions_made"]
        )

    async def test_caps_next_steps_to_three(self) -> None:
        reflections = [
            _FakeReflection("priority: do one."),
            _FakeReflection("priority: do two."),
            _FakeReflection("priority: do three."),
            _FakeReflection("priority: do four."),
        ]
        db = MagicMock()
        db.search_reflections = AsyncMock(return_value=reflections)

        summary: dict[str, Any] = create_empty_summary()
        await process_recent_reflections(db, summary)

        assert summary["next_steps"] == ["do one", "do two", "do three"]

    async def test_skips_reflections_without_known_markers(self) -> None:
        """Reflections that don't trigger any extractor produce empty buckets."""
        reflections = [_FakeReflection("boring prose with no markers.")]
        db = MagicMock()
        db.search_reflections = AsyncMock(return_value=reflections)

        summary: dict[str, Any] = create_empty_summary()
        await process_recent_reflections(db, summary)

        assert summary["key_topics"] == []
        assert summary["decisions_made"] == []
        assert summary["next_steps"] == []

    async def test_content_is_lowercased_before_extraction(self) -> None:
        """The function lowercases content, so markers are case-insensitive."""
        reflections = [_FakeReflection("PROJECT CONTEXT: alpha.")]
        db = MagicMock()
        db.search_reflections = AsyncMock(return_value=reflections)

        summary: dict[str, Any] = create_empty_summary()
        await process_recent_reflections(db, summary)

        assert summary["key_topics"] == ["alpha"]

    async def test_reflection_decision_attention_keyword(self) -> None:
        reflections = [_FakeReflection("This needs attention.")]
        db = MagicMock()
        db.search_reflections = AsyncMock(return_value=reflections)

        summary: dict[str, Any] = create_empty_summary()
        await process_recent_reflections(db, summary)

        assert summary["decisions_made"] == [
            "Identified areas needing workflow optimization",
        ]


# ---------------------------------------------------------------------------
# ensure_summary_defaults
# ---------------------------------------------------------------------------


class TestEnsureSummaryDefaults:
    def test_fills_all_three_default_buckets_when_empty(self) -> None:
        summary: dict[str, Any] = create_empty_summary()
        ensure_summary_defaults(summary)
        assert summary["key_topics"] == [
            "session management",
            "workflow optimization",
        ]
        assert summary["decisions_made"] == [
            "Proceeding with current development approach",
        ]
        assert summary["next_steps"] == [
            "Continue with regular checkpoint monitoring",
        ]

    def test_preserves_existing_key_topics(self) -> None:
        summary: dict[str, Any] = {
            "key_topics": ["already", "set"],
            "decisions_made": [],
            "next_steps": [],
        }
        ensure_summary_defaults(summary)
        assert summary["key_topics"] == ["already", "set"]
        assert summary["decisions_made"] == [
            "Proceeding with current development approach",
        ]
        assert summary["next_steps"] == [
            "Continue with regular checkpoint monitoring",
        ]

    def test_preserves_existing_decisions(self) -> None:
        summary: dict[str, Any] = {
            "key_topics": [],
            "decisions_made": ["keep me"],
            "next_steps": [],
        }
        ensure_summary_defaults(summary)
        assert summary["decisions_made"] == ["keep me"]
        assert summary["next_steps"] == [
            "Continue with regular checkpoint monitoring",
        ]

    def test_preserves_existing_next_steps(self) -> None:
        summary: dict[str, Any] = {
            "key_topics": [],
            "decisions_made": [],
            "next_steps": ["keep me too"],
        }
        ensure_summary_defaults(summary)
        assert summary["next_steps"] == ["keep me too"]
        # Decisions defaults are still applied since they were empty.
        assert summary["decisions_made"] == [
            "Proceeding with current development approach",
        ]


# ---------------------------------------------------------------------------
# get_fallback_summary
# ---------------------------------------------------------------------------


class TestGetFallbackSummary:
    def test_returns_dict_with_expected_keys(self) -> None:
        result = get_fallback_summary()
        assert set(result.keys()) == {
            "key_topics",
            "decisions_made",
            "next_steps",
            "problems_solved",
            "code_changes",
        }

    def test_fallback_topics_present(self) -> None:
        result = get_fallback_summary()
        assert result["key_topics"] == ["development session", "workflow management"]

    def test_fallback_decisions_present(self) -> None:
        result = get_fallback_summary()
        assert result["decisions_made"] == ["Maintaining current session approach"]

    def test_fallback_next_steps_present(self) -> None:
        result = get_fallback_summary()
        assert result["next_steps"] == ["Continue monitoring session quality"]

    def test_fallback_problems_solved_present(self) -> None:
        result = get_fallback_summary()
        assert result["problems_solved"] == ["Session management optimization"]

    def test_fallback_code_changes_present(self) -> None:
        result = get_fallback_summary()
        assert result["code_changes"] == ["Enhanced checkpoint functionality"]

    def test_fallback_returns_independent_dict(self) -> None:
        first = get_fallback_summary()
        first["key_topics"].append("x")
        second = get_fallback_summary()
        assert "x" not in second["key_topics"]


# ---------------------------------------------------------------------------
# get_error_summary
# ---------------------------------------------------------------------------


class TestGetErrorSummary:
    def test_includes_error_message(self) -> None:
        result = get_error_summary(ValueError("boom"))
        assert result["error"] == "boom"

    def test_includes_basic_keys(self) -> None:
        result = get_error_summary(ValueError("oops"))
        assert result["key_topics"] == ["session analysis"]
        assert result["decisions_made"] == ["Error during analysis"]
        assert result["next_steps"] == ["Retry conversation summary"]

    def test_problems_and_code_changes_are_empty_lists(self) -> None:
        result = get_error_summary(ValueError("oops"))
        assert result["problems_solved"] == []
        assert result["code_changes"] == []

    def test_error_stringification_handles_non_string(self) -> None:
        class WeirdError(Exception):
            def __str__(self) -> str:
                return "weird-error"

        result = get_error_summary(WeirdError())
        assert result["error"] == "weird-error"

    def test_returns_independent_dict(self) -> None:
        first = get_error_summary(ValueError("x"))
        first["key_topics"].append("y")
        second = get_error_summary(ValueError("z"))
        assert "y" not in second["key_topics"]


# ---------------------------------------------------------------------------
# Async sanity marker (kept off by default; allows `pytest -m asyncio` runs).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_module_top_level_smoke() -> None:
    """Smoke test that the public surface is importable and usable."""
    assert create_empty_summary() is not None
    assert get_fallback_summary() is not None
    assert get_error_summary(RuntimeError("x"))["error"] == "x"
