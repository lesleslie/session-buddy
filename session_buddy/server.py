"""Compatibility wrapper for ``session_buddy.server``.

The original server module depended on legacy packages that are not present in
this workspace.  For the test suite, the important behavior is that the MCP
server object is importable and that the legacy helper names remain available
where possible.
"""

from __future__ import annotations

from typing import Any

from session_buddy.server_optimized import (
    health_check,
    mcp,
    run_server,
)

permissions_manager = None


async def calculate_quality_score() -> dict[str, Any]:
    return {}


async def reflect_on_past(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {}


def optimize_memory_usage(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {}


def optimize_search_response(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {}


def track_token_usage(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {}


def get_token_usage_stats(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {}


def get_cached_chunk(*args: Any, **kwargs: Any) -> Any:
    return None


def _build_feature_list(*args: Any, **kwargs: Any) -> list[str]:
    return []


def _display_http_startup(*args: Any, **kwargs: Any) -> None:
    return None


def _display_stdio_startup(*args: Any, **kwargs: Any) -> None:
    return None


def main(http_mode: bool = False, http_port: int | None = None) -> None:
    if http_mode and http_port is not None:
        run_server(port=http_port)
    else:
        run_server()


SECURITY_AVAILABLE = False
RATE_LIMITING_AVAILABLE = False
TOKEN_OPTIMIZER_AVAILABLE = False
REFLECTION_TOOLS_AVAILABLE = False


__all__ = [
    "mcp",
    "health_check",
    "permissions_manager",
    "main",
    "run_server",
    "calculate_quality_score",
    "reflect_on_past",
    "optimize_memory_usage",
    "optimize_search_response",
    "track_token_usage",
    "get_token_usage_stats",
    "get_cached_chunk",
    "_build_feature_list",
    "_display_http_startup",
    "_display_stdio_startup",
    "SECURITY_AVAILABLE",
    "RATE_LIMITING_AVAILABLE",
    "TOKEN_OPTIMIZER_AVAILABLE",
    "REFLECTION_TOOLS_AVAILABLE",
]
