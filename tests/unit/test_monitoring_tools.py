from __future__ import annotations

from types import SimpleNamespace

import pytest


class DummyServer:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FakeMonitor:
    def __init__(self) -> None:
        self.started = []
        self.stopped = False

    async def start_monitoring(self, project_paths=None):
        self.started.append(project_paths)

    async def stop_monitoring(self):
        self.stopped = True
        return {
            "duration_minutes": 12.5,
            "files_tracked": 4,
            "apps_monitored": 3,
            "context_switches": 2,
        }

    def get_activity_summary(self, hours: int):  # NOTE: sync, matches production
        return {
            "has_data": True,
            "file_activity": [
                {"path": "/a.py", "access_count": 4},
                {"path": "/b.py", "access_count": 2},
            ],
            "app_activity": [
                {"name": "VS Code", "focus_time_minutes": 30.0},
            ],
            "productivity_metrics": {
                "focus_time_minutes": 40,
                "context_switches": 3,
                "deep_work_periods": 2,
            },
        }

    async def get_context_insights(self, hours: int):
        return {
            "has_data": True,
            "current_focus": {"area": "refactoring", "duration_minutes": 22},
            "project_patterns": [{"description": "Tests first"}],
            "technology_context": [{"name": "Python", "confidence": 0.91}],
            "recommendations": ["keep going"],
        }

    async def get_active_files(self, minutes: int):
        return [
            {"path": "/a.py", "last_modified": "now", "change_count": 5},
            {"path": "/b.py", "last_modified": "later", "change_count": 2},
        ]


class FakeInterruptionManager:
    def __init__(self) -> None:
        self.started = []

    async def start_monitoring(self, session_id: str, user_id: str):
        self.started.append((session_id, user_id))

    async def stop_monitoring(self):
        return {
            "duration_minutes": 8.0,
            "interruption_count": 1,
            "contexts_saved": 1,
        }

    async def create_context_snapshot(self, session_id: str, context_data: dict):
        return "ctx-123"

    async def preserve_context(self, session_id: str, interruption_reason: str):
        return {"id": "snap-1", "item_count": 3}

    async def restore_context(self, session_id: str):
        return {
            "success": True,
            "item_count": 2,
            "original_timestamp": "2026-01-01T00:00:00Z",
        }

    async def get_interruption_history(self, user_id: str, hours: int):
        return [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "type": "sleep",
                "reason": "system sleep",
                "recovery_action": "resume",
            }
        ]


def test_format_helpers_cover_key_branches() -> None:
    from session_buddy.mcp.tools.monitoring.monitoring_tools import (
        _format_app_activity,
        _format_context_insights_output,
        _format_file_activity,
        _format_productivity_metrics,
    )

    assert _format_file_activity([]) == []
    assert _format_app_activity([]) == []
    assert _format_productivity_metrics({}) == []

    file_lines = _format_file_activity(
        [{"path": f"/f{i}.py", "access_count": i} for i in range(12)]
    )
    assert file_lines[0] == "📄 File Activity (12 files):"
    assert any("... and 2 more files" in line for line in file_lines)

    app_lines = _format_app_activity(
        [{"name": "Editor", "focus_time_minutes": 12.5}]
    )
    assert app_lines[0].startswith("\n🖥️ Application Focus:")

    productivity_lines = _format_productivity_metrics(
        {
            "focus_time_minutes": 40,
            "context_switches": 3,
            "deep_work_periods": 2,
        }
    )
    assert productivity_lines[0].startswith("\n📈 Productivity Metrics:")

    context_lines = _format_context_insights_output(
        {
            "has_data": True,
            "current_focus": {"area": "tests", "duration_minutes": 15},
            "project_patterns": [{"description": "morning focus"}],
            "technology_context": [{"name": "Python", "confidence": 0.88}],
            "recommendations": ["keep shipping"],
        },
        1,
    )
    assert any("Current Focus" in line for line in context_lines)
    assert any("Project Patterns" in line for line in context_lines)
    assert any("Technology Context" in line for line in context_lines)
    assert any("Recommendations" in line for line in context_lines)


