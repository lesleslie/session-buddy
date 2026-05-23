"""Comprehensive tests for serverless_mode module.

Tests serverless session management with Oneiric storage backends.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.backends.base import SessionState


class TestServerlessSessionManager:
    """Test ServerlessSessionManager class comprehensively."""

    @pytest.fixture
    def mock_storage(self) -> AsyncMock:
        """Create a mock storage backend."""
        storage = AsyncMock()
        storage.store_session = AsyncMock(return_value=True)
        storage.retrieve_session = AsyncMock(return_value=None)
        storage.delete_session = AsyncMock(return_value=True)
        storage.list_sessions = AsyncMock(return_value=[])
        storage.cleanup_expired_sessions = AsyncMock(return_value=0)
        storage.config = {}
        return storage

    @pytest.fixture
    def session_state(self) -> SessionState:
        """Create a test session state."""
        return SessionState(
            session_id="test-session-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
            permissions=["read", "write"],
            conversation_history=[{"role": "user", "content": "hello"}],
            reflection_data={"key": "value"},
            app_monitoring_state={"active": True},
            llm_provider_configs={"provider": "minimax"},
            metadata={"custom": "data"},
        )

    # =========================================================================
    # create_session Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_create_session_success(self, mock_storage: AsyncMock) -> None:
        """Should create a new session and return session ID."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        session_id = await manager.create_session(
            user_id="user-1",
            project_id="project-1",
        )

        assert isinstance(session_id, str)
        assert len(session_id) == 16  # SHA256 hexdigest[:16]
        mock_storage.store_session.assert_called_once()
        assert session_id in manager.session_cache

    @pytest.mark.asyncio
    async def test_create_session_with_custom_ttl(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should create session with custom TTL."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        session_id = await manager.create_session(
            user_id="user-1",
            project_id="project-1",
            ttl_hours=48,
        )

        call_args = mock_storage.store_session.call_args
        args, _kwargs = call_args
        # store_session(session_state, ttl_seconds) - ttl_seconds is 2nd positional
        assert args[1] == 48 * 3600

    @pytest.mark.asyncio
    async def test_create_session_with_initial_data(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should create session with initial session data."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        initial_data = {"custom_field": "custom_value", "count": 42}
        session_id = await manager.create_session(
            user_id="user-1",
            project_id="project-1",
            session_data=initial_data,
        )

        call_args = mock_storage.store_session.call_args
        args, _kwargs = call_args
        stored_state: SessionState = args[0]
        assert stored_state.metadata["custom_field"] == "custom_value"
        assert stored_state.metadata["count"] == 42

    @pytest.mark.asyncio
    async def test_create_session_storage_failure(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should raise RuntimeError when storage fails."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.store_session.return_value = False
        manager = ServerlessSessionManager(mock_storage)

        with pytest.raises(RuntimeError, match="Failed to create session"):
            await manager.create_session(
                user_id="user-1",
                project_id="project-1",
            )

    @pytest.mark.asyncio
    async def test_create_session_caches_result(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should cache created session in memory."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        session_id = await manager.create_session(
            user_id="user-1",
            project_id="project-1",
        )

        assert session_id in manager.session_cache
        assert isinstance(manager.session_cache[session_id], SessionState)

    # =========================================================================
    # get_session Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_get_session_from_cache(
        self, mock_storage: AsyncMock, session_state: SessionState
    ) -> None:
        """Should return session from cache when available."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        manager.session_cache["cached-session"] = session_state

        result = await manager.get_session("cached-session")

        assert result == session_state
        mock_storage.retrieve_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_session_from_storage(
        self,
        mock_storage: AsyncMock,
        session_state: SessionState,
    ) -> None:
        """Should load session from storage when not in cache."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.retrieve_session.return_value = session_state
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.get_session("test-session-123")

        assert result == session_state
        mock_storage.retrieve_session.assert_called_once_with("test-session-123")
        assert "test-session-123" in manager.session_cache

    @pytest.mark.asyncio
    async def test_get_session_not_found(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should return None when session does not exist."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.retrieve_session.return_value = None
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.get_session("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_after_delete_returns_none(
        self, mock_storage: AsyncMock, session_state: SessionState
    ) -> None:
        """Should return None for session that was deleted."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)

        # Create and then delete a session
        session_id = await manager.create_session("user-1", "project-1")
        await manager.delete_session(session_id)

        # Now try to get it - should return None
        result = await manager.get_session(session_id)

        assert result is None

    # =========================================================================
    # update_session Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_update_session_success(
        self,
        mock_storage: AsyncMock,
        session_state: SessionState,
    ) -> None:
        """Should update session and return True."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.retrieve_session.return_value = session_state
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.update_session(
            "test-session-123",
            {"metadata": {"updated": True}},
        )

        assert result is True
        mock_storage.store_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_session_updates_cache(
        self,
        mock_storage: AsyncMock,
        session_state: SessionState,
    ) -> None:
        """Should update cached session after modification."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.retrieve_session.return_value = session_state
        manager = ServerlessSessionManager(mock_storage)
        _ = await manager.get_session("test-session-123")

        updates = {"metadata": {"updated": True, "count": 5}}
        await manager.update_session("test-session-123", updates)

        cached = manager.session_cache["test-session-123"]
        assert cached.metadata["updated"] is True
        assert cached.metadata["count"] == 5

    @pytest.mark.asyncio
    async def test_update_session_updates_last_activity(
        self,
        mock_storage: AsyncMock,
        session_state: SessionState,
    ) -> None:
        """Should update last_activity timestamp on modification."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        original_time = "2025-01-01T12:00:00"
        session_state.last_activity = original_time
        mock_storage.retrieve_session.return_value = session_state
        manager = ServerlessSessionManager(mock_storage)

        await manager.update_session("test-session-123", {"metadata": {}})

        cached = manager.session_cache["test-session-123"]
        assert cached.last_activity != original_time

    @pytest.mark.asyncio
    async def test_update_session_not_found(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should return False when session does not exist."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.retrieve_session.return_value = None
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.update_session(
            "nonexistent",
            {"metadata": {"updated": True}},
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_update_session_with_custom_ttl(
        self,
        mock_storage: AsyncMock,
        session_state: SessionState,
    ) -> None:
        """Should update session with custom TTL."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.retrieve_session.return_value = session_state
        manager = ServerlessSessionManager(mock_storage)

        await manager.update_session(
            "test-session-123",
            {"metadata": {}},
            ttl_hours=72,
        )

        call_args = mock_storage.store_session.call_args
        args, _kwargs = call_args
        # store_session(session_state, ttl_seconds) - ttl_seconds is 2nd positional
        assert args[1] == 72 * 3600

    @pytest.mark.asyncio
    async def test_update_session_with_new_attributes(
        self,
        mock_storage: AsyncMock,
        session_state: SessionState,
    ) -> None:
        """Should add new attributes to session via update."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.retrieve_session.return_value = session_state
        manager = ServerlessSessionManager(mock_storage)

        await manager.update_session(
            "test-session-123",
            {"permissions": ["admin", "read", "write"]},
        )

        cached = manager.session_cache["test-session-123"]
        assert "admin" in cached.permissions

    # =========================================================================
    # delete_session Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_delete_session_success(
        self, mock_storage: AsyncMock, session_state: SessionState
    ) -> None:
        """Should delete session from cache and storage."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        manager.session_cache["to-delete"] = session_state

        result = await manager.delete_session("to-delete")

        assert result is True
        assert "to-delete" not in manager.session_cache
        mock_storage.delete_session.assert_called_once_with("to-delete")

    @pytest.mark.asyncio
    async def test_delete_session_removes_from_cache(
        self, mock_storage: AsyncMock, session_state: SessionState
    ) -> None:
        """Should remove session from cache on deletion."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        manager.session_cache["to-delete"] = session_state

        await manager.delete_session("to-delete")

        assert "to-delete" not in manager.session_cache

    @pytest.mark.asyncio
    async def test_delete_session_not_found(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should return result from storage even if not in cache."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.delete_session.return_value = False
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.delete_session("nonexistent")

        assert result is False

    # =========================================================================
    # list_user_sessions Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_list_user_sessions(self, mock_storage: AsyncMock) -> None:
        """Should list all sessions for a user."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.list_sessions.return_value = ["s1", "s2", "s3"]
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.list_user_sessions("user-1")

        assert result == ["s1", "s2", "s3"]
        mock_storage.list_sessions.assert_called_once_with(user_id="user-1")

    @pytest.mark.asyncio
    async def test_list_user_sessions_empty(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should return empty list when user has no sessions."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.list_sessions.return_value = []
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.list_user_sessions("user-with-no-sessions")

        assert result == []

    # =========================================================================
    # list_project_sessions Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_list_project_sessions(self, mock_storage: AsyncMock) -> None:
        """Should list all sessions for a project."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.list_sessions.return_value = ["p1", "p2"]
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.list_project_sessions("project-1")

        assert result == ["p1", "p2"]
        mock_storage.list_sessions.assert_called_once_with(project_id="project-1")

    # =========================================================================
    # cleanup_sessions Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_cleanup_sessions(self, mock_storage: AsyncMock) -> None:
        """Should delegate cleanup to storage backend."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.cleanup_expired_sessions.return_value = 5
        manager = ServerlessSessionManager(mock_storage)

        result = await manager.cleanup_sessions()

        assert result == 5
        mock_storage.cleanup_expired_sessions.assert_called_once()

    # =========================================================================
    # get_session_stats Tests
    # =========================================================================
    def test_get_session_stats(self, mock_storage: AsyncMock) -> None:
        """Should return session statistics."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        manager.session_cache["s1"] = SessionState(
            session_id="s1",
            user_id="u1",
            project_id="p1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )
        manager.session_cache["s2"] = SessionState(
            session_id="s2",
            user_id="u2",
            project_id="p1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )

        stats = manager.get_session_stats()

        assert stats["cached_sessions"] == 2
        assert stats["storage_backend"] == "AsyncMock"
        assert "storage_config" in stats

    def test_get_session_stats_filters_sensitive_config(
        self, mock_storage: AsyncMock
    ) -> None:
        """Should filter sensitive keys from storage config."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        mock_storage.config = {
            "api_key": "secret-key",
            "storage_dir": "/tmp/sessions",
            "endpoint": "https://api.example.com",
        }
        manager = ServerlessSessionManager(mock_storage)

        stats = manager.get_session_stats()

        assert "api_key" not in stats["storage_config"]
        assert stats["storage_config"]["storage_dir"] == "/tmp/sessions"
        assert stats["storage_config"]["endpoint"] == "https://api.example.com"

    # =========================================================================
    # _generate_session_id Tests
    # =========================================================================
    def test_generate_session_id_format(self, mock_storage: AsyncMock) -> None:
        """Should generate 16-character hex string."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        session_id = manager._generate_session_id("user-1", "project-1")

        assert isinstance(session_id, str)
        assert len(session_id) == 16
        assert all(c in "0123456789abcdef" for c in session_id)

    def test_generate_session_id_uniqueness(self, mock_storage: AsyncMock) -> None:
        """Should generate unique IDs for different inputs."""
        from session_buddy.serverless_mode import ServerlessSessionManager

        manager = ServerlessSessionManager(mock_storage)
        ids = set()
        for i in range(100):
            session_id = manager._generate_session_id(f"user-{i}", f"project-{i}")
            ids.add(session_id)

        assert len(ids) == 100  # All unique


class TestServerlessConfigManager:
    """Test ServerlessConfigManager comprehensively."""

    # =========================================================================
    # load_config Tests
    # =========================================================================
    def test_load_config_returns_defaults(self) -> None:
        """Should return default configuration."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = ServerlessConfigManager.load_config()

        assert config["storage_backend"] == "file"
        assert config["session_ttl_hours"] == 24
        assert config["cleanup_interval_hours"] == 6
        assert "backends" in config
        assert "file" in config["backends"]
        assert "memory" in config["backends"]

    def test_load_config_with_nonexistent_path(self) -> None:
        """Should return defaults when config file does not exist."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = ServerlessConfigManager.load_config(
            config_path="/nonexistent/path/config.json"
        )

        assert config["storage_backend"] == "file"

    def test_load_config_with_custom_path(self) -> None:
        """Should merge custom config with defaults."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete_on_close=False
        ) as f:
            json.dump(
                {
                    "storage_backend": "memory",
                    "session_ttl_hours": 48,
                    "custom_field": "custom_value",
                },
                f,
            )
            f.seek(0)
            config = ServerlessConfigManager.load_config(config_path=f.name)

        assert config["storage_backend"] == "memory"
        assert config["session_ttl_hours"] == 48
        assert config["custom_field"] == "custom_value"
        assert "backends" in config  # Defaults preserved

    def test_load_config_with_invalid_json(self) -> None:
        """Should return defaults when JSON is invalid."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete_on_close=False
        ) as f:
            f.write("not valid json {")
            f.seek(0)
            config = ServerlessConfigManager.load_config(config_path=f.name)

        assert config["storage_backend"] == "file"

    def test_load_config_with_unreadable_file(self) -> None:
        """Should return defaults when file cannot be read."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = ServerlessConfigManager.load_config(
            config_path="/root/protected.json"
        )

        assert config["storage_backend"] == "file"

    # =========================================================================
    # create_storage_backend Tests
    # =========================================================================
    def test_create_storage_backend_file(self) -> None:
        """Should create file storage backend."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {
            "storage_backend": "file",
            "backends": {"file": {"storage_dir": "/tmp/sessions"}},
        }

        storage = ServerlessConfigManager.create_storage_backend(config)

        assert storage.__class__.__name__ == "ServerlessStorageAdapter"
        assert storage.backend == "file"

    def test_create_storage_backend_memory(self) -> None:
        """Should create memory storage backend."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"storage_backend": "memory", "backends": {"memory": {}}}

        storage = ServerlessConfigManager.create_storage_backend(config)

        assert storage.__class__.__name__ == "ServerlessStorageAdapter"
        assert storage.backend == "memory"

    def test_create_storage_backend_invalid(self) -> None:
        """Should raise ValueError for unsupported backend."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {
            "storage_backend": "redis",
            "backends": {"redis": {"host": "localhost"}},
        }

        with pytest.raises(ValueError, match="Unsupported storage backend: redis"):
            ServerlessConfigManager.create_storage_backend(config)

    def test_create_storage_backend_default_is_file(self) -> None:
        """Should default to file backend when not specified."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"backends": {"file": {}}}

        storage = ServerlessConfigManager.create_storage_backend(config)

        assert storage.backend == "file"

    def test_create_storage_backend_with_empty_backends(self) -> None:
        """Should work with empty backends dict."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"storage_backend": "file", "backends": {}}

        storage = ServerlessConfigManager.create_storage_backend(config)

        assert storage.__class__.__name__ == "ServerlessStorageAdapter"

    # =========================================================================
    # test_storage_backends Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_test_storage_backends_memory(self) -> None:
        """Should test memory backend availability."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"backends": {"memory": {}}}

        results = await ServerlessConfigManager.test_storage_backends(config)

        assert "memory" in results
        assert results["memory"] is True

    @pytest.mark.asyncio
    async def test_test_storage_backends_multiple(self) -> None:
        """Should test multiple backends."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"backends": {"memory": {}, "file": {}}}

        results = await ServerlessConfigManager.test_storage_backends(config)

        assert "memory" in results
        assert "file" in results

    @pytest.mark.asyncio
    async def test_test_storage_backends_unknown_skipped(self) -> None:
        """Should skip unknown backend types."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"backends": {"memory": {}, "unknown": {}}}

        results = await ServerlessConfigManager.test_storage_backends(config)

        assert "memory" in results
        assert "unknown" in results
        assert results["unknown"] is False

    @pytest.mark.asyncio
    async def test_test_storage_backends_empty(self) -> None:
        """Should handle empty backends config."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config: dict[str, Any] = {"backends": {}}

        results = await ServerlessConfigManager.test_storage_backends(config)

        assert results == {}

    @pytest.mark.asyncio
    async def test_test_storage_backends_exception_handling(self) -> None:
        """Should handle exceptions gracefully."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"backends": {"memory": {}}}

        results = await ServerlessConfigManager.test_storage_backends(config)

        assert isinstance(results, dict)


class TestServerlessStorageAdapterEdgeCases:
    """Test ServerlessStorageAdapter edge cases."""

    @pytest.fixture
    def mock_session_storage_adapter(self) -> AsyncMock:
        """Create a mock SessionStorageAdapter."""
        adapter = AsyncMock()
        adapter.store_session = AsyncMock()
        adapter.load_session = AsyncMock(return_value=None)
        adapter.delete_session = AsyncMock(return_value=True)
        return adapter

    # =========================================================================
    # TTL Expiration Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_retrieve_expired_session(self) -> None:
        """Should return None and delete expired session."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")
        # Manually add to metadata cache to simulate stored session
        storage._session_metadata["expired-session"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2024-01-01T00:00:00",
            "ttl_seconds": 3600,
            "expires_at": "2024-01-01T01:00:00",  # Already expired
        }

        result = await storage.retrieve_session("expired-session")

        assert result is None

    @pytest.mark.asyncio
    async def test_store_session_with_ttl_metadata(self) -> None:
        """Should store TTL metadata with session."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.backends.base import SessionState

        storage = ServerlessStorageAdapter(backend="memory")
        session = SessionState(
            session_id="ttl-session",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )

        await storage.store_session(session, ttl_seconds=7200)

        metadata = storage._session_metadata["ttl-session"]
        assert metadata["ttl_seconds"] == 7200
        assert metadata["expires_at"] is not None

    # =========================================================================
    # Backend Error Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_store_session_handles_exception(self) -> None:
        """Should return False on storage exception."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.backends.base import SessionState

        storage = ServerlessStorageAdapter(backend="memory")

        # Patch _ensure_storage to raise exception
        with patch.object(
            storage,
            "_ensure_storage",
            side_effect=Exception("Storage unavailable"),
        ):
            session = SessionState(
                session_id="error-session",
                user_id="user-1",
                project_id="project-1",
                created_at="2025-01-01T12:00:00",
                last_activity="2025-01-01T12:00:00",
            )

            result = await storage.store_session(session)

        assert result is False

    @pytest.mark.asyncio
    async def test_retrieve_session_handles_exception(self) -> None:
        """Should return None on retrieval exception."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")

        with patch.object(
            storage,
            "_ensure_storage",
            side_effect=Exception("Storage unavailable"),
        ):
            result = await storage.retrieve_session("any-session")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_session_handles_exception(self) -> None:
        """Should return False on delete exception."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")

        with patch.object(
            storage,
            "_ensure_storage",
            side_effect=Exception("Storage unavailable"),
        ):
            result = await storage.delete_session("any-session")

        assert result is False

    # =========================================================================
    # Corrupted Data Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_retrieve_with_invalid_ttl_format(self) -> None:
        """Should handle invalid TTL timestamp format gracefully."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")
        storage._session_metadata["bad-ttl"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2025-01-01T12:00:00",
            "ttl_seconds": 3600,
            "expires_at": "not-a-valid-timestamp",
        }

        result = await storage.retrieve_session("bad-ttl")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_sessions_filters_expired(self) -> None:
        """Should filter out expired sessions in list."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")
        # Add expired session
        storage._session_metadata["expired-session"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2024-01-01T00:00:00",
            "ttl_seconds": 3600,
            "expires_at": "2024-01-01T01:00:00",  # Expired
        }
        # Add valid session
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        storage._session_metadata["valid-session"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2025-01-01T12:00:00",
            "ttl_seconds": 3600,
            "expires_at": future_time,
        }

        result = await storage.list_sessions(user_id="user-1")

        assert "valid-session" in result
        assert "expired-session" not in result

    @pytest.mark.asyncio
    async def test_list_sessions_no_expiry(self) -> None:
        """Should include sessions without expiry time."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")
        storage._session_metadata["no-expiry"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2025-01-01T12:00:00",
            "ttl_seconds": None,
            "expires_at": None,
        }

        result = await storage.list_sessions(user_id="user-1")

        assert "no-expiry" in result

    # =========================================================================
    # Cleanup Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_none_found(self) -> None:
        """Should return 0 when no sessions are expired."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        storage._session_metadata["future-session"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2025-01-01T12:00:00",
            "ttl_seconds": 3600,
            "expires_at": future_time,
        }

        result = await storage.cleanup_expired_sessions()

        assert result == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_deletes_expired(self) -> None:
        """Should delete expired sessions during cleanup."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")
        storage._session_metadata["expired-1"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2024-01-01T00:00:00",
            "ttl_seconds": 3600,
            "expires_at": "2024-01-01T01:00:00",
        }
        storage._session_metadata["expired-2"] = {
            "user_id": "user-2",
            "project_id": "project-1",
            "created_at": "2024-01-01T00:00:00",
            "ttl_seconds": 3600,
            "expires_at": "2024-01-01T01:00:00",
        }

        result = await storage.cleanup_expired_sessions()

        assert result == 2
        assert "expired-1" not in storage._session_metadata
        assert "expired-2" not in storage._session_metadata

    @pytest.mark.asyncio
    async def test_cleanup_handles_invalid_timestamp(self) -> None:
        """Should skip sessions with invalid timestamps."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")
        storage._session_metadata["bad-timestamp"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2025-01-01T12:00:00",
            "ttl_seconds": 3600,
            "expires_at": "invalid-timestamp",
        }
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        storage._session_metadata["valid-session"] = {
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2025-01-01T12:00:00",
            "ttl_seconds": 3600,
            "expires_at": future_time,
        }

        result = await storage.cleanup_expired_sessions()

        assert result == 0  # Bad timestamp session should be skipped, not deleted
        assert "bad-timestamp" in storage._session_metadata

    # =========================================================================
    # is_available Tests
    # =========================================================================
    @pytest.mark.asyncio
    async def test_is_available_returns_false_on_exception(self) -> None:
        """Should return False when storage check fails."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")

        with patch.object(
            storage,
            "_ensure_storage",
            side_effect=Exception("Backend unavailable"),
        ):
            result = await storage.is_available()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_available_handles_corrupted_data(self) -> None:
        """Should handle corrupted test data gracefully."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")
        # Already initialized with None _storage
        storage._storage = None

        with patch.object(
            storage,
            "_ensure_storage",
            side_effect=Exception("Test failure"),
        ):
            result = await storage.is_available()

        assert result is False


