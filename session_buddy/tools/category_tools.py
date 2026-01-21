"""MCP tools for Category Evolution (Phase 5).

This module provides MCP tools for managing and interacting with the
category evolution system.
"""

from typing import Any

from session_buddy.memory.category_evolution import (
    CategoryEvolutionEngine,
    TopLevelCategory,
)


async def get_evolution_engine() -> CategoryEvolutionEngine:
    """Get or create the category evolution engine.

    Returns:
        Initialized CategoryEvolutionEngine instance
    """
    # TODO: Implement singleton pattern or DI integration
    engine = CategoryEvolutionEngine()
    await engine.initialize()
    return engine


async def get_subcategories(
    category: str,
) -> dict[str, Any]:
    """Get all subcategories for a top-level category.

    Args:
        category: Top-level category name (facts, preferences, skills, rules, context)

    Returns:
        Dictionary with subcategories list and statistics
    """
    try:
        cat_enum = TopLevelCategory(category.lower())
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid category: {category}. Valid options: facts, preferences, skills, rules, context",
        }

    engine = await get_evolution_engine()
    subcategories = engine.get_subcategories(cat_enum)

    return {
        "success": True,
        "category": category,
        "subcategory_count": len(subcategories),
        "subcategories": [
            {
                "id": sc.id,
                "name": sc.name,
                "keywords": sc.keywords,
                "memory_count": sc.memory_count,
                "created_at": sc.created_at.isoformat(),
                "updated_at": sc.updated_at.isoformat(),
            }
            for sc in subcategories
        ],
    }


async def evolve_categories(
    category: str,
    memory_count_threshold: int = 10,
) -> dict[str, Any]:
    """Trigger category evolution for a top-level category.

    This will reorganize subcategories based on recent memories.

    Args:
        category: Top-level category name to evolve
        memory_count_threshold: Minimum number of new memories since last evolution

    Returns:
        Dictionary with evolution results
    """
    try:
        cat_enum = TopLevelCategory(category.lower())
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid category: {category}",
        }

    engine = await get_evolution_engine()

    # TODO: Fetch memories for this category from database
    # For now, return a message indicating this needs integration
    # memories = await _fetch_category_memories(cat_enum, limit=1000)

    return {
        "success": True,
        "category": category,
        "message": "Category evolution triggered. Database integration pending.",
        "subcategory_count": len(engine.get_subcategories(cat_enum)),
        "note": "This tool requires database integration to fetch category memories.",
    }


async def assign_memory_subcategory(
    memory_id: str,
    content: str,
    category: str | None = None,
    use_fingerprint: bool = True,
) -> dict[str, Any]:
    """Manually assign a memory to a subcategory.

    Args:
        memory_id: ID of the memory to assign
        content: Memory content for category detection
        category: Top-level category name (auto-detected if None)
        use_fingerprint: Whether to use fingerprint pre-filtering

    Returns:
        Dictionary with assignment result
    """
    # TODO: Fetch memory with embedding and fingerprint from database
    # For now, create a mock memory
    memory = {
        "id": memory_id,
        "content": content,
        "embedding": None,  # TODO: Generate embedding
        "fingerprint": None,  # TODO: Generate fingerprint
    }

    engine = await get_evolution_engine()

    if category:
        try:
            cat_enum = TopLevelCategory(category.lower())
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid category: {category}",
            }
    else:
        cat_enum = None

    result = await engine.assign_subcategory(
        memory=memory,
        category=cat_enum,
        use_fingerprint_prefilter=use_fingerprint,
    )

    return {
        "success": True,
        "memory_id": memory_id,
        "category": result.category.value,
        "subcategory": result.subcategory,
        "confidence": result.confidence,
        "method": result.method,
    }


async def category_stats(
    category: str | None = None,
) -> dict[str, Any]:
    """Get category evolution statistics.

    Args:
        category: Specific category to get stats for, or None for all categories

    Returns:
        Dictionary with category statistics
    """
    engine = await get_evolution_engine()

    if category:
        try:
            cat_enum = TopLevelCategory(category.lower())
            subcategories = engine.get_subcategories(cat_enum)

            return {
                "success": True,
                "category": category,
                "subcategory_count": len(subcategories),
                "total_memories": sum(sc.memory_count for sc in subcategories),
                "subcategories": [
                    {
                        "name": sc.name,
                        "memory_count": sc.memory_count,
                        "keyword_count": len(sc.keywords),
                    }
                    for sc in subcategories
                ],
            }
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid category: {category}",
            }
    else:
        # Stats for all categories
        all_stats = {}
        for cat in TopLevelCategory:
            subcategories = engine.get_subcategories(cat)
            all_stats[cat.value] = {
                "subcategory_count": len(subcategories),
                "total_memories": sum(sc.memory_count for sc in subcategories),
            }

        return {
            "success": True,
            "categories": all_stats,
        }


def register_category_tools(mcp: Any) -> None:
    """Register all category evolution tools with the MCP server.

    Args:
        mcp: FastMCP instance to register tools with
    """
    mcp.tool()(get_subcategories)
    mcp.tool()(evolve_categories)
    mcp.tool()(assign_memory_subcategory)
    mcp.tool()(category_stats)
