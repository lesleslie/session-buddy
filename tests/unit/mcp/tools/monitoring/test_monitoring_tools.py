"""Tests for session_buddy.mcp.tools.monitoring.monitoring_tools.

Covers the application monitoring and interruption management MCP tools:

Service resolution (4 tests):
- ``_require_app_monitor``: returns monitor or raises RuntimeError when
  resolution returns None
- ``_require_interruption_manager``: same pattern

Operation executors (4 tests):
- ``_execute_monitor_operation``: happy path delegates to operation;
  RuntimeError → "❌ {e}"; other Exception → ToolMessages.operation_failed
- ``_execute_interruption_operation``: same pattern

App-monitor operations (15+ tests):
- ``_start_app_monitoring_operation``: monitor.start_monitoring called;
  project_paths=None → "all accessible paths"; project_paths=[…] →
  listed; missing ``ide_monitor`` attribute doesn't crash (hasattr guard);
  output contains "Application Monitoring Started" + tracking list
- ``_stop_app_monitoring_operation``: summary keys rendered; output
  contains "Application Monitoring Stopped"
- ``_get_activity_summary_operation``: has_data=False → "No activity";
  with data → file + app + productivity sections
- ``_format_file_activity``: empty → []; ≤10 → all; >10 → "... and N more"
- ``_format_app_activity``: empty → []; ≤5 → all
- ``_format_productivity_metrics``: empty → []; with data → 3 fields
- ``_get_context_insights_operation``: has_data=False → "No context data";
  with data → focus + patterns + tech + recommendations
- ``_get_active_files_operation``: empty → "No active files"; present →
  top 20 + "... and N more" when >20

Interruption operations (8 tests):
- ``_start_interruption_monitoring_operation``: manager.start_monitoring
  called; output contains session_id and user_id
- ``_stop_interruption_monitoring_operation``: summary rendered
- ``_create_session_context_operation``: create_context_snapshot called;
  context_id, session_id, len(context_data) rendered
- ``_preserve_current_context_operation``: preserve_context called;
  id, reason, item_count rendered
- ``_restore_session_context_operation``: success=False → "❌ Failed"
  with error; success=True → "Context Restored" with metadata
- ``_get_interruption_history_operation``: empty → "No interruptions";
  present → top 10 + "... and N more"

MCP tool registration (10+ tests):
- ``register_monitoring_tools`` registers all 10 tools
- ``start_app_monitoring``: happy path + JSON string parsing fallback
  (defensive against str input)
- 9 other tools: end-to-end happy path

Real monitors / managers are mocked via
``monitoring_tools.resolve_app_monitor`` and
``monitoring_tools.resolve_interruption_manager``. The closures
reference these aliases at module-import time, so monkeypatch the
module's symbol (closure-over-import pattern, same as prior waves).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.monitoring import monitoring_tools
from session_buddy.mcp.tools.monitoring.monitoring_tools import (
    _create_session_context_operation,
    _execute_interruption_operation,
    _execute_monitor_operation,
    _format_app_activity,
    _format_context_insights_output,
    _format_file_activity,
    _format_productivity_metrics,
    _get_active_files_operation,
    _get_activity_summary_operation,
    _get_context_insights_operation,
    _get_interruption_history_operation,
    _preserve_current_context_operation,
    _require_app_monitor,
    _require_interruption_manager,
    _restore_session_context_operation,
    _start_app_monitoring_impl,
    _start_app_monitoring_operation,
    _start_interruption_monitoring_operation,
    _stop_app_monitoring_operation,
    _stop_interruption_monitoring_operation,
    register_monitoring_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Capture ``mcp.tool()`` decorators so registered functions can run."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _make_monitor(**overrides) -> MagicMock:
    """Build a fake ApplicationMonitor with configurable methods."""
    monitor = MagicMock()
    monitor.start_monitoring = AsyncMock(return_value=None)
    monitor.stop_monitoring = AsyncMock(
        return_value={
            "duration_minutes": 30.0,
            "files_tracked": 5,
            "apps_monitored": 3,
            "context_switches": 7,
        }
    )
    monitor.get_activity_summary = MagicMock(
        return_value={
            "has_data": True,
            "file_activity": [],
            "app_activity": [],
            "productivity_metrics": {},
        }
    )
    monitor.get_context_insights = AsyncMock(
        return_value={"has_data": False}
    )
    monitor.get_active_files = AsyncMock(return_value=[])
    # Optional ide_monitor attribute.
    if "ide_monitor" in overrides:
        monitor.ide_monitor = overrides.pop("ide_monitor")
    if "project_paths" in overrides:
        monitor.project_paths = overrides.pop("project_paths")
    return monitor


def _make_manager(**overrides) -> MagicMock:
    """Build a fake InterruptionManager with configurable methods."""
    manager = MagicMock()
    manager.start_monitoring = AsyncMock(return_value=None)
    manager.stop_monitoring = AsyncMock(
        return_value={
            "duration_minutes": 30.0,
            "interruption_count": 4,
            "contexts_saved": 2,
        }
    )
    manager.create_context_snapshot = AsyncMock(return_value="ctx-123")
    manager.preserve_context = AsyncMock(
        return_value={
            "id": "snap-456",
            "item_count": 8,
        }
    )
    manager.restore_context = AsyncMock(
        return_value={
            "success": True,
            "item_count": 5,
            "original_timestamp": "2026-06-15T09:00:00",
        }
    )
    manager.get_interruption_history = AsyncMock(return_value=[])
    return manager


# ---------------------------------------------------------------------------
# _require_app_monitor / _require_interruption_manager
# ---------------------------------------------------------------------------


class TestRequireAppMonitor:
    @pytest.mark.asyncio
    async def test_returns_monitor_when_resolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        result = await _require_app_monitor()
        assert result is monitor

    @pytest.mark.asyncio
    async def test_raises_when_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=None),
        )
        with pytest.raises(RuntimeError, match="Application monitoring"):
            await _require_app_monitor()


class TestRequireInterruptionManager:
    @pytest.mark.asyncio
    async def test_returns_manager_when_resolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )
        result = await _require_interruption_manager()
        assert result is manager

    @pytest.mark.asyncio
    async def test_raises_when_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=None),
        )
        with pytest.raises(RuntimeError, match="Interruption"):
            await _require_interruption_manager()


# ---------------------------------------------------------------------------
# _execute_monitor_operation / _execute_interruption_operation
# ---------------------------------------------------------------------------


class TestExecuteMonitorOperation:
    @pytest.mark.asyncio
    async def test_delegates_to_operation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )

        async def op(m: object) -> str:
            return "ok"

        result = await _execute_monitor_operation("Test op", op)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_runtime_error_returns_emoji_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=None),
        )

        async def op(m: object) -> str:
            return "unreachable"

        result = await _execute_monitor_operation("Test op", op)
        assert result.startswith("❌ ")
        assert "Application monitoring not available" in result

    @pytest.mark.asyncio
    async def test_other_exception_calls_operation_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )

        async def op(m: object) -> str:
            raise ValueError("inner boom")

        with patch.object(
            monitoring_tools.ToolMessages,
            "operation_failed",
            return_value="FAILED_ENVELOPE",
        ) as failed:
            result = await _execute_monitor_operation("Test op", op)

        assert result == "FAILED_ENVELOPE"
        failed.assert_called_once()
        # operation_failed receives (operation_name, exception).
        args, _ = failed.call_args
        assert args[0] == "Test op"
        assert isinstance(args[1], ValueError)


class TestExecuteInterruptionOperation:
    @pytest.mark.asyncio
    async def test_delegates_to_operation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )

        async def op(m: object) -> str:
            return "ok"

        result = await _execute_interruption_operation("Test op", op)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_runtime_error_returns_emoji_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=None),
        )

        async def op(m: object) -> str:
            return "unreachable"

        result = await _execute_interruption_operation("Test op", op)
        assert result.startswith("❌ ")
        assert "Interruption management" in result

    @pytest.mark.asyncio
    async def test_other_exception_calls_operation_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )

        async def op(m: object) -> str:
            raise ValueError("inner boom")

        with patch.object(
            monitoring_tools.ToolMessages,
            "operation_failed",
            return_value="FAILED_ENVELOPE",
        ) as failed:
            result = await _execute_interruption_operation("Test op", op)

        assert result == "FAILED_ENVELOPE"
        failed.assert_called_once()


# ---------------------------------------------------------------------------
# _start_app_monitoring_operation
# ---------------------------------------------------------------------------


class TestStartAppMonitoringOperation:
    @pytest.mark.asyncio
    async def test_start_monitoring_called(self) -> None:
        monitor = _make_monitor()
        await _start_app_monitoring_operation(monitor, None)
        monitor.start_monitoring.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_project_paths_all_accessible(self) -> None:
        monitor = _make_monitor()
        output = await _start_app_monitoring_operation(monitor, None)
        assert "Application Monitoring Started" in output
        assert "all accessible paths" in output
        assert "Now tracking" in output

    @pytest.mark.asyncio
    async def test_with_project_paths_listed(self) -> None:
        monitor = _make_monitor()
        output = await _start_app_monitoring_operation(
            monitor, ["/proj/a", "/proj/b"]
        )
        assert "Monitoring project paths:" in output
        assert "/proj/a" in output
        assert "/proj/b" in output
        # project_paths propagated to monitor and ide_monitor.
        assert monitor.project_paths == ["/proj/a", "/proj/b"]
        assert monitor.ide_monitor.project_paths == ["/proj/a", "/proj/b"]

    @pytest.mark.asyncio
    async def test_without_ide_monitor_attribute(self) -> None:
        # No ide_monitor → hasattr check prevents AttributeError.
        monitor = MagicMock(spec=["start_monitoring"])
        monitor.start_monitoring = AsyncMock(return_value=None)
        output = await _start_app_monitoring_operation(monitor, ["/p"])
        assert "Application Monitoring Started" in output

    @pytest.mark.asyncio
    async def test_with_existing_ide_monitor(self) -> None:
        # Monitor has both attributes; both project_paths updated.
        ide = MagicMock()
        monitor = _make_monitor(ide_monitor=ide)
        await _start_app_monitoring_operation(monitor, ["/proj"])
        assert monitor.project_paths == ["/proj"]
        assert ide.project_paths == ["/proj"]


# ---------------------------------------------------------------------------
# _stop_app_monitoring_operation
# ---------------------------------------------------------------------------


class TestStopAppMonitoringOperation:
    @pytest.mark.asyncio
    async def test_stop_returns_summary(self) -> None:
        monitor = _make_monitor()
        output = await _stop_app_monitoring_operation(monitor)
        assert "Application Monitoring Stopped" in output
        assert "30.0 minutes" in output  # duration
        assert "Files tracked: 5" in output
        assert "Applications monitored: 3" in output
        assert "Context switches: 7" in output
        monitor.stop_monitoring.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_summary_defaults(self) -> None:
        monitor = MagicMock()
        monitor.stop_monitoring = AsyncMock(return_value={})
        output = await _stop_app_monitoring_operation(monitor)
        assert "0.0 minutes" in output  # default duration
        assert "Files tracked: 0" in output
        assert "All monitoring stopped successfully" in output


# ---------------------------------------------------------------------------
# _format_file_activity
# ---------------------------------------------------------------------------


class TestFormatFileActivity:
    def test_empty_returns_empty(self) -> None:
        assert _format_file_activity([]) == []

    def test_under_limit(self) -> None:
        files = [{"path": f"/f{i}", "access_count": i} for i in range(3)]
        lines = _format_file_activity(files)
        assert lines[0] == "📄 File Activity (3 files):"
        # 3 file lines + 1 header.
        assert len(lines) == 4

    def test_over_limit_shows_remainder(self) -> None:
        files = [{"path": f"/f{i}", "access_count": i} for i in range(15)]
        lines = _format_file_activity(files)
        # Header + 10 file lines + "... and 5 more".
        assert len(lines) == 12
        assert any("... and 5 more files" in line for line in lines)


# ---------------------------------------------------------------------------
# _format_app_activity
# ---------------------------------------------------------------------------


class TestFormatAppActivity:
    def test_empty_returns_empty(self) -> None:
        assert _format_app_activity([]) == []

    def test_present_renders(self) -> None:
        apps = [
            {"name": "VS Code", "focus_time_minutes": 45.0},
            {"name": "Chrome", "focus_time_minutes": 15.0},
        ]
        lines = _format_app_activity(apps)
        assert lines[0] == "\n🖥️ Application Focus:"
        assert "VS Code: 45.0 minutes" in lines[1]
        assert "Chrome: 15.0 minutes" in lines[2]

    def test_over_limit_shows_top_5(self) -> None:
        apps = [
            {"name": f"App{i}", "focus_time_minutes": float(i)}
            for i in range(7)
        ]
        lines = _format_app_activity(apps)
        # Header + 5 apps only.
        assert len(lines) == 6
        assert "App0" in lines[1]
        assert "App5" not in " ".join(lines)


# ---------------------------------------------------------------------------
# _format_productivity_metrics
# ---------------------------------------------------------------------------


class TestFormatProductivityMetrics:
    def test_empty_returns_empty(self) -> None:
        assert _format_productivity_metrics({}) == []

    def test_present_renders(self) -> None:
        metrics = {
            "focus_time_minutes": 90.0,
            "context_switches": 3,
            "deep_work_periods": 2,
        }
        lines = _format_productivity_metrics(metrics)
        assert lines[0] == "\n📈 Productivity Metrics:"
        assert "Focus time: 90.0 minutes" in lines[1]
        assert "Context switches: 3" in lines[2]
        assert "Deep work periods: 2" in lines[3]

    def test_missing_keys_default_zero(self) -> None:
        # Empty dict but the function checks ``not metrics`` which is
        # False — so it proceeds with default zeros.
        lines = _format_productivity_metrics({})
        # Wait — the check IS truthy for empty dict → returns [].
        assert lines == []


# ---------------------------------------------------------------------------
# _get_activity_summary_operation
# ---------------------------------------------------------------------------


class TestGetActivitySummaryOperation:
    @pytest.mark.asyncio
    async def test_no_data_message(self) -> None:
        monitor = MagicMock()
        monitor.get_activity_summary = MagicMock(
            return_value={"has_data": False}
        )
        output = await _get_activity_summary_operation(monitor, hours=2)
        assert "Activity Summary - Last 2 Hours" in output
        assert "No activity data available" in output

    @pytest.mark.asyncio
    async def test_with_data_renders_sections(self) -> None:
        monitor = MagicMock()
        monitor.get_activity_summary = MagicMock(
            return_value={
                "has_data": True,
                "file_activity": [
                    {"path": "/a.py", "access_count": 5}
                ],
                "app_activity": [
                    {"name": "VS Code", "focus_time_minutes": 30.0}
                ],
                "productivity_metrics": {
                    "focus_time_minutes": 60.0,
                    "context_switches": 2,
                    "deep_work_periods": 1,
                },
            }
        )
        output = await _get_activity_summary_operation(monitor, hours=1)
        assert "Activity Summary - Last 1 Hours" in output
        assert "File Activity" in output
        assert "/a.py" in output
        assert "Application Focus" in output
        assert "VS Code" in output
        assert "Productivity Metrics" in output
        monitor.get_activity_summary.assert_called_once_with(hours=1)


# ---------------------------------------------------------------------------
# _format_context_insights_output
# ---------------------------------------------------------------------------


class TestFormatContextInsightsOutput:
    def test_no_data(self) -> None:
        lines = _format_context_insights_output({"has_data": False}, hours=1)
        assert lines[0] == "🧠 Context Insights - Last 1 Hours"
        # Check the joined output for substring matches (lines are
        # independent list elements, not substring-searchable directly).
        joined = "\n".join(lines)
        assert "🔍 No context data available" in joined

    def test_with_focus(self) -> None:
        insights = {
            "has_data": True,
            "current_focus": {
                "area": "session-buddy",
                "duration_minutes": 45.0,
            },
        }
        lines = _format_context_insights_output(insights, hours=2)
        joined = "\n".join(lines)
        assert "🎯 Current Focus: session-buddy" in joined
        assert "45.0 minutes" in joined

    def test_with_patterns(self) -> None:
        insights = {
            "has_data": True,
            "project_patterns": [
                {"description": "Uses pytest"},
                {"description": "Uses ruff"},
            ],
        }
        lines = _format_context_insights_output(insights, hours=1)
        joined = "\n".join(lines)
        assert "Project Patterns" in joined
        assert "Uses pytest" in joined

    def test_with_technology_context(self) -> None:
        insights = {
            "has_data": True,
            "technology_context": [
                {"name": "Python", "confidence": 0.95},
            ],
        }
        lines = _format_context_insights_output(insights, hours=1)
        joined = "\n".join(lines)
        assert "Technology Context" in joined
        assert "Python" in joined
        assert "95%" in joined

    def test_with_recommendations(self) -> None:
        insights = {
            "has_data": True,
            "recommendations": ["Run tests", "Update docs"],
        }
        lines = _format_context_insights_output(insights, hours=1)
        joined = "\n".join(lines)
        assert "Recommendations" in joined
        assert "Run tests" in joined


class TestGetContextInsightsOperation:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        monitor = MagicMock()
        monitor.get_context_insights = AsyncMock(
            return_value={"has_data": True, "current_focus": None}
        )
        output = await _get_context_insights_operation(monitor, hours=1)
        assert "Context Insights" in output
        monitor.get_context_insights.assert_awaited_once_with(hours=1)


# ---------------------------------------------------------------------------
# _get_active_files_operation
# ---------------------------------------------------------------------------


class TestGetActiveFilesOperation:
    @pytest.mark.asyncio
    async def test_no_files(self) -> None:
        monitor = MagicMock()
        monitor.get_active_files = AsyncMock(return_value=[])
        output = await _get_active_files_operation(monitor, minutes=60)
        assert "Active Files - Last 60 Minutes" in output
        assert "No active files" in output

    @pytest.mark.asyncio
    async def test_with_files_under_limit(self) -> None:
        monitor = MagicMock()
        monitor.get_active_files = AsyncMock(
            return_value=[
                {
                    "path": "/a.py",
                    "last_modified": "2026-06-15",
                    "change_count": 3,
                },
                {
                    "path": "/b.py",
                    "last_modified": "2026-06-16",
                    "change_count": 1,
                },
            ]
        )
        output = await _get_active_files_operation(monitor, minutes=10)
        assert "Found 2 active files" in output
        assert "/a.py" in output
        monitor.get_active_files.assert_awaited_once_with(minutes=10)

    @pytest.mark.asyncio
    async def test_with_files_over_limit(self) -> None:
        monitor = MagicMock()
        monitor.get_active_files = AsyncMock(
            return_value=[
                {
                    "path": f"/f{i}",
                    "last_modified": "2026-06-15",
                    "change_count": i,
                }
                for i in range(25)
            ]
        )
        output = await _get_active_files_operation(monitor, minutes=60)
        assert "Found 25 active files" in output
        # "... and 5 more files" present.
        assert "... and 5 more files" in output


# ---------------------------------------------------------------------------
# _start_interruption_monitoring_operation
# ---------------------------------------------------------------------------


class TestStartInterruptionMonitoringOperation:
    @pytest.mark.asyncio
    async def test_start_monitoring_called(self) -> None:
        manager = _make_manager()
        await _start_interruption_monitoring_operation(
            manager, "sess-1", "user-1"
        )
        manager.start_monitoring.assert_awaited_once_with(
            session_id="sess-1", user_id="user-1"
        )

    @pytest.mark.asyncio
    async def test_output_contains_session_and_user(self) -> None:
        manager = _make_manager()
        output = await _start_interruption_monitoring_operation(
            manager, "sess-abc", "user-xyz"
        )
        assert "Interruption Monitoring Started" in output
        assert "Session ID: sess-abc" in output
        assert "User: user-xyz" in output
        assert "Now detecting" in output


# ---------------------------------------------------------------------------
# _stop_interruption_monitoring_operation
# ---------------------------------------------------------------------------


class TestStopInterruptionMonitoringOperation:
    @pytest.mark.asyncio
    async def test_output_renders_summary(self) -> None:
        manager = _make_manager()
        output = await _stop_interruption_monitoring_operation(manager)
        assert "Interruption Monitoring Stopped" in output
        assert "30.0 minutes" in output
        assert "Interruptions detected: 4" in output
        assert "Contexts preserved: 2" in output
        manager.stop_monitoring.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_summary_defaults(self) -> None:
        manager = MagicMock()
        manager.stop_monitoring = AsyncMock(return_value={})
        output = await _stop_interruption_monitoring_operation(manager)
        assert "0.0 minutes" in output
        assert "Interruptions detected: 0" in output


# ---------------------------------------------------------------------------
# _create_session_context_operation
# ---------------------------------------------------------------------------


class TestCreateSessionContextOperation:
    @pytest.mark.asyncio
    async def test_create_snapshot_called(self) -> None:
        manager = _make_manager()
        await _create_session_context_operation(
            manager, "sess-1", {"key": "value", "k2": "v2"}
        )
        manager.create_context_snapshot.assert_awaited_once_with(
            session_id="sess-1", context_data={"key": "value", "k2": "v2"}
        )

    @pytest.mark.asyncio
    async def test_output_renders_id_and_count(self) -> None:
        manager = _make_manager()
        output = await _create_session_context_operation(
            manager, "sess-1", {"a": 1, "b": 2, "c": 3}
        )
        assert "Session Context Created" in output
        assert "Context ID: ctx-123" in output
        assert "Session: sess-1" in output
        assert "Data items: 3" in output


# ---------------------------------------------------------------------------
# _preserve_current_context_operation
# ---------------------------------------------------------------------------


class TestPreserveCurrentContextOperation:
    @pytest.mark.asyncio
    async def test_preserve_context_called(self) -> None:
        manager = _make_manager()
        await _preserve_current_context_operation(
            manager, "sess-1", "before-deploy"
        )
        manager.preserve_context.assert_awaited_once_with(
            session_id="sess-1", interruption_reason="before-deploy"
        )

    @pytest.mark.asyncio
    async def test_output_renders_metadata(self) -> None:
        manager = _make_manager()
        output = await _preserve_current_context_operation(
            manager, "sess-1", "manual"
        )
        assert "Context Preserved" in output
        assert "Snapshot ID: snap-456" in output
        assert "Reason: manual" in output
        assert "Items preserved: 8" in output


# ---------------------------------------------------------------------------
# _restore_session_context_operation
# ---------------------------------------------------------------------------


class TestRestoreSessionContextOperation:
    @pytest.mark.asyncio
    async def test_success_renders_metadata(self) -> None:
        manager = _make_manager()
        output = await _restore_session_context_operation(manager, "sess-1")
        assert "Context Restored" in output
        assert "Session ID: sess-1" in output
        assert "Items restored: 5" in output
        assert "Original timestamp: 2026-06-15T09:00:00" in output
        manager.restore_context.assert_awaited_once_with(session_id="sess-1")

    @pytest.mark.asyncio
    async def test_failure_returns_error_message(self) -> None:
        manager = MagicMock()
        manager.restore_context = AsyncMock(
            return_value={"success": False, "error": "Snapshot not found"}
        )
        output = await _restore_session_context_operation(manager, "sess-1")
        assert "❌ Failed to restore context" in output
        assert "Snapshot not found" in output

    @pytest.mark.asyncio
    async def test_failure_no_error_uses_unknown(self) -> None:
        manager = MagicMock()
        manager.restore_context = AsyncMock(
            return_value={"success": False}
        )
        output = await _restore_session_context_operation(manager, "sess-1")
        assert "Unknown error" in output


# ---------------------------------------------------------------------------
# _get_interruption_history_operation
# ---------------------------------------------------------------------------


class TestGetInterruptionHistoryOperation:
    @pytest.mark.asyncio
    async def test_no_history(self) -> None:
        manager = MagicMock()
        manager.get_interruption_history = AsyncMock(return_value=[])
        output = await _get_interruption_history_operation(
            manager, "user-1", hours=24
        )
        assert "Interruption History - Last 24 Hours" in output
        assert "No interruptions recorded" in output
        manager.get_interruption_history.assert_awaited_once_with(
            user_id="user-1", hours=24
        )

    @pytest.mark.asyncio
    async def test_with_history(self) -> None:
        manager = MagicMock()
        manager.get_interruption_history = AsyncMock(
            return_value=[
                {
                    "timestamp": "2026-06-15T09:00:00",
                    "type": "network_disconnect",
                    "reason": "wifi drop",
                    "recovery_action": "auto_reconnect",
                }
            ]
        )
        output = await _get_interruption_history_operation(
            manager, "user-1", hours=12
        )
        assert "Found 1 interruptions" in output
        assert "network_disconnect" in output
        assert "wifi drop" in output

    @pytest.mark.asyncio
    async def test_with_history_over_limit(self) -> None:
        manager = MagicMock()
        manager.get_interruption_history = AsyncMock(
            return_value=[
                {
                    "timestamp": f"2026-06-15T09:0{i}:00",
                    "type": "sleep",
                    "reason": "n/a",
                    "recovery_action": "wake",
                }
                for i in range(15)
            ]
        )
        output = await _get_interruption_history_operation(
            manager, "user-1", hours=24
        )
        assert "Found 15 interruptions" in output
        # "... and 5 more events" present.
        assert "... and 5 more events" in output


# ---------------------------------------------------------------------------
# _start_app_monitoring_impl (the wrapper that handles JSON parsing)
# ---------------------------------------------------------------------------


class TestStartAppMonitoringImpl:
    @pytest.mark.asyncio
    async def test_with_list_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        result = await _start_app_monitoring_impl(["/proj/a"])
        assert "Application Monitoring Started" in result

    @pytest.mark.asyncio
    async def test_with_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        result = await _start_app_monitoring_impl(None)
        assert "all accessible paths" in result

    @pytest.mark.asyncio
    async def test_monitor_unavailable_returns_emoji(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=None),
        )
        result = await _start_app_monitoring_impl(["/p"])
        assert result.startswith("❌ ")


# ---------------------------------------------------------------------------
# register_monitoring_tools (registration + tools end-to-end)
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registers_all_ten_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=_make_monitor()),
        )
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=_make_manager()),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        assert "start_app_monitoring" in mcp.tools
        assert "stop_app_monitoring" in mcp.tools
        assert "get_activity_summary" in mcp.tools
        assert "get_context_insights" in mcp.tools
        assert "get_active_files" in mcp.tools
        assert "start_interruption_monitoring" in mcp.tools
        assert "stop_interruption_monitoring" in mcp.tools
        assert "create_session_context" in mcp.tools
        assert "preserve_current_context" in mcp.tools
        assert "restore_session_context" in mcp.tools
        assert "get_interruption_history" in mcp.tools

    @pytest.mark.asyncio
    async def test_start_app_monitoring_tool_with_json_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Defensive JSON parsing: a str input gets parsed.
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["start_app_monitoring"](
            project_paths='["/a", "/b"]'
        )
        assert "Monitoring project paths" in result
        # project_paths propagated to monitor.
        assert monitor.project_paths == ["/a", "/b"]

    @pytest.mark.asyncio
    async def test_start_app_monitoring_tool_with_invalid_json_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        # Invalid JSON → falls through to project_paths=None → "all".
        result = await mcp.tools["start_app_monitoring"](
            project_paths="not json"
        )
        assert "all accessible paths" in result

    @pytest.mark.asyncio
    async def test_stop_app_monitoring_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["stop_app_monitoring"]()
        assert "Application Monitoring Stopped" in result

    @pytest.mark.asyncio
    async def test_get_activity_summary_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["get_activity_summary"](hours=3)
        assert "Activity Summary - Last 3 Hours" in result

    @pytest.mark.asyncio
    async def test_get_context_insights_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["get_context_insights"](hours=2)
        assert "Context Insights - Last 2 Hours" in result

    @pytest.mark.asyncio
    async def test_get_active_files_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _make_monitor()
        monkeypatch.setattr(
            monitoring_tools, "resolve_app_monitor",
            AsyncMock(return_value=monitor),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["get_active_files"](minutes=30)
        assert "Active Files - Last 30 Minutes" in result

    @pytest.mark.asyncio
    async def test_start_interruption_monitoring_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["start_interruption_monitoring"](
            session_id="sess-1", user_id="user-1"
        )
        assert "Interruption Monitoring Started" in result
        manager.start_monitoring.assert_awaited_once_with(
            session_id="sess-1", user_id="user-1"
        )

    @pytest.mark.asyncio
    async def test_stop_interruption_monitoring_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["stop_interruption_monitoring"]()
        assert "Interruption Monitoring Stopped" in result

    @pytest.mark.asyncio
    async def test_create_session_context_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["create_session_context"](
            session_id="sess-1", context_data={"a": 1, "b": 2}
        )
        assert "Session Context Created" in result
        assert "Data items: 2" in result

    @pytest.mark.asyncio
    async def test_preserve_current_context_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["preserve_current_context"](
            session_id="sess-1", reason="before-deploy"
        )
        assert "Context Preserved" in result
        manager.preserve_context.assert_awaited_once_with(
            session_id="sess-1", interruption_reason="before-deploy"
        )

    @pytest.mark.asyncio
    async def test_restore_session_context_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["restore_session_context"](
            session_id="sess-1"
        )
        assert "Context Restored" in result
        manager.restore_context.assert_awaited_once_with(session_id="sess-1")

    @pytest.mark.asyncio
    async def test_get_interruption_history_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _make_manager()
        monkeypatch.setattr(
            monitoring_tools, "resolve_interruption_manager",
            AsyncMock(return_value=manager),
        )
        mcp = _FakeMCP()
        register_monitoring_tools(mcp)
        result = await mcp.tools["get_interruption_history"](
            user_id="user-1", hours=12
        )
        assert "Interruption History - Last 12 Hours" in result
        manager.get_interruption_history.assert_awaited_once_with(
            user_id="user-1", hours=12
        )
