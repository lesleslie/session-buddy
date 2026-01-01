"""Redis-based session storage backend.

**DEPRECATED**: This module is deprecated and will be removed in v1.0.
Use ServerlessStorageAdapter instead, which provides Oneiric storage backends
and standardized lifecycle handling.

Migration:
    Old: RedisStorage(config)
    New: ServerlessStorageAdapter(config, backend="memory") for caching

This module provides a Redis implementation of the SessionStorage interface
for storing and retrieving session state in Redis with TTL support.
"""

from __future__ import annotations

import gzip
import json
import warnings
from typing import Any

from session_buddy.backends.base import SessionState, SessionStorage


class RedisStorage(SessionStorage):
    """Redis-based session storage.

    .. deprecated:: 0.9.3
        RedisStorage is deprecated. Use ``ServerlessStorageAdapter`` for Oneiric storage.

    """

    def __init__(self, config: dict[str, Any]) -> None:
        warnings.warn(
            "RedisStorage is deprecated and will be removed in v1.0. "
            "Use ServerlessStorageAdapter for Oneiric storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(config)
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 6379)
        self.db = config.get("db", 0)
        self.password = config.get("password")
        self.key_prefix = config.get("key_prefix", "session_mgmt:")
        self._redis = None

    async def _get_redis(self) -> Any:
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as redis

                self._redis = redis.Redis(  # type: ignore[assignment]
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    decode_responses=False,  # We handle encoding ourselves
                )
            except ImportError:
                msg = "Redis package not installed. Install with: pip install redis"
                raise ImportError(
                    msg,
                )
        return self._redis

    def _get_key(self, session_id: str) -> str:
        """Get Redis key for session."""
        return f"{self.key_prefix}session:{session_id}"

    def _get_index_key(self, index_type: str) -> str:
        """Get Redis key for index."""
        return f"{self.key_prefix}index:{index_type}"

    async def store_session(
        self,
        session_state: SessionState,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store session in Redis with optional TTL."""
        try:
            redis_client = await self._get_redis()

            # Serialize and compress session state
            serialized = json.dumps(session_state.to_dict())
            compressed = gzip.compress(serialized.encode("utf-8"))

            # Store session data
            key = self._get_key(session_state.session_id)
            await redis_client.set(key, compressed, ex=ttl_seconds)

            # Update indexes
            user_index_key = self._get_index_key(f"user:{session_state.user_id}")
            project_index_key = self._get_index_key(
                f"project:{session_state.project_id}",
            )

            await redis_client.sadd(user_index_key, session_state.session_id)
            await redis_client.sadd(project_index_key, session_state.session_id)

            # Set TTL on indexes if specified
            if ttl_seconds:
                await redis_client.expire(user_index_key, ttl_seconds)
                await redis_client.expire(project_index_key, ttl_seconds)

            return True

        except Exception as e:
            self.logger.exception(
                f"Failed to store session {session_state.session_id}: {e}",
            )
            return False

    async def retrieve_session(self, session_id: str) -> SessionState | None:
        """Retrieve session from Redis."""
        try:
            redis_client = await self._get_redis()
            key = self._get_key(session_id)

            compressed_data = await redis_client.get(key)
            if not compressed_data:
                return None

            # Decompress and deserialize
            serialized = gzip.decompress(compressed_data).decode("utf-8")
            session_data = json.loads(serialized)

            return SessionState.from_dict(session_data)

        except Exception as e:
            self.logger.exception(f"Failed to retrieve session {session_id}: {e}")
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete session from Redis."""
        try:
            redis_client = await self._get_redis()

            # Get session to find user/project for index cleanup
            session_state = await self.retrieve_session(session_id)

            # Delete session data
            key = self._get_key(session_id)
            deleted_result = await redis_client.delete(key)
            deleted = int(deleted_result) if deleted_result is not None else 0

            # Clean up indexes
            if session_state:
                user_index_key = self._get_index_key(f"user:{session_state.user_id}")
                project_index_key = self._get_index_key(
                    f"project:{session_state.project_id}",
                )

                await redis_client.srem(user_index_key, session_id)
                await redis_client.srem(project_index_key, session_id)

            return deleted > 0

        except Exception as e:
            self.logger.exception(f"Failed to delete session {session_id}: {e}")
            return False

    async def list_sessions(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[str]:
        """List sessions by user or project."""
        try:
            redis_client = await self._get_redis()

            if user_id:
                index_key = self._get_index_key(f"user:{user_id}")
                session_ids = await redis_client.smembers(index_key)
                return [
                    sid.decode("utf-8") if isinstance(sid, bytes) else sid
                    for sid in session_ids
                ]

            if project_id:
                index_key = self._get_index_key(f"project:{project_id}")
                session_ids = await redis_client.smembers(index_key)
                return [
                    sid.decode("utf-8") if isinstance(sid, bytes) else sid
                    for sid in session_ids
                ]

            # List all sessions (expensive operation)
            pattern = self._get_key("*")
            keys = await redis_client.keys(pattern)
            return [
                key.decode("utf-8").split(":")[-1]
                if isinstance(key, bytes)
                else key.split(":")[-1]
                for key in keys
            ]

        except Exception as e:
            self.logger.exception(f"Failed to list sessions: {e}")
            return []

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        # Redis automatically handles TTL expiration
        # This method could scan for orphaned index entries
        try:
            redis_client = await self._get_redis()
            index_keys = await self._get_index_keys(redis_client)

            cleaned = 0
            for index_key in index_keys:
                cleaned += await self._cleanup_index_key(redis_client, index_key)

            return cleaned

        except Exception as e:
            self.logger.exception(f"Failed to cleanup expired sessions: {e}")
            return 0

    async def _get_index_keys(self, redis_client: Any) -> list[str]:
        """Get all index keys for cleanup."""
        index_pattern = self._get_index_key("*")
        raw_keys = await redis_client.keys(index_pattern)

        return [
            key.decode("utf-8") if isinstance(key, bytes) else key for key in raw_keys
        ]

    async def _cleanup_index_key(self, redis_client: Any, index_key: str) -> int:
        """Clean up orphaned sessions from a single index key."""
        session_ids = await redis_client.smembers(index_key)
        cleaned = 0

        for session_id in session_ids:
            if await self._is_orphaned_session(redis_client, session_id):
                await redis_client.srem(index_key, session_id)
                cleaned += 1

        return cleaned

    async def _is_orphaned_session(self, redis_client: Any, session_id: Any) -> bool:
        """Check if a session ID refers to an orphaned session."""
        if isinstance(session_id, bytes):
            session_id = session_id.decode("utf-8")

        session_key = self._get_key(session_id)
        return not await redis_client.exists(session_key)

    async def is_available(self) -> bool:
        """Check if Redis is available."""
        try:
            redis_client = await self._get_redis()
            await redis_client.ping()
            return True
        except Exception:
            return False
