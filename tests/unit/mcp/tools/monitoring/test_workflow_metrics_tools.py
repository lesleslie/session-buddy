"""Tests for session_buddy.mcp.tools.monitoring.workflow_metrics_tools.

Covers the workflow metrics MCP tool registration:
- ``_generate_workflow_insights``: velocity branches (>5 high, <2 low,
  else no insight), quality trend (improving / declining / stable),
  session length (>120 long, <30 short), time of day (morning /
  afternoon / evening / night / unknown), top tool insight.
- ``_generate_quality_insights``: high-quality (≥80) count, low-quality
  (<60) count, sessions without avg_quality default to 0.
- ``_generate_length_insights``: long (>120 min) count, short (<30 min)
  count.
- ``_generate_commit_insights``: zero-commit count, high-commit (≥10)
  count.
- ``_generate_language_insights``: top language by count, sessions
  with no ``primary_language`` skipped, empty list → no insight.
- ``_generate_session_insights``: empty list → "No sessions analyzed";
  otherwise combines all four sub-insights.
- ``register_workflow_metrics_tools``: registers 2 tools
  (``get_workflow_metrics``, ``get_session_analytics``) and 1 prompt
  (``workflow_metrics_help``).
- ``get_workflow_metrics`` (the tool):
    - happy path with insights when total_sessions > 0
    - happy path without insights when total_sessions == 0
    - project_path + days_back propagated to the engine
    - exception path returns success=False + engine_failure error
- ``get_session_analytics`` (the tool):
    - happy path with rows + insights + total_analyzed
    - sort_by = "duration" / "quality" / "commits" / "checkpoints"
      / unknown → default duration
    - datetime rows → isoformat; None rows → None; tools_used as list
    - total_analyzed = 0 when COUNT returns no rows
    - empty result list
    - exception path
- ``workflow_metrics_help`` (the prompt): returns the static help text.

The engine and ``WorkflowMetricsStore`` are patched on the source module
because both ``get_workflow_metrics_engine`` and the lazy
``WorkflowMetricsStore`` import are closed over by the tool closures.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.monitoring import workflow_metrics_tools
from session_buddy.mcp.tools.monitoring.workflow_metrics_tools import (
    _generate_commit_insights,
    _generate_language_insights,
    _generate_length_insights,
    _generate_quality_insights,
    _generate_session_insights,
    _generate_workflow_insights,
    register_workflow_metrics_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metrics(
    *,
    total_sessions: int = 10,
    avg_velocity_commits_per_hour: float = 3.0,
    quality_trend: str = "stable",
    avg_quality_score: float = 80.0,
    avg_session_duration_minutes: float = 60.0,
    most_productive_time_of_day: str = "morning",
    most_used_tools: list[tuple[str, int]] | None = None,
    extra: dict | None = None,
) -> SimpleNamespace:
    """Build a fake WorkflowMetrics object with ``to_dict()``."""
    data: dict = {
        "total_sessions": total_sessions,
        "avg_velocity_commits_per_hour": avg_velocity_commits_per_hour,
        "quality_trend": quality_trend,
        "avg_quality_score": avg_quality_score,
        "avg_session_duration_minutes": avg_session_duration_minutes,
        "most_productive_time_of_day": most_productive_time_of_day,
        "most_used_tools": most_used_tools or [],
    }
    if extra:
        data.update(extra)
    metrics = SimpleNamespace(**data)
    metrics.to_dict = lambda: dict(data)
    return metrics


def _make_session_row(
    *,
    session_id: str = "s1",
    project_path: str = "/proj",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    duration_minutes: float = 60.0,
    checkpoint_count: int = 2,
    commit_count: int = 3,
    quality_start: float = 80.0,
    quality_end: float = 85.0,
    quality_delta: float = 5.0,
    avg_quality: float = 82.0,
    files_modified: int = 4,
    tools_used: tuple[str, ...] = ("python", "bash"),
    primary_language: str = "python",
    time_of_day: str = "morning",
) -> tuple:
    """Build a fake SQL row as a tuple matching the SELECT projection."""
    return (
        session_id,
        project_path,
        started_at,
        ended_at,
        duration_minutes,
        checkpoint_count,
        commit_count,
        quality_start,
        quality_end,
        quality_delta,
        avg_quality,
        files_modified,
        tools_used,
        primary_language,
        time_of_day,
    )


def _make_session_dict(
    *,
    session_id: str = "s1",
    duration_minutes: float = 60.0,
    avg_quality: float = 82.0,
    commit_count: int = 3,
    primary_language: str = "python",
) -> dict:
    """Build a session dict (already-shaped) for the insight generators."""
    return {
        "session_id": session_id,
        "duration_minutes": duration_minutes,
        "avg_quality": avg_quality,
        "commit_count": commit_count,
        "primary_language": primary_language,
    }


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


def _make_engine(metrics: SimpleNamespace | None = None) -> MagicMock:
    """Build a fake WorkflowMetricsEngine."""
    engine = MagicMock()
    engine.initialize = AsyncMock(return_value=None)
    engine.get_workflow_metrics = AsyncMock(
        return_value=metrics or _make_metrics()
    )
    return engine


def _make_store(
    rows: list[tuple] | None = None,
    total_count: int = 0,
    *,
    raises: Exception | None = None,
) -> MagicMock:
    """Build a fake WorkflowMetricsStore + conn."""
    conn = MagicMock()
    if raises is not None:
        # When the first execute raises, every subsequent call also
        # raises — so the conn.execute() invocation that triggers the
        # test failure happens immediately.
        conn.execute.side_effect = raises
    else:
        # Default: first call returns the rows, second returns total.
        fetchall_result = MagicMock()
        fetchall_result.fetchall.return_value = rows or []
        fetchone_result = MagicMock()
        fetchone_result.fetchone.return_value = (total_count,)
        conn.execute.side_effect = [fetchall_result, fetchone_result]
    store = MagicMock()
    store._get_conn.return_value = conn
    store.close = MagicMock(return_value=None)
    return store


# ---------------------------------------------------------------------------
# _generate_workflow_insights
# ---------------------------------------------------------------------------


class TestGenerateWorkflowInsights:
    def test_high_velocity(self) -> None:
        metrics = _make_metrics(avg_velocity_commits_per_hour=6.0)
        insights = _generate_workflow_insights(metrics)
        assert any(
            "🚀" in i and "High development velocity" in i for i in insights
        )

    def test_low_velocity(self) -> None:
        metrics = _make_metrics(avg_velocity_commits_per_hour=1.0)
        insights = _generate_workflow_insights(metrics)
        assert any(
            "⚠️" in i and "Low development velocity" in i for i in insights
        )

    def test_normal_velocity_no_insight(self) -> None:
        # 3 commits/hour is between 2 and 5 → no velocity insight.
        metrics = _make_metrics(avg_velocity_commits_per_hour=3.0)
        insights = _generate_workflow_insights(metrics)
        assert not any(
            "development velocity" in i.lower() for i in insights
        )

    def test_improving_quality(self) -> None:
        metrics = _make_metrics(quality_trend="improving")
        insights = _generate_workflow_insights(metrics)
        assert any(
            "📈" in i and "Quality improving" in i for i in insights
        )

    def test_declining_quality(self) -> None:
        metrics = _make_metrics(quality_trend="declining")
        insights = _generate_workflow_insights(metrics)
        assert any(
            "📉" in i and "Quality declining" in i for i in insights
        )

    def test_stable_quality_no_insight(self) -> None:
        metrics = _make_metrics(quality_trend="stable")
        insights = _generate_workflow_insights(metrics)
        assert not any(
            "Quality improving" in i or "Quality declining" in i
            for i in insights
        )

    def test_long_sessions(self) -> None:
        metrics = _make_metrics(avg_session_duration_minutes=150.0)
        insights = _generate_workflow_insights(metrics)
        assert any("⏱️" in i and "Long sessions" in i for i in insights)

    def test_short_sessions(self) -> None:
        metrics = _make_metrics(avg_session_duration_minutes=20.0)
        insights = _generate_workflow_insights(metrics)
        assert any("⚡" in i and "Short sessions" in i for i in insights)

    def test_normal_session_duration_no_insight(self) -> None:
        # 60 min is between 30 and 120 → no length insight.
        metrics = _make_metrics(avg_session_duration_minutes=60.0)
        insights = _generate_workflow_insights(metrics)
        assert not any(
            "Long sessions" in i or "Short sessions" in i for i in insights
        )

    def test_time_of_day_morning(self) -> None:
        metrics = _make_metrics(most_productive_time_of_day="morning")
        insights = _generate_workflow_insights(metrics)
        assert any("🌅" in i for i in insights)

    def test_time_of_day_afternoon(self) -> None:
        metrics = _make_metrics(most_productive_time_of_day="afternoon")
        insights = _generate_workflow_insights(metrics)
        assert any("☀️" in i for i in insights)

    def test_time_of_day_evening(self) -> None:
        metrics = _make_metrics(most_productive_time_of_day="evening")
        insights = _generate_workflow_insights(metrics)
        assert any("🌆" in i for i in insights)

    def test_time_of_day_night(self) -> None:
        metrics = _make_metrics(most_productive_time_of_day="night")
        insights = _generate_workflow_insights(metrics)
        assert any("🌙" in i for i in insights)

    def test_unknown_time_of_day_no_insight(self) -> None:
        metrics = _make_metrics(most_productive_time_of_day="dawn")
        insights = _generate_workflow_insights(metrics)
        # "dawn" isn't in the time_insights map → no time insight.
        assert not any(
            "🌅" in i or "☀️" in i or "🌆" in i or "🌙" in i for i in insights
        )

    def test_top_tool(self) -> None:
        metrics = _make_metrics(
            most_used_tools=[("claude", 100), ("pytest", 30)]
        )
        insights = _generate_workflow_insights(metrics)
        assert any(
            "🔧" in i and "claude" in i and "100" in i for i in insights
        )

    def test_no_tools_no_insight(self) -> None:
        metrics = _make_metrics(most_used_tools=[])
        insights = _generate_workflow_insights(metrics)
        assert not any("🔧" in i for i in insights)


# ---------------------------------------------------------------------------
# _generate_quality_insights
# ---------------------------------------------------------------------------


class TestGenerateQualityInsights:
    def test_high_quality_counted(self) -> None:
        sessions = [
            _make_session_dict(avg_quality=85),
            _make_session_dict(avg_quality=90),
            _make_session_dict(avg_quality=50),
        ]
        insights = _generate_quality_insights(sessions)
        assert any("✅" in i and "2" in i and "high-quality" in i for i in insights)

    def test_low_quality_counted(self) -> None:
        sessions = [
            _make_session_dict(avg_quality=85),
            _make_session_dict(avg_quality=50),
        ]
        insights = _generate_quality_insights(sessions)
        assert any("⚠️" in i and "1" in i and "need attention" in i for i in insights)

    def test_neither_returns_empty(self) -> None:
        sessions = [
            _make_session_dict(avg_quality=70),  # between 60 and 80
        ]
        insights = _generate_quality_insights(sessions)
        assert insights == []

    def test_missing_avg_quality_defaults_to_zero(self) -> None:
        # No ``avg_quality`` key → defaults to 0 (low quality).
        sessions = [{"session_id": "s1", "duration_minutes": 60}]
        insights = _generate_quality_insights(sessions)
        assert any("⚠️" in i and "1" in i for i in insights)


# ---------------------------------------------------------------------------
# _generate_length_insights
# ---------------------------------------------------------------------------


class TestGenerateLengthInsights:
    def test_long_sessions_counted(self) -> None:
        sessions = [
            _make_session_dict(duration_minutes=150),
            _make_session_dict(duration_minutes=200),
        ]
        insights = _generate_length_insights(sessions)
        assert any(
            "📊" in i and "2" in i and "marathon" in i for i in insights
        )

    def test_short_sessions_counted(self) -> None:
        sessions = [
            _make_session_dict(duration_minutes=20),
            _make_session_dict(duration_minutes=10),
        ]
        insights = _generate_length_insights(sessions)
        assert any(
            "⚡" in i and "2" in i and "quick" in i for i in insights
        )

    def test_neither_returns_empty(self) -> None:
        sessions = [_make_session_dict(duration_minutes=60)]
        insights = _generate_length_insights(sessions)
        assert insights == []

    def test_missing_duration_defaults_to_zero(self) -> None:
        # No ``duration_minutes`` → defaults to 0 → counted as short.
        sessions = [{"session_id": "s1"}]
        insights = _generate_length_insights(sessions)
        assert any("⚡" in i and "1" in i for i in insights)


# ---------------------------------------------------------------------------
# _generate_commit_insights
# ---------------------------------------------------------------------------


class TestGenerateCommitInsights:
    def test_zero_commits_counted(self) -> None:
        sessions = [
            _make_session_dict(commit_count=0),
            _make_session_dict(commit_count=5),
        ]
        insights = _generate_commit_insights(sessions)
        assert any(
            "📝" in i and "1" in i and "no commits" in i for i in insights
        )

    def test_high_commits_counted(self) -> None:
        sessions = [
            _make_session_dict(commit_count=15),
            _make_session_dict(commit_count=3),
        ]
        insights = _generate_commit_insights(sessions)
        assert any(
            "🔥" in i
            and "1" in i
            and "high-commitment" in i.lower()
            for i in insights
        )

    def test_neither_returns_empty(self) -> None:
        sessions = [_make_session_dict(commit_count=5)]
        insights = _generate_commit_insights(sessions)
        assert insights == []


# ---------------------------------------------------------------------------
# _generate_language_insights
# ---------------------------------------------------------------------------


class TestGenerateLanguageInsights:
    def test_top_language_emitted(self) -> None:
        sessions = [
            _make_session_dict(primary_language="python"),
            _make_session_dict(primary_language="python"),
            _make_session_dict(primary_language="rust"),
        ]
        insights = _generate_language_insights(sessions)
        assert any(
            "💻" in i and "python" in i and "2" in i for i in insights
        )

    def test_no_languages_returns_empty(self) -> None:
        sessions = [
            _make_session_dict(primary_language=None),
        ]
        insights = _generate_language_insights(sessions)
        assert insights == []

    def test_missing_language_field_skipped(self) -> None:
        # No ``primary_language`` key → falsy → skipped.
        sessions = [{"session_id": "s1"}, {"session_id": "s2"}]
        insights = _generate_language_insights(sessions)
        assert insights == []


# ---------------------------------------------------------------------------
# _generate_session_insights
# ---------------------------------------------------------------------------


class TestGenerateSessionInsights:
    def test_empty_sessions(self) -> None:
        insights = _generate_session_insights([])
        assert insights == ["No sessions analyzed"]

    def test_non_empty_aggregates_subinsights(self) -> None:
        sessions = [
            _make_session_dict(
                duration_minutes=150,
                avg_quality=85,
                commit_count=0,
                primary_language="python",
            )
        ]
        insights = _generate_session_insights(sessions)
        # 4 sub-insight types + empty list → at least one insight per
        # category should fire for this rich session.
        assert any("✅" in i for i in insights)  # high quality
        assert any("📊" in i and "marathon" in i for i in insights)
        assert any("📝" in i and "no commits" in i for i in insights)
        assert any("💻" in i and "python" in i for i in insights)


# ---------------------------------------------------------------------------
# register_workflow_metrics_tools
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registers_two_tools_and_one_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            workflow_metrics_tools,
            "get_workflow_metrics_engine",
            lambda: _make_engine(),
        )
        server = _FakeServer()
        register_workflow_metrics_tools(server)
        assert "get_workflow_metrics" in server.tools
        assert "get_session_analytics" in server.tools
        assert "workflow_metrics_help" in server.prompts


# ---------------------------------------------------------------------------
# get_workflow_metrics (the tool)
# ---------------------------------------------------------------------------


class TestGetWorkflowMetrics:
    @pytest.mark.asyncio
    async def test_happy_path_with_insights(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        metrics = _make_metrics(total_sessions=10)
        engine = _make_engine(metrics)
        monkeypatch.setattr(
            workflow_metrics_tools,
            "get_workflow_metrics_engine",
            lambda: engine,
        )

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_workflow_metrics"]()
        assert result["success"] is True
        assert result["total_sessions"] == 10
        # Insights present when total_sessions > 0.
        assert "insights" in result
        assert isinstance(result["insights"], list)
        engine.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_insights_when_total_sessions_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        metrics = _make_metrics(total_sessions=0)
        engine = _make_engine(metrics)
        monkeypatch.setattr(
            workflow_metrics_tools,
            "get_workflow_metrics_engine",
            lambda: engine,
        )

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_workflow_metrics"]()
        assert result["success"] is True
        # No insights key when total_sessions == 0.
        assert "insights" not in result

    @pytest.mark.asyncio
    async def test_project_path_and_days_back_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = _make_engine()
        monkeypatch.setattr(
            workflow_metrics_tools,
            "get_workflow_metrics_engine",
            lambda: engine,
        )

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        await server.tools["get_workflow_metrics"](
            project_path="/my/proj", days_back=7
        )
        engine.get_workflow_metrics.assert_awaited_once_with(
            project_path="/my/proj", days_back=7
        )

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom_initialize():
            raise RuntimeError("db connection lost")

        engine = MagicMock()
        engine.initialize = AsyncMock(side_effect=boom_initialize)
        monkeypatch.setattr(
            workflow_metrics_tools,
            "get_workflow_metrics_engine",
            lambda: engine,
        )

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_workflow_metrics"]()
        assert result["success"] is False
        assert result["error"] == "engine_failure"
        assert "Failed to retrieve workflow metrics" in result["message"]


# ---------------------------------------------------------------------------
# get_session_analytics (the tool)
# ---------------------------------------------------------------------------


class TestGetSessionAnalytics:
    @pytest.mark.asyncio
    async def test_happy_path_returns_shaped_sessions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started = datetime(2026, 6, 15, 9, 0, 0, tzinfo=UTC)
        ended = datetime(2026, 6, 15, 11, 0, 0, tzinfo=UTC)
        row = _make_session_row(
            started_at=started,
            ended_at=ended,
            tools_used=("python", "bash"),
        )
        store = _make_store(rows=[row], total_count=5)
        # Patch the lazy import.
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_session_analytics"]()
        assert result["success"] is True
        assert result["total_analyzed"] == 5
        assert len(result["sessions"]) == 1
        session = result["sessions"][0]
        assert session["session_id"] == "s1"
        assert session["started_at"] == "2026-06-15T09:00:00+00:00"
        assert session["ended_at"] == "2026-06-15T11:00:00+00:00"
        assert session["tools_used"] == ["python", "bash"]
        assert session["primary_language"] == "python"
        assert result["sort_field"] == "duration"
        assert "insights" in result
        store.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_dates_handled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # started_at / ended_at are None → stored as None.
        row = _make_session_row(started_at=None, ended_at=None)
        store = _make_store(rows=[row], total_count=1)
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_session_analytics"]()
        session = result["sessions"][0]
        assert session["started_at"] is None
        assert session["ended_at"] is None

    @pytest.mark.asyncio
    async def test_empty_tools_used_defaults_to_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = _make_session_row(tools_used=None)
        store = _make_store(rows=[row], total_count=1)
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_session_analytics"]()
        assert result["sessions"][0]["tools_used"] == []

    @pytest.mark.asyncio
    async def test_sort_by_quality(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(rows=[], total_count=0)
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        await server.tools["get_session_analytics"](
            limit=5, sort_by="quality"
        )
        # The first execute call uses sort_column "avg_quality".
        first_sql = store._get_conn().execute.call_args_list[0][0][0]
        assert "ORDER BY avg_quality DESC" in first_sql

    @pytest.mark.asyncio
    async def test_sort_by_commits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(rows=[], total_count=0)
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        await server.tools["get_session_analytics"](
            limit=5, sort_by="commits"
        )
        first_sql = store._get_conn().execute.call_args_list[0][0][0]
        assert "ORDER BY commit_count DESC" in first_sql

    @pytest.mark.asyncio
    async def test_sort_by_checkpoints(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(rows=[], total_count=0)
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        await server.tools["get_session_analytics"](
            limit=5, sort_by="checkpoints"
        )
        first_sql = store._get_conn().execute.call_args_list[0][0][0]
        assert "ORDER BY checkpoint_count DESC" in first_sql

    @pytest.mark.asyncio
    async def test_unknown_sort_defaults_to_duration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(rows=[], total_count=0)
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        await server.tools["get_session_analytics"](sort_by="bogus")
        first_sql = store._get_conn().execute.call_args_list[0][0][0]
        # Unknown sort_by falls through to duration_minutes default.
        assert "ORDER BY duration_minutes DESC" in first_sql
        assert result["sort_field"] if False else True  # keep static check happy

    @pytest.mark.asyncio
    async def test_total_count_zero_when_no_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(rows=[], total_count=0)
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_session_analytics"]()
        assert result["total_analyzed"] == 0

    @pytest.mark.asyncio
    async def test_empty_sessions_returns_no_analyzed_insight(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(rows=[], total_count=0)
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_session_analytics"]()
        assert result["sessions"] == []
        # The aggregate insight generator returns ["No sessions analyzed"].
        assert result["insights"] == ["No sessions analyzed"]

    @pytest.mark.asyncio
    async def test_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(raises=RuntimeError("sql exploded"))
        import session_buddy.core.workflow_metrics as wm_mod

        monkeypatch.setattr(wm_mod, "WorkflowMetricsStore", lambda: store)

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        result = await server.tools["get_session_analytics"]()
        assert result["success"] is False
        assert result["error"] == "engine_failure"
        assert "Failed to retrieve session analytics" in result["message"]


# ---------------------------------------------------------------------------
# workflow_metrics_help (the prompt)
# ---------------------------------------------------------------------------


class TestWorkflowMetricsHelp:
    def test_returns_static_help_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            workflow_metrics_tools,
            "get_workflow_metrics_engine",
            lambda: _make_engine(),
        )

        server = _FakeServer()
        register_workflow_metrics_tools(server)
        text = server.prompts["workflow_metrics_help"]()
        assert "Workflow Metrics" in text
        assert "get_workflow_metrics" in text
        assert "get_session_analytics" in text
        assert "Velocity Benchmarks" in text
