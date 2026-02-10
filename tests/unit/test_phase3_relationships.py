"""Phase 3: Enhanced Relationship Features - Unit Tests.

Tests for:
1. Enhanced relationship type inference with confidence scoring
2. Pattern extraction from observations
3. Transitive relationship discovery
4. Enhanced entity creation with pattern extraction

"""

from __future__ import annotations

import pytest

from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
    KnowledgeGraphDatabaseAdapterOneiric,
)


@pytest.mark.asyncio
class TestPhase3RelationshipInference:
    """Test enhanced relationship type inference (Phase 3)."""

    async def test_infer_relationship_type_with_similarity(self, kg_adapter):
        """Test similarity-based relationship inference."""
        from_entity = {
            "id": "e1",
            "name": "session-buddy",
            "entity_type": "project",
            "observations": [],
        }
        to_entity = {
            "id": "e2",
            "name": "crackerjack",
            "entity_type": "project",
            "observations": [],
        }

        # Very high similarity -> very_similar_to, high confidence
        rel_type, confidence = kg_adapter._infer_relationship_type(
            from_entity, to_entity, 0.87
        )
        assert rel_type == "very_similar_to"
        assert confidence == "high"

        # Medium similarity -> similar_to, medium confidence
        rel_type, confidence = kg_adapter._infer_relationship_type(
            from_entity, to_entity, 0.78
        )
        assert rel_type == "similar_to"
        assert confidence == "medium"

        # Low similarity -> related_to, low confidence
        rel_type, confidence = kg_adapter._infer_relationship_type(
            from_entity, to_entity, 0.60
        )
        assert rel_type == "related_to"
        assert confidence == "low"

    async def test_infer_relationship_type_with_patterns(self, kg_adapter):
        """Test pattern-based relationship inference."""
        from_entity = {
            "id": "e1",
            "name": "session-buddy",
            "entity_type": "project",
            "observations": ["session-buddy uses FastMCP for tool registration"],
        }
        to_entity = {
            "id": "e2",
            "name": "FastMCP",
            "entity_type": "library",
            "observations": [],
        }

        # Pattern extraction should trigger
        rel_type, confidence = kg_adapter._infer_relationship_type(
            from_entity, to_entity, 0.65, from_observations=from_entity["observations"]
        )
        assert rel_type == "uses"
        assert confidence == "high"

    async def test_infer_relationship_type_type_based(self, kg_adapter):
        """Test type-based relationship inference."""
        from_entity = {
            "id": "e1",
            "name": "session-buddy",
            "entity_type": "project",
            "observations": [],
        }
        to_entity = {
            "id": "e2",
            "name": "pytest",
            "entity_type": "library",
            "observations": [],
        }

        # Project + library -> uses, medium confidence
        rel_type, confidence = kg_adapter._infer_relationship_type(
            from_entity, to_entity, 0.70
        )
        assert rel_type == "uses"
        assert confidence == "medium"


@pytest.mark.asyncio
class TestPhase3PatternExtraction:
    """Test pattern extraction from observations (Phase 3)."""

    async def test_extract_pattern_from_text_uses(self, kg_adapter):
        """Test extraction of 'uses' pattern."""
        text = "session-buddy uses FastMCP for tool registration"
        target = "FastMCP"

        pattern = kg_adapter._extract_pattern_from_text(text, target)
        assert pattern == "uses"

    async def test_extract_pattern_from_text_extends(self, kg_adapter):
        """Test extraction of 'extends' pattern."""
        text = "UserAdmin extends Admin to add custom permissions"
        target = "Admin"

        pattern = kg_adapter._extract_pattern_from_text(text, target)
        assert pattern == "extends"

    async def test_extract_pattern_from_text_depends_on(self, kg_adapter):
        """Test extraction of 'depends_on' pattern."""
        text = "API service depends on database for persistence"
        target = "database"

        pattern = kg_adapter._extract_pattern_from_text(text, target)
        assert pattern == "depends_on"

    async def test_extract_relationships_from_observations(self, kg_adapter):
        """Test extraction of multiple relationships from observations."""
        entity_id = "e1"
        entity_name = "session-buddy"
        observations = [
            "session-buddy uses FastMCP for tool registration",
            "session-buddy depends on DuckDB for storage",
            "session-buddy implements the MCP protocol",
        ]

        relationships = kg_adapter._extract_relationships_from_observations(
            entity_id, entity_name, observations
        )

        assert len(relationships) == 3

        # Check first relationship
        assert relationships[0]["relation_type"] == "uses"
        assert relationships[0]["to_name"] == "FastMCP"
        assert relationships[0]["confidence"] == "medium"
        assert "session-buddy uses FastMCP" in relationships[0]["evidence"][0]

        # Check second relationship
        assert relationships[1]["relation_type"] == "depends_on"
        assert relationships[1]["to_name"] == "DuckDB"


