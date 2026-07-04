"""Re-export shim for ``session_buddy.tools.search_tools``.

Mirrors :mod:`session_buddy.tools.memory_tools` — exposes module-level
wrappers for the MCP tool closures (``quick_search``, ``search_by_concept``,
``search_code``, ``reflection_stats``) so callers and the type checker can
import them from the conventional ``session_buddy.tools.search_tools`` path.
"""

from __future__ import annotations

from session_buddy.mcp.tools.memory.search_tools import register_search_tools
from session_buddy.mcp.tools.memory.search_tools import (
    quick_search as _quick_search_impl,  # ty: ignore[unresolved-import]
    reflection_stats as _reflection_stats_impl,  # ty: ignore[unresolved-import]
    search_by_concept as _search_by_concept_impl,  # ty: ignore[unresolved-import]
    search_code as _search_code_impl,  # ty: ignore[unresolved-import]
    store_reflection as _store_reflection_impl,  # ty: ignore[unresolved-import]
)


async def store_reflection(
    content: str, tags: list[str] | None = None
) -> str:
    """Store an important insight or reflection for future reference."""
    return await _store_reflection_impl(content, tags)


async def quick_search(
    query: str,
    project: str | None = None,
    min_score: float = 0.7,
    limit: int = 5,
) -> str:
    """Quick search for an overview of the top result."""
    return await _quick_search_impl(query, project, min_score, limit)


async def search_by_concept(
    concept: str,
    include_files: bool = True,
    limit: int = 10,
    project: str | None = None,
    min_score: float = 0.7,
) -> str:
    """Search for conversations about a specific development concept."""
    return await _search_by_concept_impl(
        concept, include_files, limit, project, min_score
    )


async def search_code(
    query: str,
    pattern_type: str | None = None,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for code patterns across indexed repositories."""
    return await _search_code_impl(query, pattern_type, limit, project)


async def reflection_stats() -> str:
    """Get statistics about the reflection database."""
    return await _reflection_stats_impl()


__all__ = [
    "register_search_tools",
    "store_reflection",
    "quick_search",
    "search_by_concept",
    "search_code",
    "reflection_stats",
]