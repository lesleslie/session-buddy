"""Serverless storage adapter bridge for session state persistence.

This module provides a bridge between the old SessionStorage protocol (used by
serverless_mode.py) and the Oneiric SessionStorageAdapter. This enables
serverless deployments to use Oneiric storage adapters while maintaining API
compatibility.

Architecture:
    Old: serverless_mode.py → SessionStorage protocol → legacy backends
    New: serverless_mode.py → ServerlessStorageAdapter → SessionStorageAdapter → Oneiric storage

Example:
    >>> from session_buddy.adapters import ServerlessStorageAdapter
    >>> storage = ServerlessStorageAdapter(backend="file")
    >>> await storage.store_session(session_state, ttl_seconds=3600)
    True

"""

from __future__ import annotations

import logging
import typing as t
from datetime import datetime, timedelta

from session_buddy.backends.base import SessionState, SessionStorage

if t.TYPE_CHECKING:
    from session_buddy.adapters.session_storage_adapter import (
        SessionStorageAdapter,
    )


class ServerlessStorageAdapter(SessionStorage):
    """Bridge adapter implementing SessionStorage protocol using SessionStorageAdapter.

    This adapter maintains backward compatibility with serverless_mode.py while
    using the Oneiric SessionStorageAdapter underneath.

    Attributes:
        backend: Storage backend type (file, memory)
        _storage: Internal SessionStorageAdapter instance
        _session_metadata: Cache for session metadata (TTL tracking)

    Example:
        >>> adapter = ServerlessStorageAdapter(backend="s3")
        >>> await adapter.store_session(session_state, ttl_seconds=3600)
        >>> state = await adapter.retrieve_session("session_123")

    """

    def __init__(self, config: dict[str, t.Any] | None = None, backend: str = "file"):
        """Initialize serverless storage adapter.

        Args:
            config: Legacy config dict (for compatibility, mostly ignored)
            backend: Storage backend type (s3, file, azure, gcs, memory)

        """
        super().__init__(config or {})
        self.backend = backend
        self._storage: SessionStorageAdapter | None = None
        self._session_metadata: dict[str, dict[str, t.Any]] = {}
        self.logger = logging.getLogger(f"serverless.storage.{backend}")

    async def _ensure_storage(self) -> SessionStorageAdapter:
        """Ensure storage adapter is initialized.

        Returns:
            Initialized SessionStorageAdapter instance

        """
        if self._storage is None:
            from session_buddy.adapters.session_storage_adapter import (
                SessionStorageAdapter,
            )

            self._storage = SessionStorageAdapter(backend=self.backend)

        return self._storage

    async def store_session(
        self,
        session_state: SessionState,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store session state with optional TTL.

        Args:
            session_state: Session state to store
            ttl_seconds: Time-to-live in seconds (for expiration tracking)

        Returns:
            True if successful, False otherwise

        Note:
            TTL is stored as metadata for cleanup purposes. Actual expiration
            depends on the storage backend's TTL support.

        """
        try:
            storage = await self._ensure_storage()

            # Convert SessionState to dict
            state_dict = session_state.to_dict()

            # Add TTL metadata if provided
            if ttl_seconds:
                expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
                state_dict["_ttl"] = {
                    "ttl_seconds": ttl_seconds,
                    "expires_at": expires_at.isoformat(),
                }

            # Store using SessionStorageAdapter
            await storage.store_session(session_state.session_id, state_dict)

            # Cache metadata for TTL tracking
            self._session_metadata[session_state.session_id] = {
                "user_id": session_state.user_id,
                "project_id": session_state.project_id,
                "created_at": session_state.created_at,
                "ttl_seconds": ttl_seconds,
                "expires_at": state_dict.get("_ttl", {}).get("expires_at"),
            }

            return True

        except Exception as e:
            self.logger.exception(
                f"Failed to store session {session_state.session_id}: {e}"
            )
            return False

    async def retrieve_session(self, session_id: str) -> SessionState | None:
        """Retrieve session state by ID.

        Args:
            session_id: Unique session identifier

        Returns:
            SessionState if found, None otherwise

        Note:
            Checks TTL expiration before returning session.

        """
        try:
            storage = await self._ensure_storage()

            # Load from SessionStorageAdapter
            state_dict = await storage.load_session(session_id)

            if not state_dict:
                return None

            # Check TTL expiration
            ttl_info = state_dict.get("_ttl", {})
            if ttl_info and "expires_at" in ttl_info:
                expires_at = datetime.fromisoformat(ttl_info["expires_at"])
                if datetime.now() > expires_at:
                    # Session expired, delete it
                    await self.delete_session(session_id)
                    return None

            # Remove TTL metadata before creating SessionState
            state_dict.pop("_ttl", None)
            state_dict.pop("_metadata", None)  # Remove storage metadata

            # Convert dict back to SessionState
            return SessionState.from_dict(state_dict)

        except Exception as e:
            self.logger.exception(f"Failed to retrieve session {session_id}: {e}")
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete session state.

        Args:
            session_id: Unique session identifier

        Returns:
            True if deleted, False if not found or error

        """
        try:
            storage = await self._ensure_storage()

            # Delete from storage
            success = await storage.delete_session(session_id)

            # Remove from metadata cache
            self._session_metadata.pop(session_id, None)

            return success

        except Exception as e:
            self.logger.exception(f"Failed to delete session {session_id}: {e}")
            return False

    async def list_sessions(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[str]:
        """List session IDs matching criteria.

        Args:
            user_id: Filter by user ID (optional)
            project_id: Filter by project ID (optional)

        Returns:
            List of session IDs

        Note:
            Current implementation returns sessions from metadata cache.
            Full implementation would require iterating through storage.

        """
        # Filter from metadata cache
        matching_sessions = []

        for session_id, metadata in self._session_metadata.items():
            if user_id and metadata.get("user_id") != user_id:
                continue
            if project_id and metadata.get("project_id") != project_id:
                continue

            # Check if expired
            expires_at_str = metadata.get("expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now() > expires_at:
                    continue

            matching_sessions.append(session_id)

        return matching_sessions

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions deleted

        Note:
            Iterates through metadata cache to find expired sessions.

        """
        deleted_count = 0
        expired_sessions = []

        # Find expired sessions
        for session_id, metadata in self._session_metadata.items():
            expires_at_str = metadata.get("expires_at")
            if not expires_at_str:
                continue

            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now() > expires_at:
                    expired_sessions.append(session_id)
            except ValueError:
                # Invalid timestamp, skip
                continue

        # Delete expired sessions
        for session_id in expired_sessions:
            try:
                success = await self.delete_session(session_id)
                if success:
                    deleted_count += 1
            except Exception as e:
                self.logger.warning(
                    f"Failed to delete expired session {session_id}: {e}"
                )

        if deleted_count > 0:
            self.logger.info(f"Cleaned up {deleted_count} expired sessions")

        return deleted_count

    async def is_available(self) -> bool:
        """Check if storage backend is available.

        Returns:
            True if storage is accessible, False otherwise

        """
        try:
            storage = await self._ensure_storage()

            # Test storage with a ping operation
            test_session_id = "_health_check_"
            test_state = {"test": True}

            # Try to store and retrieve
            await storage.store_session(test_session_id, test_state)
            result = await storage.load_session(test_session_id)

            # Cleanup test session
            await storage.delete_session(test_session_id)

            return result is not None

        except Exception as e:
            self.logger.warning(f"Storage backend unavailable: {e}")
            return False


def create_serverless_storage(
    backend: str = "file",
    config: dict[str, t.Any] | None = None,
) -> ServerlessStorageAdapter:
    """Factory function to create serverless storage adapter.

    Args:
        backend: Storage backend type (file, memory)
        config: Legacy config dict (for compatibility)

    Returns:
        Configured ServerlessStorageAdapter instance

    Example:
        >>> storage = create_serverless_storage("s3")
        >>> await storage.store_session(session_state)

    """
    return ServerlessStorageAdapter(config=config, backend=backend)


__all__ = [
    "ServerlessStorageAdapter",
    "create_serverless_storage",
]
