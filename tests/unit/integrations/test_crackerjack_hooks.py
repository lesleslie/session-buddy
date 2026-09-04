"""Unit tests for crackerjack integration hooks.

Tests session_buddy.integrations.crackerjack_hooks module:
- CrackerjackPhaseMetrics dataclass behavior
- CrackerjackIntegration class with mocked SkillsTracker
- Phase mapping, tracking, and reporting
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------
# Phase metrics dataclass
# ---------------------------------------------------------------


class TestCrackerjackPhaseMetrics:
    """Tests for CrackerjackPhaseMetrics dataclass."""

    def test_default_construction(self):
        """Test that defaults are zero-initialized."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackPhaseMetrics,
        )

        metrics = CrackerjackPhaseMetrics(phase_name="tests")

        assert metrics.phase_name == "tests"
        assert metrics.total_invocations == 0
        assert metrics.completed_invocations == 0
        assert metrics.total_duration_seconds == 0.0
        assert metrics.tools_used == set()
        assert metrics.common_failures == {}

    def test_completion_rate_zero_runs(self):
        """Test that completion_rate returns 0.0 when total_invocations is zero."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackPhaseMetrics,
        )

        metrics = CrackerjackPhaseMetrics(phase_name="tests")
        assert metrics.completion_rate() == 0.0

    def test_completion_rate_full(self):
        """Test 100% completion rate when all invocations complete."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackPhaseMetrics,
        )

        metrics = CrackerjackPhaseMetrics(
            phase_name="tests",
            total_invocations=4,
            completed_invocations=4,
        )
        assert metrics.completion_rate() == 100.0

    def test_completion_rate_partial(self):
        """Test partial completion rate calculation."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackPhaseMetrics,
        )

        metrics = CrackerjackPhaseMetrics(
            phase_name="tests",
            total_invocations=10,
            completed_invocations=7,
        )
        assert metrics.completion_rate() == 70.0

    def test_avg_duration_no_completed(self):
        """Test avg_duration_seconds returns 0.0 when no completions."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackPhaseMetrics,
        )

        metrics = CrackerjackPhaseMetrics(
            phase_name="tests",
            total_invocations=5,
            completed_invocations=0,
        )
        assert metrics.avg_duration_seconds() == 0.0

    def test_avg_duration_calculates_average(self):
        """Test avg_duration_seconds computes mean of completed durations."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackPhaseMetrics,
        )

        metrics = CrackerjackPhaseMetrics(
            phase_name="tests",
            completed_invocations=4,
            total_duration_seconds=20.0,
        )
        assert metrics.avg_duration_seconds() == 5.0

    def test_set_and_dict_defaults_independent(self):
        """Test that mutable defaults are not shared between instances."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackPhaseMetrics,
        )

        first = CrackerjackPhaseMetrics(phase_name="tests")
        first.tools_used.add("ruff-check")
        first.common_failures["timeout"] = 1

        second = CrackerjackPhaseMetrics(phase_name="ai_fix")
        assert second.tools_used == set()
        assert second.common_failures == {}


# ---------------------------------------------------------------
# Integration initialization
# ---------------------------------------------------------------


class TestCrackerjackIntegrationInit:
    """Tests for CrackerjackIntegration construction."""

    def _make_tracker(self) -> MagicMock:
        """Construct a MagicMock SkillsTracker with track_invocation callable."""
        tracker = MagicMock()
        tracker.session_id = "crackerjack_test_123"
        # track_invocation returns a callable that captures kwargs
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        return tracker

    def test_init_stores_skills_tracker_and_path(self):
        """Test that init stores the SkillsTracker and project path."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = self._make_tracker()
        project = Path("/tmp/fake-project")

        integration = CrackerjackIntegration(tracker, project)

        assert integration.skills_tracker is tracker
        assert integration.crackerjack_project_path == project

    def test_init_initializes_phase_metrics(self):
        """Test that init creates empty phase metrics for every known phase."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = self._make_tracker()
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        assert set(integration.phase_metrics.keys()) == set(
            CrackerjackIntegration.PHASE_MAPPING.keys()
        )
        for phase_name, metrics in integration.phase_metrics.items():
            assert metrics.phase_name == phase_name
            assert metrics.total_invocations == 0


# ---------------------------------------------------------------
# track_crackerjack_phase
# ---------------------------------------------------------------


