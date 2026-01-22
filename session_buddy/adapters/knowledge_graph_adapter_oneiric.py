"""Oneiric-compatible knowledge graph adapter using native DuckDB implementation.

Provides a Oneiric-compatible knowledge graph adapter that maintains the existing
KnowledgeGraphDatabase API while using native DuckDB operations instead of ACB.

Phase 5: Oneiric Adapter Conversion - Knowledge Graph Adapter

Key Features:
    - Native DuckDB PGQ extension for property graph queries
    - Oneiric settings and lifecycle management
    - Backward-compatible API with existing KnowledgeGraphDatabase
    - No ACB dependencies
    - Fast local/in-memory operations

"""

from __future__ import annotations

import json
import typing as t
import uuid
from datetime import UTC, datetime

from session_buddy.adapters.settings import KnowledgeGraphAdapterSettings

if t.TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType

    import duckdb

# DuckDB will be imported at runtime
DUCKDB_AVAILABLE = True
try:
    import duckdb
except ImportError:
    DUCKDB_AVAILABLE = False
    if t.TYPE_CHECKING:
        # Type stub for type checking when duckdb is not installed
        import types

        duckdb = types.SimpleNamespace()  # type: ignore[misc,assignment]


class KnowledgeGraphDatabaseAdapterOneiric:
    """Oneiric-compatible knowledge graph adapter using native DuckDB.

    This adapter provides the same API as the ACB-based KnowledgeGraphDatabaseAdapter
    but uses native DuckDB operations and Oneiric settings instead of ACB configuration.

    Key differences from ACB implementation:
        - Uses Oneiric settings (dataclass-based) instead of ACB Config
        - No ACB dependency injection
        - Same hybrid sync/async pattern (sync DuckDB ops, async interface)
        - Maintains full API compatibility

    Example:
        >>> settings = KnowledgeGraphAdapterSettings.from_settings()
        >>> async with KnowledgeGraphDatabaseAdapterOneiric(settings=settings) as kg:
        >>>     entity = await kg.create_entity("project", "project", ["observation"])
        >>>     relation = await kg.create_relation("proj1", "proj2", "depends_on")

    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        settings: KnowledgeGraphAdapterSettings | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Initialize adapter with optional database path.

        Args:
            db_path: Path to DuckDB database file. If None, uses path from settings.
            settings: KnowledgeGraphAdapterSettings instance. If None, creates from defaults.
            collection_name: Optional collection name (alias for graph_name for API compatibility).

        """
        # Create settings with custom graph_name if collection_name provided
        if collection_name and settings is None:
            # Create custom settings with collection_name as graph_name
            from session_buddy.adapters.settings import _resolve_data_dir

            data_dir = _resolve_data_dir()
            settings = KnowledgeGraphAdapterSettings(
                database_path=data_dir / f"knowledge_graph_{collection_name}.duckdb",
                graph_name=collection_name,
            )

        self.settings = settings or KnowledgeGraphAdapterSettings.from_settings()
        # Use unique database file per graph name to avoid DuckDB locking conflicts
        if db_path:
            self.db_path = str(db_path)
        else:
            # Add graph name suffix to database path for test isolation
            db_path_from_settings = self.settings.database_path
            graph_name = self.settings.graph_name
            if graph_name != "session_mgmt_graph" and not str(
                db_path_from_settings
            ).endswith(f"{graph_name}.duckdb"):
                # Create unique database file per graph name
                self.db_path = str(
                    db_path_from_settings.parent
                    / f"{db_path_from_settings.stem}_{graph_name}.duckdb"
                )
            else:
                self.db_path = str(db_path_from_settings)
        self.conn: t.Any = None  # DuckDB connection (sync)
        self._duckpgq_installed = False
        self._initialized = False

    def __enter__(self) -> t.Self:
        """Sync context manager entry (not recommended - use async)."""
        msg = "Use 'async with' instead of 'with' for KnowledgeGraphDatabaseAdapterOneiric"
        raise RuntimeError(msg)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Sync context manager exit."""

    async def __aenter__(self) -> t.Self:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Async context manager exit with cleanup."""
        self.close()

    def close(self) -> None:
        """Close DuckDB connection."""
        # Use hasattr to safely check for conn attribute (may not exist if init failed)
        if hasattr(self, "conn") and self.conn is not None:
            self.conn.close()
            self.conn = None

    def __del__(self) -> None:
        """Destructor to ensure cleanup."""
        self.close()

    async def aclose(self) -> None:
        """Async close method for compatibility with async context managers."""
        self.close()

    def _get_db_path(self) -> str:
        """Get database path from settings or use default.

        Returns:
            Database file path

        """
        # Prefer instance path when provided
        if self.db_path:
            return self.db_path

        # Use settings path
        return str(self.settings.database_path)

    async def initialize(self) -> None:
        """Initialize DuckDB connection and create schema.

        This method:
        1. Gets database path from settings
        2. Creates sync DuckDB connection (fast, local)
        3. Installs and loads DuckPGQ extension
        4. Creates knowledge graph schema
        """
        if self._initialized:
            return

        if not DUCKDB_AVAILABLE:
            msg = "DuckDB not available. Install with: uv add duckdb"
            raise ImportError(msg)

        # Get database path
        db_path = self._get_db_path()

        # Create sync DuckDB connection (fast, local operation)
        self.conn = duckdb.connect(db_path)

        # Install and load DuckPGQ extension
        try:
            extensions = self.settings.install_extensions
            for extension in extensions:
                self.conn.execute(f"INSTALL {extension} FROM community")
                self.conn.execute(f"LOAD {extension}")
            self._duckpgq_installed = True
        except Exception as e:
            msg = f"Failed to install DuckPGQ extension: {e}"
            raise RuntimeError(msg) from e

        # Create schema (sync operations, complete quickly)
        await self._create_schema()

        self._initialized = True

    def _get_conn(self) -> t.Any:
        """Get DuckDB connection, raising error if not initialized.

        Returns:
            Active DuckDB connection

        Raises:
            RuntimeError: If connection not initialized

        """
        if self.conn is None:
            msg = "Database connection not initialized. Call initialize() first"
            raise RuntimeError(msg)
        return self.conn

    async def _resolve_entity_id(self, identifier: str) -> str:
        """Resolve an entity identifier to its canonical ID."""
        entity = await self.find_entity_by_name(identifier)
        if entity:
            # Type narrow entity["id"] to str
            entity_id = entity["id"]
            return entity_id if isinstance(entity_id, str) else str(entity_id)

        row = (
            self._get_conn()
            .execute(
                "SELECT id FROM kg_entities WHERE id = ?",
                (identifier,),
            )
            .fetchone()
        )
        if row:
            # Type narrow row[0] to str (id column is TEXT in SQL)
            return row[0] if isinstance(row[0], str) else str(row[0])

        msg = f"Entity '{identifier}' not found"
        raise ValueError(msg)

    def _format_timestamp(self, value: t.Any) -> str | None:
        """Format timestamps consistently across DuckDB outputs."""
        if value is None:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    async def _create_schema(self) -> None:
        """Create knowledge graph schema.

        Creates:
        - kg_entities table (nodes)
        - kg_relationships table (edges)
        - Indexes for performance

        Note: Executes synchronously but completes quickly (local operation)
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kg_relationships (
                id VARCHAR PRIMARY KEY,
                from_entity VARCHAR NOT NULL,
                to_entity VARCHAR NOT NULL,
                relation_type VARCHAR NOT NULL,
                properties JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSON
            )
        """)

        # Ensure columns exist when DuckPGQ pre-creates tables without all fields.
        relationship_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info('kg_relationships')").fetchall()
        }
        if "updated_at" not in relationship_columns:
            conn.execute(
                "ALTER TABLE kg_relationships "
                "ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )

        # Create indexes for performance
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entities_name ON kg_entities(name)",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entities_type ON kg_entities(entity_type)",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relationships_from "
            "ON kg_relationships(from_entity)",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relationships_to "
            "ON kg_relationships(to_entity)",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relationships_type "
            "ON kg_relationships(relation_type)",
        )

    async def create_entity(
        self,
        name: str,
        entity_type: str,
        observations: list[str] | None = None,
        properties: dict[str, t.Any] | None = None,
        metadata: dict[str, t.Any] | None = None,
        attributes: list[str] | None = None,  # Deprecated alias for observations
    ) -> dict[str, t.Any]:
        """Create a new entity (node) in the knowledge graph.

        Args:
            name: Entity name (must be unique)
            entity_type: Type/category of entity
            observations: List of observation strings
            properties: Additional properties as key-value pairs
            metadata: Additional metadata
            attributes: Deprecated alias for observations (for backward compatibility)

        Returns:
            Created entity as dictionary

        Raises:
            ValueError: If entity with name already exists

        """
        conn = self._get_conn()

        # Support both 'attributes' (deprecated) and 'observations' parameters
        # Handle backward compatibility where 'attributes' might be a dict (properties) or list (observations)
        if attributes is not None:
            if isinstance(attributes, dict):
                # 'attributes' is actually properties - merge with properties param
                properties = {**(properties or {}), **attributes}
                entity_observations = observations or []
            elif isinstance(attributes, list):
                # 'attributes' is a list - treat as observations
                entity_observations = observations or attributes
            else:
                entity_observations = observations or []
        else:
            entity_observations = observations or []

        # Check if entity already exists
        existing = await self.find_entity_by_name(name)
        if existing:
            msg = f"Entity with name '{name}' already exists"
            raise ValueError(msg)

        entity_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)

        # Sync DuckDB execution (fast, local operation)
        conn.execute(
            """
            INSERT INTO kg_entities
            (id, name, entity_type, observations, properties, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                name,
                entity_type,
                entity_observations,
                json.dumps(properties or {}),
                now,
                now,
                json.dumps(metadata or {}),
            ),
        )

        return {
            "id": entity_id,
            "name": name,
            "entity_type": entity_type,
            "observations": observations or [],
            "properties": properties or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "metadata": metadata or {},
        }

    async def get_entity(self, entity_id: str) -> dict[str, t.Any] | None:
        """Get entity by ID.

        Args:
            entity_id: Entity UUID

        Returns:
            Entity dictionary or None if not found

        """
        conn = self._get_conn()

        result = conn.execute(
            "SELECT * FROM kg_entities WHERE id = ?",
            (entity_id,),
        ).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "name": result[1],
            "entity_type": result[2],
            "observations": list(result[3]) if result[3] else [],
            "properties": json.loads(result[4]) if result[4] else {},
            "created_at": self._format_timestamp(result[5]),
            "updated_at": self._format_timestamp(result[6]),
            "metadata": json.loads(result[7]) if result[7] else {},
        }

    async def find_entity_by_name(self, name: str) -> dict[str, t.Any] | None:
        """Find entity by name.

        Args:
            name: Entity name to search for

        Returns:
            Entity dictionary or None if not found

        """
        conn = self._get_conn()

        result = conn.execute(
            """
            SELECT id, name, entity_type, observations, properties,
                   created_at, updated_at, metadata
            FROM kg_entities
            WHERE name = ?
            """,
            (name,),
        ).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "name": result[1],
            "entity_type": result[2],
            "observations": list(result[3]) if result[3] else [],
            "properties": json.loads(result[4]) if result[4] else {},
            "created_at": result[5].isoformat() if result[5] else None,
            "updated_at": result[6].isoformat() if result[6] else None,
            "metadata": json.loads(result[7]) if result[7] else {},
        }

    async def create_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        properties: dict[str, t.Any] | None = None,
        metadata: dict[str, t.Any] | None = None,
    ) -> dict[str, t.Any]:
        """Create a relationship (edge) between two entities.

        Args:
            from_entity: Source entity name
            to_entity: Target entity name
            relation_type: Type of relationship
            properties: Additional properties
            metadata: Additional metadata

        Returns:
            Created relationship as dictionary

        Raises:
            ValueError: If either entity doesn't exist

        """
        conn = self._get_conn()

        # Resolve entity identifiers to IDs (accepts names or IDs)
        resolved_from_entity = await self._resolve_entity_id(from_entity)
        resolved_to_entity = await self._resolve_entity_id(to_entity)

        relation_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)

        conn.execute(
            """
            INSERT INTO kg_relationships
            (id, from_entity, to_entity, relation_type, properties, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation_id,
                resolved_from_entity,
                resolved_to_entity,
                relation_type,
                json.dumps(properties or {}),
                now,
                now,
                json.dumps(metadata or {}),
            ),
        )

        return {
            "id": relation_id,
            "from_entity": resolved_from_entity,
            "to_entity": resolved_to_entity,
            "relation_type": relation_type,
            "properties": properties or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "metadata": metadata or {},
        }

    async def add_observation(
        self,
        entity_name: str,
        observation: str,
    ) -> dict[str, t.Any]:
        """Add an observation to an entity.

        Args:
            entity_name: Name of entity to update
            observation: Observation text to add

        Returns:
            Updated entity dictionary

        Raises:
            ValueError: If entity doesn't exist

        """
        conn = self._get_conn()

        entity = await self.find_entity_by_name(entity_name)
        if not entity:
            msg = f"Entity '{entity_name}' not found"
            raise ValueError(msg)

        now = datetime.now(tz=UTC)

        # Append observation to array
        conn.execute(
            """
            UPDATE kg_entities
            SET observations = list_append(observations, ?),
                updated_at = ?
            WHERE name = ?
            """,
            (observation, now, entity_name),
        )

        # Return updated entity
        return await self.find_entity_by_name(entity_name)  # type: ignore[return-value]

    async def search_entities(
        self,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, t.Any]]:
        """Search for entities by name or observations.

        Args:
            query: Search query (matches name and observations)
            entity_type: Filter by entity type
            limit: Maximum number of results

        Returns:
            List of matching entities

        """
        conn = self._get_conn()

        # Build query dynamically
        conditions = []
        params: list[t.Any] = []

        if query:
            conditions.append("(name LIKE ? OR list_contains(observations, ?))")
            params.extend([f"%{query}%", query])

        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        # Build SQL safely - all user input is parameterized via params list
        sql = (
            "SELECT id, name, entity_type, observations, properties, "
            "created_at, updated_at, metadata "
            "FROM kg_entities WHERE "
            + where_clause
            + " ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)

        result = conn.execute(sql, params).fetchall()

        # Use list comprehension for better readability (refurb FURB138)
        return [
            {
                "id": row[0],
                "name": row[1],
                "entity_type": row[2],
                "observations": list(row[3]) if row[3] else [],
                "properties": json.loads(row[4]) if row[4] else {},
                "created_at": self._format_timestamp(row[5]),
                "updated_at": self._format_timestamp(row[6]),
                "metadata": json.loads(row[7]) if row[7] else {},
            }
            for row in result
        ]

    async def get_relationships(
        self,
        entity_name: str,
        relation_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, t.Any]]:
        """Get all relationships for a specific entity.

        Args:
            entity_name: Name of entity to get relationships for
            relation_type: Optional filter by relationship type
            direction: "outgoing", "incoming", or "both" (default)

        Returns:
            List of relationships involving this entity

        """
        conn = self._get_conn()
        resolved_entity = await self._resolve_entity_id(entity_name)

        conditions = []
        params: list[t.Any] = []

        if direction == "outgoing":
            conditions.append("from_entity = ?")
            params.append(resolved_entity)
        elif direction == "incoming":
            conditions.append("to_entity = ?")
            params.append(resolved_entity)
        else:  # both
            conditions.append("(from_entity = ? OR to_entity = ?)")
            params.extend([resolved_entity, resolved_entity])

        if relation_type:
            conditions.append("relation_type = ?")
            params.append(relation_type)

        where_clause = " AND ".join(conditions)
        # Build SQL safely - all user input is parameterized via params list
        sql = (
            "SELECT id, from_entity, to_entity, relation_type, properties, "
            "created_at, updated_at, metadata "
            "FROM kg_relationships WHERE " + where_clause + " ORDER BY created_at DESC"
        )

        result = conn.execute(sql, params).fetchall()

        # Use list comprehension for better readability (refurb FURB138)
        return [
            {
                "id": row[0],
                "from_entity": row[1],
                "to_entity": row[2],
                "relation_type": row[3],
                "properties": json.loads(row[4]) if row[4] else {},
                "created_at": self._format_timestamp(row[5]),
                "updated_at": self._format_timestamp(row[6]),
                "metadata": json.loads(row[7]) if row[7] else {},
            }
            for row in result
        ]

    async def find_path(
        self,
        from_entity: str,
        to_entity: str,
        max_depth: int = 5,
    ) -> list[dict[str, t.Any]]:
        """Find paths between two entities using breadth-first search.

        Args:
            from_entity: Starting entity name
            to_entity: Target entity name
            max_depth: Maximum path length to search

        Returns:
            Paths found between entities with hop counts

        """
        conn = self._get_conn()
        resolved_from_entity = await self._resolve_entity_id(from_entity)
        resolved_to_entity = await self._resolve_entity_id(to_entity)

        # Get all relationships in one query (sync, fast local operation)
        result = conn.execute(
            "SELECT from_entity, to_entity, relation_type FROM kg_relationships",
        ).fetchall()

        # Build adjacency list
        graph: dict[str, list[tuple[str, str]]] = {}
        for row in result:
            from_e = row[0]
            to_e = row[1]
            rel_type = row[2]

            if from_e not in graph:
                graph[from_e] = []
            graph[from_e].append((to_e, rel_type))

        # BFS to find shortest path
        from collections import deque

        queue: deque[tuple[str, list[str], list[str]]] = deque(
            [(resolved_from_entity, [resolved_from_entity], [])],
        )
        visited = {resolved_from_entity}

        paths: list[dict[str, t.Any]] = []
        while queue and not paths:  # Find first path only (refurb FURB115)
            current, path, relations = queue.popleft()

            if len(path) > max_depth + 1:
                continue

            if current == resolved_to_entity and len(path) > 1:
                paths.append(
                    {
                        "path": path,
                        "relations": relations,
                        "hops": len(path) - 1,
                    },
                )
                break

            for neighbor, rel_type in graph.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, [*path, neighbor], [*relations, rel_type]))

        return paths

    async def get_stats(self) -> dict[str, t.Any]:
        """Get statistics about the knowledge graph.

        Returns:
            Summary with entity count, relationship count, type distributions

        """
        conn = self._get_conn()

        # Entity count
        entity_count = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]

        # Relationship count
        relationship_count = conn.execute(
            "SELECT COUNT(*) FROM kg_relationships",
        ).fetchone()[0]

        # Entity types distribution
        entity_types_result = conn.execute(
            """
            SELECT entity_type, COUNT(*) as count
            FROM kg_entities
            GROUP BY entity_type
        """,
        ).fetchall()
        entity_types = {row[0]: row[1] for row in entity_types_result}

        # Relationship types distribution
        relationship_types_result = conn.execute(
            """
            SELECT relation_type, COUNT(*) as count
            FROM kg_relationships
            GROUP BY relation_type
        """,
        ).fetchall()
        relationship_types = {row[0]: row[1] for row in relationship_types_result}

        return {
            "total_entities": entity_count or 0,
            "total_relationships": relationship_count or 0,
            "entity_types": entity_types,
            "relationship_types": relationship_types,
        }
