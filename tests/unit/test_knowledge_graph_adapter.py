#!/usr/bin/env python3
"""Tests for knowledge_graph_adapter with Oneiric settings.

Tests the KnowledgeGraphDatabaseAdapter which uses Oneiric settings for configuration
and DuckDB PGQ extension for property graph queries.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


class TestKnowledgeGraphAdapterInit:
    """Test KnowledgeGraphDatabaseAdapter initialization.

    Phase 2: Core Coverage - knowledge_graph_adapter.py (0% → 60%)
    """

    def test_adapter_init_with_explicit_path(self) -> None:
        """Should initialize with explicit database path."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = "/tmp/test.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        assert adapter.db_path == db_path
        assert adapter.conn is None
        assert adapter._initialized is False

    def test_adapter_init_without_path(self) -> None:
        """Should initialize without database path (uses config later)."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        adapter = KnowledgeGraphDatabaseAdapter()

        assert adapter.db_path is None
        assert adapter.conn is None
        assert adapter._initialized is False

    def test_adapter_init_with_path_object(self, tmp_path: Path) -> None:
        """Should accept Path object as database path."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / "test.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        assert adapter.db_path == str(db_path)


class TestContextManagers:
    """Test context manager protocols.

    Phase 2: Core Coverage - knowledge_graph_adapter.py (0% → 60%)
    """

    def test_sync_context_manager_raises_error(self, tmp_path: Path) -> None:
        """Should raise error when using sync context manager."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        with pytest.raises(
            RuntimeError,
            match="Use 'async with' instead of 'with' for KnowledgeGraphDatabaseAdapter",
        ):
            with adapter:
                pass

    @pytest.mark.asyncio
    async def test_async_context_manager_initializes(self, tmp_path: Path) -> None:
        """Should initialize when entering async context manager."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        async with adapter as kg:
            assert kg is adapter
            assert kg.conn is not None
            assert kg._initialized is True

        # Connection should be closed after exit
        assert adapter.conn is None

    @pytest.mark.asyncio
    async def test_async_context_manager_cleanup_on_exception(
        self, tmp_path: Path
    ) -> None:
        """Should cleanup connection even if exception occurs."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        with pytest.raises(ValueError, match="test exception"):
            async with adapter:
                msg = "test exception"
                raise ValueError(msg)

        # Connection should still be cleaned up
        assert adapter.conn is None


class TestDatabasePathResolution:
    """Test _get_db_path method with Oneiric settings."""

    def test_get_db_path_uses_settings_path(self, tmp_path: Path) -> None:
        """Should use settings path when no instance path provided."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )
        from session_buddy.adapters.settings import KnowledgeGraphAdapterSettings

        settings = KnowledgeGraphAdapterSettings(
            database_path=tmp_path / "settings.duckdb",
        )
        adapter = KnowledgeGraphDatabaseAdapter(settings=settings)

        result = adapter._get_db_path()

        assert result == str(settings.database_path)

    def test_get_db_path_uses_instance_path(self, tmp_path: Path) -> None:
        """Should prefer instance path when provided."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / "instance.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        result = adapter._get_db_path()

        assert result == str(db_path)


class TestInitialization:
    """Test initialize method.

    Phase 2: Core Coverage - knowledge_graph_adapter.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_initialize_creates_connection(self, tmp_path: Path) -> None:
        """Should create DuckDB connection."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        await adapter.initialize()

        assert adapter.conn is not None
        assert adapter._initialized is True

        adapter.close()

    @pytest.mark.asyncio
    async def test_initialize_creates_schema(self, tmp_path: Path) -> None:
        """Should create knowledge graph schema."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        await adapter.initialize()

        # Verify schema was created by checking for tables
        cursor = adapter.conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        )
        tables = {row[0] for row in cursor.fetchall()}

        assert "kg_entities" in tables
        assert "kg_relationships" in tables

        adapter.close()

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, tmp_path: Path) -> None:
        """Should be safe to call initialize multiple times."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        await adapter.initialize()

        await adapter.initialize()
        second_conn = adapter.conn

        # Should reuse connection or create new one gracefully
        assert second_conn is not None

        adapter.close()


class TestCloseAndCleanup:
    """Test close and cleanup methods.

    Phase 2: Core Coverage - knowledge_graph_adapter.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_close_closes_connection(self, tmp_path: Path) -> None:
        """Should close DuckDB connection."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        await adapter.initialize()
        assert adapter.conn is not None

        adapter.close()
        assert adapter.conn is None

    def test_close_when_not_initialized(self) -> None:
        """Should handle close when connection is None."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        adapter = KnowledgeGraphDatabaseAdapter()
        adapter.close()  # Should not raise

        assert adapter.conn is None

    @pytest.mark.asyncio
    async def test_destructor_closes_connection(self, tmp_path: Path) -> None:
        """Should close connection in destructor."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)

        await adapter.initialize()

        # Trigger destructor
        del adapter

        # Connection should be closed (can't verify directly, but shouldn't error)
        # This test mainly ensures __del__ doesn't raise


class TestEntityOperations:
    """Test entity CRUD operations.

    Phase 2: Core Coverage - knowledge_graph_adapter.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_create_entity_with_observations(self, tmp_path: Path) -> None:
        """Should create entity with observations."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_name = f"test-project-{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            result = await kg.create_entity(
                name=unique_name,
                entity_type="project",
                observations=["First observation", "Second observation"],
            )

            assert "id" in result
            assert result["name"] == unique_name
            assert result["entity_type"] == "project"
            assert len(result["observations"]) == 2

    @pytest.mark.asyncio
    async def test_create_entity_with_properties(self, tmp_path: Path) -> None:
        """Should create entity with properties."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_name = f"FastMCP-{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            properties = {"version": "1.0", "language": "python"}
            result = await kg.create_entity(
                name=unique_name,
                entity_type="library",
                observations=["MCP framework"],
                properties=properties,
            )

            assert result["name"] == unique_name
            # Properties should be stored in metadata
            assert "properties" in result or "metadata" in result

    @pytest.mark.asyncio
    async def test_find_entity_by_name(self, tmp_path: Path) -> None:
        """Should find entity by name."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_name = f"unique-entity-{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Create entity
            created = await kg.create_entity(
                name=unique_name, entity_type="test", observations=["test"]
            )

            # Find it
            found = await kg.find_entity_by_name(unique_name)

            assert found is not None
            assert found["id"] == created["id"]
            assert found["name"] == unique_name

    @pytest.mark.asyncio
    async def test_find_entity_not_found(self, tmp_path: Path) -> None:
        """Should return None when entity not found."""
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}.duckdb"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            result = await kg.find_entity_by_name("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_add_observation_to_entity(self, tmp_path: Path) -> None:
        """Should add observation to existing entity."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_name = f"test-entity-{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Create entity
            entity = await kg.create_entity(
                name=unique_name, entity_type="test", observations=["first"]
            )

            # Add observation using entity name (not ID)
            updated_entity = await kg.add_observation(
                entity["name"], "second observation"
            )

            assert isinstance(updated_entity, dict)
            assert "second observation" in updated_entity["observations"]

            # Verify observation was added
            updated = await kg.find_entity_by_name(unique_name)
            assert len(updated["observations"]) == 2

    @pytest.mark.asyncio
    async def test_search_entities_by_query(self, tmp_path: Path) -> None:
        """Should search entities by query."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_id = f"{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Create test entities with unique names
            await kg.create_entity(
                name=f"python-lib-{unique_id}",
                entity_type="library",
                observations=["Python library"],
            )
            await kg.create_entity(
                name=f"js-lib-{unique_id}",
                entity_type="library",
                observations=["JavaScript library"],
            )

            # Search for python
            results = await kg.search_entities("python")

            assert len(results) >= 1
            assert any(
                "python" in r["name"].lower()
                or "python" in str(r.get("observations", [])).lower()
                for r in results
            )


class TestRelationshipOperations:
    """Test relationship CRUD operations.

    Phase 2: Core Coverage - knowledge_graph_adapter.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_create_relation_between_entities(self, tmp_path: Path) -> None:
        """Should create relationship between entities."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_id = f"{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Create two entities with unique names
            entity1 = await kg.create_entity(
                name=f"project-a-{unique_id}",
                entity_type="project",
                observations=["test"],
            )
            entity2 = await kg.create_entity(
                name=f"project-b-{unique_id}",
                entity_type="project",
                observations=["test"],
            )

            # Create relationship using entity names (not IDs)
            relation = await kg.create_relation(
                from_entity=entity1["name"],
                to_entity=entity2["name"],
                relation_type="depends_on",
            )

            assert "id" in relation
            assert relation["relation_type"] == "depends_on"

    @pytest.mark.asyncio
    async def test_create_relation_with_properties(self, tmp_path: Path) -> None:
        """Should create relationship with properties."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_id = f"{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Create two entities with unique names
            entity1 = await kg.create_entity(
                name=f"service-a-{unique_id}",
                entity_type="service",
                observations=["test"],
            )
            entity2 = await kg.create_entity(
                name=f"service-b-{unique_id}",
                entity_type="service",
                observations=["test"],
            )

            # Create relationship with properties using entity names (not IDs)
            properties = {"version": ">=1.0", "optional": False}
            relation = await kg.create_relation(
                from_entity=entity1["name"],
                to_entity=entity2["name"],
                relation_type="requires",
                properties=properties,
            )

            assert "id" in relation
            # Properties should be in metadata
            assert "properties" in relation or "metadata" in relation

    @pytest.mark.asyncio
    async def test_get_entity_relationships(self, tmp_path: Path) -> None:
        """Should get all relationships for an entity."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_id = f"{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Create entities with unique names
            entity1 = await kg.create_entity(
                name=f"center-{unique_id}", entity_type="test", observations=["test"]
            )
            entity2 = await kg.create_entity(
                name=f"related1-{unique_id}", entity_type="test", observations=["test"]
            )
            entity3 = await kg.create_entity(
                name=f"related2-{unique_id}", entity_type="test", observations=["test"]
            )

            # Create relationships using entity names (not IDs)
            await kg.create_relation(entity1["name"], entity2["name"], "uses")
            await kg.create_relation(entity3["name"], entity1["name"], "extends")

            # Get relationships using correct method name and entity name
            relationships = await kg.get_relationships(entity1["name"])

            assert len(relationships) >= 2

    @pytest.mark.asyncio
    async def test_find_path_between_entities(self, tmp_path: Path) -> None:
        """Should find paths between entities."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_id = f"{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Create chain of entities with unique names
            e1 = await kg.create_entity(f"start-{unique_id}", "test", ["test"])
            e2 = await kg.create_entity(f"middle-{unique_id}", "test", ["test"])
            e3 = await kg.create_entity(f"end-{unique_id}", "test", ["test"])

            # Create path using entity names (not IDs)
            await kg.create_relation(e1["name"], e2["name"], "connects_to")
            await kg.create_relation(e2["name"], e3["name"], "connects_to")

            # Find path using entity names
            paths = await kg.find_path(e1["name"], e3["name"])

            # Should find a path through middle entity
            assert len(paths) >= 1


class TestStatistics:
    """Test graph statistics methods.

    Phase 2: Core Coverage - knowledge_graph_adapter.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_get_statistics_empty_graph(self, tmp_path: Path) -> None:
        """Should get statistics for empty graph."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Use correct method name: get_stats() not get_statistics()
            stats = await kg.get_stats()

            # API returns total_entities and total_relationships
            assert "total_entities" in stats
            assert "total_relationships" in stats
            assert stats["total_entities"] == 0
            assert stats["total_relationships"] == 0

    @pytest.mark.asyncio
    async def test_get_statistics_with_data(self, tmp_path: Path) -> None:
        """Should get accurate statistics."""
        import time

        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        db_path = tmp_path / f"test_{id(tmp_path)}-{int(time.time() * 1000000)}.duckdb"
        unique_id = f"{id(tmp_path)}-{int(time.time() * 1000000)}"

        async with KnowledgeGraphDatabaseAdapter(db_path) as kg:
            # Create some entities and relationships with unique names
            e1 = await kg.create_entity(f"entity1-{unique_id}", "test", ["test"])
            e2 = await kg.create_entity(f"entity2-{unique_id}", "test", ["test"])
            # Use entity names (not IDs) for create_relation
            await kg.create_relation(e1["name"], e2["name"], "relates_to")

            # Use correct method name: get_stats() not get_statistics()
            stats = await kg.get_stats()

            # API returns total_entities and total_relationships
            assert stats["total_entities"] == 2
            assert stats["total_relationships"] == 1
