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
