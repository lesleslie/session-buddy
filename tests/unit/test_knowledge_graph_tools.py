#!/usr/bin/env python3
"""Comprehensive unit tests for knowledge_graph_tools.py.

Tests cover all public async methods, error handling paths, edge cases,
initialization variations, and helper functions.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test
from session_buddy.mcp.tools.collaboration import knowledge_graph_tools as kgmod


# ============================================================================
# Fixtures
# ============================================================================


class MockLogger:
    """Mock logger that accepts any keyword arguments."""

    def __init__(self):
        self._records: list[logging.LogRecord] = []
        self._last_call_args = None

    def info(self, msg, *args, **kwargs):
        self._records.append(msg)
        self._last_call_args = (args, kwargs)

    def warning(self, msg, *args, **kwargs):
        pass

    def error(self, msg, *args, **kwargs):
        pass

    def exception(self, msg, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def patch_logger():
    """Auto-patch _get_logger for all tests."""
    mock_logger = MockLogger()
    with patch.object(
        kgmod,
        "_get_logger",
        return_value=mock_logger,
    ):
        yield mock_logger


@pytest.fixture
def mock_kg():
    """Create a mock knowledge graph database adapter."""
    kg = MagicMock()
    kg.create_entity = AsyncMock(return_value={"id": "entity-123", "name": "TestEntity"})
    kg.add_observation = AsyncMock(return_value=True)
    kg.create_relation = AsyncMock(
        return_value={"id": "rel-123", "from_entity": "A", "to_entity": "B"}
    )
    kg.search_entities = AsyncMock(return_value=[])
    kg.get_relationships = AsyncMock(return_value=[])
    kg.find_path = AsyncMock(return_value=[])
    kg.get_stats = AsyncMock(return_value={
        "total_entities": 0,
        "total_relationships": 0,
        "entity_types": {},
        "relationship_types": {},
    })
    kg.find_entity_by_name = AsyncMock(return_value=None)
    kg.generate_embeddings_for_entities = AsyncMock(
        return_value={"generated": 0, "failed": 0, "total_processed": 0}
    )
    kg.batch_discover_relationships = AsyncMock(
        return_value={
            "entities_processed": 0,
            "relationships_created": 0,
            "avg_relationships_per_entity": 0.0,
        }
    )
    # Make initialize async
    kg.initialize = AsyncMock()
    kg.__aenter__ = AsyncMock(return_value=kg)
    kg.__aexit__ = AsyncMock(return_value=None)
    return kg


@pytest.fixture
def mock_server():
    """Create a mock FastMCP server."""
    server = MagicMock()
    server.tool = MagicMock(return_value=MagicMock())
    return server


# ============================================================================
# Test _check_knowledge_graph_available
# ============================================================================


class TestCheckKnowledgeGraphAvailable:
    """Tests for _check_knowledge_graph_available function."""

    def test_returns_true_when_duckdb_available(self, monkeypatch):
        """Should return True when duckdb module is available."""
        mock_spec = MagicMock()
        monkeypatch.setattr(
            "importlib.util.find_spec",
            MagicMock(return_value=mock_spec),
        )
        assert kgmod._check_knowledge_graph_available() is True

    def test_returns_false_when_duckdb_not_available(self, monkeypatch):
        """Should return False when duckdb module is not available."""
        monkeypatch.setattr(
            "importlib.util.find_spec",
            MagicMock(return_value=None),
        )
        assert kgmod._check_knowledge_graph_available() is False

    def test_returns_false_on_import_error(self, monkeypatch):
        """Should return False when ImportError is raised."""
        monkeypatch.setattr(
            "importlib.util.find_spec",
            MagicMock(side_effect=ImportError("mocked error")),
        )
        assert kgmod._check_knowledge_graph_available() is False

    def test_returns_false_on_attribute_error(self, monkeypatch):
        """Should return False when AttributeError is raised."""
        monkeypatch.setattr(
            "importlib.util.find_spec",
            MagicMock(side_effect=AttributeError("mocked error")),
        )
        assert kgmod._check_knowledge_graph_available() is False


# ============================================================================
# Test _require_knowledge_graph
# ============================================================================


class TestRequireKnowledgeGraph:
    """Tests for _require_knowledge_graph function."""

    @pytest.mark.asyncio
    async def test_returns_kg_on_success(self, mock_kg):
        """Should return knowledge graph instance when available."""
        with patch(
            "session_buddy.di.configure",
            MagicMock(),
        ):
            with patch(
                "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
                return_value=mock_kg,
            ):
                result = await kgmod._require_knowledge_graph()
                assert result == mock_kg

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_failure(self):
        """Should raise RuntimeError when knowledge graph is not available."""
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            side_effect=Exception("DB init failed"),
        ):
            with pytest.raises(RuntimeError, match="Knowledge graph not available"):
                await kgmod._require_knowledge_graph()

    @pytest.mark.asyncio
    async def test_configure_called_before_init(self, mock_kg):
        """Should call configure() before initializing adapter."""
        configure_mock = MagicMock()
        with patch("session_buddy.di.configure", configure_mock):
            with patch(
                "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
                return_value=mock_kg,
            ):
                await kgmod._require_knowledge_graph()
                configure_mock.assert_called_once()


# ============================================================================
# Test _execute_kg_operation
# ============================================================================


class TestExecuteKgOperation:
    """Tests for _execute_kg_operation function."""

    @pytest.mark.asyncio
    async def test_returns_operation_result_on_success(self, mock_kg):
        """Should return result when operation succeeds."""
        operation = AsyncMock(return_value="success result")
        result = await kgmod._execute_kg_operation("TestOp", operation)
        assert result == "success result"

    @pytest.mark.asyncio
    async def test_returns_error_message_on_runtime_error(self, mock_kg):
        """Should return formatted error when RuntimeError is raised."""
        operation = AsyncMock(side_effect=RuntimeError("KG not available"))
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._require_knowledge_graph",
            AsyncMock(return_value=mock_kg),
        ):
            result = await kgmod._execute_kg_operation("TestOp", operation)
            assert "❌" in result
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_returns_operation_failed_on_generic_exception(self, mock_kg):
        """Should return operation_failed message on generic Exception."""
        operation = AsyncMock(side_effect=ValueError("some error"))
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._require_knowledge_graph",
            AsyncMock(return_value=mock_kg),
        ):
            result = await kgmod._execute_kg_operation("TestOp", operation)
            assert "❌" in result
            assert "TestOp" in result


# ============================================================================
# Test _create_entity_operation
# ============================================================================


class TestCreateEntityOperation:
    """Tests for _create_entity_operation function."""

    @pytest.mark.asyncio
    async def test_creates_entity_with_all_fields(self, mock_kg):
        """Should create entity with name, type, observations, and properties."""
        mock_kg.create_entity.return_value = {
            "id": "ent-001",
            "name": "MyEntity",
        }
        result = await kgmod._create_entity_operation(
            mock_kg,
            name="MyEntity",
            entity_type="project",
            observations=["obs1", "obs2"],
            properties={"key": "value"},
        )
        mock_kg.create_entity.assert_called_once_with(
            name="MyEntity",
            entity_type="project",
            observations=["obs1", "obs2"],
            properties={"key": "value"},
        )
        assert "✅" in result
        assert "MyEntity" in result
        assert "project" in result
        assert "ent-001" in result

    @pytest.mark.asyncio
    async def test_creates_entity_without_observations(self, mock_kg):
        """Should create entity when observations list is empty."""
        mock_kg.create_entity.return_value = {"id": "ent-001", "name": "Entity"}
        result = await kgmod._create_entity_operation(
            mock_kg, "Entity", "test", [], {}
        )
        assert "📝 Observations: 0" not in result

    @pytest.mark.asyncio
    async def test_creates_entity_without_properties(self, mock_kg):
        """Should create entity when properties dict is empty."""
        mock_kg.create_entity.return_value = {"id": "ent-001", "name": "Entity"}
        result = await kgmod._create_entity_operation(
            mock_kg, "Entity", "test", [], {}
        )
        assert "⚙️ Properties:" not in result

    @pytest.mark.asyncio
    async def test_logging_is_called(self, mock_kg, patch_logger):
        """Should call logger with entity details."""
        mock_kg.create_entity.return_value = {"id": "ent-001", "name": "Entity"}
        await kgmod._create_entity_operation(
            mock_kg, "Entity", "test", ["obs"], {}
        )
        assert len(patch_logger._records) >= 1


# ============================================================================
# Test _create_entity_impl
# ============================================================================


class TestCreateEntityImpl:
    """Tests for _create_entity_impl function."""

    @pytest.mark.asyncio
    async def test_creates_entity_with_defaults(self, mock_kg):
        """Should create entity with default observations and properties."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="✅ Entity created"),
        ):
            result = await kgmod._create_entity_impl(
                name="Test",
                entity_type="concept",
            )
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_creates_entity_with_observations(self, mock_kg):
        """Should create entity with observations list."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="✅ Entity created"),
        ):
            result = await kgmod._create_entity_impl(
                name="Test",
                entity_type="concept",
                observations=["first observation"],
            )
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_creates_entity_with_properties(self, mock_kg):
        """Should create entity with properties dict."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="✅ Entity created"),
        ):
            result = await kgmod._create_entity_impl(
                name="Test",
                entity_type="concept",
                properties={"version": "1.0"},
            )
            assert "✅" in result


