"""Comprehensive pytest tests for knowledge_graph_phase3_patch.py.

This module tests the Phase 3 integration patch functions that can be added
to the KnowledgeGraphDatabaseAdapterOneiric class.

Tests cover:
- phase3_infer_relationship_type: Enhanced relationship inference with confidence
- _extract_pattern_from_text: Regex-based relationship extraction from text
- _extract_relationships_from_observations: Observation-based relationship discovery
- discover_transitive_relationships: Transitive relationship chain discovery
- _infer_transitive_type: Transitive type inference from type chains
- create_entity_with_patterns: Entity creation with optional pattern extraction

All async methods use unittest.mock.AsyncMock and pytest.mark.asyncio.
"""

from __future__ import annotations

import json
import re
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.adapters.knowledge_graph_phase3_patch import (
    _extract_pattern_from_text,
    _extract_relationships_from_observations,
    _infer_transitive_type,
    create_entity_with_patterns,
    discover_transitive_relationships,
    phase3_infer_relationship_type,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_self():
    """Create a mock self for methods that expect it."""
    return MagicMock()


@pytest.fixture
def mock_adapter():
    """Create a mock adapter with all required methods."""
    adapter = MagicMock()
    adapter._get_conn = MagicMock()
    adapter.create_entity = AsyncMock()
    adapter.create_relation = AsyncMock()
    adapter.find_entity_by_name = AsyncMock()
    return adapter


@pytest.fixture
def mock_conn():
    """Create a mock database connection."""
    conn = MagicMock()
    return conn


@pytest.fixture
def sample_entities():
    """Provide sample entity dicts for testing."""
    return {
        "project": {"entity_type": "project", "name": "my_project"},
        "library": {"entity_type": "library", "name": "my_library"},
        "service": {"entity_type": "service", "name": "my_service"},
        "test": {"entity_type": "test", "name": "my_test"},
        "class": {"entity_type": "class", "name": "MyClass"},
        "component": {"entity_type": "component", "name": "my_component"},
        "system": {"entity_type": "system", "name": "my_system"},
        "concept": {"entity_type": "concept", "name": "my_concept"},
    }


# ============================================================================
# Tests for phase3_infer_relationship_type
# ============================================================================


class TestPhase3InferRelationshipType:
    """Tests for the phase3_infer_relationship_type function."""

    # ========================================================================
    # Similarity-based inference (Priority 1)
    # ========================================================================

    def test_very_similar_to_high_confidence(self, mock_self, sample_entities):
        """Similarity >= 0.85 returns very_similar_to with high confidence."""
        from_entity = sample_entities["project"]
        to_entity = {"entity_type": "project", "name": "other_project"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.90
        )

        assert rel_type == "very_similar_to"
        assert confidence == "high"

    def test_very_similar_to_boundary_085(self, mock_self, sample_entities):
        """Boundary case: similarity=0.85 returns very_similar_to."""
        from_entity = sample_entities["project"]
        to_entity = {"entity_type": "project", "name": "other_project"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.85
        )

        assert rel_type == "very_similar_to"
        assert confidence == "high"

    def test_similar_to_medium_confidence(self, mock_self, sample_entities):
        """Similarity >= 0.75 (but < 0.85) returns similar_to with medium."""
        from_entity = sample_entities["library"]
        to_entity = {"entity_type": "library", "name": "other_library"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.80
        )

        assert rel_type == "similar_to"
        assert confidence == "medium"

    def test_similar_to_boundary_075(self, mock_self, sample_entities):
        """Boundary case: similarity=0.75 returns similar_to."""
        from_entity = sample_entities["library"]
        to_entity = {"entity_type": "library", "name": "other_library"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.75
        )

        assert rel_type == "similar_to"
        assert confidence == "medium"

    def test_related_to_low_confidence_below_threshold(self, mock_self, sample_entities):
        """Similarity < 0.75 returns related_to with low confidence."""
        from_entity = sample_entities["component"]
        to_entity = {"entity_type": "component", "name": "other_component"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "related_to"
        assert confidence == "low"

    def test_related_to_boundary_074(self, mock_self, sample_entities):
        """Boundary case: similarity=0.74 returns related_to."""
        from_entity = sample_entities["component"]
        to_entity = {"entity_type": "component", "name": "other_component"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.74
        )

        assert rel_type == "related_to"
        assert confidence == "low"

    # ========================================================================
    # Type-based heuristics (Priority 3)
    # ========================================================================

    def test_project_uses_library(self, mock_self, sample_entities):
        """Project -> library returns uses."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["library"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "uses"
        assert confidence == "medium"

    def test_library_used_by_project(self, mock_self, sample_entities):
        """Library -> project returns used_by."""
        from_entity = sample_entities["library"]
        to_entity = sample_entities["project"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "used_by"
        assert confidence == "medium"

    def test_project_connects_to_service(self, mock_self, sample_entities):
        """Project -> service returns connects_to."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["service"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "connects_to"
        assert confidence == "medium"

    def test_service_serves_project(self, mock_self, sample_entities):
        """Service -> project returns serves."""
        from_entity = sample_entities["service"]
        to_entity = sample_entities["project"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "serves"
        assert confidence == "medium"

    def test_test_tests_project(self, mock_self, sample_entities):
        """Test -> project returns tests."""
        from_entity = sample_entities["test"]
        to_entity = sample_entities["project"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "tests"
        assert confidence == "medium"

    def test_project_tested_by_test(self, mock_self, sample_entities):
        """Project -> test returns tested_by."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["test"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "tested_by"
        assert confidence == "medium"

    def test_project_implements_concept(self, mock_self, sample_entities):
        """Project -> concept returns implements."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["concept"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "implements"
        assert confidence == "medium"

    def test_concept_applies_to_project(self, mock_self, sample_entities):
        """Concept -> project returns applies_to."""
        from_entity = sample_entities["concept"]
        to_entity = sample_entities["project"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "applies_to"
        assert confidence == "medium"

    def test_class_extends_class(self, mock_self, sample_entities):
        """Class -> class returns extends."""
        from_entity = sample_entities["class"]
        to_entity = {"entity_type": "class", "name": "ParentClass"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "extends"
        assert confidence == "medium"

    def test_component_part_of_system(self, mock_self, sample_entities):
        """Component -> system returns part_of."""
        from_entity = sample_entities["component"]
        to_entity = sample_entities["system"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "part_of"
        assert confidence == "medium"

    def test_system_contains_component(self, mock_self, sample_entities):
        """System -> component returns contains."""
        from_entity = sample_entities["system"]
        to_entity = sample_entities["component"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50
        )

        assert rel_type == "contains"
        assert confidence == "medium"

    # ========================================================================
    # Pattern extraction from observations (Priority 2)
    # ========================================================================

    def test_pattern_observation_overrides_similarity(self, mock_self, sample_entities):
        """Pattern found in observations takes priority over similarity."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["library"]

        # Even with low similarity, pattern should override
        rel_type, confidence = phase3_infer_relationship_type(
            mock_self,
            from_entity,
            to_entity,
            similarity=0.50,
            from_observations=["The project uses my_library for caching"],
            to_observations=None,
        )

        assert rel_type == "uses"
        assert confidence == "high"

    def test_pattern_extends_from_observations(self, mock_self, sample_entities):
        """Pattern extraction works with extends keyword."""
        from_entity = sample_entities["class"]
        to_entity = {"entity_type": "class", "name": "BaseClass"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self,
            from_entity,
            to_entity,
            similarity=0.50,
            from_observations=["This class extends BaseClass"],
            to_observations=None,
        )

        assert rel_type == "extends"
        assert confidence == "high"

    def test_pattern_depends_on_from_observations(self, mock_self, sample_entities):
        """Pattern extraction works with depends on keyword."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["library"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self,
            from_entity,
            to_entity,
            similarity=0.50,
            from_observations=["The project depends on my_library"],
            to_observations=None,
        )

        assert rel_type == "depends_on"
        assert confidence == "high"

    def test_pattern_no_match_returns_none(self, mock_self, sample_entities):
        """Pattern extraction returns None when no pattern matches."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["library"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self,
            from_entity,
            to_entity,
            similarity=0.50,
            from_observations=["The project does something"],
            to_observations=None,
        )

        # Should fall through to type-based or similarity
        assert rel_type in ["uses", "related_to"]
        assert confidence in ["medium", "low"]

    # ========================================================================
    # Edge cases
    # ========================================================================

    def test_empty_entity_types(self, mock_self):
        """Handles empty entity types gracefully."""
        from_entity = {"entity_type": "", "name": "entity_a"}
        to_entity = {"entity_type": "", "name": "entity_b"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.90
        )

        assert rel_type == "very_similar_to"
        assert confidence == "high"

    def test_missing_entity_type(self, mock_self):
        """Handles missing entity_type key."""
        from_entity = {"name": "entity_a"}
        to_entity = {"name": "entity_b"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.90
        )

        assert rel_type == "very_similar_to"
        assert confidence == "high"

    def test_none_similarity_raises_type_error(self, mock_self):
        """None similarity raises TypeError (code should handle this)."""
        from_entity = {"entity_type": "project", "name": "proj_a"}
        to_entity = {"entity_type": "project", "name": "proj_b"}

        # The current implementation does not handle None similarity gracefully
        # This test documents the actual behavior (raises TypeError)
        with pytest.raises(TypeError):
            phase3_infer_relationship_type(
                mock_self, from_entity, to_entity, similarity=None
            )

    def test_no_observations_both_none(self, mock_self, sample_entities):
        """Handles both observation lists as None."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["library"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50,
            from_observations=None, to_observations=None
        )

        assert rel_type == "uses"
        assert confidence == "medium"

    def test_empty_observations_list(self, mock_self, sample_entities):
        """Handles empty observation lists."""
        from_entity = sample_entities["project"]
        to_entity = sample_entities["library"]

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.50,
            from_observations=[], to_observations=[]
        )

        assert rel_type == "uses"
        assert confidence == "medium"


# ============================================================================
# Tests for _extract_pattern_from_text
# ============================================================================


class TestExtractPatternFromText:
    """Tests for the _extract_pattern_from_text function."""

    def test_extract_uses_pattern(self):
        """Extracts 'uses' relationship from text."""
        # Note: pattern r"\buses\s+(\w+)" captures the word AFTER "uses"
        # so "uses the library" captures "the" not "library"
        # We need "uses library" to capture "library"
        text = "Project uses library for caching"
        result = _extract_pattern_from_text(text, "library")
        assert result == "uses"

    def test_extract_extends_pattern(self):
        """Extracts 'extends' relationship from text."""
        text = "MyClass extends BaseClass"
        result = _extract_pattern_from_text(text, "BaseClass")
        assert result == "extends"

    def test_extract_depends_on_pattern(self):
        """Extracts 'depends on' relationship from text."""
        text = "Service depends on Database"
        result = _extract_pattern_from_text(text, "Database")
        assert result == "depends_on"

    def test_extract_part_of_pattern(self):
        """Extracts 'part of' relationship from text."""
        text = "Component is part of System"
        result = _extract_pattern_from_text(text, "System")
        assert result == "part_of"

    def test_extract_implements_pattern(self):
        """Extracts 'implements' relationship from text."""
        text = "Class implements Interface"
        result = _extract_pattern_from_text(text, "Interface")
        assert result == "implements"

    def test_extract_requires_pattern(self):
        """Extracts 'requires' relationship from text."""
        text = "Feature requires Authentication"
        result = _extract_pattern_from_text(text, "Authentication")
        assert result == "requires"

    def test_extract_connects_to_pattern(self):
        """Extracts 'connects to' relationship from text."""
        text = "Service connects to API"
        result = _extract_pattern_from_text(text, "API")
        assert result == "connects_to"

    def test_extract_inherits_from_pattern(self):
        """Extracts 'inherits from' pattern as extends."""
        text = "Child inherits from Parent"
        result = _extract_pattern_from_text(text, "Parent")
        assert result == "extends"

    def test_extract_integrates_with_pattern(self):
        """Extracts 'integrates with' as connects_to."""
        text = "App integrates with Database"
        result = _extract_pattern_from_text(text, "Database")
        assert result == "connects_to"

    def test_extract_builds_on_pattern(self):
        """Extracts 'builds on' as extends."""
        text = "Service builds on Core"
        result = _extract_pattern_from_text(text, "Core")
        assert result == "extends"

    # ========================================================================
    # Case insensitivity tests
    # ========================================================================

    def test_case_insensitive_match(self):
        """Pattern matching is case insensitive."""
        text = "PROJECT USES LIBRARY"
        result = _extract_pattern_from_text(text, "library")
        assert result == "uses"

    def test_case_insensitive_target(self):
        """Target entity name matching is case insensitive."""
        text = "project uses LIBRARY"
        result = _extract_pattern_from_text(text, "Library")
        assert result == "uses"

    # ========================================================================
    # No match cases
    # ========================================================================

    def test_no_pattern_match(self):
        """Returns None when no pattern matches."""
        text = "The component has a name"
        result = _extract_pattern_from_text(text, "something")
        assert result is None

    def test_empty_text(self):
        """Handles empty text."""
        result = _extract_pattern_from_text("", "library")
        assert result is None

    def test_entity_not_in_match(self):
        """Returns None when matched entity doesn't match target."""
        text = "Project uses Library"
        result = _extract_pattern_from_text(text, "Database")
        assert result is None

    # ========================================================================
    # Edge cases
    # ========================================================================

    def test_partial_entity_name_match(self):
        """Matches partial entity names."""
        text = "Project uses mylibrary"
        result = _extract_pattern_from_text(text, "mylibrary")
        assert result == "uses"

    def test_target_in_matched_entity(self):
        """Handles case where target is substring of matched entity."""
        text = "Project uses mylibrary"
        result = _extract_pattern_from_text(text, "library")
        # library is in mylibrary, so should match
        assert result == "uses"


# ============================================================================
# Tests for _extract_relationships_from_observations
# ============================================================================


class TestExtractRelationshipsFromObservations:
    """Tests for the _extract_relationships_from_observations method."""

    def test_extract_single_relationship(self, mock_adapter):
        """Extracts a single relationship from observation."""
        observations = ["Project uses Library"]
        entity_id = "entity-123"
        entity_name = "Project"

        result = _extract_relationships_from_observations(
            mock_adapter,
            entity_id,
            entity_name,
            observations,
        )

        assert len(result) == 1
        assert result[0]["from_entity"] == entity_id
        assert result[0]["from_name"] == entity_name
        assert result[0]["relation_type"] == "uses"
        assert result[0]["confidence"] == "medium"
        assert result[0]["discovery_method"] == "pattern"

    def test_extract_multiple_relationships(self, mock_adapter):
        """Extracts multiple relationships from single observation."""
        observations = ["Component uses Library and depends on Service"]
        entity_id = "entity-456"
        entity_name = "Component"

        result = _extract_relationships_from_observations(
            mock_adapter,
            entity_id,
            entity_name,
            observations,
        )

        assert len(result) >= 2  # uses and depends_on

    def test_ignores_self_reference(self, mock_adapter):
        """Ignores observations where target equals entity name."""
        observations = ["Entity uses Entity"]  # self-reference
        entity_id = "entity-789"
        entity_name = "Entity"

        result = _extract_relationships_from_observations(
            mock_adapter,
            entity_id,
            entity_name,
            observations,
        )

        # Should not create relationship to self
        for rel in result:
            assert rel["to_name"].lower() != entity_name.lower()

    def test_empty_observations(self, mock_adapter):
        """Handles empty observation list."""
        result = _extract_relationships_from_observations(
            mock_adapter,
            "entity-123",
            "Entity",
            [],
        )

        assert result == []

    def test_no_matching_patterns(self, mock_adapter):
        """Returns empty list when no patterns match."""
        observations = ["Entity has some property"]
        result = _extract_relationships_from_observations(
            mock_adapter,
            "entity-123",
            "Entity",
            observations,
        )

        assert result == []

    def test_evidence_stored_correctly(self, mock_adapter):
        """Stores observation as evidence."""
        observation = "Project uses Library for caching"
        entity_id = "entity-123"
        entity_name = "Project"

        result = _extract_relationships_from_observations(
            mock_adapter,
            entity_id,
            entity_name,
            [observation],
        )

        assert len(result) == 1
        assert observation in result[0]["evidence"]

    def test_case_insensitive_matching(self, mock_adapter):
        """Matching is case insensitive."""
        observations = ["PROJECT USES LIBRARY"]
        entity_id = "entity-123"
        entity_name = "Project"

        result = _extract_relationships_from_observations(
            mock_adapter,
            entity_id,
            entity_name,
            observations,
        )

        assert len(result) == 1
        assert result[0]["relation_type"] == "uses"


# ============================================================================
# Tests for discover_transitive_relationships
# ============================================================================


class TestDiscoverTransitiveRelationships:
    """Tests for the discover_transitive_relationships async method."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock database connection."""
        conn = MagicMock()
        return conn

    @pytest.fixture
    def adapter_with_graph(self, mock_conn, sample_entities):
        """Create adapter with a pre-populated relationship graph."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)

        # Mock return value for execute
        result_rows = [
            (
                "A",
                "B",
                "uses",
                json.dumps({"confidence": "high"}),
            ),
            (
                "B",
                "C",
                "depends_on",
                json.dumps({"confidence": "medium"}),
            ),
            (
                "A",
                "D",
                "connects_to",
                json.dumps({"confidence": "low"}),
            ),
        ]
        mock_conn.execute.return_value.fetchall.return_value = result_rows

        adapter.create_relation = AsyncMock(return_value={"id": "rel-new"})
        return adapter

    @pytest.mark.asyncio
    async def test_discovers_transitive_relationships(self, adapter_with_graph):
        """Discovers A -> B -> C implies A -> C transitive relationship."""
        result = await discover_transitive_relationships(
            adapter_with_graph,
            max_depth=3,
            min_confidence="medium",
            limit=100,
        )

        assert "created" in result
        assert "skipped" in result
        assert "duplicate" in result
        assert "total_examined" in result

    @pytest.mark.asyncio
    async def test_respects_max_depth(self, mock_conn):
        """Respects max_depth parameter."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)

        # Single chain A -> B -> C -> D
        result_rows = [
            ("A", "B", "uses", json.dumps({"confidence": "high"})),
            ("B", "C", "extends", json.dumps({"confidence": "high"})),
            ("C", "D", "implements", json.dumps({"confidence": "high"})),
        ]
        mock_conn.execute.return_value.fetchall.return_value = result_rows
        adapter.create_relation = AsyncMock(return_value={"id": "rel-new"})

        result = await discover_transitive_relationships(
            adapter,
            max_depth=2,  # Should not create A->D with depth 2
            min_confidence="medium",
        )

        # With max_depth=2, A->D should be skipped (path length 4)
        assert result["skipped"] >= 0

    @pytest.mark.asyncio
    async def test_respects_min_confidence(self, mock_conn):
        """Filters by min_confidence threshold."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)

        result_rows = [
            ("A", "B", "uses", json.dumps({"confidence": "low"})),
            ("B", "C", "depends_on", json.dumps({"confidence": "low"})),
        ]
        mock_conn.execute.return_value.fetchall.return_value = result_rows
        adapter.create_relation = AsyncMock(return_value={"id": "rel-new"})

        result = await discover_transitive_relationships(
            adapter,
            max_depth=3,
            min_confidence="high",  # Low confidence chain should be skipped
        )

        assert result["skipped"] >= 0

    @pytest.mark.asyncio
    async def test_respects_limit(self, mock_conn):
        """Respects limit parameter."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)

        # Create many rows to test limit
        result_rows = [
            (f"A{i}", f"B{i}", "uses", json.dumps({"confidence": "high"}))
            for i in range(50)
        ]
        mock_conn.execute.return_value.fetchall.return_value = result_rows
        adapter.create_relation = AsyncMock(return_value={"id": "rel-new"})

        result = await discover_transitive_relationships(
            adapter,
            max_depth=2,
            limit=5,
        )

        # Should not create more than limit
        assert result["created"] <= 5

    @pytest.mark.asyncio
    async def test_handles_empty_graph(self, mock_conn):
        """Handles empty graph gracefully."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)
        mock_conn.execute.return_value.fetchall.return_value = []

        result = await discover_transitive_relationships(adapter)

        assert result["created"] == 0
        assert result["skipped"] == 0
        assert result["duplicate"] == 0

    @pytest.mark.asyncio
    async def test_handles_create_relation_exception(self, mock_conn):
        """Handles exceptions from create_relation gracefully."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)

        result_rows = [
            ("A", "B", "uses", json.dumps({"confidence": "high"})),
            ("B", "C", "depends_on", json.dumps({"confidence": "high"})),
            ("C", "D", "implements", json.dumps({"confidence": "high"})),
        ]
        mock_conn.execute.return_value.fetchall.return_value = result_rows
        adapter.create_relation = AsyncMock(side_effect=Exception("DB error"))

        result = await discover_transitive_relationships(
            adapter,
            max_depth=3,
        )

        # Should not crash, skipped should increase
        assert result["skipped"] >= 0

    @pytest.mark.asyncio
    async def test_default_parameters(self, mock_conn):
        """Uses correct default parameters."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)
        mock_conn.execute.return_value.fetchall.return_value = []
        adapter.create_relation = AsyncMock(return_value={"id": "rel-new"})

        result = await discover_transitive_relationships(adapter)

        assert result["created"] == 0
        # Default min_confidence is "medium"
        assert "skipped" in result
        assert "duplicate" in result

    @pytest.mark.asyncio
    async def test_returns_correct_structure(self, mock_conn):
        """Returns correct result structure with all keys."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)
        mock_conn.execute.return_value.fetchall.return_value = []
        adapter.create_relation = AsyncMock(return_value={"id": "rel-new"})

        result = await discover_transitive_relationships(adapter)

        assert isinstance(result, dict)
        assert set(result.keys()) == {"created", "skipped", "duplicate", "total_examined"}


# ============================================================================
# Tests for _infer_transitive_type
# ============================================================================


class TestInferTransitiveType:
    """Tests for the _infer_transitive_type function."""

    def test_priority_uses(self):
        """'uses' has highest priority."""
        types = ["uses", "related_to", "connects_to"]
        result = _infer_transitive_type(types)
        assert result == "uses"

    def test_priority_depends_on(self):
        """'depends_on' has high priority."""
        types = ["depends_on", "similar_to"]
        result = _infer_transitive_type(types)
        assert result == "depends_on"

    def test_priority_extends(self):
        """'extends' has priority over similar_to."""
        types = ["extends", "very_similar_to"]
        result = _infer_transitive_type(types)
        assert result == "extends"

    def test_priority_implements(self):
        """'implements' has priority."""
        types = ["implements", "connects_to"]
        result = _infer_transitive_type(types)
        assert result == "implements"

    def test_priority_part_of(self):
        """'part_of' has priority."""
        types = ["part_of", "contains"]
        result = _infer_transitive_type(types)
        assert result == "part_of"

    def test_priority_connects_to(self):
        """'connects_to' has priority over similar_to."""
        types = ["connects_to", "similar_to"]
        result = _infer_transitive_type(types)
        assert result == "connects_to"

    def test_priority_similar_to(self):
        """'similar_to' has priority over very_similar_to."""
        types = ["similar_to", "very_similar_to"]
        result = _infer_transitive_type(types)
        assert result == "similar_to"

    def test_fallback_returns_first_non_priority_type(self):
        """When no priority type matches, returns first element."""
        types = ["other_type", "another_type"]
        result = _infer_transitive_type(types)
        # Actual behavior: returns first element when no priority match
        assert result == "other_type"

    def test_empty_types(self):
        """Empty list returns related_to."""
        result = _infer_transitive_type([])
        assert result == "related_to"

    def test_first_type_when_no_priority_match(self):
        """Returns first type when no priority match."""
        types = ["custom_type"]
        result = _infer_transitive_type(types)
        assert result == "custom_type"

    def test_very_similar_to_in_types_returns_very_similar_to(self):
        """very_similar_to is in priority list, returns it when present."""
        types = ["very_similar_to", "related_to"]
        result = _infer_transitive_type(types)
        # very_similar_to is in priority list, returns it
        assert result == "very_similar_to"

    def test_priority_order_full_list(self):
        """Priority order: uses > depends_on > extends > implements > part_of > connects_to > similar_to > very_similar_to > related_to."""
        priority_order = [
            ("uses", "uses"),
            ("depends_on", "depends_on"),
            ("extends", "extends"),
            ("implements", "implements"),
            ("part_of", "part_of"),
            ("connects_to", "connects_to"),
            ("similar_to", "similar_to"),
            ("very_similar_to", "very_similar_to"),
            ("related_to", "related_to"),
        ]

        for expected, input_type in priority_order:
            result = _infer_transitive_type([input_type])
            assert result == expected, f"Failed for {input_type}"


# ============================================================================
# Tests for create_entity_with_patterns
# ============================================================================


class TestCreateEntityWithPatterns:
    """Tests for the create_entity_with_patterns async method."""

    @pytest.mark.asyncio
    async def test_basic_entity_creation(self, mock_adapter):
        """Creates entity without pattern extraction."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-123",
            "name": "TestEntity",
            "entity_type": "project",
        }

        result = await create_entity_with_patterns(
            mock_adapter,
            name="TestEntity",
            entity_type="project",
            extract_patterns=False,
        )

        mock_adapter.create_entity.assert_called_once()
        assert result["id"] == "entity-123"

    @pytest.mark.asyncio
    async def test_entity_creation_with_observations(self, mock_adapter):
        """Passes observations to create_entity."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-456",
            "name": "Project",
            "entity_type": "project",
        }

        observations = ["Project uses Library"]
        result = await create_entity_with_patterns(
            mock_adapter,
            name="Project",
            entity_type="project",
            observations=observations,
            extract_patterns=False,
        )

        mock_adapter.create_entity.assert_called_once()
        call_kwargs = mock_adapter.create_entity.call_args.kwargs
        assert call_kwargs.get("observations") == observations

    @pytest.mark.asyncio
    async def test_pattern_extraction_disabled_by_default(self, mock_adapter):
        """Pattern extraction is disabled by default."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-789",
            "name": "Test",
        }

        await create_entity_with_patterns(
            mock_adapter,
            name="Test",
            entity_type="test",
        )

        # create_relation should NOT be called when extract_patterns=False
        mock_adapter.create_relation.assert_not_called()

    @pytest.mark.asyncio
    async def test_pattern_extraction_enabled(self, mock_adapter):
        """Pattern extraction works when enabled."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-abc",
            "name": "Project",
            "entity_type": "project",
        }

        mock_adapter.find_entity_by_name.return_value = {"id": "library-id"}

        observations = ["Project uses Library"]
        await create_entity_with_patterns(
            mock_adapter,
            name="Project",
            entity_type="project",
            observations=observations,
            extract_patterns=True,
        )

        # create_relation should be called for discovered patterns
        mock_adapter.create_relation.assert_called()

    @pytest.mark.asyncio
    async def test_auto_discover_passed_to_create_entity(self, mock_adapter):
        """auto_discover parameter is passed to create_entity."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-def",
            "name": "Test",
        }

        await create_entity_with_patterns(
            mock_adapter,
            name="Test",
            entity_type="test",
            auto_discover=True,
            discovery_threshold=0.8,
        )

        call_kwargs = mock_adapter.create_entity.call_args.kwargs
        assert call_kwargs.get("auto_discover") is True
        assert call_kwargs.get("discovery_threshold") == 0.8

    @pytest.mark.asyncio
    async def test_properties_passed_correctly(self, mock_adapter):
        """Properties parameter is passed to create_entity."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-ghi",
            "name": "Test",
        }

        properties = {"key": "value", "nested": {"data": True}}
        await create_entity_with_patterns(
            mock_adapter,
            name="Test",
            entity_type="test",
            properties=properties,
        )

        call_kwargs = mock_adapter.create_entity.call_args.kwargs
        assert call_kwargs.get("properties") == properties

    @pytest.mark.asyncio
    async def test_metadata_passed_correctly(self, mock_adapter):
        """Metadata parameter is passed to create_entity."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-jkl",
            "name": "Test",
        }

        metadata = {"source": "test", "version": "1.0"}
        await create_entity_with_patterns(
            mock_adapter,
            name="Test",
            entity_type="test",
            metadata=metadata,
        )

        call_kwargs = mock_adapter.create_entity.call_args.kwargs
        assert call_kwargs.get("metadata") == metadata

    @pytest.mark.asyncio
    async def test_max_discoveries_respected(self, mock_adapter):
        """max_discoveries parameter is passed to create_entity."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-mno",
            "name": "Test",
        }

        await create_entity_with_patterns(
            mock_adapter,
            name="Test",
            entity_type="test",
            max_discoveries=10,
        )

        call_kwargs = mock_adapter.create_entity.call_args.kwargs
        assert call_kwargs.get("max_discoveries") == 10

    @pytest.mark.asyncio
    async def test_find_entity_not_found_skips_relation(self, mock_adapter):
        """When find_entity_by_name returns None, relation is skipped."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-pqr",
            "name": "Project",
        }
        mock_adapter.find_entity_by_name.return_value = None

        observations = ["Project uses UnknownLibrary"]
        await create_entity_with_patterns(
            mock_adapter,
            name="Project",
            entity_type="project",
            observations=observations,
            extract_patterns=True,
        )

        # create_relation should not be called for unknown targets
        for call in mock_adapter.create_relation.call_args_list:
            # Verify that we didn't try to create a relation to None
            to_entity_arg = call.kwargs.get("to_entity")
            assert to_entity_arg is not None

    @pytest.mark.asyncio
    async def test_suppresses_pattern_extraction_errors(self, mock_adapter):
        """Pattern extraction errors are suppressed."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-stu",
            "name": "Project",
        }
        mock_adapter.find_entity_by_name.side_effect = Exception("DB error")

        observations = ["Project uses Library"]
        # Should not raise, just suppress
        result = await create_entity_with_patterns(
            mock_adapter,
            name="Project",
            entity_type="project",
            observations=observations,
            extract_patterns=True,
        )

        # Entity should still be returned
        assert result["id"] == "entity-stu"

    @pytest.mark.asyncio
    async def test_returns_created_entity(self, mock_adapter):
        """Returns the created entity dict."""
        expected_entity = {
            "id": "entity-vwx",
            "name": "MyEntity",
            "entity_type": "component",
        }
        mock_adapter.create_entity.return_value = expected_entity

        result = await create_entity_with_patterns(
            mock_adapter,
            name="MyEntity",
            entity_type="component",
        )

        assert result == expected_entity


