"""Unit tests for metrics module.

Tests:
- SessionMetrics class
- get_metrics function
- track_operation_duration decorator
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.mcp.metrics import (
    SessionMetrics,
    get_metrics,
    track_operation_duration,
)


class TestSessionMetrics:
    """Tests for SessionMetrics class."""

    def test_init_creates_all_counters(self) -> None:
        """Test that __init__ creates all expected Prometheus metrics."""
        metrics = SessionMetrics()

        # Session lifecycle
        assert metrics.session_start_total is not None
        assert metrics.session_end_total is not None
        assert metrics.session_duration_seconds is not None

        # MCP event metrics
        assert metrics.mcp_event_emit_success_total is not None
        assert metrics.mcp_event_emit_failure_total is not None
        assert metrics.mcp_event_emit_duration_seconds is not None

        # System health
        assert metrics.active_sessions is not None
        assert metrics.session_quality_score is not None

    def test_init_with_custom_registry(self) -> None:
        """Test initialization with custom CollectorRegistry."""
        from prometheus_client.registry import CollectorRegistry

        registry = CollectorRegistry()
        metrics = SessionMetrics(registry=registry)

        assert metrics.registry is registry

    def test_record_session_start_increments_counter(self) -> None:
        """Test that record_session_start increments the counter."""
        metrics = SessionMetrics()

        metrics.record_session_start("test", "TestShell")

        # Verify counter incremented by checking internal value
        counter_value = metrics.session_start_total.labels(
            component_name="test", shell_type="TestShell"
        )._value._value

        assert counter_value == 1

    def test_record_session_start_increments_active_sessions(self) -> None:
        """Test that record_session_start increments active_sessions gauge."""
        metrics = SessionMetrics()

        metrics.record_session_start("test", "TestShell")

        # Gauge value is accessed via _value for MutexValue
        gauge_value = metrics.active_sessions.labels(component_name="test")._value._value

        assert gauge_value == 1

    def test_record_session_end_increments_counter(self) -> None:
        """Test that record_session_end increments the counter."""
        metrics = SessionMetrics()

        metrics.record_session_start("test", "TestShell")
        metrics.record_session_end("test", "success", duration_seconds=120.0)

        # Verify counter incremented
        counter_value = metrics.session_end_total.labels(
            component_name="test", status="success"
        )._value._value

        assert counter_value == 1

    def test_record_session_end_observes_duration(self) -> None:
        """Test that record_session_end observes session duration."""
        metrics = SessionMetrics()

        metrics.record_session_start("test", "TestShell")
        metrics.record_session_end("test", "success", duration_seconds=3600.0)

        # Duration histogram should have observed value via _sum._value
        duration_value = metrics.session_duration_seconds.labels(
            component_name="test"
        )._sum._value

        assert duration_value == 3600.0

    def test_record_session_end_without_duration(self) -> None:
        """Test that record_session_end works when duration is omitted."""
        metrics = SessionMetrics()

        metrics.record_session_start("test", "TestShell")
        metrics.record_session_end("test", "success", duration_seconds=None)

        counter_value = metrics.session_end_total.labels(
            component_name="test", status="success"
        )._value._value

        assert counter_value == 1

    def test_record_session_end_decrements_active_sessions(self) -> None:
        """Test that record_session_end decrements active_sessions gauge."""
        metrics = SessionMetrics()

        metrics.record_session_start("test", "TestShell")
        initial_active = metrics.active_sessions.labels(component_name="test")._value._value

        metrics.record_session_end("test", "success")

        new_active = metrics.active_sessions.labels(component_name="test")._value._value

        assert new_active == initial_active - 1

    def test_record_mcp_event_emit_success(self) -> None:
        """Test recording successful MCP event emission."""
        metrics = SessionMetrics()

        metrics.record_mcp_event_emit_success(
            component_name="test",
            event_type="session_start",
            duration_seconds=0.025,
        )

        # Verify counter incremented
        counter_value = metrics.mcp_event_emit_success_total.labels(
            component_name="test", event_type="session_start"
        )._value._value

        assert counter_value == 1

        # Verify duration observed via _sum._value
        duration_value = metrics.mcp_event_emit_duration_seconds.labels(
            component_name="test", event_type="session_start"
        )._sum._value

        assert duration_value == 0.025

    def test_record_mcp_event_emit_failure(self) -> None:
        """Test recording failed MCP event emission."""
        metrics = SessionMetrics()

        metrics.record_mcp_event_emit_failure(
            component_name="test",
            event_type="session_start",
            error_type="ConnectionError",
            duration_seconds=5.0,
        )

        # Verify counter incremented
        counter_value = metrics.mcp_event_emit_failure_total.labels(
            component_name="test", event_type="session_start", error_type="ConnectionError"
        )._value._value

        assert counter_value == 1

        # Verify duration observed via _sum._value
        duration_value = metrics.mcp_event_emit_duration_seconds.labels(
            component_name="test", event_type="session_start"
        )._sum._value

        assert duration_value == 5.0

    def test_set_session_quality_score(self) -> None:
        """Test setting session quality score gauge."""
        metrics = SessionMetrics()

        metrics.set_session_quality_score("test", 85.5)

        gauge_value = metrics.session_quality_score.labels(
            component_name="test"
        )._value._value

        assert gauge_value == 85.5

    def test_export_metrics(self) -> None:
        """Test exporting metrics in Prometheus text format."""
        metrics = SessionMetrics()

        metrics.record_session_start("test", "TestShell")

        exported = metrics.export_metrics()

        assert isinstance(exported, bytes)
        assert b"session_start_total" in exported

    def test_clear_metrics(self) -> None:
        """Test clearing all metrics."""
        metrics = SessionMetrics()

        # Record some data
        metrics.record_session_start("test", "TestShell")
        metrics.record_session_start("test2", "TestShell")

        # Clear metrics
        metrics.clear_metrics()

        # Counter should be reset
        counter_value = metrics.session_start_total.labels(
            component_name="test", shell_type="TestShell"
        )._value._value

        assert counter_value == 0


class TestGetMetrics:
    """Tests for get_metrics function."""

    def test_get_metrics_returns_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that get_metrics returns the same instance."""
        # Reset global metrics by patching the module-level variable
        import session_buddy.mcp.metrics as metrics_module

        monkeypatch.setattr(metrics_module, "_metrics", None)

        metrics1 = get_metrics()
        metrics2 = get_metrics()

        assert metrics1 is metrics2

    def test_get_metrics_returns_session_metrics_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that get_metrics returns a SessionMetrics instance."""
        import session_buddy.mcp.metrics as metrics_module

        monkeypatch.setattr(metrics_module, "_metrics", None)

        metrics = get_metrics()

        assert isinstance(metrics, SessionMetrics)


class TestTrackOperationDuration:
    """Tests for track_operation_duration decorator."""

    def test_sync_function_success(self) -> None:
        """Test decorator tracks successful sync function execution."""
        metrics = SessionMetrics()

        @track_operation_duration("test_operation", "test-component", metrics)
        def sync_function():
            return "result"

        result = sync_function()

        assert result == "result"

        # Verify success counter was incremented
        counter_value = metrics.mcp_event_emit_success_total.labels(
            component_name="test-component", event_type="test_operation"
        )._value._value

        assert counter_value == 1

    def test_sync_function_failure(self) -> None:
        """Test decorator tracks failed sync function execution."""
        metrics = SessionMetrics()

        @track_operation_duration("failing_operation", "test-component", metrics)
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()

        # Verify failure counter was incremented
        counter_value = metrics.mcp_event_emit_failure_total.labels(
            component_name="test-component",
            event_type="failing_operation",
            error_type="ValueError",
        )._value._value

        assert counter_value == 1

    @pytest.mark.asyncio
    async def test_async_function_success(self) -> None:
        """Test decorator tracks successful async function execution."""
        metrics = SessionMetrics()

        @track_operation_duration("async_operation", "test-component", metrics)
        async def async_function():
            return "async_result"

        result = await async_function()

        assert result == "async_result"

        # Verify success counter was incremented
        counter_value = metrics.mcp_event_emit_success_total.labels(
            component_name="test-component", event_type="async_operation"
        )._value._value

        assert counter_value == 1

    @pytest.mark.asyncio
    async def test_async_function_with_return_annotation_uses_async_wrapper(
        self,
    ) -> None:
        """Test that an annotated async function uses the async wrapper branch."""
        metrics = SessionMetrics()

        @track_operation_duration("annotated_async_operation", "test-component", metrics)
        async def annotated_async_function() -> str:
            return "annotated"

        result = await annotated_async_function()

        assert result == "annotated"

        counter_value = metrics.mcp_event_emit_success_total.labels(
            component_name="test-component",
            event_type="annotated_async_operation",
        )._value._value

        assert counter_value == 1

    @pytest.mark.asyncio
    async def test_async_function_failure(self) -> None:
        """Test decorator tracks failed async function execution."""
        metrics = SessionMetrics()

        @track_operation_duration("failing_async_operation", "test-component", metrics)
        async def failing_async_function() -> str:
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await failing_async_function()

        counter_value = metrics.mcp_event_emit_failure_total.labels(
            component_name="test-component",
            event_type="failing_async_operation",
            error_type="ValueError",
        )._value._value

        assert counter_value == 1


class TestMetricsModuleExports:
    """Tests for module-level exports."""

    def test_module_exports_correct_functions(self) -> None:
        """Test that __all__ contains expected items."""
        from session_buddy.mcp import metrics

        expected_exports = [
            "SessionMetrics",
            "get_metrics",
            "track_operation_duration",
        ]

        for export in expected_exports:
            assert export in metrics.__all__
            assert hasattr(metrics, export)
