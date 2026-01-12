"""Session storage adapter facade for unified session state persistence.

This module provides a high-level interface for storing and retrieving session
state using Oneiric storage adapters as the backend. It abstracts away the
bucket-based API of the storage adapters and provides a session-centric interface.

The adapter supports the Oneiric storage backends registered in the storage registry.

Example:
    >>> from session_buddy.adapters import SessionStorageAdapter
    >>> storage = SessionStorageAdapter(backend="file")
    >>> await storage.store_session("session_123", {"status": "active"})
    >>> state = await storage.load_session("session_123")
    >>> print(state)
    {'status': 'active'}

"""

from __future__ import annotations

import json
import typing as t
from contextlib import suppress
from datetime import datetime

if t.TYPE_CHECKING:
    from session_buddy.adapters.storage_oneiric import StorageBaseOneiric

# Default bucket for session storage
DEFAULT_SESSION_BUCKET = "sessions"


class SessionStorageAdapter:
    """Unified storage adapter for session state persistence.

    This facade provides a simple, session-focused API on top of ACB storage
    adapters. It handles JSON serialization, path construction, and error
    handling automatically.

    Attributes:
        backend: Storage backend type ("s3", "file", "azure", "gcs", "memory")
        bucket: Bucket name for session storage (default: "sessions")

    Example:
        >>> storage = SessionStorageAdapter(backend="file")
        >>> await storage.store_session("abc123", {"status": "active"})
        >>> state = await storage.load_session("abc123")

    """

    def __init__(self, backend: str = "file", bucket: str = DEFAULT_SESSION_BUCKET):
        """Initialize session storage adapter.

        Args:
            backend: Storage backend type (s3, file, azure, gcs, memory)
            bucket: Bucket name for session storage (default: "sessions")

        Raises:
            ValueError: If backend is not supported

        """
        self.backend = backend
        self.bucket = bucket
        self._adapter: StorageBaseOneiric | None = None
        self._initialized = False

    async def _ensure_adapter(self) -> StorageBaseOneiric:
        """Ensure storage adapter is initialized.

        Returns:
            Initialized storage adapter instance

        Raises:
            ValueError: If adapter not registered

        """
        if self._adapter is None:
            from session_buddy.adapters.storage_registry import get_storage_adapter

            self._adapter = get_storage_adapter(self.backend)

        if not self._initialized:
            # Initialize buckets on first use
            await self._adapter.init()
            self._initialized = True

        return self._adapter

    def _get_session_path(self, session_id: str, filename: str = "state.json") -> str:
        """Construct storage path for session file.

        Args:
            session_id: Unique session identifier
            filename: Filename within session directory (default: state.json)

        Returns:
            Storage path string in format: session_id/filename

        Example:
            >>> adapter._get_session_path("abc123")
            'abc123/state.json'
            >>> adapter._get_session_path("abc123", "checkpoint_001.json")
            'abc123/checkpoint_001.json'

        """
        return f"{session_id}/{filename}"

    async def store_session(
        self,
        session_id: str,
        state: dict[str, t.Any],
        filename: str = "state.json",
    ) -> None:
        """Store session state to storage backend.

        Args:
            session_id: Unique session identifier
            state: Session state dictionary to store
            filename: Filename for the state file (default: state.json)

        Raises:
            ValueError: If state is not serializable to JSON
            OSError: If storage operation fails

        Example:
            >>> await storage.store_session("abc123", {"status": "active"})
            >>> await storage.store_session(
            ...     "abc123", checkpoint_data, "checkpoint_001.json"
            ... )

        """
        adapter = await self._ensure_adapter()
        path = self._get_session_path(session_id, filename)

        # Add metadata to state
        enhanced_state = state | {
            "_metadata": {
                "session_id": session_id,
                "stored_at": datetime.now().isoformat(),
                "backend": self.backend,
            },
        }

        # Serialize to JSON bytes
        try:
            data = json.dumps(enhanced_state, indent=2).encode("utf-8")
        except (TypeError, ValueError) as e:
            msg = f"Failed to serialize session state: {e}"
            raise ValueError(msg) from e

        # Upload to storage
        await adapter.upload(self.bucket, path, data)

    async def load_session(
        self,
        session_id: str,
        filename: str = "state.json",
    ) -> dict[str, t.Any] | None:
        """Load session state from storage backend.

        Args:
            session_id: Unique session identifier
            filename: Filename to load (default: state.json)

        Returns:
            Session state dictionary, or None if session not found

        Raises:
            ValueError: If stored data is not valid JSON
            OSError: If storage read fails

        Example:
            >>> state = await storage.load_session("abc123")
            >>> if state:
            ...     print(state["status"])

        """
        adapter = await self._ensure_adapter()
        path = self._get_session_path(session_id, filename)

        # Check if session exists
        with suppress(Exception):
            # If exists() fails, try downloading anyway
            exists = await adapter.exists(self.bucket, path)
            if not exists:
                return None

        # Download from storage
        try:
            file_obj = await adapter.download(self.bucket, path)
            # Read file content (file_obj is a BinaryIO or bytes)
            if isinstance(file_obj, (bytes, bytearray)):
                # file_obj is already bytes
                data = file_obj
            else:
                # file_obj is a file-like object
                data = file_obj.read()

            # Decode and parse JSON
            result: dict[str, t.Any] = json.loads(data.decode("utf-8"))
            return result

        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            msg = f"Failed to parse session state: {e}"
            raise ValueError(msg) from e

    async def delete_session(
        self,
        session_id: str,
        filename: str | None = None,
    ) -> bool:
        """Delete session state from storage backend.

        Args:
            session_id: Unique session identifier
            filename: Specific file to delete, or None to delete all session files

        Returns:
            True if deletion successful, False if session not found

        Raises:
            OSError: If storage delete operation fails

        Example:
            >>> await storage.delete_session("abc123")  # Delete all files
            True
            >>> await storage.delete_session(
            ...     "abc123", "checkpoint_001.json"
            ... )  # Delete specific
            True

        """
        adapter = await self._ensure_adapter()

        if filename:
            # Delete specific file
            path = self._get_session_path(session_id, filename)
            try:
                await adapter.delete(self.bucket, path)
                return True
            except FileNotFoundError:
                return False
        else:
            # Delete all session files (requires listing directory)
            # For now, just delete state.json
            # TODO: Implement directory listing and bulk delete
            path = self._get_session_path(session_id, "state.json")
            try:
                await adapter.delete(self.bucket, path)
                return True
            except FileNotFoundError:
                return False

    async def session_exists(self, session_id: str) -> bool:
        """Check if session exists in storage.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session exists, False otherwise

        Example:
            >>> if await storage.session_exists("abc123"):
            ...     state = await storage.load_session("abc123")

        """
        adapter = await self._ensure_adapter()
        path = self._get_session_path(session_id)

        try:
            exists: bool = await adapter.exists(self.bucket, path)
            return exists
        except Exception:
            # On any error, assume session doesn't exist
            return False

    async def get_session_metadata(
        self,
        session_id: str,
    ) -> dict[str, t.Any] | None:
        """Get session metadata without loading full state.

        Args:
            session_id: Unique session identifier

        Returns:
            Metadata dictionary with size, timestamps, etc., or None if not found

        Example:
            >>> metadata = await storage.get_session_metadata("abc123")
            >>> print(f"Session size: {metadata['size']} bytes")

        """
        adapter = await self._ensure_adapter()
        path = self._get_session_path(session_id)

        try:
            stats = await adapter.stat(self.bucket, path)
            return {
                "session_id": session_id,
                "size": stats.get("size", 0),
                "modified": stats.get("updated") or stats.get("mtime"),
                "created": stats.get("timeCreated") or stats.get("created"),
                "backend": self.backend,
            }
        except FileNotFoundError:
            return None
        except Exception:
            # Return minimal metadata on error
            return {
                "session_id": session_id,
                "backend": self.backend,
            }

    async def list_sessions(self) -> list[str]:
        """List all session IDs in storage.

        Returns:
            List of session IDs

        Note:
            This operation may be slow for large numbers of sessions.
            Consider implementing pagination for production use.

        Example:
            >>> sessions = await storage.list_sessions()
            >>> print(f"Found {len(sessions)} sessions")

        """
        # TODO: Implement using adapter.stat() to list bucket contents
        # This requires iterating through bucket and extracting session IDs
        # For now, return empty list as this is not critical for Phase 1
        return []


def get_default_storage_adapter() -> SessionStorageAdapter:
    """Get default session storage adapter from DI.

    Returns:
        SessionStorageAdapter configured with default backend

    Example:
        >>> storage = get_default_storage_adapter()
        >>> await storage.store_session("abc123", {"status": "active"})

    """
    from session_buddy.adapters.settings import StorageAdapterSettings

    settings = StorageAdapterSettings.from_settings()
    backend = settings.default_backend or "file"
    return SessionStorageAdapter(backend=backend)


__all__ = [
    "DEFAULT_SESSION_BUCKET",
    "SessionStorageAdapter",
    "get_default_storage_adapter",
]
