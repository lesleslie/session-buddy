from pathlib import Path
from typing import Any


async def _start_impl_1(working_directory: str | None = None) -> str:
    """Initialize Claude session with comprehensive setup including UV dependencies and automation tools."""
    return await _start_impl(working_directory)


async def _checkpoint_impl_1(working_directory: str | None = None) -> str:
    """Perform mid-session quality checkpoint with workflow analysis and optimization recommendations."""
    return await _checkpoint_impl(working_directory)


async def _end_impl_1(working_directory: str | None = None) -> str:
    """End Claude session with cleanup, learning capture, and handoff file creation."""
    return await _end_impl(working_directory)


async def _status_impl_1(working_directory: str | None = None) -> str:
    """Get current session status and project context information with health checks."""
    return await _status_impl(working_directory)


async def _health_check_impl() -> str:
    """Simple health check that doesn't require database or session context."""
    import os
    import platform
    import time

    try:
        working_directory = str(Path.cwd())
    except FileNotFoundError:
        working_directory = "[Current directory unavailable]"
    health_info = {
        "server_status": "✅ Active",
        "timestamp": time.time(),
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "process_id": os.getpid(),
        "working_directory": working_directory,
    }
    return f"🏥 MCP Server Health Check\n================================\nServer Status: {health_info['server_status']}\nPlatform: {health_info['platform']}\nPython: {health_info['python_version']}\nProcess ID: {health_info['process_id']}\nWorking Directory: {health_info['working_directory']}\nTimestamp: {health_info['timestamp']}\n\n✅ MCP server is operational and responding to requests."


async def _server_info_impl() -> str:
    """Get basic server information without requiring session context."""
    import time

    try:
        home_dir = Path.home()
        try:
            current_dir = Path.cwd()
        except FileNotFoundError:
            current_dir = Path("[Current directory unavailable]")
        return f"📊 Session-mgmt MCP Server Information\n===========================================\n🏠 Home Directory: {home_dir}\n📁 Current Directory: {current_dir}\n🕐 Server Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n🔧 FastMCP Framework: Active\n🌐 Transport: streamable-http\n📡 Endpoint: /mcp\n\n✅ Server is running and accessible."
    except Exception as e:
        return f"⚠️ Server info error: {e!s}"


async def _ping_impl() -> str:
    """Simple ping endpoint to test MCP connectivity."""
    return "🏓 Pong! MCP server is responding"


async def _pre_compact_sync_impl_1() -> str:
    """Sync session state before context compaction (called via PreCompactHook)."""
    result = await _pre_compact_sync_impl()
    if result["success"]:
        output = [
            "🗜️ Pre-Compact Sync Complete",
            "=" * 30,
            f"📁 Project: {result.get('project', 'unknown')}",
            f"⏰ Timestamp: {result['timestamp']}",
        ]
        if result.get("quality_score") is not None:
            output.append(f"📊 Quality score: {result['quality_score']}/100")
        if result.get("reflection_stored"):
            output.append(
                f"💾 Reflection stored: {result.get('reflection_id', 'unknown')}"
            )
            output.append(f"🏷️ Tags: {', '.join(result.get('tags', []))}")
        else:
            output.append("⚠️ Reflection storage skipped")
        output.append("\n✅ Context preserved before compaction")
        return "\n".join(output)
    else:
        return f"❌ Pre-compact sync failed: {result.get('error', 'unknown error')}"


async def _get_tools_impl() -> dict[str, Any]:
    return compat_tools


def register_session_tools(mcp_server: FastMCP) -> None:
    """Register all session management tools with the MCP server."""
    mcp.tool()(_start_impl_1)
    mcp.tool()(_checkpoint_impl_1)
    mcp.tool()(_end_impl_1)
    mcp.tool()(_status_impl_1)
    mcp.tool()(_health_check_impl)
    mcp.tool()(_server_info_impl)
    mcp.tool()(_ping_impl)
    mcp.tool()(_pre_compact_sync_impl_1)
    compat_tools = {
        name: SimpleNamespace(function=tool, fn=tool, parameters={"properties": {}})
        for name, tool in {
            "start": start,
            "checkpoint": checkpoint,
            "end": end,
            "status": status,
            "health_check": health_check,
            "server_info": server_info,
            "ping": ping,
            "pre_compact_sync": pre_compact_sync,
        }.items()
    }
    mcp.tool()(_get_tools_impl)
    mcp_server.get_tools = get_tools
    mcp_server.tools = compat_tools
    mcp_server._tools = compat_tools