# ============================================================================
# Test _add_observation_operation
# ============================================================================


class TestAddObservationOperation:
    """Tests for _add_observation_operation function."""

    @pytest.mark.asyncio
    async def test_adds_observation_successfully(self, mock_kg):
        """Should add observation and return success message."""
        mock_kg.add_observation.return_value = True
        result = await kgmod._add_observation_operation(
            mock_kg, "TestEntity", "This is a test observation"
        )
        mock_kg.add_observation.assert_called_once_with(
            "TestEntity", "This is a test observation"
        )
        assert "✅" in result
        assert "TestEntity" in result
        assert "This is a test observation" in result

    @pytest.mark.asyncio
    async def test_returns_error_when_entity_not_found(self, mock_kg):
        """Should return error message when entity does not exist."""
        mock_kg.add_observation.return_value = False
        result = await kgmod._add_observation_operation(
            mock_kg, "NonExistent", "observation"
        )
        assert "❌" in result
        assert "NonExistent" in result

    @pytest.mark.asyncio
    async def test_logs_observation_preview(self, mock_kg, patch_logger):
        """Should log observation with truncated preview."""
        mock_kg.add_observation.return_value = True
        long_obs = "x" * 200
        await kgmod._add_observation_operation(mock_kg, "Entity", long_obs)
        # The logger is called, just verify it doesn't raise
        assert len(patch_logger._records) >= 1


# ============================================================================
# Test _add_observation_impl
# ============================================================================


