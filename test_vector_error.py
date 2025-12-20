#!/usr/bin/env python3
"""Test script to reproduce Vector import error."""

import asyncio
import traceback


async def test_vector_error():
    """Reproduce the Vector error."""
    # Simulate tools unavailable
    from session_buddy.tools import memory_tools
    from session_buddy.tools.memory_tools import _store_reflection_impl

    memory_tools._reflection_tools_available = False

    result = await _store_reflection_impl("Test content")
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(test_vector_error())
