"""IPFS storage backend for Session-Buddy distributed memory.

This module provides:
- Content-addressed storage via IPFS
- Deduplication of identical memories
- Distributed caching
- Cross-instance memory sharing
- Integration with Akosha analytics

Example:
    ```python
    from session_buddy.storage.ipfs import IPFSStorage

    # Create IPFS storage backend
    storage = IPFSStorage(
        gateway_url="https://ipfs.io/ipfs/",
        api_url="http://localhost:5001/api/v0",
    )

    # Store memory
    cid = await storage.store_memory(
        content="Agent execution result",
        metadata={"agent": "python-pro", "status": "completed"}
    )

    # Retrieve memory
    memory = await storage.retrieve_memory(cid)
    ```
"""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class IPFSStorage:
    """IPFS-based distributed storage for Session-Buddy.

    Features:
    - Content-addressed storage (CID-based)
    - Automatic deduplication
    - Distributed caching
    - Cross-pool sharing
    - Pin management for critical data

    Attributes:
        gateway_url: IPFS gateway URL for retrieval
        api_url: IPFS API URL for storage operations
        client: HTTP client for IPFS operations
        pin_enabled: Enable pinning of critical memories
    """

    def __init__(
        self,
        gateway_url: str = "https://ipfs.io/ipfs/",
        api_url: str = "http://localhost:5001/api/v0",
        pin_enabled: bool = True,
    ):
        """Initialize IPFS storage backend.

        Args:
            gateway_url: IPFS gateway URL (default: public gateway)
            api_url: IPFS API URL (default: local Kubo node)
            pin_enabled: Enable pinning of critical memories
        """
        self.gateway_url = gateway_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self.pin_enabled = pin_enabled

        # Async HTTP client
        self.client = httpx.AsyncClient(timeout=30.0)

        logger.info(
            f"IPFS storage initialized (gateway: {gateway_url}, "
            f"api: {api_url}, pinning: {pin_enabled})"
        )

    async def store_memory(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store memory in IPFS.

        Args:
            content: Memory content to store
            metadata: Optional metadata dict

        Returns:
            CID (Content Identifier) of stored memory

        Example:
            ```python
            cid = await storage.store_memory(
                content="Agent output data",
                metadata={"agent": "python-pro", "task": "analysis"}
            )
            print(f"Stored with CID: {cid}")
            ```
        """
        try:
            # Prepare memory data
            memory_data = {
                "content": content,
                "metadata": metadata or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Add to IPFS
            response = await self.client.post(
                f"{self.api_url}/add",
                files={"file": json.dumps(memory_data)},
            )

            if response.status_code != 200:
                raise Exception(f"IPFS add failed: {response.text}")

            result = response.json()
            cid = result["Hash"]

            # Pin if enabled
            if self.pin_enabled:
                await self._pin_cid(cid)

            logger.debug(f"Stored memory with CID: {cid}")
            return cid

        except Exception as e:
            logger.error(f"Failed to store memory in IPFS: {e}")
            raise

    async def retrieve_memory(self, cid: str) -> dict[str, Any]:
        """Retrieve memory from IPFS by CID.

        Args:
            cid: Content identifier

        Returns:
            Memory data dict with content and metadata

        Raises:
            Exception: If retrieval fails

        Example:
            ```python
            memory = await storage.retrieve_memory(
                "QmXxx..."
            )
            print(f"Content: {memory['content']}")
            print(f"Metadata: {memory['metadata']}")
            ```
        """
        try:
            # Retrieve from IPFS gateway
            response = await self.client.get(f"{self.gateway_url}/{cid}")

            if response.status_code != 200:
                raise Exception(f"IPFS retrieval failed: {response.text}")

            memory_data = response.json()

            logger.debug(f"Retrieved memory CID: {cid}")
            return memory_data

        except Exception as e:
            logger.error(f"Failed to retrieve memory {cid}: {e}")
            raise

    async def batch_store(
        self,
        memories: list[dict[str, Any]],
    ) -> list[str]:
        """Store multiple memories in batch.

        Args:
            memories: List of memory dicts with 'content' and 'metadata'

        Returns:
            List of CIDs

        Example:
            ```python
            cids = await storage.batch_store([
                {"content": "Memory 1", "metadata": {...}},
                {"content": "Memory 2", "metadata": {...}},
            ])
            ```
        """
        logger.info(f"Batch storing {len(memories)} memories")

        # Store in parallel
        tasks = [
            self.store_memory(m["content"], m.get("metadata"))
            for m in memories
        ]

        cids = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results
        successful_cids = [cid for cid in cids if isinstance(cid, str)]

        logger.info(
            f"Batch store complete: {len(successful_cids)}/{len(memories)} successful"
        )

        return successful_cids

    async def _pin_cid(self, cid: str) -> None:
        """Pin CID to prevent garbage collection.

        Args:
            cid: Content identifier to pin
        """
        try:
            response = await self.client.post(f"{self.api_url}/pin/add?arg={cid}")

            if response.status_code != 200:
                logger.warning(f"Failed to pin CID {cid}: {response.text}")
            else:
                logger.debug(f"Pinned CID: {cid}")

        except Exception as e:
            logger.warning(f"Failed to pin CID {cid}: {e}")

    async def unpin_cid(self, cid: str) -> None:
        """Unpin CID to allow garbage collection.

        Args:
            cid: Content identifier to unpin
        """
        try:
            response = await self.client.post(f"{self.api_url}/pin/rm?arg={cid}")

            if response.status_code != 200:
                logger.warning(f"Failed to unpin CID {cid}: {response.text}")
            else:
                logger.debug(f"Unpinned CID: {cid}")

        except Exception as e:
            logger.warning(f"Failed to unpin CID {cid}: {e}")

    async def get_stats(self) -> dict[str, Any]:
        """Get IPFS node statistics.

        Returns:
            Statistics dict with repo size, pins, etc.
        """
        try:
            # Get repo stats
            stats_response = await self.client.post(f"{self.api_url}/repo/stat")

            if stats_response.status_code == 200:
                stats = stats_response.json()
                return {
                    "status": "healthy",
                    "repo_size_bytes": stats.get("RepoSize", 0),
                    "storage_max": stats.get("StorageMax", 0),
                    "pin_count": stats.get("Pins", []).__len__(),
                }
            else:
                return {"status": "unhealthy", "error": "Failed to get stats"}

        except Exception as e:
            logger.error(f"Failed to get IPFS stats: {e}")
            return {"status": "error", "error": str(e)}

    async def close(self) -> None:
        """Close IPFS client connection."""
        await self.client.aclose()
        logger.info("IPFS storage connection closed")


class DistributedMemoryAggregator:
    """Aggregate and distribute memory across pools via IPFS.

    Features:
    - Collect memory from local pools
    - Store in distributed IPFS network
    - Sync with Akosha for analytics
    - Enable cross-pool memory search
    """

    def __init__(
        self,
        ipfs_storage: IPFSStorage,
        akosha_url: str | None = None,
    ):
        """Initialize distributed memory aggregator.

        Args:
            ipfs_storage: IPFS storage backend
            akosha_url: Optional Akosha analytics URL
        """
        self.ipfs_storage = ipfs_storage
        self.akosha_url = akosha_url

        # Memory aggregation cache
        self._aggregation_cache: dict[str, list[str]] = {}

        logger.info("Distributed memory aggregator initialized")

    async def aggregate_pool_memory(
        self,
        pool_id: str,
        memories: list[dict[str, Any]],
    ) -> list[str]:
        """Aggregate memories from a pool to IPFS.

        Args:
            pool_id: Pool identifier
            memories: List of memory dicts

        Returns:
            List of CIDs for stored memories

        Example:
            ```python
            # Collect from pool
            pool_memories = await pool.collect_memory()

            # Aggregate to IPFS
            cids = await aggregator.aggregate_pool_memory(
                pool_id="pool_abc",
                memories=pool_memories
            )
            ```
        """
        logger.info(f"Aggregating {len(memories)} memories from pool {pool_id}")

        # Prepare memory data
        memory_data = [
            {
                "content": m.get("content", ""),
                "metadata": {
                    **m.get("metadata", {}),
                    "pool_id": pool_id,
                    "aggregated_at": datetime.now(UTC).isoformat(),
                },
            }
            for m in memories
        ]

        # Store in IPFS
        cids = await self.ipfs_storage.batch_store(memory_data)

        # Cache CIDs for this pool
        self._aggregation_cache[pool_id] = cids

        # Sync with Akosha if configured
        if self.akosha_url:
            await self._sync_to_akosha(cids, pool_id)

        logger.info(f"Aggregated {len(cids)} memories from pool {pool_id}")

        return cids

    async def search_cross_pool(
        self,
        query: str,
        pools: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search memories across all pools.

        Args:
            query: Search query string
            pools: List of pool IDs to search (None = all pools)

        Returns:
            List of matching memory dicts

        Example:
            ```python
            results = await aggregator.search_cross_pool(
                query="authentication error",
                pools=["pool_abc", "pool_def"]
            )
            ```
        """
        logger.info(f"Searching cross-pool for: {query}")

        # This is a simplified implementation
        # In production, would use IPFS content routing or DHT

        # Search local aggregation cache
        all_cids = []
        if pools:
            for pool_id in pools:
                all_cids.extend(self._aggregation_cache.get(pool_id, []))
        else:
            for pool_cids in self._aggregation_cache.values():
                all_cids.extend(pool_cids)

        # Retrieve and filter memories
        results = []
        for cid in all_cids[:50]:  # Limit to 50 for performance
            try:
                memory = await self.ipfs_storage.retrieve_memory(cid)
                if query.lower() in memory.get("content", "").lower():
                    results.append(memory)
            except Exception as e:
                logger.warning(f"Failed to retrieve CID {cid}: {e}")

        logger.info(f"Found {len(results)} matching memories")
        return results

    async def _sync_to_akosha(
        self,
        cids: list[str],
        pool_id: str,
    ) -> None:
        """Sync aggregated memories to Akosha analytics.

        Args:
            cids: List of IPFS CIDs
            pool_id: Source pool ID
        """
        if not self.akosha_url:
            return

        try:
            # Prepare sync data
            sync_data = {
                "source": "session_buddy_ipfs",
                "pool_id": pool_id,
                "cids": cids,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Send to Akosha
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.akosha_url}/api/v1/memory/sync",
                    json=sync_data,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info(f"Synced {len(cids)} memories to Akosha")
                else:
                    logger.warning(
                        f"Akosha sync failed: {response.status_code}"
                    )

        except Exception as e:
            logger.warning(f"Failed to sync to Akosha: {e}")

    async def get_aggregation_stats(self) -> dict[str, Any]:
        """Get memory aggregation statistics.

        Returns:
            Statistics dict
        """
        total_memories = sum(len(cids) for cids in self._aggregation_cache.values())

        return {
            "total_pools": len(self._aggregation_cache),
            "total_memories": total_memories,
            "pools": {
                pool_id: len(cids)
                for pool_id, cids in self._aggregation_cache.items()
            },
        }


# ============================================================================
# Convenience Functions
# ============================================================================


async def create_ipfs_storage(
    gateway_url: str = "https://ipfs.io/ipfs/",
    api_url: str = "http://localhost:5001/api/v0",
) -> IPFSStorage:
    """Create IPFS storage backend.

    Args:
        gateway_url: IPFS gateway URL
        api_url: IPFS API URL

    Returns:
        IPFSStorage instance
    """
    return IPFSStorage(
        gateway_url=gateway_url,
        api_url=api_url,
    )


async def create_distributed_aggregator(
    ipfs_storage: IPFSStorage | None = None,
    akosha_url: str | None = None,
) -> DistributedMemoryAggregator:
    """Create distributed memory aggregator.

    Args:
        ipfs_storage: IPFS storage backend (created if None)
        akosha_url: Optional Akosha analytics URL

    Returns:
        DistributedMemoryAggregator instance
    """
    if ipfs_storage is None:
        ipfs_storage = await create_ipfs_storage()

    return DistributedMemoryAggregator(
        ipfs_storage=ipfs_storage,
        akosha_url=akosha_url,
    )