class TestTrackCrackerjackPhase:
    """Tests for CrackerjackIntegration.track_crackerjack_phase."""

    def _build(self) -> tuple[MagicMock, "CrackerjackIntegration"]:  # noqa: F821
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session-xyz"
        complete_fn = MagicMock()
        tracker.track_invocation.return_value = complete_fn
        tracker.recommend_skills.return_value = []

        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))
        return tracker, integration

    def test_track_completed_invocation(self):
        """Test tracking a successful invocation updates phase metrics."""
        _, integration = self._build()

        integration.track_crackerjack_phase(
            phase_name="fast_hooks",
            skill_name="ruff-check",
            completed=True,
            duration_seconds=2.5,
        )

        metrics = integration.phase_metrics["fast_hooks"]
        assert metrics.total_invocations == 1
        assert metrics.completed_invocations == 1
        assert metrics.total_duration_seconds == 2.5
        assert "ruff-check" in metrics.tools_used
        assert metrics.common_failures == {}

    def test_track_failed_invocation_records_error(self):
        """Test that failure with error_message records common failure."""
        _, integration = self._build()

        integration.track_crackerjack_phase(
            phase_name="tests",
            skill_name="pytest-run",
            completed=False,
            duration_seconds=10.0,
            error_message="AssertionError: 1 != 2",
        )

        metrics = integration.phase_metrics["tests"]
        assert metrics.total_invocations == 1
        assert metrics.completed_invocations == 0
        assert metrics.common_failures == {"AssertionError: 1 != 2": 1}

    def test_track_failed_invocation_without_error_message(self):
        """Test that failure without error_message is silently tracked."""
        _, integration = self._build()

        integration.track_crackerjack_phase(
            phase_name="comprehensive_hooks",
            skill_name="mypy-check",
            completed=False,
            duration_seconds=1.0,
        )

        metrics = integration.phase_metrics["comprehensive_hooks"]
        assert metrics.total_invocations == 1
        assert metrics.completed_invocations == 0
        assert metrics.common_failures == {}

    def test_track_repeated_error_increments_count(self):
        """Test that repeated identical errors increment the count."""
        _, integration = self._build()

        for _ in range(3):
            integration.track_crackerjack_phase(
                phase_name="tests",
                skill_name="pytest-run",
                completed=False,
                duration_seconds=1.0,
                error_message="timeout",
            )

        metrics = integration.phase_metrics["tests"]
        assert metrics.common_failures == {"timeout": 3}

    def test_track_unknown_phase_raises_value_error(self):
        """Test that unknown phase raises ValueError."""
        _, integration = self._build()

        with pytest.raises(ValueError, match="Unknown crackerjack phase"):
            integration.track_crackerjack_phase(
                phase_name="nonexistent-phase",
                skill_name="ruff-check",
                completed=True,
                duration_seconds=1.0,
            )

    def test_track_invokes_skills_tracker_with_workflow_phase(self):
        """Test that the workflow phase is mapped correctly to Oneiric."""
        tracker, integration = self._build()

        integration.track_crackerjack_phase(
            phase_name="ai_fix",
            skill_name="refactoring-agent",
            completed=True,
            duration_seconds=5.0,
        )

        tracker.track_invocation.assert_called_once()
        call_kwargs = tracker.track_invocation.call_args.kwargs
        assert call_kwargs["skill_name"] == "refactoring-agent"
        assert call_kwargs["workflow_path"] == "execution"
        assert "ai_fix" in call_kwargs["user_query"]

    def test_track_invokes_complete_fn_with_completion_and_error(self):
        """Test that the complete callback receives completed and error_type."""
        tracker, integration = self._build()
        complete_fn = tracker.track_invocation.return_value

        integration.track_crackerjack_phase(
            phase_name="fast_hooks",
            skill_name="ruff-format",
            completed=False,
            duration_seconds=1.0,
            error_message="format failed",
        )

        complete_fn.assert_called_once_with(
            completed=False, error_type="format failed"
        )

    def test_track_all_phases_increment(self):
        """Test tracking across all four known phases."""
        _, integration = self._build()

        integration.track_crackerjack_phase(
            phase_name="fast_hooks", skill_name="ruff-check",
            completed=True, duration_seconds=1.0,
        )
        integration.track_crackerjack_phase(
            phase_name="tests", skill_name="pytest-run",
            completed=True, duration_seconds=10.0,
        )
        integration.track_crackerjack_phase(
            phase_name="comprehensive_hooks", skill_name="mypy-check",
            completed=True, duration_seconds=5.0,
        )
        integration.track_crackerjack_phase(
            phase_name="ai_fix", skill_name="refactoring-agent",
            completed=False, duration_seconds=3.0, error_message="oops",
        )

        assert integration.phase_metrics["fast_hooks"].total_invocations == 1
        assert integration.phase_metrics["tests"].total_invocations == 1
        assert (
            integration.phase_metrics["comprehensive_hooks"].total_invocations == 1
        )
        assert integration.phase_metrics["ai_fix"].total_invocations == 1

    def test_tools_used_set_dedupes(self):
        """Test that tools_used is a set (no duplicate entries)."""
        _, integration = self._build()

        for _ in range(5):
            integration.track_crackerjack_phase(
                phase_name="fast_hooks",
                skill_name="ruff-check",
                completed=True,
                duration_seconds=0.5,
            )

        assert integration.phase_metrics["fast_hooks"].tools_used == {"ruff-check"}


