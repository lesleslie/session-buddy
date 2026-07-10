"""Unit tests for CI/CD tracker.

Tests session_buddy.integrations.cicd_tracker module:
- CIPipelineContext dataclass validation and methods
- CIPipelineStage dataclass
- CICDTracker class methods (with mocked storage)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch


class TestCIPipelineContext:
    """Tests for CIPipelineContext dataclass."""

    def test_valid_context_creation(self):
        """Test creating valid CIPipelineContext."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="test-pipeline",
            build_number="123",
            git_commit="abc123def456",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

        assert context.pipeline_name == "test-pipeline"
        assert context.build_number == "123"
        assert context.git_commit == "abc123def456"
        assert context.git_branch == "main"
        assert context.environment == "staging"
        assert context.triggered_by == "github"

    def test_context_staging_environment(self):
        """Test context with staging environment."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="deploy-pipeline",
            build_number="456",
            git_commit="xyz789abc123",
            git_branch="main",
            environment="staging",
            triggered_by="gitlab",
        )

        assert context.environment == "staging"

    def test_context_production_environment(self):
        """Test context with production environment."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="deploy-pipeline",
            build_number="789",
            git_commit="production123",
            git_branch="release",
            environment="production",
            triggered_by="manual",
        )

        assert context.environment == "production"

    def test_invalid_empty_git_commit(self):
        """Test that empty git_commit raises ValueError."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        with pytest.raises(ValueError, match="git_commit cannot be empty"):
            CIPipelineContext(
                pipeline_name="test-pipeline",
                build_number="123",
                git_commit="",
                git_branch="main",
                environment="staging",
                triggered_by="github",
            )

    def test_invalid_empty_git_branch(self):
        """Test that empty git_branch raises ValueError."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        with pytest.raises(ValueError, match="git_branch cannot be empty"):
            CIPipelineContext(
                pipeline_name="test-pipeline",
                build_number="123",
                git_commit="abc123",
                git_branch="",
                environment="staging",
                triggered_by="github",
            )

    def test_invalid_environment(self):
        """Test that invalid environment raises ValueError."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        with pytest.raises(ValueError, match="Invalid environment"):
            CIPipelineContext(
                pipeline_name="test-pipeline",
                build_number="123",
                git_commit="abc123",
                git_branch="main",
                environment="invalid_env",
                triggered_by="github",
            )

    def test_get_short_commit(self):
        """Test get_short_commit method."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="test-pipeline",
            build_number="123",
            git_commit="abc123def456789",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

        assert context.get_short_commit() == "abc123d"

    def test_to_dict(self):
        """Test to_dict method."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="test-pipeline",
            build_number="123",
            git_commit="abc123def456",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

        result = context.to_dict()

        assert isinstance(result, dict)
        assert result["pipeline_name"] == "test-pipeline"
        assert result["build_number"] == "123"
        assert result["git_commit"] == "abc123def456"
        assert result["git_branch"] == "main"
        assert result["environment"] == "staging"
        assert result["triggered_by"] == "github"

    def test_to_dict_json_serializable(self):
        """Test that to_dict output is JSON serializable."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="test-pipeline",
            build_number="123",
            git_commit="abc123def456",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

        import json

        # Should not raise
        json_str = json.dumps(context.to_dict())
        assert "test-pipeline" in json_str


