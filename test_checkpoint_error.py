#!/usr/bin/env python3
"""Reproduce the checkpoint tool unhashable error."""

import asyncio
import sys
from pathlib import Path

# Add session-buddy to path
sys.path.insert(0, str(Path(__file__).parent))


async def test_checkpoint_call():
    """Test calling the checkpoint tool directly."""
    from mcp.types import CallToolRequestParams
    from session_buddy.server import mcp

    # Create params exactly as Claude Code would
    params = CallToolRequestParams(
        name="checkpoint",
        arguments={"working_directory": "/Users/les/Projects/raindropio-mcp"},
    )

    print(f"✅ Created params: {params}")

    # Try to call the tool
    try:
        # This should trigger the error if it exists
        result = await mcp._call_tool("checkpoint", params.arguments or {})
        print(f"✅ Tool call succeeded: {result}")
    except Exception as e:
        print(f"❌ Tool call failed: {e}")
        import traceback

        traceback.print_exc()

    # Try to hash the params (this should fail)
    try:
        hash_val = hash(params)
        print(f"✅ Hash succeeded: {hash_val}")
    except TypeError as e:
        print(f"⚠️  Hash failed (expected): {e}")


if __name__ == "__main__":
    asyncio.run(test_checkpoint_call())
