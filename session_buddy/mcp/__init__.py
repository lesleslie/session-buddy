"""Session Buddy MCP Server Components.

This module contains the MCP (Model Context Protocol) server implementation,
including FastMCP setup, tool registration, and server lifecycle management.

The server provides 70+ tools across 8 functional domains:
- Session management (5 tools)
- Memory & search (4 tools)
- Monitoring & analytics (4 tools)
- Team collaboration (2 tools)
- LLM & intelligence (3 tools)
- Infrastructure (4 tools)
- Advanced features (7 tools)
- Utilities (3 tools)

Example:
    >>> from session_buddy.mcp.server import mcp
    >>> # Server is initialized and tools are registered automatically
"""

from session_buddy.mcp.event_models import (
    EnvironmentInfo,
    ErrorResponse,
    SessionEndEvent,
    SessionEndResult,
    SessionStartEvent,
    SessionStartResult,
    UserInfo,
    get_session_end_event_schema,
    get_session_end_result_schema,
    get_session_start_event_schema,
    get_session_start_result_schema,
)
from session_buddy.mcp.server import mcp  # noqa: F401
from session_buddy.mcp.session_tracker import SessionTracker  # noqa: F401

__all__ = [
    "mcp",
    # Session tracking
    "SessionTracker",
    # Event models
    "SessionStartEvent",
    "SessionEndEvent",
    "UserInfo",
    "EnvironmentInfo",
    # Result models
    "SessionStartResult",
    "SessionEndResult",
    "ErrorResponse",
    # JSON Schema helpers
    "get_session_start_event_schema",
    "get_session_end_event_schema",
    "get_session_start_result_schema",
    "get_session_end_result_schema",
]
