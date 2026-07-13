"""Unit tests for session_buddy/core/skills_tracker.py.

Covers:
- SkillInvocation / SkillMetrics dataclasses
- SkillsTracker initialization (fresh + from existing file)
- track_invocation returning a completion callable
- get_session_skills / get_session_summary
- get_skill_metrics
- export_metrics
- recommend_skills (no db returns empty; with stubbed storage returns sorted list)
- generate_workflow_report (no db returns stub, with stubbed storage builds sections)
- generate_phase_heatmap (no db returns stub, with stubbed storage builds table)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


# ============================================================================
# Imports — pull from production module to keep coverage accurate
# ============================================================================

from session_buddy.core.skills_tracker import (
    SkillInvocation,
    SkillMetrics,
    SkillsTracker,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def session_id() -> str:
    return "session-fixture-001"


@pytest.fixture
def tracker(session_id: str) -> SkillsTracker:
    """A fresh in-memory tracker (no metrics_file)."""
    return SkillsTracker(session_id=session_id)


@pytest.fixture
def metrics_file(tmp_path: Path) -> Path:
    return tmp_path / "metrics.json"


@pytest.fixture
def fake_skill_metric() -> MagicMock:
    """Mock for SkillsStorage metric rows (StoredMetrics-like)."""
    metric = MagicMock()
    metric.skill_name = "alpha_skill"
    metric.completion_rate = 90.0
    metric.total_invocations = 7
    return metric


@pytest.fixture
def fake_effectiveness() -> list[dict[str, Any]]:
    return [
        {
            "skill_name": "alpha_skill",
            "workflow_phase": "design",
            "completion_rate": 92.0,
            "avg_duration_seconds": 1.5,
            "total_invocations": 10,
        },
        {
            "skill_name": "beta_skill",
            "workflow_phase": "design",
            "completion_rate": 80.0,
            "avg_duration_seconds": 2.0,
            "total_invocations": 6,
        },
        {
            "skill_name": "alpha_skill",
            "workflow_phase": "review",
            "completion_rate": 70.0,
            "avg_duration_seconds": 3.0,
            "total_invocations": 4,
        },
    ]


@pytest.fixture
def fake_bottlenecks() -> list[dict[str, Any]]:
    return [
        {
            "workflow_phase": "design",
            "abandonment_rate": 0.55,
            "bottleneck_score": 0.91,
        },
        {
            "workflow_phase": "review",
            "abandonment_rate": 0.25,
            "bottleneck_score": 0.40,
        },
    ]


@pytest.fixture
def fake_transitions() -> list[dict[str, Any]]:
    return [
        {
            "from_phase": "design",
            "to_phase": "review",
            "invocation_count": 12,
            "most_common_skill": "alpha_skill",
        },
        {
            "from_phase": "review",
            "to_phase": "ship",
            "invocation_count": 5,
            "most_common_skill": "beta_skill",
        },
    ]


# ============================================================================
# Dataclass tests
# ============================================================================


class TestSkillMetrics:
    def test_completion_rate_no_invocations(self) -> None:
        metrics = SkillMetrics(skill_name="any")
        assert metrics.completion_rate() == 0.0

    def test_completion_rate_full_completion(self) -> None:
        metrics = SkillMetrics(
            skill_name="any",
            total_invocations=4,
            completed_invocations=4,
        )
        assert metrics.completion_rate() == 100.0

    def test_completion_rate_partial(self) -> None:
        metrics = SkillMetrics(
            skill_name="any",
            total_invocations=4,
            completed_invocations=1,
        )
        assert metrics.completion_rate() == 25.0


class TestSkillInvocation:
    def test_defaults(self) -> None:
        inv = SkillInvocation(skill_name="x", invoked_at="t", session_id="s")
        assert inv.completed is False
        assert inv.workflow_path is None
        assert inv.alternatives_considered == []
        assert inv.follow_up_actions == []
        assert inv.error_type is None
        assert inv.duration_seconds is None
        assert inv.selection_rank is None


# ============================================================================
# Lifecycle tests
# ============================================================================


class TestInit:
    def test_initializes_with_session_id(self, session_id: str) -> None:
        t = SkillsTracker(session_id=session_id)
        assert t.session_id == session_id
        assert t._invocations == []
        assert t._skill_metrics == {}

    def test_loads_existing_metrics_when_file_present(
        self, session_id: str, metrics_file: Path
    ) -> None:
        inv = SkillInvocation(
            skill_name="alpha",
            invoked_at="2026-01-01T00:00:00",
            session_id=session_id,
            completed=True,
            duration_seconds=2.5,
        )
        metrics_file.write_text(
            json.dumps({"invocations": [inv.__dict__]})
        )

        t = SkillsTracker(session_id=session_id, metrics_file=metrics_file)

        assert len(t._invocations) == 1
        assert t._skill_metrics["alpha"].total_invocations == 1
        assert t._skill_metrics["alpha"].completed_invocations == 1

    def test_empty_metrics_file_does_not_raise(
        self, session_id: str, metrics_file: Path
    ) -> None:
        metrics_file.write_text("")
        t = SkillsTracker(session_id=session_id, metrics_file=metrics_file)
        assert t._invocations == []

    def test_corrupt_json_does_not_raise(
        self, session_id: str, metrics_file: Path
    ) -> None:
        metrics_file.write_text("not-json {")
        t = SkillsTracker(session_id=session_id, metrics_file=metrics_file)
        assert t._invocations == []


# ============================================================================
# track_invocation / completion callable
# ============================================================================


class TestTrackInvocation:
    def test_returns_completion_callable(self, tracker: SkillsTracker) -> None:
        complete = tracker.track_invocation("checkout")
        assert callable(complete)

    def test_records_invocation_metadata(self, tracker: SkillsTracker) -> None:
        complete = tracker.track_invocation(
            skill_name="checkout",
            workflow_path="/work/checkout",
            user_query="run checkout",
            alternatives_considered=["git", "worktree"],
            selection_rank=2,
        )

        invocations = tracker.get_session_skills()
        assert len(invocations) == 1
        invocation = invocations[0]
        assert invocation.skill_name == "checkout"
        assert invocation.workflow_path == "/work/checkout"
        assert invocation.user_query == "run checkout"
        assert invocation.alternatives_considered == ["git", "worktree"]
        assert invocation.selection_rank == 2
        assert invocation.session_id == tracker.session_id
        assert not invocation.completed

        # callable must accept **kwargs without raising
        complete(
            completed=True,
            duration_seconds=1.25,
            follow_up_actions=["cleanup"],
        )

        assert invocation.completed is True
        assert invocation.duration_seconds == 1.25
        assert invocation.follow_up_actions == ["cleanup"]

    def test_completion_marks_invocation_as_abandoned(
        self, tracker: SkillsTracker
    ) -> None:
        complete = tracker.track_invocation("broken")
        complete(completed=False, error_type="RuntimeError")

        inv = tracker.get_session_skills()[0]
        assert inv.completed is False
        assert inv.error_type == "RuntimeError"
        # duration not set when completed is False
        assert inv.duration_seconds is None

    def test_track_invocation_copies_alternatives_list(
        self, tracker: SkillsTracker
    ) -> None:
        alternatives = ["a", "b"]
        tracker.track_invocation(
            skill_name="x", alternatives_considered=alternatives
        )
        # mutating the source list must not retroactively change the record
        alternatives.append("c")
        assert tracker.get_session_skills()[0].alternatives_considered == ["a", "b"]


# ============================================================================
# get_session_skills / get_session_summary
# ============================================================================


class TestSessionSummary:
    def test_summary_zero_invocations(self, tracker: SkillsTracker) -> None:
        summary = tracker.get_session_summary()
        assert summary == {
            "session_id": tracker.session_id,
            "total_invocations": 0,
            "completed_invocations": 0,
            "abandoned_invocations": 0,
            "total_duration_seconds": 0,
        }

    def test_summary_counts_completed_and_abandoned(
        self, tracker: SkillsTracker
    ) -> None:
        a = tracker.track_invocation("a")
        a(completed=True, duration_seconds=1.0)

        b = tracker.track_invocation("b")
        b(completed=False, error_type="boom")

        c = tracker.track_invocation("c")
        c(completed=True, duration_seconds=2.5)

        summary = tracker.get_session_summary()
        assert summary["total_invocations"] == 3
        assert summary["completed_invocations"] == 2
        assert summary["abandoned_invocations"] == 1
        assert summary["total_duration_seconds"] == 3.5

    def test_get_session_skills_returns_copy(self, tracker: SkillsTracker) -> None:
        tracker.track_invocation("a")
        skills = tracker.get_session_skills()
        skills.clear()
        # internal state must not be affected
        assert len(tracker.get_session_skills()) == 1


# ============================================================================
# get_skill_metrics
# ============================================================================


class TestSkillMetricsLookup:
    def test_unknown_skill_returns_none(self, tracker: SkillsTracker) -> None:
        assert tracker.get_skill_metrics("never-tracked") is None

    def test_tracked_skill_returns_aggregates(self, tracker: SkillsTracker) -> None:
        c1 = tracker.track_invocation("checkout", workflow_path="/work/checkout")
        c1(completed=True, duration_seconds=1.0)

        c2 = tracker.track_invocation("checkout", workflow_path="/work/checkout")
        c2(completed=False, error_type="TimeoutError")

        c3 = tracker.track_invocation("checkout")
        c3(completed=True, duration_seconds=2.0)

        metrics = tracker.get_skill_metrics("checkout")
        assert metrics is not None
        assert metrics.total_invocations == 3
        assert metrics.completed_invocations == 2
        assert metrics.abandoned_invocations == 1
        assert metrics.total_duration_seconds == 3.0
        assert metrics.workflow_paths["/work/checkout"] == 2
        assert metrics.common_errors["TimeoutError"] == 1


# ============================================================================
# export_metrics
# ============================================================================


class TestExportMetrics:
    def test_export_writes_json(self, tracker: SkillsTracker, tmp_path: Path) -> None:
        tracker.track_invocation("alpha")
        out_path = tmp_path / "export.json"
        tracker.export_metrics(out_path)

        data = json.loads(out_path.read_text())
        assert "invocations" in data
        assert len(data["invocations"]) == 1
        assert data["invocations"][0]["skill_name"] == "alpha"


# ============================================================================
# recommend_skills (uses SkillsStorage at import boundary)
# ============================================================================


class TestRecommendSkills:
    def test_no_db_returns_empty(self, tracker: SkillsTracker) -> None:
        # No db_path provided → immediate empty result without storage call
        assert tracker.recommend_skills(user_query="any query") == []

    def test_recommends_from_storage(
        self,
        tracker: SkillsTracker,
        tmp_path: Path,
        fake_skill_metric: MagicMock,
    ) -> None:
        # second metric to validate ordering by (rate, total) DESC
        beta = MagicMock()
        beta.skill_name = "beta_skill"
        beta.completion_rate = 60.0
        beta.total_invocations = 3

        storage = MagicMock()
        storage.get_all_metrics.return_value = [beta, fake_skill_metric]

        fake_module = MagicMock()
        fake_module.SkillsStorage = lambda db_path: storage

        import sys
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(
                sys.modules,
                "session_buddy.storage.skills_storage",
                fake_module,
            )
            recs = tracker.recommend_skills(
                user_query="help me out",
                limit=2,
                workflow_phase="design",
                phase_weight=0.3,
                db_path=tmp_path / "skills.db",
            )

        assert len(recs) == 2
        # Sorted by (completion_rate, total_invocations) DESC — alpha first
        assert recs[0]["skill_name"] == "alpha_skill"
        assert recs[1]["skill_name"] == "beta_skill"
        assert recs[0]["similarity_score"] == pytest.approx(0.9)
        assert recs[0]["workflow_phase"] == "design"


# ============================================================================
# generate_workflow_report (uses SkillsStorage)
# ============================================================================


class TestGenerateWorkflowReport:
    def test_no_db_returns_stub(self, tracker: SkillsTracker) -> None:
        report = tracker.generate_workflow_report()
        assert "Workflow Correlation Report" in report
        assert "No database available" in report

    def test_full_report_with_sections(
        self,
        tracker: SkillsTracker,
        tmp_path: Path,
        fake_effectiveness: list[dict[str, Any]],
        fake_bottlenecks: list[dict[str, Any]],
        fake_transitions: list[dict[str, Any]],
    ) -> None:
        storage = MagicMock()
        storage.get_workflow_skill_effectiveness.return_value = fake_effectiveness
        storage.identify_workflow_bottlenecks.return_value = fake_bottlenecks
        storage.get_workflow_phase_transitions.return_value = fake_transitions

        fake_module = MagicMock()
        fake_module.SkillsStorage = lambda db_path: storage

        import sys
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(
                sys.modules,
                "session_buddy.storage.skills_storage",
                fake_module,
            )
            report = tracker.generate_workflow_report(
                db_path=tmp_path / "skills.db",
                session_id="abc-123",
            )

        assert "Workflow Correlation Report" in report
        assert "Session: abc-123" in report
        assert "Skill Effectiveness by Workflow Phase" in report
        assert "design:" in report
        assert "Workflow Bottlenecks" in report
        assert "55.0% abandonment" in report
        assert "Phase Transitions" in report
        assert "design -> review (12)" in report
        assert "review -> ship (5)" in report
        assert "Recommendations by Phase" in report

    def test_full_report_empty_data(
        self, tracker: SkillsTracker, tmp_path: Path
    ) -> None:
        storage = MagicMock()
        storage.get_workflow_skill_effectiveness.return_value = []
        storage.identify_workflow_bottlenecks.return_value = []
        storage.get_workflow_phase_transitions.return_value = []

        fake_module = MagicMock()
        fake_module.SkillsStorage = lambda db_path: storage

        import sys
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(
                sys.modules,
                "session_buddy.storage.skills_storage",
                fake_module,
            )
            report = tracker.generate_workflow_report(
                db_path=tmp_path / "skills.db",
            )

        assert "No workflow data available" in report
        assert "No significant bottlenecks" in report
        assert "No phase transition data available" in report
        assert "No recommendations available" in report


# ============================================================================
# generate_phase_heatmap (uses SkillsStorage)
# ============================================================================


class TestGeneratePhaseHeatmap:
    def test_no_db_returns_stub(self, tracker: SkillsTracker) -> None:
        heatmap = tracker.generate_phase_heatmap()
        assert "Skill Usage Heatmap" in heatmap
        assert "No workflow data available" in heatmap
        assert "denser marks" in heatmap

    def test_full_heatmap(
        self,
        tracker: SkillsTracker,
        tmp_path: Path,
        fake_effectiveness: list[dict[str, Any]],
    ) -> None:
        storage = MagicMock()
        storage.get_workflow_skill_effectiveness.return_value = fake_effectiveness

        fake_module = MagicMock()
        fake_module.SkillsStorage = lambda db_path: storage

        import sys
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(
                sys.modules,
                "session_buddy.storage.skills_storage",
                fake_module,
            )
            heatmap = tracker.generate_phase_heatmap(
                db_path=tmp_path / "skills.db",
                session_id="abc",
            )

        assert "Skill Usage Heatmap" in heatmap
        assert "design" in heatmap
        assert "review" in heatmap
        # alpha_skill appears in both design & review → "##" cells
        assert "alpha_skill | ##" in heatmap
        # beta_skill only appears in design → ## for design, .. for review
        assert "beta_skill | ## | .." in heatmap

    def test_heatmap_empty_effectiveness(
        self, tracker: SkillsTracker, tmp_path: Path
    ) -> None:
        storage = MagicMock()
        storage.get_workflow_skill_effectiveness.return_value = []

        fake_module = MagicMock()
        fake_module.SkillsStorage = lambda db_path: storage

        import sys
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(
                sys.modules,
                "session_buddy.storage.skills_storage",
                fake_module,
            )
            heatmap = tracker.generate_phase_heatmap(
                db_path=tmp_path / "skills.db"
            )

        assert "No workflow data available" in heatmap