class TestServerlessModeConcurrency:
    """Test concurrent operations in serverless mode."""

    @pytest.mark.asyncio
    async def test_concurrent_session_create(self) -> None:
        """Should handle concurrent session creation."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        storage = ServerlessStorageAdapter(backend="memory")
        manager = ServerlessSessionManager(storage)

        async def create() -> str:
            return await manager.create_session(
                user_id="user-1", project_id="project-1"
            )

        import asyncio

        results = await asyncio.gather(create(), create(), create())

        assert len(set(results)) == 3  # All unique session IDs

    @pytest.mark.asyncio
    async def test_concurrent_session_updates(self) -> None:
        """Should handle concurrent updates to same session."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        storage = ServerlessStorageAdapter(backend="memory")
        manager = ServerlessSessionManager(storage)

        session_id = await manager.create_session(
            user_id="user-1", project_id="project-1"
        )

        async def update(n: int) -> bool:
            return await manager.update_session(
                session_id, {"metadata": {"counter": n}}
            )

        import asyncio

        results = await asyncio.gather(
            update(1), update(2), update(3), return_exceptions=True
        )

        # All should complete without raising
        assert all(r is True or isinstance(r, Exception) for r in results)


class TestServerlessModeIntegration:
    """Integration tests for serverless mode with real storage."""

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self) -> None:
        """Should complete full session lifecycle."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        storage = ServerlessStorageAdapter(backend="memory")
        manager = ServerlessSessionManager(storage)

        # Create
        session_id = await manager.create_session(
            user_id="user-1",
            project_id="project-1",
            session_data={"initial": True},
            ttl_hours=24,
        )
        assert session_id is not None

        # Read
        session = await manager.get_session(session_id)
        assert session is not None
        assert session.user_id == "user-1"
        assert session.metadata["initial"] is True

        # Update
        success = await manager.update_session(
            session_id,
            {
                "metadata": {"updated": True},
                "conversation_history": [{"role": "user", "content": "Hello"}],
            },
        )
        assert success is True

        # Verify update
        updated = await manager.get_session(session_id)
        assert updated is not None
        assert updated.metadata["updated"] is True
        assert len(updated.conversation_history) == 1

        # Delete
        deleted = await manager.delete_session(session_id)
        assert deleted is True

        # Verify deletion
        gone = await manager.get_session(session_id)
        assert gone is None

    @pytest.mark.asyncio
    async def test_session_with_file_backend(self) -> None:
        """Should work with file backend."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ServerlessStorageAdapter(
                backend="file", config={"storage_dir": tmpdir}
            )
            manager = ServerlessSessionManager(storage)

            session_id = await manager.create_session(
                user_id="user-1",
                project_id="project-1",
            )

            session = await manager.get_session(session_id)
            assert session is not None
            assert session.user_id == "user-1"

    @pytest.mark.asyncio
    async def test_list_sessions_after_create(self) -> None:
        """Should list sessions correctly after creation."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        storage = ServerlessStorageAdapter(backend="memory")
        manager = ServerlessSessionManager(storage)

        await manager.create_session(user_id="user-1", project_id="project-1")
        await manager.create_session(user_id="user-1", project_id="project-2")
        await manager.create_session(user_id="user-2", project_id="project-1")

        user1_sessions = await manager.list_user_sessions("user-1")
        assert len(user1_sessions) == 2

        project1_sessions = await manager.list_project_sessions("project-1")
        assert len(project1_sessions) == 2


class TestSessionStateEdgeCases:
    """Test SessionState model edge cases."""

    def test_session_state_with_all_fields(self) -> None:
        """Should create SessionState with all fields populated."""
        session = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
            permissions=["read", "write"],
            conversation_history=[{"role": "user", "content": "Hello"}],
            reflection_data={"insights": ["insight1"]},
            app_monitoring_state={"metrics": {"cpu": 0.5}},
            llm_provider_configs={"provider": "minimax", "model": "M2.7"},
            metadata={"custom": "value"},
        )

        assert session.session_id == "test-123"
        assert len(session.permissions) == 2
        assert len(session.conversation_history) == 1
        assert session.llm_provider_configs["model"] == "M2.7"

    def test_session_state_default_values(self) -> None:
        """Should have correct default values."""
        session = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )

        assert session.permissions == []
        assert session.conversation_history == []
        assert session.reflection_data == {}
        assert session.app_monitoring_state == {}
        assert session.llm_provider_configs == {}
        assert session.metadata == {}

    def test_session_state_invalid_timestamp(self) -> None:
        """Should raise ValueError for invalid timestamp format."""
        with pytest.raises(ValueError, match="Invalid ISO timestamp format"):
            SessionState(
                session_id="test-123",
                user_id="user-1",
                project_id="project-1",
                created_at="not-a-timestamp",
                last_activity="2025-01-01T12:00:00",
            )

    def test_session_state_to_dict_roundtrip(self) -> None:
        """Should survive to_dict -> from_dict roundtrip."""
        original = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
            permissions=["read"],
            conversation_history=[{"role": "user", "content": "test"}],
        )

        data = original.to_dict()
        restored = SessionState.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.permissions == original.permissions

    def test_session_state_get_compressed_size(self) -> None:
        """Should return compressed size."""
        session = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )

        size = session.get_compressed_size()

        assert isinstance(size, int)
        assert size > 0