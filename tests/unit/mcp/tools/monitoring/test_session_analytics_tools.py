"""Tests for session_buddy.mcp.tools.monitoring.session_analytics_tools.

Covers the session analytics MCP tool registration:
- ``_generate_length_distribution_insights``: empty total → "No
  sessions analyzed"; balance branches (medium > 50 → ✅ balanced,
  short > 60 → ⚡ fragmented, long > 40 → 🔥 marathon); duration
  branches (avg > 120 → ⏰ long, avg < 30 → ⚡ short); variability
  branch (|median vs avg| > 30%) → 📊.
- ``_generate_temporal_patterns_insights``: frequency trend
  (increasing/decreasing/stable); peak productivity window; avg
  sessions/day (≥2 → 🔄, <0.5 → 📅, else none); top time of day.
- ``_generate_correlation_insights``: |duration-quality| > 0.3 (positive
  → ✅, negative → ⚡); |quality-commits| > 0.3 (positive → ✅, negative
  → 🎯); high quality rate (>70 → 🌟, <40 → ⚠️); long high-quality
  sessions count → 🏆.
- ``_generate_streak_insights``: empty total_active_days → "No session
  data available"; current streak (≥7 → 🔥, ≥3 → 📈); longest streak
  (≥14 → 💪, ≥7 → ✅); consistent daily sessions flag; avg gap
  (>48 → ⚠️, <24 → ✅); most consistent week.
- ``_generate_productivity_insights``: best performance window,
  recommended length, optimal break interval (always emitted),
  peak periods, quality factors, improvement suggestions.
- ``register_session_analytics_tools``: registers 5 tools + 1 prompt.
- 5 tools: happy path with insights, project_path + days_back
  propagated, exception path.
- ``session_analytics_help``: returns the static help text.

The analytics engine is patched on the module's symbol because
``get_session_analytics`` is imported at module level into
``session_analytics_tools``'s namespace.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.monitoring import session_analytics_tools
from session_buddy.mcp.tools.monitoring.session_analytics_tools import (
    _generate_correlation_insights,
    _generate_length_distribution_insights,
    _generate_productivity_insights,
    _generate_streak_insights,
    _generate_temporal_patterns_insights,
    register_session_analytics_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_length_distribution(**overrides) -> SimpleNamespace:
    base = dict(
        total_sessions=10,
        short_percentage=20.0,
        medium_percentage=60.0,
        long_percentage=20.0,
        avg_duration_minutes=60.0,
        median_duration_minutes=60.0,
    )
    base.update(overrides)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


def _make_temporal_patterns(**overrides) -> SimpleNamespace:
    base = dict(
        session_frequency_trend="stable",
        most_productive_time_slot="",
        avg_sessions_per_day=1.0,
        time_of_day_distribution={},
    )
    base.update(overrides)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


def _make_correlations(**overrides) -> SimpleNamespace:
    base = dict(
        duration_quality_correlation=0.0,
        quality_commits_correlation=0.0,
        high_quality_sessions=0,
        low_quality_sessions=0,
        long_high_quality_sessions=0,
    )
    base.update(overrides)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


def _make_streaks(**overrides) -> SimpleNamespace:
    base = dict(
        total_active_days=10,
        current_streak_days=0,
        longest_streak_days=0,
        consistent_daily_sessions=False,
        avg_gap_between_sessions_hours=24.0,
        most_consistent_week="",
    )
    base.update(overrides)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


def _make_productivity(**overrides) -> SimpleNamespace:
    base = dict(
        best_performance_window="",
        recommended_session_length="",
        optimal_break_interval=25.0,
        peak_productivity_periods=[],
        quality_factors=[],
        improvement_suggestions=[],
    )
    base.update(overrides)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


class _FakeServer:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.prompts: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def prompt(self):
        def decorator(fn):
            self.prompts[fn.__name__] = fn
            return fn

        return decorator


def _make_analytics(**overrides) -> MagicMock:
    """Build a fake SessionAnalytics with the given return values."""
    analytics = MagicMock()
    analytics.initialize = AsyncMock(return_value=None)
    method_map = {
        "get_session_length_distribution": "length_distribution",
        "get_temporal_patterns": "temporal_patterns",
        "get_activity_correlations": "correlations",
        "get_session_streaks": "streaks",
        "get_productivity_insights": "productivity",
    }
    for method, key in method_map.items():
        raise_key = f"{method}_raises"
        if raise_key in overrides:
            setattr(
                analytics,
                method,
                AsyncMock(side_effect=overrides[raise_key]),
            )
        else:
            setattr(
                analytics,
                method,
                AsyncMock(return_value=overrides.get(key)),
            )
    return analytics


# ---------------------------------------------------------------------------
# _generate_length_distribution_insights
# ---------------------------------------------------------------------------


class TestGenerateLengthDistributionInsights:
    def test_no_sessions(self) -> None:
        dist = _make_length_distribution(total_sessions=0)
        insights = _generate_length_distribution_insights(dist)
        assert insights == ["No sessions analyzed"]

    def test_balanced_schedule(self) -> None:
        dist = _make_length_distribution(medium_percentage=60.0)
        insights = _generate_length_distribution_insights(dist)
        assert any(
            "✅" in i and "Balanced schedule" in i and "60.0%" in i
            for i in insights
        )

    def test_fragmented_work(self) -> None:
        # medium_percentage must be ≤50 for fragmented branch.
        dist = _make_length_distribution(
            medium_percentage=30.0, short_percentage=70.0
        )
        insights = _generate_length_distribution_insights(dist)
        assert any(
            "⚡" in i and "Fragmented work" in i for i in insights
        )

    def test_marathon_sessions(self) -> None:
        # medium ≤50, short ≤60, long >40 → marathon branch.
        dist = _make_length_distribution(
            medium_percentage=30.0,
            short_percentage=20.0,
            long_percentage=50.0,
        )
        insights = _generate_length_distribution_insights(dist)
        assert any(
            "🔥" in i and "Marathon sessions" in i for i in insights
        )

    def test_long_average(self) -> None:
        dist = _make_length_distribution(avg_duration_minutes=150.0)
        insights = _generate_length_distribution_insights(dist)
        assert any("⏰" in i and "Long average" in i for i in insights)

    def test_short_average(self) -> None:
        dist = _make_length_distribution(avg_duration_minutes=20.0)
        insights = _generate_length_distribution_insights(dist)
        assert any("⚡" in i and "Short average" in i for i in insights)

    def test_normal_average_no_insight(self) -> None:
        # 60 min is between 30 and 120 → no avg insight.
        dist = _make_length_distribution(avg_duration_minutes=60.0)
        insights = _generate_length_distribution_insights(dist)
        assert not any(
            "Long average" in i or "Short average" in i for i in insights
        )

    def test_variability_high_positive(self) -> None:
        # avg=100, median=50 → diff_pct=100% → variability insight.
        dist = _make_length_distribution(
            avg_duration_minutes=100.0, median_duration_minutes=50.0
        )
        insights = _generate_length_distribution_insights(dist)
        assert any("📊" in i and "Variability" in i for i in insights)

    def test_variability_negative(self) -> None:
        # avg=40, median=80 → diff_pct = -50% → variability insight.
        dist = _make_length_distribution(
            avg_duration_minutes=40.0, median_duration_minutes=80.0
        )
        insights = _generate_length_distribution_insights(dist)
        assert any("📊" in i and "Variability" in i for i in insights)

    def test_no_variability_within_30_pct(self) -> None:
        # avg=65, median=50 → diff_pct=30% → NOT >30 → no insight.
        dist = _make_length_distribution(
            avg_duration_minutes=65.0, median_duration_minutes=50.0
        )
        insights = _generate_length_distribution_insights(dist)
        assert not any("Variability" in i for i in insights)

    def test_zero_median_no_variability(self) -> None:
        # median=0 → guarded → no variability insight.
        dist = _make_length_distribution(
            avg_duration_minutes=60.0, median_duration_minutes=0.0
        )
        insights = _generate_length_distribution_insights(dist)
        assert not any("Variability" in i for i in insights)


# ---------------------------------------------------------------------------
# _generate_temporal_patterns_insights
# ---------------------------------------------------------------------------


class TestGenerateTemporalPatternsInsights:
    def test_increasing_frequency(self) -> None:
        patterns = _make_temporal_patterns(
            session_frequency_trend="increasing"
        )
        insights = _generate_temporal_patterns_insights(patterns)
        assert any(
            "📈" in i and "Increasing session frequency" in i
            for i in insights
        )

    def test_decreasing_frequency(self) -> None:
        patterns = _make_temporal_patterns(
            session_frequency_trend="decreasing"
        )
        insights = _generate_temporal_patterns_insights(patterns)
        assert any(
            "📉" in i and "Decreasing session frequency" in i
            for i in insights
        )

    def test_stable_frequency_no_insight(self) -> None:
        patterns = _make_temporal_patterns(
            session_frequency_trend="stable"
        )
        insights = _generate_temporal_patterns_insights(patterns)
        assert not any(
            "Increasing session" in i or "Decreasing session" in i
            for i in insights
        )

    def test_peak_productivity(self) -> None:
        patterns = _make_temporal_patterns(
            most_productive_time_slot="Tuesday morning"
        )
        insights = _generate_temporal_patterns_insights(patterns)
        assert any(
            "⭐" in i and "Peak productivity" in i
            and "Tuesday morning" in i
            for i in insights
        )

    def test_no_peak_no_insight(self) -> None:
        patterns = _make_temporal_patterns(
            most_productive_time_slot=""
        )
        insights = _generate_temporal_patterns_insights(patterns)
        assert not any("⭐" in i for i in insights)

    def test_high_frequency(self) -> None:
        patterns = _make_temporal_patterns(avg_sessions_per_day=3.0)
        insights = _generate_temporal_patterns_insights(patterns)
        assert any("🔄" in i and "High frequency" in i for i in insights)

    def test_low_frequency(self) -> None:
        patterns = _make_temporal_patterns(avg_sessions_per_day=0.3)
        insights = _generate_temporal_patterns_insights(patterns)
        assert any("📅" in i and "Low frequency" in i for i in insights)

    def test_normal_frequency_no_insight(self) -> None:
        patterns = _make_temporal_patterns(avg_sessions_per_day=1.0)
        insights = _generate_temporal_patterns_insights(patterns)
        assert not any(
            "High frequency" in i or "Low frequency" in i for i in insights
        )

    def test_top_time_of_day(self) -> None:
        patterns = _make_temporal_patterns(
            time_of_day_distribution={
                "morning": 5,
                "afternoon": 2,
                "evening": 1,
            }
        )
        insights = _generate_temporal_patterns_insights(patterns)
        # morning is top with 5/8 = 62.5% (formatted as 62%).
        assert any(
            "🌅" in i and "morning" in i and "62" in i
            for i in insights
        )

    def test_no_time_distribution_no_insight(self) -> None:
        patterns = _make_temporal_patterns(time_of_day_distribution={})
        insights = _generate_temporal_patterns_insights(patterns)
        assert not any("🌅" in i for i in insights)

    def test_zero_total_no_time_insight(self) -> None:
        # All-zero distribution → total=0 → no insight.
        patterns = _make_temporal_patterns(
            time_of_day_distribution={"morning": 0}
        )
        insights = _generate_temporal_patterns_insights(patterns)
        assert not any("🌅" in i for i in insights)


# ---------------------------------------------------------------------------
# _generate_correlation_insights
# ---------------------------------------------------------------------------


class TestGenerateCorrelationInsights:
    def test_positive_duration_quality(self) -> None:
        corr = _make_correlations(duration_quality_correlation=0.5)
        insights = _generate_correlation_insights(corr)
        assert any(
            "✅" in i and "Longer sessions correlate" in i and "0.50" in i
            for i in insights
        )

    def test_negative_duration_quality(self) -> None:
        corr = _make_correlations(duration_quality_correlation=-0.5)
        insights = _generate_correlation_insights(corr)
        assert any(
            "⚡" in i and "Shorter sessions correlate" in i
            for i in insights
        )

    def test_weak_duration_quality_no_insight(self) -> None:
        corr = _make_correlations(duration_quality_correlation=0.1)
        insights = _generate_correlation_insights(corr)
        assert not any(
            "correlate" in i.lower() for i in insights
        )

    def test_positive_quality_commits(self) -> None:
        corr = _make_correlations(quality_commits_correlation=0.6)
        insights = _generate_correlation_insights(corr)
        assert any(
            "✅" in i and "More commits correlate" in i
            for i in insights
        )

    def test_negative_quality_commits(self) -> None:
        corr = _make_correlations(quality_commits_correlation=-0.4)
        insights = _generate_correlation_insights(corr)
        assert any(
            "🎯" in i and "Fewer commits correlate" in i
            for i in insights
        )

    def test_weak_quality_commits_no_insight(self) -> None:
        corr = _make_correlations(quality_commits_correlation=0.1)
        insights = _generate_correlation_insights(corr)
        # Only one weak correlation → no insight for either.
        assert not any(
            "commits correlate" in i.lower() for i in insights
        )

    def test_high_quality_rate(self) -> None:
        corr = _make_correlations(
            high_quality_sessions=8, low_quality_sessions=2
        )
        insights = _generate_correlation_insights(corr)
        # 8/10 = 80% → "🌟 High quality rate".
        assert any("🌟" in i and "High quality rate" in i for i in insights)

    def test_low_quality_rate(self) -> None:
        corr = _make_correlations(
            high_quality_sessions=2, low_quality_sessions=8
        )
        insights = _generate_correlation_insights(corr)
        # 2/10 = 20% → "⚠️ Quality challenges".
        assert any(
            "⚠️" in i and "Quality challenges" in i for i in insights
        )

    def test_medium_quality_rate_no_insight(self) -> None:
        # 5/10 = 50% → between 40 and 70 → no insight.
        corr = _make_correlations(
            high_quality_sessions=5, low_quality_sessions=5
        )
        insights = _generate_correlation_insights(corr)
        assert not any(
            "High quality rate" in i or "Quality challenges" in i
            for i in insights
        )

    def test_zero_quality_no_insight(self) -> None:
        # No high or low → total=0 → no insight.
        corr = _make_correlations(
            high_quality_sessions=0, low_quality_sessions=0
        )
        insights = _generate_correlation_insights(corr)
        assert not any(
            "High quality rate" in i or "Quality challenges" in i
            for i in insights
        )

    def test_long_high_quality(self) -> None:
        corr = _make_correlations(long_high_quality_sessions=3)
        insights = _generate_correlation_insights(corr)
        assert any(
            "🏆" in i and "3 marathon sessions" in i for i in insights
        )

    def test_no_long_high_quality(self) -> None:
        corr = _make_correlations(long_high_quality_sessions=0)
        insights = _generate_correlation_insights(corr)
        assert not any("🏆" in i for i in insights)


# ---------------------------------------------------------------------------
# _generate_streak_insights
# ---------------------------------------------------------------------------


class TestGenerateStreakInsights:
    def test_no_session_data(self) -> None:
        streaks = _make_streaks(total_active_days=0)
        insights = _generate_streak_insights(streaks)
        assert insights == ["No session data available"]

    def test_strong_momentum(self) -> None:
        streaks = _make_streaks(current_streak_days=10)
        insights = _generate_streak_insights(streaks)
        assert any(
            "🔥" in i and "Strong momentum" in i and "10" in i
            for i in insights
        )

    def test_building_momentum(self) -> None:
        streaks = _make_streaks(current_streak_days=5)
        insights = _generate_streak_insights(streaks)
        assert any(
            "📈" in i and "Building momentum" in i and "5" in i
            for i in insights
        )

    def test_no_current_streak_insight(self) -> None:
        streaks = _make_streaks(current_streak_days=2)
        insights = _generate_streak_insights(streaks)
        assert not any(
            "Strong momentum" in i or "Building momentum" in i
            for i in insights
        )

    def test_excellent_consistency(self) -> None:
        streaks = _make_streaks(longest_streak_days=20)
        insights = _generate_streak_insights(streaks)
        assert any(
            "💪" in i and "Excellent consistency" in i for i in insights
        )

    def test_good_consistency(self) -> None:
        streaks = _make_streaks(longest_streak_days=10)
        insights = _generate_streak_insights(streaks)
        assert any(
            "✅" in i and "Good consistency" in i for i in insights
        )

    def test_no_longest_streak_insight(self) -> None:
        streaks = _make_streaks(longest_streak_days=5)
        insights = _generate_streak_insights(streaks)
        assert not any(
            "Excellent consistency" in i or "Good consistency" in i
            for i in insights
        )

    def test_consistent_daily(self) -> None:
        streaks = _make_streaks(consistent_daily_sessions=True)
        insights = _generate_streak_insights(streaks)
        assert any(
            "🎯" in i and "Consistent daily work" in i for i in insights
        )

    def test_no_consistent_daily(self) -> None:
        streaks = _make_streaks(consistent_daily_sessions=False)
        insights = _generate_streak_insights(streaks)
        assert not any("🎯" in i for i in insights)

    def test_large_gaps(self) -> None:
        streaks = _make_streaks(avg_gap_between_sessions_hours=72.0)
        insights = _generate_streak_insights(streaks)
        assert any("⚠️" in i and "Large gaps" in i for i in insights)

    def test_frequent_engagement(self) -> None:
        streaks = _make_streaks(avg_gap_between_sessions_hours=12.0)
        insights = _generate_streak_insights(streaks)
        assert any(
            "✅" in i and "Frequent engagement" in i for i in insights
        )

    def test_normal_gap_no_insight(self) -> None:
        streaks = _make_streaks(avg_gap_between_sessions_hours=36.0)
        insights = _generate_streak_insights(streaks)
        assert not any(
            "Large gaps" in i or "Frequent engagement" in i for i in insights
        )

    def test_most_consistent_week(self) -> None:
        streaks = _make_streaks(most_consistent_week="2026-W26")
        insights = _generate_streak_insights(streaks)
        assert any(
            "📅" in i and "Best week" in i and "2026-W26" in i
            for i in insights
        )

    def test_no_most_consistent_week(self) -> None:
        streaks = _make_streaks(most_consistent_week="")
        insights = _generate_streak_insights(streaks)
        assert not any("📅" in i for i in insights)


# ---------------------------------------------------------------------------
# _generate_productivity_insights
# ---------------------------------------------------------------------------


class TestGenerateProductivityInsights:
    def test_optimal_time(self) -> None:
        p = _make_productivity(best_performance_window="morning")
        insights = _generate_productivity_insights(p)
        assert any(
            "⭐" in i and "Optimal time" in i and "morning" in i
            for i in insights
        )

    def test_no_optimal_time(self) -> None:
        p = _make_productivity(best_performance_window="")
        insights = _generate_productivity_insights(p)
        assert not any("⭐" in i for i in insights)

    def test_recommended_length(self) -> None:
        p = _make_productivity(recommended_session_length="60-90min")
        insights = _generate_productivity_insights(p)
        assert any(
            "📐" in i and "Recommended length" in i and "60-90min" in i
            for i in insights
        )

    def test_no_recommended_length(self) -> None:
        p = _make_productivity(recommended_session_length="")
        insights = _generate_productivity_insights(p)
        assert not any("📐" in i for i in insights)

    def test_break_interval_always_emitted(self) -> None:
        p = _make_productivity(optimal_break_interval=25.0)
        insights = _generate_productivity_insights(p)
        assert any(
            "⏱️" in i and "Break interval" in i and "25" in i
            for i in insights
        )

    def test_peak_periods_joined_top_three(self) -> None:
        p = _make_productivity(
            peak_productivity_periods=["morning", "afternoon", "evening", "night"]
        )
        insights = _generate_productivity_insights(p)
        # Top 3 joined.
        assert any(
            "🎯" in i
            and "morning" in i
            and "afternoon" in i
            and "evening" in i
            and "night" not in i  # 4th item excluded
            for i in insights
        )

    def test_no_peak_periods(self) -> None:
        p = _make_productivity(peak_productivity_periods=[])
        insights = _generate_productivity_insights(p)
        assert not any("🎯" in i for i in insights)

    def test_quality_factors_emitted(self) -> None:
        p = _make_productivity(quality_factors=["good tests", "clean code"])
        insights = _generate_productivity_insights(p)
        assert any(
            "💡" in i and "good tests" in i for i in insights
        )
        assert any("💡" in i and "clean code" in i for i in insights)

    def test_no_quality_factors(self) -> None:
        p = _make_productivity(quality_factors=[])
        insights = _generate_productivity_insights(p)
        assert not any("💡" in i for i in insights)

    def test_improvement_suggestions_emitted(self) -> None:
        p = _make_productivity(
            improvement_suggestions=["add tests", "refactor modules"]
        )
        insights = _generate_productivity_insights(p)
        assert any(
            "✨" in i and "add tests" in i for i in insights
        )
        assert any("✨" in i and "refactor modules" in i for i in insights)

    def test_no_improvement_suggestions(self) -> None:
        p = _make_productivity(improvement_suggestions=[])
        insights = _generate_productivity_insights(p)
        assert not any("✨" in i for i in insights)


# ---------------------------------------------------------------------------
# register_session_analytics_tools
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registers_five_tools_and_one_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: _make_analytics(),
        )
        server = _FakeServer()
        register_session_analytics_tools(server)
        assert "get_session_length_distribution" in server.tools
        assert "get_temporal_patterns" in server.tools
        assert "get_activity_correlations" in server.tools
        assert "get_session_streaks" in server.tools
        assert "get_productivity_insights" in server.tools
        assert "session_analytics_help" in server.prompts


# ---------------------------------------------------------------------------
# get_session_length_distribution (the tool)
# ---------------------------------------------------------------------------


class TestGetSessionLengthDistribution:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dist = _make_length_distribution(medium_percentage=60.0)
        analytics = _make_analytics(length_distribution=dist)
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_session_length_distribution"]()
        assert result["success"] is True
        assert result["medium_percentage"] == 60.0
        assert "insights" in result
        analytics.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(length_distribution=_make_length_distribution())
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        await server.tools["get_session_length_distribution"](
            project_path="/my/proj", days_back=14
        )
        analytics.get_session_length_distribution.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(
            get_session_length_distribution_raises=RuntimeError("db down")
        )
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_session_length_distribution"]()
        assert result["success"] is False
        assert "db down" in result["error"]
        assert (
            "Failed to retrieve session length distribution"
            in result["message"]
        )


# ---------------------------------------------------------------------------
# get_temporal_patterns (the tool)
# ---------------------------------------------------------------------------


class TestGetTemporalPatterns:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patterns = _make_temporal_patterns(
            session_frequency_trend="increasing"
        )
        analytics = _make_analytics(temporal_patterns=patterns)
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_temporal_patterns"]()
        assert result["success"] is True
        assert result["session_frequency_trend"] == "increasing"
        assert "insights" in result

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(
            temporal_patterns=_make_temporal_patterns()
        )
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        await server.tools["get_temporal_patterns"](
            project_path="/my/proj", days_back=14
        )
        analytics.get_temporal_patterns.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(
            get_temporal_patterns_raises=RuntimeError("patterns down")
        )
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_temporal_patterns"]()
        assert result["success"] is False
        assert "patterns down" in result["error"]


# ---------------------------------------------------------------------------
# get_activity_correlations (the tool)
# ---------------------------------------------------------------------------


class TestGetActivityCorrelations:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        corr = _make_correlations(duration_quality_correlation=0.5)
        analytics = _make_analytics(correlations=corr)
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_activity_correlations"]()
        assert result["success"] is True
        assert result["duration_quality_correlation"] == 0.5
        assert "insights" in result

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(correlations=_make_correlations())
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        await server.tools["get_activity_correlations"](
            project_path="/my/proj", days_back=14
        )
        analytics.get_activity_correlations.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(
            get_activity_correlations_raises=RuntimeError("corr fail")
        )
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_activity_correlations"]()
        assert result["success"] is False
        assert "corr fail" in result["error"]


# ---------------------------------------------------------------------------
# get_session_streaks (the tool)
# ---------------------------------------------------------------------------


class TestGetSessionStreaks:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        streaks = _make_streaks(current_streak_days=10)
        analytics = _make_analytics(streaks=streaks)
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_session_streaks"]()
        assert result["success"] is True
        assert result["current_streak_days"] == 10
        assert "insights" in result

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(streaks=_make_streaks())
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        await server.tools["get_session_streaks"](
            project_path="/my/proj", days_back=14
        )
        analytics.get_session_streaks.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(
            get_session_streaks_raises=RuntimeError("streak fail")
        )
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_session_streaks"]()
        assert result["success"] is False
        assert "streak fail" in result["error"]


# ---------------------------------------------------------------------------
# get_productivity_insights (the tool)
# ---------------------------------------------------------------------------


class TestGetProductivityInsights:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prod = _make_productivity(
            best_performance_window="morning",
            recommended_session_length="60-90min",
        )
        analytics = _make_analytics(productivity=prod)
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_productivity_insights"]()
        assert result["success"] is True
        assert result["best_performance_window"] == "morning"
        assert "insights" in result

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(productivity=_make_productivity())
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        await server.tools["get_productivity_insights"](
            project_path="/my/proj", days_back=14
        )
        analytics.get_productivity_insights.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analytics = _make_analytics(
            get_productivity_insights_raises=RuntimeError("prod fail")
        )
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: analytics,
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        result = await server.tools["get_productivity_insights"]()
        assert result["success"] is False
        assert "prod fail" in result["error"]


# ---------------------------------------------------------------------------
# session_analytics_help (the prompt)
# ---------------------------------------------------------------------------


class TestSessionAnalyticsHelp:
    def test_returns_static_help_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            session_analytics_tools,
            "get_session_analytics",
            lambda: _make_analytics(),
        )

        server = _FakeServer()
        register_session_analytics_tools(server)
        text = server.prompts["session_analytics_help"]()
        assert "Session Analytics" in text
        assert "get_session_length_distribution" in text
        assert "get_temporal_patterns" in text
        assert "get_activity_correlations" in text
        assert "get_session_streaks" in text
        assert "get_productivity_insights" in text
        assert "Session Length Benchmarks" in text
