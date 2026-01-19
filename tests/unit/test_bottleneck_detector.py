"""Tests for bottleneck_detector module.

Tests bottleneck detection including:
- Quality bottleneck detection (sudden drops, consecutive low quality)
- Velocity bottleneck detection (low commits, zero-commit sessions)
- Session pattern bottlenecks (marathons, fragmentation, consistency)
- Bottleneck insights synthesis

Phase: Week 4 - Monitoring & Organization Testing
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.core.bottleneck_detector import (
    BottleneckDetector,
    QualityBottleneck,
    VelocityBottleneck,
    SessionPatternBottleneck,
    BottleneckInsights,
)


class TestBottleneckDetector:
    """Test BottleneckDetector class for workflow impediment detection."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database connection."""
        db = MagicMock()

        # Create a mock result that behaves like fetchall/fetchone
        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[])
        mock_result.fetchone = MagicMock(return_value=None)

        # Make execute return the mock result
        db.execute = MagicMock(return_value=mock_result)
        db.fetchall = MagicMock(return_value=[])
        db.fetchone = MagicMock(return_value=None)

        return db

    @pytest.fixture
    def detector(self, mock_db: MagicMock) -> BottleneckDetector:
        """Create BottleneckDetector instance with mock database."""
        with patch("session_buddy.core.bottleneck_detector.duckdb.connect", return_value=mock_db):
            detector = BottleneckDetector(db_path=":memory:")
            # Pre-set the connection to our mock
            detector._conn = mock_db
            return detector

    @pytest.mark.asyncio
    async def test_initialize_opens_connection(self, detector: BottleneckDetector) -> None:
        """Should open database connection on initialization."""
        await detector.initialize()
        assert detector._conn is not None

    @pytest.mark.asyncio
    async def test_detect_quality_bottlenecks_sudden_drops(self, detector: BottleneckDetector, mock_db: MagicMock) -> None:
        """Should detect sudden quality drops (>10 point decline)."""
        # Mock quality drop count
        mock_result = mock_db.execute.return_value
        mock_result.fetchone.return_value = (5,)  # 5 sudden quality drops
        mock_result.fetchall.return_value = []

        result = await detector.detect_quality_bottlenecks(project_path="/test/project", days_back=30)

        assert result.sudden_quality_drops == 5
        assert isinstance(result, QualityBottleneck)

    @pytest.mark.asyncio
    async def test_detect_quality_bottlenecks_consecutive_low_quality(self, detector: BottleneckDetector, mock_db: MagicMock) -> None:
        """Should detect consecutive low quality sessions."""
        # Mock consecutive low quality sessions
        mock_result = mock_db.execute.return_value
        mock_result.fetchall.return_value = [
            (datetime.now(UTC), 55.0, 70.0),
            (datetime.now(UTC) - timedelta(hours=2), 50.0, 65.0),
            (datetime.now(UTC) - timedelta(hours=4), 58.0, 62.0),
        ]
        mock_result.fetchone.return_value = None

        result = await detector.detect_quality_bottlenecks(project_path="/test/project", days_back=30)

        assert result.consecutive_low_quality_sessions >= 0

    @pytest.mark.asyncio
    async def test_detect_velocity_bottlenecks_low_velocity(self, detector: BottleneckDetector, mock_db: MagicMock) -> None:
        """Should detect low velocity sessions (<2 commits/hour)."""
        # Mock velocity metrics
        mock_result = mock_db.execute.return_value
        mock_result.fetchone.return_value = (3,)  # 3 low velocity sessions
        mock_result.fetchall.return_value = []

        result = await detector.detect_velocity_bottlenecks(project_path="/test/project", days_back=30)

        assert result.low_velocity_sessions == 3
        assert isinstance(result, VelocityBottleneck)

    @pytest.mark.asyncio
    async def test_detect_velocity_bottlenecks_zero_commits(self, detector: BottleneckDetector, mock_db: MagicMock) -> None:
        """Should detect zero-commit sessions."""
        mock_result = mock_db.execute.return_value
        mock_result.fetchone.return_value = (2,)  # 2 zero-commit sessions

        result = await detector.detect_velocity_bottlenecks(project_path="/test/project", days_back=30)

        assert result.zero_commit_sessions == 2

    @pytest.mark.asyncio
    async def test_detect_session_pattern_bottlenecks_marathons(self, detector: BottleneckDetector, mock_db: MagicMock) -> None:
        """Should detect marathon sessions (>4 hours)."""
        # Mock marathon session count
        mock_result = mock_db.execute.return_value
        mock_result.fetchone.return_value = (4,)  # 4 marathon sessions
        mock_result.fetchall.return_value = []

        result = await detector.detect_session_pattern_bottlenecks(project_path="/test/project", days_back=30)

        assert result.marathon_sessions == 4
        assert isinstance(result, SessionPatternBottleneck)

    @pytest.mark.asyncio
    async def test_detect_session_pattern_bottlenecks_fragmentation(self, detector: BottleneckDetector, mock_db: MagicMock) -> None:
        """Should detect fragmented work sessions (<15 minutes)."""
        mock_result = mock_db.execute.return_value
        mock_result.fetchone.return_value = (8,)  # 8 fragmented sessions

        result = await detector.detect_session_pattern_bottlenecks(project_path="/test/project", days_back=30)

        assert result.fragmented_work_sessions == 8

    @pytest.mark.asyncio
    async def test_detect_session_pattern_bottlenecks_consistency_score(self, detector: BottleneckDetector, mock_db: MagicMock) -> None:
        """Should calculate inconsistency score (0-100)."""
        # Mock inconsistency score calculation
        mock_result = mock_db.execute.return_value
        mock_result.fetchone.return_value = (65.0,)  # 65/100 inconsistency score

        result = await detector.detect_session_pattern_bottlenecks(project_path="/test/project", days_back=30)

        assert result.inconsistent_schedule_score == 65.0
        assert 0 <= result.inconsistent_schedule_score <= 100

    @pytest.mark.asyncio
    async def test_get_bottleneck_insights_synthesis(self, detector: BottleneckDetector, mock_db: MagicMock) -> None:
        """Should synthesize insights across all bottleneck types."""
        # Mock individual bottleneck queries
        mock_result = mock_db.execute.return_value
        mock_result.fetchall.return_value = []
        mock_result.fetchone.return_value = (2,)

        result = await detector.get_bottleneck_insights(project_path="/test/project", days_back=30)

        assert isinstance(result, BottleneckInsights)
        assert "critical_bottlenecks" in result.to_dict()
        assert "improvement_recommendations" in result.to_dict()
        assert "estimated_impact_if_resolved" in result.to_dict()


