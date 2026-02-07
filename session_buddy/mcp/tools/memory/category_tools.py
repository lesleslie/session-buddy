"""MCP tools for Category Evolution (Phase 5).

This module provides MCP tools for managing and interacting with the
category evolution system.
"""

import asyncio
from typing import Any

from session_buddy.memory.category_evolution import (
    CategoryEvolutionEngine,
    TopLevelCategory,
)

# Module-level singleton instance and lock
_evolution_engine: CategoryEvolutionEngine | None = None
_engine_lock = asyncio.Lock()


async def get_evolution_engine() -> CategoryEvolutionEngine:
    """Get or create the category evolution engine (thread-safe singleton).

    Uses double-checked locking pattern for efficient singleton access
    in async contexts.

    Returns:
        Initialized CategoryEvolutionEngine instance
    """
    global _evolution_engine

    # Fast path: return existing instance
    if _evolution_engine is not None:
        return _evolution_engine

    # Slow path: create new instance with lock
    async with _engine_lock:
        # Double-check: another coroutine might have created it
        if _evolution_engine is not None:
            return _evolution_engine

        # Create and initialize the engine
        _evolution_engine = CategoryEvolutionEngine()
        await _evolution_engine.initialize()

    return _evolution_engine


async def _fetch_category_memories(
    category: TopLevelCategory,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch memories for a specific category from the database.

    Args:
        category: Top-level category to fetch memories for
        limit: Maximum number of memories to fetch

    Returns:
        List of memory dictionaries with id, content, embedding, and fingerprint
    """
    try:
        from session_buddy.reflection_tools import get_reflection_database

        db = await get_reflection_database()  # type: ignore[misc]

        # Search for reflections with the category tag
        # Use a broad search to get memories, then filter by category tag
        query = category.value  # Use category name as search term
        reflections = await db.search_reflections(
            query=query,
            limit=limit,
            use_embeddings=True,
        )

        # Convert reflections to memory format for evolution engine
        memories = []
        for refl in reflections:
            memory = {
                "id": refl.get("id", ""),
                "content": refl.get("content", ""),
                "embedding": refl.get("embedding"),
                "fingerprint": refl.get("fingerprint"),
                "tags": refl.get("tags", []) or [],
                "created_at": refl.get("created_at"),
            }

            # Only include memories that have the category tag
            tags: list[str] = memory.get("tags") or []
            if category.value in tags:
                memories.append(memory)

        return memories

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching memories for category {category.value}: {e}")
        return []


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
    temporal_decay_enabled: bool = True,
    temporal_decay_days: int = 90,
    archive_option: bool = False,
    min_silhouette_score: float = 0.2,
) -> dict[str, Any]:
    """Trigger category evolution for a top-level category.

    This will reorganize subcategories based on recent memories, with optional
    temporal decay to remove stale subcategories.

    Args:
        category: Top-level category name to evolve
        memory_count_threshold: Minimum number of memories needed for evolution
        temporal_decay_enabled: Whether to apply temporal decay (default: True)
        temporal_decay_days: Days of inactivity before decay (default: 90)
        archive_option: If True, archive stale subcategories; if False, delete them
        min_silhouette_score: Minimum acceptable silhouette score (default: 0.2)

    Returns:
        Dictionary with comprehensive evolution results including:
        - success: Boolean indicating success
        - before_state: Dict with before metrics (subcategory_count, silhouette, total_memories)
        - after_state: Dict with after metrics
        - decay_results: Dict with temporal decay results
        - duration_ms: Evolution duration in milliseconds
    """
    try:
        cat_enum = TopLevelCategory(category.lower())
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid category: {category}",
        }

    engine = await get_evolution_engine()

    # Fetch memories for this category from database
    memories = await _fetch_category_memories(cat_enum, limit=1000)

    # Check if we have enough memories to trigger evolution
    if len(memories) < memory_count_threshold:
        return {
            "success": True,
            "category": category,
            "message": f"Insufficient memories for evolution. Found {len(memories)}, need {memory_count_threshold}.",
            "subcategory_count": len(engine.get_subcategories(cat_enum)),
            "memory_count": len(memories),
            "threshold": memory_count_threshold,
        }

    # Create evolution config
    from session_buddy.memory.evolution_config import EvolutionConfig

    config = EvolutionConfig(
        temporal_decay_enabled=temporal_decay_enabled,
        temporal_decay_days=temporal_decay_days,
        archive_option=archive_option,
        min_silhouette_score=min_silhouette_score,
    )

    # Validate config
    validation_errors = config.validate()
    if validation_errors:
        return {
            "success": False,
            "category": category,
            "error": f"Invalid configuration: {', '.join(validation_errors)}",
        }

    # Perform evolution
    try:
        result = await engine.evolve_category(cat_enum, memories, config)

        # Add human-readable summary
        silhouette_delta = (
            result["after_state"]["silhouette"] - result["before_state"]["silhouette"]
        )

        if silhouette_delta > 0.1:
            level = "Significant improvement"
        elif silhouette_delta > 0:
            level = "Moderate improvement"
        elif silhouette_delta > -0.1:
            level = "Minor change (acceptable)"
        else:
            level = f"Quality decreased: {silhouette_delta:.2f} ⚠️"

        count_delta = (
            result["after_state"]["subcategory_count"]
            - result["before_state"]["subcategory_count"]
        )

        if count_delta > 0:
            count_change = f"Created {count_delta} subcategories"
        elif count_delta < 0:
            count_change = f"Removed {abs(count_delta)} subcategories"
        else:
            count_change = "Maintained subcategory count"

        freed = result["decay_results"].get("freed_space", 0)
        storage_msg = f" freed {_format_bytes(freed)}" if freed > 0 else ""

        result["summary"] = (
            f"{level} (silhouette: {silhouette_delta:+.2f}), "
            f"{count_change},{storage_msg}."
        )

        return result

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error during category evolution: {e}")
        return {
            "success": False,
            "category": category,
            "error": str(e),
        }


def _format_bytes(bytes_count: float) -> str:
    """Format bytes as human-readable string.

    Args:
        bytes_count: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 KB", "2.3 MB")
    """
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_count < 1024:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f} TB"


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
    # Generate embedding for the content
    embedding = None
    try:
        from session_buddy.reflection_tools import get_reflection_database

        db = await get_reflection_database()  # type: ignore[misc]
        embedding = await db._generate_embedding(content)
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to generate embedding: {e}")

    # Generate fingerprint for the content
    fingerprint = None
    try:
        from session_buddy.utils.fingerprint import MinHashSignature

        fp_obj = MinHashSignature.from_text(content)
        fingerprint = fp_obj.to_bytes()
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to generate fingerprint: {e}")

    # Create memory dictionary with generated embedding and fingerprint
    memory = {
        "id": memory_id,
        "content": content,
        "embedding": embedding,
        "fingerprint": fingerprint,
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
        "embedding_generated": embedding is not None,
        "fingerprint_generated": fingerprint is not None,
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
