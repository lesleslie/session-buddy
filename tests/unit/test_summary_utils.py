from __future__ import annotations

import asyncio
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SUMMARY_PATH = (
    Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "quality" / "summary.py"
)
_SUMMARY_SPEC = spec_from_file_location(
    "session_buddy.utils.quality.summary",
    _SUMMARY_PATH,
)
assert _SUMMARY_SPEC is not None and _SUMMARY_SPEC.loader is not None
_summary = module_from_spec(_SUMMARY_SPEC)
sys.modules[_SUMMARY_SPEC.name] = _summary
_SUMMARY_SPEC.loader.exec_module(_summary)

create_empty_summary = _summary.create_empty_summary
ensure_summary_defaults = _summary.ensure_summary_defaults
extract_decisions_from_content = _summary.extract_decisions_from_content
extract_next_steps_from_content = _summary.extract_next_steps_from_content
extract_topics_from_content = _summary.extract_topics_from_content
get_error_summary = _summary.get_error_summary
get_fallback_summary = _summary.get_fallback_summary
process_recent_reflections = _summary.process_recent_reflections


def test_create_empty_summary_and_extract_helpers() -> None:
    summary = create_empty_summary()

    assert summary == {
        "key_topics": [],
        "decisions_made": [],
        "next_steps": [],
        "problems_solved": [],
        "code_changes": [],
    }
    assert extract_topics_from_content("project context: alpha, beta.") == {"alpha", "beta"}
    assert extract_topics_from_content("no context here") == set()
    assert extract_decisions_from_content("excellent") == [
        "Maintaining productive workflow patterns",
    ]
    assert extract_decisions_from_content("attention") == [
        "Identified areas needing workflow optimization",
    ]
    assert extract_decisions_from_content("good progress") == [
        "Steady development progress confirmed",
    ]
    assert extract_decisions_from_content("neutral") == []
    assert extract_next_steps_from_content("priority: ship it.") == ["ship it"]
    assert extract_next_steps_from_content("priority:    .") == []
    assert extract_next_steps_from_content("no next step") == []


def test_process_recent_reflections_populates_summary() -> None:
    class FakeDb:
        async def search_reflections(self, _kind: str, limit: int = 5):
            assert limit == 5
            return [
                {
                    "content": (
                        "Project context: alpha, beta. Excellent. Priority: write tests."
                    ),
                },
                {
                    "content": (
                        "Project context: gamma. Good progress. Priority: update docs."
                    ),
                },
            ]

    summary = create_empty_summary()

    asyncio.run(process_recent_reflections(FakeDb(), summary))

    assert set(summary["key_topics"]) == {"alpha", "beta", "gamma"}
    assert summary["decisions_made"] == [
        "Maintaining productive workflow patterns",
        "Steady development progress confirmed",
    ]
    assert summary["next_steps"] == ["write tests", "update docs"]


def test_process_recent_reflections_handles_empty_results() -> None:
    class EmptyDb:
        async def search_reflections(self, _kind: str, limit: int = 5):
            assert limit == 5
            return []

    summary = create_empty_summary()
    summary["key_topics"] = ["existing"]

    asyncio.run(process_recent_reflections(EmptyDb(), summary))

    assert summary["key_topics"] == ["existing"]
    assert summary["decisions_made"] == []
    assert summary["next_steps"] == []


def test_ensure_summary_defaults_and_error_helpers() -> None:
    summary = create_empty_summary()
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

    fallback = get_fallback_summary()
    error_summary = get_error_summary(RuntimeError("boom"))

    assert fallback["key_topics"] == ["development session", "workflow management"]
    assert error_summary["error"] == "boom"


def test_ensure_summary_defaults_noop_when_already_populated() -> None:
    summary = {
        "key_topics": ["already there"],
        "decisions_made": ["done"],
        "next_steps": ["next"],
        "problems_solved": [],
        "code_changes": [],
    }

    ensure_summary_defaults(summary)

    assert summary["key_topics"] == ["already there"]
    assert summary["decisions_made"] == ["done"]
    assert summary["next_steps"] == ["next"]
