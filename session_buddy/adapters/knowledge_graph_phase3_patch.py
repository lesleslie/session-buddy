"""Phase 3 Integration Patch for Knowledge Graph Adapter.

This module contains the integrated Phase 3 methods that can be added to
the KnowledgeGraphDatabaseAdapterOneiric class.

To apply this patch, add these methods to the adapter class and update
the _infer_relationship_type method.

"""

import json
import re
import typing as t

if t.TYPE_CHECKING:
    pass


def phase3_infer_relationship_type(
    self,
    from_entity: dict[str, t.Any],
    to_entity: dict[str, t.Any],
    similarity: float,
    from_observations: list[str] | None = None,
    to_observations: list[str] | None = None,
) -> tuple[str, str]:
    """Infer relationship type and confidence level (Phase 3 enhanced).

    Returns:
        Tuple of (relationship_type, confidence) where confidence is "low"/"medium"/"high"

    Relationship Type Hierarchy (15+ types):
    - very_similar_to: similarity ≥ 0.85 (high confidence)
    - similar_to: similarity ≥ 0.75 (medium confidence)
    - uses/extends/depends_on/part_of/implements/requires/connects_to: pattern-based
    - Type-specific: used_by, serves, tests, tested_by, applies_to
    - related_to: default (low confidence)
    """
    from_type = from_entity.get("entity_type", "").lower()
    to_type = to_entity.get("entity_type", "").lower()

    # Priority 1: Pattern extraction from observations
    if from_observations:
        pattern_type = _extract_pattern_from_text(
            " ".join(from_observations),
            to_entity.get("name", ""),
        )
        if pattern_type:
            return pattern_type, "high"

    # Priority 2: Similarity-based hierarchy
    if similarity >= 0.85:
        return "very_similar_to", "high"
    if similarity >= 0.75:
        return "similar_to", "medium"

    # Priority 3: Type-based heuristics
    type_pairs = [
        (("project", "library"), "uses"),
        (("library", "project"), "used_by"),
        (("project", "service"), "connects_to"),
        (("service", "project"), "serves"),
        (("test", "project"), "tests"),
        (("project", "test"), "tested_by"),
        (("project", "concept"), "implements"),
        (("concept", "project"), "applies_to"),
        (("class", "class"), "extends"),
        (("component", "system"), "part_of"),
        (("system", "component"), "contains"),
    ]

    for (type1, type2), rel_type in type_pairs:
        if from_type == type1 and to_type == type2:
            return rel_type, "medium"

    return "related_to", "low"


# Regex patterns for relationship extraction
_RELATIONSHIP_PATTERNS: dict[str, re.Pattern[str]] = {
    r"\buses\s+(\w+)": "uses",
    r"\bextends\s+(\w+)": "extends",
    r"\bdepends\s+on\s+(\w+)": "depends_on",
    r"\bpart\s+of\s+(\w+)": "part_of",
    r"\bimplements\s+(\w+)": "implements",
    r"\brequires\s+(\w+)": "requires",
    r"\bconnects?\s+to\s+(\w+)": "connects_to",
    r"\binherits\s+from\s+(\w+)": "extends",
    r"\bintegrates\s+with\s+(\w+)": "connects_to",
    r"\bbuilds?\s+on\s+(\w+)": "extends",
}


def _extract_pattern_from_text(
    text: str,
    target_entity_name: str,
) -> str | None:
    """Extract relationship type from text using regex patterns."""
    text_lower = text.lower()
    target_lower = target_entity_name.lower()

    for pattern, rel_type in _RELATIONSHIP_PATTERNS.items():
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            matched_entity = match.group(1).lower()
            if matched_entity in target_lower or target_lower in matched_entity:
                return rel_type

    return None


def _extract_relationships_from_observations(
    self,
    entity_id: str,
    entity_name: str,
    observations: list[str],
) -> list[dict[str, t.Any]]:
    """Extract relationships from text observations (Phase 3)."""
    discovered = []

    for observation in observations:
        for pattern, rel_type in _RELATIONSHIP_PATTERNS.items():
            matches = re.finditer(pattern, observation, re.IGNORECASE)
            for match in matches:
                target_entity = match.group(1)

                if target_entity.lower() == entity_name.lower():
                    continue

                discovered.append(
                    {
                        "from_entity": entity_id,
                        "from_name": entity_name,
                        "to_entity": target_entity,
                        "to_name": target_entity,
                        "relation_type": rel_type,
                        "confidence": "medium",
                        "evidence": [observation],
                        "discovery_method": "pattern",
                    }
                )

    return discovered


