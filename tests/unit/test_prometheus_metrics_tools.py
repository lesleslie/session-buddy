from __future__ import annotations

from types import SimpleNamespace

import pytest


class DummyMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _metric(name: str, value: float, labels: dict[str, str] | None = None):
    sample = SimpleNamespace(name=name, value=value, labels=labels or {})
    return SimpleNamespace(samples=[sample])


@pytest.mark.asyncio
async def test_prometheus_metrics_tools_cover_available_and_unavailable_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.monitoring import prometheus_metrics_tools as tools

    mcp = DummyMCP()

    monkeypatch.setattr(tools, "METRICS_AVAILABLE", False)
    tools.register_prometheus_metrics_tools(mcp)
    assert (
        await mcp.tools["get_prometheus_metrics"]()
        == "Error: Prometheus metrics module not available. Install prometheus_client to enable metrics."
    )

    class FakeMetrics:
        session_start_total = SimpleNamespace(
            collect=lambda: [_metric("session_start_total_total", 3)]
        )
        session_end_total = SimpleNamespace(
            collect=lambda: [_metric("session_end_total_total", 2)]
        )
        active_sessions = SimpleNamespace(
            collect=lambda: [_metric("active_sessions", 5, {"component_name": "core"})]
        )
        session_quality_score = SimpleNamespace(
            collect=lambda: [_metric("session_quality_score", 88.5, {"component_name": "core"})]
        )
        mcp_event_emit_success_total = SimpleNamespace(
            collect=lambda: [_metric("mcp_event_emit_success_total_total", 7)]
        )
        mcp_event_emit_failure_total = SimpleNamespace(
            collect=lambda: [_metric("mcp_event_emit_failure_total_total", 1)]
        )

        def export_metrics(self) -> bytes:
            return b"session_buddy_metric 1\n"

    monkeypatch.setattr(tools, "METRICS_AVAILABLE", True)
    monkeypatch.setattr(tools, "get_metrics", lambda: FakeMetrics())
    monkeypatch.setattr(
        tools,
        "get_prometheus_tools_logger",
        lambda: SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
        ),
    )

    mcp = DummyMCP()
    tools.register_prometheus_metrics_tools(mcp)

    metrics_text = await mcp.tools["get_prometheus_metrics"]()
    summary = await mcp.tools["get_metrics_summary"]()
    listing = await mcp.tools["list_session_metrics"]()

    assert "session_buddy_metric 1" in metrics_text
    assert summary == {
        "total_sessions_started": 3,
        "total_sessions_ended": 2,
        "active_sessions": {"core": 5},
        "quality_scores": {"core": 88.5},
        "mcp_events_success": 7,
        "mcp_events_failure": 1,
    }
    assert "session_lifecycle_metrics" in listing
    assert "mcp_event_metrics" in listing
    assert "system_health_metrics" in listing

