"""Tests for session_buddy.mcp.tools.monitoring.prometheus_metrics_tools.

Covers the Prometheus metrics MCP tool registration:
- ``_collect_session_start_total``: ``_total``-suffixed sample counted,
  non-``_total`` skipped, integer coercion
- ``_collect_session_end_total``: same pattern; status="error" branch
  is a no-op (already counted in total)
- ``_collect_active_sessions``: component_name labels extracted,
  default "unknown"
- ``_collect_session_quality_score``: component_name labels extracted,
  float coercion, default "unknown"
- ``_collect_mcp_event_emit_success_total``: ``_total``-suffixed sample
  counted
- ``_collect_mcp_event_emit_failure_total``: same pattern
- ``register_prometheus_metrics_tools``:
    - registers all three public tools (``get_prometheus_metrics``,
      ``list_session_metrics``, ``get_metrics_summary``)
    - logs a warning + registers an error-returning tool when
      ``METRICS_AVAILABLE`` is False
    - logs info message on success
- ``get_prometheus_metrics`` (the tool, invoked through a fake MCP):
    - returns static error string when ``METRICS_AVAILABLE`` is False
    - concatenates ``export_metrics()`` + ``generate_latest(REGISTRY)``
      when ``METRICS_AVAILABLE`` is True
    - exception path returns "# Error exporting metrics: see server logs"
- ``get_metrics_summary`` (the tool, invoked through a fake MCP):
    - happy path populates every summary field via the collectors
    - exception path returns a fully-populated error-shaped dict
- ``list_session_metrics`` (the tool): returns the static 3-section
  catalog with expected metric keys/types/labels
- ``__all__`` exports

The collectors are exercised directly using ``SimpleNamespace``-built
fake metrics that mimic ``SessionMetrics``' surface. The tool
registration uses a fake MCP that captures ``tool()`` decorators so
the registered functions can be invoked in isolation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.mcp.tools.monitoring import prometheus_metrics_tools
from session_buddy.mcp.tools.monitoring.prometheus_metrics_tools import (
    _collect_active_sessions,
    _collect_mcp_event_emit_failure_total,
    _collect_mcp_event_emit_success_total,
    _collect_session_end_total,
    _collect_session_quality_score,
    _collect_session_start_total,
    get_prometheus_tools_logger,
    register_prometheus_metrics_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metric(samples: list[SimpleNamespace]) -> SimpleNamespace:
    """Build a fake ``metric`` object with the given samples."""
    return SimpleNamespace(samples=samples)


def _make_metrics(
    *,
    session_start_total: list[SimpleNamespace] | None = None,
    session_end_total: list[SimpleNamespace] | None = None,
    active_sessions: list[SimpleNamespace] | None = None,
    session_quality_score: list[SimpleNamespace] | None = None,
    mcp_event_emit_success_total: list[SimpleNamespace] | None = None,
    mcp_event_emit_failure_total: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    """Build a fake ``metrics`` object with the given sample lists.

    Each attribute maps to a list of "metric" objects whose ``collect()``
    returns a list of samples. A None defaults to an empty metric.
    """

    def _make_attr(samples):
        m = MagicMock()

        def _collect():
            return [_make_metric(samples)]

        m.collect = _collect
        return m

    return SimpleNamespace(
        session_start_total=_make_attr(session_start_total or []),
        session_end_total=_make_attr(session_end_total or []),
        active_sessions=_make_attr(active_sessions or []),
        session_quality_score=_make_attr(session_quality_score or []),
        mcp_event_emit_success_total=_make_attr(
            mcp_event_emit_success_total or []
        ),
        mcp_event_emit_failure_total=_make_attr(
            mcp_event_emit_failure_total or []
        ),
    )


class _FakeMCP:
    """Capture ``mcp.tool()`` decorators so registered functions can run."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            # Use the function's __name__ as the registration key so
            # multiple registrations with the same name (e.g. two
            # definitions of get_prometheus_metrics across the
            # METRICS_AVAILABLE branches) resolve to the last one.
            self.tools[fn.__name__] = fn
            return fn

        return decorator


# ---------------------------------------------------------------------------
# _collect_session_start_total
# ---------------------------------------------------------------------------