async def discover_transitive_relationships(
    self,
    max_depth: int = 3,
    min_confidence: str = "medium",
    limit: int = 100,
) -> dict[str, int]:
    """Discover transitive relationships (A→B→C implies A→C) (Phase 3)."""
    conn = self._get_conn()

    confidence_rank = {"low": 1, "medium": 2, "high": 3}
    min_rank = confidence_rank.get(min_confidence, 2)

    result = conn.execute(
        "SELECT from_entity, to_entity, relation_type, properties FROM kg_relationships",
    ).fetchall()

    graph: dict[str, list[tuple[str, str, str]]] = {}
    for row in result:
        from_e = row[0]
        to_e = row[1]
        rel_type = row[2]
        props = json.loads(row[3]) if row[3] else {}
        conf = props.get("confidence", "medium")

        if from_e not in graph:
            graph[from_e] = []
        graph[from_e].append((to_e, rel_type, conf))

    created = 0
    skipped = 0
    duplicate = 0

    for from_entity in graph:
        from collections import deque

        queue: deque[tuple[str, list[str], list[str], list[str]]] = deque(
            [(from_entity, [from_entity], [], [])],
        )
        visited: set[tuple[str, str]] = set()

        while queue and created < limit:
            current, path, types, confidences = queue.popleft()

            if len(path) > max_depth + 1:
                continue

            if len(path) > 1 and current == from_entity:
                continue

            if len(path) >= 3:
                transitive_conf = min(
                    (confidence_rank.get(c, 2) for c in confidences),
                    default=2,
                )

                if transitive_conf < min_rank:
                    skipped += 1
                    continue

                to_entity = current
                relation_key = (from_entity, to_entity)

                if relation_key in visited:
                    duplicate += 1
                    continue

                transitive_type = _infer_transitive_type(types)

                try:
                    await self.create_relation(
                        from_entity=from_entity,
                        to_entity=to_entity,
                        relation_type=transitive_type,
                        properties={
                            "confidence": ["low", "medium", "high"][
                                transitive_conf - 1
                            ],
                            "transitive": True,
                            "path": path,
                            "path_types": types,
                            "path_confidences": confidences,
                            "discovery_method": "transitive",
                            "chain_length": len(path) - 1,
                        },
                    )
                    created += 1
                    visited.add(relation_key)
                except Exception:
                    skipped += 1
                    continue

            for neighbor, rel_type, conf in graph.get(current, []):
                if neighbor not in path:
                    new_path = path + [neighbor]
                    new_types = types + [rel_type]
                    new_confs = confidences + [conf]
                    queue.append((neighbor, new_path, new_types, new_confs))

    return {
        "created": created,
        "skipped": skipped,
        "duplicate": duplicate,
        "total_examined": created + skipped + duplicate,
    }


def _infer_transitive_type(types: list[str]) -> str:
    """Infer transitive relationship type from chain of types."""
    if not types:
        return "related_to"

    priority = [
        "uses",
        "depends_on",
        "extends",
        "implements",
        "part_of",
        "connects_to",
        "similar_to",
        "very_similar_to",
        "related_to",
    ]

    for rel_type in priority:
        if rel_type in types:
            return rel_type

    return types[0]


async def create_entity_with_patterns(
    self,
    name: str,
    entity_type: str,
    observations: list[str] | None = None,
    properties: dict[str, t.Any] | None = None,
    metadata: dict[str, t.Any] | None = None,
    extract_patterns: bool = False,
    auto_discover: bool = False,
    discovery_threshold: float = 0.75,
    max_discoveries: int = 5,
) -> dict[str, t.Any]:
    """Create entity with optional pattern extraction from observations (Phase 3)."""
    entity = await self.create_entity(
        name=name,
        entity_type=entity_type,
        observations=observations,
        properties=properties,
        metadata=metadata,
        auto_discover=auto_discover,
        discovery_threshold=discovery_threshold,
        max_discoveries=max_discoveries,
    )

    if extract_patterns and observations:
        discovered = _extract_relationships_from_observations(
            self,
            entity_id=entity["id"],
            entity_name=name,
            observations=observations,
        )

        for rel in discovered:
            try:
                target_entity = await self.find_entity_by_name(rel["to_name"])
                if target_entity:
                    await self.create_relation(
                        from_entity=entity["id"],
                        to_entity=target_entity["id"],
                        relation_type=rel["relation_type"],
                        properties={
                            "confidence": rel["confidence"],
                            "discovery_method": rel["discovery_method"],
                            "evidence": rel["evidence"],
                        },
                    )
            except Exception:
                pass

    return entity


# Export all functions
__all__ = [
    "phase3_infer_relationship_type",
    "_extract_pattern_from_text",
    "_extract_relationships_from_observations",
    "discover_transitive_relationships",
    "_infer_transitive_type",
    "create_entity_with_patterns",
]
