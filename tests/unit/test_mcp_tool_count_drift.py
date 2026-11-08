"""CI guard: pin session-buddy MCP tool count to prevent docs drift.

Refreshed 2026-08-19 from stale `42 MCP tools` claim in README.md:330 and
CLAUDE.md:443. The actual FULL profile count is 199, verified via
``SESSION_BUDDY_TOOL_PROFILE=full`` registration log.

The count is measured against the *live* surface -- the instance the
server actually serves -- via
``session_buddy.server_optimized.build_live_server()``. It used to be
measured against ``session_buddy.mcp.server``, whose import applied the
profile; that module is only imported by tests, so the running server
served a smaller, hard-coded surface than the count claimed.

If this test fails, regenerate the count with:

    cd /Users/les/Projects/session-buddy && \\
        SESSION_BUDDY_TOOL_PROFILE=full uv run python -c \\
        "import asyncio; from session_buddy.server_optimized import build_live_server; \\
        print(len(asyncio.run(build_live_server().list_tools())))"

Then update this assertion AND the README/CLAUDE.md tool counts in the
same commit.
"""

from __future__ import annotations

import asyncio

EXPECTED_FULL_TOOL_COUNT = 226


def test_full_profile_tool_count_pinned() -> None:
    """Pin the FULL profile tool count to prevent doc drift.

    Reads ``SESSION_BUDDY_TOOL_PROFILE`` from env. The default registration
    path runs at import time, so this test relies on whatever profile the
    test session was bootstrapped with. To force a fresh count, set
    ``SESSION_BUDDY_TOOL_PROFILE=full`` before invoking pytest.
    """
    try:
        from session_buddy.server_optimized import build_live_server
    except ImportError:
        pytest_skip("session_buddy.server_optimized unavailable")

    tools = asyncio.run(build_live_server().list_tools())
    assert len(tools) == EXPECTED_FULL_TOOL_COUNT, (
        f"Tool count drifted from {EXPECTED_FULL_TOOL_COUNT} to {len(tools)}. "
        "Update the README/CLAUDE.md tool counts + this test in the same commit."
    )


def pytest_skip(reason: str) -> None:
    import pytest

    pytest.skip(reason)
