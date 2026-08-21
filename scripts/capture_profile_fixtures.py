"""Capture golden fixture of tool names at each ToolProfile level.

Modeled on W1.1 mahavishnu's capture script. Use before refactoring to lock
the current behavior; subsequent refactors must produce identical tool sets.

Usage:
    cd /Users/les/Projects/session-buddy
    uv run python scripts/capture_profile_fixtures.py [minimal|standard|full]

Default: capture all three profiles.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


async def _capture(profile: str) -> list[str]:
    """Import session_buddy.mcp.server with the given profile and list tools."""
    # Force the env var BEFORE importing server.py
    import os

    os.environ["SESSION_BUDDY_TOOL_PROFILE"] = profile

    # Reload to re-evaluate the registration loop with the new env var
    if "session_buddy.mcp.server" in sys.modules:
        del sys.modules["session_buddy.mcp.server"]
    if "session_buddy" in sys.modules:
        del sys.modules["session_buddy"]

    from session_buddy.mcp.server import mcp

    tools = await mcp.list_tools()
    return sorted(t.name for t in tools)


async def main(profiles: list[str]) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for profile in profiles:
        out_dir = FIXTURES / profile
        out_dir.mkdir(parents=True, exist_ok=True)
        names = await _capture(profile)
        (out_dir / "tool_names.json").write_text(json.dumps(names, indent=2))
        print(f"{profile}: {len(names)} tools captured → {out_dir}/tool_names.json")


if __name__ == "__main__":
    requested = sys.argv[1:] or ["minimal", "standard", "full"]
    asyncio.run(main(requested))
