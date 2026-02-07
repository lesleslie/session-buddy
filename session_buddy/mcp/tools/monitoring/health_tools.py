"""Health check MCP tools for session-mgmt-mcp.

Provides health status endpoints compatible with Docker and Kubernetes
orchestration systems.

Phase 10.1: Production Hardening - Health Check Tools
"""

from __future__ import annotations

import time
import typing as t

from mcp_common.health import HealthCheckResponse

# Server start time for uptime calculation
_SERVER_START_TIME = time.time()


def _normalize_dict_component(
    component: dict[str, t.Any],
) -> t.Any:  # Returns MCPComponentHealth
    """Normalize dictionary component to MCPComponentHealth."""
    from mcp_common.health import ComponentHealth as MCPComponentHealth
    from mcp_common.health import HealthStatus as MCPHealthStatus

    status_value = component.get("status", "degraded")
    try:
        status = MCPHealthStatus(status_value)
    except ValueError:
        status = MCPHealthStatus.DEGRADED

    return MCPComponentHealth(
        name=component.get("name", "unknown"),
        status=status,
        message=component.get("message"),
        latency_ms=component.get("latency_ms"),
        metadata=component.get("metadata", {}),
    )


def _normalize_object_component(
    component: t.Any,
) -> t.Any:  # Returns MCPComponentHealth
    """Normalize object component to MCPComponentHealth."""
    from mcp_common.health import ComponentHealth as MCPComponentHealth
    from mcp_common.health import HealthStatus as MCPHealthStatus

    status_attr = getattr(component, "status", MCPHealthStatus.DEGRADED)
    try:
        status = (
            status_attr
            if isinstance(status_attr, MCPHealthStatus)
            else MCPHealthStatus(str(status_attr))
        )
    except ValueError:
        status = MCPHealthStatus.DEGRADED

    return MCPComponentHealth(
        name=getattr(component, "name", "unknown"),
        status=status,
        message=getattr(component, "message", None),
        latency_ms=getattr(component, "latency_ms", None),
        metadata=getattr(component, "metadata", {}),
    )


def _normalize_components(
    components: list[t.Any],
) -> list[t.Any]:  # Returns list[MCPComponentHealth]
    """Normalize health check components to standard format."""
    from mcp_common.health import ComponentHealth as MCPComponentHealth

    normalized: list[t.Any] = []  # list[MCPComponentHealth]
    for component in components:
        if isinstance(component, MCPComponentHealth):
            normalized.append(component)
        elif isinstance(component, dict):
            normalized.append(_normalize_dict_component(component))
        else:
            normalized.append(_normalize_object_component(component))

    return normalized


def _prepare_readiness_result(
    response: t.Any,  # HealthCheckResponse
) -> dict[str, t.Any]:
    """Prepare result for readiness check."""
    result: dict[str, t.Any] = response.to_dict()
    result["ready"] = response.is_healthy()
    return result


def _prepare_liveness_result(
    response: t.Any,  # HealthCheckResponse
) -> dict[str, t.Any]:
    """Prepare result for liveness check."""
    result: dict[str, t.Any] = response.to_dict()
    result["alive"] = response.is_ready()
    return result


async def get_health_status(ready: bool = False) -> dict[str, t.Any]:
    """Get comprehensive health status of the session management server.

    Args:
        ready: If True, use readiness check logic (stricter, for K8s readiness probes)
               If False, use liveness check logic (looser, for K8s liveness probes)

    Returns:
        Dictionary with health status suitable for JSON serialization

    Example Response:
        {
            "status": "healthy",
            "timestamp": "2025-10-28T12:00:00Z",
            "version": "1.0.0",
            "uptime_seconds": 3600.5,
            "components": [
                {
                    "name": "database",
                    "status": "healthy",
                    "message": "Database operational",
                    "latency_ms": 12.5
                },
                ...
            ]
        }

    Usage:
        # Kubernetes liveness probe (checks if server should be restarted)
        await get_health_status(ready=False)

        # Kubernetes readiness probe (checks if server should receive traffic)
        await get_health_status(ready=True)

        # Docker health check
        await get_health_status()

    """
    from session_buddy.health_checks import get_all_health_checks

    # Get server version
    try:
        from session_buddy import __version__

        version = __version__
    except (ImportError, AttributeError):
        version = "unknown"

    # Run all health checks and normalize
    components = await get_all_health_checks()
    normalized_components = _normalize_components(components)

    # Create health response
    response = HealthCheckResponse.create(
        components=normalized_components,
        version=version,
        start_time=_SERVER_START_TIME,
        metadata={"check_type": "readiness" if ready else "liveness"},
    )

    # Return appropriate result based on check type
    return (
        _prepare_readiness_result(response)
        if ready
        else _prepare_liveness_result(response)
    )


__all__ = ["get_health_status"]