class TestCollectSessionStartTotal:
    def test_total_sample_counted(self) -> None:
        metrics = _make_metrics(
            session_start_total=[
                SimpleNamespace(name="session_start_total", value=42),
            ]
        )
        summary: dict = {"total_sessions_started": 0}
        _collect_session_start_total(metrics, summary)
        assert summary["total_sessions_started"] == 42

    def test_non_total_sample_skipped(self) -> None:
        metrics = _make_metrics(
            session_start_total=[
                SimpleNamespace(name="session_start_created", value=999),
            ]
        )
        summary: dict = {"total_sessions_started": 0}
        _collect_session_start_total(metrics, summary)
        assert summary["total_sessions_started"] == 0

    def test_multiple_samples_summed(self) -> None:
        metrics = _make_metrics(
            session_start_total=[
                SimpleNamespace(name="session_start_total", value=10),
                SimpleNamespace(name="session_start_total", value=5),
            ]
        )
        summary: dict = {"total_sessions_started": 0}
        _collect_session_start_total(metrics, summary)
        assert summary["total_sessions_started"] == 15

    def test_float_value_coerced_to_int(self) -> None:
        metrics = _make_metrics(
            session_start_total=[
                SimpleNamespace(name="session_start_total", value=7.9),
            ]
        )
        summary: dict = {"total_sessions_started": 0}
        _collect_session_start_total(metrics, summary)
        # int() truncates toward zero (7.9 → 7), but the call must
        # produce an int.
        assert summary["total_sessions_started"] == 7
        assert isinstance(summary["total_sessions_started"], int)


# ---------------------------------------------------------------------------
# _collect_session_end_total
# ---------------------------------------------------------------------------


class TestCollectSessionEndTotal:
    def test_total_sample_counted(self) -> None:
        metrics = _make_metrics(
            session_end_total=[
                SimpleNamespace(
                    name="session_end_total",
                    value=100,
                    labels={"status": "ok"},
                ),
            ]
        )
        summary: dict = {"total_sessions_ended": 0}
        _collect_session_end_total(metrics, summary)
        assert summary["total_sessions_ended"] == 100

    def test_error_status_branch_is_noop(self) -> None:
        # The function checks labels.get("status") == "error" but takes
        # no action — it must still count the sample's value.
        metrics = _make_metrics(
            session_end_total=[
                SimpleNamespace(
                    name="session_end_total",
                    value=3,
                    labels={"status": "error"},
                ),
            ]
        )
        summary: dict = {"total_sessions_ended": 0}
        _collect_session_end_total(metrics, summary)
        assert summary["total_sessions_ended"] == 3

    def test_missing_labels_safe(self) -> None:
        # No labels at all → labels.get("status") returns None → branch
        # skipped, value still counted.
        metrics = _make_metrics(
            session_end_total=[
                SimpleNamespace(name="session_end_total", value=11, labels=None),
            ]
        )
        summary: dict = {"total_sessions_ended": 0}
        _collect_session_end_total(metrics, summary)
        assert summary["total_sessions_ended"] == 11

    def test_non_total_sample_skipped(self) -> None:
        # NOTE: production code at line 69 accesses ``sample.labels``
        # unconditionally (not guarded by the ``endswith("_total")``
        # check above). Real Prometheus samples always carry a
        # ``.labels`` attribute (empty dict when no labels are defined),
        # so this test mirrors that realistic sample shape.
        metrics = _make_metrics(
            session_end_total=[
                SimpleNamespace(name="session_end_created", value=999, labels={}),
            ]
        )
        summary: dict = {"total_sessions_ended": 0}
        _collect_session_end_total(metrics, summary)
        assert summary["total_sessions_ended"] == 0


# ---------------------------------------------------------------------------
# _collect_active_sessions
# ---------------------------------------------------------------------------