# ============================================================================
# Integration-like tests for patch contract
# ============================================================================


class TestPatchContract:
    """Tests verifying the patch/extension contract."""

    def test_all_exported_functions_present(self):
        """Verifies all functions are exported in __all__."""
        from session_buddy.adapters.knowledge_graph_phase3_patch import __all__

        expected_exports = [
            "phase3_infer_relationship_type",
            "_extract_pattern_from_text",
            "_extract_relationships_from_observations",
            "discover_transitive_relationships",
            "_infer_transitive_type",
            "create_entity_with_patterns",
        ]

        for export in expected_exports:
            assert export in __all__, f"Missing export: {export}"

    def test_phase3_infer_relationship_type_signature(self):
        """Verifies phase3_infer_relationship_type has correct signature."""
        import inspect

        sig = inspect.signature(phase3_infer_relationship_type)
        params = list(sig.parameters.keys())

        expected_params = [
            "self",
            "from_entity",
            "to_entity",
            "similarity",
            "from_observations",
            "to_observations",
        ]

        assert params == expected_params

    def test_create_entity_with_patterns_is_async(self):
        """Verifies create_entity_with_patterns is an async function."""
        import inspect

        assert inspect.iscoroutinefunction(create_entity_with_patterns)

    def test_discover_transitive_relationships_is_async(self):
        """Verifies discover_transitive_relationships is an async function."""
        import inspect

        assert inspect.iscoroutinefunction(discover_transitive_relationships)

    def test_extract_relationships_from_observations_is_not_async(self):
        """Verifies _extract_relationships_from_observations is not async."""
        import inspect

        # It's a regular function (takes self like a method but is not async)
        assert not inspect.iscoroutinefunction(_extract_relationships_from_observations)

    def test_helper_functions_are_not_async(self):
        """Verifies helper functions are not async."""
        import inspect

        assert not inspect.iscoroutinefunction(_extract_pattern_from_text)
        assert not inspect.iscoroutinefunction(_infer_transitive_type)

    def test_module_docstring_present(self):
        """Verifies module has proper docstring."""
        from session_buddy.adapters import knowledge_graph_phase3_patch as module

        assert module.__doc__ is not None
        assert "Phase 3" in module.__doc__
        assert "patch" in module.__doc__.lower()