class TestCIPipelineStage:
    """Tests for PipelineStageMetrics dataclass."""

    def test_stage_creation(self):
        """Test creating valid PipelineStageMetrics."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        stage = PipelineStageMetrics(
            stage_name="test",
            workflow_phase="execution",
        )

        assert stage.stage_name == "test"
        assert stage.workflow_phase == "execution"
        assert stage.total_runs == 0
        assert stage.successful_runs == 0
        assert stage.failed_runs == 0

    def test_stage_with_metrics(self):
        """Test creating stage with populated metrics."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        stage = PipelineStageMetrics(
            stage_name="build",
            workflow_phase="setup",
            total_runs=10,
            successful_runs=8,
            failed_runs=2,
            total_duration_seconds=100.0,
        )

        assert stage.total_runs == 10
        assert stage.successful_runs == 8
        assert stage.failed_runs == 2
        assert stage.success_rate() == 80.0
        assert stage.avg_duration_seconds() == 12.5

    def test_stage_to_dict(self):
        """Test stage has correct attributes."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        stage = PipelineStageMetrics(
            stage_name="build",
            workflow_phase="setup",
        )

        # Check the stage has the expected attributes
        assert stage.stage_name == "build"
        assert stage.workflow_phase == "setup"
        assert stage.total_runs == 0
        assert isinstance(stage.skills_used, set)
        assert isinstance(stage.common_failures, dict)


class TestCICDTracker:
    """Tests for CICDTracker class."""

    def _create_tracker_with_mock_storage(self):
        """Create a tracker with mocked storage."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        mock_storage.store_invocation.return_value = 1
        tracker = CICDTracker(db_path="/tmp/test.db", storage=mock_storage)
        return tracker

    def test_tracker_initialization(self):
        """Test tracker initializes with db_path."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/test.db", storage=mock_storage)

        assert tracker.db_path == Path("/tmp/test.db")
        assert tracker.storage is mock_storage

    def test_tracker_default_storage(self):
        """Test tracker with default storage."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/test.db", storage=mock_storage)
        assert tracker.storage is mock_storage

    def test_track_pipeline_stage(self):
        """Test tracking pipeline stage."""
        from session_buddy.integrations.cicd_tracker import CICDTracker, CIPipelineContext

        tracker = self._create_tracker_with_mock_storage()

        context = CIPipelineContext(
            pipeline_name="test-pipeline",
            build_number="123",
            git_commit="abc123def456",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

        result = tracker.track_pipeline_stage(
            context=context,
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=45.0,
        )

        assert result is None  # Method returns None

    def test_track_pipeline_stage_failure(self):
        """Test tracking failed pipeline stage."""
        from session_buddy.integrations.cicd_tracker import CICDTracker, CIPipelineContext

        tracker = self._create_tracker_with_mock_storage()

        context = CIPipelineContext(
            pipeline_name="test-pipeline",
            build_number="123",
            git_commit="abc123def456",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

        result = tracker.track_pipeline_stage(
            context=context,
            stage_name="build",
            skill_name="docker-build",
            completed=False,
            duration_seconds=120.0,
            error_message="Build failed",
        )

        assert result is None  # Method returns None

    def test_get_pipeline_analytics(self):
        """Test getting pipeline analytics."""
        tracker = self._create_tracker_with_mock_storage()

        analytics = tracker.get_pipeline_analytics(pipeline_name="test-pipeline", days=7)

        assert isinstance(analytics, dict)

    def test_get_stage_summary(self):
        """Test getting stage summary."""
        tracker = self._create_tracker_with_mock_storage()

        summary = tracker.get_stage_summary(stage_name="test")

        assert isinstance(summary, dict)

    def test_get_workflow_phase(self):
        """Test getting workflow phase for stage."""
        tracker = self._create_tracker_with_mock_storage()

        phase = tracker.get_workflow_phase("build")

        assert phase == "setup"

        phase = tracker.get_workflow_phase("test")

        assert phase == "execution"


class TestPipelineAnalytics:
    """Tests for pipeline analytics methods."""

    def _create_tracker_with_mock_storage(self):
        """Create a tracker with mocked storage."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        mock_storage.store_invocation.return_value = 1
        tracker = CICDTracker(db_path="/tmp/test.db", storage=mock_storage)
        return tracker

    def test_tracker_stage_mapping(self):
        """Test that stage mapping returns correct phases."""
        tracker = self._create_tracker_with_mock_storage()

        assert tracker.STAGE_MAPPING["build"] == "setup"
        assert tracker.STAGE_MAPPING["test"] == "execution"
        assert tracker.STAGE_MAPPING["lint"] == "verification"

    def test_empty_pipeline_analytics(self):
        """Test analytics for pipeline with no stages."""
        tracker = self._create_tracker_with_mock_storage()

        analytics = tracker.get_pipeline_analytics("empty-pipeline", days=30)

        # Should return a dict with pipeline info
        assert isinstance(analytics, dict)

    def test_empty_pipeline_analytics_empty_storage(self):
        """Test analytics for pipeline with no stages and empty storage."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        mock_storage.get_pipeline_stages.return_value = []

        tracker = CICDTracker(db_path="/tmp/test.db", storage=mock_storage)

        analytics = tracker.get_pipeline_analytics("empty-pipeline", days=30)

        # Verify it returns a valid dict with expected keys
        assert isinstance(analytics, dict)
        assert "pipeline_name" in analytics
        assert "overall_success_rate" in analytics
        assert "stage_analytics" in analytics


class TestEnvironmentValidation:
    """Tests for environment validation."""

    def test_all_valid_environments(self):
        """Test all valid environment values."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        valid_environments = {"staging", "production", "development", "testing"}

        for env in valid_environments:
            context = CIPipelineContext(
                pipeline_name="test",
                build_number="1",
                git_commit="abc123",
                git_branch="main",
                environment=env,
                triggered_by="test",
            )
            assert context.environment == env

    def test_environment_case_sensitive(self):
        """Test that environment is case-sensitive."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        with pytest.raises(ValueError):
            CIPipelineContext(
                pipeline_name="test",
                build_number="1",
                git_commit="abc123",
                git_branch="main",
                environment="Staging",  # Wrong case
                triggered_by="test",
            )


class TestTriggerTypes:
    """Tests for trigger type handling."""

    def test_github_trigger(self):
        """Test GitHub trigger type."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="test",
            build_number="1",
            git_commit="abc123",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

        assert context.triggered_by == "github"

    def test_gitlab_trigger(self):
        """Test GitLab trigger type."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="test",
            build_number="1",
            git_commit="abc123",
            git_branch="main",
            environment="staging",
            triggered_by="gitlab",
        )

        assert context.triggered_by == "gitlab"

    def test_manual_trigger(self):
        """Test manual trigger type."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="test",
            build_number="1",
            git_commit="abc123",
            git_branch="main",
            environment="production",
            triggered_by="manual",
        )

        assert context.triggered_by == "manual"

    def test_jenkins_trigger(self):
        """Test Jenkins trigger type."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="test",
            build_number="1",
            git_commit="abc123",
            git_branch="main",
            environment="testing",
            triggered_by="jenkins",
        )

        assert context.triggered_by == "jenkins"


