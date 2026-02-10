"""Prometheus metrics for session tracking in Session-Buddy.

This module provides comprehensive Prometheus metrics for monitoring session
lifecycle, MCP event emission, and system performance. Metrics are exported
in Prometheus text format for scraping by Prometheus server.

Architecture:
    1. SessionMetrics class defines all Prometheus Counter/Histogram metrics
    2. SessionTracker integration records metrics during session operations
    3. MCP endpoint exposes metrics for Prometheus scraping
    4. Configuration controls metrics collection via environment variables

Example:
    >>> from session_buddy.mcp.metrics import SessionMetrics
    >>> from prometheus_client import generate_latest
    >>>
    >>> metrics = SessionMetrics()
    >>> metrics.record_session_start("mahavishnu", "MahavishnuShell")
    >>> metrics.record_session_end("mahavishnu", "success")
    >>>
    >>> # Export metrics for Prometheus
    >>> metrics_data = generate_latest()
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_client.registry import CollectorRegistry

try:
    from prometheus_client.exposition import choose_formatter
except ImportError:
    # prometheus_client < 0.20.0
    from prometheus_client.exposition import (
        CONTENT_TYPE_LATEST,
    )

    def choose_formatter(_: str) -> tuple[str, bytes]:
        """Compatibility wrapper for older prometheus_client versions."""
        return CONTENT_TYPE_LATEST, generate_latest()


def get_metrics_logger() -> logging.Logger:
    """Get the metrics logger instance.

    This function is used in tests for mocking purposes.
    """
    return logging.getLogger(__name__)


class SessionMetrics:
    """Prometheus metrics for session tracking in Session-Buddy.

    This class defines comprehensive metrics for monitoring session lifecycle,
    MCP event emission, and system performance. All metrics use proper labels
    for dimensional data and follow Prometheus best practices.

    Metrics Categories:
        - Session lifecycle (start, end, duration)
        - MCP event emission (success, failure, duration)
        - System health (active sessions, quality scores)
        - Performance (operation latencies)

    Attributes:
        registry: Prometheus CollectorRegistry for metrics isolation
        session_start_total: Counter for session start events
        session_end_total: Counter for session end events
        session_duration_seconds: Histogram for session duration
        mcp_event_emit_success_total: Counter for successful MCP events
        mcp_event_emit_failure_total: Counter for failed MCP events
        mcp_event_emit_duration_seconds: Histogram for MCP event duration
        active_sessions: Gauge for currently active sessions
        session_quality_score: Gauge for session quality scores

    Example:
        >>> metrics = SessionMetrics()
        >>> metrics.record_session_start("mahavishnu", "MahavishnuShell")
        >>> metrics.record_session_end("mahavishnu", "success")
        >>> metrics_data = metrics.export_metrics()
    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Initialize session metrics with Prometheus collectors.

        Args:
            registry: Optional CollectorRegistry for metrics isolation.
                     Defaults to global registry if None.

        Example:
            >>> from prometheus_client.registry import CollectorRegistry
            >>> registry = CollectorRegistry()
            >>> metrics = SessionMetrics(registry=registry)
        """
        self.registry = registry or CollectorRegistry()
        self.logger = get_metrics_logger()

        # Session lifecycle metrics
        self.session_start_total = Counter(
            "session_start_total",
            "Total number of session start events tracked",
            ["component_name", "shell_type"],
            registry=self.registry,
        )

        self.session_end_total = Counter(
            "session_end_total",
            "Total number of session end events tracked",
            ["component_name", "status"],
            registry=self.registry,
        )

        self.session_duration_seconds = Histogram(
            "session_duration_seconds",
            "Session duration in seconds",
            ["component_name"],
            buckets=[
                60,  # 1 minute
                300,  # 5 minutes
                900,  # 15 minutes
                1800,  # 30 minutes
                3600,  # 1 hour
                7200,  # 2 hours
                14400,  # 4 hours
                28800,  # 8 hours
            ],
            registry=self.registry,
        )

        # MCP event emission metrics
        self.mcp_event_emit_success_total = Counter(
            "mcp_event_emit_success_total",
            "Total number of successful MCP event emissions",
            ["component_name", "event_type"],
            registry=self.registry,
        )

        self.mcp_event_emit_failure_total = Counter(
            "mcp_event_emit_failure_total",
            "Total number of failed MCP event emissions",
            ["component_name", "event_type", "error_type"],
            registry=self.registry,
        )

        self.mcp_event_emit_duration_seconds = Histogram(
            "mcp_event_emit_duration_seconds",
            "MCP event emission duration in seconds",
            ["component_name", "event_type"],
            buckets=[
                0.001,  # 1ms
                0.005,  # 5ms
                0.01,  # 10ms
                0.025,  # 25ms
                0.05,  # 50ms
                0.1,  # 100ms
                0.25,  # 250ms
                0.5,  # 500ms
                1.0,  # 1s
                2.5,  # 2.5s
                5.0,  # 5s
                10.0,  # 10s
            ],
            registry=self.registry,
        )

        # System health metrics
        self.active_sessions = Gauge(
            "active_sessions",
            "Number of currently active sessions",
            ["component_name"],
            registry=self.registry,
        )

        self.session_quality_score = Gauge(
            "session_quality_score",
            "Session quality score (0-100)",
            ["component_name"],
            registry=self.registry,
        )

        self.logger.info("SessionMetrics initialized with Prometheus collectors")

    def record_session_start(self, component_name: str, shell_type: str) -> None:
        """Record a session start event.

        Increments the session_start_total counter and active_sessions gauge.

        Args:
            component_name: Component name (e.g., "mahavishnu", "session-buddy")
            shell_type: Shell type (e.g., "MahavishnuShell", "SessionBuddyShell")

        Example:
            >>> metrics = SessionMetrics()
            >>> metrics.record_session_start("mahavishnu", "MahavishnuShell")
        """
        self.session_start_total.labels(
            component_name=component_name,
            shell_type=shell_type,
        ).inc()

        self.active_sessions.labels(component_name=component_name).inc()

        self.logger.debug(
            "Session start recorded: component=%s, shell_type=%s",
            component_name,
            shell_type,
        )

    def record_session_end(
        self,
        component_name: str,
        status: str,
        duration_seconds: float | None = None,
    ) -> None:
        """Record a session end event.

        Increments the session_end_total counter, observes duration histogram,
        and decrements the active_sessions gauge.

        Args:
            component_name: Component name (e.g., "mahavishnu", "session-buddy")
            status: Session end status ("success", "error", "not_found")
            duration_seconds: Optional session duration in seconds

        Example:
            >>> metrics = SessionMetrics()
            >>> metrics.record_session_end("mahavishnu", "success", duration_seconds=3600.5)
        """
        self.session_end_total.labels(
            component_name=component_name,
            status=status,
        ).inc()

        if duration_seconds is not None:
            self.session_duration_seconds.labels(
                component_name=component_name,
            ).observe(duration_seconds)

        self.active_sessions.labels(component_name=component_name).dec()

        self.logger.debug(
            "Session end recorded: component=%s, status=%s, duration=%.2fs",
            component_name,
            status,
            duration_seconds or 0,
        )

    def record_mcp_event_emit_success(
        self,
        component_name: str,
        event_type: str,
        duration_seconds: float,
    ) -> None:
        """Record a successful MCP event emission.

        Increments the success counter and observes the duration histogram.

        Args:
            component_name: Component name emitting the event
            event_type: Type of event emitted (e.g., "session_start", "session_end")
            duration_seconds: Time taken to emit the event in seconds

        Example:
            >>> metrics = SessionMetrics()
            >>> metrics.record_mcp_event_emit_success("mahavishnu", "session_start", 0.015)
        """
        self.mcp_event_emit_success_total.labels(
            component_name=component_name,
            event_type=event_type,
        ).inc()

        self.mcp_event_emit_duration_seconds.labels(
            component_name=component_name,
            event_type=event_type,
        ).observe(duration_seconds)

        self.logger.debug(
            "MCP event emit success: component=%s, event_type=%s, duration=%.3fs",
            component_name,
            event_type,
            duration_seconds,
        )

    def record_mcp_event_emit_failure(
        self,
        component_name: str,
        event_type: str,
        error_type: str,
        duration_seconds: float,
    ) -> None:
        """Record a failed MCP event emission.

        Increments the failure counter and observes the duration histogram.

        Args:
            component_name: Component name emitting the event
            event_type: Type of event being emitted
            error_type: Type of error that occurred (e.g., "ValidationError", "ConnectionError")
            duration_seconds: Time taken before failure in seconds

        Example:
            >>> metrics = SessionMetrics()
            >>> metrics.record_mcp_event_emit_failure("mahavishnu", "session_start", "ConnectionError", 5.2)
        """
        self.mcp_event_emit_failure_total.labels(
            component_name=component_name,
            event_type=event_type,
            error_type=error_type,
        ).inc()

        self.mcp_event_emit_duration_seconds.labels(
            component_name=component_name,
            event_type=event_type,
        ).observe(duration_seconds)

        self.logger.debug(
            "MCP event emit failure: component=%s, event_type=%s, error_type=%s, duration=%.3fs",
            component_name,
            event_type,
            error_type,
            duration_seconds,
        )

    def set_session_quality_score(
        self, component_name: str, quality_score: float
    ) -> None:
        """Set the session quality score gauge.

        Args:
            component_name: Component name
            quality_score: Quality score (0-100)

        Example:
            >>> metrics = SessionMetrics()
            >>> metrics.set_session_quality_score("mahavishnu", 85.5)
        """
        self.session_quality_score.labels(component_name=component_name).set(
            quality_score
        )

        self.logger.debug(
            "Session quality score set: component=%s, score=%.1f",
            component_name,
            quality_score,
        )

    def export_metrics(self) -> bytes:
        """Export metrics in Prometheus text format.

        Returns:
            Metrics in Prometheus text format (CONTENT_TYPE_LATEST)

        Example:
            >>> metrics = SessionMetrics()
            >>> metrics_data = metrics.export_metrics()
            >>> print(metrics_data.decode('utf-8'))
        """
        return generate_latest(self.registry)

    def clear_metrics(self) -> None:
        """Clear all metrics (useful for testing).

        Example:
            >>> metrics = SessionMetrics()
            >>> metrics.record_session_start("test", "TestShell")
            >>> metrics.clear_metrics()
            >>> assert metrics.session_start_total._value._value == 0
        """
        # Clear all metrics in the registry
        for collector in list(self.registry._collector_to_names.keys()):
            self.registry.unregister(collector)

        # Reinitialize all metrics
        self.__init__(registry=self.registry)

        self.logger.debug("All metrics cleared")


# Global metrics instance
_metrics: SessionMetrics | None = None


def get_metrics() -> SessionMetrics:
    """Get the global SessionMetrics instance.

    This function provides a singleton pattern for metrics collection.
    The global instance is initialized on first call.

    Returns:
        Global SessionMetrics instance

    Example:
        >>> from session_buddy.mcp.metrics import get_metrics
        >>>
        >>> metrics = get_metrics()
        >>> metrics.record_session_start("mahavishnu", "MahavishnuShell")
    """
    global _metrics

    if _metrics is None:
        _metrics = SessionMetrics()

    return _metrics


# Decorator for timing operations


F = TypeVar("F", bound=Callable[..., Any])


def track_operation_duration(
    operation_name: str,
    component_name: str = "session-buddy",
    metrics_instance: SessionMetrics | None = None,
) -> Callable[[F], F]:
    """Decorator to track operation duration with Prometheus metrics.

    This decorator measures the execution time of the wrapped function
    and records it to the mcp_event_emit_duration_seconds histogram.
    It also tracks success/failure counts.

    Args:
        operation_name: Name of the operation (used as event_type label)
        component_name: Component name for label
        metrics_instance: Optional SessionMetrics instance (uses global if None)

    Returns:
        Decorated function with duration tracking

    Example:
        >>> from session_buddy.mcp.metrics import track_operation_duration
        >>>
        >>> @track_operation_duration("database_query", "session-buddy")
        ... async def query_data():
        ...     # ... database query logic
        ...     return results
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            metrics = metrics_instance or get_metrics()
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                metrics.record_mcp_event_emit_success(
                    component_name=component_name,
                    event_type=operation_name,
                    duration_seconds=duration,
                )

                return result

            except Exception as e:
                duration = time.time() - start_time
                error_type = type(e).__name__

                metrics.record_mcp_event_emit_failure(
                    component_name=component_name,
                    event_type=operation_name,
                    error_type=error_type,
                    duration_seconds=duration,
                )

                raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            metrics = metrics_instance or get_metrics()
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                metrics.record_mcp_event_emit_success(
                    component_name=component_name,
                    event_type=operation_name,
                    duration_seconds=duration,
                )

                return result

            except Exception as e:
                duration = time.time() - start_time
                error_type = type(e).__name__

                metrics.record_mcp_event_emit_failure(
                    component_name=component_name,
                    event_type=operation_name,
                    error_type=error_type,
                    duration_seconds=duration,
                )

                raise

        # Check if function is async or sync
        if hasattr(func, "__annotations__") and "return" in func.__annotations__:
            # Async function
            return async_wrapper  # type: ignore[return-value]
        else:
            # Sync function
            return sync_wrapper  # type: ignore[return-value]

    return decorator


__all__ = [
    "SessionMetrics",
    "get_metrics",
    "track_operation_duration",
]
