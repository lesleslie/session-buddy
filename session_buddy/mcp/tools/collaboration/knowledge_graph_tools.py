#!/usr/bin/env python3
"""Knowledge Graph MCP tools for semantic memory management.

This module provides MCP tools for interacting with the DuckPGQ-based knowledge graph,
enabling semantic memory through entity-relationship modeling.

Refactored to use utility modules for reduced code duplication.
Phase 2: Added auto-discovery tools for relationship generation
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from session_buddy.utils.error_management import _get_logger
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from session_buddy.adapters.knowledge_graph_adapter import (
        KnowledgeGraphDatabaseAdapter as KnowledgeGraphDatabase,
    )


# ============================================================================
# Service Resolution
# ============================================================================


def _check_knowledge_graph_available() -> bool:
    """Check if knowledge graph dependencies are available."""
    try:
        import importlib.util

        return importlib.util.find_spec("duckdb") is not None
    except (ImportError, AttributeError):
        return False


async def _require_knowledge_graph() -> KnowledgeGraphDatabase:
    """Get knowledge graph database instance or raise error."""
    try:
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )
        from session_buddy.di import configure

        configure()
        kg = KnowledgeGraphDatabaseAdapter()
        await kg.initialize()
        return kg
    except Exception as e:
        msg = f"Knowledge graph not available: {e}"
        raise RuntimeError(msg) from e


async def _execute_kg_operation(
    operation_name: str, operation: Callable[[Any], Awaitable[str]]
) -> str:
    """Execute a knowledge graph operation with error handling."""
    try:
        async with await _require_knowledge_graph() as kg:
            return await operation(kg)
    except RuntimeError as e:
        return f"❌ {e!s}. Install dependencies: uv sync"
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


# ============================================================================
# Entity Extraction Patterns
# ============================================================================


ENTITY_PATTERNS = {
    "project": r"\b([A-Z][a-z]+-[a-z]+(?:-[a-z]+)*)\b",  # kebab-case projects
    "library": r"\b(ACB|FastMCP|DuckDB|pytest|pydantic|uvicorn)\b",
    "technology": r"\b(Python|JavaScript|TypeScript|Docker|Kubernetes)\b",
    "concept": r"\b(dependency injection|semantic memory|property graph|vector search)\b",
}


# ============================================================================
# Entity Operations
# ============================================================================


async def _create_entity_operation(
    kg: Any,
    name: str,
    entity_type: str,
    observations: list[str],
    properties: dict[str, Any],
) -> str:
    """Create an entity in the knowledge graph."""
    entity = await kg.create_entity(
        name=name,
        entity_type=entity_type,
        observations=observations,
        properties=properties,
    )

    lines = [
        f"✅ Entity '{name}' created successfully!",
        f"📊 Type: {entity_type}",
        f"🆔 ID: {entity['id']}",
    ]

    if observations:
        lines.append(f"📝 Observations: {len(observations)}")
    if properties:
        lines.append(f"⚙️ Properties: {', '.join(properties.keys())}")

    _get_logger().info(
        "Entity created",
        entity_name=name,
        entity_type=entity_type,
        observations_count=len(observations),
    )
    return "\n".join(lines)


async def _create_entity_impl(
    name: str,
    entity_type: str,
    observations: list[str] | None = None,
    properties: dict[str, Any] | None = None,
) -> str:
    """Create an entity in the knowledge graph."""

    async def operation_wrapper(kg: Any) -> str:
        return await _create_entity_operation(
            kg, name, entity_type, observations or [], properties or {}
        )

    return await _execute_kg_operation(
        "Create entity",
        operation_wrapper,
    )


async def _add_observation_operation(
    kg: Any, entity_name: str, observation: str
) -> str:
    """Add an observation (fact) to an existing entity."""
    success = await kg.add_observation(entity_name, observation)

    if not success:
        return f"❌ Entity '{entity_name}' not found"

    _get_logger().info(
        "Observation added",
        entity_name=entity_name,
        observation=observation[:100],
    )
    return "\n".join(
        [
            f"✅ Observation added to '{entity_name}'",
            f"📝 Observation: {observation}",
        ]
    )


async def _add_observation_impl(entity_name: str, observation: str) -> str:
    """Add an observation (fact) to an existing entity."""

    async def operation_wrapper(kg: Any) -> str:
        return await _add_observation_operation(kg, entity_name, observation)

    return await _execute_kg_operation(
        "Add observation",
        operation_wrapper,
    )


# ============================================================================
# Relationship Operations
# ============================================================================


async def _create_relation_operation(
    kg: Any,
    from_entity: str,
    to_entity: str,
    relation_type: str,
    properties: dict[str, Any],
) -> str:
    """Create a relationship between two entities."""
    relation = await kg.create_relation(
        from_entity=from_entity,
        to_entity=to_entity,
        relation_type=relation_type,
        properties=properties,
    )

    if not relation:
        return f"❌ One or both entities not found: {from_entity}, {to_entity}"

    lines = [
        f"✅ Relationship created: {from_entity} --[{relation_type}]--> {to_entity}",
        f"🆔 Relation ID: {relation['id']}",
    ]

    if properties:
        lines.append(f"⚙️ Properties: {', '.join(properties.keys())}")

    _get_logger().info(
        "Relation created",
        from_entity=from_entity,
        to_entity=to_entity,
        relation_type=relation_type,
    )
    return "\n".join(lines)


async def _create_relation_impl(
    from_entity: str,
    to_entity: str,
    relation_type: str,
    properties: dict[str, Any] | None = None,
) -> str:
    """Create a relationship between two entities."""

    async def operation_wrapper(kg: Any) -> str:
        return await _create_relation_operation(
            kg, from_entity, to_entity, relation_type, properties or {}
        )

    return await _execute_kg_operation(
        "Create relation",
        operation_wrapper,
    )


# ============================================================================
# Search Operations
# ============================================================================


def _format_entity_result(entity: dict[str, Any]) -> list[str]:
    """Format a single entity search result."""
    lines = [f"📌 {entity['name']} ({entity['entity_type']})"]

    observations = entity.get("observations")
    if observations:
        lines.append(f"   📝 Observations: {len(observations)}")
        if observations:
            preview = observations[0]
            lines.append(f"   └─ {preview[:80]}{'...' if len(preview) > 80 else ''}")

    lines.append("")
    return lines


def _format_batch_results(
    created: list[str],
    failed: list[tuple[str, str]],
) -> list[str]:
    """Format batch entity creation results."""
    lines = [
        "📦 Batch Entity Creation Results",
        "",
        f"Successfully Created: {len(created)}",
    ]

    if created:
        max_show = 10
        for name in created[:max_show]:
            lines.append(f"  • {name}")
        remaining = len(created) - max_show
        if remaining > 0:
            lines.append(f"  • and {remaining} more")

    if failed:
        lines.extend(("", f"Failed: {len(failed)}"))
        max_failed = 5
        for name, error in failed[:max_failed]:
            lines.append(f"  • {name}: {error}")
        remaining_failed = len(failed) - max_failed
        if remaining_failed > 0:
            lines.append(f"  • and {remaining_failed} more")

    return lines


async def _search_entities_operation(
    kg: Any, query: str, entity_type: str | None, limit: int
) -> str:
    """Search for entities by name or observations."""
    results = await kg.search_entities(
        query=query,
        entity_type=entity_type,
        limit=limit,
    )

    if not results:
        return f"🔍 No entities found matching '{query}'"

    lines = [f"🔍 Found {len(results)} entities matching '{query}':", ""]

    for entity in results:
        lines.extend(_format_entity_result(entity))

    _get_logger().info(
        "Entities searched",
        query=query,
        entity_type=entity_type,
        results_count=len(results),
    )
    return "\n".join(lines)


async def _search_entities_impl(
    query: str,
    entity_type: str | None = None,
    limit: int = 10,
) -> str:
    """Search for entities by name or observations."""

    async def operation_wrapper(kg: Any) -> str:
        return await _search_entities_operation(kg, query, entity_type, limit)

    return await _execute_kg_operation(
        "Search entities",
        operation_wrapper,
    )


def _format_relationship(rel: dict[str, Any], direction: str, entity_name: str) -> str:
    """Format a single relationship based on direction."""
    if direction == "outgoing" or (
        direction == "both" and rel["from_entity"] == entity_name
    ):
        return (
            f"  {rel['from_entity']} --[{rel['relation_type']}]--> {rel['to_entity']}"
        )
    return f"  {rel['from_entity']} <--[{rel['relation_type']}]-- {rel['to_entity']}"


async def _get_entity_relationships_operation(
    kg: Any, entity_name: str, relation_type: str | None, direction: str
) -> str:
    """Get all relationships for an entity."""
    relationships = await kg.get_relationships(
        entity_name=entity_name,
        relation_type=relation_type,
        direction=direction,
    )

    if not relationships:
        return f"🔍 No relationships found for '{entity_name}'"

    lines = [f"🔗 Found {len(relationships)} relationships for '{entity_name}':", ""]

    for rel in relationships:
        lines.append(_format_relationship(rel, direction, entity_name))

    _get_logger().info(
        "Relationships retrieved",
        entity_name=entity_name,
        relation_type=relation_type,
        direction=direction,
        count=len(relationships),
    )
    return "\n".join(lines)


async def _get_entity_relationships_impl(
    entity_name: str,
    relation_type: str | None = None,
    direction: str = "both",
) -> str:
    """Get all relationships for an entity."""

    async def operation_wrapper(kg: Any) -> str:
        return await _get_entity_relationships_operation(
            kg, entity_name, relation_type, direction
        )

    return await _execute_kg_operation(
        "Get entity relationships",
        operation_wrapper,
    )


# ============================================================================
# Path Finding
# ============================================================================


async def _find_path_operation(
    kg: Any, from_entity: str, to_entity: str, max_depth: int
) -> str:
    """Find paths between two entities using SQL/PGQ."""
    paths = await kg.find_path(
        from_entity=from_entity,
        to_entity=to_entity,
        max_depth=max_depth,
    )

    if not paths:
        return f"🔍 No path found between '{from_entity}' and '{to_entity}'"

    lines = [
        f"🛤️ Found {len(paths)} path(s) from '{from_entity}' to '{to_entity}':",
        "",
    ]

    for i, path in enumerate(paths, 1):
        lines.extend(
            [
                f"{i}. Path length: {path['path_length']} hop(s)",
                f"   {path['from_entity']} ➜ ... ➜ {path['to_entity']}",
                "",
            ]
        )

    _get_logger().info(
        "Paths found",
        from_entity=from_entity,
        to_entity=to_entity,
        paths_count=len(paths),
    )
    return "\n".join(lines)


async def _find_path_impl(
    from_entity: str,
    to_entity: str,
    max_depth: int = 5,
) -> str:
    """Find paths between two entities using SQL/PGQ."""

    async def operation_wrapper(kg: Any) -> str:
        return await _find_path_operation(kg, from_entity, to_entity, max_depth)

    return await _execute_kg_operation(
        "Find path",
        operation_wrapper,
    )


# ============================================================================
# Statistics
# ============================================================================


def _format_entity_types(entity_types: dict[str, int]) -> list[str]:
    """Format entity type counts for statistics output."""
    if not entity_types:
        return []

    lines = ["📊 Entity Types:"]
    lines.extend(f"   • {etype}: {count}" for etype, count in entity_types.items())
    lines.append("")
    return lines


def _format_relationship_types(relationship_types: dict[str, int]) -> list[str]:
    """Format relationship type counts for statistics output."""
    if not relationship_types:
        return []

    lines = ["🔗 Relationship Types:"]
    lines.extend(
        f"   • {rtype}: {count}" for rtype, count in relationship_types.items()
    )
    lines.append("")
    return lines


async def _get_knowledge_graph_stats_operation(kg: Any) -> str:
    """Get knowledge graph statistics with connectivity metrics."""
    stats = await kg.get_stats()

    lines = [
        "📊 Knowledge Graph Statistics",
        "",
        f"📌 Total Entities: {stats['total_entities']}",
        f"🔗 Total Relationships: {stats['total_relationships']}",
        "",
    ]

    # Phase 2: Connectivity metrics
    if "connectivity_ratio" in stats:
        lines.extend(
            [
                f"🔗 Connectivity Ratio: {stats['connectivity_ratio']:.3f}",
                f"📈 Average Degree: {stats['avg_degree']:.3f}",
                f"🏝️ Isolated Entities: {stats['isolated_entities']}",
                f"🧠 Embedding Coverage: {stats['embedding_coverage']:.1%}",
                "",
            ]
        )

    # Entity types
    entity_types = stats.get("entity_types", {})
    lines.extend(_format_entity_types(entity_types))

    # Relationship types
    relationship_types = stats.get("relationship_types", {})
    lines.extend(_format_relationship_types(relationship_types))

    if "database_path" in stats:
        lines.extend(
            [
                f"💾 Database: {stats['database_path']}",
            ]
        )

    _get_logger().info("Knowledge graph stats retrieved", **stats)
    return "\n".join(lines)


async def _get_knowledge_graph_stats_impl() -> str:
    """Get knowledge graph statistics."""
    return await _execute_kg_operation(
        "Get KG stats", _get_knowledge_graph_stats_operation
    )


# ============================================================================
# Entity Extraction
# ============================================================================


def _extract_patterns_from_context(context: str) -> dict[str, set[str]]:
    """Extract entity patterns from context text."""
    extracted: dict[str, set[str]] = {}
    for entity_type, pattern in ENTITY_PATTERNS.items():
        matches = re.findall(pattern, context, re.IGNORECASE)
        if matches:
            extracted[entity_type] = set(matches)
    return extracted


async def _auto_create_entity_if_new(
    kg: Any, entity_name: str, entity_type: str
) -> bool:
    """Create entity if it doesn't exist. Returns True if created."""
    existing = await kg.find_entity_by_name(entity_name)
    if not existing:
        await kg.create_entity(
            name=entity_name,
            entity_type=entity_type,
            observations=["Extracted from conversation context"],
        )
        return True
    return False