class TestQualityBottleneck:
    """Test QualityBottleneck dataclass."""

    def test_quality_bottleneck_creation(self) -> None:
        """Should create QualityBottleneck with valid data."""
        bottleneck = QualityBottleneck(
            sudden_quality_drops=3,
            consecutive_low_quality_sessions=5,
            low_quality_periods=[
                {"start": "2025-01-01", "end": "2025-01-03", "avg_quality": 55.0},
            ],
            avg_recovery_time_hours=12.5,
            most_common_quality_drop_cause="fatigue",
        )

        assert bottleneck.sudden_quality_drops == 3
        assert bottleneck.consecutive_low_quality_sessions == 5
        assert len(bottleneck.low_quality_periods) == 1
        assert bottleneck.avg_recovery_time_hours == 12.5

    def test_quality_bottleneck_to_dict(self) -> None:
        """Should convert to dictionary for JSON serialization."""
        bottleneck = QualityBottleneck(
            sudden_quality_drops=2,
            consecutive_low_quality_sessions=3,
            low_quality_periods=[],
            avg_recovery_time_hours=8.0,
            most_common_quality_drop_cause=None,
        )

        result = bottleneck.to_dict()

        assert isinstance(result, dict)
        assert result["sudden_quality_drops"] == 2
        assert result["avg_recovery_time_hours"] == 8.0
        assert result["most_common_quality_drop_cause"] is None


