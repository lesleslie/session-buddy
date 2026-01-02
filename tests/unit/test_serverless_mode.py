"""Tests for serverless_mode module.

Tests serverless session management with Oneiric storage backends.
"""

from __future__ import annotations

import pytest


class TestSessionState:
    """Test SessionState Pydantic model."""

    def test_session_state_initialization(self) -> None:
        """Should create SessionState with required fields."""
        from session_buddy.serverless_mode import SessionState

        session = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )

        assert session.session_id == "test-123"
        assert session.user_id == "user-1"
        assert session.project_id == "project-1"
        assert isinstance(session.permissions, list)
        assert isinstance(session.conversation_history, list)

    def test_session_state_to_dict(self) -> None:
        """Should convert SessionState to dictionary."""
        from session_buddy.serverless_mode import SessionState

        session = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )

        data = session.to_dict()

        assert isinstance(data, dict)
        assert data["session_id"] == "test-123"
        assert data["user_id"] == "user-1"

    def test_session_state_from_dict(self) -> None:
        """Should create SessionState from dictionary."""
        from session_buddy.serverless_mode import SessionState

        data = {
            "session_id": "test-123",
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2025-01-01T12:00:00",
            "last_activity": "2025-01-01T12:00:00",
            "permissions": [],
            "conversation_history": [],
            "reflection_data": {},
            "app_monitoring_state": {},
            "llm_provider_configs": {},
            "metadata": {},
        }

        session = SessionState.from_dict(data)

        assert session.session_id == "test-123"
        assert session.user_id == "user-1"


class TestServerlessStorageAdapter:
    """Test ServerlessStorageAdapter with Oneiric storage backends."""

    @pytest.mark.asyncio
    async def test_store_session_success(self) -> None:
        """Should store session using aiocache."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import SessionState

        storage = ServerlessStorageAdapter(backend="memory")

        session = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )

        result = await storage.store_session(session, ttl_seconds=60)

        assert result is True
        # Verify it can be retrieved back
        retrieved = await storage.retrieve_session("test-123")
        assert retrieved is not None
        assert retrieved.session_id == "test-123"

    @pytest.mark.asyncio
    async def test_retrieve_session_success(self) -> None:
        """Should retrieve session from aiocache."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import SessionState

        storage = ServerlessStorageAdapter(backend="memory")

        session = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )
        await storage.store_session(session)

        session = await storage.retrieve_session("test-123")

        assert session is not None
        assert session.session_id == "test-123"
        assert session.session_id == "test-123"

    @pytest.mark.asyncio
    async def test_retrieve_session_not_found(self) -> None:
        """Should return None when session not found."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")

        session = await storage.retrieve_session("nonexistent")

        assert session is None

    @pytest.mark.asyncio
    async def test_delete_session_success(self) -> None:
        """Should delete session from aiocache."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import SessionState

        storage = ServerlessStorageAdapter(backend="memory")
        session = SessionState(
            session_id="test-123",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )
        await storage.store_session(session)

        result = await storage.delete_session("test-123")

        assert result is True
        assert result is True

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self) -> None:
        """Should return empty list when no sessions."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")

        sessions = await storage.list_sessions()

        assert sessions == []

    @pytest.mark.asyncio
    async def test_list_sessions_with_filter(self) -> None:
        """Should filter sessions by user_id and project_id."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import SessionState

        storage = ServerlessStorageAdapter(backend="memory")

        sessions = [
            SessionState(
                session_id="session-1",
                user_id="user-1",
                project_id="project-1",
                created_at="2025-01-01T12:00:00",
                last_activity="2025-01-01T12:00:00",
            ),
            SessionState(
                session_id="session-2",
                user_id="user-2",
                project_id="project-1",
                created_at="2025-01-01T12:00:00",
                last_activity="2025-01-01T12:00:00",
            ),
            SessionState(
                session_id="session-3",
                user_id="user-1",
                project_id="project-2",
                created_at="2025-01-01T12:00:00",
                last_activity="2025-01-01T12:00:00",
            ),
        ]

        for session in sessions:
            await storage.store_session(session)

        # Filter by user_id
        sessions = await storage.list_sessions(user_id="user-1")
        assert len(sessions) == 2
        assert "session-1" in sessions
        assert "session-3" in sessions

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self) -> None:
        """Should cleanup stale index entries."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import SessionState

        storage = ServerlessStorageAdapter(backend="memory")
        session = SessionState(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-01T12:00:00",
            last_activity="2025-01-01T12:00:00",
        )
        await storage.store_session(session, ttl_seconds=-1)

        cleaned = await storage.cleanup_expired_sessions()

        assert cleaned == 1  # One session expired

    @pytest.mark.asyncio
    async def test_is_available_success(self) -> None:
        """Should return True when storage is available."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )

        storage = ServerlessStorageAdapter(backend="memory")

        available = await storage.is_available()

        assert available is True


class TestServerlessSessionManager:
    """Test ServerlessSessionManager class."""

    @pytest.mark.asyncio
    async def test_create_session(self) -> None:
        """Should create new session with ServerlessSessionManager."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        storage = ServerlessStorageAdapter(backend="memory")

        manager = ServerlessSessionManager(storage)

        session_id = await manager.create_session(
            user_id="user-1", project_id="project-1"
        )

        assert isinstance(session_id, str)
        assert len(session_id) > 0

    @pytest.mark.asyncio
    async def test_get_session(self) -> None:
        """Should retrieve session state."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        storage = ServerlessStorageAdapter(backend="memory")
        manager = ServerlessSessionManager(storage)

        session_id = await manager.create_session("user-1", "project-1")
        session = await manager.get_session(session_id)

        assert session is not None
        assert session.user_id == "user-1"

    @pytest.mark.asyncio
    async def test_update_session(self) -> None:
        """Should update session state."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        storage = ServerlessStorageAdapter(backend="memory")
        manager = ServerlessSessionManager(storage)

        session_id = await manager.create_session("user-1", "project-1")
        result = await manager.update_session(
            session_id,
            {"metadata": {"updated": True}},
        )

        assert result is True
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_session(self) -> None:
        """Should delete session."""
        from session_buddy.adapters.serverless_storage_adapter import (
            ServerlessStorageAdapter,
        )
        from session_buddy.serverless_mode import ServerlessSessionManager

        storage = ServerlessStorageAdapter(backend="memory")
        manager = ServerlessSessionManager(storage)

        session_id = await manager.create_session("user-1", "project-1")
        result = await manager.delete_session(session_id)

        assert result is True


class TestServerlessConfigManager:
    """Test ServerlessConfigManager factory methods."""

    def test_create_storage_backend_default(self) -> None:
        """Should create Oneiric storage adapter by default."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"storage_backend": "file", "backends": {"file": {}}}

        storage = ServerlessConfigManager.create_storage_backend(config)

        assert storage.__class__.__name__ == "ServerlessStorageAdapter"

    def test_create_storage_backend_invalid_backend(self) -> None:
        """Should reject unsupported backends."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {"storage_backend": "redis", "backends": {"redis": {}}}

        with pytest.raises(ValueError):
            ServerlessConfigManager.create_storage_backend(config)

    @pytest.mark.asyncio
    async def test_test_storage_backends(self) -> None:
        """Should test all configured backends."""
        from session_buddy.serverless_mode import ServerlessConfigManager

        config = {
            "backends": {
                "memory": {},
            }
        }

        results = await ServerlessConfigManager.test_storage_backends(config)

        assert isinstance(results, dict)
        assert "memory" in results
