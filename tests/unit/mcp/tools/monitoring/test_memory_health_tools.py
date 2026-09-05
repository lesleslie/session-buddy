"""Tests for session_buddy.mcp.tools.monitoring.memory_health_tools.

Covers the memory health monitoring MCP tool registration:
- ``_generate_reflection_health_insights``: branches on stale_pct
  (>20 → high, >10 → growing, else healthy), storage_mb (>100 → large,
  >50 → moderate, else efficient), avg_age (>60 → aging, <14 → fresh),
  tags_distribution (top tag insight, empty → no insight); total=0
  suppresses staleness branch.
- ``_generate_error_hotspot_insights``: branches on recent_error_rate
  (>2.0 → high, >1.0 → elevated, >0.5 → moderate, else low),
  unresolved_errors (>10 → many, >5 → some), avg_resolution_time
  (<5 → fast, >15 → slow, None → no insight), most_common_error_types
  (count>=5 → recurring, count>=3 → pattern, empty → no insight).
- ``register_memory_health_tools``: registers 3 tools (``get_reflection_health``,
  ``get_error_hotspots``, ``get_cleanup_recommendations``) and 1 prompt
  (``memory_health_help``).
- ``get_reflection_health`` (the tool):
    - happy path: ``metrics.to_dict()`` + ``success=True`` + insights
    - stale_threshold_days propagated to the analyzer
    - exception path: ``success=False`` + ``error`` + ``message``
- ``get_error_hotspots`` (the tool):
    - happy path
    - exception path
- ``get_cleanup_recommendations`` (the tool):
    - happy path: groups by priority (high/medium/low) and category,
      counts total
    - empty list → empty groups
    - exception path
- ``memory_health_help`` (the prompt): returns the static help text.

The analyzer is patched on the module's symbol because
``get_memory_health_analyzer`` is imported at module level into
``memory_health_tools``'s namespace (closure-over-import pattern,
same as the akosha_tools gotcha).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.monitoring import memory_health_tools
from session_buddy.mcp.tools.monitoring.memory_health_tools import (
    _generate_error_hotspot_insights,
    _generate_reflection_health_insights,
    register_memory_health_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metrics(
    *,
    total_reflections: int = 100,
    stale_reflections: int = 0,
    stale_threshold_days: int = 90,
    storage_size_bytes: int = 10 * 1024 * 1024,
    avg_reflection_age_days: float = 30.0,
    tags_distribution: dict[str, int] | None = None,
    recent_error_rate: float = 1.0,
    unresolved_errors: int = 0,
    avg_resolution_time_minutes: float | None = 5.0,
    most_common_error_types: list[tuple[str, int]] | None = None,
    extra: dict | None = None,
) -> SimpleNamespace:
    """Build a fake metrics object that supports to_dict()."""
    data: dict = {
        "total_reflections": total_reflections,
        "stale_reflections": stale_reflections,
        "stale_threshold_days": stale_threshold_days,
        "storage_size_bytes": storage_size_bytes,
        "avg_reflection_age_days": avg_reflection_age_days,
        "tags_distribution": tags_distribution or {},
        "recent_error_rate": recent_error_rate,
        "unresolved_errors": unresolved_errors,
        "avg_resolution_time_minutes": avg_resolution_time_minutes,
        "most_common_error_types": most_common_error_types or [],
    }
    if extra:
        data.update(extra)
    metrics = SimpleNamespace(**data)
    metrics.to_dict = lambda: dict(data)
    return metrics


class _FakeServer:
    """Capture ``server.tool()`` and ``server.prompt()`` decorators."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.prompts: dict[str, object] = {}

    def tool(self):  # noqa: D401 — fake decorator factory
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def prompt(self):  # noqa: D401 — fake decorator factory
        def decorator(fn):
            self.prompts[fn.__name__] = fn
            return fn

        return decorator


def _make_analyzer(
    *,
    reflection_health: SimpleNamespace | None = None,
    error_hotspots: SimpleNamespace | None = None,
    cleanup_recommendations: list[dict] | None = None,
    init_raises: Exception | None = None,
    get_reflection_health_raises: Exception | None = None,
    get_error_hotspots_raises: Exception | None = None,
    get_cleanup_recommendations_raises: Exception | None = None,
) -> MagicMock:
    """Build a fake analyzer whose methods can be configured to raise."""
    analyzer = MagicMock()
    if init_raises is not None:
        analyzer.initialize = AsyncMock(side_effect=init_raises)
    else:
        analyzer.initialize = AsyncMock(return_value=None)
    if get_reflection_health_raises is not None:
        analyzer.get_reflection_health = AsyncMock(
            side_effect=get_reflection_health_raises
        )
    else:
        analyzer.get_reflection_health = AsyncMock(
            return_value=reflection_health or _make_metrics()
        )
    if get_error_hotspots_raises is not None:
        analyzer.get_error_hotspots = AsyncMock(
            side_effect=get_error_hotspots_raises
        )
    else:
        analyzer.get_error_hotspots = AsyncMock(
            return_value=error_hotspots or _make_metrics()
        )
    if get_cleanup_recommendations_raises is not None:
        analyzer.get_cleanup_recommendations = AsyncMock(
            side_effect=get_cleanup_recommendations_raises
        )
    else:
        analyzer.get_cleanup_recommendations = AsyncMock(
            return_value=cleanup_recommendations or []
        )
    return analyzer


