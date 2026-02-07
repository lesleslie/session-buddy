"""Prometheus metrics tools for Session-Buddy MCP server.

This module provides MCP tools for exposing Prometheus metrics for
session tracking and system monitoring.

Tools:
    - get_prometheus_metrics: Export metrics in Prometheus text format
    - list_session_metrics: List available session metrics with descriptions
    - get_metrics_summary: Get summary statistics of session metrics

Example:
    >>> from session_buddy.mcp.tools.monitoring.prometheus_metrics_tools import register_prometheus_metrics_tools
    >>> import fastmcp
    >>>
    >>> mcp = fastmcp.FastMCP("Session-Buddy")
    >>> register_prometheus_metrics_tools(mcp)
"""

from __future__ import annotations

import logging
from typing import Any

# Import FastMCP with type checking ignore
try:
    from fastmcp import FastMCP
except ImportError:
    FastMCP = Any  # type: ignore[assignment, misc]

# Import metrics module with graceful degradation
try:
    from prometheus_client import CONTENT_TYPE_LATEST
except ImportError:
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

try:
    from session_buddy.mcp.metrics import get_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


def get_prometheus_tools_logger() -> logging.Logger:
    """Get the Prometheus tools logger instance.

    This function is used in tests for mocking purposes.
    """
    return logging.getLogger(__name__)


