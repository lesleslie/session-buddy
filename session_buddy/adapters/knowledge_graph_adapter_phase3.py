"""Phase 3: Enhanced Relationship Methods for Knowledge Graph Adapter.

This module provides the enhanced semantic relationship methods for Phase 3:
- Rich relationship type hierarchy (15+ types)
- Confidence scoring (low/medium/high)
- Pattern extraction from observations
- Transitive relationship discovery

These methods can be mixed into KnowledgeGraphDatabaseAdapterOneiric.

"""

from __future__ import annotations

import json
import re
import typing as t
from datetime import UTC, datetime

if t.TYPE_CHECKING:
    from collections.abc import Callable


class Phase3RelationshipMixin:
    """Mixin class providing Phase 3 enhanced relationship methods.

    This mixin adds advanced relationship capabilities to the knowledge graph:
    1. Enhanced type inference with confidence scoring
    2. Pattern extraction from observations
    3. Transitive relationship discovery

    Usage:
        class KnowledgeGraphDatabaseAdapterOneiric(Phase3RelationshipMixin):
            ...
    """

    # ========================================================================
    # Phase 3.1: Enhanced Relationship Type Inference
    # ========================================================================

    def _infer_relationship_type(
        self,
        from_entity: dict[str, t.Any],
        to_entity: dict[str, t.Any],
        similarity: float,
        from_observations: list[str] | None = None,
        to_observations: list[str] | None = None,
    ) -> tuple[str, str]:
        """Infer relationship type and confidence level.

        Args:
            from_entity: Source entity dictionary
            to_entity: Target entity dictionary
            similarity: Cosine similarity score (0.0-1.0)
            from_observations: Optional observations from source entity for pattern matching
            to_observations: Optional observations from target entity for pattern matching

        Returns:
            Tuple of (relationship_type, confidence) where confidence is "low"/"medium"/"high"

        Relationship Type Hierarchy (15+ types):

        Similarity-based (priority 1):
        - very_similar_to: similarity ≥ 0.85 (high confidence)
        - similar_to: similarity ≥ 0.75 (medium confidence)
        - related_to: default/fallback (low confidence)

        Pattern-based (priority 2):
        - uses: X uses Y (e.g., "session-buddy uses FastMCP")
        - extends: X extends Y (e.g., "UserAdmin extends Admin")
        - depends_on: X depends on Y (e.g., "service depends on database")
        - part_of: X is part of Y (e.g., "AuthService part_of API")
        - implements: X implements Y (e.g., "Class implements Interface")
        - requires: X requires Y (e.g., "project requires Python 3.13+")
        - connects_to: X connects to Y (e.g., "client connects_to server")

        Type-based (priority 3):
        - used_by: library used_by project
        - serves: service serves project
        - tests: test tests project
        - tested_by: project tested_by test
        - applies_to: concept applies_to project
        """
        from_type = from_entity.get("entity_type", "").lower()
        to_type = to_entity.get("entity_type", "").lower()

        # Priority 1: Pattern extraction from observations
        if from_observations:
            pattern_type = self._extract_pattern_from_text(
                " ".join(from_observations),
                to_entity.get("name", ""),
            )
            if pattern_type:
                # High confidence if found in text
                return pattern_type, "high"

        # Priority 2: Similarity-based hierarchy
        if similarity >= 0.85:
            return "very_similar_to", "high"
        if similarity >= 0.75:
            return "similar_to", "medium"

        # Priority 3: Type-based heuristics (ordered by specificity)
        type_pairs = [
            # Most specific first
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
            if (from_type == type1 and to_type == type2):
                # Medium confidence for type-based inference
                return rel_type, "medium"

        # Default fallback
        return "related_to", "low"

    # ========================================================================
    # Phase 3.2: Pattern Extraction from Observations
    # ========================================================================

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
        self,
        text: str,
        target_entity_name: str,
    ) -> str | None:
        """Extract relationship type from text using regex patterns.

        Args:
            text: Text to search (e.g., observations)
            target_entity_name: Name of target entity to match

        Returns:
            Relationship type if pattern found, None otherwise

        Examples:
            >>> self._extract_pattern_from_text(
            ...     "session-buddy uses FastMCP for tool registration",
            ...     "FastMCP"
            ... )
            "uses"
        """
        text_lower = text.lower()
        target_lower = target_entity_name.lower()

        # Check each pattern
        for pattern, rel_type in self._RELATIONSHIP_PATTERNS.items():
            # Look for pattern with entity name
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                # Check if matched entity matches target
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
        """Extract relationships from text observations.

        Scans observations for relationship patterns and extracts potential
        connections to other entities.

        Args:
            entity_id: Source entity ID
            entity_name: Source entity name
            observations: List of observation strings

        Returns:
            List of discovered relationships with evidence

        Example:
            >>> relationships = self._extract_relationships_from_observations(
            ...     entity_id="abc123",
            ...     entity_name="session-buddy",
            ...     observations=["session-buddy uses FastMCP for tool registration"]
            ... )
            >>> relationships[0]["relation_type"]
            "uses"
            >>> relationships[0]["to_entity"]
            "FastMCP"
            >>> relationships[0]["evidence"]
            ["session-buddy uses FastMCP for tool registration"]
        """
        discovered = []

        for observation in observations:
            # Extract all potential relationships from this observation
            for pattern, rel_type in self._RELATIONSHIP_PATTERNS.items():
                matches = re.finditer(pattern, observation, re.IGNORECASE)
                for match in matches:
                    target_entity = match.group(1)

                    # Skip self-references
                    if target_entity.lower() == entity_name.lower():
                        continue

                    discovered.append({
                        "from_entity": entity_id,
                        "from_name": entity_name,
                        "to_entity": target_entity,  # Name, not ID (will resolve later)
                        "to_name": target_entity,
                        "relation_type": rel_type,
                        "confidence": "medium",  # Pattern extraction = medium confidence
                        "evidence": [observation],
                        "discovery_method": "pattern",
                    })

        return discovered

    # ========================================================================
    # Phase 3.3: Transitive Relationship Discovery
    # ========================================================================

    async def discover_transitive_relationships(
        self,
        max_depth: int = 3,
        min_confidence: str = "medium",
        limit: int = 100,
    ) -> dict[str, int]:
        """Discover transitive relationships (A→B→C implies A→C).

        For example:
            - session-buddy uses FastMCP
            - FastMCP extends MCP
            - Therefore: session-buddy uses MCP (transitive)

        Args:
            max_depth: Maximum chain length (default: 3)
            min_confidence: Minimum confidence level ("low"/"medium"/high")
            limit: Maximum relationships to create

        Returns:
            Dictionary with created/skipped/duplicate counts

        Example:
            >>> result = await kg.discover_transitive_relationships(max_depth=2)
            >>> print(result)
            {"created": 45, "skipped": 12, "duplicate": 8}
        """
        conn = self._get_conn()

        # Confidence ranking for min comparison
        confidence_rank = {"low": 1, "medium": 2, "high": 3}
        min_rank = confidence_rank.get(min_confidence, 2)

        # Get all existing relationships
        result = conn.execute(
            "SELECT from_entity, to_entity, relation_type, properties FROM kg_relationships",
        ).fetchall()

        # Build adjacency list: from_entity -> [(to_entity, relation_type, confidence)]
        graph: dict[str, list[tuple[str, str, str]]] = {}
        for row in result:
            from_e = row[0]
            to_e = row[1]
            rel_type = row[2]
            props = json.loads(row[3]) if row[3] else {}

            # Get confidence from properties or default to "medium"
            conf = props.get("confidence", "medium")

            if from_e not in graph:
                graph[from_e] = []
            graph[from_e].append((to_e, rel_type, conf))

        # Discover transitive relationships
        created = 0
        skipped = 0
        duplicate = 0

        # Pre-populate visited set with all existing relationships for duplicate detection
        visited: set[tuple[str, str]] = set()
        for from_e in graph:
            for (to_e, _, _) in graph[from_e]:
                visited.add((from_e, to_e))

        for from_entity in graph:
            # BFS to find transitive chains
            from collections import deque

            queue: deque[tuple[str, list[str], list[str], list[str]]] = deque(
                [(from_entity, [from_entity], [], [])],
            )

            while queue and created < limit:
                current, path, types, confidences = queue.popleft()

                # Skip if too deep
                if len(path) > max_depth + 1:
                    continue

                # Skip if back to start
                if len(path) > 1 and current == from_entity:
                    continue

                # Found a transitive path (length >= 3)
                if len(path) >= 3:
                    # Calculate transitive confidence (minimum of all edges)
                    transitive_conf = min(
                        (confidence_rank.get(c, 2) for c in confidences),
                        default=2,
                    )
                    transitive_conf_str = ["low", "medium", "high"][transitive_conf - 1]

                    # Skip if below minimum confidence
                    if transitive_conf < min_rank:
                        skipped += 1
                        continue

                    to_entity = current
                    relation_key = (from_entity, to_entity)

                    # Check if direct relationship already exists
                    if relation_key in visited:
                        duplicate += 1
                        continue

                    # Infer transitive relationship type
                    # Use the most specific type from the chain
                    transitive_type = self._infer_transitive_type(types)

                    # Create transitive relationship
                    try:
                        await self.create_relation(
                            from_entity=from_entity,
                            to_entity=to_entity,
                            relation_type=transitive_type,
                            properties={
                                "confidence": transitive_conf_str,
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
                        # Silently skip failures (duplicates, missing entities)
                        skipped += 1
                        continue

                # Explore neighbors
                for neighbor, rel_type, conf in graph.get(current, []):
                    if neighbor not in path:  # Avoid cycles
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

    def _infer_transitive_type(self, types: list[str]) -> str:
        """Infer transitive relationship type from chain of types.

        Args:
            types: List of relationship types in the chain

        Returns:
            Most appropriate transitive relationship type

        Examples:
            >>> self._infer_transitive_type(["uses", "extends"])
            "uses"
            >>> self._infer_transitive_type(["related_to", "related_to"])
            "related_to"
        """
        if not types:
            return "related_to"

        # Priority order (most specific first)
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

        # Find highest priority type in chain
        for rel_type in priority:
            if rel_type in types:
                return rel_type

        # Default to first type
        return types[0]

    # ========================================================================
    # Phase 3.4: Enhanced Entity Creation with Pattern Extraction
    # ========================================================================

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
        """Create entity with optional pattern extraction from observations.

        Enhanced version of create_entity() that can extract relationships
        from text observations using regex patterns.

        Args:
            name: Entity name (must be unique)
            entity_type: Type/category of entity
            observations: List of observation strings
            properties: Additional properties as key-value pairs
            metadata: Additional metadata
            extract_patterns: Extract relationships from observations (Phase 3)
            auto_discover: Auto-discover similar entities (Phase 2)
            discovery_threshold: Similarity threshold for auto-discovery
            max_discoveries: Maximum relationships to create via auto-discovery

        Returns:
            Created entity as dictionary

        Example:
            >>> entity = await kg.create_entity_with_patterns(
            ...     name="session-buddy",
            ...     entity_type="project",
            ...     observations=["session-buddy uses FastMCP for tool registration"],
            ...     extract_patterns=True
            ... )
            # Creates entity and extracts relationship: session-buddy -> uses -> FastMCP
        """
        # Create entity first
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

        # Extract relationships from observations if enabled
        if extract_patterns and observations:
            discovered = self._extract_relationships_from_observations(
                entity_id=entity["id"],
                entity_name=name,
                observations=observations,
            )

            # Try to create discovered relationships
            for rel in discovered:
                try:
                    # Resolve target entity by name
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
                    # Silently skip if target entity doesn't exist yet
                    pass

        return entity


# Export the mixin for easy importing
__all__ = ["Phase3RelationshipMixin"]
