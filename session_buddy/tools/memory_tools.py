"""Re-export shim for ``session_buddy.tools.memory_tools``.

The MCP ``@mcp.tool()`` decorator binds tool functions as closures inside
``register_memory_tools(mcp)``, so the canonical names (``store_reflection``,
``quick_search``, ``search_by_concept``, ``reflection_stats``) are not present
at module scope. Tests and external callers historically imported them from
``session_buddy.tools.memory_tools``; this shim exposes module-level wrappers
that delegate to the underlying ``_*_impl`` functions so the names resolve at
type-check time and at runtime.

The wrappers are intentionally thin — the real work lives in the impls.
"""

from __future__ import annotations

# NOTE: The ``_impl`` aliases below resolve to ``_*_impl`` functions in
# ``session_buddy.mcp.tools.memory.memory_tools``. Their public wrappers
# (``store_reflection``, ``quick_search``, etc.) are closures inside
# ``register_memory_tools(mcp)`` and so are not directly importable by
# name. We import the *impls* and call them — the public-name wrappers
# at the bottom of this file are what external callers (and tests) use.
from session_buddy.mcp.tools.memory.memory_tools import (
    register_memory_tools,
)
from session_buddy.mcp.tools.memory.memory_tools import (
    quick_search as _quick_search_impl,  # ty: ignore[unresolved-import]
    reflection_stats as _reflection_stats_impl,  # ty: ignore[unresolved-import]
    search_by_concept as _search_by_concept_impl,  # ty: ignore[unresolved-import]
    store_reflection as _store_reflection_impl,  # ty: ignore[unresolved-import]
)


async def store_reflection(
    content: str, tags: list[str] | None = None
) -> str:
    """Store an important insight or reflection for future reference."""
    return await _store_reflection_impl(content, tags)


async def quick_search(
    query: str,
    min_score: float = 0.7,
    project: str | None = None,
) -> str:
    """Quick search that returns only the count and top result for fast overview."""
    return await _quick_search_impl(query, min_score, project)


async def search_by_concept(
    concept: str,
    include_files: bool = True,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for conversations about a specific development concept."""
    return await _search_by_concept_impl(
        concept, include_files, limit, project
    )


async def reflection_stats(project: str | None = None) -> str:
    """Get statistics about the reflection database."""
    return await _reflection_stats_impl()


async def search_reflections(
    query: str,
    limit: int = 10,
    project: str | None = None,
) -> list[dict[str, object]]:
    """Search reflections by semantic similarity or text match.

    Thin module-level wrapper that retrieves the active ``ReflectionDatabase``
    and delegates to :func:`session_buddy.reflection.search.search_reflections`.
    Provided so callers and type checkers can resolve the name from the
    conventional ``session_buddy.tools.memory_tools`` path.
    """
    from session_buddy.reflection.search import (
        search_reflections as _search_reflections,
    )
    from session_buddy.reflection_tools import (
        get_reflection_database,
    )

    db = await get_reflection_database()
    return await _search_reflections(  # type: ignore[no-any-return]
        db=db,
        query=query,
        query_embedding=None,
        limit=limit,
        project=project,
    )


__all__ = [
    "register_memory_tools",
    "store_reflection",
    "quick_search",
    "search_by_concept",
    "search_reflections",
    "reflection_stats",
]