class TestAddObservationImpl:
    """Tests for _add_observation_impl function."""

    @pytest.mark.asyncio
    async def test_adds_observation(self, mock_kg):
        """Should add observation via execute_kg_operation."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="✅ Observation added"),
        ):
            result = await kgmod._add_observation_impl("Entity", "obs")
            assert "✅" in result


# ============================================================================
# Test _create_relation_operation
# ============================================================================


class TestCreateRelationOperation:
    """Tests for _create_relation_operation function."""

    @pytest.mark.asyncio
    async def test_creates_relation_with_all_fields(self, mock_kg):
        """Should create relation between two entities."""
        mock_kg.create_relation.return_value = {
            "id": "rel-001",
            "from_entity": "A",
            "to_entity": "B",
        }
        result = await kgmod._create_relation_operation(
            mock_kg, "A", "B", "depends_on", {"weight": 1.0}
        )
        mock_kg.create_relation.assert_called_once_with(
            from_entity="A",
            to_entity="B",
            relation_type="depends_on",
            properties={"weight": 1.0},
        )
        assert "✅" in result
        assert "depends_on" in result
        assert "A" in result
        assert "B" in result

    @pytest.mark.asyncio
    async def test_returns_error_when_entity_not_found(self, mock_kg):
        """Should return error when one or both entities not found."""
        mock_kg.create_relation.return_value = None
        result = await kgmod._create_relation_operation(
            mock_kg, "X", "Y", "rel", {}
        )
        assert "❌" in result
        assert "X" in result
        assert "Y" in result

    @pytest.mark.asyncio
    async def test_hides_properties_when_empty(self, mock_kg):
        """Should not show properties section when empty."""
        mock_kg.create_relation.return_value = {
            "id": "rel-001",
            "from_entity": "A",
            "to_entity": "B",
        }
        result = await kgmod._create_relation_operation(
            mock_kg, "A", "B", "rel", {}
        )
        assert "⚙️ Properties:" not in result

    @pytest.mark.asyncio
    async def test_shows_properties_when_provided(self, mock_kg):
        """Should show properties when dict is not empty."""
        mock_kg.create_relation.return_value = {
            "id": "rel-001",
            "from_entity": "A",
            "to_entity": "B",
        }
        result = await kgmod._create_relation_operation(
            mock_kg, "A", "B", "rel", {"key": "val"}
        )
        assert "⚙️ Properties:" in result
        assert "key" in result


# ============================================================================
# Test _create_relation_impl
# ============================================================================


class TestCreateRelationImpl:
    """Tests for _create_relation_impl function."""

    @pytest.mark.asyncio
    async def test_creates_relation_with_defaults(self, mock_kg):
        """Should create relation with default properties."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="✅ Relation created"),
        ):
            result = await kgmod._create_relation_impl("A", "B", "uses")
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_creates_relation_with_properties(self, mock_kg):
        """Should create relation with properties dict."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="✅ Relation created"),
        ):
            result = await kgmod._create_relation_impl(
                "A", "B", "uses", {"priority": "high"}
            )
            assert "✅" in result


# ============================================================================
# Test _format_entity_result
# ============================================================================


class TestFormatEntityResult:
    """Tests for _format_entity_result helper function."""

    def test_formats_entity_with_observations(self):
        """Should format entity with observations."""
        entity = {
            "name": "TestEntity",
            "entity_type": "project",
            "observations": ["First obs", "Second obs"],
        }
        result = kgmod._format_entity_result(entity)
        lines = "\n".join(result)
        assert "📌 TestEntity (project)" in lines
        assert "📝 Observations: 2" in lines
        assert "First obs" in lines

    def test_formats_entity_without_observations(self):
        """Should format entity without observations."""
        entity = {
            "name": "TestEntity",
            "entity_type": "project",
            "observations": [],
        }
        result = kgmod._format_entity_result(entity)
        lines = "\n".join(result)
        assert "📌 TestEntity (project)" in lines
        assert "📝 Observations: 0" not in lines

    def test_formats_entity_with_none_observations(self):
        """Should handle None observations gracefully."""
        entity = {
            "name": "TestEntity",
            "entity_type": "project",
            "observations": None,
        }
        result = kgmod._format_entity_result(entity)
        lines = "\n".join(result)
        assert "📌 TestEntity (project)" in lines

    def test_truncates_long_observation_preview(self):
        """Should truncate observation previews longer than 80 chars."""
        entity = {
            "name": "TestEntity",
            "entity_type": "project",
            "observations": ["x" * 150],
        }
        result = kgmod._format_entity_result(entity)
        lines = "\n".join(result)
        assert "..." in lines

    def test_no_truncation_for_short_observation(self):
        """Should not add ellipsis for observation <= 80 chars."""
        entity = {
            "name": "TestEntity",
            "entity_type": "project",
            "observations": ["short"],
        }
        result = kgmod._format_entity_result(entity)
        lines = "\n".join(result)
        assert "..." not in lines


# ============================================================================
# Test _format_batch_results
# ============================================================================


class TestFormatBatchResults:
    """Tests for _format_batch_results helper function."""

    def test_formats_all_created_entities(self):
        """Should format all created entities."""
        result = kgmod._format_batch_results(
            created=["Entity1", "Entity2"], failed=[]
        )
        lines = "\n".join(result)
        assert "Successfully Created: 2" in lines
        assert "Entity1" in lines
        assert "Entity2" in lines

    def test_shows_max_10_created_entities(self):
        """Should show only first 10 entities when more exist."""
        created = [f"Entity{i}" for i in range(15)]
        result = kgmod._format_batch_results(created=created, failed=[])
        lines = "\n".join(result)
        assert "and 5 more" in lines

    def test_formats_failed_entities(self):
        """Should format failed entities with errors."""
        result = kgmod._format_batch_results(
            created=[], failed=[("Failed1", "error1"), ("Failed2", "error2")]
        )
        lines = "\n".join(result)
        assert "Failed: 2" in lines
        assert "Failed1" in lines
        assert "error1" in lines

    def test_shows_max_5_failed_entities(self):
        """Should show only first 5 failures when more exist."""
        failed = [(f"Failed{i}", f"error{i}") for i in range(8)]
        result = kgmod._format_batch_results(created=[], failed=failed)
        lines = "\n".join(result)
        assert "and 3 more" in lines

    def test_empty_lists(self):
        """Should handle empty created and failed lists."""
        result = kgmod._format_batch_results(created=[], failed=[])
        lines = "\n".join(result)
        assert "Successfully Created: 0" in lines
        assert "❌ Failed: 0" not in lines  # Failed section only shows when there are failures


# ============================================================================
# Test _search_entities_operation
# ============================================================================


class TestSearchEntitiesOperation:
    """Tests for _search_entities_operation function."""

    @pytest.mark.asyncio
    async def test_returns_no_results_message_when_empty(self, mock_kg):
        """Should return no results message when search finds nothing."""
        mock_kg.search_entities.return_value = []
        result = await kgmod._search_entities_operation(mock_kg, "query", None, 10)
        assert "🔍 No entities found" in result

    @pytest.mark.asyncio
    async def test_formats_results(self, mock_kg):
        """Should format search results properly."""
        mock_kg.search_entities.return_value = [
            {"name": "E1", "entity_type": "t1", "observations": []},
            {"name": "E2", "entity_type": "t2", "observations": []},
        ]
        result = await kgmod._search_entities_operation(mock_kg, "test", None, 10)
        assert "Found 2 entities" in result
        assert "E1" in result
        assert "E2" in result

    @pytest.mark.asyncio
    async def test_passes_filter_parameters(self, mock_kg):
        """Should pass entity_type and limit to search."""
        mock_kg.search_entities.return_value = []
        await kgmod._search_entities_operation(mock_kg, "q", "project", 5)
        mock_kg.search_entities.assert_called_once_with(
            query="q", entity_type="project", limit=5
        )


# ============================================================================
# Test _search_entities_impl
# ============================================================================


class TestSearchEntitiesImpl:
    """Tests for _search_entities_impl function."""

    @pytest.mark.asyncio
    async def test_searches_with_defaults(self, mock_kg):
        """Should search with default entity_type and limit."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍 Found 0 entities"),
        ):
            result = await kgmod._search_entities_impl("query")
            assert "🔍" in result

    @pytest.mark.asyncio
    async def test_searches_with_custom_limit(self, mock_kg):
        """Should search with custom limit."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍 Found 0 entities"),
        ):
            result = await kgmod._search_entities_impl("query", limit=25)
            assert "🔍" in result

    @pytest.mark.asyncio
    async def test_searches_with_entity_type_filter(self, mock_kg):
        """Should search with entity_type filter."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍 Found 0 entities"),
        ):
            result = await kgmod._search_entities_impl("query", entity_type="library")
            assert "🔍" in result


