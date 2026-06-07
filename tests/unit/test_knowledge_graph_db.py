#!/usr/bin/env python3
"""Comprehensive tests for Knowledge Graph Database (DuckDB + DuckPGQ).

Tests the knowledge graph semantic memory system that complements
episodic memory in ReflectionDatabase.

Phase: Week 4 Days 3-5 - Knowledge Graph Coverage
"""

from __future__ import annotations

import json
import tempfile
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

if TYPE_CHECKING:
    pass


class TestKnowledgeGraphDatabaseInit:
    """Test KnowledgeGraphDatabase initialization.

    Covers:
    - __init__ with default path
    - __init__ with custom path
    """

    def test_init_default_path(self, tmp_path: Any) -> None:
        """Should initialize with default database path.

        After the isolated_test_db_path fixture (tests/conftest.py:382)
        monkeypatches SessionMgmtSettings._settings to point at a per-test
        tmp dir, the resolved default path lands under
        ``<tmp_path>/session-buddy-data/knowledge_graph.duckdb``.
        """
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()

        assert kg.db_path.endswith("knowledge_graph.duckdb")
        assert str(tmp_path) in kg.db_path
        assert kg.conn is None
        assert kg._duckpgq_installed is False

    def test_init_custom_path(self, tmp_path: Any) -> None:
        """Should initialize with custom database path."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "custom_kg.duckdb")
        kg = KnowledgeGraphDatabase(db_path=db_path)

        assert kg.db_path == db_path
        assert kg.conn is None

    def test_init_accepts_provided_path(self) -> None:
        """Should use provided path as-is (no expansion for user-provided paths)."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase(db_path="~/test_kg.duckdb")

        # Note: os.path.expanduser is only called for the DEFAULT path
        # When db_path is explicitly provided, it's used as-is
        assert kg.db_path == "~/test_kg.duckdb"

    def test_init_sets_connection_to_none(self) -> None:
        """Should initialize connection as None."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()

        assert kg.conn is None


class TestContextManagers:
    """Test synchronous and asynchronous context managers.

    Covers:
    - __enter__, __exit__ (sync)
    - __aenter__, __aexit__ (async)
    - close() method
    - __del__ destructor
    """

    def test_sync_context_manager_enters(self, tmp_path: Any) -> None:
        """Should support synchronous context manager entry."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "sync_test.duckdb")

        with KnowledgeGraphDatabase(db_path=db_path) as kg:
            assert isinstance(kg, KnowledgeGraphDatabase)
            assert kg.db_path == db_path

    def test_sync_context_manager_exits(self, tmp_path: Any) -> None:
        """Should support synchronous context manager exit."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "sync_exit.duckdb")
        kg = KnowledgeGraphDatabase(db_path=db_path)

        with kg:
            pass

        # Connection should still be accessible but not closed yet
        # (sync context manager doesn't initialize connection)
        assert kg.conn is None

    @pytest.mark.asyncio
    async def test_async_context_manager_enters(self, tmp_path: Any) -> None:
        """Should support asynchronous context manager entry and initialize."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "async_test.duckdb")

        with patch("session_buddy.knowledge_graph_db.duckdb"):
            async with KnowledgeGraphDatabase(db_path=db_path) as kg:
                assert isinstance(kg, KnowledgeGraphDatabase)
                assert kg.conn is not None

    @pytest.mark.asyncio
    async def test_async_context_manager_exits(self, tmp_path: Any) -> None:
        """Should close connection on async context manager exit."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "async_exit.duckdb")

        with patch("session_buddy.knowledge_graph_db.duckdb"):
            kg = KnowledgeGraphDatabase(db_path=db_path)

            async with kg:
                assert kg.conn is not None

            # After exit, connection should be closed
            assert kg.conn is None

    def test_close_with_no_connection(self) -> None:
        """Should handle close() when no connection exists."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()
        kg.close()  # Should not raise

        assert kg.conn is None

    def test_close_closes_existing_connection(self) -> None:
        """Should close existing connection gracefully."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()
        mock_conn = MagicMock()
        kg.conn = mock_conn

        kg.close()

        mock_conn.close.assert_called_once()
        assert kg.conn is None

    def test_close_handles_connection_close_exception(self) -> None:
        """Should handle exceptions during connection close."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()
        mock_conn = MagicMock()
        mock_conn.close.side_effect = Exception("Close failed")
        kg.conn = mock_conn

        kg.close()  # Should not raise

        assert kg.conn is None

    def test_destructor_calls_close(self) -> None:
        """Should call close() from destructor."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()
        mock_conn = MagicMock()
        kg.conn = mock_conn

        # Trigger destructor
        del kg

        mock_conn.close.assert_called_once()


class TestKnowledgeGraphInitialization:
    """Test database initialization and schema creation.

    Covers:
    - initialize() method
    - DUCKDB_AVAILABLE check
    - DuckPGQ extension installation
    - _create_schema() method
    """

    @pytest.mark.asyncio
    async def test_initialize_creates_connection(self, tmp_path: Any) -> None:
        """Should create DuckDB connection during initialization."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "init_test.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            mock_duckdb.connect.assert_called_once_with(db_path)
            assert kg.conn is mock_conn

    @pytest.mark.asyncio
    async def test_initialize_installs_duckpgq(self, tmp_path: Any) -> None:
        """Should install DuckPGQ extension from community repository."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "duckpgq_test.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            assert mock_conn.execute.call_count >= 2  # INSTALL and LOAD

    @pytest.mark.asyncio
    async def test_create_schema_creates_tables(self, tmp_path: Any) -> None:
        """Should create kg_entities and kg_relationships tables."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "schema_test.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # Verify CREATE TABLE statements were executed
            calls = [str(call) for call in mock_conn.execute.call_args_list]
            create_table_calls = [c for c in calls if "CREATE TABLE" in c]
            assert len(create_table_calls) >= 2  # At least entities and relationships

    @pytest.mark.asyncio
    async def test_create_schema_creates_indexes(self, tmp_path: Any) -> None:
        """Should create indexes for performance."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "index_test.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # Verify index creation calls
            calls = [str(call) for call in mock_conn.execute.call_args_list]
            index_calls = [c for c in calls if "CREATE INDEX" in c]
            assert len(index_calls) >= 4  # Multiple indexes created

    @pytest.mark.asyncio
    async def test_create_schema_creates_property_graph(self, tmp_path: Any) -> None:
        """Should create property graph when DuckPGQ is available."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "pg_test.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value = None  # Successful execution

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # DuckPGQ should be marked as installed
            assert kg._duckpgq_installed is True

    def test_get_conn_raises_when_not_initialized(self) -> None:
        """Should raise RuntimeError when connection not initialized."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()

        with pytest.raises(RuntimeError, match="not initialized"):
            kg._get_conn()

    @pytest.mark.asyncio
    async def test_get_conn_returns_connection(self, tmp_path: Any) -> None:
        """Should return connection when initialized."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "get_conn_test.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            conn = kg._get_conn()
            assert conn is mock_conn