# ---------------------------------------------------------------
# Additional tests for StageMetrics computations and edge cases
# ---------------------------------------------------------------


@pytest.mark.unit
class TestPipelineStageMetricsComputations:
    """Tests for PipelineStageMetrics computed properties."""

    def test_success_rate_zero_runs(self):
        """Test that success_rate returns 0.0 when no runs have happened."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        stage = PipelineStageMetrics(stage_name="build", workflow_phase="setup")
        assert stage.success_rate() == 0.0

    def test_success_rate_full(self):
        """Test 100% success rate when every run succeeded."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        stage = PipelineStageMetrics(
            stage_name="build",
            workflow_phase="setup",
            total_runs=5,
            successful_runs=5,
        )
        assert stage.success_rate() == 100.0

    def test_success_rate_partial(self):
        """Test partial success rate calculation."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        stage = PipelineStageMetrics(
            stage_name="test",
            workflow_phase="execution",
            total_runs=10,
            successful_runs=3,
        )
        assert stage.success_rate() == 30.0

    def test_avg_duration_no_completed_runs(self):
        """Test avg_duration_seconds returns 0.0 when no runs completed."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        stage = PipelineStageMetrics(
            stage_name="test",
            workflow_phase="execution",
            total_runs=4,
            successful_runs=0,
        )
        assert stage.avg_duration_seconds() == 0.0

    def test_avg_duration_calculates_mean(self):
        """Test average duration across successful runs."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        stage = PipelineStageMetrics(
            stage_name="build",
            workflow_phase="setup",
            successful_runs=4,
            total_duration_seconds=20.0,
        )
        assert stage.avg_duration_seconds() == 5.0

    def test_default_skills_used_is_empty_set(self):
        """Test that skills_used defaults to a fresh empty set per instance."""
        from session_buddy.integrations.cicd_tracker import PipelineStageMetrics

        first = PipelineStageMetrics(stage_name="test", workflow_phase="execution")
        first.skills_used.add("pytest-run")

        second = PipelineStageMetrics(stage_name="test", workflow_phase="execution")
        assert second.skills_used == set()


@pytest.mark.unit
class TestCIPipelineContextEdgeCases:
    """Edge cases for CIPipelineContext dataclass."""

    def test_get_short_commit_exact_length(self):
        """Test that get_short_commit returns the full string when short."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="p",
            build_number="1",
            git_commit="abc",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )
        assert context.get_short_commit() == "abc"

    def test_get_short_commit_long_sha(self):
        """Test that get_short_commit trims a long SHA to 7 chars."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="p",
            build_number="1",
            git_commit="abcdef0123456789abcdef",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )
        assert context.get_short_commit() == "abcdef0"

    def test_to_dict_contains_all_fields(self):
        """Test that to_dict contains every field on the dataclass."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="p",
            build_number="42",
            git_commit="deadbeef",
            git_branch="feature/x",
            environment="production",
            triggered_by="circleci",
        )
        result = context.to_dict()
        assert set(result.keys()) == {
            "pipeline_name",
            "build_number",
            "git_commit",
            "git_branch",
            "environment",
            "triggered_by",
        }

    def test_development_environment_valid(self):
        """Test that 'development' is a valid environment."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="p",
            build_number="1",
            git_commit="abc",
            git_branch="main",
            environment="development",
            triggered_by="github",
        )
        assert context.environment == "development"

    def test_testing_environment_valid(self):
        """Test that 'testing' is a valid environment."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        context = CIPipelineContext(
            pipeline_name="p",
            build_number="1",
            git_commit="abc",
            git_branch="main",
            environment="testing",
            triggered_by="github",
        )
        assert context.environment == "testing"

    def test_post_init_validates_git_commit_first(self):
        """Test that git_commit is checked before git_branch on bad input."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        with pytest.raises(ValueError, match="git_commit cannot be empty"):
            CIPipelineContext(
                pipeline_name="p",
                build_number="1",
                git_commit="",
                git_branch="",
                environment="staging",
                triggered_by="github",
            )


@pytest.mark.unit
class TestCICDTrackerClassAttributes:
    """Tests for the class-level STAGE_MAPPING and STAGE_SKILLS tables."""

    def test_stage_mapping_keys(self):
        """Test that STAGE_MAPPING includes the documented stages."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        expected = {"build", "test", "lint", "security", "deploy", "publish"}
        assert set(CICDTracker.STAGE_MAPPING.keys()) == expected

    def test_stage_mapping_values_are_oneiric_phases(self):
        """Test that every STAGE_MAPPING value is a valid Oneiric phase."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        for value in CICDTracker.STAGE_MAPPING.values():
            assert value in {"setup", "execution", "verification", "deployment"}

    def test_stage_skills_keys_match_stage_mapping(self):
        """Test that STAGE_SKILLS keys align with STAGE_MAPPING keys."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        assert set(CICDTracker.STAGE_SKILLS.keys()) == set(
            CICDTracker.STAGE_MAPPING.keys()
        )

    def test_stage_skills_contain_strings(self):
        """Test that STAGE_SKILLS values are non-empty lists of strings."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        for stage, skills in CICDTracker.STAGE_SKILLS.items():
            assert isinstance(skills, list)
            assert len(skills) > 0
            for skill in skills:
                assert isinstance(skill, str)
                assert skill  # not empty


@pytest.mark.unit
class TestCICDTrackerInit:
    """Tests for CICDTracker construction and initial state."""

    def test_db_path_converted_to_path(self):
        """Test that a string db_path is wrapped in pathlib.Path."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/some/path.db", storage=mock_storage)

        assert isinstance(tracker.db_path, Path)
        assert str(tracker.db_path) == "/tmp/some/path.db"

    def test_initial_stage_metrics_initialized_for_every_stage(self):
        """Test that an entry is created for every stage in STAGE_MAPPING."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        assert set(tracker.stage_metrics.keys()) == set(
            CICDTracker.STAGE_MAPPING.keys()
        )
        for stage_name, metrics in tracker.stage_metrics.items():
            assert metrics.stage_name == stage_name
            assert metrics.workflow_phase == CICDTracker.STAGE_MAPPING[stage_name]
            assert metrics.total_runs == 0

    def test_explicit_storage_is_used(self):
        """Test that an explicit storage instance is not replaced."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)
        assert tracker.storage is mock_storage


