"""Health status tools for Session-Buddy.

Provides get_health_status() for Docker and Kubernetes orchestration
health probes (liveness and readiness checks).

Phase: Week 1 Day 1 - Quick Win Coverage
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from session_buddy import health_checks
from session_buddy.health_checks import ComponentHealth

# Module-level constant for uptime calculation
_SERVER_START_TIME: float = time.time()


async def get_health_status(
    ready: bool = False,
) -> dict[str, Any]:
    """Return health status dictionary for orchestration probes.

    Args:
        ready: If True, perform a strict readiness check (only HEALTHY
            components pass). If False, perform a loose liveness check
            (only UNHEALTHY components fail).

    Returns:
        Dictionary with status, timestamp, version, uptime_seconds,
        components, and probe-specific keys (alive/ready, metadata).
    """
    components: list[ComponentHealth] = await health_checks.get_all_health_checks()

    # Convert ComponentHealth dataclasses to dicts if needed
    serialised: list[dict[str, Any]] = []
    for comp in components:
        if isinstance(comp, ComponentHealth):
            serialised.append(
                {
                    "name": comp.name,
                    "status": str(comp.status),
                    "message": comp.message,
                    "latency_ms": comp.latency_ms,
                }
                | comp.metadata
            )
        else:
            # Defensive fallback for any dict-like component
            serialised.append(dict(comp))

    # Determine overall health
    statuses = [c.get("status", "healthy") for c in serialised]

    if ready:
        # Readiness: strict -- only fully healthy passes
        is_ready = all(s == health_checks.HealthStatus.HEALTHY for s in statuses)
        check_type = "readiness"
    else:
        # Liveness: loose -- only unhealthy fails
        is_alive = not any(s == health_checks.HealthStatus.UNHEALTHY for s in statuses)
        check_type = "liveness"

    # Version
    try:
        from session_buddy import __version__

        version: str = __version__
    except (ImportError, AttributeError):
        version = "unknown"

    result: dict[str, Any] = {
        "status": "healthy" if (is_ready if ready else is_alive) else "unhealthy",
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "version": version,
        "uptime_seconds": round(time.time() - _SERVER_START_TIME, 3),
        "components": serialised,
        "metadata": {"check_type": check_type},
    }

    if ready:
        result["ready"] = is_ready
    else:
        result["alive"] = is_alive

    return result


__all__ = ["get_health_status"]
