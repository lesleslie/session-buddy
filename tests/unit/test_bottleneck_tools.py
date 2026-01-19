"""Tests for bottleneck_tools module.

Tests MCP tools for bottleneck detection including:
- Insight generation helpers
- Bottleneck synthesis logic

Note: The actual MCP tools are registered via register_bottleneck_tools(),
so this test file focuses on testing the helper functions and logic.

Phase: Week 4 - Monitoring & Organization Testing
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import actual helper functions from bottleneck_tools.py
from session_buddy.tools.bottleneck_tools import (
    _generate_quality_bottleneck_insights,
    _generate_velocity_bottleneck_insights,
    _generate_pattern_bottleneck_insights,
    _synthesize_bottleneck_insights,
)


# Test helper functions directly
class TestGenerateQualityBottleneckInsights:
    """Test _generate_quality_bottleneck_insights helper."""

    def test_no_quality_drops(self) -> None:
        """Should generate positive insight when no quality drops."""
        mock_bottleneck = MagicMock(
            sudden_quality_drops=0,
            consecutive_low_quality_sessions=0,
            avg_recovery_time_hours=0,
            low_quality_periods=[],
            most_common_quality_drop_cause=None,
        )

        insights = _generate_quality_bottleneck_insights(mock_bottleneck)

        assert any("✅ No sudden quality drops" in insight for insight in insights)

    def test_frequent_quality_drops(self) -> None:
        """Should generate warning for frequent quality drops."""
        mock_bottleneck = MagicMock(
            sudden_quality_drops=5,
            consecutive_low_quality_sessions=3,
            avg_recovery_time_hours=24.0,
            low_quality_periods=[],
            most_common_quality_drop_cause=None,
        )

        insights = _generate_quality_bottleneck_insights(mock_bottleneck)

        assert any("🚨 Frequent quality drops" in insight for insight in insights)
        assert any("5 instances" in insight for insight in insights)

    def test_slow_recovery(self) -> None:
        """Should generate warning for slow recovery time."""
        mock_bottleneck = MagicMock(
            sudden_quality_drops=2,
            consecutive_low_quality_sessions=0,
            avg_recovery_time_hours=48.0,
            low_quality_periods=[],
            most_common_quality_drop_cause=None,
        )

        insights = _generate_quality_bottleneck_insights(mock_bottleneck)

        assert any("🐌 Slow recovery" in insight for insight in insights)
        assert any("48.0h" in insight for insight in insights)


class TestGenerateVelocityBottleneckInsights:
    """Test _generate_velocity_bottleneck_insights helper."""

    def test_no_velocity_issues(self) -> None:
        """Should generate positive insight when velocity is healthy."""
        mock_bottleneck = MagicMock(
            low_velocity_sessions=0,
            zero_commit_sessions=0,
            long_sessions_without_commits=0,
            velocity_stagnation_days=0,
        )

        insights = _generate_velocity_bottleneck_insights(mock_bottleneck)

        assert any("✅ No low-velocity sessions" in insight for insight in insights)

    def test_many_zero_commit_sessions(self) -> None:
        """Should generate warning for many zero-commit sessions."""
        mock_bottleneck = MagicMock(
            low_velocity_sessions=10,
            zero_commit_sessions=8,
            long_sessions_without_commits=2,
            velocity_stagnation_days=0,
        )

        insights = _generate_velocity_bottleneck_insights(mock_bottleneck)

        assert any("🚨 High zero-commit count" in insight for insight in insights)

    def test_velocity_stagnation(self) -> None:
        """Should generate warning for velocity stagnation."""
        mock_bottleneck = MagicMock(
            low_velocity_sessions=5,
            zero_commit_sessions=2,
            long_sessions_without_commits=0,
            velocity_stagnation_days=7,
        )

        insights = _generate_velocity_bottleneck_insights(mock_bottleneck)

        assert any("📉 Declining trend" in insight for insight in insights)


class TestGeneratePatternBottleneckInsights:
    """Test _generate_pattern_bottleneck_insights helper."""

    def test_no_pattern_issues(self) -> None:
        """Should generate positive insight when patterns are healthy."""
        mock_bottleneck = MagicMock(
            marathon_sessions=0,
            fragmented_work_sessions=2,
            infrequent_checkpoint_sessions=1,
            excessive_session_gaps=12.0,
            inconsistent_schedule_score=25.0,
        )

        insights = _generate_pattern_bottleneck_insights(mock_bottleneck)

        assert any("✅ No marathon sessions" in insight for insight in insights)

    def test_marathon_sessions(self) -> None:
        """Should generate warning for marathon sessions."""
        mock_bottleneck = MagicMock(
            marathon_sessions=6,
            fragmented_work_sessions=3,
            infrequent_checkpoint_sessions=1,
            excessive_session_gaps=12.0,
            inconsistent_schedule_score=45.0,
        )

        insights = _generate_pattern_bottleneck_insights(mock_bottleneck)

        assert any("🔥 Frequent marathons" in insight for insight in insights)

    def test_high_inconsistency(self) -> None:
        """Should generate warning for inconsistent schedule."""
        mock_bottleneck = MagicMock(
            marathon_sessions=2,
            fragmented_work_sessions=5,
            infrequent_checkpoint_sessions=1,
            excessive_session_gaps=12.0,
            inconsistent_schedule_score=75.0,
        )

        insights = _generate_pattern_bottleneck_insights(mock_bottleneck)

        assert any("🔄 Highly inconsistent" in insight for insight in insights)


class TestSynthesizeBottleneckInsights:
    """Test _synthesize_bottleneck_insights helper."""

    def test_synthesis_critical_bottlenecks(self) -> None:
        """Should identify critical bottlenecks across all types."""
        insights_mock = MagicMock(
            critical_bottlenecks=["Quality drops", "Marathon sessions"],
            improvement_recommendations=["Take breaks"],
            workflow_optimization_opportunities=["Automate checkpoints"],
        )

        result = _synthesize_bottleneck_insights(insights_mock)

        assert isinstance(result, list)
        assert len(result) > 0
        # Should mention critical bottleneck count
        assert any("critical" in insight.lower() for insight in result)

    def test_synthesis_recommendations(self) -> None:
        """Should generate actionable recommendations."""
        insights_mock = MagicMock(
            critical_bottlenecks=["Quality drops"],
            improvement_recommendations=["Take breaks", "Set reminders"],
            workflow_optimization_opportunities=["Optimize session length"],
        )

        result = _synthesize_bottleneck_insights(insights_mock)

        assert isinstance(result, list)
        assert len(result) > 0
        # Should mention recommendations
        assert any("recommendation" in insight.lower() for insight in result)

    def test_synthesis_health_score(self) -> None:
        """Should identify when workflow is healthy."""
        insights_mock = MagicMock(
            critical_bottlenecks=[],
            improvement_recommendations=[],
            workflow_optimization_opportunities=[],
        )

        result = _synthesize_bottleneck_insights(insights_mock)

        assert isinstance(result, list)
        assert len(result) > 0
        # Should mention healthy workflow
        assert any("healthy" in insight.lower() or "no critical" in insight.lower() for insight in result)

    def test_synthesis_impact_estimation(self) -> None:
        """Should provide impact estimation."""
        insights_mock = MagicMock(
            critical_bottlenecks=[],
            improvement_recommendations=[],
            workflow_optimization_opportunities=[],
        )

        result = _synthesize_bottleneck_insights(insights_mock)

        assert isinstance(result, list)
        assert len(result) > 0