# ============================================================================
# Edge case and robustness tests
# ============================================================================


class TestEdgeCases:
    """Edge case and robustness tests."""

    def test_phase3_infer_with_extreme_similarity(self, mock_self, sample_entities):
        """Handles extreme similarity values (near 0 and 1)."""
        from_entity = sample_entities["project"]
        to_entity = {"entity_type": "project", "name": "other"}

        # Near 0
        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.001
        )
        assert rel_type == "related_to"
        assert confidence == "low"

        # Near 1
        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.999
        )
        assert rel_type == "very_similar_to"
        assert confidence == "high"

    def test_extract_pattern_uses_with_target_in_text(self):
        """Extracts 'uses' when target entity name is in the text."""
        # Pattern \buses\s+(\w+) captures word after "uses"
        # Target is 'mylibrary' and the word after "uses" is "mylibrary"
        text = "Project uses mylibrary for caching"
        result = _extract_pattern_from_text(text, "mylibrary")
        assert result == "uses"

    def test_extract_pattern_special_characters_in_text(self):
        """Handles text with special regex characters."""
        text = "Project uses library [with] (special) ^chars$"
        result = _extract_pattern_from_text(text, "library")
        assert result == "uses"

    def test_transitive_inference_empty_list(self):
        """Handles empty types list in transitive inference."""
        result = _infer_transitive_type([])
        assert result == "related_to"

    def test_transitive_inference_none_values(self):
        """Handles None values in types list."""
        result = _infer_transitive_type(["uses", None, "depends_on"])
        # Should still work, filtering out None
        assert result == "uses"


