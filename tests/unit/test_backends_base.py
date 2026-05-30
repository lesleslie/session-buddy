"""Unit tests for session_buddy.backends.base module."""

from __future__ import annotations

import gzip
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from session_buddy.backends.base import SessionState, SessionStorage


class TestSessionState:
    """Tests for SessionState model."""

    def test_valid_session_state_creation(self):
        """Test creating a valid SessionState instance."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="test-session-123",
            user_id="user-456",
            project_id="project-789",
            created_at=now,
            last_activity=now,
        )
        assert state.session_id == "test-session-123"
        assert state.user_id == "user-456"
        assert state.project_id == "project-789"
        assert state.created_at == now
        assert state.last_activity == now
        assert state.permissions == []
        assert state.conversation_history == []
        assert state.reflection_data == {}
        assert state.app_monitoring_state == {}
        assert state.llm_provider_configs == {}
        assert state.metadata == {}

    def test_session_state_with_all_fields(self):
        """Test creating SessionState with all optional fields populated."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="full-session",
            user_id="user",
            project_id="project",
            created_at=now,
            last_activity=now,
            permissions=["read", "write"],
            conversation_history=[{"role": "user", "content": "hello"}],
            reflection_data={"key": "value"},
            app_monitoring_state={"active": True},
            llm_provider_configs={"provider": "minimax"},
            metadata={"meta": "data"},
        )
        assert state.permissions == ["read", "write"]
        assert state.conversation_history == [{"role": "user", "content": "hello"}]
        assert state.reflection_data == {"key": "value"}
        assert state.app_monitoring_state == {"active": True}
        assert state.llm_provider_configs == {"provider": "minimax"}
        assert state.metadata == {"meta": "data"}

    def test_session_state_invalid_timestamp_raises_error(self):
        """Test that invalid ISO timestamp raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            SessionState(
                session_id="session",
                user_id="user",
                project_id="project",
                created_at="not-a-timestamp",
                last_activity=datetime.now().isoformat(),
            )
        assert "Invalid ISO timestamp format" in str(exc_info.value)

    def test_session_state_invalid_last_activity_timestamp(self):
        """Test that invalid last_activity timestamp raises ValueError."""
        now = datetime.now().isoformat()
        with pytest.raises(ValidationError) as exc_info:
            SessionState(
                session_id="session",
                user_id="user",
                project_id="project",
                created_at=now,
                last_activity="invalid-timestamp",
            )
        assert "Invalid ISO timestamp format" in str(exc_info.value)

    def test_session_state_empty_session_id_raises_error(self):
        """Test that empty session_id raises ValidationError."""
        now = datetime.now().isoformat()
        with pytest.raises(ValidationError):
            SessionState(
                session_id="",
                user_id="user",
                project_id="project",
                created_at=now,
                last_activity=now,
            )

    def test_session_state_empty_user_id_raises_error(self):
        """Test that empty user_id raises ValidationError."""
        now = datetime.now().isoformat()
        with pytest.raises(ValidationError):
            SessionState(
                session_id="session",
                user_id="",
                project_id="project",
                created_at=now,
                last_activity=now,
            )

    def test_session_state_empty_project_id_raises_error(self):
        """Test that empty project_id raises ValidationError."""
        now = datetime.now().isoformat()
        with pytest.raises(ValidationError):
            SessionState(
                session_id="session",
                user_id="user",
                project_id="",
                created_at=now,
                last_activity=now,
            )

    def test_to_dict(self):
        """Test conversion to dictionary."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="session",
            user_id="user",
            project_id="project",
            created_at=now,
            last_activity=now,
            permissions=["admin"],
        )
        result = state.to_dict()
        assert isinstance(result, dict)
        assert result["session_id"] == "session"
        assert result["user_id"] == "user"
        assert result["project_id"] == "project"
        assert result["permissions"] == ["admin"]

    def test_from_dict(self):
        """Test creation from dictionary."""
        now = datetime.now().isoformat()
        data = {
            "session_id": "session",
            "user_id": "user",
            "project_id": "project",
            "created_at": now,
            "last_activity": now,
            "permissions": ["read"],
        }
        state = SessionState.from_dict(data)
        assert state.session_id == "session"
        assert state.permissions == ["read"]

    def test_from_dict_round_trip(self):
        """Test that to_dict and from_dict are reversible."""
        now = datetime.now().isoformat()
        original = SessionState(
            session_id="round-trip",
            user_id="user",
            project_id="project",
            created_at=now,
            last_activity=now,
            conversation_history=[{"test": "data"}],
        )
        recovered = SessionState.from_dict(original.to_dict())
        assert recovered.session_id == original.session_id
        assert recovered.conversation_history == original.conversation_history

    def test_get_compressed_size(self):
        """Test compressed size calculation."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="compress-test",
            user_id="user",
            project_id="project",
            created_at=now,
            last_activity=now,
            metadata={"large_data": "x" * 1000},
        )
        size = state.get_compressed_size()
        assert isinstance(size, int)
        assert size > 0

    def test_get_compressed_size_empty_state(self):
        """Test compressed size for minimal state."""
        now = datetime.now().isoformat()
        state = SessionState(
            session_id="minimal",
            user_id="user",
            project_id="project",
            created_at=now,
            last_activity=now,
        )
        size = state.get_compressed_size()
        assert isinstance(size, int)
        assert size > 0


class TestSessionStorage:
    """Tests for SessionStorage abstract base class."""

    def test_abstract_class_cannot_be_instantiated_directly(self):
        """Test that SessionStorage cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            SessionStorage(config={})
        # ABC compliance - can't instantiate abstract class
        assert "abstract" in str(exc_info.value).lower() or "__init__" in str(exc_info.value)

    def test_abstract_methods_exist(self):
        """Test that all abstract methods are defined."""
        # Verify abstract method signatures exist
        assert hasattr(SessionStorage, "store_session")
        assert hasattr(SessionStorage, "retrieve_session")
        assert hasattr(SessionStorage, "delete_session")
        assert hasattr(SessionStorage, "list_sessions")
        assert hasattr(SessionStorage, "cleanup_expired_sessions")
        assert hasattr(SessionStorage, "is_available")

    def test_config_stored(self):
        """Test that config is stored on instantiation."""

        class ConcreteStorage(SessionStorage):
            async def store_session(
                self, session_state: SessionState, ttl_seconds: int | None = None
            ) -> bool:
                return True

            async def retrieve_session(self, session_id: str) -> SessionState | None:
                return None

            async def delete_session(self, session_id: str) -> bool:
                return True

            async def list_sessions(
                self, user_id: str | None = None, project_id: str | None = None
            ) -> list[str]:
                return []

            async def cleanup_expired_sessions(self) -> int:
                return 0

            async def is_available(self) -> bool:
                return True

        config = {"host": "localhost", "port": 6379}
        storage = ConcreteStorage(config=config)
        assert storage.config == config

    def test_logger_name(self):
        """Test that logger is properly named."""

        class ConcreteStorage(SessionStorage):
            async def store_session(
                self, session_state: SessionState, ttl_seconds: int | None = None
            ) -> bool:
                return True

            async def retrieve_session(self, session_id: str) -> SessionState | None:
                return None

            async def delete_session(self, session_id: str) -> bool:
                return True

            async def list_sessions(
                self, user_id: str | None = None, project_id: str | None = None
            ) -> list[str]:
                return []

            async def cleanup_expired_sessions(self) -> int:
                return 0

            async def is_available(self) -> bool:
                return True

        storage = ConcreteStorage(config={})
        # Logger name should contain "serverless" and lowercase class name
        assert "serverless" in storage.logger.name.lower()
