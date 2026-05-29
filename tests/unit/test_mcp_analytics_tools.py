from __future__ import annotations

from types import SimpleNamespace


def test_workflow_metrics_insights_cover_branches() -> None:
    from session_buddy.mcp.tools.monitoring.workflow_metrics_tools import (
        _generate_session_insights,
        _generate_workflow_insights,
    )

    workflow_metrics = SimpleNamespace(
        avg_velocity_commits_per_hour=6.2,
        quality_trend="declining",
        avg_quality_score=72,
        avg_session_duration_minutes=150,
        most_productive_time_of_day="morning",
        most_used_tools=[("search", 11)],
    )

    workflow_insights = _generate_workflow_insights(workflow_metrics)
    assert any("high development velocity" in item.lower() for item in workflow_insights)
    assert any("quality declining" in item.lower() for item in workflow_insights)
    assert any("long sessions" in item.lower() for item in workflow_insights)
    assert any("most productive in morning" in item.lower() for item in workflow_insights)
    assert any("most used tool" in item.lower() for item in workflow_insights)

    sessions = [
        {
            "avg_quality": 90,
            "duration_minutes": 180,
            "commit_count": 12,
            "primary_language": "Python",
        },
        {
            "avg_quality": 55,
            "duration_minutes": 20,
            "commit_count": 0,
            "primary_language": "Python",
        },
        {
            "avg_quality": 50,
            "duration_minutes": 10,
            "commit_count": 1,
            "primary_language": "Rust",
        },
    ]

    session_insights = _generate_session_insights(sessions)
    assert any("high-quality sessions" in item.lower() for item in session_insights)
    assert any("sessions need attention" in item.lower() for item in session_insights)
    assert any("marathon sessions" in item.lower() for item in session_insights)
    assert any("quick sessions" in item.lower() for item in session_insights)
    assert any("no commits" in item.lower() for item in session_insights)
    assert any("high-commitment" in item.lower() for item in session_insights)
    assert any("primary language" in item.lower() for item in session_insights)


def test_session_analytics_insights_cover_branches() -> None:
    from session_buddy.mcp.tools.monitoring.session_analytics_tools import (
        _generate_correlation_insights,
        _generate_length_distribution_insights,
        _generate_productivity_insights,
        _generate_streak_insights,
        _generate_temporal_patterns_insights,
    )

    length = SimpleNamespace(
        total_sessions=10,
        medium_percentage=60,
        short_percentage=10,
        long_percentage=30,
        avg_duration_minutes=145,
        median_duration_minutes=90,
    )
    temporal = SimpleNamespace(
        session_frequency_trend="increasing",
        most_productive_time_slot="Tuesday morning",
        avg_sessions_per_day=2.5,
        time_of_day_distribution={"morning": 8, "afternoon": 2},
    )
    correlations = SimpleNamespace(
        duration_quality_correlation=0.4,
        quality_commits_correlation=-0.5,
        high_quality_sessions=8,
        low_quality_sessions=2,
        long_high_quality_sessions=3,
    )
    streaks = SimpleNamespace(
        total_active_days=20,
        current_streak_days=8,
        longest_streak_days=15,
        consistent_daily_sessions=True,
        avg_gap_between_sessions_hours=12,
        most_consistent_week="2026-W01",
    )
    productivity = SimpleNamespace(
        best_performance_window="morning",
        recommended_session_length="90 minutes",
        optimal_break_interval=45,
        peak_productivity_periods=["morning", "evening"],
        quality_factors=["tests", "focus"],
        improvement_suggestions=["sleep more"],
    )

    length_insights = _generate_length_distribution_insights(length)
    temporal_insights = _generate_temporal_patterns_insights(temporal)
    correlation_insights = _generate_correlation_insights(correlations)
    streak_insights = _generate_streak_insights(streaks)
    productivity_insights = _generate_productivity_insights(productivity)

    assert any("balanced schedule" in item.lower() for item in length_insights)
    assert any("long average" in item.lower() for item in length_insights)
    assert any("variability" in item.lower() for item in length_insights)

    assert any("increasing session frequency" in item.lower() for item in temporal_insights)
    assert any("peak productivity" in item.lower() for item in temporal_insights)
    assert any("high frequency" in item.lower() for item in temporal_insights)
    assert any("primary work time" in item.lower() for item in temporal_insights)

    assert any("longer sessions correlate" in item.lower() for item in correlation_insights)
    assert any("fewer commits correlate" in item.lower() for item in correlation_insights)
    assert any("high quality rate" in item.lower() for item in correlation_insights)
    assert any("marathon sessions" in item.lower() for item in correlation_insights)

    assert any("strong momentum" in item.lower() for item in streak_insights)
    assert any("excellent consistency" in item.lower() for item in streak_insights)
    assert any("consistent daily work" in item.lower() for item in streak_insights)
    assert any("frequent engagement" in item.lower() for item in streak_insights)
    assert any("best week" in item.lower() for item in streak_insights)

    assert any("optimal time" in item.lower() for item in productivity_insights)
    assert any("recommended length" in item.lower() for item in productivity_insights)
    assert any("break interval" in item.lower() for item in productivity_insights)
    assert any("peak periods" in item.lower() for item in productivity_insights)
    assert any("tests" in item.lower() for item in productivity_insights)
    assert any("sleep more" in item.lower() for item in productivity_insights)
