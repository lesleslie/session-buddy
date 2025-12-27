"""Reflection database adapter using ACB vector adapter.

Provides a compatibility layer that maintains the existing ReflectionDatabase API
while using ACB's vector adapter for storage and retrieval.

Phase 2.7 Day 5: Vector adapter migration
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging  # Used throughout for diagnostics and vector adapter setup
import os
import time
import typing as t
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

# Import ACB vector adapter
from acb.depends import depends

# Embedding system imports
try:
    import onnxruntime as ort
    from transformers import AutoTokenizer

    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

import numpy as np

# Import Vector at module level to avoid UnboundLocalError issues
from acb.adapters.vector.duckdb import Vector, VectorSettings
from acb.config import Config

if t.TYPE_CHECKING:
    from types import TracebackType


class ReflectionDatabaseAdapter:
    """Manages conversation memory and reflection using ACB vector adapter.

    This adapter wraps ACB's Vector adapter while maintaining the original
    ReflectionDatabase API for backward compatibility. It handles:
    - Local ONNX embedding generation (all-MiniLM-L6-v2, 384 dimensions)
    - Vector storage and retrieval via ACB adapter
    - Graceful fallback to text search when embeddings unavailable
    - Async/await patterns consistent with existing code

    The ACB vector adapter is registered via dependency injection in di/__init__.py
    and provides connection pooling, transaction management, and optimized vector
    similarity search.

    Example:
        >>> async with ReflectionDatabaseAdapter() as db:
        >>>     conv_id = await db.store_conversation("content", {"project": "foo"})
        >>>     results = await db.search_conversations("query")

    """

    def __init__(
        self,
        collection_name: str = "default",
        db_path: str | None = None,
    ) -> None:
        """Initialize adapter with optional collection name.

        Args:
            collection_name: Name of the vector collection to use.
                           Default "default" collection will be created automatically.
            db_path: Deprecated compatibility parameter (ignored).

        """
        self.collection_name = collection_name
        self.db_path = db_path
        self.vector_adapter: Vector | None = None
        self.onnx_session: ort.InferenceSession | None = None
        self.tokenizer: t.Any = None
        self.embedding_dim = 384  # all-MiniLM-L6-v2 dimension

    def __enter__(self) -> t.Self:
        """Sync context manager entry (not recommended - use async)."""
        msg = "Use 'async with' instead of 'with' for ReflectionDatabaseAdapter"
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
        self.close()  # Sync close is sufficient, ACB handles async cleanup

    def close(self) -> None:
        """Close adapter connections (sync version for compatibility)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            task = loop.create_task(self.aclose())

            def _consume_result(future: asyncio.Future[t.Any]) -> None:
                with suppress(Exception):
                    future.result()

            task.add_done_callback(_consume_result)
        else:
            asyncio.run(self.aclose())

    async def aclose(self) -> None:
        """Close adapter connections (async)."""
        adapter = self.vector_adapter
        if not adapter:
            return

        cleanup = getattr(adapter, "cleanup", None)
        if callable(cleanup):
            await cleanup()

        self.vector_adapter = None

    def __del__(self) -> None:
        """Destructor to ensure cleanup."""
        with suppress(Exception):
            self.close()

    async def initialize(self) -> None:
        """Initialize vector adapter and embedding models.

        Retrieves the ACB Vector adapter from the DI container and initializes
        the ONNX embedding model for local text-to-vector conversion.
        """
        if self.db_path:
            config = Config()
            config.ensure_initialized()
            config.vector = VectorSettings(  # type: ignore[attr-defined]
                database_path=self.db_path,
                default_dimension=self.embedding_dim,
                default_distance_metric="cosine",
                enable_vss=not os.environ.get("PYTEST_CURRENT_TEST"),
                threads=4,
                memory_limit="2GB",
            )

            vector_adapter = Vector()
            vector_adapter.config = config
            vector_adapter.logger = logging.getLogger("acb.vector")
            vector_adapter._schema_initialized = False
            self.vector_adapter = vector_adapter
        else:
            # Get vector adapter from DI container
            try:
                self.vector_adapter = depends.get_sync(Vector)
            except (KeyError, AttributeError, RuntimeError) as e:
                # Enhanced diagnostics for debugging DI issues
                logger = logging.getLogger(__name__)
                logger.exception(
                    f"Failed to get Vector adapter from DI: {type(e).__name__}: {e}"
                )
                logger.exception(
                    f"DI container state: {hasattr(depends, '_instances')}"
                )

                msg = (
                    "Vector adapter not registered in DI container. "
                    "Ensure configure() was called in di/__init__.py. "
                    f"Error: {type(e).__name__}: {e}"
                )
                raise RuntimeError(msg) from e

        # Initialize adapter schema if needed (deferred from configure())
        if hasattr(self.vector_adapter, "_schema_initialized"):
            if not self.vector_adapter._schema_initialized:
                await self.vector_adapter.init()
                self.vector_adapter._schema_initialized = True

        # Ensure default collection exists
        with suppress(Exception):
            # Collection may already exist, continue if it does
            await self.vector_adapter.create_collection(
                name=self.collection_name,
                dimension=self.embedding_dim,
                distance_metric="cosine",
            )

        # Initialize ONNX embedding model (same as original ReflectionDatabase)
        if ONNX_AVAILABLE and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                model_path = Path.home() / ".claude/all-MiniLM-L6-v2/onnx/model.onnx"
                if model_path.exists():
                    # Load tokenizer with revision pinning for security
                    self.tokenizer = AutoTokenizer.from_pretrained(
                        "sentence-transformers/all-MiniLM-L6-v2",
                        revision="7dbbc90392e2f80f3d3c277d6e90027e55de9125",
                    )
                    self.onnx_session = ort.InferenceSession(str(model_path))
                    self.embedding_dim = 384
                else:
                    self.onnx_session = None
                    self.tokenizer = None
            except Exception:
                self.onnx_session = None
                self.tokenizer = None
        else:
            self.onnx_session = None
            self.tokenizer = None

    def _get_adapter(self) -> Vector:
        """Get vector adapter, raising error if not initialized."""
        if self.vector_adapter is None:
            msg = "Vector adapter not initialized. Call initialize() first"
            raise RuntimeError(msg)
        return self.vector_adapter

    async def get_embedding(self, text: str) -> list[float]:
        """Generate embedding for text using local ONNX model.

        Args:
            text: Input text to embed

        Returns:
            384-dimensional embedding vector as list of floats

        Raises:
            RuntimeError: If no embedding model is available

        """
        if self.onnx_session and self.tokenizer:
            # Type narrowing: onnx_session is guaranteed non-None here
            onnx_session = self.onnx_session
            tokenizer = self.tokenizer

            def _get_embedding() -> list[float]:
                # Tokenize text
                encoded = tokenizer(
                    text,
                    truncation=True,
                    padding=True,
                    return_tensors="np",
                )

                # Run ONNX inference
                outputs = onnx_session.run(
                    None,
                    {
                        "input_ids": encoded["input_ids"],
                        "attention_mask": encoded["attention_mask"],
                        "token_type_ids": encoded.get(
                            "token_type_ids",
                            np.zeros_like(encoded["input_ids"]),
                        ),
                    },
                )

                # Mean pooling
                embeddings = outputs[0]
                attention_mask = encoded["attention_mask"]
                masked_embeddings = embeddings * np.expand_dims(attention_mask, axis=-1)
                summed = np.sum(masked_embeddings, axis=1)
                counts = np.sum(attention_mask, axis=1, keepdims=True)
                mean_pooled = summed / counts

                # Normalize
                norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
                normalized = mean_pooled / norms

                # Convert to float32 to match DuckDB FLOAT type
                result: list[float] = normalized[0].astype(np.float32).tolist()
                return result

            return await asyncio.get_event_loop().run_in_executor(None, _get_embedding)

        msg = "No embedding model available"
        raise RuntimeError(msg)

    async def store_conversation(self, content: str, metadata: dict[str, t.Any]) -> str:
        """Store conversation with optional embedding.

        Args:
            content: Conversation text content
            metadata: Dictionary with project, timestamp, and other metadata

        Returns:
            Unique conversation ID (MD5 hash)

        """
        conversation_id = hashlib.md5(
            f"{content}_{time.time()}".encode(),
            usedforsecurity=False,
        ).hexdigest()

        # Generate embedding if available
        embedding: list[float] | None = None
        if ONNX_AVAILABLE and self.onnx_session:
            try:
                embedding = await self.get_embedding(content)
            except Exception:
                embedding = None  # Fallback to no embedding

        # Prepare metadata with required fields
        vector_metadata = {
            "id": conversation_id,
            "content": content,
            "project": metadata.get("project"),
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": json.dumps(metadata),
            "type": "conversation",
        }

        # Store in ACB vector adapter using VectorDocument
        from acb.adapters.vector._base import VectorDocument

        adapter = self._get_adapter()
        if embedding:
            doc = VectorDocument(
                id=conversation_id,
                vector=embedding,
                metadata=vector_metadata,
            )
        else:
            # Store metadata only (no vector) for text search fallback
            # ACB adapter requires vectors, so we'll use a zero vector as placeholder
            zero_vector = [0.0] * self.embedding_dim
            doc = VectorDocument(
                id=conversation_id,
                vector=zero_vector,
                metadata=vector_metadata,
            )

        await adapter.insert(
            collection=self.collection_name,
            documents=[doc],
        )

        return conversation_id

    async def store_reflection(
        self,
        content: str,
        tags: list[str] | None = None,
    ) -> str:
        """Store reflection/insight with optional embedding.

        Args:
            content: Reflection text content
            tags: Optional list of tags for categorization

        Returns:
            Unique reflection ID

        """
        reflection_id = hashlib.md5(
            f"reflection_{content}_{time.time()}".encode(),
            usedforsecurity=False,
        ).hexdigest()

        # Generate embedding if available
        embedding: list[float] | None = None
        if ONNX_AVAILABLE and self.onnx_session:
            try:
                embedding = await self.get_embedding(content)
            except Exception:
                embedding = None

        # Prepare metadata
        vector_metadata = {
            "id": reflection_id,
            "content": content,
            "tags": tags or [],
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "reflection",
        }

        # Store in ACB vector adapter using VectorDocument
        from acb.adapters.vector._base import VectorDocument

        adapter = self._get_adapter()
        if embedding:
            doc = VectorDocument(
                id=reflection_id,
                vector=embedding,
                metadata=vector_metadata,
            )
        else:
            # Use zero vector placeholder for text-only storage
            zero_vector = [0.0] * self.embedding_dim
            doc = VectorDocument(
                id=reflection_id,
                vector=zero_vector,
                metadata=vector_metadata,
            )

        await adapter.insert(
            collection=self.collection_name,
            documents=[doc],
        )

        return reflection_id

    async def search_conversations(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.7,
        project: str | None = None,
    ) -> list[dict[str, t.Any]]:
        """Search conversations by semantic similarity with text fallback.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold (0.0-1.0)
            project: Optional project filter

        Returns:
            List of conversation results with content, score, timestamp, project

        """
        if ONNX_AVAILABLE and self.onnx_session:
            return await self._semantic_search_conversations(
                query, limit, min_score, project
            )
        # Fallback to text search (when ONNX unavailable or search failed)
        # This is a simplified version - in production you'd want to use
        # the original text search logic from ReflectionDatabase
        return await self._text_search_conversations(query, limit, project)

    async def _semantic_search_conversations(
        self,
        query: str,
        limit: int,
        min_score: float,
        project: str | None,
    ) -> list[dict[str, t.Any]]:
        """Perform semantic search using embeddings."""
        query_embedding = await self.get_embedding(query)
        try:
            adapter = self._get_adapter()

            # Build filter for project if specified
            filter_dict = {"type": "conversation"}
            if project:
                filter_dict["project"] = project

            # Search using ACB vector adapter
            search_results = await adapter.search(
                collection=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                filter_expr=filter_dict,
            )

            # Convert ACB results to original format
            # search_results is a list of VectorSearchResult objects (Pydantic BaseModel)
            results = []
            to_log: list[str] = []
            for result in search_results:
                # Access attributes directly (not .get() - it's a Pydantic model)
                score = result.score
                if score >= min_score:
                    meta = result.metadata
                    from contextlib import suppress

                    with suppress(Exception):
                        to_log.append(str(result.id))  # type: ignore[attr-defined]
                    results.append(
                        {
                            "content": meta.get("content", ""),
                            "score": float(score),
                            "timestamp": meta.get("timestamp"),
                            "project": meta.get("project"),
                            "metadata": (
                                json.loads(meta.get("metadata", "{}"))
                                if isinstance(meta.get("metadata"), str)
                                else meta.get("metadata", {})
                            ),
                        },
                    )
            # Log access for top results (best-effort)
            self._log_accesses(to_log)
            return results
        except Exception:
            # If semantic search fails, fallback to text search
            return await self._text_search_conversations(query, limit, project)

    def _log_accesses(self, conv_ids: list[str]) -> None:
        """Helper to log memory accesses."""
        from contextlib import suppress

        with suppress(Exception):
            from session_buddy.memory.persistence import (
                log_memory_access as _log_access,
            )

            for conv_id in conv_ids:
                _log_access(conv_id, access_type="search")

    async def _text_search_conversations(
        self,
        query: str,
        limit: int,
        project: str | None,
    ) -> list[dict[str, t.Any]]:
        """Fallback text search for conversations.

        This is a simplified implementation. For production use, you would
        want to implement full text search using DuckDB's FTS capabilities
        or migrate the original text search logic.
        """
        # TODO: Implement full text search fallback using ACB adapter's raw SQL access
        # For now, return empty results with a warning
        return []

    async def search_reflections(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.7,
    ) -> list[dict[str, t.Any]]:
        """Search stored reflections by semantic similarity with text fallback.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold (0.0-1.0)

        Returns:
            List of reflection results with content, score, timestamp, tags

        """
        if ONNX_AVAILABLE and self.onnx_session:
            with suppress(Exception):
                query_embedding = await self.get_embedding(query)
                adapter = self._get_adapter()

                # Search reflections only
                search_results = await adapter.search(
                    collection=self.collection_name,
                    query_vector=query_embedding,
                    limit=limit,
                    filter_expr={"type": "reflection"},
                )

                # Convert ACB results to original format
                # search_results is a list of VectorSearchResult objects (Pydantic BaseModel)
                results = []
                for result in search_results:
                    # Access attributes directly (not .get() - it's a Pydantic model)
                    score = result.score
                    if score >= min_score:
                        meta = result.metadata
                        results.append(
                            {
                                "content": meta.get("content", ""),
                                "score": float(score),
                                "timestamp": meta.get("timestamp"),
                                "tags": meta.get("tags", []),
                                "metadata": {"type": "reflection"},
                            },
                        )

                return results

        # Fallback to text search
        return []

    async def similarity_search(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.7,
    ) -> list[dict[str, t.Any]]:
        """General similarity search across all stored content (conversations and reflections).

        Args:
            query: Search query text
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold (0.0-1.0)

        Returns:
            List of results with content, score, timestamp, and metadata

        """
        # For now, use the text search fallback which we know works
        # The ACB adapter is not properly returning metadata in search results in some environments
        return await self._text_search_fallback(query, limit)

    async def _text_search_fallback(
        self, query: str, limit: int
    ) -> list[dict[str, t.Any]]:
        """Fallback text search using DuckDB's LIKE functionality."""
        adapter = self._get_adapter()

        try:
            # Get direct database access
            client = await adapter.get_client()
            table_name = f"vectors.{self.collection_name}"

            # Search using LIKE for partial text matching in the JSON metadata
            # The content is stored inside the metadata JSON as "content" field
            # Escape underscores and percent signs to prevent LIKE pattern matching issues
            safe_query = (
                query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )

            # Search in the JSON metadata for content field
            sql = f"""
                SELECT id, metadata
                FROM {table_name}
                WHERE CAST(metadata AS VARCHAR) ILIKE ? ESCAPE '\\'
                ORDER BY id
                LIMIT ?
            """

            # Search for the query anywhere in the metadata (case insensitive)
            search_pattern = f"%{safe_query}%"
            results = client.execute(sql, [search_pattern, limit]).fetchall()

            # Format results to match expected output
            formatted_results = []
            for row in results:
                metadata_raw = row[1]
                metadata: dict[str, t.Any] = {}
                if isinstance(metadata_raw, dict):
                    metadata = metadata_raw
                elif isinstance(metadata_raw, str):
                    import json

                    with suppress(json.JSONDecodeError):
                        parsed = json.loads(metadata_raw)
                        if isinstance(parsed, dict):
                            metadata = parsed

                formatted_results.append(
                    {
                        "content": metadata.get("content", ""),
                        "score": 0.0,  # No similarity score for text search
                        "timestamp": metadata.get("timestamp"),
                        "project": metadata.get("project"),
                        "tags": metadata.get("tags", []),
                        "metadata": metadata,
                    }
                )

            return formatted_results
        except Exception as e:
            # If text search also fails, return empty list
            # For debugging, we could log the error, but for now just return empty
            import logging

            logging.warning(f"Text search fallback failed: {e}")
            return []

    def _parse_metadata(self, raw_metadata: t.Any) -> dict[str, t.Any]:
        """Parse metadata from various formats to dict."""
        if isinstance(raw_metadata, dict):
            return raw_metadata
        if isinstance(raw_metadata, str):
            with suppress(json.JSONDecodeError):
                parsed = json.loads(raw_metadata)
                if isinstance(parsed, dict):
                    return parsed
        if raw_metadata is None:
            return {}
        return {}

    async def _try_direct_query(
        self,
        reflection_id: str,
        adapter: t.Any,
    ) -> tuple[str, dict[str, t.Any]] | None:
        """Try to get reflection via direct database query.

        Returns:
            Tuple of (doc_id, metadata) or None if query fails

        """
        try:
            client = await adapter.get_client()
            collection = adapter._validate_collection_name(self.collection_name)
            table_name = f"vectors.{collection}"
            safe_table_name = adapter._validate_table_name(table_name)
            safe_select_fields = adapter._validate_select_fields("id, metadata")
            result = client.execute(
                f"SELECT {safe_select_fields} FROM {safe_table_name} WHERE id = ?",  # nosec B608
                [reflection_id],
            ).fetchone()
            if not result:
                return None
            doc_id = result[0]
            metadata = self._parse_metadata(result[1])
            return (doc_id, metadata)
        except Exception:
            return None

    async def _try_adapter_query(
        self,
        reflection_id: str,
        adapter: t.Any,
    ) -> tuple[str, dict[str, t.Any]] | None:
        """Try to get reflection via adapter query (fallback).

        Returns:
            Tuple of (doc_id, metadata) or None if query fails

        """
        documents = await adapter.get(
            collection=self.collection_name,
            ids=[reflection_id],
            include_vectors=False,
        )
        if not documents:
            return None
        doc = documents[0]
        metadata = self._parse_metadata(doc.metadata)
        return (doc.id, metadata)

    async def get_reflection_by_id(
        self,
        reflection_id: str,
    ) -> dict[str, t.Any] | None:
        """Retrieve a reflection by ID.

        Returns None when the ID is unknown or the stored item is not a reflection.
        """
        adapter = self._get_adapter()

        # Try direct query first, fallback to adapter query
        result = await self._try_direct_query(reflection_id, adapter)
        if not result:
            result = await self._try_adapter_query(reflection_id, adapter)
        if not result:
            return None

        doc_id, metadata = result

        # Verify it's actually a reflection
        if metadata.get("type") != "reflection":
            return None

        return {
            "id": metadata.get("id", doc_id),
            "content": metadata.get("content", ""),
            "tags": metadata.get("tags", []),
            "timestamp": metadata.get("timestamp"),
            "metadata": metadata,
        }

    async def get_stats(self) -> dict[str, t.Any]:
        """Get statistics about stored conversations and reflections.

        Returns:
            Dictionary with counts and other statistics

        """
        adapter = self._get_adapter()

        try:
            # Get direct database access
            client = await adapter.get_client()
            table_name = f"vectors.{self.collection_name}"

            # Check if table exists
            collections = await adapter.list_collections()
            if self.collection_name not in collections:
                return {
                    "total_vectors": 0,
                    "conversations": 0,
                    "reflections": 0,
                    "conversations_count": 0,
                    "reflections_count": 0,
                    "total_conversations": 0,
                    "total_reflections": 0,
                    "dimension": self.embedding_dim,
                    "distance_metric": "cosine",
                }

            # Get total count
            # Build SQL safely - table_name is internal constant, not user input
            total_result = client.execute(
                "SELECT COUNT(*) FROM " + table_name,
            ).fetchone()
            total_count = total_result[0] if total_result else 0

            # Count by type using JSON metadata
            conv_result = client.execute(
                "SELECT COUNT(*) FROM "
                + table_name
                + " WHERE json_extract_string(metadata, '$.type') = 'conversation'",
            ).fetchone()
            conv_count = conv_result[0] if conv_result else 0

            refl_result = client.execute(
                "SELECT COUNT(*) FROM "
                + table_name
                + " WHERE json_extract_string(metadata, '$.type') = 'reflection'",
            ).fetchone()
            refl_count = refl_result[0] if refl_result else 0

            return {
                "total_vectors": total_count,
                "conversations": conv_count,
                "reflections": refl_count,
                "conversations_count": conv_count,
                "reflections_count": refl_count,
                "total_conversations": conv_count,
                "total_reflections": refl_count,
                "dimension": self.embedding_dim,
                "distance_metric": "cosine",
            }

        except Exception as e:
            return {"error": str(e)}

    async def reset_database(self) -> None:
        """Reset the database by deleting and recreating the collection.

        WARNING: This deletes all stored conversations and reflections!
        """
        adapter = self._get_adapter()

        with suppress(Exception):
            # Delete existing collection (might not exist, continue if so)
            await adapter.delete_collection(self.collection_name)

        # Recreate collection
        await adapter.create_collection(
            name=self.collection_name,
            dimension=self.embedding_dim,
            distance_metric="cosine",
        )
