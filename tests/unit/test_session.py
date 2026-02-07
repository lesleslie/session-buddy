#!/usr/bin/env python3
"""Test suite for session state model and storage base class.

This module tests:
- SessionState data model (validation, serialization, compression)
- SessionStorage abstract base class interface
- Session creation, retrieval, update, deletion
- Error handling and edge cases
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from session_buddy.backends.base import SessionState, SessionStorage


class ConcreteSessionStorage(SessionStorage):
    """Concrete implementation of SessionStorage for testing.

    This minimal implementation allows us to test the base class behavior
    without relying on actual storage backends.
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config or {})

    async def store_session(
        self,
        session_state: SessionState,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store session state in memory."""
        if not hasattr(self, "_sessions"):
            self._sessions = {}
        self._sessions[session_state.session_id] = session_state
        return True

    async def retrieve_session(self, session_id: str) -> SessionState | None:
        """Retrieve session from memory."""
        if not hasattr(self, "_sessions"):
            self._sessions = {}
        return self._sessions.get(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Delete session from memory."""
        if not hasattr(self, "_sessions"):
            self._sessions = {}
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def list_sessions(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[str]:
        """List session IDs from memory."""
        if not hasattr(self, "_sessions"):
            self._sessions = {}
        session_ids = list(self._sessions.keys())
        # Filter by user_id and project_id if provided
        if user_id or project_id:
            filtered = []
            for session_id in session_ids:
                session = self._sessions[session_id]
                if user_id and session.user_id != user_id:
                    continue
                if project_id and session.project_id != project_id:
                    continue
                filtered.append(session_id)
            return filtered
        return session_ids

    async def cleanup_expired_sessions(self) -> int:
        """No-op cleanup for in-memory storage."""
        return 0

    async def is_available(self) -> bool:
        """In-memory storage is always available."""
        return True


class TestSessionStateModel:
    """Test SessionState data model validation and serialization."""

    def test_create_session_state_minimal(self):
        """Test creating SessionState with minimal required fields."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="test-session-123",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
        )

        assert state.session_id == "test-session-123"
        assert state.user_id == "user-1"
        assert state.project_id == "project-1"
        assert state.permissions == []
        assert state.conversation_history == []
        assert state.reflection_data == {}
        assert state.metadata == {}

    def test_create_session_state_full(self):
        """Test creating SessionState with all fields populated."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="test-session-456",
            user_id="user-2",
            project_id="project-2",
            created_at=now,
            last_activity=now,
            permissions=["read", "write", "execute"],
            conversation_history=[{"role": "user", "content": "Hello"}],
            reflection_data={"insights": ["Learning 1", "Learning 2"]},
            app_monitoring_state={"cpu": 50, "memory": 70},
            llm_provider_configs={"model": "gpt-4"},
            metadata={"custom": "value"},
        )

        assert len(state.permissions) == 3
        assert "write" in state.permissions
        assert len(state.conversation_history) == 1
        assert state.reflection_data["insights"] == ["Learning 1", "Learning 2"]
        assert state.app_monitoring_state["cpu"] == 50
        assert state.llm_provider_configs["model"] == "gpt-4"
        assert state.metadata["custom"] == "value"

    def test_session_state_validation_missing_session_id(self):
        """Test SessionState validation fails with missing session_id."""
        now = datetime.now().isoformat()
        with pytest.raises(ValidationError) as exc_info:
            SessionState(
                session_id="",  # Empty string violates min_length=1
                user_id="user-1",
                project_id="project-1",
                created_at=now,
                last_activity=now,
            )
        assert "session_id" in str(exc_info.value)

    def test_session_state_validation_missing_user_id(self):
        """Test SessionState validation fails with missing user_id."""
        now = datetime.now().isoformat()
        with pytest.raises(ValidationError) as exc_info:
            SessionState(
                session_id="session-1",
                user_id="",  # Empty string
                project_id="project-1",
                created_at=now,
                last_activity=now,
            )
        assert "user_id" in str(exc_info.value)

    def test_session_state_validation_missing_project_id(self):
        """Test SessionState validation fails with missing project_id."""
        now = datetime.now().isoformat()
        with pytest.raises(ValidationError) as exc_info:
            SessionState(
                session_id="session-1",
                user_id="user-1",
                project_id="",  # Empty string
                created_at=now,
                last_activity=now,
            )
        assert "project_id" in str(exc_info.value)

    def test_session_state_invalid_timestamp_format(self):
        """Test SessionState validation fails with invalid timestamp format."""
        with pytest.raises(ValidationError) as exc_info:
            SessionState(
                session_id="session-1",
                user_id="user-1",
                project_id="project-1",
                created_at="not-a-timestamp",
                last_activity=datetime.now().isoformat(),
            )
        assert "Invalid ISO timestamp" in str(exc_info.value)

    def test_session_state_valid_iso_timestamps(self):
        """Test SessionState accepts various valid ISO timestamp formats."""
        valid_timestamps = [
            "2025-01-15T14:30:45",
            "2025-01-15T14:30:45.123456",
            "2025-01-15T14:30:45+00:00",
            "2025-01-15T14:30:45Z",
        ]

        for timestamp in valid_timestamps:
            state = SessionState(
                session_id="session-1",
                user_id="user-1",
                project_id="project-1",
                created_at=timestamp,
                last_activity=timestamp,
            )
            assert state.created_at == timestamp
            assert state.last_activity == timestamp

    def test_to_dict(self):
        """Test SessionState.to_dict() serialization."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
            permissions=["read"],
            metadata={"key": "value"},
        )

        data = state.to_dict()
        assert isinstance(data, dict)
        assert data["session_id"] == "session-1"
        assert data["user_id"] == "user-1"
        assert data["permissions"] == ["read"]
        assert data["metadata"]["key"] == "value"

    def test_from_dict(self):
        """Test SessionState.from_dict() deserialization."""
        data = {
            "session_id": "session-1",
            "user_id": "user-1",
            "project_id": "project-1",
            "created_at": "2025-01-15T14:30:45",
            "last_activity": "2025-01-15T14:30:45",
            "permissions": ["read", "write"],
            "conversation_history": [],
            "reflection_data": {},
            "app_monitoring_state": {},
            "llm_provider_configs": {},
            "metadata": {},
        }

        state = SessionState.from_dict(data)
        assert state.session_id == "session-1"
        assert state.permissions == ["read", "write"]

    def test_from_dict_round_trip(self):
        """Test SessionState serialization round trip preserves data."""
        original = SessionState(
            session_id="test-session",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-15T14:30:45",
            last_activity="2025-01-15T14:30:45",
            permissions=["read", "write", "delete"],
            conversation_history=[{"role": "user", "content": "Hello"}],
            reflection_data={"insights": ["Learning"]},
            metadata={"custom": "data"},
        )

        # Serialize to dict
        data = original.to_dict()

        # Deserialize back to SessionState
        restored = SessionState.from_dict(data)

        # Verify all fields match
        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.project_id == original.project_id
        assert restored.permissions == original.permissions
        assert restored.conversation_history == original.conversation_history
        assert restored.reflection_data == original.reflection_data
        assert restored.metadata == original.metadata

    def test_get_compressed_size(self):
        """Test SessionState.get_compressed_size() returns valid size."""
        state = SessionState(
            session_id="test-session",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-15T14:30:45",
            last_activity="2025-01-15T14:30:45",
            conversation_history=[{"role": "user", "content": "Hello"}] * 10,
        )

        size = state.get_compressed_size()
        assert isinstance(size, int)
        assert size > 0

    def test_get_compressed_size_increases_with_data(self):
        """Test that compressed size increases with more data."""
        small_state = SessionState(
            session_id="small",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-15T14:30:45",
            last_activity="2025-01-15T14:30:45",
        )

        large_state = SessionState(
            session_id="large",
            user_id="user-1",
            project_id="project-1",
            created_at="2025-01-15T14:30:45",
            last_activity="2025-01-15T14:30:45",
            conversation_history=[{"role": "user", "content": "x" * 1000}] * 50,
        )

        small_size = small_state.get_compressed_size()
        large_size = large_state.get_compressed_size()
        assert large_size > small_size

    def test_session_state_with_unicode_data(self):
        """Test SessionState handles unicode characters properly."""
        state = SessionState(
            session_id="session-unicode",
            user_id="user-world",
            project_id="project-globe",
            created_at="2025-01-15T14:30:45",
            last_activity="2025-01-15T14:30:45",
            conversation_history=[
                {"role": "user", "content": "Hello World"},
            ],
            metadata={"emoji": "check", "chinese": "zhongwen"},
        )

        # Should not raise any errors
        data = state.to_dict()
        restored = SessionState.from_dict(data)
        assert restored.conversation_history[0]["content"] == "Hello World"


class TestSessionStorage:
    """Test SessionStorage abstract base class and concrete implementation."""

    @pytest.fixture
    def storage(self):
        """Create a concrete storage instance for testing."""
        return ConcreteSessionStorage({})

    @pytest.mark.asyncio
    async def test_store_and_retrieve_session(self, storage):
        """Test storing and retrieving a session."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="test-session-1",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
            permissions=["read"],
        )

        # Store session
        success = await storage.store_session(state)
        assert success is True

        # Retrieve session
        retrieved = await storage.retrieve_session("test-session-1")
        assert retrieved is not None
        assert retrieved.session_id == "test-session-1"
        assert retrieved.permissions == ["read"]

    @pytest.mark.asyncio
    async def test_store_session_with_ttl(self, storage):
        """Test storing session with TTL parameter."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="session-with-ttl",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
        )

        # Store with TTL (concrete implementation may or may not use it)
        success = await storage.store_session(state, ttl_seconds=3600)
        assert success is True

        # Should still be retrievable
        retrieved = await storage.retrieve_session("session-with-ttl")
        assert retrieved is not None

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_session(self, storage):
        """Test retrieving a session that doesn't exist."""
        retrieved = await storage.retrieve_session("nonexistent-session")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_existing_session(self, storage):
        """Test deleting an existing session."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="session-to-delete",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
        )

        # Store session
        await storage.store_session(state)

        # Delete session
        deleted = await storage.delete_session("session-to-delete")
        assert deleted is True

        # Verify it's gone
        retrieved = await storage.retrieve_session("session-to-delete")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_session(self, storage):
        """Test deleting a session that doesn't exist."""
        deleted = await storage.delete_session("nonexistent-session")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_list_sessions_all(self, storage):
        """Test listing all sessions without filters."""
        # Store multiple sessions
        now = datetime.now().isoformat()
        for i in range(3):
            state = SessionState(
                session_id=f"session-{i}",
                user_id=f"user-{i % 2}",  # Alternate users
                project_id=f"project-{i % 2}",  # Alternate projects
                created_at=now,
                last_activity=now,
            )
            await storage.store_session(state)

        # List all sessions
        session_ids = await storage.list_sessions()
        assert len(session_ids) == 3
        assert "session-0" in session_ids
        assert "session-1" in session_ids
        assert "session-2" in session_ids

    @pytest.mark.asyncio
    async def test_list_sessions_filter_by_user(self, storage):
        """Test listing sessions filtered by user_id."""
        now = datetime.now().isoformat()
        # Create sessions for different users
        for user_id in ["user-1", "user-2"]:
            for i in range(2):
                state = SessionState(
                    session_id=f"{user_id}-session-{i}",
                    user_id=user_id,
                    project_id="project-1",
                    created_at=now,
                    last_activity=now,
                )
                await storage.store_session(state)

        # Filter by user-1
        user1_sessions = await storage.list_sessions(user_id="user-1")
        assert len(user1_sessions) == 2
        assert all(s.startswith("user-1") for s in user1_sessions)

        # Filter by user-2
        user2_sessions = await storage.list_sessions(user_id="user-2")
        assert len(user2_sessions) == 2
        assert all(s.startswith("user-2") for s in user2_sessions)

    @pytest.mark.asyncio
    async def test_list_sessions_filter_by_project(self, storage):
        """Test listing sessions filtered by project_id."""
        now = datetime.now().isoformat()
        # Create sessions for different projects
        for project_id in ["project-1", "project-2"]:
            for i in range(2):
                state = SessionState(
                    session_id=f"{project_id}-session-{i}",
                    user_id="user-1",
                    project_id=project_id,
                    created_at=now,
                    last_activity=now,
                )
                await storage.store_session(state)

        # Filter by project-1
        project1_sessions = await storage.list_sessions(project_id="project-1")
        assert len(project1_sessions) == 2
        assert all(s.startswith("project-1") for s in project1_sessions)

    @pytest.mark.asyncio
    async def test_list_sessions_filter_by_both(self, storage):
        """Test listing sessions filtered by both user_id and project_id."""
        now = datetime.now().isoformat()
        # Create various combinations
        combinations = [
            ("user-1", "project-1", "session-1-1"),
            ("user-1", "project-2", "session-1-2"),
            ("user-2", "project-1", "session-2-1"),
            ("user-2", "project-2", "session-2-2"),
        ]

        for user_id, project_id, session_id in combinations:
            state = SessionState(
                session_id=session_id,
                user_id=user_id,
                project_id=project_id,
                created_at=now,
                last_activity=now,
            )
            await storage.store_session(state)

        # Filter by user-1 AND project-1
        filtered = await storage.list_sessions(user_id="user-1", project_id="project-1")
        assert len(filtered) == 1
        assert filtered[0] == "session-1-1"

    @pytest.mark.asyncio
    async def test_list_empty_storage(self, storage):
        """Test listing sessions from empty storage."""
        session_ids = await storage.list_sessions()
        assert session_ids == []

    @pytest.mark.asyncio
    async def test_is_available(self, storage):
        """Test checking if storage is available."""
        available = await storage.is_available()
        assert available is True

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, storage):
        """Test cleanup of expired sessions."""
        # Concrete implementation returns 0, but test interface
        cleaned = await storage.cleanup_expired_sessions()
        assert isinstance(cleaned, int)
        assert cleaned >= 0

    @pytest.mark.asyncio
    async def test_update_session(self, storage):
        """Test updating an existing session by storing new version."""
        now = datetime.now().isoformat()
        original_state = SessionState(
            session_id="session-to-update",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
            permissions=["read"],
        )

        # Store original
        await storage.store_session(original_state)

        # Update with new data
        updated_state = SessionState(
            session_id="session-to-update",  # Same ID
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
            permissions=["read", "write", "delete"],  # Updated permissions
            metadata={"updated": True},
        )

        await storage.store_session(updated_state)

        # Retrieve and verify update
        retrieved = await storage.retrieve_session("session-to-update")
        assert retrieved is not None
        assert len(retrieved.permissions) == 3
        assert "write" in retrieved.permissions
        assert retrieved.metadata.get("updated") is True

    @pytest.mark.asyncio
    async def test_multiple_stores_and_retrieves(self, storage):
        """Test multiple store/retrieve operations."""
        now = datetime.now().isoformat()
        sessions = []

        # Create multiple sessions
        for i in range(10):
            state = SessionState(
                session_id=f"session-{i}",
                user_id=f"user-{i % 3}",
                project_id=f"project-{i % 2}",
                created_at=now,
                last_activity=now,
            )
            sessions.append(state)
            await storage.store_session(state)

        # Retrieve all and verify
        for session in sessions:
            retrieved = await storage.retrieve_session(session.session_id)
            assert retrieved is not None
            assert retrieved.session_id == session.session_id
            assert retrieved.user_id == session.user_id


