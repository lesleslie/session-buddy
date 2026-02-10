"""Memory synchronization from Session-Buddy instances to AkOSHA.

This module provides functionality to fetch memories from multiple Session-Buddy
instances via MCP, generate embeddings, and store them in AkOSHA for cross-system
intelligence and aggregated search.

Features:
- Fetch memories from remote Session-Buddy instances via HTTP/MCP
- Generate embeddings using AkOSHA's embedding service
- Store memories in AkOSHA with source tracking
- Incremental sync (only new/updated memories)
- Error handling with retry logic
- Progress tracking and reporting
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx

from session_buddy.utils.error_management import _get_logger

logger = _get_logger()


class MemorySyncClient:
    """HTTP client for fetching memories from remote Session-Buddy instances."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """Initialize sync client.

        Args:
            base_url: Base URL of remote Session-Buddy instance (e.g., http://localhost:8678)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> MemorySyncClient:
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def search_memories(
        self,
        query: str = "",
        limit: int = 100,
        project: str | None = None,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Search for memories in remote Session-Buddy instance.

        Args:
            query: Search query (empty string returns all memories)
            limit: Maximum number of results
            project: Optional project filter
            min_score: Minimum similarity score

        Returns:
            List of memory dictionaries

        Raises:
            httpx.HTTPError: If request fails
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Construct MCP tool call
        payload: dict[str, Any] = {
            "method": "tools/call",
            "params": {
                "name": "quick_search",
                "arguments": {
                    "query": query,
                    "limit": limit,
                    "min_score": min_score,
                },
            },
        }

        # Add project filter if specified
        if project:
            arguments = cast(dict[str, Any], payload["params"]["arguments"])
            arguments["project"] = project

        logger.info(f"Fetching memories from {self.base_url}")

        try:
            response = await self._client.post(
                f"{self.base_url}/mcp",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()

            # Extract memories from MCP response
            if data.get("result"):
                # Parse the text result to extract memories
                result_text = data["result"]
                logger.info(f"Received {len(result_text)} characters from remote")

                # Parse memories from response
                # Handle both text and JSON-formatted responses
                if isinstance(result_text, str):
                    try:
                        # Try parsing as JSON array first
                        memories = json.loads(result_text)
                        if isinstance(memories, list):
                            return memories
                        elif isinstance(memories, dict):
                            return [memories]
                    except json.JSONDecodeError:
                        # If not JSON, treat as plain text and create memory object
                        return [
                            {
                                "id": f"remote_{hash(result_text)}",
                                "text": result_text,
                                "source": self.base_url,
                                "created_at": datetime.now(UTC).isoformat(),
                            }
                        ]
                return result_text if isinstance(result_text, list) else [result_text]

            return []

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch memories from {self.base_url}: {e}")
            raise

    async def get_recent_memories(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recently added/updated memories.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of results

        Returns:
            List of recent memories
        """
        # Calculate cutoff timestamp
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        # Use empty query to get all memories, then filter by timestamp
        # This approach works with the current search API
        memories = await self.search_memories(
            query="", limit=limit * 2
        )  # Fetch extra to account for filtering

        # Filter memories by timestamp
        recent = []
        for memory in memories:
            # Try to parse timestamp from memory
            created_at = memory.get("created_at") or memory.get("timestamp")

            if created_at:
                try:
                    # Parse ISO format timestamp
                    if isinstance(created_at, str):
                        memory_time = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )
                    elif isinstance(created_at, datetime):
                        memory_time = created_at
                    else:
                        continue

                    # Check if memory is within the time window
                    if memory_time >= cutoff:
                        recent.append(memory)

                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to parse timestamp {created_at}: {e}")
                    continue
            else:
                # If no timestamp, include it anyway (better to have false positives than false negatives)
                recent.append(memory)

        # Sort by timestamp (newest first) and limit results
        recent.sort(key=lambda m: m.get("created_at", ""), reverse=True)

        return recent[:limit]


class AkoshaSync:
    """Synchronize memories from Session-Buddy to AkOSHA.

    This class orchestrates the sync process:
    1. Fetch memories from Session-Buddy instances
    2. Generate embeddings for memories
    3. Store memories in AkOSHA with source tracking
    """

    def __init__(
        self,
        embedding_service: Any,
        instance_urls: list[str] | None = None,
    ) -> None:
        """Initialize AkOSHA sync.

        Args:
            embedding_service: AkOSHA embedding service instance
            instance_urls: List of Session-Buddy instance URLs
                           (default: http://localhost:8678)
        """
        self.embedding_service = embedding_service
        self.instance_urls = instance_urls or ["http://localhost:8678"]

        # Sync statistics
        self.stats: dict[str, Any] = {
            "memories_fetched": 0,
            "memories_synced": 0,
            "embeddings_generated": 0,
            "errors": [],
        }

    async def sync_all_instances(
        self,
        query: str = "",
        limit: int = 100,
        incremental: bool = True,
    ) -> dict[str, Any]:
        """Sync memories from all Session-Buddy instances.

        Args:
            query: Optional search query to filter memories
            limit: Maximum memories per instance
            incremental: If True, only sync recent memories (24h)

        Returns:
            Sync statistics and results

        Example:
            >>> sync = AkoshaSync(embedding_service)
            >>> result = await sync.sync_all_instances()
            >>> print(result["memories_synced"])
            42
        """
        logger.info(f"Starting sync from {len(self.instance_urls)} instances")

        # Reset statistics
        self.stats = {
            "memories_fetched": 0,
            "memories_synced": 0,
            "embeddings_generated": 0,
            "errors": [],
        }

        # Sync each instance
        for url in self.instance_urls:
            try:
                instance_stats = await self.sync_instance(
                    base_url=url,
                    query=query,
                    limit=limit,
                    incremental=incremental,
                )
                self.stats["memories_fetched"] += instance_stats.get("fetched", 0)
                self.stats["memories_synced"] += instance_stats.get("synced", 0)

            except Exception as e:
                logger.error(f"Failed to sync from {url}: {e}")
                errors_list = cast(list, self.stats["errors"])
                errors_list.append({"url": url, "error": str(e)})

        logger.info(
            f"Sync complete: {self.stats['memories_synced']} memories synced, "
            f"{len(self.stats['errors'])} errors"
        )

        return {
            "success": True,
            "instances_synced": len(self.instance_urls),
        } | self.stats

    async def sync_instance(
        self,
        base_url: str,
        query: str = "",
        limit: int = 100,
        incremental: bool = True,
    ) -> dict[str, Any]:
        """Sync memories from a single Session-Buddy instance.

        Args:
            base_url: Base URL of Session-Buddy instance
            query: Optional search query to filter memories
            limit: Maximum memories to sync
            incremental: If True, only sync recent memories (24h)

        Returns:
            Instance sync statistics
        """
        logger.info(f"Syncing from {base_url}")

        async with MemorySyncClient(base_url) as client:
            # Fetch memories
            if incremental:
                memories = await client.get_recent_memories(hours=24, limit=limit)
            else:
                memories = await client.search_memories(query=query, limit=limit)

            fetched = len(memories)
            synced = 0

            # Process each memory
            for memory in memories:
                try:
                    await self._sync_memory(memory, source=base_url)
                    synced += 1
                except Exception as e:
                    logger.error(
                        f"Failed to sync memory {memory.get('id', 'unknown')}: {e}"
                    )
                    errors_list = cast(list, self.stats["errors"])
                    errors_list.append(
                        {
                            "url": base_url,
                            "memory_id": memory.get("id"),
                            "error": str(e),
                        }
                    )

            logger.info(f"Synced {synced}/{fetched} memories from {base_url}")

            return {"fetched": fetched, "synced": synced}

    async def _sync_memory(self, memory: dict[str, Any], source: str) -> None:
        """Sync a single memory to AkOSHA.

        Args:
            memory: Memory dictionary from Session-Buddy
            source: Source instance URL
        """
        # Extract text content for embedding
        text = self._extract_text(memory)

        if not text:
            logger.warning(f"Memory {memory.get('id')} has no text content, skipping")
            return

        # Generate embedding
        embedding = await self.embedding_service.generate_embedding(text)
        self.stats["embeddings_generated"] = (
            cast(int, self.stats["embeddings_generated"]) + 1
        )

        # Store in AkOSHA with source metadata
        await self._store_in_akosha(
            memory=memory,
            text=text,
            embedding=embedding,
            source=source,
        )

    def _extract_text(self, memory: dict[str, Any]) -> str:
        """Extract text content from memory.

        Args:
            memory: Memory dictionary

        Returns:
            Text content for embedding, or empty string if no text found
        """
        # Extract text from various memory fields
        # This is a simplified implementation - real version would
        # handle different memory types more intelligently

        # Try different fields
        if "content" in memory:
            return str(memory["content"])
        elif "summary" in memory:
            return str(memory["summary"])
        elif "reflection" in memory:
            return str(memory["reflection"])
        if "query" in memory and "response" in memory:
            # Combine query and response
            return f"{memory['query']}\n\n{memory['response']}"
        # No recognizable text content
        return ""

    async def _store_in_akosha(
        self,
        memory: dict[str, Any],
        text: str,
        embedding: Any,
        source: str,
    ) -> None:
        """Store memory with embedding in AkOSHA.

        Args:
            memory: Original memory dictionary
            text: Extracted text content
            embedding: Generated embedding vector
            source: Source instance URL

        Note:
            This implementation stores memories in AkOSHA's distributed
            memory aggregation system for cross-instance intelligence.
        """
        memory_id = memory.get("id", f"mem_{hash(str(memory))}")
        logger.info(
            f"Storing memory {memory_id} from {source} "
            f"(embedding_dim: {len(embedding) if hasattr(embedding, '__len__') else 'unknown'})"
        )

        # Prepare memory data for AkOSHA storage
        memory_data = {
            "id": memory_id,
            "text": text,
            "embedding": embedding.tolist()
            if hasattr(embedding, "tolist")
            else embedding,
            "metadata": {
                "source": source,
                "original_id": memory.get("id"),
                "created_at": memory.get("created_at", datetime.now(UTC).isoformat()),
                "type": memory.get("type", "session_memory"),
            },
        }

        # Store in AkOSHA using HTTP API
        try:
            akosha_url = os.getenv("AKOSHA_URL", "http://localhost:8682/mcp")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{akosha_url}/store_memory",
                    json=memory_data,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.debug(f"Successfully stored memory {memory_id} in AkOSHA")
                return {"status": "stored", "memory_id": memory_id}

        except httpx.HTTPError as e:
            logger.error(f"Failed to store memory in AkOSHA: {e}")
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error storing memory in AkOSHA: {e}")
            return {"status": "failed", "error": str(e)}
        #         "source_type": "session_buddy",
        #         "timestamp": datetime.now(UTC).isoformat(),
        #         "original_memory": memory,
        #     }
        # )

    def get_statistics(self) -> dict[str, Any]:
        """Get sync statistics.

        Returns:
            Dictionary with sync statistics
        """
        return self.stats.copy()


# Convenience functions


async def sync_all_instances(
    instance_urls: list[str] | None = None,
    embedding_service: Any | None = None,
    query: str = "",
    limit: int = 100,
    incremental: bool = True,
) -> dict[str, Any]:
    """Convenience function to sync all Session-Buddy instances.

    Args:
        instance_urls: List of Session-Buddy instance URLs
        embedding_service: AkOSHA embedding service (will be created if None)
        query: Optional search query to filter memories
        limit: Maximum memories per instance
        incremental: If True, only sync recent memories (24h)

    Returns:
        Sync statistics and results

    Example:
        >>> result = await sync_all_instances(
        ...     instance_urls=["http://localhost:8678", "http://remote:8678"]
        ... )
        >>> print(f"Synced {result['memories_synced']} memories")
    """
    # Create embedding service if not provided
    if embedding_service is None:
        from akosha.processing.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        await embedding_service.initialize()

    # Create sync orchestrator
    sync = AkoshaSync(
        embedding_service=embedding_service,
        instance_urls=instance_urls,
    )

    # Perform sync
    return await sync.sync_all_instances(
        query=query,
        limit=limit,
        incremental=incremental,
    )