async def _process_entity_type(
    kg: Any,
    entity_type: str,
    entities: set[str],
    auto_create: bool,
) -> tuple[list[str], int, int]:
    """Process entities of a specific type."""
    lines = [f"📊 {entity_type.capitalize()}:"]
    count = 0
    created = 0

    for entity_name in sorted(entities):
        lines.append(f"   • {entity_name}")
        count += 1
        if auto_create and await _auto_create_entity_if_new(
            kg, entity_name, entity_type
        ):
            created += 1

    lines.append("")
    return lines, count, created


async def _extract_entities_from_context_impl(
    context: str,
    auto_create: bool = False,
) -> str:
    """Extract entities from conversation context using pattern matching."""

    async def operation(kg: Any) -> str:
        extracted = _extract_patterns_from_context(context)
        if not extracted:
            return "🔍 No entities detected in context"

        lines = ["🔍 Extracted Entities from Context:", ""]
        total_extracted = 0
        created_count = 0

        for entity_type, entities in extracted.items():
            type_lines, count, created = await _process_entity_type(
                kg, entity_type, entities, auto_create
            )
            lines.extend(type_lines)
            total_extracted += count
            created_count += created

        lines.append(f"📊 Total Extracted: {total_extracted}")
        if auto_create:
            lines.append(f"✅ Auto-created: {created_count} new entities")

        _get_logger().info(
            "Entities extracted from context",
            total_extracted=total_extracted,
            auto_created=created_count if auto_create else 0,
        )
        return "\n".join(lines)

    return await _execute_kg_operation("Extract entities from context", operation)


