"""Monitoring tools for Session-Buddy MCP server."""

from session_buddy.mcp.tools.monitoring.prometheus_metrics_tools import (
    register_prometheus_metrics_tools,
)

__all__ = ["register_prometheus_metrics_tools"]
