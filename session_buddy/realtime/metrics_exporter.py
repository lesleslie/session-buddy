"""Prometheus metrics exporter for skills monitoring.

This module implements a Prometheus metrics exporter that exposes skill metrics
in Prometheus format for scraping by monitoring systems (Grafana, Prometheus, etc.).

Example:
    >>> from session_buddy.realtime import PrometheusExporter
    >>>
    >>> exporter = PrometheusExporter(port=9090)
    >>> exporter.start()
    >>>
    >>> # Record metrics
    >>> exporter.record_invocation("pytest-run", "execution", True, 45.2)
    >>> exporter.update_completion_rate("pytest-run", 0.92)
    >>>
    >>> # Metrics available at: http://localhost:9090/metrics
"""

from __future__ import annotations

import logging
from threading import Thread
from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram, start_http_server

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ============================================================================
# Prometheus Metrics Definitions
# ============================================================================

# Counter: Total skill invocations
skill_invocations_total = Counter(
    "skill_invocations_total",
    "Total number of skill invocations",
    ["skill_name", "workflow_phase", "completed"],
)

# Histogram: Skill execution duration
skill_duration_seconds = Histogram(
    "skill_duration_seconds",
    "Skill execution duration in seconds",
    ["skill_name", "workflow_phase"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0],
)

# Gauge: Current skill completion rate
skill_completion_rate = Gauge(
    "skill_completion_rate",
    "Current skill completion rate",
    ["skill_name"],
)

# Gauge: Number of active sessions
active_sessions_total = Gauge(
    "active_sessions_total",
    "Number of currently active sessions",
)

# Counter: Total anomalies detected
anomalies_detected_total = Counter(
    "anomalies_detected_total",
    "Total number of anomalies detected",
    ["anomaly_type", "skill_name"],
)

# ============================================================================
# Prometheus Exporter
# ============================================================================


class PrometheusExporter:
    """Export skills metrics to Prometheus format.

    Manages Prometheus metrics and provides HTTP endpoint for scraping.
    Thread-safe for concurrent updates from multiple agents.

    Attributes:
        port: Port for HTTP metrics server
        _running: Whether exporter is currently running

    Example:
        >>> exporter = PrometheusExporter(port=9090)
        >>> exporter.start()
        >>>
        >>> # Record metrics
        >>> exporter.record_invocation("pytest-run", "execution", True, 45.2)
        >>> exporter.update_completion_rate("pytest-run", 0.92)
        >>> exporter.record_anomaly("performance_drop", "ruff-check")
        >>>
        >>> # Access metrics at: http://localhost:9090/metrics
    """

    def __init__(self, port: int = 9090) -> None:
        """Initialize Prometheus exporter.

        Args:
            port: Port for HTTP metrics server (default: 9090)

        Raises:
            ValueError: If port is not in valid range (1-65535)
        """
        if not 1 <= port <= 65535:
            msg = f"Port must be between 1 and 65535, got {port}"
            raise ValueError(msg)

        self.port = port
        self._running = False
        logger.info(f"PrometheusExporter initialized on port {port}")

    def start(self) -> None:
        """Start Prometheus metrics HTTP server.

        Starts HTTP server in background thread to serve metrics endpoint.
        Safe to call multiple times (idempotent).

        Example:
            >>> exporter = PrometheusExporter(port=9090)
            >>> exporter.start()
            >>> # Metrics now available at http://localhost:9090/metrics

        Note:
            The HTTP server runs in a daemon thread and will be stopped
            when the main program exits.
        """
        if self._running:
            logger.warning(f"Prometheus exporter already running on port {self.port}")
            return

        try:
            start_http_server(self.port)
            self._running = True
            logger.info(
                f"Prometheus metrics server started on port {self.port}, "
                f"endpoint: http://localhost:{self.port}/metrics"
            )
        except OSError as e:
            logger.error(f"Failed to start Prometheus server on port {self.port}: {e}")
            raise

    def record_invocation(
        self,
        skill_name: str,
        workflow_phase: str | None,
        completed: bool,
        duration_seconds: float | None,
    ) -> None:
        """Record a skill invocation.

        Updates invocation counter, duration histogram, and completion metrics.

        Args:
            skill_name: Name of the skill being invoked
            workflow_phase: Oneiric workflow phase (e.g., "execution", "setup")
            completed: Whether the skill completed successfully
            duration_seconds: Execution duration in seconds (None if not available)

        Example:
            >>> exporter.record_invocation(
            ...     skill_name="pytest-run",
            ...     workflow_phase="execution",
            ...     completed=True,
            ...     duration_seconds=45.2
            ... )

        Note:
            Thread-safe: Can be called from multiple threads/agents concurrently.
        """
        # Normalize labels
        phase = workflow_phase or "unknown"
        completed_str = "true" if completed else "false"

        # Update counter
        skill_invocations_total.labels(
            skill_name=skill_name,
            workflow_phase=phase,
            completed=completed_str,
        ).inc()

        # Update histogram if duration available
        if duration_seconds is not None:
            skill_duration_seconds.labels(
                skill_name=skill_name,
                workflow_phase=phase,
            ).observe(duration_seconds)

        logger.debug(
            f"Recorded invocation: skill={skill_name}, phase={phase}, "
            f"completed={completed_str}, duration={duration_seconds}"
        )

    def update_completion_rate(self, skill_name: str, rate: float) -> None:
        """Update skill completion rate gauge.

        Sets the current completion rate for a specific skill.

        Args:
            skill_name: Name of the skill
            rate: Completion rate (0.0 to 1.0)

        Raises:
            ValueError: If rate is not between 0 and 1

        Example:
            >>> exporter.update_completion_rate("pytest-run", 0.92)

        Note:
            Completion rate should be calculated periodically from database metrics.
            This method updates the current gauge value.
        """
        if not 0.0 <= rate <= 1.0:
            msg = f"Completion rate must be between 0 and 1, got {rate}"
            raise ValueError(msg)

        skill_completion_rate.labels(skill_name=skill_name).set(rate)
        logger.debug(f"Updated completion rate: skill={skill_name}, rate={rate:.2%}")

    def record_anomaly(self, anomaly_type: str, skill_name: str) -> None:
        """Record detected anomaly.

        Increments anomaly counter for specific anomaly type and skill.

        Args:
            anomaly_type: Type of anomaly (e.g., "drop", "spike", "pattern_shift")
            skill_name: Name of the skill where anomaly was detected

        Example:
            >>> exporter.record_anomaly("performance_drop", "ruff-check")

        Note:
            Anomaly types from schema:
            - "drop": Sudden drop in completion rate
            - "spike": Unusual spike in invocations
            - "pattern_shift": Change in usage patterns
        """
        anomalies_detected_total.labels(
            anomaly_type=anomaly_type,
            skill_name=skill_name,
        ).inc()

        logger.debug(
            f"Recorded anomaly: type={anomaly_type}, skill={skill_name}"
        )

    def update_active_sessions(self, count: int) -> None:
        """Update active sessions gauge.

        Sets the current number of active sessions.

        Args:
            count: Number of currently active sessions

        Raises:
            ValueError: If count is negative

        Example:
            >>> exporter.update_active_sessions(5)

        Note:
            Should be called periodically to reflect current session count.
            Typically updated by session tracking logic.
        """
        if count < 0:
            msg = f"Session count cannot be negative, got {count}"
            raise ValueError(msg)

        active_sessions_total.set(count)
        logger.debug(f"Updated active sessions: count={count}")

    def is_running(self) -> bool:
        """Check if exporter is currently running.

        Returns:
            True if exporter is running, False otherwise

        Example:
            >>> if exporter.is_running():
            ...     print("Metrics available at http://localhost:9090/metrics")
        """
        return self._running


