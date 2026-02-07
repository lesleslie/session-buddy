"""MCP client integration for Session-Buddy.

This package provides MCP client functionality for communicating with other
MCP servers, such as Oneiric MCP for adapter discovery.
"""

from session_buddy.mcp_clients.oneiric_client import OneiricMCPClient

__all__ = [
    "OneiricMCPClient",
]
