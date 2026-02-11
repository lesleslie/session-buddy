"""Real-time monitoring and WebSocket server for Session-Buddy.

This module provides real-time metrics broadcasting and WebSocket connectivity
for live skill monitoring dashboards.
"""

from session_buddy.realtime.websocket_server import RealTimeMetricsServer

__all__ = ["RealTimeMetricsServer"]