# ---------------------------------------------------------------------------
# _generate_reflection_health_insights
# ---------------------------------------------------------------------------


class TestGenerateReflectionHealthInsights:
    def test_no_insights_when_total_reflections_zero(self) -> None:
        # No reflections → staleness insight suppressed; storage/age
        # and tag insights still produced.
        metrics = _make_metrics(
            total_reflections=0,
            stale_reflections=0,
        )
        insights = _generate_reflection_health_insights(metrics)
        # No staleness insight at all.
        assert not any("staleness" in i.lower() for i in insights)
        # Storage insight still present.
        assert any("storage" in i.lower() or "MB" in i for i in insights)

    def test_high_staleness(self) -> None:
        # 30/100 = 30% stale → "High staleness" branch.
        metrics = _make_metrics(
            total_reflections=100,
            stale_reflections=30,
        )
        insights = _generate_reflection_health_insights(metrics)
        assert any("⚠️" in i and "High staleness" in i for i in insights)

    def test_growing_staleness(self) -> None:
        # 15/100 = 15% stale → "Growing staleness" branch.
        metrics = _make_metrics(
            total_reflections=100,
            stale_reflections=15,
        )
        insights = _generate_reflection_health_insights(metrics)
        assert any(
            "📊" in i and "Growing staleness" in i for i in insights
        )

    def test_healthy_staleness(self) -> None:
        # 5/100 = 5% stale → "Healthy staleness" branch.
        metrics = _make_metrics(
            total_reflections=100,
            stale_reflections=5,
        )
        insights = _generate_reflection_health_insights(metrics)
        assert any(
            "✅" in i and "Healthy staleness" in i for i in insights
        )

    def test_large_storage(self) -> None:
        # 200 MB → "Large database" branch.
        metrics = _make_metrics(
            storage_size_bytes=200 * 1024 * 1024,
        )
        insights = _generate_reflection_health_insights(metrics)
        assert any(
            "💾" in i and "Large database" in i for i in insights
        )

    def test_moderate_storage(self) -> None:
        # 75 MB → "Moderate storage" branch.
        metrics = _make_metrics(
            storage_size_bytes=75 * 1024 * 1024,
        )
        insights = _generate_reflection_health_insights(metrics)
        assert any(
            "📦" in i and "Moderate storage" in i for i in insights
        )

    def test_efficient_storage(self) -> None:
        # 10 MB → "Efficient storage" branch.
        metrics = _make_metrics(
            storage_size_bytes=10 * 1024 * 1024,
        )
        insights = _generate_reflection_health_insights(metrics)
        assert any(
            "✅" in i and "Efficient storage" in i for i in insights
        )

    def test_aging_content(self) -> None:
        metrics = _make_metrics(avg_reflection_age_days=80.0)
        insights = _generate_reflection_health_insights(metrics)
        assert any("⏰" in i and "Aging content" in i for i in insights)

    def test_fresh_content(self) -> None:
        metrics = _make_metrics(avg_reflection_age_days=10.0)
        insights = _generate_reflection_health_insights(metrics)
        assert any("🆕" in i and "Fresh content" in i for i in insights)

    def test_normal_age_no_insight(self) -> None:
        # 30 days is between 14 and 60 → no age insight emitted.
        metrics = _make_metrics(avg_reflection_age_days=30.0)
        insights = _generate_reflection_health_insights(metrics)
        assert not any(
            "Aging content" in i or "Fresh content" in i for i in insights
        )

    def test_top_tag_emitted(self) -> None:
        metrics = _make_metrics(
            tags_distribution={"python": 50, "rust": 20, "go": 10},
        )
        insights = _generate_reflection_health_insights(metrics)
        assert any(
            "🏷️" in i and "python" in i and "50" in i for i in insights
        )

    def test_empty_tags_no_insight(self) -> None:
        metrics = _make_metrics(tags_distribution={})
        insights = _generate_reflection_health_insights(metrics)
        assert not any("🏷️" in i for i in insights)

    def test_multiple_insights_aggregated(self) -> None:
        # Combine high staleness + large storage + aging + tags →
        # at least one insight per category.
        metrics = _make_metrics(
            total_reflections=100,
            stale_reflections=30,
            storage_size_bytes=200 * 1024 * 1024,
            avg_reflection_age_days=80.0,
            tags_distribution={"x": 100},
        )
        insights = _generate_reflection_health_insights(metrics)
        assert len(insights) >= 4


