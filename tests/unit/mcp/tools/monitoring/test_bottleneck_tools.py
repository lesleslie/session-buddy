"""Tests for session_buddy.mcp.tools.monitoring.bottleneck_tools.

Covers the bottleneck detection MCP tool registration:
- ``_generate_quality_bottleneck_insights``: sudden_quality_drops
  branches (0 → ✅ none, ≤2 → 📊 occasional, >2 → 🚨 frequent);
  consecutive_low_quality_sessions ≥3 → ⚠️ sustained; recovery time
  branches (>24h → 🐌 slow, >0 → ⚡ quick, =0 → none); most_common_
  quality_drop_cause present → 🔍; low_quality_periods non-empty → 📅.
- ``_generate_velocity_bottleneck_insights``: low_velocity_sessions
  branches (0 → ✅ none, ≤5 → 📊 some, >5 → ⚠️ many); zero_commit_
  sessions branches (>5 with pct calc, >0 → 📊, =0 → none);
  long_sessions_without_commits >2 → ⚠️; velocity_stagnation_days
  (>5 → 📉, >0 → 📊, =0 → none).
- ``_generate_pattern_bottleneck_insights``: marathon_sessions
  branches (0 → ✅, ≤2 → 📊, >2 → 🔥); fragmented_work_sessions
  (>5 → ⚡, >0 → 📊, =0 → none); infrequent_checkpoint_sessions >3
  → ⚠️; excessive_session_gaps (>48 → 📅, >24 → 📊, else none);
  inconsistent_schedule_score (>70 → 🔄, >50 → 📊, else ✅).
- ``_synthesize_bottleneck_insights``: critical_bottlenecks count
  (0 → ✅, ≤2 → 📊, >2 → 🚨); improvement_recommendations non-empty
  → two insights (count + 💡 focus); workflow_optimization_
  opportunities non-empty → ⚙️.
- ``register_bottleneck_tools``: registers 4 tools + 1 prompt.
- 4 tools (``detect_quality_bottlenecks``, ``detect_velocity_
  bottlenecks``, ``detect_session_pattern_bottlenecks``, ``get_
  bottleneck_insights``): happy path with insights, project_path +
  days_back propagated to detector, exception path.
- ``bottleneck_help`` (the prompt): returns the static help text.

The detector is patched on the module's symbol because
``get_bottleneck_detector`` is imported at module level into
``bottleneck_tools``'s namespace.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.monitoring import bottleneck_tools
from session_buddy.mcp.tools.monitoring.bottleneck_tools import (
    _generate_pattern_bottleneck_insights,
    _generate_quality_bottleneck_insights,
    _generate_velocity_bottleneck_insights,
    _synthesize_bottleneck_insights,
    register_bottleneck_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quality_bottlenecks(**overrides) -> SimpleNamespace:
    base = dict(
        sudden_quality_drops=0,
        consecutive_low_quality_sessions=0,
        avg_recovery_time_hours=0.0,
        most_common_quality_drop_cause=None,
        low_quality_periods=[],
    )
    base.update(overrides)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


def _make_velocity_bottlenecks(**overrides) -> SimpleNamespace:
    base = dict(
        low_velocity_sessions=0,
        zero_commit_sessions=0,
        long_sessions_without_commits=0,
        velocity_stagnation_days=0,
    )
    base.update(overrides)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


def _make_pattern_bottlenecks(**overrides) -> SimpleNamespace:
    base = dict(
        marathon_sessions=0,
        fragmented_work_sessions=0,
        infrequent_checkpoint_sessions=0,
        excessive_session_gaps=0.0,
        inconsistent_schedule_score=0.0,
    )
    base.update(overrides)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


def _make_insights(
    *,
    critical_bottlenecks: list[str] | None = None,
    improvement_recommendations: list[str] | None = None,
    workflow_optimization_opportunities: list[str] | None = None,
    **extras,
) -> SimpleNamespace:
    base: dict = {
        "critical_bottlenecks": critical_bottlenecks or [],
        "improvement_recommendations": improvement_recommendations or [],
        "workflow_optimization_opportunities": (
            workflow_optimization_opportunities or []
        ),
    }
    base.update(extras)
    metrics = SimpleNamespace(**base)
    metrics.to_dict = lambda: dict(base)
    return metrics


class _FakeServer:
    """Capture ``server.tool()`` and ``server.prompt()`` decorators."""

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


def _make_detector(**overrides) -> MagicMock:
    """Build a fake BottleneckDetector.

    Each ``detect_*`` method takes ``project_path``, ``days_back`` and
    returns the provided metric object. Pass ``raises=<name>:<Exc>``
    to make a method raise.
    """
    detector = MagicMock()
    detector.initialize = AsyncMock(return_value=None)
    for method in (
        "detect_quality_bottlenecks",
        "detect_velocity_bottlenecks",
        "detect_session_pattern_bottlenecks",
    ):
        if f"{method}_raises" in overrides:
            setattr(
                detector,
                method,
                AsyncMock(side_effect=overrides[f"{method}_raises"]),
            )
        else:
            setattr(detector, method, AsyncMock(return_value=overrides.get(method)))
    if "get_bottleneck_insights_raises" in overrides:
        detector.get_bottleneck_insights = AsyncMock(
            side_effect=overrides["get_bottleneck_insights_raises"]
        )
    else:
        detector.get_bottleneck_insights = AsyncMock(
            return_value=overrides.get("get_bottleneck_insights")
        )
    return detector


# ---------------------------------------------------------------------------
# _generate_quality_bottleneck_insights
# ---------------------------------------------------------------------------


class TestGenerateQualityBottleneckInsights:
    def test_no_sudden_drops(self) -> None:
        bn = _make_quality_bottlenecks(sudden_quality_drops=0)
        insights = _generate_quality_bottleneck_insights(bn)
        assert any(
            "✅" in i and "No sudden quality drops" in i for i in insights
        )

    def test_occasional_drops(self) -> None:
        for n in (1, 2):
            bn = _make_quality_bottlenecks(sudden_quality_drops=n)
            insights = _generate_quality_bottleneck_insights(bn)
            assert any(
                "📊" in i and "Occasional quality drops" in i
                and f"{n}" in i
                for i in insights
            )

    def test_frequent_drops(self) -> None:
        bn = _make_quality_bottlenecks(sudden_quality_drops=5)
        insights = _generate_quality_bottleneck_insights(bn)
        assert any(
            "🚨" in i and "Frequent quality drops" in i and "5" in i
            for i in insights
        )

    def test_sustained_low_quality(self) -> None:
        bn = _make_quality_bottlenecks(consecutive_low_quality_sessions=3)
        insights = _generate_quality_bottleneck_insights(bn)
        assert any(
            "⚠️" in i and "Sustained low quality" in i for i in insights
        )

    def test_low_consecutive_count_no_insight(self) -> None:
        bn = _make_quality_bottlenecks(consecutive_low_quality_sessions=2)
        insights = _generate_quality_bottleneck_insights(bn)
        assert not any("Sustained low quality" in i for i in insights)

    def test_slow_recovery(self) -> None:
        bn = _make_quality_bottlenecks(avg_recovery_time_hours=30.0)
        insights = _generate_quality_bottleneck_insights(bn)
        assert any(
            "🐌" in i and "Slow recovery" in i and "30.0" in i
            for i in insights
        )

    def test_quick_recovery(self) -> None:
        bn = _make_quality_bottlenecks(avg_recovery_time_hours=2.0)
        insights = _generate_quality_bottleneck_insights(bn)
        assert any(
            "⚡" in i and "Quick recovery" in i for i in insights
        )

    def test_zero_recovery_no_insight(self) -> None:
        bn = _make_quality_bottlenecks(avg_recovery_time_hours=0.0)
        insights = _generate_quality_bottleneck_insights(bn)
        assert not any(
            "Slow recovery" in i or "Quick recovery" in i for i in insights
        )

    def test_common_cause_emitted(self) -> None:
        bn = _make_quality_bottlenecks(
            most_common_quality_drop_cause="pytest fixture"
        )
        insights = _generate_quality_bottleneck_insights(bn)
        assert any(
            "🔍" in i and "pytest fixture" in i for i in insights
        )

    def test_no_cause_no_insight(self) -> None:
        bn = _make_quality_bottlenecks(most_common_quality_drop_cause=None)
        insights = _generate_quality_bottleneck_insights(bn)
        assert not any("🔍" in i for i in insights)

    def test_low_quality_periods_counted(self) -> None:
        bn = _make_quality_bottlenecks(
            low_quality_periods=["2026-06-15", "2026-06-20", "2026-06-25"]
        )
        insights = _generate_quality_bottleneck_insights(bn)
        assert any(
            "📅" in i and "3" in i and "low-quality period" in i
            for i in insights
        )

    def test_no_periods_no_insight(self) -> None:
        bn = _make_quality_bottlenecks(low_quality_periods=[])
        insights = _generate_quality_bottleneck_insights(bn)
        assert not any("📅" in i for i in insights)


# ---------------------------------------------------------------------------
# _generate_velocity_bottleneck_insights
# ---------------------------------------------------------------------------


class TestGenerateVelocityBottleneckInsights:
    def test_no_low_velocity(self) -> None:
        bn = _make_velocity_bottlenecks(low_velocity_sessions=0)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert any(
            "✅" in i and "No low-velocity" in i for i in insights
        )

    def test_some_low_velocity(self) -> None:
        bn = _make_velocity_bottlenecks(low_velocity_sessions=3)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert any(
            "📊" in i and "Some low-velocity" in i and "3" in i
            for i in insights
        )

    def test_many_low_velocity(self) -> None:
        bn = _make_velocity_bottlenecks(low_velocity_sessions=10)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert any(
            "⚠️" in i and "Many slow sessions" in i and "10" in i
            for i in insights
        )

    def test_high_zero_commit_with_pct(self) -> None:
        bn = _make_velocity_bottlenecks(
            low_velocity_sessions=10, zero_commit_sessions=8
        )
        insights = _generate_velocity_bottleneck_insights(bn)
        # 8/10 = 80% of slow sessions.
        assert any(
            "🚨" in i
            and "High zero-commit" in i
            and "80" in i
            for i in insights
        )

    def test_low_zero_commit_counted(self) -> None:
        bn = _make_velocity_bottlenecks(
            low_velocity_sessions=10, zero_commit_sessions=2
        )
        insights = _generate_velocity_bottleneck_insights(bn)
        assert any(
            "📊" in i and "Zero-commit sessions" in i and "2" in i
            for i in insights
        )

    def test_zero_zero_commit_no_insight(self) -> None:
        bn = _make_velocity_bottlenecks(zero_commit_sessions=0)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert not any("Zero-commit" in i for i in insights)

    def test_zero_pct_calculation_when_no_low_velocity(self) -> None:
        # When low_velocity_sessions == 0, zero_pct is 0; zero_commit
        # insight still fires (>0).
        bn = _make_velocity_bottlenecks(
            low_velocity_sessions=0, zero_commit_sessions=3
        )
        insights = _generate_velocity_bottleneck_insights(bn)
        assert any(
            "📊" in i and "Zero-commit" in i for i in insights
        )

    def test_unproductive_marathons(self) -> None:
        bn = _make_velocity_bottlenecks(long_sessions_without_commits=5)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert any(
            "⚠️" in i and "Unproductive marathons" in i and "5" in i
            for i in insights
        )

    def test_few_marathons_no_insight(self) -> None:
        bn = _make_velocity_bottlenecks(long_sessions_without_commits=2)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert not any("Unproductive marathons" in i for i in insights)

    def test_declining_trend(self) -> None:
        bn = _make_velocity_bottlenecks(velocity_stagnation_days=7)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert any(
            "📉" in i and "Declining trend" in i and "7" in i
            for i in insights
        )

    def test_some_stagnation(self) -> None:
        bn = _make_velocity_bottlenecks(velocity_stagnation_days=3)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert any(
            "📊" in i and "Some stagnation" in i and "3" in i
            for i in insights
        )

    def test_no_stagnation_no_insight(self) -> None:
        bn = _make_velocity_bottlenecks(velocity_stagnation_days=0)
        insights = _generate_velocity_bottleneck_insights(bn)
        assert not any(
            "Declining trend" in i or "Some stagnation" in i
            for i in insights
        )


# ---------------------------------------------------------------------------
# _generate_pattern_bottleneck_insights
# ---------------------------------------------------------------------------


class TestGeneratePatternBottleneckInsights:
    def test_no_marathons(self) -> None:
        bn = _make_pattern_bottlenecks(marathon_sessions=0)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "✅" in i and "No marathon" in i for i in insights
        )

    def test_occasional_marathons(self) -> None:
        for n in (1, 2):
            bn = _make_pattern_bottlenecks(marathon_sessions=n)
            insights = _generate_pattern_bottleneck_insights(bn)
            assert any(
                "📊" in i and "Occasional marathons" in i and f"{n}" in i
                for i in insights
            )

    def test_frequent_marathons(self) -> None:
        bn = _make_pattern_bottlenecks(marathon_sessions=5)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "🔥" in i and "Frequent marathons" in i and "5" in i
            for i in insights
        )

    def test_highly_fragmented(self) -> None:
        bn = _make_pattern_bottlenecks(fragmented_work_sessions=10)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "⚡" in i and "Highly fragmented" in i and "10" in i
            for i in insights
        )

    def test_some_fragmentation(self) -> None:
        bn = _make_pattern_bottlenecks(fragmented_work_sessions=3)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "📊" in i and "Some fragmentation" in i and "3" in i
            for i in insights
        )

    def test_no_fragmentation_no_insight(self) -> None:
        bn = _make_pattern_bottlenecks(fragmented_work_sessions=0)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert not any(
            "fragmented" in i.lower() for i in insights
        )

    def test_infrequent_checkpoints(self) -> None:
        bn = _make_pattern_bottlenecks(infrequent_checkpoint_sessions=5)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "⚠️" in i
            and "Infrequent checkpoints" in i
            and "5" in i
            for i in insights
        )

    def test_few_checkpoints_no_insight(self) -> None:
        bn = _make_pattern_bottlenecks(infrequent_checkpoint_sessions=3)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert not any("Infrequent checkpoints" in i for i in insights)

    def test_large_gaps(self) -> None:
        bn = _make_pattern_bottlenecks(excessive_session_gaps=72.0)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "📅" in i and "Large gaps" in i and "72.0" in i
            for i in insights
        )

    def test_moderate_gaps(self) -> None:
        bn = _make_pattern_bottlenecks(excessive_session_gaps=36.0)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "📊" in i and "Moderate gaps" in i for i in insights
        )

    def test_normal_gaps_no_insight(self) -> None:
        bn = _make_pattern_bottlenecks(excessive_session_gaps=12.0)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert not any("gaps" in i.lower() for i in insights)

    def test_highly_inconsistent_schedule(self) -> None:
        bn = _make_pattern_bottlenecks(inconsistent_schedule_score=80.0)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "🔄" in i and "Highly inconsistent" in i for i in insights
        )

    def test_somewhat_inconsistent_schedule(self) -> None:
        bn = _make_pattern_bottlenecks(inconsistent_schedule_score=60.0)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "📊" in i and "Somewhat inconsistent" in i for i in insights
        )

    def test_consistent_schedule(self) -> None:
        bn = _make_pattern_bottlenecks(inconsistent_schedule_score=30.0)
        insights = _generate_pattern_bottleneck_insights(bn)
        assert any(
            "✅" in i and "Consistent schedule" in i for i in insights
        )


# ---------------------------------------------------------------------------
# _synthesize_bottleneck_insights
# ---------------------------------------------------------------------------


class TestSynthesizeBottleneckInsights:
    def test_no_critical(self) -> None:
        insights = _make_insights(critical_bottlenecks=[])
        synth = _synthesize_bottleneck_insights(insights)
        assert any(
            "✅" in i and "No critical" in i for i in synth
        )

    def test_few_critical(self) -> None:
        insights = _make_insights(
            critical_bottlenecks=["a", "b"]
        )
        synth = _synthesize_bottleneck_insights(insights)
        assert any(
            "📊" in i and "2 critical" in i for i in synth
        )

    def test_many_critical(self) -> None:
        insights = _make_insights(
            critical_bottlenecks=["a", "b", "c", "d"]
        )
        synth = _synthesize_bottleneck_insights(insights)
        assert any(
            "🚨" in i and "4 critical" in i for i in synth
        )

    def test_improvement_recommendations_counted(self) -> None:
        insights = _make_insights(
            improvement_recommendations=["rec1", "rec2", "rec3"]
        )
        synth = _synthesize_bottleneck_insights(insights)
        # Two insights: count + "💡 Focus on..."
        assert any(
            "→" in i and "3 improvement" in i for i in synth
        )
        assert any(
            "💡" in i and "Focus on highest-impact" in i for i in synth
        )

    def test_no_improvement_recommendations(self) -> None:
        insights = _make_insights(improvement_recommendations=[])
        synth = _synthesize_bottleneck_insights(insights)
        # No → or 💡 insight.
        assert not any(
            "improvement recommendations" in i.lower() for i in synth
        )
        assert not any("💡" in i for i in synth)

    def test_workflow_optimization_counted(self) -> None:
        insights = _make_insights(
            workflow_optimization_opportunities=["opp1", "opp2"]
        )
        synth = _synthesize_bottleneck_insights(insights)
        assert any(
            "⚙️" in i and "2 optimization" in i for i in synth
        )

    def test_no_workflow_optimization(self) -> None:
        insights = _make_insights(
            workflow_optimization_opportunities=[]
        )
        synth = _synthesize_bottleneck_insights(insights)
        assert not any("⚙️" in i for i in synth)


# ---------------------------------------------------------------------------
# register_bottleneck_tools
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registers_four_tools_and_one_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: _make_detector(),
        )
        server = _FakeServer()
        register_bottleneck_tools(server)
        assert "detect_quality_bottlenecks" in server.tools
        assert "detect_velocity_bottlenecks" in server.tools
        assert "detect_session_pattern_bottlenecks" in server.tools
        assert "get_bottleneck_insights" in server.tools
        assert "bottleneck_help" in server.prompts


# ---------------------------------------------------------------------------
# detect_quality_bottlenecks (the tool)
# ---------------------------------------------------------------------------


class TestDetectQualityBottlenecks:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bn = _make_quality_bottlenecks(sudden_quality_drops=3)
        detector = _make_detector(detect_quality_bottlenecks=bn)
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        result = await server.tools["detect_quality_bottlenecks"]()
        assert result["success"] is True
        assert result["sudden_quality_drops"] == 3
        assert "insights" in result
        detector.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = _make_detector(detect_quality_bottlenecks=_make_quality_bottlenecks())
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        await server.tools["detect_quality_bottlenecks"](
            project_path="/my/proj", days_back=14
        )
        detector.detect_quality_bottlenecks.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = _make_detector(
            detect_quality_bottlenecks_raises=RuntimeError("detector down")
        )
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        result = await server.tools["detect_quality_bottlenecks"]()
        assert result["success"] is False
        assert "detector down" in result["error"]
        assert (
            "Failed to detect quality bottlenecks" in result["message"]
        )


# ---------------------------------------------------------------------------
# detect_velocity_bottlenecks (the tool)
# ---------------------------------------------------------------------------


class TestDetectVelocityBottlenecks:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bn = _make_velocity_bottlenecks(low_velocity_sessions=10)
        detector = _make_detector(detect_velocity_bottlenecks=bn)
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        result = await server.tools["detect_velocity_bottlenecks"]()
        assert result["success"] is True
        assert result["low_velocity_sessions"] == 10
        assert "insights" in result

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = _make_detector(
            detect_velocity_bottlenecks=_make_velocity_bottlenecks()
        )
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        await server.tools["detect_velocity_bottlenecks"](
            project_path="/my/proj", days_back=14
        )
        detector.detect_velocity_bottlenecks.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = _make_detector(
            detect_velocity_bottlenecks_raises=RuntimeError("query failed")
        )
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        result = await server.tools["detect_velocity_bottlenecks"]()
        assert result["success"] is False
        assert "query failed" in result["error"]


# ---------------------------------------------------------------------------
# detect_session_pattern_bottlenecks (the tool)
# ---------------------------------------------------------------------------


class TestDetectSessionPatternBottlenecks:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bn = _make_pattern_bottlenecks(marathon_sessions=5)
        detector = _make_detector(detect_session_pattern_bottlenecks=bn)
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        result = await server.tools["detect_session_pattern_bottlenecks"]()
        assert result["success"] is True
        assert result["marathon_sessions"] == 5
        assert "insights" in result

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = _make_detector(
            detect_session_pattern_bottlenecks=_make_pattern_bottlenecks()
        )
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        await server.tools["detect_session_pattern_bottlenecks"](
            project_path="/my/proj", days_back=14
        )
        detector.detect_session_pattern_bottlenecks.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = _make_detector(
            detect_session_pattern_bottlenecks_raises=RuntimeError("oops")
        )
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        result = await server.tools["detect_session_pattern_bottlenecks"]()
        assert result["success"] is False
        assert "oops" in result["error"]


# ---------------------------------------------------------------------------
# get_bottleneck_insights (the tool)
# ---------------------------------------------------------------------------


class TestGetBottleneckInsights:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        synth = _make_insights(critical_bottlenecks=["a", "b"])
        detector = _make_detector(get_bottleneck_insights=synth)
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        result = await server.tools["get_bottleneck_insights"]()
        assert result["success"] is True
        assert result["critical_bottlenecks"] == ["a", "b"]
        # Synthesized insights populated.
        assert "insights" in result
        assert isinstance(result["insights"], list)

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = _make_detector(get_bottleneck_insights=_make_insights())
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        await server.tools["get_bottleneck_insights"](
            project_path="/my/proj", days_back=14
        )
        detector.get_bottleneck_insights.assert_awaited_once_with(
            project_path="/my/proj", days_back=14
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = _make_detector(
            get_bottleneck_insights_raises=RuntimeError("synth failed")
        )
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: detector,
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        result = await server.tools["get_bottleneck_insights"]()
        assert result["success"] is False
        assert "synth failed" in result["error"]


# ---------------------------------------------------------------------------
# bottleneck_help (the prompt)
# ---------------------------------------------------------------------------


class TestBottleneckHelp:
    def test_returns_static_help_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            bottleneck_tools,
            "get_bottleneck_detector",
            lambda: _make_detector(),
        )

        server = _FakeServer()
        register_bottleneck_tools(server)
        text = server.prompts["bottleneck_help"]()
        assert "Bottleneck Detection" in text
        assert "detect_quality_bottlenecks" in text
        assert "detect_velocity_bottlenecks" in text
        assert "detect_session_pattern_bottlenecks" in text
        assert "get_bottleneck_insights" in text
        assert "Priority Levels" in text
