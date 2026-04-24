"""MCP client integration for Session-Buddy.

This package provides MCP client functionality for communicating with other
MCP servers, such as the Dhara adapter registry for adapter discovery.
"""

from session_buddy.mcp_clients.oneiric_client import (
    DharaAdapterRegistryClient,
    OneiricMCPClient,
)

__all__ = [
    "DharaAdapterRegistryClient",
    "OneiricMCPClient",
]