@pytest.mark.asyncio
async def test_monitoring_and_interruption_impls_success_and_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.monitoring import monitoring_tools as mod

    monitor = FakeMonitor()
    interruption_manager = FakeInterruptionManager()

    async def resolve_app_monitor():
        return monitor

    async def resolve_interruption_manager():
        return interruption_manager

    monkeypatch.setattr(mod, "resolve_app_monitor", resolve_app_monitor)
    monkeypatch.setattr(mod, "resolve_interruption_manager", resolve_interruption_manager)

    started = await mod._start_app_monitoring_impl(["/repo/a", "/repo/b"])
    summary = await mod._get_activity_summary_impl(4)
    insights = await mod._get_context_insights_impl(2)
    active = await mod._get_active_files_impl(60)
    stopped = await mod._stop_app_monitoring_impl()
    int_started = await mod._start_interruption_monitoring_impl("sess-1", "user-1")
    int_summary = await mod._stop_interruption_monitoring_impl()
    created = await mod._create_session_context_impl("sess-2", {"a": 1, "b": 2})
    preserved = await mod._preserve_current_context_impl("sess-3", "manual")
    restored = await mod._restore_session_context_impl("sess-4")
    history = await mod._get_interruption_history_impl("user-1", 24)

    assert "Application Monitoring Started" in started
    assert "Activity Summary" in summary
    assert "Context Insights" in insights
    assert "Active Files" in active
    assert "Application Monitoring Stopped" in stopped
    assert "Interruption Monitoring Started" in int_started
    assert "Interruption Monitoring Stopped" in int_summary
    assert "Session Context Created" in created
    assert "Context Preserved" in preserved
    assert "Context Restored" in restored
    assert "Interruption History" in history

    async def resolve_none():
        return None

    monkeypatch.setattr(mod, "resolve_app_monitor", resolve_none)
    monkeypatch.setattr(mod, "resolve_interruption_manager", resolve_none)

    assert "not available" in await mod._start_app_monitoring_impl(None)
    assert "not available" in await mod._stop_app_monitoring_impl()
    assert "not available" in await mod._get_activity_summary_impl()
    assert "not available" in await mod._get_context_insights_impl()
    assert "not available" in await mod._get_active_files_impl()
    assert "not available" in await mod._start_interruption_monitoring_impl("x")
    assert "not available" in await mod._stop_interruption_monitoring_impl()
    assert "not available" in await mod._create_session_context_impl("x", {})
    assert "not available" in await mod._preserve_current_context_impl("x")
    assert "not available" in await mod._restore_session_context_impl("x")
    assert "not available" in await mod._get_interruption_history_impl("u")


class SyncFakeMonitor:
    """Fake AppMonitor whose ``get_activity_summary`` is sync, mirroring the
    real ``AppMonitor.get_activity_summary`` signature at
    ``session_buddy/app_monitor.py`` (a plain ``def`` that returns ``dict``)."""

    def __init__(self) -> None:
        self.started: list[object] = []
        self.stopped = False
        self.activity_calls: list[int] = []

    async def start_monitoring(self, project_paths=None):
        self.started.append(project_paths)

    async def stop_monitoring(self):
        self.stopped = True
        return {
            "duration_minutes": 12.5,
            "files_tracked": 4,
            "apps_monitored": 3,
            "context_switches": 2,
        }

    def get_activity_summary(self, hours: int):  # NOTE: sync, NOT async
        self.activity_calls.append(hours)
        return {
            "has_data": True,
            "file_activity": [
                {"path": "/a.py", "access_count": 4},
                {"path": "/b.py", "access_count": 2},
            ],
            "app_activity": [
                {"name": "VS Code", "focus_time_minutes": 30.0},
            ],
            "productivity_metrics": {
                "focus_time_minutes": 40,
                "context_switches": 3,
                "deep_work_periods": 2,
            },
        }


@pytest.mark.asyncio
async def test_get_activity_summary_impl_works_with_sync_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for session-buddy-activity-summary.

    The real ``AppMonitor.get_activity_summary`` is a plain ``def`` that
    returns a ``dict``. Awaiting it raises ``TypeError: object dict can't
    be used in 'await' expression``. This test pins the call site to the
    actual sync contract by using a sync fake monitor.
    """
    from session_buddy.mcp.tools.monitoring import monitoring_tools as mod

    sync_monitor = SyncFakeMonitor()

    async def resolve_sync_monitor():
        return sync_monitor

    monkeypatch.setattr(mod, "resolve_app_monitor", resolve_sync_monitor)

    summary = await mod._get_activity_summary_impl(3)

    # If the call site were still `await monitor.get_activity_summary(...)`,
    # this would raise TypeError before we ever got here.
    assert "Activity Summary" in summary
    assert "Last 3 Hours" in summary
    assert sync_monitor.activity_calls == [3]


@pytest.mark.asyncio
async def test_get_activity_summary_operation_does_not_await_sync_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for session-buddy-activity-summary.

    Exercises the inner operation directly with a sync-returning monitor.
    Pre-fix, this raised ``TypeError: object dict can't be used in 'await'
    expression`` at monitoring_tools.py:199.
    """
    from session_buddy.mcp.tools.monitoring import monitoring_tools as mod

    sync_monitor = SyncFakeMonitor()

    result = await mod._get_activity_summary_operation(sync_monitor, 2)

    assert "Activity Summary" in result
    assert "Last 2 Hours" in result
    assert sync_monitor.activity_calls == [2]  # confirms the call happened
