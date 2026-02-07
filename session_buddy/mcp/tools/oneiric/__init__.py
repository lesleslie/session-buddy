"""Oneiric discovery tools for Session-Buddy.

This package provides MCP tools for discovering and resolving Oneiric
storage backends via the Oneiric MCP server.
"""

from session_buddy.mcp.tools.oneiric.oneiric_discovery_tools import (
    register_oneiric_discovery_tools,
)

__all__ = [
    "register_oneiric_discovery_tools",
]