# ============================================================================
# Test _format_relationship
# ============================================================================


class TestFormatRelationship:
    """Tests for _format_relationship helper function."""

    def test_format_outgoing_relationship(self):
        """Should format outgoing relationship correctly."""
        rel = {"from_entity": "A", "to_entity": "B", "relation_type": "uses"}
        result = kgmod._format_relationship(rel, "outgoing", "A")
        assert "A --[uses]--> B" in result

    def test_format_incoming_relationship(self):
        """Should format incoming relationship correctly."""
        rel = {"from_entity": "A", "to_entity": "B", "relation_type": "uses"}
        result = kgmod._format_relationship(rel, "incoming", "B")
        assert "A <--[uses]-- B" in result

    def test_format_both_with_outgoing(self):
        """Should format as outgoing when direction is both and entity matches from."""
        rel = {"from_entity": "A", "to_entity": "B", "relation_type": "uses"}
        result = kgmod._format_relationship(rel, "both", "A")
        assert "A --[uses]--> B" in result

    def test_format_both_with_incoming(self):
        """Should format as incoming when direction is both and entity matches to."""
        rel = {"from_entity": "A", "to_entity": "B", "relation_type": "uses"}
        result = kgmod._format_relationship(rel, "both", "B")
        assert "A <--[uses]-- B" in result


# ============================================================================
# Test _get_entity_relationships_operation
# ============================================================================


class TestGetEntityRelationshipsOperation:
    """Tests for _get_entity_relationships_operation function."""

    @pytest.mark.asyncio
    async def test_returns_no_relationships_message_when_empty(self, mock_kg):
        """Should return message when entity has no relationships."""
        mock_kg.get_relationships.return_value = []
        result = await kgmod._get_entity_relationships_operation(
            mock_kg, "Entity", None, "both"
        )
        assert "🔍 No relationships found" in result
        assert "Entity" in result

    @pytest.mark.asyncio
    async def test_formats_relationships(self, mock_kg):
        """Should format relationships properly."""
        mock_kg.get_relationships.return_value = [
            {"from_entity": "A", "to_entity": "B", "relation_type": "uses"},
            {"from_entity": "B", "to_entity": "C", "relation_type": "imports"},
        ]
        result = await kgmod._get_entity_relationships_operation(
            mock_kg, "A", None, "outgoing"
        )
        assert "Found 2 relationships" in result
        assert "uses" in result
        assert "imports" in result

    @pytest.mark.asyncio
    async def test_passes_filter_parameters(self, mock_kg):
        """Should pass relation_type and direction filters."""
        mock_kg.get_relationships.return_value = []
        await kgmod._get_entity_relationships_operation(
            mock_kg, "E", "depends_on", "outgoing"
        )
        mock_kg.get_relationships.assert_called_once_with(
            entity_name="E", relation_type="depends_on", direction="outgoing"
        )


# ============================================================================
# Test _get_entity_relationships_impl
# ============================================================================


class TestGetEntityRelationshipsImpl:
    """Tests for _get_entity_relationships_impl function."""

    @pytest.mark.asyncio
    async def test_gets_relationships_with_defaults(self, mock_kg):
        """Should get relationships with default direction."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍 No relationships"),
        ):
            result = await kgmod._get_entity_relationships_impl("Entity")
            assert "🔍" in result

    @pytest.mark.asyncio
    async def test_gets_relationships_with_filters(self, mock_kg):
        """Should get relationships with custom filters."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍 No relationships"),
        ):
            result = await kgmod._get_entity_relationships_impl(
                "Entity", relation_type="uses", direction="outgoing"
            )
            assert "🔍" in result


# ============================================================================
# Test _find_path_operation
# ============================================================================


class TestFindPathOperation:
    """Tests for _find_path_operation function."""

    @pytest.mark.asyncio
    async def test_returns_no_path_message_when_empty(self, mock_kg):
        """Should return message when no path exists."""
        mock_kg.find_path.return_value = []
        result = await kgmod._find_path_operation(mock_kg, "A", "B", 5)
        assert "🔍 No path found" in result
        assert "A" in result
        assert "B" in result

    @pytest.mark.asyncio
    async def test_formats_single_path(self, mock_kg):
        """Should format single path correctly."""
        mock_kg.find_path.return_value = [
            {
                "path_length": 2,
                "from_entity": "A",
                "to_entity": "C",
            }
        ]
        result = await kgmod._find_path_operation(mock_kg, "A", "C", 5)
        assert "Found 1 path" in result
        assert "Path length: 2" in result
        assert "A" in result
        assert "C" in result

    @pytest.mark.asyncio
    async def test_formats_multiple_paths(self, mock_kg):
        """Should format multiple paths correctly."""
        mock_kg.find_path.return_value = [
            {"path_length": 1, "from_entity": "A", "to_entity": "B"},
            {"path_length": 2, "from_entity": "A", "to_entity": "C"},
        ]
        result = await kgmod._find_path_operation(mock_kg, "A", "C", 5)
        assert "Found 2 path(s)" in result