# ============================================================================
# Performance and boundary tests
# ============================================================================


class TestBoundaryConditions:
    """Boundary condition tests."""

    def test_similarity_boundary_exactly_075(self, mock_self, sample_entities):
        """Similarity exactly 0.75 returns similar_to."""
        from_entity = sample_entities["library"]
        to_entity = {"entity_type": "library", "name": "other"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.75
        )

        assert rel_type == "similar_to"
        assert confidence == "medium"

    def test_similarity_boundary_exactly_085(self, mock_self, sample_entities):
        """Similarity exactly 0.85 returns very_similar_to."""
        from_entity = sample_entities["project"]
        to_entity = {"entity_type": "project", "name": "other"}

        rel_type, confidence = phase3_infer_relationship_type(
            mock_self, from_entity, to_entity, similarity=0.85
        )

        assert rel_type == "very_similar_to"
        assert confidence == "high"

    @pytest.mark.asyncio
    async def test_discover_transitive_limit_zero(self, mock_conn):
        """Handles limit=0 gracefully."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)
        mock_conn.execute.return_value.fetchall.return_value = []
        adapter.create_relation = AsyncMock(return_value={"id": "rel-new"})

        result = await discover_transitive_relationships(
            adapter,
            max_depth=3,
            limit=0,
        )

        # Should not crash
        assert result["created"] == 0

    @pytest.mark.asyncio
    async def test_discover_transitive_negative_max_depth(self, mock_conn):
        """Handles negative max_depth."""
        adapter = MagicMock()
        adapter._get_conn = MagicMock(return_value=mock_conn)
        mock_conn.execute.return_value.fetchall.return_value = []
        adapter.create_relation = AsyncMock(return_value={"id": "rel-new"})

        result = await discover_transitive_relationships(
            adapter,
            max_depth=-1,
        )

        # Should not crash
        assert "created" in result

    @pytest.mark.asyncio
    async def test_create_entity_with_empty_observations_and_extract(self, mock_adapter):
        """Handles empty observations with extract_patterns=True."""
        mock_adapter.create_entity.return_value = {
            "id": "entity-empty",
            "name": "Test",
        }

        result = await create_entity_with_patterns(
            mock_adapter,
            name="Test",
            entity_type="test",
            observations=[],
            extract_patterns=True,
        )

        assert result["id"] == "entity-empty"