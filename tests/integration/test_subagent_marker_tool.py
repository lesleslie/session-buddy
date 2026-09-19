"""End-to-end integration test for the ``subagent_marker`` MCP tool.

Per Bodai MCP-backend-wiring discipline (``.claude/decisions/mcp-backend-wiring-discipline.md``),
every registered tool must have a working data feed and an integration test
asserting non-empty results. This is the integration test for the
subagent lockfile marker tool.

Builds a real FastMCP app, registers the tool, and exercises the wire
contract via ``app.list_tools()`` (the same way production clients see it).

Note: ``session_buddy.mcp.tools.__init__`` transitively imports
``agents_tools`` → ``agent_schema`` → ``mcp_common.canonical_schemas._validators``
which is missing in the installed ``mcp-common==0.26.4`` (a pre-existing
session-buddy environment issue, unrelated to this tool). We pre-stub
the missing submodule in ``sys.modules`` so the package init completes
without dragging in the unrelated broken chain.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Pre-import stub: bypass the unrelated broken agents_tools chain so the
# package init can complete. This is a TEST-ONLY workaround for an
# environment issue in session-buddy that's outside the scope of the
# subagent lockfile producer work.
# ---------------------------------------------------------------------------

_VALIDATORS_STUB = types.ModuleType("mcp_common.canonical_schemas._validators")
_VALIDATORS_STUB.NAME_OR_SERVER_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
# Use direct assignment (not setdefault) so we override any pre-existing
# entry — pytest's collection may import siblings via conftest.py that
# already populated ``sys.modules`` with a partial module object.
sys.modules["mcp_common.canonical_schemas._validators"] = _VALIDATORS_STUB


# ---------------------------------------------------------------------------
# FastMCP app binding (mirrors production wiring)
# ---------------------------------------------------------------------------


def _build_app() -> Any:
    """Build a fresh FastMCP app with the subagent_marker tools registered."""
    from fastmcp import FastMCP

    # Re-install the stub at call time — pytest's collection may have
    # imported sibling modules that wiped our pre-stub from sys.modules.
    sys.modules["mcp_common.canonical_schemas._validators"] = _VALIDATORS_STUB

    from session_buddy.mcp.tools.subagent_marker import (
        register_subagent_marker_tools,
    )

    app = FastMCP("session-buddy-subagent-marker-test")
    register_subagent_marker_tools(app)
    return app


async def _resolve_tool(app: Any, name: str) -> Any:
    """Return the registered tool callable by its public name."""
    tools = await app.list_tools()
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool.fn
    registered = [getattr(t, "name", "?") for t in tools]
    msg = f"tool {name!r} not found; registered: {registered}"
    raise KeyError(msg)


# ---------------------------------------------------------------------------
# Tool registration smoke
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_subagent_marker_tool_is_registered() -> None:
    """The tool is exposed on the FastMCP app under its public name."""
    app = _build_app()
    names = {getattr(t, "name", None) for t in await app.list_tools()}
    assert "subagent_marker" in names


# ---------------------------------------------------------------------------
# Wire-shape contract
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_subagent_marker_mark_creates_lockfile(tmp_path: Path) -> None:
    """Mark action writes the lockfile with a JSON payload and returns success."""
    app = _build_app()
    tool = await _resolve_tool(app, "subagent_marker")

    result_str = await tool(
        working_dir=str(tmp_path),
        action="mark",
    )
    result = json.loads(result_str)

    assert result["success"] is True
    assert result["action"] == "mark"
    assert result["lockfile_path"] == str(
        tmp_path / ".session-buddy" / "subagent.lock"
    )

    lock = tmp_path / ".session-buddy" / "subagent.lock"
    assert lock.exists()
    payload = json.loads(lock.read_text())
    assert {"pid", "started_at_ms", "node_id", "parent_agent_id"} <= payload.keys()


@pytest.mark.integration
async def test_subagent_marker_clear_removes_lockfile(tmp_path: Path) -> None:
    """Clear action unlinks the lockfile."""
    app = _build_app()
    tool = await _resolve_tool(app, "subagent_marker")

    # Mark first so there's something to clear.
    await tool(working_dir=str(tmp_path), action="mark")
    lock = tmp_path / ".session-buddy" / "subagent.lock"
    assert lock.exists()

    result_str = await tool(working_dir=str(tmp_path), action="clear")
    result = json.loads(result_str)
    assert result["success"] is True
    assert result["action"] == "clear"
    assert not lock.exists()


@pytest.mark.integration
async def test_subagent_marker_rejects_invalid_action(tmp_path: Path) -> None:
    """Invalid actions are surfaced as structured errors, not raised."""
    app = _build_app()
    tool = await _resolve_tool(app, "subagent_marker")

    result_str = await tool(
        working_dir=str(tmp_path),
        action="toggle",  # not in {mark, clear}
    )
    result = json.loads(result_str)
    assert result["success"] is False
    assert result["error_code"] == "invalid_action"
    assert "toggle" in result["error"]


@pytest.mark.integration
async def test_subagent_marker_rejects_relative_working_dir(tmp_path: Path) -> None:
    """Relative paths are rejected at the boundary (defense in depth)."""
    app = _build_app()
    tool = await _resolve_tool(app, "subagent_marker")

    result_str = await tool(working_dir="relative/path", action="mark")
    result = json.loads(result_str)
    assert result["success"] is False
    assert result["error_code"] == "invalid_working_dir"


@pytest.mark.integration
async def test_subagent_marker_rejects_nonexistent_dir(tmp_path: Path) -> None:
    """Non-existent directories are surfaced as structured errors."""
    app = _build_app()
    tool = await _resolve_tool(app, "subagent_marker")

    result_str = await tool(
        working_dir=str(tmp_path / "does-not-exist"),
        action="mark",
    )
    result = json.loads(result_str)
    assert result["success"] is False
    assert result["error_code"] == "not_a_directory"


@pytest.mark.integration
async def test_subagent_marker_clear_is_idempotent(tmp_path: Path) -> None:
    """Clearing a non-existent lockfile succeeds (matches LockfileSignalSource semantics)."""
    app = _build_app()
    tool = await _resolve_tool(app, "subagent_marker")

    # Never marked; clear should still succeed.
    result_str = await tool(working_dir=str(tmp_path), action="clear")
    result = json.loads(result_str)
    assert result["success"] is True
    assert result["action"] == "clear"