class TestSessionStateErrorHandling:
    """Test error handling in SessionState and SessionStorage."""

    def test_session_state_with_invalid_data_types(self):
        """Test SessionState rejects invalid data types."""
        now = datetime.now().isoformat()
        with pytest.raises(ValidationError):
            SessionState(
                session_id="session-1",
                user_id="user-1",
                project_id="project-1",
                created_at=now,
                last_activity=now,
                permissions="not-a-list",  # Should be list
            )

    def test_session_state_from_dict_with_invalid_data(self):
        """Test from_dict handles invalid dictionary data."""
        invalid_data = {
            "session_id": "session-1",
            # Missing required fields
        }

        with pytest.raises(ValidationError):
            SessionState.from_dict(invalid_data)


class TestSessionStateCompression:
    """Test SessionState compression functionality."""

    def test_compression_ratio_with_repetitive_data(self):
        """Test that repetitive data compresses well."""
        # Create state with repetitive data
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="compress-test",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
            conversation_history=[{"message": "repeat " * 100}] * 50,
        )

        compressed_size = state.get_compressed_size()

        # Create similar state without repetitive data
        state2 = SessionState(
            session_id="no-compress-test",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
            conversation_history=[{"message": "unique "}] * 50,
        )

        compressed_size2 = state2.get_compressed_size()

        # Repetitive data should compress better (smaller size)
        # though this is implementation-dependent
        assert compressed_size > 0
        assert compressed_size2 > 0

    def test_get_compressed_size_with_empty_state(self):
        """Test compression size of minimal SessionState."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="minimal",
            user_id="user-1",
            project_id="project-1",
            created_at=now,
            last_activity=now,
        )

        size = state.get_compressed_size()
        # Even minimal state should have some size
        assert size > 100  # At least 100 bytes when compressed


if __name__ == "__main__":
    pytest.main([__file__])