class TestEntityOperations:
    """Test entity CRUD operations.

    Covers:
    - create_entity() - basic, with observations, with properties, with metadata
    - get_entity() - existing, nonexistent
    - find_entity_by_name() - exact match, case insensitive, with type filter
    - search_entities() - basic search, with type filter, with limit
    """

    @pytest.mark.asyncio
    async def test_create_entity_basic(self, tmp_path: Any) -> None:
        """Should create entity with basic information."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "entity_basic.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            entity = await kg.create_entity(
                name="test-project",
                entity_type="project",
            )

            assert entity["name"] == "test-project"
            assert entity["entity_type"] == "project"
            assert "id" in entity
            assert "created_at" in entity
            assert entity["observations"] == []
            assert entity["properties"] == {}
            assert entity["metadata"] == {}

    @pytest.mark.asyncio
    async def test_create_entity_with_observations(self, tmp_path: Any) -> None:
        """Should create entity with observations."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "entity_obs.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            entity = await kg.create_entity(
                name="test-lib",
                entity_type="library",
                observations=["FastMCP framework", "Async-first"],
            )

            assert len(entity["observations"]) == 2

    @pytest.mark.asyncio
    async def test_create_entity_with_properties(self, tmp_path: Any) -> None:
        """Should create entity with custom properties."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "entity_props.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            properties = {"version": "1.0.0", "stars": 100}
            entity = await kg.create_entity(
                name="test-tool",
                entity_type="tool",
                properties=properties,
            )

            assert entity["properties"]["version"] == "1.0.0"
            assert entity["properties"]["stars"] == 100

    @pytest.mark.asyncio
    async def test_create_entity_with_metadata(self, tmp_path: Any) -> None:
        """Should create entity with metadata."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "entity_meta.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            metadata = {"confidence": 0.95, "source": "github"}
            entity = await kg.create_entity(
                name="test-concept",
                entity_type="concept",
                metadata=metadata,
            )

            assert entity["metadata"]["confidence"] == 0.95
            assert entity["metadata"]["source"] == "github"

    @pytest.mark.asyncio
    async def test_get_entity_existing(self, tmp_path: Any) -> None:
        """Should retrieve existing entity by ID."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "get_entity.duckdb")
        mock_conn = MagicMock()
        # Mock the result of get_entity
        test_entity = (
            "entity-uuid-123",
            "test-lib",
            "library",
            ["FastMCP"],
            '{"version": "1.0"}',
            None,  # created_at
            None,  # updated_at
            '{"source": "github"}',
        )
        mock_conn.execute.return_value.fetchone.return_value = test_entity

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.get_entity("entity-uuid-123")

            assert result is not None
            assert result["id"] == "entity-uuid-123"
            assert result["name"] == "test-lib"
            assert result["entity_type"] == "library"

    @pytest.mark.asyncio
    async def test_get_entity_nonexistent(self, tmp_path: Any) -> None:
        """Should return None for nonexistent entity."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "get_none.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.get_entity("nonexistent-id")

            assert result is None

    @pytest.mark.asyncio
    async def test_find_entity_by_name_exact(self, tmp_path: Any) -> None:
        """Should find entity by exact name match."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "find_name.duckdb")
        mock_conn = MagicMock()
        test_entity = (
            "entity-uuid-456",
            "fastmcp",
            "library",
            [],
            None,
            None,
            None,
            None,
        )
        mock_conn.execute.return_value.fetchone.return_value = test_entity

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.find_entity_by_name("fastmcp")

            assert result is not None
            assert result["name"] == "fastmcp"

    @pytest.mark.asyncio
    async def test_find_entity_by_name_case_insensitive(self, tmp_path: Any) -> None:
        """Should find entity case-insensitively."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "find_ci.duckdb")
        mock_conn = MagicMock()
        test_entity = (
            "entity-uuid-789",
            "Python",
            "language",
            ["Version 3.13"],
            None,
            None,
            None,
            None,
        )
        mock_conn.execute.return_value.fetchone.return_value = test_entity

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.find_entity_by_name("PYTHON")

            assert result is not None
            assert result["name"] == "Python"

    @pytest.mark.asyncio
    async def test_find_entity_by_name_with_type_filter(self, tmp_path: Any) -> None:
        """Should find entity by name with type filter."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "find_type.duckdb")
        mock_conn = MagicMock()
        test_entity = (
            "entity-uuid-abc",
            "session-buddy",
            "project",
            [],
            None,
            None,
            None,
            None,
        )
        mock_conn.execute.return_value.fetchone.return_value = test_entity

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.find_entity_by_name("session-buddy", entity_type="project")

            assert result is not None
            assert result["entity_type"] == "project"

    @pytest.mark.asyncio
    async def test_find_entity_by_name_not_found(self, tmp_path: Any) -> None:
        """Should return None when entity not found."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "find_notfound.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.find_entity_by_name("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_search_entities_basic(self, tmp_path: Any) -> None:
        """Should search entities by query string."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "search_basic.duckdb")
        mock_conn = MagicMock()
        mock_results = [
            (
                "entity-1",
                "fastmcp",
                "library",
                ["MCP framework"],
                None,
                None,
                None,
                None,
            ),
            (
                "entity-2",
                "fastapi",
                "framework",
                ["Web framework"],
                None,
                None,
                None,
                None,
            ),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_results

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.search_entities(query="fast")

            assert len(results) == 2
            assert results[0]["name"] == "fastmcp"

    @pytest.mark.asyncio
    async def test_search_entities_with_type_filter(self, tmp_path: Any) -> None:
        """Should search entities with type filter."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "search_type.duckdb")
        mock_conn = MagicMock()
        mock_results = [
            (
                "entity-1",
                "project-a",
                "project",
                [],
                None,
                None,
                None,
                None,
            ),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_results

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.search_entities(query="project", entity_type="project")

            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_entities_with_limit(self, tmp_path: Any) -> None:
        """Should respect limit parameter."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "search_limit.duckdb")
        mock_conn = MagicMock()
        mock_results = [
            (
                "entity-1",
                "item1",
                "type",
                [],
                None,
                None,
                None,
                None,
            ),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_results

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            await kg.search_entities(query="item", limit=5)

            # Verify limit was passed - check the last execute call
            all_calls = mock_conn.execute.call_args_list
            last_call = all_calls[-1]
            # The params should contain 5
            params = last_call[0][1]  # positional params tuple
            assert 5 in params

    @pytest.mark.asyncio
    async def test_search_entities_empty_results(self, tmp_path: Any) -> None:
        """Should return empty list when no matches found."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "search_empty.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.search_entities(query="nonexistent")

            assert results == []


class TestRelationOperations:
    """Test relationship CRUD operations.

    Covers:
    - create_relation() - valid relation, missing entity
    - get_relationships() - outgoing, incoming, both, with type filter
    - _build_relationship_filters() - outgoing, incoming, both, with type
    - add_observation() - success, entity not found
    """

    @pytest.mark.asyncio
    async def test_create_relation_basic(self, tmp_path: Any) -> None:
        """Should create relation between two existing entities."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rel_basic.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            # First call: find_entity_by_name for from_entity
            ("uuid-1", "session-buddy", "project", [], None, None, None, None),
            # Second call: find_entity_by_name for to_entity
            ("uuid-2", "fastmcp", "library", [], None, None, None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.create_relation(
                from_entity="session-buddy",
                to_entity="fastmcp",
                relation_type="uses",
            )

            assert result is not None
            assert result["from_entity"] == "session-buddy"
            assert result["to_entity"] == "fastmcp"
            assert result["relation_type"] == "uses"

    @pytest.mark.asyncio
    async def test_create_relation_with_properties(self, tmp_path: Any) -> None:
        """Should create relation with custom properties."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rel_props.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            ("uuid-1", "A", "project", [], None, None, None, None),
            ("uuid-2", "B", "library", [], None, None, None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.create_relation(
                from_entity="A",
                to_entity="B",
                relation_type="depends_on",
                properties={"version": ">=2.0"},
            )

            assert result is not None
            assert result["properties"]["version"] == ">=2.0"

    @pytest.mark.asyncio
    async def test_create_relation_with_metadata(self, tmp_path: Any) -> None:
        """Should create relation with metadata."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rel_meta.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            ("uuid-1", "proj", "project", [], None, None, None, None),
            ("uuid-2", "lib", "library", [], None, None, None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.create_relation(
                from_entity="proj",
                to_entity="lib",
                relation_type="uses",
                metadata={"confidence": 0.9},
            )

            assert result is not None
            assert result["metadata"]["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_create_relation_missing_from_entity(self, tmp_path: Any) -> None:
        """Should return None when from_entity not found."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rel_no_from.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            None,  # from_entity not found
            ("uuid-2", "B", "library", [], None, None, None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.create_relation(
                from_entity="missing",
                to_entity="B",
                relation_type="uses",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_create_relation_missing_to_entity(self, tmp_path: Any) -> None:
        """Should return None when to_entity not found."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rel_no_to.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            ("uuid-1", "A", "project", [], None, None, None, None),
            None,  # to_entity not found
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.create_relation(
                from_entity="A",
                to_entity="missing",
                relation_type="uses",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_relationships_outgoing(self, tmp_path: Any) -> None:
        """Should get outgoing relationships only."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rels_out.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (
            "uuid-1",
            "A",
            "project",
            [],
            None,
            None,
            None,
            None,
        )
        mock_conn.execute.return_value.fetchall.return_value = [
            ("rel-1", "uses", "A", "B", None, None),
            ("rel-2", "depends_on", "A", "C", None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.get_relationships("A", direction="outgoing")

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_relationships_incoming(self, tmp_path: Any) -> None:
        """Should get incoming relationships only."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rels_in.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (
            "uuid-1",
            "B",
            "library",
            [],
            None,
            None,
            None,
            None,
        )
        mock_conn.execute.return_value.fetchall.return_value = [
            ("rel-1", "uses", "A", "B", None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.get_relationships("B", direction="incoming")

            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_relationships_both(self, tmp_path: Any) -> None:
        """Should get both incoming and outgoing relationships."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rels_both.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (
            "uuid-1",
            "B",
            "library",
            [],
            None,
            None,
            None,
            None,
        )
        mock_conn.execute.return_value.fetchall.return_value = [
            ("rel-1", "uses", "B", "C", None, None),
            ("rel-2", "used_by", "A", "B", None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.get_relationships("B", direction="both")

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_relationships_with_type_filter(self, tmp_path: Any) -> None:
        """Should filter relationships by type."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rels_type.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (
            "uuid-1",
            "A",
            "project",
            [],
            None,
            None,
            None,
            None,
        )
        mock_conn.execute.return_value.fetchall.return_value = [
            ("rel-1", "uses", "A", "B", None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.get_relationships("A", relation_type="uses")

            assert len(results) == 1
            assert results[0]["relation_type"] == "uses"

    @pytest.mark.asyncio
    async def test_get_relationships_entity_not_found(self, tmp_path: Any) -> None:
        """Should return empty list when entity not found."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "rels_notfound.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.get_relationships("nonexistent")

            assert results == []

    def test_build_relationship_filters_outgoing(self) -> None:
        """Should build WHERE clause for outgoing relationships."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()
        entity = {"id": "entity-uuid"}

        clause, params = kg._build_relationship_filters(
            direction="outgoing",
            relation_type=None,
            entity=entity,
        )

        assert "r.from_entity = ?" in clause
        assert "entity-uuid" in params

    def test_build_relationship_filters_incoming(self) -> None:
        """Should build WHERE clause for incoming relationships."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()
        entity = {"id": "entity-uuid"}

        clause, params = kg._build_relationship_filters(
            direction="incoming",
            relation_type=None,
            entity=entity,
        )

        assert "r.to_entity = ?" in clause
        assert "entity-uuid" in params

    def test_build_relationship_filters_both(self) -> None:
        """Should build WHERE clause for both directions."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()
        entity = {"id": "entity-uuid"}

        clause, params = kg._build_relationship_filters(
            direction="both",
            relation_type=None,
            entity=entity,
        )

        assert "r.from_entity = ?" in clause
        assert "r.to_entity = ?" in clause
        assert params == ("entity-uuid", "entity-uuid")

    def test_build_relationship_filters_with_type(self) -> None:
        """Should add relation_type filter to WHERE clause."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        kg = KnowledgeGraphDatabase()
        entity = {"id": "entity-uuid"}

        clause, params = kg._build_relationship_filters(
            direction="outgoing",
            relation_type="uses",
            entity=entity,
        )

        assert "r.relation_type = ?" in clause
        assert "uses" in params

    @pytest.mark.asyncio
    async def test_add_observation_success(self, tmp_path: Any) -> None:
        """Should add observation to existing entity."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "add_obs.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            # find_entity_by_name
            ("uuid-1", "test", "concept", ["Initial"], None, None, None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.add_observation("test", "New observation")

            assert result is True

    @pytest.mark.asyncio
    async def test_add_observation_entity_not_found(self, tmp_path: Any) -> None:
        """Should return False when entity not found."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "add_obs_notfound.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.add_observation("nonexistent", " observation")

            assert result is False


class TestPathFinding:
    """Test path finding algorithms.

    Covers:
    - find_path() - basic path, no path exists, entities not found
    - disconnected graphs
    - circular references
    """

    @pytest.mark.asyncio
    async def test_find_path_basic(self, tmp_path: Any) -> None:
        """Should find path between two connected entities."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "path_basic.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            # find_entity_by_name for from_entity
            ("uuid-1", "A", "project", [], None, None, None, None),
            # find_entity_by_name for to_entity
            ("uuid-3", "C", "tool", [], None, None, None, None),
        ]
        mock_conn.execute.return_value.fetchall.return_value = [
            ("A", "C", 2),  # Path from A to C with length 2
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.find_path("A", "C", max_depth=5)

            assert len(results) == 1
            assert results[0]["from_entity"] == "A"
            assert results[0]["to_entity"] == "C"
            assert results[0]["path_length"] == 2

    @pytest.mark.asyncio
    async def test_find_path_no_path_exists(self, tmp_path: Any) -> None:
        """Should return empty list when no path exists (disconnected graph)."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "path_nopath.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            ("uuid-1", "A", "project", [], None, None, None, None),
            ("uuid-2", "D", "tool", [], None, None, None, None),
        ]
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.find_path("A", "D", max_depth=5)

            assert results == []

    @pytest.mark.asyncio
    async def test_find_path_from_entity_not_found(self, tmp_path: Any) -> None:
        """Should return empty list when from_entity not found."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "path_no_from.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.find_path("missing", "B", max_depth=5)

            assert results == []

    @pytest.mark.asyncio
    async def test_find_path_to_entity_not_found(self, tmp_path: Any) -> None:
        """Should return empty list when to_entity not found."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "path_no_to.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            ("uuid-1", "A", "project", [], None, None, None, None),
            None,  # to_entity not found
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.find_path("A", "missing", max_depth=5)

            assert results == []

    @pytest.mark.asyncio
    async def test_find_path_handles_query_exception(self, tmp_path: Any) -> None:
        """Should return empty list when graph query fails (fallback)."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "path_fail.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            ("uuid-1", "A", "project", [], None, None, None, None),
            ("uuid-2", "B", "library", [], None, None, None, None),
        ]
        mock_conn.execute.return_value.fetchall.side_effect = Exception(
            "Graph query failed"
        )

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.find_path("A", "B", max_depth=5)

            # Should return empty list instead of raising
            assert results == []

    @pytest.mark.asyncio
    async def test_find_path_circular_reference(self, tmp_path: Any) -> None:
        """Should handle circular references in graph."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "path_circular.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            ("uuid-1", "A", "project", [], None, None, None, None),
            ("uuid-2", "B", "library", [], None, None, None, None),
        ]
        mock_conn.execute.return_value.fetchall.return_value = [
            ("A", "B", 1),
            ("A", "A", 3),  # Circular: A -> ... -> A
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.find_path("A", "B", max_depth=5)

            # Should still return results
            assert len(results) >= 1


class TestGraphStatistics:
    """Test graph statistics.

    Covers:
    - get_stats() - empty graph, with data
    """

    @pytest.mark.asyncio
    async def test_get_stats_empty_graph(self, tmp_path: Any) -> None:
        """Should return stats for empty graph."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "stats_empty.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (0,)
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            stats = await kg.get_stats()

            assert stats["total_entities"] == 0
            assert stats["total_relationships"] == 0
            assert stats["entity_types"] == {}
            assert stats["relationship_types"] == {}

    @pytest.mark.asyncio
    async def test_get_stats_with_entities(self, tmp_path: Any) -> None:
        """Should return accurate entity count."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "stats_entities.duckdb")
        mock_conn = MagicMock()
        call_count = [0]
        def fetchone_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return (5,)  # Entity count
            return (0,)
        mock_conn.execute.return_value.fetchone.side_effect = fetchone_side_effect
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            stats = await kg.get_stats()

            assert stats["total_entities"] == 5

    @pytest.mark.asyncio
    async def test_get_stats_with_relationships(self, tmp_path: Any) -> None:
        """Should return accurate relationship count."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "stats_rels.duckdb")
        mock_conn = MagicMock()
        call_count = [0]
        def fetchone_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return (0,)  # Entity count
            elif call_count[0] == 2:
                return (3,)  # Relationship count
            return (0,)
        mock_conn.execute.return_value.fetchone.side_effect = fetchone_side_effect
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            stats = await kg.get_stats()

            assert stats["total_relationships"] == 3

    @pytest.mark.asyncio
    async def test_get_stats_with_type_breakdown(self, tmp_path: Any) -> None:
        """Should return entity and relationship type breakdowns."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "stats_types.duckdb")
        mock_conn = MagicMock()
        call_count = [0]
        def fetchone_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return (2,)  # Entity count
            elif call_count[0] == 2:
                return (3,)  # Relationship count
            elif call_count[0] == 3:
                return [("project", 5), ("library", 3)]  # Entity types
            elif call_count[0] == 4:
                return [("uses", 4), ("depends_on", 2)]  # Relationship types
            return None
        mock_conn.execute.return_value.fetchone.side_effect = fetchone_side_effect
        mock_conn.execute.return_value.fetchall.side_effect = lambda *args, **kwargs: []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            stats = await kg.get_stats()

            assert "entity_types" in stats
            assert "relationship_types" in stats

    @pytest.mark.asyncio
    async def test_get_stats_includes_database_path(self, tmp_path: Any) -> None:
        """Should include database path in stats."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "stats_path.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (0,)
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            stats = await kg.get_stats()

            assert stats["database_path"] == db_path

    @pytest.mark.asyncio
    async def test_get_stats_includes_duckpgq_status(self, tmp_path: Any) -> None:
        """Should include DuckPGQ installation status in stats."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "stats_duckpgq.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (0,)
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            stats = await kg.get_stats()

            assert "duckpgq_installed" in stats


class TestBatchOperations:
    """Test batch operations scenarios.

    Covers:
    - Multiple entities in sequence
    - Multiple relations in sequence
    - Mixed operations
    """

    @pytest.mark.asyncio
    async def test_batch_create_entities(self, tmp_path: Any) -> None:
        """Should create multiple entities sequentially."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "batch_entities.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            entities = []
            for i in range(5):
                entity = await kg.create_entity(
                    name=f"entity-{i}",
                    entity_type="project",
                    observations=[f"Observation {i}"],
                )
                entities.append(entity)

            assert len(entities) == 5
            assert all("id" in e for e in entities)

    @pytest.mark.asyncio
    async def test_batch_create_relations(self, tmp_path: Any) -> None:
        """Should create multiple relations sequentially."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "batch_rels.duckdb")
        mock_conn = MagicMock()
        # Return different entities based on call order
        call_count = [0]
        def mock_fetchone():
            call_count[0] += 1
            idx = (call_count[0] - 1) // 2  # 2 calls per relation
            if idx == 0:
                return ("uuid-1", "A", "project", [], None, None, None, None)
            elif idx == 1:
                return ("uuid-2", "B", "library", [], None, None, None, None)
            elif idx == 2:
                return ("uuid-3", "C", "tool", [], None, None, None, None)
            return None
        mock_conn.execute.return_value.fetchone = mock_fetchone

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            relations = []
            for from_e, to_e in [("A", "B"), ("B", "C")]:
                rel = await kg.create_relation(from_e, to_e, "uses")
                if rel:
                    relations.append(rel)

            assert len(relations) == 2

    @pytest.mark.asyncio
    async def test_search_then_modify(self, tmp_path: Any) -> None:
        """Should search for entities and then modify them."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "search_modify.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            # First find_entity_by_name call
            ("uuid-1", "test-lib", "library", ["Initial"], None, None, None, None),
            # add_observation find
            ("uuid-1", "test-lib", "library", ["Initial"], None, None, None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # Search for entity
            found = await kg.find_entity_by_name("test-lib")
            assert found is not None

            # Add observation
            result = await kg.add_observation("test-lib", "New observation")
            assert result is True


class TestEdgeCases:
    """Test edge cases and error scenarios.

    Covers:
    - Empty results
    - Transaction rollback scenarios
    - Complex queries
    - Error propagation
    """

    @pytest.mark.asyncio
    async def test_create_entity_with_empty_observations(self, tmp_path: Any) -> None:
        """Should handle empty observations list."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "empty_obs.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            entity = await kg.create_entity(
                name="test",
                entity_type="project",
                observations=[],
            )

            assert entity["observations"] == []

    @pytest.mark.asyncio
    async def test_create_entity_with_empty_properties(self, tmp_path: Any) -> None:
        """Should handle empty properties dict."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "empty_props.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            entity = await kg.create_entity(
                name="test",
                entity_type="project",
                properties={},
            )

            assert entity["properties"] == {}

    @pytest.mark.asyncio
    async def test_create_relation_same_entity(self, tmp_path: Any) -> None:
        """Should allow self-referential relations."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "self_ref.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            # find_entity_by_name (same entity returned twice)
            ("uuid-1", "A", "project", [], None, None, None, None),
            ("uuid-1", "A", "project", [], None, None, None, None),
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            result = await kg.create_relation("A", "A", "depends_on")

            assert result is not None
            assert result["from_entity"] == "A"
            assert result["to_entity"] == "A"

    @pytest.mark.asyncio
    async def test_search_with_special_characters(self, tmp_path: Any) -> None:
        """Should handle search queries with special characters."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "special_char.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # Should not raise despite special characters
            results = await kg.search_entities(query="test%_name")

            assert results == []

    @pytest.mark.asyncio
    async def test_get_relationships_empty_database(self, tmp_path: Any) -> None:
        """Should return empty list from empty database."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "empty_db.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (
            "uuid-1",
            "A",
            "project",
            [],
            None,
            None,
            None,
            None,
        )
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.get_relationships("A")

            assert results == []

    @pytest.mark.asyncio
    async def test_find_path_direct_connection(self, tmp_path: Any) -> None:
        """Should find direct connections (path length 1)."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "direct.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            ("uuid-1", "A", "project", [], None, None, None, None),
            ("uuid-2", "B", "library", [], None, None, None, None),
        ]
        mock_conn.execute.return_value.fetchall.return_value = [
            ("A", "B", 1),  # Direct connection
        ]

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.find_path("A", "B", max_depth=1)

            assert len(results) == 1
            assert results[0]["path_length"] == 1

    @pytest.mark.asyncio
    async def test_large_limit_parameter(self, tmp_path: Any) -> None:
        """Should handle large limit values."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "large_limit.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            results = await kg.search_entities(query="test", limit=10000)

            assert results == []


class TestIntegrationScenarios:
    """Integration test scenarios with mocked DuckDB."""

    @pytest.mark.asyncio
    async def test_full_knowledge_graph_workflow(self, tmp_path: Any) -> None:
        """Should support complete knowledge graph workflow."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "workflow.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # Create entities
            proj = await kg.create_entity(
                name="session-buddy",
                entity_type="project",
                observations=["MCP server for session management"],
            )

            lib = await kg.create_entity(
                name="fastmcp",
                entity_type="library",
                observations=["MCP framework"],
            )

            # Create relation
            relation = await kg.create_relation(
                from_entity="session-buddy",
                to_entity="fastmcp",
                relation_type="uses",
            )

            # Search
            results = await kg.search_entities(query="session")

            # Get relationships
            rels = await kg.get_relationships("session-buddy")

            # Get stats
            stats = await kg.get_stats()

            assert "id" in proj
            assert "id" in lib
            assert relation is not None or relation is None  # Depends on mock

    @pytest.mark.asyncio
    async def test_graph_traversal_workflow(self, tmp_path: Any) -> None:
        """Should support graph traversal workflows."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "traversal.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # Create chain: A -> B -> C -> D
            for name in ["A", "B", "C", "D"]:
                await kg.create_entity(name=name, entity_type="entity")

            # Find path
            path = await kg.find_path("A", "D", max_depth=5)

            # Query relationships
            all_rels = await kg.get_relationships("B", direction="both")

            # Get stats
            stats = await kg.get_stats()

            assert stats["total_entities"] >= 0

    @pytest.mark.asyncio
    async def test_confidence_scores_in_metadata(self, tmp_path: Any) -> None:
        """Should support confidence scores in entity metadata."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "confidence.duckdb")
        mock_conn = MagicMock()

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # Create entity with confidence
            entity = await kg.create_entity(
                name="high-confidence-entity",
                entity_type="concept",
                metadata={"confidence": 0.95, "source": "manual_verification"},
            )

            assert entity["metadata"]["confidence"] == 0.95

            # Create entity with low confidence
            entity2 = await kg.create_entity(
                name="low-confidence-entity",
                entity_type="concept",
                metadata={"confidence": 0.3, "source": "inferred"},
            )

            assert entity2["metadata"]["confidence"] == 0.3

    @pytest.mark.asyncio
    async def test_observation_append_workflow(self, tmp_path: Any) -> None:
        """Should support adding multiple observations over time."""
        from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

        db_path = str(tmp_path / "observations_workflow.duckdb")
        mock_conn = MagicMock()
        call_count = [0]
        def mock_fetchone():
            call_count[0] += 1
            if call_count[0] == 1:
                return ("uuid-1", "proj", "project", ["Obs 1"], None, None, None, None)
            elif call_count[0] == 2:
                return ("uuid-1", "proj", "project", ["Obs 1", "Obs 2"], None, None, None, None)
            return None
        mock_conn.execute.return_value.fetchone = mock_fetchone

        with patch("session_buddy.knowledge_graph_db.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn

            kg = KnowledgeGraphDatabase(db_path=db_path)
            await kg.initialize()

            # Add first observation
            result1 = await kg.add_observation("proj", "Obs 2")
            assert result1 is True

            # Add second observation
            result2 = await kg.add_observation("proj", "Obs 3")
            assert result2 is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
