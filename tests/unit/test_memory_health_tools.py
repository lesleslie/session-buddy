from __future__ import annotations

from types import SimpleNamespace

import pytest


class DummyServer:
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


class FakeMetrics:
    def __init__(
        self,
        *,
        total_reflections: int = 100,
        stale_reflections: int = 15,
        stale_threshold_days: int = 90,
        storage_size_bytes: int = 75 * 1024 * 1024,
        avg_reflection_age_days: int = 70,
        tags_distribution: dict[str, int] | None = None,
        recent_error_rate: float = 2.5,
        unresolved_errors: int = 7,
        avg_resolution_time_minutes: float = 20.0,
        most_common_error_types: list[tuple[str, int]] | None = None,
    ) -> None:
        self.total_reflections = total_reflections
        self.stale_reflections = stale_reflections
        self.stale_threshold_days = stale_threshold_days
        self.storage_size_bytes = storage_size_bytes
        self.avg_reflection_age_days = avg_reflection_age_days
        self.tags_distribution = tags_distribution or {"release": 4, "bug": 2}
        self.recent_error_rate = recent_error_rate
        self.unresolved_errors = unresolved_errors
        self.avg_resolution_time_minutes = avg_resolution_time_minutes
        self.most_common_error_types = most_common_error_types or [("ValueError", 6)]

    def to_dict(self) -> dict[str, object]:
        return {"metric": "value"}


@pytest.mark.asyncio
async def test_register_memory_health_tools_happy_path_and_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.monitoring import memory_health_tools as mod

    analyzer = SimpleNamespace(
        initialize=lambda: None,
        get_reflection_health=lambda stale_threshold_days=90: FakeMetrics(),
        get_error_hotspots=lambda: FakeMetrics(),
        get_cleanup_recommendations=lambda: [
            {"priority": "high", "category": "storage", "action": "archive"},
            {"priority": "medium", "category": "errors", "action": "review"},
            {"priority": "low", "category": "docs", "action": "document"},
        ],
    )

    async def initialize():
        return None

    async def get_reflection_health(stale_threshold_days=90):
        return FakeMetrics(stale_threshold_days=stale_threshold_days)

    async def get_error_hotspots():
        return FakeMetrics()

    async def get_cleanup_recommendations():
        return [
            {"priority": "high", "category": "storage", "action": "archive"},
            {"priority": "medium", "category": "errors", "action": "review"},
            {"priority": "low", "category": "docs", "action": "document"},
        ]

    analyzer.initialize = initialize
    analyzer.get_reflection_health = get_reflection_health
    analyzer.get_error_hotspots = get_error_hotspots
    analyzer.get_cleanup_recommendations = get_cleanup_recommendations

    monkeypatch.setattr(mod, "get_memory_health_analyzer", lambda: analyzer)

    server = DummyServer()
    mod.register_memory_health_tools(server)

    reflection = await server.tools["get_reflection_health"]()
    errors = await server.tools["get_error_hotspots"]()
    cleanup = await server.tools["get_cleanup_recommendations"]()
    help_text = server.prompts["memory_health_help"]()

    assert reflection["success"] is True
    assert any("staleness" in insight.lower() for insight in reflection["insights"])
    assert any("storage" in insight.lower() for insight in reflection["insights"])

    assert errors["success"] is True
    assert any("error rate" in insight.lower() for insight in errors["insights"])
    assert any("recurring issue" in insight.lower() for insight in errors["insights"])

    assert cleanup["success"] is True
    assert cleanup["by_priority"]["high"][0]["action"] == "archive"
    assert "memory health monitoring" in help_text.lower()


def test_memory_health_insight_generators_cover_branches() -> None:
    from session_buddy.mcp.tools.monitoring.memory_health_tools import (
        _generate_error_hotspot_insights,
        _generate_reflection_health_insights,
    )

    reflection = FakeMetrics(
        total_reflections=10,
        stale_reflections=1,
        storage_size_bytes=150 * 1024 * 1024,
        avg_reflection_age_days=10,
        tags_distribution={"bug": 5, "docs": 2},
    )
    error_metrics = FakeMetrics(
        recent_error_rate=0.4,
        unresolved_errors=12,
        avg_resolution_time_minutes=3.0,
        most_common_error_types=[("TypeError", 5)],
    )

    reflection_insights = _generate_reflection_health_insights(reflection)
    error_insights = _generate_error_hotspot_insights(error_metrics)

    assert any("healthy staleness" in item.lower() for item in reflection_insights)
    assert any("large database" in item.lower() for item in reflection_insights)
    assert any("fresh content" in item.lower() for item in reflection_insights)
    assert any("most common tag" in item.lower() for item in reflection_insights)

    assert any("low error rate" in item.lower() for item in error_insights)
    assert any("many unresolved errors" in item.lower() for item in error_insights)
    assert any("fast resolution" in item.lower() for item in error_insights)
    assert any("recurring issue" in item.lower() for item in error_insights)