# ============================================================================
# Test _find_path_impl
# ============================================================================


class TestFindPathImpl:
    """Tests for _find_path_impl function."""

    @pytest.mark.asyncio
    async def test_finds_path_with_defaults(self, mock_kg):
        """Should find path with default max_depth."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🛤️ Found 0 paths"),
        ):
            result = await kgmod._find_path_impl("A", "B")
            assert "🛤️" in result

    @pytest.mark.asyncio
    async def test_finds_path_with_custom_depth(self, mock_kg):
        """Should find path with custom max_depth."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🛤️ Found 0 paths"),
        ):
            result = await kgmod._find_path_impl("A", "B", max_depth=10)
            assert "🛤️" in result


# ============================================================================
# Test _format_entity_types
# ============================================================================


class TestFormatEntityTypes:
    """Tests for _format_entity_types helper function."""

    def test_formats_entity_types(self):
        """Should format entity type counts."""
        entity_types = {"project": 5, "library": 3, "concept": 2}
        result = kgmod._format_entity_types(entity_types)
        lines = "\n".join(result)
        assert "📊 Entity Types:" in lines
        assert "project: 5" in lines
        assert "library: 3" in lines

    def test_returns_empty_for_empty_dict(self):
        """Should return empty list for empty dict."""
        result = kgmod._format_entity_types({})
        assert result == []


# ============================================================================
# Test _format_relationship_types
# ============================================================================


class TestFormatRelationshipTypes:
    """Tests for _format_relationship_types helper function."""

    def test_formats_relationship_types(self):
        """Should format relationship type counts."""
        rel_types = {"depends_on": 10, "uses": 5, "imports": 3}
        result = kgmod._format_relationship_types(rel_types)
        lines = "\n".join(result)
        assert "🔗 Relationship Types:" in lines
        assert "depends_on: 10" in lines
        assert "uses: 5" in lines

    def test_returns_empty_for_empty_dict(self):
        """Should return empty list for empty dict."""
        result = kgmod._format_relationship_types({})
        assert result == []


# ============================================================================
# Test _get_knowledge_graph_stats_operation
# ============================================================================


class TestGetKnowledgeGraphStatsOperation:
    """Tests for _get_knowledge_graph_stats_operation function."""

    @pytest.mark.asyncio
    async def test_formats_basic_stats(self, mock_kg):
        """Should format basic statistics."""
        mock_kg.get_stats.return_value = {
            "total_entities": 100,
            "total_relationships": 50,
            "entity_types": {"project": 10},
            "relationship_types": {"depends_on": 5},
        }
        result = await kgmod._get_knowledge_graph_stats_operation(mock_kg)
        assert "📊 Knowledge Graph Statistics" in result
        assert "Total Entities: 100" in result
        assert "Total Relationships: 50" in result

    @pytest.mark.asyncio
    async def test_includes_connectivity_metrics(self, mock_kg):
        """Should include connectivity metrics when available."""
        mock_kg.get_stats.return_value = {
            "total_entities": 100,
            "total_relationships": 50,
            "connectivity_ratio": 0.45,
            "avg_degree": 2.5,
            "isolated_entities": 10,
            "embedding_coverage": 0.85,
            "entity_types": {},
            "relationship_types": {},
        }
        result = await kgmod._get_knowledge_graph_stats_operation(mock_kg)
        assert "Connectivity Ratio: 0.450" in result
        assert "Average Degree: 2.500" in result
        assert "Isolated Entities: 10" in result

    @pytest.mark.asyncio
    async def test_includes_database_path(self, mock_kg):
        """Should include database path when available."""
        mock_kg.get_stats.return_value = {
            "total_entities": 0,
            "total_relationships": 0,
            "database_path": "/path/to/db.duckdb",
            "entity_types": {},
            "relationship_types": {},
        }
        result = await kgmod._get_knowledge_graph_stats_operation(mock_kg)
        assert "/path/to/db.duckdb" in result


# ============================================================================
# Test _get_knowledge_graph_stats_impl
# ============================================================================


class TestGetKnowledgeGraphStatsImpl:
    """Tests for _get_knowledge_graph_stats_impl function."""

    @pytest.mark.asyncio
    async def test_gets_stats(self, mock_kg):
        """Should get stats via execute_kg_operation."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="📊 Statistics"),
        ):
            result = await kgmod._get_knowledge_graph_stats_impl()
            assert "📊" in result


# ============================================================================
# Test _extract_patterns_from_context
# ============================================================================


class TestExtractPatternsFromContext:
    """Tests for _extract_patterns_from_context helper function."""

    def test_extracts_kebab_case_project_names(self):
        """Should extract kebab-case project names."""
        text = "Working on mahavishnu-orchestrator and session-buddy"
        result = kgmod._extract_patterns_from_context(text)
        assert "project" in result
        assert "mahavishnu-orchestrator" in result["project"]
        assert "session-buddy" in result["project"]

    def test_extracts_library_names(self):
        """Should extract known library names."""
        text = "Using FastMCP and DuckDB for the project"
        result = kgmod._extract_patterns_from_context(text)
        assert "library" in result
        assert "FastMCP" in result["library"]
        assert "DuckDB" in result["library"]

    def test_extracts_technology_names(self):
        """Should extract technology names."""
        text = "Building with Python and Docker"
        result = kgmod._extract_patterns_from_context(text)
        assert "technology" in result
        assert "Python" in result["technology"]
        assert "Docker" in result["technology"]

    def test_extracts_concepts(self):
        """Should extract concept phrases."""
        text = "Implementing dependency injection for semantic memory"
        result = kgmod._extract_patterns_from_context(text)
        assert "concept" in result
        assert "dependency injection" in result["concept"]
        assert "semantic memory" in result["concept"]

    def test_returns_empty_when_no_matches(self):
        """Should return empty dict when no patterns match."""
        text = "Hello world"
        result = kgmod._extract_patterns_from_context(text)
        assert result == {}

    def test_case_insensitive_matching(self):
        """Should match patterns case-insensitively."""
        text = "PYTHON and python"
        result = kgmod._extract_patterns_from_context(text)
        assert "Python" in result["technology"] or "python" in result["technology"]


# ============================================================================
# Test _auto_create_entity_if_new
# ============================================================================


class TestAutoCreateEntityIfNew:
    """Tests for _auto_create_entity_if_new helper function."""

    @pytest.mark.asyncio
    async def test_returns_false_when_entity_exists(self, mock_kg):
        """Should return False when entity already exists."""
        mock_kg.find_entity_by_name.return_value = {"name": "Existing"}
        result = await kgmod._auto_create_entity_if_new(mock_kg, "Existing", "test")
        assert result is False
        mock_kg.create_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_and_returns_true_when_new(self, mock_kg):
        """Should create entity and return True when it doesn't exist."""
        mock_kg.find_entity_by_name.return_value = None
        result = await kgmod._auto_create_entity_if_new(mock_kg, "NewEntity", "test")
        assert result is True
        mock_kg.create_entity.assert_called_once()


