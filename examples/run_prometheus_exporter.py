#!/usr/bin/env python3
"""Run Prometheus metrics exporter for Session-Buddy Phase 4 monitoring.

This script starts the Prometheus metrics exporter that exposes skill metrics
in Prometheus format for scraping by monitoring systems (Grafana, Prometheus, etc.).

Usage:
    python examples/run_prometheus_exporter.py

Once running, metrics are available at: http://localhost:9090/metrics

Example curl command:
    curl http://localhost:9090/metrics

Expected output includes:
    - skill_invocations_total: Total invocations per skill
    - skill_duration_seconds: Execution duration histogram
    - skill_completion_rate: Current completion rates
    - active_sessions_total: Number of active sessions
    - anomalies_detected_total: Anomaly counts
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from session_buddy.realtime.metrics_exporter import PrometheusExporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Start Prometheus metrics exporter with sample data."""
    print("=" * 70)
    print("🔌 Session-Buddy Prometheus Metrics Exporter")
    print("=" * 70)
    print()

    # Create and start exporter
    exporter = PrometheusExporter(port=9090)

    try:
        exporter.start()
        print("✅ Prometheus metrics server started successfully!")
        print()
        print("📍 Metrics endpoint: http://localhost:9090/metrics")
        print("📊 Health check: curl http://localhost:9090/metrics")
        print()
        print("Recording sample metrics every 5 seconds...")
        print("Press Ctrl+C to stop")
        print()

        iteration = 0
        while True:
            iteration += 1

            # Record sample invocations (simulating real usage)
            exporter.record_invocation("pytest-run", "execution", True, 45.2)
            exporter.record_invocation("ruff-check", "setup", True, 2.1)
            exporter.record_invocation("pytest-run", "execution", False, 120.5)
            exporter.record_invocation("mypy-check", "verification", True, 15.8)
            exporter.record_invocation("docker-build", "deployment", True, 180.3)

            # Update completion rates
            exporter.update_completion_rate("pytest-run", 0.92)
            exporter.update_completion_rate("ruff-check", 0.87)
            exporter.update_completion_rate("mypy-check", 0.95)
            exporter.update_completion_rate("docker-build", 0.78)

            # Record some anomalies (simulated)
            if iteration % 3 == 0:
                exporter.record_anomaly("performance_drop", "pytest-run")
                logger.info("Recorded anomaly: performance_drop for pytest-run")

            if iteration % 5 == 0:
                exporter.record_anomaly("spike", "ruff-check")
                logger.info("Recorded anomaly: spike for ruff-check")

            # Update active sessions
            active_sessions = min(iteration % 10, 5)
            exporter.update_active_sessions(active_sessions)

            print(f"=== Iteration {iteration} ===")
            print("✅ Sample metrics recorded")
            print(f"📈 Active sessions: {active_sessions}")
            print("🔗 Check: http://localhost:9090/metrics")
            print()
            print("Waiting 5 seconds...")

            time.sleep(5)

    except KeyboardInterrupt:
        print()
        print("=" * 70)
        print("🛑 Shutting down...")
        print("✅ Metrics server stopped")
        print("=" * 70)
        return 0
    except OSError as e:
        logger.error(f"❌ Failed to start Prometheus server: {e}")
        print()
        print("Troubleshooting:")
        print("  1. Check if port 9090 is already in use:")
        print("     lsof -i :9090")
        print("  2. Kill the process using port 9090:")
        print("     kill -9 <PID>")
        print("  3. Or use a different port by modifying this script")
        return 1
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
