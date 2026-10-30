"""The running server's tool surface must include the task-system tools.

Regression (2026-10-29). The live server built its FastMCP instance from
``session_buddy.server_optimized`` and registered ten hard-coded tool
groups there. The profile dispatch -- the only path to the remaining
groups, the task system among them -- was never applied to that
instance, so the seven ``tasks_*`` tools were absent from the running
server even though ``REGISTRATION_MAP`` listed them and the launchd
plist set ``SESSION_BUDDY_TOOL_PROFILE=full``.

This is not only a missing feature. The ``bodai_events`` health feed
counts successful task-event publishes, and the task tools are the only
thing that publishes them -- so with no task tools on the server the
feed's ``entities_count`` stayed at 0 and ``/health`` reported
``warming_up`` forever.

The tests below assert the surface of the instance the *server* serves.
They deliberately do not apply the profile themselves: doing so would
make them pass against the very bug they guard against.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from typing import Any

TASK_SYSTEM_TOOLS = frozenset(
    {
        "tasks_create",
        "tasks_list",
        "tasks_get",
        "tasks_update",
        "tasks_complete",
        "tasks_search",
        "tasks_history",
    }
)


def _tool_names(server: Any) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_the_launch_path_completes_the_tool_surface(monkeypatch: Any) -> None:
    """``run_server`` must hand the launcher a profiled server.

    This exercises the real launch path rather than the profile helper
    directly: ``mcp_common.server.launch`` is stubbed out, so the only
    thing under test is what ``run_server`` puts in ``build_server``.
    """
    from session_buddy import server_optimized

    captured: dict[str, Any] = {}

    async def fake_launch(**kwargs: Any) -> None:
        captured["server"] = kwargs["build_server"]()

    monkeypatch.setattr("mcp_common.server.launch", fake_launch)
    server_optimized.run_server()

    server = captured["server"]
    missing = TASK_SYSTEM_TOOLS - _tool_names(server)
    assert not missing, (
        f"The server the launcher serves is missing task-system tools: "
        f"{sorted(missing)}. The profile dispatch did not run against the "
        "instance the server serves, so the task system -- and the events "
        "it publishes -- are unreachable at runtime."
    )


def test_the_profile_env_var_reaches_the_live_path() -> None:
    """``SESSION_BUDDY_TOOL_PROFILE`` must change the live tool surface.

    Before the fix the live path ignored the profile entirely -- it
    registered a fixed set of groups and read no profile at all, so the
    launchd plist's ``SESSION_BUDDY_TOOL_PROFILE=full`` was read by
    nobody and every profile produced the same surface.

    A subprocess is used because the profile is applied once per process.
    """
    script = (
        "import asyncio;"
        "from session_buddy.server_optimized import build_live_server;"
        "print(len(asyncio.run(build_live_server().list_tools())))"
    )

    def count_for(profile: str) -> int:
        env = {**os.environ, "SESSION_BUDDY_TOOL_PROFILE": profile}
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        return int(result.stdout.strip().splitlines()[-1])

    minimal = count_for("minimal")
    full = count_for("full")
    assert minimal < full, (
        f"The live surface ignores SESSION_BUDDY_TOOL_PROFILE: minimal and "
        f"full both yield {full} tools."
    )
