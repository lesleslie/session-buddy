#!/usr/bin/env python3
"""Monkey-patch CallToolRequestParams and Context to make them hashable and log when hash is called."""

import traceback

from fastmcp.server.context import Context
from mcp.types import CallToolRequestParams

# Store the original hash methods
_original_params_hash = CallToolRequestParams.__hash__
_original_context_hash = Context.__hash__


def _debug_params_hash(self):
    """Debug hash method for CallToolRequestParams that logs the stack trace when called."""
    print("=" * 80)
    print("⚠️  HASH CALLED ON CallToolRequestParams!")
    print("=" * 80)
    print(f"Instance: {self}")
    print(f"Name: {self.name}")
    print(f"Arguments: {self.arguments}")
    print("\nStack trace:")
    for line in traceback.format_stack():
        print(line.strip())
    print("=" * 80)

    # Make it hashable by using the name and a tuple of sorted arguments
    args_tuple = tuple(sorted(self.arguments.items())) if self.arguments else ()

    return hash((self.name, args_tuple))


def _debug_context_hash(self):
    """Debug hash method for Context that logs the stack trace when called."""
    print("=" * 80)
    print("⚠️  HASH CALLED ON Context!")
    print("=" * 80)
    print(f"Instance: {self}")
    print(f"FastMCP: {getattr(self, 'fastmcp', None)}")
    print("\nStack trace:")
    for line in traceback.format_stack():
        print(line.strip())
    print("=" * 80)

    # Make it hashable by using id() - each Context instance gets a unique hash
    return hash(id(self))


# Monkey-patch the hash methods
CallToolRequestParams.__hash__ = _debug_params_hash  # type: ignore[assignment]
Context.__hash__ = _debug_context_hash  # type: ignore[method-assign]

print("✅ CallToolRequestParams and Context patched to be hashable with debug logging")
