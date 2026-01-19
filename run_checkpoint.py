#!/usr/bin/env python3
"""Run session checkpoint via MCP tool call."""

import asyncio
import json
from pathlib import Path

# Add project to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from session_buddy.tools.session_tools import _checkpoint_impl


async def main():
    """Run checkpoint and display results."""
    print("Running session checkpoint...")
    print("=" * 80)

    try:
        result = await _checkpoint_impl(working_directory=None)
        print(result)
        print("\n" + "=" * 80)
        print("✅ Checkpoint complete!")

        # Try to extract quality score
        if "Quality Score" in result:
            # Extract score using simple parsing
            for line in result.split('\n'):
                if "Quality Score" in line:
                    print(f"\n📊 {line.strip()}")
        elif "quality_score" in result.lower():
            print(f"\n📊 {result}")

    except Exception as e:
        print(f"❌ Checkpoint failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