class TestVelocityBottleneck:
    """Test VelocityBottleneck dataclass."""

    def test_velocity_bottleneck_creation(self) -> None:
        """Should create VelocityBottleneck with valid data."""
        bottleneck = VelocityBottleneck(
            low_velocity_sessions=5,
            zero_commit_sessions=2,
            long_sessions_without_commits=3,
            avg_commits_per_hour_low_periods=1.2,
            velocity_stagnation_days=4,
        )

        assert bottleneck.low_velocity_sessions == 5
        assert bottleneck.zero_commit_sessions == 2
        assert bottleneck.avg_commits_per_hour_low_periods == 1.2


class TestSessionPatternBottleneck:
    """Test SessionPatternBottleneck dataclass."""

    def test_session_pattern_bottleneck_creation(self) -> None:
        """Should create SessionPatternBottleneck with valid data."""
        bottleneck = SessionPatternBottleneck(
            marathon_sessions=3,
            fragmented_work_sessions=10,
            infrequent_checkpoint_sessions=5,
            excessive_session_gaps=48.0,  # 48 hours between sessions
            inconsistent_schedule_score=70.0,
        )

        assert bottleneck.marathon_sessions == 3
        assert bottleneck.fragmented_work_sessions == 10
        assert bottleneck.excessive_session_gaps == 48.0
        assert 0 <= bottleneck.inconsistent_schedule_score <= 100


class TestBottleneckInsights:
    """Test BottleneckInsights dataclass."""

    def test_bottleneck_insights_creation(self) -> None:
        """Should create BottleneckInsights with synthesized analysis."""
        insights = BottleneckInsights(
            critical_bottlenecks=["Quality drops", "Marathon sessions"],
            improvement_recommendations=["Take breaks every 2 hours", "Set commit reminders"],
            workflow_optimization_opportunities=["Automate checkpoints", "Optimize session length"],
            estimated_impact_if_resolved="High - addressing bottlenecks could improve velocity by 30%",
        )

        assert len(insights.critical_bottlenecks) == 2
        assert len(insights.improvement_recommendations) == 2
        assert len(insights.workflow_optimization_opportunities) == 2

    def test_bottleneck_insights_to_dict(self) -> None:
        """Should convert to dictionary for JSON serialization."""
        insights = BottleneckInsights(
            critical_bottlenecks=["Velocity stagnation"],
            improvement_recommendations=["Increase commit frequency"],
            workflow_optimization_opportunities=["Schedule regular checkpoints"],
            estimated_impact_if_resolved="Medium",
        )

        result = insights.to_dict()

        assert isinstance(result, dict)
        assert result["estimated_impact_if_resolved"] == "Medium"
        assert "critical_bottlenecks" in result
        assert "improvement_recommendations" in result


class TestBottleneckThresholds:
    """Test configurable bottleneck detection thresholds."""

    @pytest.fixture
    def detector(self) -> BottleneckDetector:
        """Create detector with default thresholds."""
        return BottleneckDetector(db_path=":memory:")

    def test_default_quality_thresholds(self, detector: BottleneckDetector) -> None:
        """Should have default quality thresholds."""
        assert detector.QUALITY_DROP_THRESHOLD == -10
        assert detector.LOW_QUALITY_THRESHOLD == 60

    def test_default_velocity_thresholds(self, detector: BottleneckDetector) -> None:
        """Should have default velocity thresholds."""
        assert detector.LOW_VELOCITY_THRESHOLD == 2

    def test_default_session_pattern_thresholds(self, detector: BottleneckDetector) -> None:
        """Should have default session pattern thresholds."""
        assert detector.MARATHON_SESSION_THRESHOLD == 240  # 4 hours
        assert detector.FRAGMENTED_SESSION_THRESHOLD == 15  # 15 minutes
        assert detector.CHECKPOINT_FREQUENCY_THRESHOLD == 0.1