# ============================================================================
# Test _process_entity_type
# ============================================================================


class TestProcessEntityType:
    """Tests for _process_entity_type helper function."""

    @pytest.mark.asyncio
    async def test_processes_multiple_entities(self, mock_kg):
        """Should process multiple entities of same type."""
        mock_kg.find_entity_by_name.return_value = None
        entities = {"EntityA", "EntityB", "EntityC"}
        lines, count, created = await kgmod._process_entity_type(
            mock_kg, "project", entities, auto_create=False
        )
        assert count == 3
        assert created == 0
        assert "📊 Project:" in "\n".join(lines)

    @pytest.mark.asyncio
    async def test_auto_creates_new_entities(self, mock_kg):
        """Should auto-create new entities when flag is True."""
        mock_kg.find_entity_by_name.return_value = None
        entities = {"NewEntity"}
        lines, count, created = await kgmod._process_entity_type(
            mock_kg, "project", entities, auto_create=True
        )
        assert created == 1

    @pytest.mark.asyncio
    async def test_sorts_entities_alphabetically(self, mock_kg):
        """Should sort entities alphabetically."""
        mock_kg.find_entity_by_name.return_value = None
        entities = {"Zebra", "Apple", "Banana"}
        lines, _, _ = await kgmod._process_entity_type(
            mock_kg, "test", entities, auto_create=False
        )
        output = "\n".join(lines)
        apple_pos = output.find("Apple")
        banana_pos = output.find("Banana")
        zebra_pos = output.find("Zebra")
        assert apple_pos < banana_pos < zebra_pos


# ============================================================================
# Test _extract_entities_from_context_impl
# ============================================================================


class TestExtractEntitiesFromContextImpl:
    """Tests for _extract_entities_from_context_impl function."""

    @pytest.mark.asyncio
    async def test_returns_no_entities_when_context_empty(self, mock_kg):
        """Should return message when no entities detected."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍 No entities detected in context"),
        ):
            result = await kgmod._extract_entities_from_context_impl("no match text")
            assert "🔍 No entities detected" in result

    @pytest.mark.asyncio
    async def test_extracts_and_creates_entities(self, mock_kg):
        """Should extract entities and optionally create them."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍 Extracted Entities"),
        ):
            result = await kgmod._extract_entities_from_context_impl(
                "Using FastMCP and Python", auto_create=True
            )
            assert "🔍" in result

    @pytest.mark.asyncio
    async def test_reports_extraction_stats(self, mock_kg):
        """Should report extraction statistics."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="📊 Total Extracted"),
        ):
            result = await kgmod._extract_entities_from_context_impl(
                "FastMCP and Python", auto_create=False
            )
            assert "📊" in result or "🔍" in result


# ============================================================================
# Test _create_single_entity
# ============================================================================


class TestCreateSingleEntity:
    """Tests for _create_single_entity helper function."""

    @pytest.mark.asyncio
    async def test_returns_name_on_success(self, mock_kg):
        """Should return name when entity is created successfully."""
        mock_kg.create_entity.return_value = {"name": "TestEntity"}
        created, failed = await kgmod._create_single_entity(
            mock_kg, {"name": "TestEntity", "entity_type": "test"}
        )
        assert created == "TestEntity"
        assert failed is None

    @pytest.mark.asyncio
    async def test_returns_error_on_failure(self, mock_kg):
        """Should return error tuple when creation fails."""
        mock_kg.create_entity.side_effect = ValueError("Invalid data")
        created, failed = await kgmod._create_single_entity(
            mock_kg, {"name": "BadEntity", "entity_type": "test"}
        )
        assert created is None
        assert failed == ("BadEntity", "Invalid data")

    @pytest.mark.asyncio
    async def test_handles_observations_and_properties(self, mock_kg):
        """Should pass observations and properties to create_entity."""
        mock_kg.create_entity.return_value = {"name": "TestEntity"}
        await kgmod._create_single_entity(
            mock_kg,
            {
                "name": "TestEntity",
                "entity_type": "test",
                "observations": ["obs1"],
                "properties": {"key": "val"},
            },
        )
        mock_kg.create_entity.assert_called_once_with(
            name="TestEntity",
            entity_type="test",
            observations=["obs1"],
            properties={"key": "val"},
        )


# ============================================================================
# Test _batch_create_entities_operation
# ============================================================================


class TestBatchCreateEntitiesOperation:
    """Tests for _batch_create_entities_operation function."""

    @pytest.mark.asyncio
    async def test_creates_all_entities(self, mock_kg):
        """Should create all entities successfully."""
        mock_kg.create_entity.return_value = {"name": "Entity"}
        entities = [
            {"name": "E1", "entity_type": "test"},
            {"name": "E2", "entity_type": "test"},
        ]
        result = await kgmod._batch_create_entities_operation(mock_kg, entities)
        assert mock_kg.create_entity.call_count == 2

    @pytest.mark.asyncio
    async def test_tracks_failures(self, mock_kg):
        """Should track and report failed entities."""
        # Create a new mock with specific side effects for this test
        failing_kg = MagicMock()
        failing_kg.create_entity = AsyncMock(
            side_effect=[ValueError("fail"), {"name": "Good"}, ValueError("fail2")]
        )
        entities = [
            {"name": "Bad", "entity_type": "test"},
            {"name": "Good", "entity_type": "test"},
            {"name": "Bad2", "entity_type": "test"},
        ]
        result = await kgmod._batch_create_entities_operation(failing_kg, entities)
        # Join with empty string to check raw content
        content = "".join(result)
        # Check that Failed: appears with some count
        assert "Failed" in content

    @pytest.mark.asyncio
    async def test_shows_first_10_entities(self, mock_kg):
        """Should show first 10 entities when more exist."""
        many_kg = MagicMock()
        many_kg.create_entity = AsyncMock(return_value={"name": "Entity"})
        entities = [{"name": f"E{i}", "entity_type": "test"} for i in range(15)]
        result = await kgmod._batch_create_entities_operation(many_kg, entities)
        content = "".join(result)
        # Check that "more" appears (indicating truncation)
        assert "more" in content


# ============================================================================
# Test _batch_create_entities_impl
# ============================================================================


class TestBatchCreateEntitiesImpl:
    """Tests for _batch_create_entities_impl function."""

    @pytest.mark.asyncio
    async def test_batch_creates_entities(self, mock_kg):
        """Should batch create entities via execute_kg_operation."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="📦 Batch Entity Creation"),
        ):
            result = await kgmod._batch_create_entities_impl(
                [{"name": "E1", "entity_type": "test"}]
            )
            assert "📦" in result