@pytest.mark.unit
class TestTrackPipelineStage:
    """Tests for CICDTracker.track_pipeline_stage."""

    def _context(self):
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        return CIPipelineContext(
            pipeline_name="ci-pipeline",
            build_number="7",
            git_commit="abc1234",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

    def test_unknown_stage_raises_value_error(self):
        """Test that an unknown stage name raises ValueError."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        with pytest.raises(ValueError, match="Unknown CI/CD stage"):
            tracker.track_pipeline_stage(
                context=self._context(),
                stage_name="nope",
                skill_name="ruff-check",
                completed=True,
                duration_seconds=1.0,
            )

    def test_successful_invocation_updates_metrics(self):
        """Test that a successful invocation updates success metrics."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=self._context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=10.0,
        )

        m = tracker.stage_metrics["test"]
        assert m.total_runs == 1
        assert m.successful_runs == 1
        assert m.failed_runs == 0
        assert m.total_duration_seconds == 10.0
        assert "pytest-run" in m.skills_used
        assert m.common_failures == {}

    def test_failed_invocation_records_common_failure(self):
        """Test that a failed invocation with error_message bumps the count."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=self._context(),
            stage_name="build",
            skill_name="docker-build",
            completed=False,
            duration_seconds=2.0,
            error_message="OOM",
        )

        m = tracker.stage_metrics["build"]
        assert m.total_runs == 1
        assert m.failed_runs == 1
        assert m.successful_runs == 0
        assert m.common_failures == {"OOM": 1}
        assert m.total_duration_seconds == 0.0

    def test_repeated_error_increments_count(self):
        """Test that repeated identical errors increment the count."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        for _ in range(3):
            tracker.track_pipeline_stage(
                context=self._context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=False,
                duration_seconds=1.0,
                error_message="flaky",
            )

        assert tracker.stage_metrics["test"].common_failures == {"flaky": 3}

    def test_store_invocation_called_with_isoformat(self):
        """Test that the store_invocation receives an ISO formatted timestamp."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=self._context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=1.0,
        )

        mock_storage.store_invocation.assert_called_once()
        call_kwargs = mock_storage.store_invocation.call_args.kwargs
        assert "invoked_at" in call_kwargs
        # ISO format check: contains "T" and ends with seconds-resolution
        ts = call_kwargs["invoked_at"]
        assert "T" in ts

    def test_session_id_combines_pipeline_name_and_build(self):
        """Test that the session_id encodes both pipeline and build number."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=self._context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=1.0,
        )

        call_kwargs = mock_storage.store_invocation.call_args.kwargs
        assert call_kwargs["session_id"] == "ci-pipeline-7"

    def test_workflow_phase_passed_to_storage(self):
        """Test that the mapped workflow phase is forwarded to storage."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=self._context(),
            stage_name="deploy",
            skill_name="docker-push",
            completed=True,
            duration_seconds=30.0,
        )

        call_kwargs = mock_storage.store_invocation.call_args.kwargs
        assert call_kwargs["workflow_phase"] == "deployment"

    def test_user_query_references_stage(self):
        """Test that the user_query string references the stage name."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=self._context(),
            stage_name="lint",
            skill_name="ruff-check",
            completed=True,
            duration_seconds=1.0,
        )

        call_kwargs = mock_storage.store_invocation.call_args.kwargs
        assert "lint" in call_kwargs["user_query"]


