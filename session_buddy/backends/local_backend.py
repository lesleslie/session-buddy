"""Local file system session storage backend.

**DEPRECATED**: This module is deprecated and will be removed in v1.0.
Use ServerlessStorageAdapter with backend="file" instead, which uses ACB's
native file storage adapter with async support and better performance.

Migration:
    Old: LocalFileStorage(config)
    New: ServerlessStorageAdapter(config, backend="file")

This module provides a local file system implementation of the SessionStorage interface
for storing and retrieving session state in local files (useful for development/testing).
"""

from __future__ import annotations

import gzip
import json
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from session_buddy.backends.base import SessionState, SessionStorage
from session_buddy.utils.time import utc_now


class LocalFileStorage(SessionStorage):
    """Local file-based session storage (for development/testing).

    .. deprecated:: 0.9.3
        LocalFileStorage is deprecated. Use ``ServerlessStorageAdapter(backend="file")``
        which provides async file operations and better performance via ACB.

    """

    def __init__(self, config: dict[str, Any]) -> None:
        warnings.warn(
            "LocalFileStorage is deprecated and will be removed in v1.0. "
            "Use ServerlessStorageAdapter(backend='file') instead for "
            "async file operations and ACB integration.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(config)
        self.storage_dir = Path(
            config.get("storage_dir", Path.home() / ".claude" / "data" / "sessions"),
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_file(self, session_id: str) -> Path:
        """Get file path for session."""
        return self.storage_dir / f"{session_id}.json.gz"

    async def store_session(
        self,
        session_state: SessionState,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store session in local file."""
        try:
            # Serialize and compress session state
            serialized = json.dumps(session_state.to_dict())
            compressed = gzip.compress(serialized.encode("utf-8"))

            # Write to file
            session_file = self._get_session_file(session_state.session_id)
            with session_file.open("wb") as f:
                f.write(compressed)

            return True

        except Exception:
            self.logger.exception(
                f"Failed to store session {session_state.session_id}",
            )
            return False

    async def retrieve_session(self, session_id: str) -> SessionState | None:
        """Retrieve session from local file."""
        try:
            session_file = self._get_session_file(session_id)

            if not session_file.exists():
                return None

            # Read and decompress
            with session_file.open("rb") as f:
                compressed_data = f.read()

            serialized = gzip.decompress(compressed_data).decode("utf-8")
            session_data = json.loads(serialized)

            return SessionState.from_dict(session_data)

        except Exception:
            self.logger.exception(f"Failed to retrieve session {session_id}")
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete session file."""
        try:
            session_file = self._get_session_file(session_id)

            if session_file.exists():
                session_file.unlink()
                return True

            return False

        except Exception:
            self.logger.exception(f"Failed to delete session {session_id}")
            return False

    async def list_sessions(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[str]:
        """List session files."""
        try:
            session_ids = []
            for session_file in self.storage_dir.glob("*.json.gz"):
                session_id = self._extract_session_id(session_file)
                if await self._should_include_session(session_id, user_id, project_id):
                    session_ids.append(session_id)
            return session_ids
        except Exception:
            self.logger.exception("Failed to list sessions")
            return []

    def _extract_session_id(self, session_file: Path) -> str:
        """Extract session ID from file path."""
        return session_file.stem.replace(".json", "")

    async def _should_include_session(
        self,
        session_id: str,
        user_id: str | None,
        project_id: str | None,
    ) -> bool:
        """Check if session should be included based on filters."""
        if not user_id and not project_id:
            return True

        session_state = await self.retrieve_session(session_id)
        if not session_state:
            return False

        return self._matches_filters(session_state, user_id, project_id)

    def _matches_filters(
        self,
        session_state: SessionState,
        user_id: str | None,
        project_id: str | None,
    ) -> bool:
        """Check if session matches the given filters."""
        if user_id and session_state.user_id != user_id:
            return False
        return not (project_id and session_state.project_id != project_id)

    async def cleanup_expired_sessions(self) -> int:
        """Clean up old session files."""
        try:
            now = utc_now()
            cleaned = 0

            for session_file in self.storage_dir.glob("*.json.gz"):
                # Check file age
                file_age = now - datetime.fromtimestamp(
                    session_file.stat().st_mtime, tz=UTC
                )

                if file_age.days > 7:  # Cleanup sessions older than 7 days
                    session_file.unlink()
                    cleaned += 1

            return cleaned

        except Exception:
            self.logger.exception("Failed to cleanup expired sessions")
            return 0

    async def is_available(self) -> bool:
        """Check if local storage is available."""
        return self.storage_dir.exists() and self.storage_dir.is_dir()