# ---------------------------------------------------------------
# get_workflow_phase
# ---------------------------------------------------------------


class TestGetWorkflowPhase:
    """Tests for CrackerjackIntegration.get_workflow_phase."""

    def test_get_workflow_phase_each_mapping(self):
        """Test that each known phase resolves to the expected Oneiric phase."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        assert integration.get_workflow_phase("fast_hooks") == "setup"
        assert integration.get_workflow_phase("tests") == "execution"
        assert (
            integration.get_workflow_phase("comprehensive_hooks") == "verification"
        )
        assert integration.get_workflow_phase("ai_fix") == "execution"

    def test_get_workflow_phase_unknown_raises(self):
        """Test that unknown crackerjack phase raises ValueError."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        with pytest.raises(ValueError, match="Unknown crackerjack phase"):
            integration.get_workflow_phase("missing-phase")


# ---------------------------------------------------------------
# get_recommended_skills
# ---------------------------------------------------------------


class TestGetRecommendedSkills:
    """Tests for CrackerjackIntegration.get_recommended_skills."""

    def test_recommendations_forwarded_to_tracker(self):
        """Test that the integration calls recommend_skills with mapped phase."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = [
            {"skill_name": "ruff-check", "similarity_score": 0.9},
            {"skill_name": "black-format", "similarity_score": 0.8},
        ]
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        results = integration.get_recommended_skills("fast_hooks", limit=2)

        tracker.recommend_skills.assert_called_once()
        call_kwargs = tracker.recommend_skills.call_args.kwargs
        assert call_kwargs["limit"] == 2
        assert call_kwargs["workflow_phase"] == "setup"
        assert call_kwargs["phase_weight"] == 0.5
        assert "fast_hooks" in call_kwargs["user_query"]
        assert len(results) == 2

    def test_recommendations_empty_returns_empty_list(self):
        """Test that an empty recommendation set is propagated."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        results = integration.get_recommended_skills("tests")
        assert results == []

    def test_recommendations_unknown_phase_raises(self):
        """Test that get_recommended_skills validates phase before delegating."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        with pytest.raises(ValueError, match="Unknown crackerjack phase"):
            integration.get_recommended_skills("missing")


# ---------------------------------------------------------------
# get_phase_summary
# ---------------------------------------------------------------


class TestGetPhaseSummary:
    """Tests for CrackerjackIntegration.get_phase_summary."""

    def test_phase_summary_keys(self):
        """Test that summary exposes the expected keys."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        summary = integration.get_phase_summary("fast_hooks")

        expected_keys = {
            "phase_name",
            "workflow_phase",
            "total_invocations",
            "completed_invocations",
            "completion_rate",
            "total_duration_seconds",
            "avg_duration_seconds",
            "tools_used",
            "common_failures",
        }
        assert expected_keys.issubset(summary.keys())
        assert summary["phase_name"] == "fast_hooks"
        assert summary["workflow_phase"] == "setup"

    def test_phase_summary_unknown_raises(self):
        """Test that an unknown phase raises ValueError."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        with pytest.raises(ValueError, match="Unknown phase"):
            integration.get_phase_summary("missing-phase")

    def test_phase_summary_copies_containers(self):
        """Test that tools_used and common_failures are returned as copies."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "session"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        integration.track_crackerjack_phase(
            phase_name="fast_hooks",
            skill_name="ruff-check",
            completed=True,
            duration_seconds=1.0,
        )

        summary = integration.get_phase_summary("fast_hooks")
        summary["tools_used"].add("mutated")
        summary["common_failures"]["new"] = 1

        live = integration.phase_metrics["fast_hooks"]
        assert "mutated" not in live.tools_used
        assert "new" not in live.common_failures