class TestCollectActiveSessions:
    def test_label_extracted(self) -> None:
        metrics = _make_metrics(
            active_sessions=[
                SimpleNamespace(
                    name="active_sessions",
                    value=5,
                    labels={"component_name": "mahavishnu"},
                ),
            ]
        )
        summary: dict = {"active_sessions": {}}
        _collect_active_sessions(metrics, summary)
        assert summary["active_sessions"] == {"mahavishnu": 5}

    def test_default_unknown_when_no_label(self) -> None:
        metrics = _make_metrics(
            active_sessions=[
                SimpleNamespace(name="active_sessions", value=2, labels=None),
            ]
        )
        summary: dict = {"active_sessions": {}}
        _collect_active_sessions(metrics, summary)
        assert summary["active_sessions"] == {"unknown": 2}

    def test_default_unknown_when_label_missing_key(self) -> None:
        # Labels exist but no component_name key → defaults to "unknown".
        metrics = _make_metrics(
            active_sessions=[
                SimpleNamespace(
                    name="active_sessions",
                    value=3,
                    labels={"other": "x"},
                ),
            ]
        )
        summary: dict = {"active_sessions": {}}
        _collect_active_sessions(metrics, summary)
        assert summary["active_sessions"] == {"unknown": 3}

    def test_multiple_components(self) -> None:
        metrics = _make_metrics(
            active_sessions=[
                SimpleNamespace(
                    name="active_sessions",
                    value=4,
                    labels={"component_name": "mahavishnu"},
                ),
                SimpleNamespace(
                    name="active_sessions",
                    value=7,
                    labels={"component_name": "session-buddy"},
                ),
            ]
        )
        summary: dict = {"active_sessions": {}}
        _collect_active_sessions(metrics, summary)
        assert summary["active_sessions"] == {"mahavishnu": 4, "session-buddy": 7}


# ---------------------------------------------------------------------------
# _collect_session_quality_score
# ---------------------------------------------------------------------------


class TestCollectSessionQualityScore:
    def test_float_value_stored(self) -> None:
        metrics = _make_metrics(
            session_quality_score=[
                SimpleNamespace(
                    name="session_quality_score",
                    value=92.5,
                    labels={"component_name": "mahavishnu"},
                ),
            ]
        )
        summary: dict = {"quality_scores": {}}
        _collect_session_quality_score(metrics, summary)
        assert summary["quality_scores"] == {"mahavishnu": 92.5}

    def test_default_unknown(self) -> None:
        metrics = _make_metrics(
            session_quality_score=[
                SimpleNamespace(name="session_quality_score", value=80.0, labels=None),
            ]
        )
        summary: dict = {"quality_scores": {}}
        _collect_session_quality_score(metrics, summary)
        assert summary["quality_scores"] == {"unknown": 80.0}

    def test_int_value_coerced_to_float(self) -> None:
        # Even an int value is coerced via float().
        metrics = _make_metrics(
            session_quality_score=[
                SimpleNamespace(
                    name="session_quality_score",
                    value=85,
                    labels={"component_name": "x"},
                ),
            ]
        )
        summary: dict = {"quality_scores": {}}
        _collect_session_quality_score(metrics, summary)
        assert summary["quality_scores"] == {"x": 85.0}
        assert isinstance(summary["quality_scores"]["x"], float)


# ---------------------------------------------------------------------------
# _collect_mcp_event_emit_success_total
# ---------------------------------------------------------------------------


class TestCollectMcpEventEmitSuccessTotal:
    def test_total_sample_counted(self) -> None:
        metrics = _make_metrics(
            mcp_event_emit_success_total=[
                SimpleNamespace(name="mcp_event_emit_success_total", value=12),
            ]
        )
        summary: dict = {"mcp_events_success": 0}
        _collect_mcp_event_emit_success_total(metrics, summary)
        assert summary["mcp_events_success"] == 12

    def test_non_total_sample_skipped(self) -> None:
        metrics = _make_metrics(
            mcp_event_emit_success_total=[
                SimpleNamespace(name="mcp_event_emit_success_created", value=999),
            ]
        )
        summary: dict = {"mcp_events_success": 0}
        _collect_mcp_event_emit_success_total(metrics, summary)
        assert summary["mcp_events_success"] == 0


# ---------------------------------------------------------------------------
# _collect_mcp_event_emit_failure_total
# ---------------------------------------------------------------------------


class TestCollectMcpEventEmitFailureTotal:
    def test_total_sample_counted(self) -> None:
        metrics = _make_metrics(
            mcp_event_emit_failure_total=[
                SimpleNamespace(name="mcp_event_emit_failure_total", value=4),
            ]
        )
        summary: dict = {"mcp_events_failure": 0}
        _collect_mcp_event_emit_failure_total(metrics, summary)
        assert summary["mcp_events_failure"] == 4

    def test_non_total_sample_skipped(self) -> None:
        metrics = _make_metrics(
            mcp_event_emit_failure_total=[
                SimpleNamespace(name="mcp_event_emit_failure_created", value=999),
            ]
        )
        summary: dict = {"mcp_events_failure": 0}
        _collect_mcp_event_emit_failure_total(metrics, summary)
        assert summary["mcp_events_failure"] == 0