# ============================================================================
# Batch Operations
# ============================================================================


async def _create_single_entity(
    kg: Any, entity_data: dict[str, Any]
) -> tuple[str | None, tuple[str, str] | None]:
    """Create a single entity. Returns (created_name, None) or (None, (name, error))."""
    try:
        entity = await kg.create_entity(
            name=entity_data["name"],
            entity_type=entity_data["entity_type"],
            observations=entity_data.get("observations", []),
            properties=entity_data.get("properties", {}),
        )
        return entity["name"], None
    except Exception as e:
        return None, (entity_data["name"], str(e))


async def _batch_create_entities_operation(
    kg: Any, entities: list[dict[str, Any]]
) -> str:
    """Bulk create multiple entities."""
    created = []
    failed = []

    for entity_data in entities:
        created_name, failure = await _create_single_entity(kg, entity_data)
        if created_name:
            created.append(created_name)
        elif failure:
            failed.append(failure)

    lines = [
        "📦 Batch Entity Creation Results:",
        "",
        f"✅ Successfully Created: {len(created)}",
    ]

    if created:
        for name in created[:10]:  # Show first 10
            lines.append(f"   • {name}")
        if len(created) > 10:
            lines.append(f"   ... and {len(created) - 10} more")
    lines.append("")

    if failed:
        lines.append(f"❌ Failed: {len(failed)}")
        for name, error in failed[:5]:  # Show first 5 failures
            lines.append(f"   • {name}: {error}")
        if len(failed) > 5:
            lines.append(f"   ... and {len(failed) - 5} more")

    _get_logger().info(
        "Batch entities created",
        total=len(entities),
        created=len(created),
        failed=len(failed),
    )
    return "\n".join(lines)