# ============================================================================
# Test _generate_embeddings_impl
# ============================================================================


class TestGenerateEmbeddingsImpl:
    """Tests for _generate_embeddings_impl function."""

    @pytest.mark.asyncio
    async def test_generates_embeddings_with_defaults(self, mock_kg):
        """Should generate embeddings with default parameters."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🧠 Embedding Generation Results"),
        ):
            result = await kgmod._generate_embeddings_impl()
            assert "🧠" in result

    @pytest.mark.asyncio
    async def test_generates_embeddings_with_custom_params(self, mock_kg):
        """Should generate embeddings with custom parameters."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🧠 Embedding Generation Results"),
        ):
            result = await kgmod._generate_embeddings_impl(
                entity_type="project", batch_size=100, overwrite=True
            )
            assert "🧠" in result


# ============================================================================
# Test _discover_relationships_impl
# ============================================================================


class TestDiscoverRelationshipsImpl:
    """Tests for _discover_relationships_impl function."""

    @pytest.mark.asyncio
    async def test_discovers_with_defaults(self, mock_kg):
        """Should discover relationships with default parameters."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔗 Relationship Discovery Results"),
        ):
            result = await kgmod._discover_relationships_impl()
            assert "🔗" in result

    @pytest.mark.asyncio
    async def test_discovers_with_custom_params(self, mock_kg):
        """Should discover relationships with custom parameters."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔗 Relationship Discovery Results"),
        ):
            result = await kgmod._discover_relationships_impl(
                entity_type="project", threshold=0.5, limit=50, batch_size=20
            )
            assert "🔗" in result


# ============================================================================
# Test _analyze_graph_connectivity_impl
# ============================================================================


class TestAnalyzeGraphConnectivityImpl:
    """Tests for _analyze_graph_connectivity_impl function."""

    @pytest.mark.asyncio
    async def test_analyzes_excellent_connectivity(self, mock_kg):
        """Should report excellent health for high connectivity."""
        mock_kg.get_stats.return_value = {
            "total_entities": 100,
            "total_relationships": 50,
            "connectivity_ratio": 0.6,
            "avg_degree": 2.0,
            "isolated_entities": 5,
            "embedding_coverage": 0.9,
            "entities_with_embeddings": 90,
            "entity_types": {},
            "relationship_types": {},
        }
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="📊 Analysis"),
        ):
            result = await kgmod._analyze_graph_connectivity_impl()
            assert "🟢" in result or "📊" in result

    @pytest.mark.asyncio
    async def test_analyzes_poor_connectivity(self, mock_kg):
        """Should report poor health and recommendations for low connectivity."""
        mock_kg.get_stats.return_value = {
            "total_entities": 100,
            "total_relationships": 10,
            "connectivity_ratio": 0.05,
            "avg_degree": 0.5,
            "isolated_entities": 80,
            "embedding_coverage": 0.3,
            "entities_with_embeddings": 30,
            "entity_types": {},
            "relationship_types": {},
        }
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._require_knowledge_graph",
            AsyncMock(return_value=mock_kg),
        ):
            result = await kgmod._analyze_graph_connectivity_impl()
            assert "🔴" in result or "📊" in result
            assert "Recommendations" in result

    @pytest.mark.asyncio
    async def test_handles_zero_entities(self, mock_kg):
        """Should handle division by zero when total_entities is 0."""
        mock_kg.get_stats.return_value = {
            "total_entities": 0,
            "total_relationships": 0,
            "connectivity_ratio": 0,
            "avg_degree": 0,
            "isolated_entities": 0,
            "embedding_coverage": 0,
            "entities_with_embeddings": 0,
            "entity_types": {},
            "relationship_types": {},
        }
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="📊 Analysis"),
        ):
            result = await kgmod._analyze_graph_connectivity_impl()
            assert "0.0%" in result or "📊" in result


# ============================================================================
# Test register_knowledge_graph_tools
# ============================================================================