# ---------------------------------------------------------------
# get_crackerjack_workflow_report
# ---------------------------------------------------------------


class TestGetCrackerjackWorkflowReport:
    """Tests for CrackerjackIntegration.get_crackerjack_workflow_report."""

    def test_report_contains_required_sections(self):
        """Test that the report contains all major sections."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "sess-001"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        report = integration.get_crackerjack_workflow_report()

        assert "Crackerjack Workflow Integration Report" in report
        assert "Phase Metrics" in report
        assert "Crackerjack → Oneiric Phase Mapping" in report
        assert "Phase-Specific Recommendations" in report
        assert "fast_hooks" in report
        assert "tests" in report
        assert "comprehensive_hooks" in report
        assert "ai_fix" in report
        assert "sess-001" in report

    def test_report_after_tracking_shows_metrics(self):
        """Test that the report reflects tracked invocations."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "sess-002"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        integration.track_crackerjack_phase(
            phase_name="fast_hooks",
            skill_name="ruff-check",
            completed=True,
            duration_seconds=2.0,
        )
        integration.track_crackerjack_phase(
            phase_name="fast_hooks",
            skill_name="codespell",
            completed=False,
            duration_seconds=1.0,
            error_message="typo found",
        )

        report = integration.get_crackerjack_workflow_report()

        assert "Total Invocations: 2" in report
        assert "Completed: 1" in report
        assert "ruff-check" in report
        assert "codespell" in report
        assert "typo found" in report

    def test_report_includes_recommendations(self):
        """Test that recommendations surface in the report."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "sess-003"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = [
            {"skill_name": "ruff-check", "similarity_score": 0.91},
        ]
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        report = integration.get_crackerjack_workflow_report()

        # The fast_hooks recommendations should be in the report
        assert "ruff-check" in report
        assert "0.91" in report

    def test_report_no_recommendations_falls_back_to_placeholder(self):
        """Test that empty recommendations produce placeholder text."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        tracker = MagicMock()
        tracker.session_id = "sess-004"
        tracker.track_invocation.return_value = MagicMock()
        tracker.recommend_skills.return_value = []
        integration = CrackerjackIntegration(tracker, Path("/tmp/proj"))

        report = integration.get_crackerjack_workflow_report()

        assert "No recommendations available yet." in report


# ---------------------------------------------------------------
# Class-level configuration
# ---------------------------------------------------------------


class TestCrackerjackIntegrationClassConfig:
    """Tests for the static configuration tables on the class."""

    def test_phase_mapping_contains_all_phases(self):
        """Test that PHASE_MAPPING contains the documented phases."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        assert "fast_hooks" in CrackerjackIntegration.PHASE_MAPPING
        assert "tests" in CrackerjackIntegration.PHASE_MAPPING
        assert "comprehensive_hooks" in CrackerjackIntegration.PHASE_MAPPING
        assert "ai_fix" in CrackerjackIntegration.PHASE_MAPPING

    def test_phase_mapping_values_are_oneiric_phases(self):
        """Test that all mapping values are valid Oneiric phase names."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        for phase, oneiric in CrackerjackIntegration.PHASE_MAPPING.items():
            assert isinstance(oneiric, str)
            assert oneiric in {"setup", "execution", "verification", "deployment"}

    def test_phase_tools_contains_lists(self):
        """Test that PHASE_TOOLS maps phases to lists of skill names."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        for phase, tools in CrackerjackIntegration.PHASE_TOOLS.items():
            assert isinstance(tools, list)
            assert len(tools) > 0
            for tool in tools:
                assert isinstance(tool, str)

    def test_phase_tools_keys_match_phase_mapping_keys(self):
        """Test that PHASE_TOOLS has keys aligned with PHASE_MAPPING."""
        from session_buddy.integrations.crackerjack_hooks import (
            CrackerjackIntegration,
        )

        assert set(CrackerjackIntegration.PHASE_TOOLS.keys()) == set(
            CrackerjackIntegration.PHASE_MAPPING.keys()
        )