# ---------------------------------------------------------------------------
# get_prometheus_tools_logger
# ---------------------------------------------------------------------------


class TestGetPrometheusToolsLogger:
    def test_returns_named_logger(self) -> None:
        logger = get_prometheus_tools_logger()
        assert logger.name == prometheus_metrics_tools.__name__


# ---------------------------------------------------------------------------
# register_prometheus_metrics_tools — METRICS_AVAILABLE = True
# ---------------------------------------------------------------------------


class TestRegisterPrometheusMetricsTools:
    def test_registers_all_tools_when_metrics_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            prometheus_metrics_tools, "METRICS_AVAILABLE", True, raising=False
        )
        mcp = _FakeMCP()
        register_prometheus_metrics_tools(mcp)
        # All three tools registered.
        assert "get_prometheus_metrics" in mcp.tools
        assert "list_session_metrics" in mcp.tools
        assert "get_metrics_summary" in mcp.tools

    def test_registers_warning_and_error_tool_when_metrics_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            prometheus_metrics_tools, "METRICS_AVAILABLE", False, raising=False
        )
        mcp = _FakeMCP()
        with caplog.at_level("WARNING", logger=prometheus_metrics_tools.__name__):
            register_prometheus_metrics_tools(mcp)
        # Still registers three tools (the no-op variant of
        # get_prometheus_metrics).
        assert "get_prometheus_metrics" in mcp.tools
        assert "list_session_metrics" in mcp.tools
        assert "get_metrics_summary" in mcp.tools
        # The warning was emitted.
        assert any(
            "Prometheus metrics not available" in record.message
            for record in caplog.records
        )

    def test_logs_info_on_success(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            prometheus_metrics_tools, "METRICS_AVAILABLE", True, raising=False
        )
        mcp = _FakeMCP()
        with caplog.at_level("INFO", logger=prometheus_metrics_tools.__name__):
            register_prometheus_metrics_tools(mcp)
        assert any(
            "registered successfully" in record.message for record in caplog.records
        )


# ---------------------------------------------------------------------------
# get_prometheus_metrics (the tool, both METRICS_AVAILABLE branches)
# ---------------------------------------------------------------------------


class TestGetPrometheusMetrics:
    @pytest.mark.asyncio
    async def test_returns_error_string_when_metrics_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            prometheus_metrics_tools, "METRICS_AVAILABLE", False, raising=False
        )
        mcp = _FakeMCP()
        register_prometheus_metrics_tools(mcp)
        tool = mcp.tools["get_prometheus_metrics"]
        result = await tool()
        assert "Error" in result
        assert "Prometheus metrics module not available" in result

    @pytest.mark.asyncio
    async def test_concatenates_session_and_conscious_data_when_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            prometheus_metrics_tools, "METRICS_AVAILABLE", True, raising=False
        )
        # ``get_metrics`` is closed over at module-import time, so we
        # patch the symbol on the prometheus_metrics_tools module —
        # patching ``session_buddy.mcp.metrics.get_metrics`` would
        # leave the closure pointing at the unpatched function.
        fake_metrics = MagicMock()
        fake_metrics.export_metrics.return_value = b"# session data\n"
        monkeypatch.setattr(
            prometheus_metrics_tools,
            "get_metrics",
            lambda: fake_metrics,
        )

        # The lazy ``from prometheus_client import REGISTRY, generate_latest``
        # inside the tool body resolves symbols on the real
        # ``prometheus_client`` module — patch them in place.
        import prometheus_client

        monkeypatch.setattr(
            prometheus_client, "generate_latest", lambda _registry: b"# conscious data\n"
        )

        mcp = _FakeMCP()
        register_prometheus_metrics_tools(mcp)
        tool = mcp.tools["get_prometheus_metrics"]

        result = await tool()

        # Both halves are concatenated.
        assert "# session data" in result
        assert "# conscious data" in result

    @pytest.mark.asyncio
    async def test_returns_error_comment_on_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            prometheus_metrics_tools, "METRICS_AVAILABLE", True, raising=False
        )
        mcp = _FakeMCP()
        register_prometheus_metrics_tools(mcp)
        tool = mcp.tools["get_prometheus_metrics"]

        # Force get_metrics() to raise.
        def boom():
            raise RuntimeError("metrics unavailable")

        monkeypatch.setattr(
            prometheus_metrics_tools,
            "get_metrics",
            boom,
        )

        result = await tool()
        assert "Error exporting metrics" in result


