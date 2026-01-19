"""Tests for workflow_metrics_tools module.

Tests MCP tools for workflow metrics including:
- get_workflow_metrics tool wrapper
- get_session_analytics tool wrapper
- _generate_workflow_insights helper
- _generate_session_insights helper

Phase: Week 4 - Monitoring & Organization Testing
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.workflow_metrics import WorkflowMetrics


# Test helper functions directly
class TestGenerateWorkflowInsights:
    """Test _generate_workflow_insights helper."""

    def test_high_velocity_insights(self) -> None:
        """Should generate insight for high velocity (>5 commits/hour)."""
        mock_metrics = MagicMock(
            avg_velocity_commits_per_hour=7.5,
            quality_trend="stable",
            avg_session_duration_minutes=60,
            most_productive_time_of_day="morning",
            most_used_tools=[("pytest", 25)],
            avg_quality_score=75,
        )

        insights = _generate_workflow_insights(mock_metrics)

        assert any("🚀 High development velocity" in insight for insight in insights)
        assert any("7.5 commits/hour" in insight for insight in insights)

    def test_low_velocity_insights(self) -> None:
        """Should generate insight for low velocity (<2 commits/hour)."""
        mock_metrics = MagicMock(
            avg_velocity_commits_per_hour=1.2,
            quality_trend="stable",
            avg_session_duration_minutes=60,
            most_productive_time_of_day="afternoon",
            most_used_tools=[("ruff", 10)],
            avg_quality_score=70,
        )

        insights = _generate_workflow_insights(mock_metrics)

        assert any("⚠️ Low development velocity" in insight for insight in insights)
        assert any("1.2 commits/hour" in insight for insight in insights)
        assert any("may indicate blockers" in insight for insight in insights)

    def test_improving_quality_trend(self) -> None:
        """Should generate positive insight for improving quality."""
        mock_metrics = MagicMock(
            avg_velocity_commits_per_hour=3.5,
            quality_trend="improving",
            avg_session_duration_minutes=60,
            most_productive_time_of_day="morning",
            most_used_tools=[],
            avg_quality_score=80,
        )

        insights = _generate_workflow_insights(mock_metrics)

        assert any("📈 Quality improving" in insight for insight in insights)
        assert any("80/100" in insight for insight in insights)

    def test_declining_quality_trend(self) -> None:
        """Should generate warning for declining quality."""
        mock_metrics = MagicMock(
            avg_velocity_commits_per_hour=3.5,
            quality_trend="declining",
            avg_session_duration_minutes=60,
            most_productive_time_of_day="afternoon",
            most_used_tools=[],
            avg_quality_score=65,
        )

        insights = _generate_workflow_insights(mock_metrics)

        assert any("📉 Quality declining" in insight for insight in insights)
        assert any("65/100" in insight for insight in insights)
        assert any("consider reviewing recent changes" in insight for insight in insights)

    def test_long_sessions(self) -> None:
        """Should generate insight for long sessions (>120 minutes)."""
        mock_metrics = MagicMock(
            avg_velocity_commits_per_hour=3.5,
            quality_trend="stable",
            avg_session_duration_minutes=150,
            most_productive_time_of_day="morning",
            most_used_tools=[],
            avg_quality_score=75,
        )

        insights = _generate_workflow_insights(mock_metrics)

        assert any("⏱️ Long sessions" in insight for insight in insights)
        assert any("150min average" in insight for insight in insights)
        assert any("consider more frequent breaks" in insight for insight in insights)

    def test_short_sessions(self) -> None:
        """Should generate insight for short sessions (<30 minutes)."""
        mock_metrics = MagicMock(
            avg_velocity_commits_per_hour=3.5,
            quality_trend="stable",
            avg_session_duration_minutes=25,
            most_productive_time_of_day="afternoon",
            most_used_tools=[],
            avg_quality_score=75,
        )

        insights = _generate_workflow_insights(mock_metrics)

        assert any("⚡ Short sessions" in insight for insight in insights)
        assert any("25min average" in insight for insight in insights)
        assert any("good for focused work" in insight for insight in insights)

    def test_time_of_day_patterns(self) -> None:
        """Should generate insights for different times of day."""
        # Test morning
        mock_metrics = MagicMock(
            avg_velocity_commits_per_hour=3.5,
            quality_trend="stable",
            avg_session_duration_minutes=60,
            most_productive_time_of_day="morning",
            most_used_tools=[],
            avg_quality_score=75,
        )

        insights = _generate_workflow_insights(mock_metrics)
        assert any("🌅 Most productive in morning" in insight for insight in insights)

        # Test evening
        mock_metrics.most_productive_time_of_day = "evening"
        insights = _generate_workflow_insights(mock_metrics)
        assert any("🌆 Most productive in evening" in insight for insight in insights)

        # Test night
        mock_metrics.most_productive_time_of_day = "night"
        insights = _generate_workflow_insights(mock_metrics)
        assert any("🌙 Most productive at night" in insight for insight in insights)

    def test_most_used_tool(self) -> None:
        """Should generate insight for most used tool."""
        mock_metrics = MagicMock(
            avg_velocity_commits_per_hour=3.5,
            quality_trend="stable",
            avg_session_duration_minutes=60,
            most_productive_time_of_day="afternoon",
            most_used_tools=[("pytest", 42), ("ruff", 15)],
            avg_quality_score=75,
        )

        insights = _generate_workflow_insights(mock_metrics)

        assert any("🔧 Most used tool" in insight for insight in insights)
        assert any("pytest" in insight for insight in insights)
        assert any("42 times" in insight for insight in insights)


class TestGenerateSessionInsights:
    """Test _generate_session_insights helper."""

    def test_no_sessions(self) -> None:
        """Should return no data message when no sessions provided."""
        insights = _generate_session_insights([])

        assert insights == ["No sessions analyzed"]

    def test_high_quality_sessions(self) -> None:
        """Should identify high-quality sessions (≥80)."""
        sessions = [
            {"avg_quality": 85, "duration_minutes": 60, "commit_count": 5, "primary_language": "Python"},
            {"avg_quality": 90, "duration_minutes": 90, "commit_count": 8, "primary_language": "Python"},
            {"avg_quality": 70, "duration_minutes": 45, "commit_count": 3, "primary_language": "Python"},
        ]

        insights = _generate_session_insights(sessions)

        assert any("✅ 2 high-quality sessions" in insight for insight in insights)

    def test_low_quality_sessions(self) -> None:
        """Should identify low-quality sessions (<60)."""
        sessions = [
            {"avg_quality": 85, "duration_minutes": 60, "commit_count": 5},
            {"avg_quality": 55, "duration_minutes": 45, "commit_count": 2},
            {"avg_quality": 50, "duration_minutes": 30, "commit_count": 1},
        ]

        insights = _generate_session_insights(sessions)

        assert any("⚠️ 2 sessions need attention" in insight for insight in insights)

    def test_marathon_sessions(self) -> None:
        """Should identify marathon sessions (>120 minutes)."""
        sessions = [
            {"duration_minutes": 150, "avg_quality": 75, "commit_count": 8, "primary_language": "TypeScript"},
            {"duration_minutes": 180, "avg_quality": 80, "commit_count": 12, "primary_language": "TypeScript"},
            {"duration_minutes": 60, "avg_quality": 70, "commit_count": 4, "primary_language": "TypeScript"},
        ]

        insights = _generate_session_insights(sessions)

        assert any("📊 2 marathon sessions" in insight for insight in insights)

    def test_quick_sessions(self) -> None:
        """Should identify quick sessions (<30 minutes)."""
        sessions = [
            {"duration_minutes": 25, "avg_quality": 75, "commit_count": 2, "primary_language": "Rust"},
            {"duration_minutes": 20, "avg_quality": 70, "commit_count": 1, "primary_language": "Rust"},
            {"duration_minutes": 60, "avg_quality": 80, "commit_count": 5, "primary_language": "Rust"},
        ]

        insights = _generate_session_insights(sessions)

        assert any("⚡ 2 quick sessions" in insight for insight in insights)

    def test_zero_commit_sessions(self) -> None:
        """Should identify sessions with no commits."""
        sessions = [
            {"commit_count": 0, "avg_quality": 65, "duration_minutes": 60, "primary_language": "Go"},
            {"commit_count": 5, "avg_quality": 75, "duration_minutes": 45, "primary_language": "Go"},
            {"commit_count": 0, "avg_quality": 60, "duration_minutes": 30, "primary_language": "Go"},
        ]

        insights = _generate_session_insights(sessions)

        assert any("📝 2 sessions with no commits" in insight for insight in insights)

    def test_high_commitment_sessions(self) -> None:
        """Should identify high-commitment sessions (≥10 commits)."""
        sessions = [
            {"commit_count": 15, "avg_quality": 80, "duration_minutes": 120, "primary_language": "Java"},
            {"commit_count": 12, "avg_quality": 85, "duration_minutes": 150, "primary_language": "Java"},
            {"commit_count": 5, "avg_quality": 70, "duration_minutes": 60, "primary_language": "Java"},
        ]

        insights = _generate_session_insights(sessions)

        assert any("🔥 2 high-commitment sessions" in insight for insight in insights)

    def test_language_diversity(self) -> None:
        """Should identify primary programming language."""
        sessions = [
            {"primary_language": "Python", "avg_quality": 80, "duration_minutes": 60, "commit_count": 5},
            {"primary_language": "Python", "avg_quality": 75, "duration_minutes": 45, "commit_count": 3},
            {"primary_language": "Python", "avg_quality": 85, "duration_minutes": 90, "commit_count": 8},
            {"primary_language": "TypeScript", "avg_quality": 70, "duration_minutes": 30, "commit_count": 2},
        ]

        insights = _generate_session_insights(sessions)

        assert any("💻 Primary language: Python" in insight for insight in insights)
        assert any("3 sessions" in insight for insight in insights)

    def test_comprehensive_insights(self) -> None:
        """Should generate multiple insights for mixed session data."""
        sessions = [
            {
                "avg_quality": 85,
                "duration_minutes": 150,
                "commit_count": 15,
                "primary_language": "Python",
            },
            {
                "avg_quality": 55,
                "duration_minutes": 25,
                "commit_count": 0,
                "primary_language": "Python",
            },
            {
                "avg_quality": 90,
                "duration_minutes": 180,
                "commit_count": 12,
                "primary_language": "Python",
            },
        ]

        insights = _generate_session_insights(sessions)

        # Should have multiple insights
        assert len(insights) >= 4
        # Should detect high quality
        assert any("high-quality" in insight for insight in insights)
        # Should detect low quality
        assert any("need attention" in insight for insight in insights)
        # Should detect marathon sessions
        assert any("marathon" in insight for insight in insights)
        # Should detect quick sessions
        assert any("quick" in insight for insight in insights)


# Test MCP tool wrappers (basic integration tests)
class TestWorkflowMetricsTools:
    """Test workflow_metrics_tools MCP tool registration."""

    @pytest.fixture
    def mock_server(self) -> MagicMock:
        """Create a mock server."""
        server = MagicMock()

        # Mock tool and prompt registration to capture decorated functions
        registered_tools = {}
        registered_prompts = {}

        def mock_tool(**kwargs):
            def decorator(func):
                registered_tools[func.__name__] = func
                return func

            return decorator

        def mock_prompt(**kwargs):
            def decorator(func):
                registered_prompts[func.__name__] = func
                return func

            return decorator

        server.tool = mock_tool
        server.prompt = mock_prompt
        server._registered_tools = registered_tools
        server._registered_prompts = registered_prompts

        return server

    def test_register_workflow_metrics_tools(self, mock_server: MagicMock) -> None:
        """Should register workflow metrics tools on server."""
        from session_buddy.tools.workflow_metrics_tools import register_workflow_metrics_tools

        register_workflow_metrics_tools(mock_server)

        # Verify tools were registered
        assert "get_workflow_metrics" in mock_server._registered_tools
        assert "get_session_analytics" in mock_server._registered_tools

    def test_workflow_metrics_help_prompt(self, mock_server: MagicMock) -> None:
        """Should register help prompt for workflow metrics."""
        from session_buddy.tools.workflow_metrics_tools import register_workflow_metrics_tools

        register_workflow_metrics_tools(mock_server)

        # Verify prompt was registered
        assert "workflow_metrics_help" in mock_server._registered_prompts
        help_prompt = mock_server._registered_prompts["workflow_metrics_help"]()

        # Verify help content
        assert "Workflow Metrics" in help_prompt
        assert "get_workflow_metrics" in help_prompt
        assert "get_session_analytics" in help_prompt


# Import helper functions for testing
from session_buddy.tools.workflow_metrics_tools import (
    _generate_workflow_insights,
    _generate_session_insights,
)
