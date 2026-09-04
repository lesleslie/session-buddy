"""CI guard: pin session-buddy MCP tool count to prevent docs drift.

Refreshed 2026-08-19 from stale `42 MCP tools` claim in README.md:330 and
CLAUDE.md:443. The actual FULL profile count is 199, verified via
``SESSION_BUDDY_TOOL_PROFILE=full`` registration log.

If this test fails, regenerate the count with:

    cd /Users/les/Projects/session-buddy && \\
        SESSION_BUDDY_TOOL_PROFILE=full uv run python -c \\
        "import asyncio; from session_buddy.mcp.server import mcp; \\
        print(len(asyncio.run(mcp.list_tools())))"

Then update this assertion AND README.md:330 + CLAUDE.md:443 in the same commit.
"""

from __future__ import annotations

import asyncio

EXPECTED_FULL_TOOL_COUNT = 200


def test_full_profile_tool_count_pinned() -> None:
    """Pin the FULL profile tool count to prevent doc drift.

    Reads ``SESSION_BUDDY_TOOL_PROFILE`` from env. The default registration
    path runs at import time, so this test relies on whatever profile the
    test session was bootstrapped with. To force a fresh count, set
    ``SESSION_BUDDY_TOOL_PROFILE=full`` before invoking pytest.
    """
    try:
        from session_buddy.mcp.server import mcp
    except ImportError:
        pytest_skip("session_buddy.mcp.server unavailable")

    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == EXPECTED_FULL_TOOL_COUNT, (
        f"Tool count drifted from {EXPECTED_FULL_TOOL_COUNT} to {len(tools)}. "
        "Update README.md:330 + CLAUDE.md:443 + this test in the same commit."
    )


def pytest_skip(reason: str) -> None:
    import pytest

    pytest.skip(reason)
