"""Vulture whitelist for false positives.

Add patterns here that vulture flags but are actually used:
- Library API exports (MCP tools, public functions)
- Dynamic attribute access
- Test fixtures
- Protocol implementations
"""

# Example: Public API exports that are used externally
# from session_buddy.token_optimizer import ACBChunkCache  # noqa: F401
