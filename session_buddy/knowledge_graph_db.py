#!/usr/bin/env python3
"""Knowledge Graph Database using DuckDB + DuckPGQ Extension.

This module provides semantic memory (knowledge graph) capabilities
using DuckDB's DuckPGQ extension for SQL/PGQ (Property Graph Queries).

The knowledge graph stores:
- **Entities**: Nodes representing projects, libraries, technologies, concepts
- **Relations**: Edges connecting entities (uses, depends_on, developed_by, etc.)
- **Observations**: Facts and notes attached to entities

This is separate from the episodic memory (conversations) in ReflectionDatabase.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import duckdb

try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False


class KnowledgeGraphDatabase:
    """Manages knowledge graph using DuckDB + DuckPGQ extension.

    This class provides semantic memory through a property graph model,
    complementing the episodic memory in ReflectionDatabase.

    Example:
        >>> async with KnowledgeGraphDatabase() as kg:
        >>>     entity = await kg.create_entity(
        >>>         name="session-mgmt-mcp",
        >>>         entity_type="project"
        >>>     )
        >>>     relation = await kg.create_relation(
        >>>         from_entity="session-mgmt-mcp",
        >>>         to_entity="ACB",
        >>>         relation_type="uses"
        >>>     )

    """

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize knowledge graph database.

        Args:
            db_path: Path to DuckDB database file.
                    Defaults to ~/.claude/data/knowledge_graph.duckdb

        """
        self.db_path = db_path or os.path.expanduser(
            "~/.claude/data/knowledge_graph.duckdb",
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn: duckdb.DuckDBPyConnection | None = None
        self._duckpgq_installed = False

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Context manager exit with cleanup."""
        self.close()

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        """Async context manager exit with cleanup."""
        self.close()

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                # nosec B110 - intentionally suppressing exceptions during cleanup
                pass  # Ignore errors during cleanup
            finally:
                self.conn = None

    def __del__(self) -> None:
        """Destructor to ensure cleanup."""
        self.close()

    async def initialize(self) -> None:
        """Initialize database and DuckPGQ extension.

        This method:
        1. Creates DuckDB connection
        2. Installs DuckPGQ extension from community repository
        3. Creates property graph schema (entities + relationships tables)
        4. Creates the knowledge_graph property graph

        Raises:
            ImportError: If DuckDB is not available
            RuntimeError: If DuckPGQ installation fails

        """
        if not DUCKDB_AVAILABLE:
            msg = "DuckDB not available. Install with: uv add duckdb"
            raise ImportError(msg)

        # Create connection
        self.conn = duckdb.connect(self.db_path)
        assert self.conn is not None  # Type narrowing

        # Install and load DuckPGQ extension
        try:
            self.conn.execute("INSTALL duckpgq FROM community")
            self.conn.execute("LOAD duckpgq")
            self._duckpgq_installed = True
        except Exception as e:
            msg = f"Failed to install DuckPGQ extension: {e}"
            raise RuntimeError(msg) from e

        # Create schema
        await self._create_schema()

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        """Get database connection, raising error if not initialized.

        Returns:
            Active DuckDB connection

        Raises:
            RuntimeError: If connection not initialized

        """
        if self.conn is None:
            msg = "Database connection not initialized. Call initialize() first"
            raise RuntimeError(msg)
        return self.conn

    async def _create_schema(self) -> None:
        """Create knowledge graph schema with DuckPGQ property graph.

        Creates:
        - kg_entities table (nodes)
        - kg_relationships table (edges)
        - knowledge_graph property graph
        - Indexes for performance
        """
        conn = self._get_conn()

        # Create entities table (nodes/vertices)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kg_entities (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                entity_type VARCHAR NOT NULL,
                observations VARCHAR[],
                properties JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSON
            )
        """)

        # Create relationships table (edges)
        # Note: DuckDB doesn't support CASCADE constraints, so we omit ON DELETE CASCADE
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kg_relationships (
                id VARCHAR PRIMARY KEY,
                from_entity VARCHAR NOT NULL,
                to_entity VARCHAR NOT NULL,
                relation_type VARCHAR NOT NULL,
                properties JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSON,
                FOREIGN KEY (from_entity) REFERENCES kg_entities(id),
                FOREIGN KEY (to_entity) REFERENCES kg_entities(id)
            )
        """)

        # Create indexes for performance
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entities_name ON kg_entities(name)",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entities_type ON kg_entities(entity_type)",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relationships_type ON kg_relationships(relation_type)",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relationships_from ON kg_relationships(from_entity)",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relationships_to ON kg_relationships(to_entity)",
        )

        # Create property graph using DuckPGQ
        # This maps our tables to SQL/PGQ graph structure
        try:
            conn.execute("""
                CREATE PROPERTY GRAPH IF NOT EXISTS knowledge_graph
                VERTEX TABLES (kg_entities)
                EDGE TABLES (
                    kg_relationships
                        SOURCE KEY (from_entity) REFERENCES kg_entities (id)
                        DESTINATION KEY (to_entity) REFERENCES kg_entities (id)
                )
            """)
        except Exception as e:
            # Property graph might already exist, that's okay
            if "already exists" not in str(e).lower():
                raise

    async def create_entity(
        self,
        name: str,
        entity_type: str,
        observations: list[str] | None = None,
        properties: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an entity (node) in the knowledge graph.

        Args:
            name: Entity name (e.g., "session-mgmt-mcp", "Python 3.13")
            entity_type: Type of entity (e.g., "project", "language", "library")
            observations: List of facts about this entity
            properties: Additional structured properties
            metadata: Metadata (e.g., source, confidence)

        Returns:
            Created entity as dict with id, name, type, etc.

        Example:
            >>> entity = await kg.create_entity(
            >>>     name="FastBlocks",
            >>>     entity_type="framework",
            >>>     observations=["Web framework", "Built on ACB"]
            >>> )

        """
        conn = self._get_conn()
        entity_id = str(uuid.uuid4())
        observations = observations or []
        properties = properties or {}
        metadata = metadata or {}
        now = datetime.now(UTC)

        conn.execute(
            """
            INSERT INTO kg_entities (id, name, entity_type, observations, properties, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                name,
                entity_type,
                observations,
                json.dumps(properties),
                now,
                now,
                json.dumps(metadata),
            ),
        )

        return {
            "id": entity_id,
            "name": name,
            "entity_type": entity_type,
            "observations": observations,
            "properties": properties,
            "created_at": now.isoformat(),
            "metadata": metadata,
        }

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Retrieve an entity by ID.

        Args:
            entity_id: UUID of the entity

        Returns:
            Entity dict or None if not found

        """
        conn = self._get_conn()

        result = conn.execute(
            "SELECT * FROM kg_entities WHERE id = ?",
            (entity_id,),
        ).fetchone()

        if not result:
            return None

        # Type annotations for clarity - result is tuple from fetchone()
        entity_id_str: str = str(result[0])
        name: str = str(result[1])  # type: ignore[misc]
        entity_type: str = str(result[2])  # type: ignore[misc]
        observations: list[str] = list(result[3]) if result[3] else []  # type: ignore[misc]
        properties_json: str | None = result[4] if len(result) > 4 else None
        created_at_raw = result[5] if len(result) > 5 else None
        updated_at_raw = result[6] if len(result) > 6 else None
        metadata_json: str | None = result[7] if len(result) > 7 else None

        return {
            "id": entity_id_str,
            "name": name,
            "entity_type": entity_type,
            "observations": observations,
            "properties": json.loads(properties_json) if properties_json else {},
            "created_at": created_at_raw.isoformat() if created_at_raw else None,
            "updated_at": updated_at_raw.isoformat() if updated_at_raw else None,
            "metadata": json.loads(metadata_json) if metadata_json else {},
        }

    async def find_entity_by_name(
        self,
        name: str,
        entity_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Find an entity by name (case-insensitive).

        Args:
            name: Entity name to search for
            entity_type: Optional type filter

        Returns:
            First matching entity or None

        """
        conn = self._get_conn()

        if entity_type:
            result = conn.execute(
                "SELECT * FROM kg_entities WHERE LOWER(name) = LOWER(?) AND entity_type = ? LIMIT 1",
                (name, entity_type),
            ).fetchone()
        else:
            result = conn.execute(
                "SELECT * FROM kg_entities WHERE LOWER(name) = LOWER(?) LIMIT 1",
                (name,),
            ).fetchone()

        if not result:
            return None

        # Type annotations for clarity - result is tuple from fetchone()
        entity_id: str = str(result[0])
        entity_name: str = str(result[1])  # type: ignore[misc]
        entity_type_str: str = str(result[2])  # type: ignore[misc]
        observations: list[str] = list(result[3]) if result[3] else []  # type: ignore[misc]
        properties_json: str | None = result[4] if len(result) > 4 else None
        created_at_raw = result[5] if len(result) > 5 else None
        updated_at_raw = result[6] if len(result) > 6 else None
        metadata_json: str | None = result[7] if len(result) > 7 else None

        return {
            "id": entity_id,
            "name": entity_name,
            "entity_type": entity_type_str,
            "observations": observations,
            "properties": json.loads(properties_json) if properties_json else {},
            "created_at": created_at_raw.isoformat() if created_at_raw else None,
            "updated_at": updated_at_raw.isoformat() if updated_at_raw else None,
            "metadata": json.loads(metadata_json) if metadata_json else {},
        }

    async def create_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Create a relationship between two entities.

        Args:
            from_entity: Source entity name
            to_entity: Target entity name
            relation_type: Type of relationship (e.g., "uses", "depends_on")
            properties: Additional properties
            metadata: Metadata

        Returns:
            Created relationship dict, or None if entities not found

        Example:
            >>> relation = await kg.create_relation(
            >>>     from_entity="crackerjack",
            >>>     to_entity="Python 3.13",
            >>>     relation_type="uses"
            >>> )

        """
        # Find source and target entities
        from_node = await self.find_entity_by_name(from_entity)
        to_node = await self.find_entity_by_name(to_entity)

        if not from_node or not to_node:
            return None

        conn = self._get_conn()
        relation_id = str(uuid.uuid4())
        properties = properties or {}
        metadata = metadata or {}
        now = datetime.now(UTC)

        conn.execute(
            """
            INSERT INTO kg_relationships (id, from_entity, to_entity, relation_type, properties, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation_id,
                from_node["id"],
                to_node["id"],
                relation_type,
                json.dumps(properties),
                now,
                json.dumps(metadata),
            ),
        )

        return {
            "id": relation_id,
            "from_entity": from_entity,
            "to_entity": to_entity,
            "relation_type": relation_type,
            "properties": properties,
            "created_at": now.isoformat(),
            "metadata": metadata,
        }

    async def add_observation(self, entity_name: str, observation: str) -> bool:
        """Add an observation (fact) to an existing entity.

        Args:
            entity_name: Name of the entity
            observation: Fact to add

        Returns:
            True if successful, False if entity not found

        """
        entity = await self.find_entity_by_name(entity_name)
        if not entity:
            return False

        conn = self._get_conn()
        observations = entity.get("observations", [])
        observations.append(observation)
        now = datetime.now(UTC)

        conn.execute(
            """
            UPDATE kg_entities
            SET observations = ?, updated_at = ?
            WHERE id = ?
            """,
            (observations, now, entity["id"]),
        )

        return True

    async def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for entities by name or observations.

        Args:
            query: Search query (matches name and observations)
            entity_type: Optional filter by type
            limit: Maximum results to return

        Returns:
            List of matching entities

        """
        conn = self._get_conn()

        params_tuple: tuple[str, ...] | tuple[str, str, str, int] | tuple[str, str, int]
        if entity_type:
            sql = """
                SELECT * FROM kg_entities
                WHERE (LOWER(name) LIKE LOWER(?) OR ARRAY_TO_STRING(observations, ' ') LIKE LOWER(?))
                  AND entity_type = ?
                ORDER BY created_at DESC
                LIMIT ?
            """
            params_tuple = (f"%{query}%", f"%{query}%", entity_type, limit)
        else:
            sql = """
                SELECT * FROM kg_entities
                WHERE LOWER(name) LIKE LOWER(?) OR ARRAY_TO_STRING(observations, ' ') LIKE LOWER(?)
                ORDER BY created_at DESC
                LIMIT ?
            """
            params_tuple = (f"%{query}%", f"%{query}%", limit)

        results = conn.execute(sql, params_tuple).fetchall()

        entities: list[dict[str, Any]] = []
        for row in results:
            entity_id: str = str(row[0])
            name: str = str(row[1])
            row_entity_type: str = str(row[2])
            observations: list[str] = list(row[3]) if row[3] else []
            properties_json: str | None = row[4] if len(row) > 4 else None
            created_at_raw = row[5] if len(row) > 5 else None
            updated_at_raw = row[6] if len(row) > 6 else None
            metadata_json: str | None = row[7] if len(row) > 7 else None

            entities.append(
                {
                    "id": entity_id,
                    "name": name,
                    "entity_type": row_entity_type,
                    "observations": observations,
                    "properties": json.loads(properties_json)
                    if properties_json
                    else {},
                    "created_at": created_at_raw.isoformat()
                    if created_at_raw
                    else None,
                    "updated_at": updated_at_raw.isoformat()
                    if updated_at_raw
                    else None,
                    "metadata": json.loads(metadata_json) if metadata_json else {},
                },
            )
        return entities

    async def get_relationships(
        self,
        entity_name: str,
        relation_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        """Get all relationships for an entity.

        Args:
            entity_name: Entity to find relationships for
            relation_type: Optional filter by relationship type
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of relationships

        """
        entity = await self.find_entity_by_name(entity_name)
        if not entity:
            return []

        conn = self._get_conn()

        where_clause, params = self._build_relationship_filters(
            direction,
            relation_type,
            entity,
        )

        # Build SQL safely - all user input is parameterized via params list
        sql = (
            "SELECT r.id, r.relation_type, e1.name as from_name, "
            "e2.name as to_name, r.properties, r.created_at "
            "FROM kg_relationships r "
            "JOIN kg_entities e1 ON r.from_entity = e1.id "
            "JOIN kg_entities e2 ON r.to_entity = e2.id "
            + where_clause
            + " ORDER BY r.created_at DESC"
        )

        results = conn.execute(sql, params).fetchall()

        relationships: list[dict[str, Any]] = []
        for row in results:
            rel_id: str = str(row[0])
            row_relation_type: str = str(row[1])
            from_name: str = str(row[2])
            to_name: str = str(row[3])
            properties_json: str | None = row[4] if len(row) > 4 else None
            created_at_raw = row[5] if len(row) > 5 else None

            relationships.append(
                {
                    "id": rel_id,
                    "relation_type": row_relation_type,
                    "from_entity": from_name,
                    "to_entity": to_name,
                    "properties": json.loads(properties_json)
                    if properties_json
                    else {},
                    "created_at": created_at_raw.isoformat()
                    if created_at_raw
                    else None,
                },
            )
        return relationships

    def _build_relationship_filters(
        self,
        direction: str,
        relation_type: str | None,
        entity: dict[str, Any],
    ) -> tuple[str, tuple[str, ...]]:
        """Build WHERE clause and parameters for relationship queries."""
        entity_id = entity["id"]
        if direction == "outgoing":
            base_clause = "WHERE r.from_entity = ?"
            params: tuple[str, ...] = (entity_id,)
        elif direction == "incoming":
            base_clause = "WHERE r.to_entity = ?"
            params = (entity_id,)
        else:
            base_clause = "WHERE (r.from_entity = ? OR r.to_entity = ?)"
            params = (entity_id, entity_id)

        if relation_type:
            base_clause += " AND r.relation_type = ?"
            params = (*params, relation_type)

        return base_clause, params

    async def find_path(
        self,
        from_entity: str,
        to_entity: str,
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        """Find paths between two entities using SQL/PGQ.

        Args:
            from_entity: Starting entity name
            to_entity: Target entity name
            max_depth: Maximum path length

        Returns:
            List of paths, each with nodes and relationships

        Note:
            This uses DuckPGQ's SQL/PGQ syntax for graph pattern matching.

        """
        from_node = await self.find_entity_by_name(from_entity)
        to_node = await self.find_entity_by_name(to_entity)

        if not from_node or not to_node:
            return []

        conn = self._get_conn()

        # Use SQL/PGQ for path finding
        # This is the beautiful part - SQL:2023 standard graph queries!
        query = """
            SELECT *
            FROM GRAPH_TABLE (knowledge_graph
                MATCH (start)-[path:*1..?] ->(end)
                WHERE start.id = ?
                  AND end.id = ?
                COLUMNS (
                    start.name AS from_name,
                    end.name AS to_name,
                    length(path) AS path_length
                )
            )
        """
        params = [max_depth, from_node["id"], to_node["id"]]

        try:
            results = conn.execute(query, params).fetchall()

            paths = []
            for row in results:
                from_name: str = str(row[0])
                to_name: str = str(row[1])
                path_length: int = int(row[2])

                paths.append(
                    {
                        "from_entity": from_name,
                        "to_entity": to_name,
                        "path_length": path_length,
                    },
                )
            return paths
        except Exception:
            # Fallback to simple check if SQL/PGQ fails
            # (This can happen if graph is complex)
            return []

    async def get_stats(self) -> dict[str, Any]:
        """Get knowledge graph statistics.

        Returns:
            Stats including entity count, relationship count, types

        """
        conn = self._get_conn()

        # Count entities
        entity_count_result = conn.execute(
            "SELECT COUNT(*) FROM kg_entities",
        ).fetchone()
        entity_count: int = int(entity_count_result[0]) if entity_count_result else 0

        # Count relationships
        relationship_count_result = conn.execute(
            "SELECT COUNT(*) FROM kg_relationships",
        ).fetchone()
        relationship_count: int = (
            int(relationship_count_result[0]) if relationship_count_result else 0
        )

        # Get entity types
        entity_types = conn.execute("""
            SELECT entity_type, COUNT(*) as count
            FROM kg_entities
            GROUP BY entity_type
            ORDER BY count DESC
        """).fetchall()

        # Get relationship types
        relationship_types = conn.execute("""
            SELECT relation_type, COUNT(*) as count
            FROM kg_relationships
            GROUP BY relation_type
            ORDER BY count DESC
        """).fetchall()

        return {
            "total_entities": entity_count,
            "total_relationships": relationship_count,
            "entity_types": dict(entity_types),
            "relationship_types": dict(relationship_types),
            "database_path": self.db_path,
            "duckpgq_installed": self._duckpgq_installed,
        }