# ============================================================================
# Convenience Functions
# ============================================================================


def create_exporter(port: int = 9090) -> PrometheusExporter:
    """Create and start Prometheus exporter.

    Convenience function for one-line exporter creation.

    Args:
        port: Port for HTTP metrics server (default: 9090)

    Returns:
        Started PrometheusExporter instance

    Example:
        >>> from session_buddy.realtime.metrics_exporter import create_exporter
        >>>
        >>> exporter = create_exporter(port=9090)
        >>> exporter.record_invocation("pytest-run", "execution", True, 45.2)
    """
    exporter = PrometheusExporter(port=port)
    exporter.start()
    return exporter


# ============================================================================
# Example Usage (for testing)
# ============================================================================

if __name__ == "__main__":
    import time

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and start exporter
    exporter = PrometheusExporter(port=9090)
    exporter.start()

    print("Prometheus metrics server started on http://localhost:9090/metrics")
    print("Recording sample metrics every 5 seconds...")
    print("Press Ctrl+C to stop")

    try:
        iteration = 0
        while True:
            iteration += 1

            # Record sample invocations
            exporter.record_invocation("pytest-run", "execution", True, 45.2)
            exporter.record_invocation("ruff-check", "setup", True, 2.1)
            exporter.record_invocation("pytest-run", "execution", False, 120.5)
            exporter.record_invocation("mypy-check", "execution", True, 15.8)

            # Update completion rates
            exporter.update_completion_rate("pytest-run", 0.92)
            exporter.update_completion_rate("ruff-check", 0.87)
            exporter.update_completion_rate("mypy-check", 0.95)

            # Record some anomalies
            if iteration % 3 == 0:
                exporter.record_anomaly("performance_drop", "pytest-run")
            if iteration % 5 == 0:
                exporter.record_anomaly("spike", "ruff-check")

            # Update active sessions
            exporter.update_active_sessions(min(iteration % 10, 5))

            print(f"\n=== Iteration {iteration} ===")
            print("Sample metrics recorded. Check http://localhost:9090/metrics")
            print("Waiting 5 seconds...")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\nShutting down...")
        print("Metrics server stopped")