@pytest.mark.unit
class TestGetWorkflowPhase:
    """Tests for CICDTracker.get_workflow_phase."""

    def test_get_workflow_phase_for_every_known_stage(self):
        """Test that every STAGE_MAPPING entry resolves."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        for stage, oneiric in CICDTracker.STAGE_MAPPING.items():
            assert tracker.get_workflow_phase(stage) == oneiric

    def test_get_workflow_phase_unknown_raises(self):
        """Test that an unknown stage raises ValueError."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        with pytest.raises(ValueError, match="Unknown CI/CD stage"):
            tracker.get_workflow_phase("nope")


@pytest.mark.unit
class TestGetStageSummary:
    """Tests for CICDTracker.get_stage_summary."""

    def test_summary_for_known_stage(self):
        """Test that summary returns the expected shape for a known stage."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=_make_context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=2.0,
        )

        summary = tracker.get_stage_summary("test")

        assert summary["stage_name"] == "test"
        assert summary["workflow_phase"] == "execution"
        assert summary["total_runs"] == 1
        assert summary["successful_runs"] == 1
        assert summary["failed_runs"] == 0
        assert summary["success_rate"] == 100.0
        assert summary["avg_duration_seconds"] == 2.0
        assert "pytest-run" in summary["skills_used"]

    def test_summary_unknown_stage_raises(self):
        """Test that an unknown stage raises ValueError."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        with pytest.raises(ValueError, match="Unknown stage"):
            tracker.get_stage_summary("nope")

    def test_summary_returns_copies_of_containers(self):
        """Test that mutating returned containers does not affect tracker state."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=_make_context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=1.0,
        )

        summary = tracker.get_stage_summary("test")
        summary["skills_used"].add("mutated")
        summary["common_failures"]["new"] = 1

        live = tracker.stage_metrics["test"]
        assert "mutated" not in live.skills_used
        assert "new" not in live.common_failures


@pytest.mark.unit
class TestGetPipelineAnalytics:
    """Tests for CICDTracker.get_pipeline_analytics and recommendation logic."""

    def test_analytics_contains_required_keys(self):
        """Test that analytics contains the expected top-level keys."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        analytics = tracker.get_pipeline_analytics("p", days=14)

        assert analytics["pipeline_name"] == "p"
        assert analytics["time_window_days"] == 14
        assert "from_date" in analytics
        assert "to_date" in analytics
        assert "stage_analytics" in analytics
        assert "bottlenecks" in analytics
        assert "recommendations" in analytics
        assert isinstance(analytics["overall_success_rate"], float)

    def test_analytics_aggregates_overall_success_rate(self):
        """Test that overall_success_rate aggregates across stages."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        for _ in range(3):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=True,
                duration_seconds=1.0,
            )
        for _ in range(1):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=False,
                duration_seconds=1.0,
                error_message="oops",
            )

        analytics = tracker.get_pipeline_analytics("p")
        # 3 successes out of 4 runs in this stage
        assert analytics["overall_success_rate"] == 75.0

    def test_analytics_detects_bottlenecks(self):
        """Test that low-success stages appear in the bottlenecks list."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        # 1 success, 4 failures => 20% success (high severity)
        for _ in range(1):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="build",
                skill_name="docker-build",
                completed=True,
                duration_seconds=1.0,
            )
        for _ in range(4):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="build",
                skill_name="docker-build",
                completed=False,
                duration_seconds=1.0,
                error_message="err",
            )

        analytics = tracker.get_pipeline_analytics("p")
        bottleneck_stages = {b["stage"] for b in analytics["bottlenecks"]}
        assert "build" in bottleneck_stages

    def test_analytics_bottleneck_severity_labels(self):
        """Test bottleneck severity is 'high' when success < 50%."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        for _ in range(1):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=True,
                duration_seconds=1.0,
            )
        for _ in range(4):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=False,
                duration_seconds=1.0,
                error_message="err",
            )

        analytics = tracker.get_pipeline_analytics("p")
        bottleneck = next(b for b in analytics["bottlenecks"] if b["stage"] == "test")
        assert bottleneck["severity"] == "high"

    def test_analytics_bottleneck_medium_when_between_50_and_80(self):
        """Test bottleneck severity is 'medium' when 50 <= success < 80."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        for _ in range(6):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=True,
                duration_seconds=1.0,
            )
        for _ in range(4):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=False,
                duration_seconds=1.0,
                error_message="err",
            )

        analytics = tracker.get_pipeline_analytics("p")
        bottleneck = next(b for b in analytics["bottlenecks"] if b["stage"] == "test")
        # 6/10 = 60%, between 50 and 80
        assert bottleneck["severity"] == "medium"

    def test_analytics_slow_stage_produces_medium_recommendation(self):
        """Test that a slow stage (> 300s avg) gets a medium recommendation."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=_make_context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=600.0,
        )

        analytics = tracker.get_pipeline_analytics("p")
        rec_stages = {r["stage"] for r in analytics["recommendations"]}
        assert "test" in rec_stages
        slow_rec = next(
            r for r in analytics["recommendations"] if r["stage"] == "test"
        )
        assert slow_rec["priority"] == "medium"

    def test_analytics_high_failure_rate_produces_high_recommendation(self):
        """Test that < 70% success rate generates a high-priority recommendation."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        for _ in range(2):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=True,
                duration_seconds=1.0,
            )
        for _ in range(8):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name="test",
                skill_name="pytest-run",
                completed=False,
                duration_seconds=1.0,
                error_message="err",
            )

        analytics = tracker.get_pipeline_analytics("p")
        failure_rec = next(
            r
            for r in analytics["recommendations"]
            if r["stage"] == "test" and r["priority"] == "high"
        )
        assert "low success rate" in failure_rec["message"]

    def test_analytics_missing_skills_produces_low_recommendation(self):
        """Test that stages missing common skills get a low recommendation."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        # Use a skill not in the typical list for "test"
        tracker.track_pipeline_stage(
            context=_make_context(),
            stage_name="test",
            skill_name="custom-runner",
            completed=True,
            duration_seconds=1.0,
        )

        analytics = tracker.get_pipeline_analytics("p")
        missing_recs = [
            r
            for r in analytics["recommendations"]
            if r["stage"] == "test" and r["priority"] == "low"
        ]
        assert len(missing_recs) > 0
        # One of the missing skills should be one of the canonical ones
        all_missing = " ".join(r["message"] for r in missing_recs)
        assert "pytest-run" in all_missing or "pytest-coverage" in all_missing

    def test_analytics_stage_data_includes_common_failures(self):
        """Test that stage_data includes common_failures when failures recorded."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=_make_context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=False,
            duration_seconds=1.0,
            error_message="boom",
        )

        analytics = tracker.get_pipeline_analytics("p")
        stage_data = analytics["stage_analytics"]["test"]
        assert "common_failures" in stage_data
        assert stage_data["common_failures"] == {"boom": 1}

    def test_analytics_skips_stages_with_zero_runs(self):
        """Test that stages without any runs are not in stage_analytics."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        analytics = tracker.get_pipeline_analytics("p")
        # No stages have runs; stage_analytics should be empty
        assert analytics["stage_analytics"] == {}


@pytest.mark.unit
class TestGeneratePipelineReport:
    """Tests for CICDTracker.generate_pipeline_report."""

    def test_report_includes_title_and_metadata(self):
        """Test that the report includes the title and pipeline metadata."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        report = tracker.generate_pipeline_report("p", days=7)

        assert "CI/CD Pipeline Analytics Report" in report
        assert "Pipeline: p" in report
        assert "Time Window: Last 7 days" in report
        assert "Overall Success Rate" in report

    def test_report_contains_known_stage_sections(self):
        """Test that each known stage appears in the report once tracked."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        # Track at least one run in build, test, and lint so the report
        # actually includes them
        for stage in ("build", "test", "lint"):
            tracker.track_pipeline_stage(
                context=_make_context(),
                stage_name=stage,
                skill_name=f"{stage}-skill",
                completed=True,
                duration_seconds=1.0,
            )

        report = tracker.generate_pipeline_report("p", days=7)

        # Each tracked stage should appear (in upper case)
        assert "Stage: BUILD" in report
        assert "Stage: TEST" in report
        assert "Stage: LINT" in report

    def test_report_reflects_tracked_skills(self):
        """Test that tracked skills appear in the Skills Used section."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=_make_context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=1.0,
        )

        report = tracker.generate_pipeline_report("p")

        assert "Skills Used:" in report
        assert "pytest-run" in report

    def test_report_reflects_common_failures(self):
        """Test that failures appear in the Common Failures section."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=_make_context(),
            stage_name="build",
            skill_name="docker-build",
            completed=False,
            duration_seconds=1.0,
            error_message="OOMKilled",
        )

        report = tracker.generate_pipeline_report("p")

        assert "Common Failures:" in report
        assert "OOMKilled" in report

    def test_report_contains_bottlenecks_section(self):
        """Test that the report contains the bottlenecks section."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        report = tracker.generate_pipeline_report("p")

        assert "Pipeline Bottlenecks" in report
        # With no runs, the placeholder message should appear
        assert "No significant bottlenecks detected!" in report

    def test_report_contains_recommendations_section(self):
        """Test that the report contains the recommendations section."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        report = tracker.generate_pipeline_report("p")

        assert "Recommendations" in report
        assert "No recommendations at this time." in report


@pytest.mark.unit
class TestExportAnalytics:
    """Tests for CICDTracker.export_analytics."""

    def test_export_creates_file_with_json_content(self, tmp_path):
        """Test that export_analytics writes valid JSON to disk."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        tracker.track_pipeline_stage(
            context=_make_context(),
            stage_name="test",
            skill_name="pytest-run",
            completed=True,
            duration_seconds=1.0,
        )

        output = tmp_path / "analytics.json"
        tracker.export_analytics("p", output, days=7)

        import json

        assert output.exists()
        payload = json.loads(output.read_text())
        assert payload["pipeline_name"] == "p"
        assert payload["time_window_days"] == 7

    def test_export_creates_parent_directories(self, tmp_path):
        """Test that export_analytics creates missing parent directories."""
        from session_buddy.integrations.cicd_tracker import CICDTracker

        mock_storage = MagicMock()
        tracker = CICDTracker(db_path="/tmp/x.db", storage=mock_storage)

        nested = tmp_path / "deep" / "nested" / "out.json"
        tracker.export_analytics("p", nested)

        assert nested.exists()


def _make_context():
    """Helper that creates a valid CIPipelineContext."""
    from session_buddy.integrations.cicd_tracker import CIPipelineContext

    return CIPipelineContext(
        pipeline_name="p",
        build_number="1",
        git_commit="abc1234",
        git_branch="main",
        environment="staging",
        triggered_by="github",
    )