# ---------------------------------------------------------------------------
# _generate_error_hotspot_insights
# ---------------------------------------------------------------------------


class TestGenerateErrorHotspotInsights:
    def test_high_error_rate(self) -> None:
        metrics = _make_metrics(recent_error_rate=3.0)
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "🚨" in i and "High error rate" in i for i in insights
        )

    def test_elevated_error_rate(self) -> None:
        metrics = _make_metrics(recent_error_rate=1.5)
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "⚠️" in i and "Elevated error rate" in i for i in insights
        )

    def test_moderate_error_rate(self) -> None:
        metrics = _make_metrics(recent_error_rate=0.75)
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "📊" in i and "Moderate error rate" in i for i in insights
        )

    def test_low_error_rate(self) -> None:
        metrics = _make_metrics(recent_error_rate=0.1)
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "✅" in i and "Low error rate" in i for i in insights
        )

    def test_many_unresolved_errors(self) -> None:
        metrics = _make_metrics(unresolved_errors=15)
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "❌" in i and "Many unresolved errors" in i for i in insights
        )

    def test_some_unresolved_errors(self) -> None:
        metrics = _make_metrics(unresolved_errors=7)
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "⚠️" in i and "Unresolved errors" in i and "7" in i
            for i in insights
        )

    def test_no_unresolved_insight_when_low(self) -> None:
        metrics = _make_metrics(unresolved_errors=2)
        insights = _generate_error_hotspot_insights(metrics)
        assert not any(
            "unresolved errors" in i.lower() and ("❌" in i or "⚠️" in i)
            for i in insights
        )

    def test_fast_resolution(self) -> None:
        metrics = _make_metrics(avg_resolution_time_minutes=3.0)
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "⚡" in i and "Fast resolution" in i for i in insights
        )

    def test_slow_resolution(self) -> None:
        metrics = _make_metrics(avg_resolution_time_minutes=20.0)
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "🐌" in i and "Slow resolution" in i for i in insights
        )

    def test_normal_resolution_no_insight(self) -> None:
        # 5-15 min range → no insight.
        metrics = _make_metrics(avg_resolution_time_minutes=10.0)
        insights = _generate_error_hotspot_insights(metrics)
        assert not any(
            "resolution" in i.lower() and ("⚡" in i or "🐌" in i)
            for i in insights
        )

    def test_none_resolution_no_insight(self) -> None:
        metrics = _make_metrics(avg_resolution_time_minutes=None)
        insights = _generate_error_hotspot_insights(metrics)
        # None is falsy → no resolution insight.
        assert not any(
            "resolution" in i.lower() for i in insights
        )

    def test_recurring_issue(self) -> None:
        metrics = _make_metrics(
            most_common_error_types=[("ConnectionError", 7)]
        )
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "🔄" in i
            and "Recurring issue" in i
            and "ConnectionError" in i
            for i in insights
        )

    def test_pattern_detected(self) -> None:
        metrics = _make_metrics(
            most_common_error_types=[("TimeoutError", 4)]
        )
        insights = _generate_error_hotspot_insights(metrics)
        assert any(
            "📋" in i
            and "Pattern detected" in i
            and "TimeoutError" in i
            for i in insights
        )

    def test_low_count_no_pattern_insight(self) -> None:
        # count = 2 is below the >=3 threshold → no insight.
        metrics = _make_metrics(
            most_common_error_types=[("ValueError", 2)]
        )
        insights = _generate_error_hotspot_insights(metrics)
        assert not any(
            "Recurring" in i or "Pattern detected" in i for i in insights
        )

    def test_empty_error_types_no_insight(self) -> None:
        metrics = _make_metrics(most_common_error_types=[])
        insights = _generate_error_hotspot_insights(metrics)
        assert not any(
            "Recurring" in i or "Pattern detected" in i for i in insights
        )


# ---------------------------------------------------------------------------
# register_memory_health_tools
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registers_three_tools_and_one_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: _make_analyzer(),
        )
        server = _FakeServer()
        register_memory_health_tools(server)
        assert "get_reflection_health" in server.tools
        assert "get_error_hotspots" in server.tools
        assert "get_cleanup_recommendations" in server.tools
        assert "memory_health_help" in server.prompts


# ---------------------------------------------------------------------------
# get_reflection_health (the tool)
# ---------------------------------------------------------------------------