def register_prometheus_metrics_tools(mcp: FastMCP) -> None:
    """Register Prometheus metrics tools with the MCP server.

    Args:
        mcp: FastMCP instance to register tools with

    Example:
        >>> from fastmcp import FastMCP
        >>> mcp = FastMCP("Session-Buddy")
        >>> register_prometheus_metrics_tools(mcp)
    """
    logger = get_prometheus_tools_logger()

    if not METRICS_AVAILABLE:
        logger.warning("Prometheus metrics not available, skipping tool registration")

        @mcp.tool()
        async def get_prometheus_metrics() -> str:
            """Get Prometheus metrics (not available).

            Returns error message indicating metrics are not available.
            """
            return "Error: Prometheus metrics module not available. Install prometheus_client to enable metrics."

        return

    @mcp.tool()
    async def get_prometheus_metrics() -> str:
        """Export all Session-Buddy metrics in Prometheus text format.

        This tool exports all collected session metrics in Prometheus
        text exposition format for scraping by Prometheus server.

        Returns:
            Metrics in Prometheus text format (CONTENT_TYPE_LATEST)

        Example:
            >>> metrics = await get_prometheus_metrics()
            >>> print(metrics)
            # HELP session_start_total Total number of session start events tracked
            # TYPE session_start_total counter
            session_start_total{component_name="mahavishnu",shell_type="MahavishnuShell"} 42
        """
        try:
            metrics = get_metrics()
            metrics_data = metrics.export_metrics()
            return metrics_data.decode("utf-8")

        except Exception as e:
            logger.error("Failed to export Prometheus metrics: %s", str(e))
            return f"# Error exporting metrics: {str(e)}"

    @mcp.tool()
    async def list_session_metrics() -> dict[str, Any]:
        """List all available session metrics with descriptions.

        Returns a dictionary of all available Prometheus metrics with
        their types, descriptions, and labels.

        Returns:
            Dictionary with metric metadata

        Example:
            >>> metrics_info = await list_session_metrics()
            >>> print(metrics_info["session_start_total"]["description"])
            Total number of session start events tracked
        """
        return {
            "session_lifecycle_metrics": {
                "session_start_total": {
                    "type": "Counter",
                    "description": "Total number of session start events tracked",
                    "labels": ["component_name", "shell_type"],
                },
                "session_end_total": {
                    "type": "Counter",
                    "description": "Total number of session end events tracked",
                    "labels": ["component_name", "status"],
                },
                "session_duration_seconds": {
                    "type": "Histogram",
                    "description": "Session duration in seconds",
                    "labels": ["component_name"],
                    "buckets": [
                        60,
                        300,
                        900,
                        1800,
                        3600,
                        7200,
                        14400,
                        28800,
                    ],
                },
            },
            "mcp_event_metrics": {
                "mcp_event_emit_success_total": {
                    "type": "Counter",
                    "description": "Total number of successful MCP event emissions",
                    "labels": ["component_name", "event_type"],
                },
                "mcp_event_emit_failure_total": {
                    "type": "Counter",
                    "description": "Total number of failed MCP event emissions",
                    "labels": ["component_name", "event_type", "error_type"],
                },
                "mcp_event_emit_duration_seconds": {
                    "type": "Histogram",
                    "description": "MCP event emission duration in seconds",
                    "labels": ["component_name", "event_type"],
                    "buckets": [
                        0.001,
                        0.005,
                        0.01,
                        0.025,
                        0.05,
                        0.1,
                        0.25,
                        0.5,
                        1.0,
                        2.5,
                        5.0,
                        10.0,
                    ],
                },
            },
            "system_health_metrics": {
                "active_sessions": {
                    "type": "Gauge",
                    "description": "Number of currently active sessions",
                    "labels": ["component_name"],
                },
                "session_quality_score": {
                    "type": "Gauge",
                    "description": "Session quality score (0-100)",
                    "labels": ["component_name"],
                },
            },
        }

    @mcp.tool()
    async def get_metrics_summary() -> dict[str, Any]:
        """Get summary statistics of session metrics.

        Returns a summary of current metrics values, including totals,
        active sessions, and quality scores.

        Returns:
            Dictionary with metrics summary

        Example:
            >>> summary = await get_metrics_summary()
            >>> print(summary["total_sessions_started"])
            42
            >>> print(summary["active_sessions"]["mahavishnu"])
            3
        """
        try:
            metrics = get_metrics()

            # Extract metrics values
            summary = {
                "total_sessions_started": 0,
                "total_sessions_ended": 0,
                "active_sessions": {},
                "quality_scores": {},
                "mcp_events_success": 0,
                "mcp_events_failure": 0,
            }

            # Get session start totals
            for metric in metrics.session_start_total.collect():
                for sample in metric.samples:
                    if sample.name.endswith("_total"):
                        summary["total_sessions_started"] += int(sample.value)

            # Get session end totals
            for metric in metrics.session_end_total.collect():
                for sample in metric.samples:
                    if sample.name.endswith("_total"):
                        summary["total_sessions_ended"] += int(sample.value)
                    # Extract status from labels
                    labels = sample.labels or {}
                    if labels.get("status") == "error":
                        pass  # Already counted in total

            # Get active sessions
            for metric in metrics.active_sessions.collect():
                for sample in metric.samples:
                    labels = sample.labels or {}
                    component = labels.get("component_name", "unknown")
                    summary["active_sessions"][component] = int(sample.value)

            # Get quality scores
            for metric in metrics.session_quality_score.collect():
                for sample in metric.samples:
                    labels = sample.labels or {}
                    component = labels.get("component_name", "unknown")
                    summary["quality_scores"][component] = float(sample.value)

            # Get MCP event totals
            for metric in metrics.mcp_event_emit_success_total.collect():
                for sample in metric.samples:
                    if sample.name.endswith("_total"):
                        summary["mcp_events_success"] += int(sample.value)

            for metric in metrics.mcp_event_emit_failure_total.collect():
                for sample in metric.samples:
                    if sample.name.endswith("_total"):
                        summary["mcp_events_failure"] += int(sample.value)

            return summary

        except Exception as e:
            logger.error("Failed to get metrics summary: %s", str(e))
            return {
                "error": str(e),
                "total_sessions_started": 0,
                "total_sessions_ended": 0,
                "active_sessions": {},
                "quality_scores": {},
                "mcp_events_success": 0,
                "mcp_events_failure": 0,
            }

    logger.info("Prometheus metrics tools registered successfully")


__all__ = ["register_prometheus_metrics_tools"]