# ---------------------------------------------------------------------------
# get_metrics_summary (the tool)
# ---------------------------------------------------------------------------


class TestGetMetricsSummary:
    @pytest.mark.asyncio
    async def test_happy_path_populates_all_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            prometheus_metrics_tools, "METRICS_AVAILABLE", True, raising=False
        )
        # Build a metrics object whose collectors yield meaningful data.
        metrics = _make_metrics(
            session_start_total=[
                SimpleNamespace(name="session_start_total", value=10),
            ],
            session_end_total=[
                SimpleNamespace(
                    name="session_end_total",
                    value=8,
                    labels={"status": "ok"},
                ),
            ],
            active_sessions=[
                SimpleNamespace(
                    name="active_sessions",
                    value=2,
                    labels={"component_name": "mahavishnu"},
                ),
            ],
            session_quality_score=[
                SimpleNamespace(
                    name="session_quality_score",
                    value=88.5,
                    labels={"component_name": "mahavishnu"},
                ),
            ],
            mcp_event_emit_success_total=[
                SimpleNamespace(name="mcp_event_emit_success_total", value=3),
            ],
            mcp_event_emit_failure_total=[
                SimpleNamespace(name="mcp_event_emit_failure_total", value=1),
            ],
        )
        monkeypatch.setattr(
            prometheus_metrics_tools,
            "get_metrics",
            lambda: metrics,
        )

        mcp = _FakeMCP()
        register_prometheus_metrics_tools(mcp)
        tool = mcp.tools["get_metrics_summary"]

        result = await tool()
        assert result["total_sessions_started"] == 10
        assert result["total_sessions_ended"] == 8
        assert result["active_sessions"] == {"mahavishnu": 2}
        assert result["quality_scores"] == {"mahavishnu": 88.5}
        assert result["mcp_events_success"] == 3
        assert result["mcp_events_failure"] == 1

    @pytest.mark.asyncio
    async def test_exception_returns_error_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            prometheus_metrics_tools, "METRICS_AVAILABLE", True, raising=False
        )

        def boom():
            raise RuntimeError("metrics broken")

        monkeypatch.setattr(
            prometheus_metrics_tools,
            "get_metrics",
            boom,
        )

        mcp = _FakeMCP()
        register_prometheus_metrics_tools(mcp)
        tool = mcp.tools["get_metrics_summary"]

        result = await tool()
        assert result["error"] == "metrics broken"
        # All zero-valued defaults preserved.
        assert result["total_sessions_started"] == 0
        assert result["total_sessions_ended"] == 0
        assert result["active_sessions"] == {}
        assert result["quality_scores"] == {}
        assert result["mcp_events_success"] == 0
        assert result["mcp_events_failure"] == 0


# ---------------------------------------------------------------------------
# list_session_metrics (the tool)
# ---------------------------------------------------------------------------


class TestListSessionMetrics:
    @pytest.mark.asyncio
    async def test_returns_expected_sections(self) -> None:
        mcp = _FakeMCP()
        register_prometheus_metrics_tools(mcp)
        tool = mcp.tools["list_session_metrics"]

        result = await tool()
        assert set(result.keys()) == {
            "session_lifecycle_metrics",
            "mcp_event_metrics",
            "system_health_metrics",
        }

        # Lifecycle section.
        lifecycle = result["session_lifecycle_metrics"]
        assert "session_start_total" in lifecycle
        assert lifecycle["session_start_total"]["type"] == "Counter"
        assert "session_end_total" in lifecycle
        assert "session_duration_seconds" in lifecycle
        assert lifecycle["session_duration_seconds"]["type"] == "Histogram"

        # MCP events section.
        mcp_events = result["mcp_event_metrics"]
        assert "mcp_event_emit_success_total" in mcp_events
        assert "mcp_event_emit_failure_total" in mcp_events
        assert "mcp_event_emit_duration_seconds" in mcp_events

        # System health section.
        health = result["system_health_metrics"]
        assert "active_sessions" in health
        assert health["active_sessions"]["type"] == "Gauge"
        assert "session_quality_score" in health
        assert health["session_quality_score"]["type"] == "Gauge"


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


class TestExports:
    def test_all_exports(self) -> None:
        assert "register_prometheus_metrics_tools" in (
            prometheus_metrics_tools.__all__
        )