async def _batch_create_entities_impl(entities: list[dict[str, Any]]) -> str:
    """Bulk create multiple entities."""

    async def operation_wrapper(kg: Any) -> str:
        return await _batch_create_entities_operation(kg, entities)

    return await _execute_kg_operation(
        "Batch create entities",
        operation_wrapper,
    )


# ============================================================================
# Phase 2: Auto-Discovery Operations
# ============================================================================


async def _generate_embeddings_impl(
    entity_type: str | None = None,
    batch_size: int = 50,
    overwrite: bool = False,
) -> str:
    """Generate embeddings for entities missing them."""

    async def operation_wrapper(kg: Any) -> str:
        result = await kg.generate_embeddings_for_entities(
            entity_type=entity_type,
            batch_size=batch_size,
            overwrite=overwrite,
        )

        lines = [
            "🧠 Embedding Generation Results",
            "",
            f"✅ Generated: {result['generated']}",
            f"❌ Failed: {result['failed']}",
            f"📊 Total Processed: {result['total_processed']}",
        ]

        _get_logger().info(
            "Embeddings generated",
            generated=result["generated"],
            failed=result["failed"],
        )

        return "\n".join(lines)

    return await _execute_kg_operation(
        "Generate embeddings",
        operation_wrapper,
    )


async def _discover_relationships_impl(
    entity_type: str | None = None,
    threshold: float = 0.75,
    limit: int = 100,
    batch_size: int = 10,
) -> str:
    """Batch discover relationships for entities."""

    async def operation_wrapper(kg: Any) -> str:
        result = await kg.batch_discover_relationships(
            entity_type=entity_type,
            threshold=threshold,
            limit=limit,
            batch_size=batch_size,
        )

        lines = [
            "🔗 Relationship Discovery Results",
            "",
            f"📊 Entities Processed: {result['entities_processed']}",
            f"✅ Relationships Created: {result['relationships_created']}",
            f"📈 Avg Relationships/Entity: {result['avg_relationships_per_entity']}",
        ]

        _get_logger().info(
            "Relationships discovered",
            entities_processed=result["entities_processed"],
            relationships_created=result["relationships_created"],
        )

        return "\n".join(lines)

    return await _execute_kg_operation(
        "Discover relationships",
        operation_wrapper,
    )