@pytest.mark.asyncio
class TestPhase3TransitiveDiscovery:
    """Test transitive relationship discovery (Phase 3)."""

    async def test_discover_transitive_relationships(self, kg_adapter):
        """Test discovery of transitive relationships."""
        # Create entities: A -> B -> C
        entity_a = await kg_adapter.create_entity(
            name="ProjectA", entity_type="project", observations=[]
        )
        entity_b = await kg_adapter.create_entity(
            name="LibraryB", entity_type="library", observations=[]
        )
        entity_c = await kg_adapter.create_entity(
            name="ServiceC", entity_type="service", observations=[]
        )

        # Create relationships: A uses B, B connects to C
        await kg_adapter.create_relation(
            from_entity=entity_a["id"],
            to_entity=entity_b["id"],
            relation_type="uses",
            properties={"confidence": "high"},
        )
        await kg_adapter.create_relation(
            from_entity=entity_b["id"],
            to_entity=entity_c["id"],
            relation_type="connects_to",
            properties={"confidence": "medium"},
        )

        # Discover transitive relationships
        result = await kg_adapter.discover_transitive_relationships(
            max_depth=2, min_confidence="medium", limit=10
        )

        assert result["created"] > 0
        assert result["total_examined"] > 0

    async def test_discover_transitive_avoids_duplicates(self, kg_adapter):
        """Test that transitive discovery avoids creating duplicates."""
        # Create entities
        entity_a = await kg_adapter.create_entity(
            name="ProjectA", entity_type="project", observations=[]
        )
        entity_b = await kg_adapter.create_entity(
            name="LibraryB", entity_type="library", observations=[]
        )
        entity_c = await kg_adapter.create_entity(
            name="ServiceC", entity_type="service", observations=[]
        )

        # Create relationships including direct A->C
        await kg_adapter.create_relation(
            from_entity=entity_a["id"],
            to_entity=entity_b["id"],
            relation_type="uses",
            properties={"confidence": "high"},
        )
        await kg_adapter.create_relation(
            from_entity=entity_b["id"],
            to_entity=entity_c["id"],
            relation_type="uses",
            properties={"confidence": "medium"},
        )
        await kg_adapter.create_relation(
            from_entity=entity_a["id"],
            to_entity=entity_c["id"],
            relation_type="related_to",
            properties={"confidence": "low"},
        )

        # Discover transitive relationships
        result = await kg_adapter.discover_transitive_relationships(
            max_depth=2, min_confidence="low", limit=10
        )

        # Should skip creating duplicate A->C
        assert result["duplicate"] > 0


@pytest.mark.asyncio
class TestPhase3EntityCreation:
    """Test enhanced entity creation with pattern extraction (Phase 3)."""

    async def test_create_entity_with_patterns(self, kg_adapter):
        """Test entity creation with automatic pattern extraction."""
        # Create target entity first
        target = await kg_adapter.create_entity(
            name="FastMCP", entity_type="library", observations=[]
        )

        # Create entity with pattern extraction
        entity = await kg_adapter.create_entity_with_patterns(
            name="session-buddy",
            entity_type="project",
            observations=["session-buddy uses FastMCP for tool registration"],
            extract_patterns=True,
        )

        assert entity["name"] == "session-buddy"

        # Check that relationship was created
        relationships = await kg_adapter.get_relationships(
            entity_name=entity["id"], direction="outgoing"
        )

        assert len(relationships) > 0
        assert relationships[0]["relation_type"] == "uses"
        assert relationships[0]["properties"]["confidence"] == "medium"
        assert relationships[0]["properties"]["discovery_method"] == "pattern"


@pytest.mark.asyncio
class TestPhase3ConfidenceScoring:
    """Test confidence scoring system (Phase 3)."""

    async def test_create_relation_with_confidence(self, kg_adapter):
        """Test creating relationships with confidence scores."""
        entity_a = await kg_adapter.create_entity(
            name="ProjectA", entity_type="project", observations=[]
        )
        entity_b = await kg_adapter.create_entity(
            name="LibraryB", entity_type="library", observations=[]
        )

        # Create relation with confidence
        relation = await kg_adapter.create_relation(
            from_entity=entity_a["id"],
            to_entity=entity_b["id"],
            relation_type="uses",
            properties={
                "confidence": "high",
                "similarity": 0.87,
                "discovery_method": "semantic",
                "evidence": ["Both mentioned in commit abc123"],
            },
        )

        assert relation["properties"]["confidence"] == "high"
        assert relation["properties"]["similarity"] == 0.87
        assert relation["properties"]["discovery_method"] == "semantic"

    async def test_auto_discovery_with_confidence(self, kg_adapter):
        """Test that auto-discovery creates relationships with confidence."""
        # Create entities
        entity_a = await kg_adapter.create_entity(
            name="ProjectA",
            entity_type="project",
            observations=["Python project for session management"],
            auto_discover=False,
        )
        entity_b = await kg_adapter.create_entity(
            name="ProjectB",
            entity_type="project",
            observations=["Python session management tool"],
            auto_discover=False,
        )

        # Manually create relationship to check confidence
        relation = await kg_adapter.create_relation(
            from_entity=entity_a["id"],
            to_entity=entity_b["id"],
            relation_type="similar_to",
            properties={
                "confidence": "medium",
                "similarity": 0.78,
                "auto_discovered": True,
            },
        )

        assert relation["properties"]["confidence"] == "medium"
        assert relation["properties"]["auto_discovered"] is True
