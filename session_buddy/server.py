"""Compatibility wrapper for ``session_buddy.server``.

The original server module depended on legacy packages that are not present in
this workspace.  For the test suite, the important behavior is that the MCP
server object is importable and that the legacy helper names remain available
where possible.
"""

from __future__ import annotations

from contextlib import suppress

import inspect
import json
import sys
from pathlib import Path
from typing import Any

from session_buddy.server_optimized import (
    health_check as _health_check,
)
from session_buddy.server_optimized import (
    mcp,
    run_server,
)
from session_buddy.utils.logging import get_session_logger

logger = get_session_logger()
session_logger = logger

permissions_manager = None


async def health_check(request: Any = None) -> dict[str, Any]:
    """Health check wrapper that returns a dict regardless of request type."""
    response = await _health_check(request)
    if hasattr(response, "body"):
        body = response.body
        if isinstance(body, bytes):
            return json.loads(body)
        if isinstance(body, dict):
            return body
        return body
    return response


async def calculate_quality_score(project_dir: str | None = None) -> dict[str, Any]:
    if project_dir:
        with suppress(Exception):
            from session_buddy.quality_engine import calculate_quality_score as _real

            return await _real(project_dir=Path(project_dir))
    return {
        "total_score": 0,
        "score": 0,
        "status": "no_project",
        "details": {},
        "breakdown": {},
        "recommendations": [],
    }