async def _analyze_graph_connectivity_impl() -> str:
    """Analyze graph connectivity and health metrics."""

    async def operation_wrapper(kg: Any) -> str:
        stats = await kg.get_stats()

        # Calculate health metrics
        connectivity = stats.get("connectivity_ratio", 0)
        embedding_coverage = stats.get("embedding_coverage", 0)
        isolated = stats.get("isolated_entities", 0)
        total = stats.get("total_entities", 0)

        # Determine health status
        if connectivity >= 0.5:
            health = "🟢 Excellent"
        elif connectivity >= 0.2:
            health = "🟡 Good"
        elif connectivity >= 0.1:
            health = "🟠 Fair"
        else:
            health = "🔴 Poor"

        lines = [
            "📊 Knowledge Graph Connectivity Analysis",
            "",
            f"🏥 Health Status: {health}",
            "",
            "Connectivity Metrics:",
            f"  🔗 Connectivity Ratio: {connectivity:.3f}",
            f"  📈 Average Degree: {stats.get('avg_degree', 0):.3f}",
            "",
            "Entity Metrics:",
            f"  📌 Total Entities: {total}",
            f"  🏝️ Isolated Entities: {isolated} ({isolated / total * 100 if total > 0 else 0:.1f}%)",
            "",
            "Embedding Metrics:",
            f"  🧠 Coverage: {embedding_coverage:.1%}",
            f"  📊 With Embeddings: {stats.get('entities_with_embeddings', 0)}",
            "",
        ]

        # Recommendations
        if connectivity < 0.2:
            lines.extend(
                [
                    "💡 Recommendations:",
                    "  1. Run 'generate_embeddings' to increase embedding coverage",
                    "  2. Run 'discover_relationships' to create semantic connections",
                    "  3. Consider lowering threshold for more connections",
                    "",
                ]
            )
        elif embedding_coverage < 0.8:
            lines.extend(
                [
                    "💡 Recommendations:",
                    "  1. Run 'generate_embeddings' to increase embedding coverage",
                    "",
                ]
            )

        return "\n".join(lines)

    return await _execute_kg_operation(
        "Analyze connectivity",
        operation_wrapper,
    )