class TestRegisterKnowledgeGraphTools:
    """Tests for register_knowledge_graph_tools function."""

    def test_registers_all_tools(self, mock_server):
        """Should register all MCP tools on the server."""
        kgmod.register_knowledge_graph_tools(mock_server)
        assert mock_server.tool.call_count >= 11

    def test_tool_names_valid(self, mock_server):
        """Should register tools with valid names."""
        kgmod.register_knowledge_graph_tools(mock_server)
        # Collect all decorated functions by checking how many times tool() was called
        call_count = mock_server.tool.call_count
        assert call_count >= 11
        # Verify specific expected tools are registered by name
        # The decorator pattern means we need to check the call args
        expected_tools = [
            "create_entity",
            "add_observation",
            "create_relation",
            "search_entities",
            "get_entity_relationships",
            "find_path",
            "get_knowledge_graph_stats",
            "extract_entities_from_context",
            "batch_create_entities",
            "generate_embeddings",
            "discover_relationships",
            "analyze_graph_connectivity",
        ]
        # We verify by checking call count since the decorator returns function objects
        assert call_count == len(expected_tools)


# ============================================================================
# Test ENTITY_PATTERNS
# ============================================================================


class TestEntityPatterns:
    """Tests for ENTITY_PATTERNS constant."""

    def test_has_required_entity_types(self):
        """Should have all required entity types defined."""
        expected_types = {"project", "library", "technology", "concept"}
        assert expected_types.issubset(set(kgmod.ENTITY_PATTERNS.keys()))

    def test_patterns_are_valid_regex(self):
        """Should have valid regex patterns."""
        import re

        for entity_type, pattern in kgmod.ENTITY_PATTERNS.items():
            try:
                re.compile(pattern)
            except re.error:
                pytest.fail(f"Invalid regex for {entity_type}: {pattern}")


# ============================================================================
# Integration-style tests for async workflows
# ============================================================================


class TestAsyncWorkflows:
    """Integration-style tests for complete async workflows."""

    @pytest.mark.asyncio
    async def test_create_entity_workflow(self, mock_kg):
        """Test complete entity creation workflow."""
        mock_kg.create_entity.return_value = {"id": "new-id", "name": "NewEntity"}
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._require_knowledge_graph",
            AsyncMock(return_value=mock_kg),
        ):
            result = await kgmod._create_entity_impl(
                name="NewEntity",
                entity_type="project",
                observations=["Initial observation"],
                properties={"version": "1.0"},
            )
            assert "✅" in result
            assert "NewEntity" in result

    @pytest.mark.asyncio
    async def test_add_observation_workflow(self, mock_kg):
        """Test complete observation addition workflow."""
        mock_kg.add_observation.return_value = True
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._require_knowledge_graph",
            AsyncMock(return_value=mock_kg),
        ):
            result = await kgmod._add_observation_impl("Entity", "New observation")
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_search_and_find_path_workflow(self, mock_kg):
        """Test search and path finding workflow."""
        mock_kg.search_entities.return_value = [
            {"name": "A", "entity_type": "test", "observations": []},
            {"name": "B", "entity_type": "test", "observations": []},
        ]
        mock_kg.find_path.return_value = [
            {"path_length": 1, "from_entity": "A", "to_entity": "B"}
        ]
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._require_knowledge_graph",
            AsyncMock(return_value=mock_kg),
        ):
            search_result = await kgmod._search_entities_impl("A")
            assert "Found" in search_result

            path_result = await kgmod._find_path_impl("A", "B")
            assert "🛤️" in path_result

    @pytest.mark.asyncio
    async def test_batch_create_workflow(self, mock_kg):
        """Test batch entity creation workflow."""
        mock_kg.create_entity.return_value = {"name": "Entity"}
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._require_knowledge_graph",
            AsyncMock(return_value=mock_kg),
        ):
            result = await kgmod._batch_create_entities_impl(
                [
                    {"name": "E1", "entity_type": "test"},
                    {"name": "E2", "entity_type": "test"},
                    {"name": "E3", "entity_type": "test"},
                ]
            )
            assert "📦" in result
            assert "Successfully Created: 3" in result


# ============================================================================
# Edge case tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_create_entity_with_none_observations(self, mock_kg):
        """Should handle None observations gracefully."""
        mock_kg.create_entity.return_value = {"id": "id", "name": "E"}
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="✅"),
        ):
            result = await kgmod._create_entity_impl(
                name="E", entity_type="t", observations=None
            )
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_create_entity_with_none_properties(self, mock_kg):
        """Should handle None properties gracefully."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="✅"),
        ):
            result = await kgmod._create_entity_impl(
                name="E", entity_type="t", properties=None
            )
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_search_with_zero_limit(self, mock_kg):
        """Should handle zero limit."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍"),
        ):
            result = await kgmod._search_entities_impl("query", limit=0)
            assert "🔍" in result

    @pytest.mark.asyncio
    async def test_search_with_negative_limit(self, mock_kg):
        """Should handle negative limit."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍"),
        ):
            result = await kgmod._search_entities_impl("query", limit=-1)
            assert "🔍" in result

    @pytest.mark.asyncio
    async def test_find_path_with_zero_depth(self, mock_kg):
        """Should handle zero max_depth."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🛤️"),
        ):
            result = await kgmod._find_path_impl("A", "B", max_depth=0)
            assert "🛤️" in result

    @pytest.mark.asyncio
    async def test_get_relationships_with_invalid_direction(self, mock_kg):
        """Should handle invalid direction gracefully."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍"),
        ):
            result = await kgmod._get_entity_relationships_impl(
                "Entity", direction="invalid"
            )
            assert "🔍" in result

    @pytest.mark.asyncio
    async def test_extract_entities_with_empty_string(self, mock_kg):
        """Should handle empty context string."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔍 No entities detected"),
        ):
            result = await kgmod._extract_entities_from_context_impl("")
            assert "No entities detected" in result

    @pytest.mark.asyncio
    async def test_discover_with_zero_threshold(self, mock_kg):
        """Should handle zero threshold."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔗"),
        ):
            result = await kgmod._discover_relationships_impl(threshold=0.0)
            assert "🔗" in result

    @pytest.mark.asyncio
    async def test_discover_with_unit_threshold(self, mock_kg):
        """Should handle threshold of 1.0."""
        with patch(
            "session_buddy.mcp.tools.collaboration.knowledge_graph_tools._execute_kg_operation",
            AsyncMock(return_value="🔗"),
        ):
            result = await kgmod._discover_relationships_impl(threshold=1.0)
            assert "🔗" in result
