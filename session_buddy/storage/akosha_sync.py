"""Hybrid sync orchestrator for cloud + HTTP fallback.

This module implements the HybridAkoshaSync class which orchestrates multiple
sync methods with automatic fallback. Cloud sync is tried first (fastest),
then HTTP sync if cloud is unavailable.

Architecture (per agent recommendations):
- Simplified orchestrator (~80 lines vs 300 lines)
- Protocol-based method selection
- Priority-based fallback (cloud -> HTTP)
- Fast availability detection (1s timeout)

Example:
    >>> config = AkoshaSyncConfig.from_settings(settings)
    >>> hybrid = HybridAkoshaSync(config)
    >>> result = await hybrid.sync_memories()
    >>> print(result['method'])
    'cloud'  # or 'http' if cloud failed
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from session_buddy.storage.akosha_config import AkoshaSyncConfig
from session_buddy.storage.cloud_sync import CloudSyncMethod
from session_buddy.storage.sync_protocol import (
    HTTPSyncError,
    HybridSyncError,
    SyncMethod,
)
from session_buddy.utils.error_management import _get_logger

logger = _get_logger()

# Default batch size for batch_store_memories
DEFAULT_BATCH_SIZE = 100

# Maximum retry attempts for HTTP requests
MAX_RETRIES = 3

# Base delay for exponential backoff (seconds)
BASE_BACKOFF_DELAY = 1.0


class HttpSyncMethod(SyncMethod):
    """HTTP sync method for direct upload to Akosha.

    Pushes memories directly to Akosha's HTTP endpoints (store_memory,
    batch_store_memories) as a fallback when cloud sync is unavailable.

    This is intended for development environments where cloud storage
    is not configured.

    Features:
        - Batch upload of conversations, reflections, and entities
        - Knowledge graph entity/relationship sync
        - Incremental sync with change detection via timestamps
        - Retry logic with exponential backoff
        - Configurable batch size
    """

    AKOSHA_DEFAULT_URL = "http://localhost:8682/mcp"

    def __init__(self, config: AkoshaSyncConfig) -> None:
        """Initialize HTTP sync method.

        Args:
            config: Akosha sync configuration
        """
        self.config = config
        self._last_sync_timestamp: dict[str, str] = {}
        self._sync_state_file = (
            Path.home() / ".claude" / "data" / "akosha_sync_state.json"
        )
        self._load_sync_state()

        # Database paths (same as CloudSyncMethod)
        self.reflection_db_path = Path.home() / ".claude" / "data" / "reflection.duckdb"
        self.knowledge_graph_db_path = (
            Path.home() / ".claude" / "data" / "knowledge_graph.duckdb"
        )

    def _load_sync_state(self) -> None:
        """Load last sync timestamps from state file."""
        try:
            if self._sync_state_file.exists():
                with open(self._sync_state_file) as f:
                    self._last_sync_timestamp = json.load(f)
        except Exception as e:
            logger.debug(f"Could not load sync state: {e}")
            self._last_sync_timestamp = {}

    def _save_sync_state(self) -> None:
        """Save last sync timestamps to state file."""
        try:
            self._sync_state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._sync_state_file, "w") as f:
                json.dump(self._last_sync_timestamp, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save sync state: {e}")

    def is_available(self) -> bool:
        """Check if Akosha HTTP endpoint is reachable.

        Returns:
            True if Akosha server is running

        Example:
            >>> http_sync.is_available()
            True  # Akosha server reachable
        """
        # Quick check: try to connect to Akosha
        return self._check_akosha_reachable()

    def get_method_name(self) -> str:
        """Get method name for logging.

        Returns:
            Method name string
        """
        return "http"

    async def sync(
        self,
        upload_reflections: bool = True,
        upload_knowledge_graph: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Sync memories via HTTP POST to Akosha.

        This method implements batch upload of memories, reflections, and
        knowledge graph data to Akosha's MCP endpoints.

        Args:
            upload_reflections: Whether to upload reflections
            upload_knowledge_graph: Whether to upload knowledge graph
            **kwargs: Additional parameters (batch_size, incremental)

        Returns:
            Sync result dictionary with:
                - method: "http"
                - success: bool
                - memories_uploaded: int
                - reflections_uploaded: int
                - entities_uploaded: int
                - relationships_uploaded: int
                - bytes_transferred: int
                - duration_seconds: float
                - error: str | None

        Raises:
            HTTPSyncError: If HTTP sync fails
        """
        start_time = time.monotonic()
        akosha_url = self.config.cloud_endpoint or self.AKOSHA_DEFAULT_URL
        batch_size = kwargs.get("batch_size", DEFAULT_BATCH_SIZE)
        incremental = kwargs.get("incremental", True)

        logger.info(f"Starting HTTP sync to Akosha: {akosha_url}")

        # Track sync statistics
        stats = {
            "memories_uploaded": 0,
            "reflections_uploaded": 0,
            "entities_uploaded": 0,
            "relationships_uploaded": 0,
            "bytes_transferred": 0,
            "errors": [],
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self.config.upload_timeout_seconds,
                    write=self.config.upload_timeout_seconds,
                    pool=10.0,
                )
            ) as client:
                # Step 1: Sync conversations (memories)
                memories_result = await self._sync_conversations(
                    client=client,
                    akosha_url=akosha_url,
                    batch_size=batch_size,
                    incremental=incremental,
                )
                stats["memories_uploaded"] = memories_result["count"]
                stats["bytes_transferred"] += memories_result["bytes"]
                stats["errors"].extend(memories_result.get("errors", []))

                # Step 2: Sync reflections if enabled
                if upload_reflections:
                    reflections_result = await self._sync_reflections(
                        client=client,
                        akosha_url=akosha_url,
                        batch_size=batch_size,
                        incremental=incremental,
                    )
                    stats["reflections_uploaded"] = reflections_result["count"]
                    stats["bytes_transferred"] += reflections_result["bytes"]
                    stats["errors"].extend(reflections_result.get("errors", []))

                # Step 3: Sync knowledge graph if enabled
                if upload_knowledge_graph:
                    kg_result = await self._sync_knowledge_graph(
                        client=client,
                        akosha_url=akosha_url,
                        batch_size=batch_size,
                        incremental=incremental,
                    )
                    stats["entities_uploaded"] = kg_result["entities_count"]
                    stats["relationships_uploaded"] = kg_result["relationships_count"]
                    stats["bytes_transferred"] += kg_result["bytes"]
                    stats["errors"].extend(kg_result.get("errors", []))

            # Update sync state on success
            current_time = datetime.now(UTC).isoformat()
            self._last_sync_timestamp["last_sync"] = current_time
            self._save_sync_state()

            duration = time.monotonic() - start_time

            logger.info(
                f"HTTP sync completed: {stats['memories_uploaded']} memories, "
                f"{stats['reflections_uploaded']} reflections, "
                f"{stats['entities_uploaded']} entities, "
                f"{stats['relationships_uploaded']} relationships, "
                f"{stats['bytes_transferred']} bytes in {duration:.2f}s"
            )

            return {
                "method": "http",
                "success": True,
                "memories_uploaded": stats["memories_uploaded"],
                "reflections_uploaded": stats["reflections_uploaded"],
                "entities_uploaded": stats["entities_uploaded"],
                "relationships_uploaded": stats["relationships_uploaded"],
                "bytes_transferred": stats["bytes_transferred"],
                "duration_seconds": duration,
                "errors": stats["errors"] if stats["errors"] else None,
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP sync failed with status {e.response.status_code}: {e}")
            raise HTTPSyncError(
                message=f"Akosha HTTP error {e.response.status_code}: {e}",
                method="http",
                original=e,
            ) from e
        except httpx.RequestError as e:
            logger.error(f"HTTP sync request failed: {e}")
            raise HTTPSyncError(
                message=f"Akosha HTTP request failed: {e}",
                method="http",
                original=e,
            ) from e
        except Exception as e:
            logger.error(f"HTTP sync failed: {e}")
            raise HTTPSyncError(
                message=f"Akosha HTTP sync failed: {e}",
                method="http",
                original=e,
            ) from e

    async def _sync_conversations(
        self,
        client: httpx.AsyncClient,
        akosha_url: str,
        batch_size: int,
        incremental: bool,
    ) -> dict[str, Any]:
        """Sync conversations from DuckDB to Akosha.

        Args:
            client: HTTP client instance
            akosha_url: Akosha MCP endpoint URL
            batch_size: Number of records per batch
            incremental: Only sync records modified since last sync

        Returns:
            Dict with count, bytes, and errors
        """
        conversations = await self._fetch_conversations(
            incremental=incremental, batch_size=batch_size
        )

        if not conversations:
            logger.debug("No conversations to sync")
            return {"count": 0, "bytes": 0, "errors": []}

        # Convert to Akosha format
        memories = [self._serialize_conversation(conv) for conv in conversations]

        # Batch upload
        result = await self._batch_upload_memories(
            client=client,
            akosha_url=akosha_url,
            memories=memories,
            batch_size=batch_size,
        )

        return result

    async def _fetch_conversations(
        self,
        incremental: bool,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        """Fetch conversations from DuckDB.

        Args:
            incremental: Only fetch records modified since last sync
            batch_size: Maximum number of records to fetch

        Returns:
            List of conversation dictionaries
        """
        try:
            import duckdb
        except ImportError:
            return []

        if not self.reflection_db_path.exists():
            logger.debug(f"Reflection database not found: {self.reflection_db_path}")
            return []

        try:
            conn = duckdb.connect(str(self.reflection_db_path), read_only=True)

            # Build query with optional incremental filter
            where_clause = ""
            params: list[Any] = []

            if incremental and "conversations" in self._last_sync_timestamp:
                where_clause = "WHERE updated_at > ? OR timestamp > ?"
                last_sync = self._last_sync_timestamp["conversations"]
                params = [last_sync, last_sync]

            query = f"""
                SELECT
                    id, content, embedding, category, subcategory,
                    importance_score, memory_tier, access_count, last_accessed,
                    project, namespace, timestamp, session_id, user_id,
                    searchable_content, reasoning
                FROM conversations_v2
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params.append(batch_size * 10)  # Allow larger fetch for batching

            results = conn.execute(query, params).fetchall()
            conn.close()

            conversations = []
            for row in results:
                conversations.append(
                    {
                        "id": row[0],
                        "content": row[1],
                        "embedding": list(row[2]) if row[2] else None,
                        "category": row[3],
                        "subcategory": row[4],
                        "importance_score": row[5],
                        "memory_tier": row[6],
                        "access_count": row[7],
                        "last_accessed": row[8],
                        "project": row[9],
                        "namespace": row[10],
                        "timestamp": row[11],
                        "session_id": row[12],
                        "user_id": row[13],
                        "searchable_content": row[14],
                        "reasoning": row[15],
                    }
                )

            return conversations

        except Exception as e:
            logger.error(f"Failed to fetch conversations: {e}")
            return []

    def _serialize_conversation(self, conv: dict[str, Any]) -> dict[str, Any]:
        """Serialize a conversation for Akosha ingestion.

        Args:
            conv: Conversation dictionary from DuckDB

        Returns:
            Serialized memory dict for Akosha batch_store_memories
        """
        # Build rich text content with metadata
        text_parts = [conv.get("content", "")]

        if conv.get("reasoning"):
            text_parts.append(f"Reasoning: {conv['reasoning']}")

        text = "\n\n".join(filter(None, text_parts))

        # Build metadata
        metadata = {
            "source": self.config.system_id_resolved,
            "original_id": conv["id"],
            "type": "conversation",
            "category": conv.get("category", "context"),
            "subcategory": conv.get("subcategory"),
            "importance_score": conv.get("importance_score", 0.5),
            "memory_tier": conv.get("memory_tier", "long_term"),
            "project": conv.get("project"),
            "namespace": conv.get("namespace", "default"),
            "session_id": conv.get("session_id"),
            "user_id": conv.get("user_id", "default"),
            "created_at": conv.get("timestamp"),
            "ingestion_method": "http_push",
        }

        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return {
            "memory_id": conv["id"],
            "text": text,
            "embedding": conv.get("embedding"),
            "metadata": metadata,
        }

    async def _sync_reflections(
        self,
        client: httpx.AsyncClient,
        akosha_url: str,
        batch_size: int,
        incremental: bool,
    ) -> dict[str, Any]:
        """Sync reflections from DuckDB to Akosha.

        Args:
            client: HTTP client instance
            akosha_url: Akosha MCP endpoint URL
            batch_size: Number of records per batch
            incremental: Only sync records modified since last sync

        Returns:
            Dict with count, bytes, and errors
        """
        reflections = await self._fetch_reflections(
            incremental=incremental, batch_size=batch_size
        )

        if not reflections:
            logger.debug("No reflections to sync")
            return {"count": 0, "bytes": 0, "errors": []}

        # Upload reflections one at a time (no batch endpoint for reflections)
        uploaded = 0
        total_bytes = 0
        errors: list[dict[str, Any]] = []

        for reflection in reflections:
            try:
                serialized = self._serialize_reflection(reflection)
                result = await self._call_mcp_tool(
                    client=client,
                    akosha_url=akosha_url,
                    tool_name="store_reflection",
                    arguments=serialized,
                )

                if result.get("status") == "stored":
                    uploaded += 1
                    total_bytes += len(json.dumps(serialized))
                else:
                    errors.append(
                        {
                            "id": reflection["id"],
                            "error": result.get("error", "Unknown error"),
                        }
                    )

            except Exception as e:
                errors.append({"id": reflection["id"], "error": str(e)})

        return {"count": uploaded, "bytes": total_bytes, "errors": errors}

    async def _fetch_reflections(
        self,
        incremental: bool,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        """Fetch reflections from DuckDB.

        Args:
            incremental: Only fetch records modified since last sync
            batch_size: Maximum number of records to fetch

        Returns:
            List of reflection dictionaries
        """
        try:
            import duckdb
        except ImportError:
            return []

        if not self.reflection_db_path.exists():
            return []

        try:
            conn = duckdb.connect(str(self.reflection_db_path), read_only=True)

            where_clause = ""
            params: list[Any] = []

            if incremental and "reflections" in self._last_sync_timestamp:
                where_clause = "WHERE timestamp > ?"
                params = [self._last_sync_timestamp["reflections"]]

            query = f"""
                SELECT
                    id, content, embedding, category, importance_score,
                    memory_tier, tags, related_entities, timestamp,
                    project, namespace, access_count, last_accessed
                FROM reflections_v2
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params.append(batch_size * 5)

            results = conn.execute(query, params).fetchall()
            conn.close()

            reflections = []
            for row in results:
                reflections.append(
                    {
                        "id": row[0],
                        "content": row[1],
                        "embedding": list(row[2]) if row[2] else None,
                        "category": row[3],
                        "importance_score": row[4],
                        "memory_tier": row[5],
                        "tags": list(row[6]) if row[6] else [],
                        "related_entities": list(row[7]) if row[7] else [],
                        "timestamp": row[8],
                        "project": row[9],
                        "namespace": row[10],
                        "access_count": row[11],
                        "last_accessed": row[12],
                    }
                )

            return reflections

        except Exception as e:
            logger.error(f"Failed to fetch reflections: {e}")
            return []

    def _serialize_reflection(self, reflection: dict[str, Any]) -> dict[str, Any]:
        """Serialize a reflection for Akosha ingestion.

        Args:
            reflection: Reflection dictionary from DuckDB

        Returns:
            Serialized dict for store_reflection MCP tool
        """
        return {
            "reflection_id": reflection["id"],
            "content": reflection.get("content", ""),
            "embedding": reflection.get("embedding"),
            "metadata": {
                "source": self.config.system_id_resolved,
                "original_id": reflection["id"],
                "type": "reflection",
                "category": reflection.get("category", "context"),
                "importance_score": reflection.get("importance_score", 0.5),
                "memory_tier": reflection.get("memory_tier", "long_term"),
                "tags": reflection.get("tags", []),
                "related_entities": reflection.get("related_entities", []),
                "project": reflection.get("project"),
                "namespace": reflection.get("namespace", "default"),
                "created_at": reflection.get("timestamp"),
                "ingestion_method": "http_push",
            },
        }

    async def _sync_knowledge_graph(
        self,
        client: httpx.AsyncClient,
        akosha_url: str,
        batch_size: int,
        incremental: bool,
    ) -> dict[str, Any]:
        """Sync knowledge graph entities and relationships to Akosha.

        Args:
            client: HTTP client instance
            akosha_url: Akosha MCP endpoint URL
            batch_size: Number of records per batch
            incremental: Only sync records modified since last sync

        Returns:
            Dict with entities_count, relationships_count, bytes, and errors
        """
        # Sync entities first
        entities = await self._fetch_entities(incremental=incremental, batch_size=batch_size)
        entities_uploaded = 0
        entities_bytes = 0
        errors: list[dict[str, Any]] = []

        for entity in entities:
            try:
                serialized = self._serialize_entity(entity)
                result = await self._call_mcp_tool(
                    client=client,
                    akosha_url=akosha_url,
                    tool_name="create_entity",
                    arguments=serialized,
                )

                if result.get("id"):
                    entities_uploaded += 1
                    entities_bytes += len(json.dumps(serialized))
                else:
                    errors.append(
                        {
                            "type": "entity",
                            "id": entity["id"],
                            "error": result.get("error", "Unknown error"),
                        }
                    )

            except Exception as e:
                errors.append({"type": "entity", "id": entity["id"], "error": str(e)})

        # Sync relationships
        relationships = await self._fetch_relationships(
            incremental=incremental, batch_size=batch_size
        )
        relationships_uploaded = 0
        relationships_bytes = 0

        for rel in relationships:
            try:
                serialized = self._serialize_relationship(rel)
                result = await self._call_mcp_tool(
                    client=client,
                    akosha_url=akosha_url,
                    tool_name="create_relation",
                    arguments=serialized,
                )

                if result.get("id"):
                    relationships_uploaded += 1
                    relationships_bytes += len(json.dumps(serialized))
                else:
                    errors.append(
                        {
                            "type": "relationship",
                            "id": rel["id"],
                            "error": result.get("error", "Unknown error"),
                        }
                    )

            except Exception as e:
                errors.append({"type": "relationship", "id": rel["id"], "error": str(e)})

        return {
            "entities_count": entities_uploaded,
            "relationships_count": relationships_uploaded,
            "bytes": entities_bytes + relationships_bytes,
            "errors": errors,
        }

    async def _fetch_entities(
        self,
        incremental: bool,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        """Fetch entities from knowledge graph DuckDB.

        Args:
            incremental: Only fetch records modified since last sync
            batch_size: Maximum number of records to fetch

        Returns:
            List of entity dictionaries
        """
        try:
            import duckdb
        except ImportError:
            return []

        if not self.knowledge_graph_db_path.exists():
            return []

        try:
            conn = duckdb.connect(str(self.knowledge_graph_db_path), read_only=True)

            where_clause = ""
            params: list[Any] = []

            if incremental and "entities" in self._last_sync_timestamp:
                where_clause = "WHERE updated_at > ?"
                params = [self._last_sync_timestamp["entities"]]

            query = f"""
                SELECT
                    id, name, entity_type, observations, properties,
                    created_at, updated_at, metadata, embedding
                FROM kg_entities
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT ?
            """
            params.append(batch_size * 5)

            results = conn.execute(query, params).fetchall()
            conn.close()

            entities = []
            for row in results:
                entities.append(
                    {
                        "id": row[0],
                        "name": row[1],
                        "entity_type": row[2],
                        "observations": list(row[3]) if row[3] else [],
                        "properties": json.loads(row[4]) if row[4] else {},
                        "created_at": row[5],
                        "updated_at": row[6],
                        "metadata": json.loads(row[7]) if row[7] else {},
                        "embedding": list(row[8]) if row[8] else None,
                    }
                )

            return entities

        except Exception as e:
            logger.error(f"Failed to fetch entities: {e}")
            return []

    async def _fetch_relationships(
        self,
        incremental: bool,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        """Fetch relationships from knowledge graph DuckDB.

        Args:
            incremental: Only fetch records modified since last sync
            batch_size: Maximum number of records to fetch

        Returns:
            List of relationship dictionaries
        """
        try:
            import duckdb
        except ImportError:
            return []

        if not self.knowledge_graph_db_path.exists():
            return []

        try:
            conn = duckdb.connect(str(self.knowledge_graph_db_path), read_only=True)

            where_clause = ""
            params: list[Any] = []

            if incremental and "relationships" in self._last_sync_timestamp:
                where_clause = "WHERE updated_at > ?"
                params = [self._last_sync_timestamp["relationships"]]

            query = f"""
                SELECT
                    id, from_entity, to_entity, relation_type,
                    properties, created_at, updated_at, metadata
                FROM kg_relationships
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT ?
            """
            params.append(batch_size * 5)

            results = conn.execute(query, params).fetchall()
            conn.close()

            relationships = []
            for row in results:
                relationships.append(
                    {
                        "id": row[0],
                        "from_entity": row[1],
                        "to_entity": row[2],
                        "relation_type": row[3],
                        "properties": json.loads(row[4]) if row[4] else {},
                        "created_at": row[5],
                        "updated_at": row[6],
                        "metadata": json.loads(row[7]) if row[7] else {},
                    }
                )

            return relationships

        except Exception as e:
            logger.error(f"Failed to fetch relationships: {e}")
            return []

    def _serialize_entity(self, entity: dict[str, Any]) -> dict[str, Any]:
        """Serialize an entity for Akosha create_entity tool.

        Args:
            entity: Entity dictionary from DuckDB

        Returns:
            Serialized dict for create_entity MCP tool
        """
        return {
            "name": entity["name"],
            "entity_type": entity["entity_type"],
            "observations": entity.get("observations", []),
            "properties": {
                **entity.get("properties", {}),
                "source_system": self.config.system_id_resolved,
                "original_id": entity["id"],
                "created_at": entity.get("created_at"),
                "ingestion_method": "http_push",
            },
            "metadata": entity.get("metadata", {}),
        }

    def _serialize_relationship(self, rel: dict[str, Any]) -> dict[str, Any]:
        """Serialize a relationship for Akosha create_relation tool.

        Args:
            rel: Relationship dictionary from DuckDB

        Returns:
            Serialized dict for create_relation MCP tool
        """
        return {
            "from_entity": rel["from_entity"],
            "to_entity": rel["to_entity"],
            "relation_type": rel["relation_type"],
            "properties": {
                **rel.get("properties", {}),
                "source_system": self.config.system_id_resolved,
                "original_id": rel["id"],
                "created_at": rel.get("created_at"),
                "ingestion_method": "http_push",
            },
            "metadata": rel.get("metadata", {}),
        }

    async def _batch_upload_memories(
        self,
        client: httpx.AsyncClient,
        akosha_url: str,
        memories: list[dict[str, Any]],
        batch_size: int,
    ) -> dict[str, Any]:
        """Upload memories in batches to Akosha.

        Args:
            client: HTTP client instance
            akosha_url: Akosha MCP endpoint URL
            memories: List of serialized memories
            batch_size: Number of memories per batch

        Returns:
            Dict with count, bytes, and errors
        """
        total_uploaded = 0
        total_bytes = 0
        all_errors: list[dict[str, Any]] = []

        # Process in batches
        for i in range(0, len(memories), batch_size):
            batch = memories[i : i + batch_size]
            batch_json = json.dumps(batch)
            batch_bytes = len(batch_json)

            # Retry logic with exponential backoff
            for attempt in range(MAX_RETRIES):
                try:
                    result = await self._call_mcp_tool(
                        client=client,
                        akosha_url=akosha_url,
                        tool_name="batch_store_memories",
                        arguments={"memories": batch},
                    )

                    if result.get("status") in ("completed", "partial"):
                        total_uploaded += result.get("stored", 0)
                        total_bytes += batch_bytes

                        # Collect errors from partial success
                        if result.get("errors"):
                            all_errors.extend(result["errors"])
                        break

                    # Complete failure
                    all_errors.append(
                        {
                            "batch": i // batch_size,
                            "error": result.get("error", "Unknown error"),
                        }
                    )
                    break

                except httpx.HTTPStatusError as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = BASE_BACKOFF_DELAY * (2**attempt)
                        logger.warning(
                            f"Batch upload attempt {attempt + 1} failed, "
                            f"retrying in {delay}s: {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        all_errors.append(
                            {
                                "batch": i // batch_size,
                                "error": f"HTTP {e.response.status_code}: {e}",
                            }
                        )

                except Exception as e:
                    all_errors.append(
                        {
                            "batch": i // batch_size,
                            "error": str(e),
                        }
                    )
                    break

        return {"count": total_uploaded, "bytes": total_bytes, "errors": all_errors}

    async def _call_mcp_tool(
        self,
        client: httpx.AsyncClient,
        akosha_url: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call an MCP tool on Akosha server.

        Args:
            client: HTTP client instance
            akosha_url: Akosha MCP endpoint URL
            tool_name: Name of the MCP tool to call
            arguments: Tool arguments

        Returns:
            Tool result dictionary

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.RequestError: On request failures
        """
        # MCP protocol format for tools/call
        payload = {
            "jsonrpc": "2.0",
            "id": hashlib.md5(f"{tool_name}_{time.time()}".encode()).hexdigest(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        # Retry logic
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.post(
                    f"{akosha_url}/mcp/v1",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

                result = response.json()

                # Extract result from MCP response
                if "result" in result:
                    return result["result"]
                if "error" in result:
                    return {"status": "failed", "error": result["error"]}

                return result

            except httpx.HTTPStatusError:
                if attempt >= MAX_RETRIES - 1:
                    raise
                delay = BASE_BACKOFF_DELAY * (2**attempt)
                await asyncio.sleep(delay)

        return {"status": "failed", "error": "Max retries exceeded"}

    def _check_akosha_reachable(self) -> bool:
        """Check if Akosha server is reachable (non-blocking).

        Returns:
            True if reachable, False otherwise
        """
        # Quick check with 1s timeout
        try:
            url = self.config.cloud_endpoint or self.AKOSHA_DEFAULT_URL

            # Use synchronous check with timeout
            response = httpx.get(f"{url}/status", timeout=1.0)
            return response.status_code < 500

        except Exception:
            return False


class HybridAkoshaSync:
    """Hybrid sync orchestrator with automatic fallback.

    Tries cloud sync first (fastest), falls back to HTTP sync if cloud
    is unavailable. Uses protocol-based design for extensibility.

    Example:
        >>> config = AkoshaSyncConfig.from_settings(settings)
        >>> hybrid = HybridAkoshaSync(config)
        >>> result = await hybrid.sync_memories()
        >>> print(result['method'])
        'cloud'  # or 'http' if cloud failed
    """

    def __init__(self, config: AkoshaSyncConfig) -> None:
        """Initialize hybrid sync orchestrator.

        Args:
            config: Akosha sync configuration
        """
        self.config = config

        # Initialize sync methods in priority order
        self.methods: list[SyncMethod] = [
            CloudSyncMethod(config),
            HttpSyncMethod(config),
        ]

        logger.info(
            f"HybridAkoshaSync initialized: {len(self.methods)} methods available"
        )

    async def sync_memories(
        self,
        force_method: Literal["auto", "cloud", "http"] = "auto",
        upload_reflections: bool = True,
        upload_knowledge_graph: bool = True,
    ) -> dict[str, Any]:
        """Sync memories using available methods with automatic fallback.

        Args:
            force_method: Force specific method ("auto", "cloud", "http")
            upload_reflections: Whether to upload reflection database
            upload_knowledge_graph: Whether to upload knowledge graph database

        Returns:
            Sync result dictionary with method, success status, and metadata

        Raises:
            HybridSyncError: If all sync methods fail

        Example:
            >>> result = await hybrid.sync_memories(force_method="auto")
            >>> print(result['method'])
            'cloud'

            >>> result = await hybrid.sync_memories(force_method="http")
            >>> print(result['method'])
            'http'
        """
        # If method forced, use only that method
        if force_method != "auto":
            method = self._get_method(force_method)
            if method is None:
                raise HybridSyncError(
                    message=f"Requested method '{force_method}' not available",
                    method="hybrid",
                    errors=[{"method": force_method, "error": "Method not configured"}],
                )

            logger.info(f"Using forced method: {force_method}")
            return await method.sync(
                upload_reflections=upload_reflections,
                upload_knowledge_graph=upload_knowledge_graph,
            )

        # Auto mode: try each available method in priority order
        errors: list[dict[str, Any]] = []

        for method in self.methods:
            method_name = method.get_method_name()

            # Check if method is available
            if not method.is_available():
                logger.debug(f"Method '{method_name}' not available, skipping")
                continue

            # Try sync with this method
            try:
                logger.info(f"Trying sync method: {method_name}")

                result = await method.sync(
                    upload_reflections=upload_reflections,
                    upload_knowledge_graph=upload_knowledge_graph,
                )

                if result.get("success"):
                    logger.info(f"Sync successful using method: {method_name}")
                    return result

                # Method reported failure
                error_msg = result.get("error", "Unknown error")
                logger.warning(f"Method '{method_name}' reported failure: {error_msg}")
                errors.append({"method": method_name, "error": error_msg})

            except Exception as e:
                logger.warning(f"Method '{method_name}' raised exception: {e}")
                errors.append({"method": method_name, "error": str(e)})

                # Continue to next method
                continue

        # All methods failed
        logger.error(f"All sync methods failed: {errors}")
        raise HybridSyncError(
            message=f"All {len(self.methods)} sync methods failed",
            method="hybrid",
            errors=errors,
        )

    def _get_method(self, method_name: str) -> SyncMethod | None:
        """Get sync method by name.

        Args:
            method_name: Method name ("cloud" or "http")

        Returns:
            SyncMethod instance or None if not found
        """
        for method in self.methods:
            if method.get_method_name() == method_name:
                return method
        return None


__all__ = [
    "HybridAkoshaSync",
    "HttpSyncMethod",
]