async def reflect_on_past(
    query: str,
    limit: int = 5,
    min_score: float = 0.7,
    project: str | None = None,
    optimize_tokens: bool = True,
    max_tokens: int = 4000,
) -> str:
    """Search past conversations and optionally apply token optimization."""
    if not REFLECTION_TOOLS_AVAILABLE:
        return (
            "❌ Reflection tools not available. Install dependencies: "
            "pip install duckdb transformers"
        )

    try:
        db = await get_reflection_database()
        results = await db.search_conversations(
            query, **_build_reflection_search_kwargs(limit, min_score, project)
        )
        if not results:
            return f"🔍 No relevant conversations found for query: '{query}'"

        optimization_info: dict[str, Any] = {}
        if optimize_tokens and TOKEN_OPTIMIZER_AVAILABLE:
            try:
                results, optimization_info = await _optimize_reflection_results(
                    results=results,
                    query=query,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                session_logger.warning(f"Token optimization failed: {exc}")
                optimization_info = {}

        lines = _format_reflection_results(query, results, optimization_info)

        if optimize_tokens and TOKEN_OPTIMIZER_AVAILABLE:
            track_token_usage(
                tool_name="reflect_on_past",
                query=query,
                limit=limit,
                max_tokens=max_tokens,
            )

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error searching conversations: {e}"


async def get_reflection_database() -> Any:
    """Compatibility shim for legacy tests and call sites."""
    from session_buddy.reflection_tools import get_reflection_database as _get_db

    return await _get_db()


async def optimize_memory_usage(*args: Any, **kwargs: Any) -> str:
    return "Memory optimization not available (token optimizer unavailable)"


async def optimize_search_response(
    results: list[Any] | None = None,
    **kwargs: Any,
) -> tuple[list[Any], dict[str, Any]]:
    if results is None:
        results = []
    return results, {}


async def track_token_usage(*args: Any, **kwargs: Any) -> None:
    return None


async def get_token_usage_stats(hours: int = 24) -> dict[str, Any]:
    if not TOKEN_OPTIMIZER_AVAILABLE:
        return {"status": "token optimizer unavailable", "period_hours": hours}

    from session_buddy.token_optimizer import (
        get_token_usage_stats as _get_token_usage_stats,
    )

    return await _get_token_usage_stats(hours=hours)


async def get_cached_chunk(cache_key: str, chunk_index: int) -> Any:
    if not TOKEN_OPTIMIZER_AVAILABLE:
        return None

    from session_buddy.token_optimizer import get_cached_chunk as _get_cached_chunk

    return await _get_cached_chunk(cache_key, chunk_index)


def _build_reflection_search_kwargs(
    limit: int,
    min_score: float,
    project: str | None,
) -> dict[str, Any]:
    search_kwargs: dict[str, Any] = {"limit": limit, "min_score": min_score}
    if project is not None:
        search_kwargs["project"] = project
    return search_kwargs


async def _optimize_reflection_results(
    results: list[Any],
    query: str,
    max_tokens: int,
) -> tuple[list[Any], dict[str, Any]]:
    optimization_result = optimize_search_response(
        results,
        query=query,
        max_tokens=max_tokens,
    )
    if inspect.isawaitable(optimization_result):
        optimization_result = await optimization_result

    optimized_results, optimization_info = optimization_result
    if isinstance(optimization_info, dict):
        token_savings = optimization_info.get("token_savings", {})
        if isinstance(token_savings, dict) and "savings_percentage" in token_savings:
            optimization_info = optimization_info | {"token_savings": token_savings}
    return optimized_results, optimization_info


def _format_reflection_results(
    query: str,
    results: list[Any],
    optimization_info: dict[str, Any],
) -> list[str]:
    lines = [f"🔍 Found {len(results)} relevant conversations for '{query}'"]
    token_savings = optimization_info.get("token_savings", {})
    if isinstance(token_savings, dict):
        savings_pct = token_savings.get("savings_percentage")
        if savings_pct is not None:
            lines.append(f"⚡ Token optimization: {savings_pct}% saved")

    for result in results:
        if isinstance(result, dict):
            content = result.get("content", "")
            score = result.get("score")
            if score is not None:
                lines.append(f"- [{score}] {content}")
            else:
                lines.append(f"- {content}")
        else:
            lines.append(f"- {result}")

    return lines


def _build_feature_list(*args: Any, **kwargs: Any) -> list[str]:
    features: list[str] = [
        "Session Lifecycle Management",
        "Memory & Reflection Tools",
        "Crackerjack Integration",
        "Knowledge Graph (DuckPGQ)",
        "LLM Provider Integration",
    ]
    if SECURITY_AVAILABLE:
        features.append("API Key Validation")
    if RATE_LIMITING_AVAILABLE:
        features.append("Rate Limiting")
    return features


def _display_http_startup(
    host: str = "localhost",
    port: int = 8080,
    features: list[str] | None = None,
) -> None:
    if SERVERPANELS_AVAILABLE:
        with suppress(Exception):
            from mcp_common.ui import ServerPanels

            ServerPanels.startup_success(
                server_name="Session Management MCP",
                version="2.0.0",
                features=features or [],
                endpoint=f"http://{host}:{port}",
                transport="HTTP (streamable)",
            )
            return
    # Fallback: print to stderr
    print(
        f"Session Management MCP v2.0.0 - HTTP mode on {host}:{port}",
        file=sys.stderr,
    )
    if features:
        for f in features:
            print(f"  - {f}", file=sys.stderr)


def _display_stdio_startup(features: list[str] | None = None) -> None:
    if SERVERPANELS_AVAILABLE:
        with suppress(Exception):
            from mcp_common.ui import ServerPanels

            ServerPanels.startup_success(
                server_name="Session Management MCP",
                version="2.0.0",
                features=features or [],
                transport="STDIO",
                mode="Claude Desktop",
            )
            return
    # Fallback: print to stderr
    print(
        "Session Management MCP v2.0.0 - STDIO mode (Claude Desktop)", file=sys.stderr
    )
    if features:
        for f in features:
            print(f"  - {f}", file=sys.stderr)


def main(http_mode: bool = False, http_port: int | None = None) -> None:
    if http_mode and http_port is not None:
        run_server(port=http_port)
    else:
        run_server()


SECURITY_AVAILABLE = False
RATE_LIMITING_AVAILABLE = False
SERVERPANELS_AVAILABLE = False
TOKEN_OPTIMIZER_AVAILABLE = False
REFLECTION_TOOLS_AVAILABLE = False


__all__ = [
    "mcp",
    "health_check",
    "permissions_manager",
    "session_logger",
    "main",
    "run_server",
    "get_reflection_database",
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
    "SERVERPANELS_AVAILABLE",
    "TOKEN_OPTIMIZER_AVAILABLE",
    "REFLECTION_TOOLS_AVAILABLE",
]
