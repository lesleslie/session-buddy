"""Health check MCP tools for Session-Buddy.

These tools provide standardized health check endpoints following the
mcp-common health infrastructure pattern.

Design: docs/plans/2026-02-27-health-check-system-design.md
"""

from __future__ import annotations

import time
from typing import Any

from mcp_common.health import (
    DependencyConfig,
    register_health_tools,
)

# Service metadata
SERVICE_NAME = "session-buddy"
SERVICE_VERSION = "0.1.0"
SERVICE_START_TIME = time.time()

# Default dependencies for Session-Buddy
# These can be overridden via environment variables:
# SESSION_BUDDY_HEALTH__DEPENDENCIES__MAHAVISHNU__HOST=remote-host
DEFAULT_DEPENDENCIES = {
    "mahavishnu": DependencyConfig(
        host="localhost",
        port=8680,
        required=False,  # Optional - session-buddy can run independently
        timeout_seconds=10,
    ),
    "akosha": DependencyConfig(
        host="localhost",
        port=8682,
        required=False,  # Optional - for cross-system intelligence
        timeout_seconds=10,
    ),
}


def register_health_tools_sb(mcp: Any) -> None:
    """Register health check tools with Session-Buddy MCP server.

    This wraps mcp-common's register_health_tools with Session-Buddy
    specific configuration.

    Tools registered:
        - health_check_service: Check health of a specific service
        - health_check_all: Check all configured dependencies
        - wait_for_dependency: Wait for a dependency to become healthy
        - wait_for_all_dependencies: Wait for all dependencies
        - get_liveness: Basic liveness probe
        - get_readiness: Readiness probe with dependency checks

    Args:
        mcp: FastMCP server instance
    """
    register_health_tools(
        mcp=mcp,
        service_name=SERVICE_NAME,
        version=SERVICE_VERSION,
        start_time=SERVICE_START_TIME,
        dependencies=DEFAULT_DEPENDENCIES,
    )


__all__ = ["register_health_tools_sb"]
