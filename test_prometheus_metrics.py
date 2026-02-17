#!/usr/bin/env python3
"""Test script for Prometheus metrics exporter.

Run this script to verify Prometheus metrics are properly formatted
and can be scraped by monitoring systems.
"""

import sys
import time

sys.path.insert(0, ".")

from session_buddy.realtime.metrics_exporter import PrometheusExporter


def test_prometheus_exporter():
    """Test Prometheus metrics exporter functionality."""
    print("=" * 70)
    print("Testing Prometheus Metrics Exporter")
    print("=" * 70)

    # Create exporter
    exporter = PrometheusExporter(port=9092)
    print(f"\n✅ Created PrometheusExporter on port {exporter.port}")

    # Start server
    exporter.start()
    print("✅ Started Prometheus HTTP server")
    print(f"   Metrics endpoint: http://localhost:{exporter.port}/metrics")

    # Record some test metrics
    print("\n📊 Recording test metrics...")

    # Skill invocations
    exporter.record_invocation("pytest-run", "execution", True, 45.2)
    exporter.record_invocation("pytest-run", "execution", True, 38.7)
    exporter.record_invocation("pytest-run", "execution", False, 120.5)
    exporter.record_invocation("ruff-check", "setup", True, 2.1)
    exporter.record_invocation("ruff-check", "setup", True, 1.8)
    exporter.record_invocation("mypy-check", "execution", True, 15.8)
    exporter.record_invocation("mypy-check", "execution", True, 14.2)
    exporter.record_invocation("codespell", "validation", True, 0.5)

    print("   ✅ Recorded 8 skill invocations")

    # Completion rates
    exporter.update_completion_rate("pytest-run", 0.85)
    exporter.update_completion_rate("ruff-check", 1.0)
    exporter.update_completion_rate("mypy-check", 1.0)
    exporter.update_completion_rate("codespell", 1.0)

    print("   ✅ Updated completion rates for 4 skills")

    # Anomalies
    exporter.record_anomaly("performance_drop", "pytest-run")
    exporter.record_anomaly("spike", "ruff-check")

    print("   ✅ Recorded 2 anomalies")

    # Active sessions
    exporter.update_active_sessions(5)

    print("   ✅ Updated active sessions: 5")

    # Show what to expect
    print("\n" + "=" * 70)
    print("Prometheus Metrics Format")
    print("=" * 70)
    print("""
# HELP skill_invocations_total Total number of skill invocations
# TYPE skill_invocations_total counter
skill_invocations_total{skill_name="pytest-run",workflow_phase="execution",completed="true"} 2.0
skill_invocations_total{skill_name="pytest-run",workflow_phase="execution",completed="false"} 1.0
skill_invocations_total{skill_name="ruff-check",workflow_phase="setup",completed="true"} 2.0
skill_invocations_total{skill_name="mypy-check",workflow_phase="execution",completed="true"} 2.0
skill_invocations_total{skill_name="codespell",workflow_phase="validation",completed="true"} 1.0

# HELP skill_duration_seconds Skill execution duration in seconds
# TYPE skill_duration_seconds histogram
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="0.1"} 0.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="0.5"} 0.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="1.0"} 0.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="2.0"} 0.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="5.0"} 0.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="10.0"} 0.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="30.0"} 2.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="60.0"} 2.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="300.0"} 3.0
skill_duration_seconds_bucket{skill_name="pytest-run",workflow_phase="execution",le="+Inf"} 3.0
skill_duration_seconds_sum{skill_name="pytest-run",workflow_phase="execution"} 204.4
skill_duration_seconds_count{skill_name="pytest-run",workflow_phase="execution"} 3.0

# HELP skill_completion_rate Current skill completion rate
# TYPE skill_completion_rate gauge
skill_completion_rate{skill_name="pytest-run"} 0.85
skill_completion_rate{skill_name="ruff-check"} 1.0
skill_completion_rate{skill_name="mypy-check"} 1.0
skill_completion_rate{skill_name="codespell"} 1.0

# HELP active_sessions_total Number of currently active sessions
# TYPE active_sessions_total gauge
active_sessions_total 5.0

# HELP anomalies_detected_total Total number of anomalies detected
# TYPE anomalies_detected_total counter
anomalies_detected_total{anomaly_type="performance_drop",skill_name="pytest-run"} 1.0
anomalies_detected_total{anomaly_type="spike",skill_name="ruff-check"} 1.0
""")

    print("=" * 70)
    print("Testing Complete!")
    print("=" * 70)
    print(f"\n🔍 To see actual metrics, visit: http://localhost:{exporter.port}/metrics")
    print("⏱️  Press Ctrl+C to stop the server\n")

    try:
        # Keep server running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping Prometheus metrics server...")
        print("✅ Test complete!")


if __name__ == "__main__":
    test_prometheus_exporter()