class TestGetReflectionHealth:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_metrics = _make_metrics(
            total_reflections=100,
            stale_reflections=30,
        )
        analyzer = _make_analyzer(reflection_health=fake_metrics)
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: analyzer,
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        result = await server.tools["get_reflection_health"]()
        assert result["success"] is True
        assert result["total_reflections"] == 100
        assert result["stale_reflections"] == 30
        # Insights list attached.
        assert "insights" in result
        assert isinstance(result["insights"], list)
        analyzer.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_threshold_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = _make_analyzer()
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: analyzer,
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        await server.tools["get_reflection_health"](stale_threshold_days=60)
        # Default 90 → call was 60 → propagated.
        analyzer.get_reflection_health.assert_awaited_once_with(
            stale_threshold_days=60
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = _make_analyzer(
            get_reflection_health_raises=RuntimeError("db down")
        )
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: analyzer,
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        result = await server.tools["get_reflection_health"]()
        assert result["success"] is False
        assert "db down" in result["error"]
        assert (
            "Failed to retrieve reflection health metrics"
            in result["message"]
        )


# ---------------------------------------------------------------------------
# get_error_hotspots (the tool)
# ---------------------------------------------------------------------------


class TestGetErrorHotspots:
    @pytest.mark.asyncio
    async def test_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_metrics = _make_metrics(
            recent_error_rate=3.0,
            unresolved_errors=15,
        )
        analyzer = _make_analyzer(error_hotspots=fake_metrics)
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: analyzer,
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        result = await server.tools["get_error_hotspots"]()
        assert result["success"] is True
        assert result["recent_error_rate"] == 3.0
        assert result["unresolved_errors"] == 15
        assert "insights" in result
        analyzer.get_error_hotspots.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = _make_analyzer(
            get_error_hotspots_raises=RuntimeError("query failed")
        )
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: analyzer,
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        result = await server.tools["get_error_hotspots"]()
        assert result["success"] is False
        assert "query failed" in result["error"]


# ---------------------------------------------------------------------------
# get_cleanup_recommendations (the tool)
# ---------------------------------------------------------------------------


class TestGetCleanupRecommendations:
    @pytest.mark.asyncio
    async def test_happy_path_groups_by_priority_and_category(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recs = [
            {
                "priority": "high",
                "category": "storage",
                "action": "Archive old reflections",
                "details": "x",
                "estimated_impact": "y",
            },
            {
                "priority": "medium",
                "category": "errors",
                "action": "Investigate error patterns",
                "details": "x",
                "estimated_impact": "y",
            },
            {
                "priority": "low",
                "category": "storage",
                "action": "Optimize indices",
                "details": "x",
                "estimated_impact": "y",
            },
            {
                "priority": "high",
                "category": "errors",
                "action": "Document unresolved errors",
                "details": "x",
                "estimated_impact": "y",
            },
        ]
        analyzer = _make_analyzer(cleanup_recommendations=recs)
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: analyzer,
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        result = await server.tools["get_cleanup_recommendations"]()
        assert result["success"] is True
        assert result["total_recommendations"] == 4
        # by_priority has 2 highs, 1 medium, 1 low.
        assert len(result["by_priority"]["high"]) == 2
        assert len(result["by_priority"]["medium"]) == 1
        assert len(result["by_priority"]["low"]) == 1
        # by_category has 2 storage, 2 errors.
        assert len(result["by_category"]["storage"]) == 2
        assert len(result["by_category"]["errors"]) == 2
        # All recs preserved under "recommendations".
        assert len(result["recommendations"]) == 4

    @pytest.mark.asyncio
    async def test_empty_recommendations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = _make_analyzer(cleanup_recommendations=[])
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: analyzer,
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        result = await server.tools["get_cleanup_recommendations"]()
        assert result["success"] is True
        assert result["total_recommendations"] == 0
        assert result["by_priority"] == {
            "high": [],
            "medium": [],
            "low": [],
        }
        assert result["by_category"] == {}

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = _make_analyzer(
            get_cleanup_recommendations_raises=RuntimeError("rec gen failed")
        )
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: analyzer,
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        result = await server.tools["get_cleanup_recommendations"]()
        assert result["success"] is False
        assert "rec gen failed" in result["error"]
        assert (
            "Failed to generate cleanup recommendations" in result["message"]
        )


# ---------------------------------------------------------------------------
# memory_health_help (the prompt)
# ---------------------------------------------------------------------------


class TestMemoryHealthHelp:
    def test_returns_static_help_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            memory_health_tools,
            "get_memory_health_analyzer",
            lambda: _make_analyzer(),
        )

        server = _FakeServer()
        register_memory_health_tools(server)
        text = server.prompts["memory_health_help"]()
        assert "Memory Health Monitoring" in text
        assert "get_reflection_health" in text
        assert "get_error_hotspots" in text
        assert "get_cleanup_recommendations" in text
        assert "Priority Levels" in text