# ============================================================================
# MCP Tool Registration
# ============================================================================


def register_knowledge_graph_tools(mcp_server: Any) -> None:
    """Register all knowledge graph MCP tools with the server."""

    @mcp_server.tool()  # type: ignore[misc]
    async def create_entity(
        name: str,
        entity_type: str,
        observations: list[str] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Create an entity (node) in the knowledge graph."""
        return await _create_entity_impl(name, entity_type, observations, properties)

    @mcp_server.tool()  # type: ignore[misc]
    async def add_observation(entity_name: str, observation: str) -> str:
        """Add an observation (fact) to an existing entity."""
        return await _add_observation_impl(entity_name, observation)

    @mcp_server.tool()  # type: ignore[misc]
    async def create_relation(
        from_entity: str,
        to_entity: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Create a relationship between two entities in the knowledge graph."""
        return await _create_relation_impl(
            from_entity, to_entity, relation_type, properties
        )

    @mcp_server.tool()  # type: ignore[misc]
    async def search_entities(
        query: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> str:
        """Search for entities by name or observations."""
        return await _search_entities_impl(query, entity_type, limit)

    @mcp_server.tool()  # type: ignore[misc]
    async def get_entity_relationships(
        entity_name: str,
        relation_type: str | None = None,
        direction: str = "both",
    ) -> str:
        """Get all relationships for a specific entity."""
        return await _get_entity_relationships_impl(
            entity_name, relation_type, direction
        )

    @mcp_server.tool()  # type: ignore[misc]
    async def find_path(
        from_entity: str,
        to_entity: str,
        max_depth: int = 5,
    ) -> str:
        """Find paths between two entities using DuckPGQ's SQL/PGQ graph queries."""
        return await _find_path_impl(from_entity, to_entity, max_depth)

    @mcp_server.tool()  # type: ignore[misc]
    async def get_knowledge_graph_stats() -> str:
        """Get statistics about the knowledge graph."""
        return await _get_knowledge_graph_stats_impl()

    @mcp_server.tool()  # type: ignore[misc]
    async def extract_entities_from_context(
        context: str,
        auto_create: bool = False,
    ) -> str:
        """Extract entities from conversation context using pattern matching."""
        return await _extract_entities_from_context_impl(context, auto_create)

    @mcp_server.tool()  # type: ignore[misc]
    async def batch_create_entities(entities: list[dict[str, Any]]) -> str:
        """Bulk create multiple entities in one operation."""
        return await _batch_create_entities_impl(entities)

    # Phase 2: Auto-discovery tools
    @mcp_server.tool()  # type: ignore[misc]
    async def generate_embeddings(
        entity_type: str | None = None,
        batch_size: int = 50,
        overwrite: bool = False,
    ) -> str:
        """Generate embeddings for entities missing them.

        Args:
            entity_type: Optional filter by entity type (None = all)
            batch_size: Number of entities to process per batch
            overwrite: Regenerate existing embeddings

        Returns:
            Summary of embeddings generated
        """
        return await _generate_embeddings_impl(entity_type, batch_size, overwrite)

    @mcp_server.tool()  # type: ignore[misc]
    async def discover_relationships(
        entity_type: str | None = None,
        threshold: float = 0.75,
        limit: int = 100,
        batch_size: int = 10,
    ) -> str:
        """Batch discover relationships for entities.

        Args:
            entity_type: Optional filter by entity type (None = all)
            threshold: Similarity threshold (0.0-1.0)
            limit: Max entities to process
            batch_size: Entities per batch

        Returns:
            Summary of relationships created
        """
        return await _discover_relationships_impl(
            entity_type, threshold, limit, batch_size
        )

    @mcp_server.tool()  # type: ignore[misc]
    async def analyze_graph_connectivity() -> str:
        """Analyze graph connectivity and health metrics.

        Returns:
            Connectivity metrics and recommendations
        """
        return await _analyze_graph_connectivity_impl()
