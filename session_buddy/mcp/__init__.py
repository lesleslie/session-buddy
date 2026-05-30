"""Session Buddy MCP Server Components."""

from __future__ import annotations

from importlib import import_module
from typing import Any

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
from session_buddy.mcp.telemetry import attach_otel_middleware, configure_otel_tracing

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "mcp": ("session_buddy.mcp.server", "mcp"),
    "SessionTracker": ("session_buddy.mcp.session_tracker", "SessionTracker"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    "mcp",
    "SessionTracker",
    "attach_otel_middleware",
    "configure_otel_tracing",
    "SessionStartEvent",
    "SessionEndEvent",
    "UserInfo",
    "EnvironmentInfo",
    "SessionStartResult",
    "SessionEndResult",
    "ErrorResponse",
    "get_session_start_event_schema",
    "get_session_end_event_schema",
    "get_session_start_result_schema",
    "get_session_end_result_schema",
]
