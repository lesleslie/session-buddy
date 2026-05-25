"""Unit tests for serverless_storage_adapter module.

Tests the ServerlessStorageAdapter which bridges serverless_mode.py to
the Oneiric SessionStorageAdapter for persistent session state.

Phase 1: Serverless Storage Adapter Foundation
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.adapters.serverless_storage_adapter import (
    ServerlessStorageAdapter,
    create_serverless_storage,
)
from session_buddy.backends.base import SessionState


class TestServerlessStorageAdapterInitialization:
    """Test ServerlessStorageAdapter initialization and configuration."""

    def test_init_with_default_backend(self):
        """Test initialization with default 'file' backend."""
        adapter = ServerlessStorageAdapter()

        assert adapter.backend == "file"
        assert adapter._storage is None
        assert adapter._session_metadata == {}
        assert adapter.logger is not None
        assert "serverless.storage.file" in adapter.logger.name

    def test_init_with_memory_backend(self):
        """Test initialization with 'memory' backend."""
        adapter = ServerlessStorageAdapter(backend="memory")

        assert adapter.backend == "memory"
        assert "serverless.storage.memory" in adapter.logger.name

    def test_init_with_custom_config(self):
        """Test initialization with custom config dict."""
        config = {"host": "localhost", "port": 6379}
        adapter = ServerlessStorageAdapter(config=config)

        assert adapter.config == config

    def test_init_with_s3_backend(self):
        """Test initialization with 's3' backend."""
        adapter = ServerlessStorageAdapter(backend="s3")

        assert adapter.backend == "s3"

    def test_init_with_azure_backend(self):
        """Test initialization with 'azure' backend."""
        adapter = ServerlessStorageAdapter(backend="azure")

        assert adapter.backend == "azure"

    def test_init_with_gcs_backend(self):
        """Test initialization with 'gcs' backend."""
        adapter = ServerlessStorageAdapter(backend="gcs")

        assert adapter.backend == "gcs"


class TestServerlessStorageAdapterEnsureStorage:
    """Test _ensure_storage internal method."""

    @pytest.fixture
    def mock_session_storage_adapter(self):
        """Create a mock SessionStorageAdapter."""
        mock = AsyncMock()
        mock.store_session = AsyncMock()
        mock.load_session = AsyncMock(return_value=None)
        mock.delete_session = AsyncMock(return_value=True)
        return mock

    async def test_ensure_storage_creates_adapter(self, mock_session_storage_adapter):
        """Test _ensure_storage creates SessionStorageAdapter lazily."""
        adapter = ServerlessStorageAdapter(backend="memory")

        with patch(
            "session_buddy.adapters.session_storage_adapter.SessionStorageAdapter",
            return_value=mock_session_storage_adapter,
        ):
            result = await adapter._ensure_storage()

        assert result is mock_session_storage_adapter
        assert adapter._storage is mock_session_storage_adapter

    async def test_ensure_storage_returns_cached(self, mock_session_storage_adapter):
        """Test _ensure_storage returns cached adapter on subsequent calls."""
        adapter = ServerlessStorageAdapter(backend="memory")
        adapter._storage = mock_session_storage_adapter

        result = await adapter._ensure_storage()

        assert result is mock_session_storage_adapter

    async def test_ensure_storage_uses_correct_backend(self):
        """Test _ensure_storage passes correct backend to SessionStorageAdapter."""
        adapter = ServerlessStorageAdapter(backend="s3")

        with patch(
            "session_buddy.adapters.session_storage_adapter.SessionStorageAdapter"
        ) as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance

            await adapter._ensure_storage()

            mock_class.assert_called_once_with(backend="s3")


class TestServerlessStorageAdapterStoreSession:
    """Test store_session method."""

    @pytest.fixture
    def mock_session_storage_adapter(self):
        """Create a mock SessionStorageAdapter."""
        mock = AsyncMock()
        mock.store_session = AsyncMock()
        mock.load_session = AsyncMock(return_value=None)
        mock.delete_session = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def adapter_with_mock(self, mock_session_storage_adapter):
        """Create adapter with mocked storage."""
        adapter = ServerlessStorageAdapter(backend="memory")
        adapter._storage = mock_session_storage_adapter
        return adapter

    @pytest.fixture
    def sample_session_state(self):
        """Create a sample SessionState for testing."""
        return SessionState(
            session_id="test-session-123",
            user_id="user-456",
            project_id="project-789",
            created_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat(),
            permissions=["read", "write"],
        )

    async def test_store_session_success(
        self, adapter_with_mock, mock_session_storage_adapter, sample_session_state
    ):
        """Test successful session storage."""
        result = await adapter_with_mock.store_session(sample_session_state)

        assert result is True
        mock_session_storage_adapter.store_session.assert_called_once()
        call_args = mock_session_storage_adapter.store_session.call_args
        assert call_args[0][0] == "test-session-123"

    async def test_store_session_with_ttl(
        self, adapter_with_mock, mock_session_storage_adapter, sample_session_state
    ):
        """Test session storage with TTL."""
        result = await adapter_with_mock.store_session(
            sample_session_state, ttl_seconds=3600
        )

        assert result is True
        call_args = mock_session_storage_adapter.store_session.call_args
        state_dict = call_args[0][1]

        # Verify TTL metadata was added
        assert "_ttl" in state_dict
        assert state_dict["_ttl"]["ttl_seconds"] == 3600
        assert "expires_at" in state_dict["_ttl"]

    async def test_store_session_metadata_cached(
        self, adapter_with_mock, mock_session_storage_adapter, sample_session_state
    ):
        """Test that session metadata is cached."""
        await adapter_with_mock.store_session(
            sample_session_state, ttl_seconds=7200
        )

        assert sample_session_state.session_id in adapter_with_mock._session_metadata
        metadata = adapter_with_mock._session_metadata[
            sample_session_state.session_id
        ]
        assert metadata["user_id"] == "user-456"
        assert metadata["project_id"] == "project-789"
        assert metadata["ttl_seconds"] == 7200

    async def test_store_session_without_ttl(
        self, adapter_with_mock, mock_session_storage_adapter, sample_session_state
    ):
        """Test session storage without TTL."""
        result = await adapter_with_mock.store_session(sample_session_state)

        assert result is True
        call_args = mock_session_storage_adapter.store_session.call_args
        state_dict = call_args[0][1]

        # TTL should not be added if not provided
        assert "_ttl" not in state_dict

    async def test_store_session_failure(
        self, adapter_with_mock, mock_session_storage_adapter, sample_session_state
    ):
        """Test store_session handles exceptions gracefully."""
        mock_session_storage_adapter.store_session = AsyncMock(
            side_effect=Exception("Storage error")
        )

        result = await adapter_with_mock.store_session(sample_session_state)

        assert result is False


class TestServerlessStorageAdapterRetrieveSession:
    """Test retrieve_session method."""

    @pytest.fixture
    def mock_session_storage_adapter(self):
        """Create a mock SessionStorageAdapter."""
        mock = AsyncMock()
        mock.store_session = AsyncMock()
        mock.load_session = AsyncMock(return_value=None)
        mock.delete_session = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def adapter_with_mock(self, mock_session_storage_adapter):
        """Create adapter with mocked storage."""
        adapter = ServerlessStorageAdapter(backend="memory")
        adapter._storage = mock_session_storage_adapter
        return adapter

    async def test_retrieve_session_success(self, adapter_with_mock):
        """Test successful session retrieval."""
        session_id = "test-session-123"
        state_dict = {
            "session_id": session_id,
            "user_id": "user-456",
            "project_id": "project-789",
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "permissions": ["read"],
            "conversation_history": [],
            "reflection_data": {},
            "app_monitoring_state": {},
            "llm_provider_configs": {},
            "metadata": {},
        }
        adapter_with_mock._storage.load_session = AsyncMock(
            return_value=state_dict
        )

        result = await adapter_with_mock.retrieve_session(session_id)

        assert result is not None
        assert result.session_id == session_id
        assert result.user_id == "user-456"

    async def test_retrieve_session_not_found(self, adapter_with_mock):
        """Test retrieval of non-existent session."""
        adapter_with_mock._storage.load_session = AsyncMock(return_value=None)

        result = await adapter_with_mock.retrieve_session("nonexistent-session")

        assert result is None

    async def test_retrieve_session_with_expired_ttl(self, adapter_with_mock):
        """Test retrieval of session with expired TTL deletes it."""
        session_id = "expired-session"
        # Set expires_at to yesterday
        expired_time = (datetime.now() - timedelta(days=1)).isoformat()
        state_dict = {
            "session_id": session_id,
            "user_id": "user-456",
            "project_id": "project-789",
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "permissions": [],
            "conversation_history": [],
            "reflection_data": {},
            "app_monitoring_state": {},
            "llm_provider_configs": {},
            "metadata": {},
            "_ttl": {"ttl_seconds": 3600, "expires_at": expired_time},
        }
        adapter_with_mock._storage.load_session = AsyncMock(
            return_value=state_dict
        )

        result = await adapter_with_mock.retrieve_session(session_id)

        assert result is None
        adapter_with_mock._storage.delete_session.assert_called_once_with(session_id)

    async def test_retrieve_session_removes_ttl_metadata(self, adapter_with_mock):
        """Test that _ttl and _metadata are removed from retrieved state."""
        session_id = "test-session"
        state_dict = {
            "session_id": session_id,
            "user_id": "user-456",
            "project_id": "project-789",
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "permissions": [],
            "conversation_history": [],
            "reflection_data": {},
            "app_monitoring_state": {},
            "llm_provider_configs": {},
            "metadata": {},
            "_ttl": {"ttl_seconds": 3600, "expires_at": "2099-01-01T00:00:00"},
            "_metadata": {"some": "metadata"},
        }
        adapter_with_mock._storage.load_session = AsyncMock(
            return_value=state_dict
        )

        result = await adapter_with_mock.retrieve_session(session_id)

        assert result is not None
        # Verify _ttl and _metadata are not in the result
        assert not hasattr(result, "_ttl")
        # The result is a SessionState, so we check it doesn't have TTL in dict form
        result_dict = result.model_dump()
        assert "_ttl" not in result_dict
        assert "_metadata" not in result_dict

    async def test_retrieve_session_failure(self, adapter_with_mock):
        """Test retrieve_session handles exceptions gracefully."""
        adapter_with_mock._storage.load_session = AsyncMock(
            side_effect=Exception("Storage error")
        )

        result = await adapter_with_mock.retrieve_session("test-session")

        assert result is None


class TestServerlessStorageAdapterDeleteSession:
    """Test delete_session method."""

    @pytest.fixture
    def mock_session_storage_adapter(self):
        """Create a mock SessionStorageAdapter."""
        mock = AsyncMock()
        mock.store_session = AsyncMock()
        mock.load_session = AsyncMock(return_value=None)
        mock.delete_session = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def adapter_with_mock(self, mock_session_storage_adapter):
        """Create adapter with mocked storage."""
        adapter = ServerlessStorageAdapter(backend="memory")
        adapter._storage = mock_session_storage_adapter
        # Pre-populate metadata cache
        adapter._session_metadata["session-to-delete"] = {
            "user_id": "user",
            "project_id": "project",
            "ttl_seconds": 3600,
        }
        return adapter

    async def test_delete_session_success(self, adapter_with_mock):
        """Test successful session deletion."""
        session_id = "session-to-delete"

        result = await adapter_with_mock.delete_session(session_id)

        assert result is True
        adapter_with_mock._storage.delete_session.assert_called_once_with(session_id)

    async def test_delete_session_removes_from_cache(self, adapter_with_mock):
        """Test that session is removed from metadata cache after deletion."""
        session_id = "session-to-delete"

        await adapter_with_mock.delete_session(session_id)

        assert session_id not in adapter_with_mock._session_metadata

    async def test_delete_session_not_found(self, adapter_with_mock):
        """Test deleting non-existent session returns False."""
        adapter_with_mock._storage.delete_session = AsyncMock(return_value=False)

        result = await adapter_with_mock.delete_session("nonexistent-session")

        assert result is False

    async def test_delete_session_failure(self, adapter_with_mock):
        """Test delete_session handles exceptions gracefully."""
        adapter_with_mock._storage.delete_session = AsyncMock(
            side_effect=Exception("Storage error")
        )

        result = await adapter_with_mock.delete_session("test-session")

        assert result is False


class TestServerlessStorageAdapterListSessions:
    """Test list_sessions method."""

    @pytest.fixture
    def mock_session_storage_adapter(self):
        """Create a mock SessionStorageAdapter."""
        mock = AsyncMock()
        mock.store_session = AsyncMock()
        mock.load_session = AsyncMock(return_value=None)
        mock.delete_session = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def adapter_with_mock(self, mock_session_storage_adapter):
        """Create adapter with mocked storage and populated cache."""
        adapter = ServerlessStorageAdapter(backend="memory")
        adapter._storage = mock_session_storage_adapter
        # Populate metadata cache with test sessions
        now = datetime.now()
        future_time = (now + timedelta(days=1)).isoformat()
        past_time = (now - timedelta(days=1)).isoformat()

        adapter._session_metadata = {
            "session-active-1": {
                "user_id": "user-1",
                "project_id": "project-1",
                "expires_at": future_time,
            },
            "session-active-2": {
                "user_id": "user-1",
                "project_id": "project-2",
                "expires_at": future_time,
            },
            "session-expired": {
                "user_id": "user-2",
                "project_id": "project-1",
                "expires_at": past_time,
            },
            "session-no-expiry": {
                "user_id": "user-2",
                "project_id": "project-2",
                "expires_at": None,
            },
        }
        return adapter

    async def test_list_sessions_no_filter(self, adapter_with_mock):
        """Test listing all non-expired sessions with no filter."""
        result = await adapter_with_mock.list_sessions()

        assert len(result) == 3
        assert "session-active-1" in result
        assert "session-active-2" in result
        assert "session-no-expiry" in result
        assert "session-expired" not in result

    async def test_list_sessions_filter_by_user(self, adapter_with_mock):
        """Test listing sessions filtered by user_id."""
        result = await adapter_with_mock.list_sessions(user_id="user-1")

        assert len(result) == 2
        assert "session-active-1" in result
        assert "session-active-2" in result

    async def test_list_sessions_filter_by_project(self, adapter_with_mock):
        """Test listing sessions filtered by project_id."""
        result = await adapter_with_mock.list_sessions(project_id="project-1")

        assert len(result) == 1
        assert "session-active-1" in result

    async def test_list_sessions_filter_by_user_and_project(self, adapter_with_mock):
        """Test listing sessions filtered by both user_id and project_id."""
        result = await adapter_with_mock.list_sessions(
            user_id="user-1", project_id="project-2"
        )

        assert len(result) == 1
        assert "session-active-2" in result

    async def test_list_sessions_no_matches(self, adapter_with_mock):
        """Test listing sessions when no matches found."""
        result = await adapter_with_mock.list_sessions(user_id="nonexistent-user")

        assert len(result) == 0

    async def test_list_sessions_empty_cache(self, adapter_with_mock):
        """Test listing sessions with empty cache."""
        adapter_with_mock._session_metadata = {}

        result = await adapter_with_mock.list_sessions()

        assert result == []


class TestServerlessStorageAdapterCleanupExpiredSessions:
    """Test cleanup_expired_sessions method."""

    @pytest.fixture
    def mock_session_storage_adapter(self):
        """Create a mock SessionStorageAdapter."""
        mock = AsyncMock()
        mock.store_session = AsyncMock()
        mock.load_session = AsyncMock(return_value=None)
        mock.delete_session = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def adapter_with_mock(self, mock_session_storage_adapter):
        """Create adapter with mocked storage and expired sessions."""
        adapter = ServerlessStorageAdapter(backend="memory")
        adapter._storage = mock_session_storage_adapter
        return adapter

    async def test_cleanup_expired_sessions(self, adapter_with_mock):
        """Test cleanup removes expired sessions."""
        now = datetime.now()
        past_time = (now - timedelta(days=1)).isoformat()
        future_time = (now + timedelta(days=1)).isoformat()

        adapter_with_mock._session_metadata = {
            "session-expired-1": {
                "user_id": "user-1",
                "project_id": "project-1",
                "expires_at": past_time,
            },
            "session-expired-2": {
                "user_id": "user-2",
                "project_id": "project-2",
                "expires_at": past_time,
            },
            "session-active": {
                "user_id": "user-3",
                "project_id": "project-3",
                "expires_at": future_time,
            },
        }

        result = await adapter_with_mock.cleanup_expired_sessions()

        assert result == 2
        assert "session-active" in adapter_with_mock._session_metadata
        assert "session-expired-1" not in adapter_with_mock._session_metadata
        assert "session-expired-2" not in adapter_with_mock._session_metadata

    async def test_cleanup_expired_sessions_none_to_clean(self, adapter_with_mock):
        """Test cleanup when no sessions are expired."""
        future_time = (datetime.now() + timedelta(days=1)).isoformat()

        adapter_with_mock._session_metadata = {
            "session-active": {
                "user_id": "user-1",
                "project_id": "project-1",
                "expires_at": future_time,
            }
        }

        result = await adapter_with_mock.cleanup_expired_sessions()

        assert result == 0

    async def test_cleanup_expired_sessions_empty_cache(self, adapter_with_mock):
        """Test cleanup with empty cache."""
        adapter_with_mock._session_metadata = {}

        result = await adapter_with_mock.cleanup_expired_sessions()

        assert result == 0

    async def test_cleanup_expired_sessions_invalid_timestamp(
        self, adapter_with_mock
    ):
        """Test cleanup skips sessions with invalid timestamps."""
        adapter_with_mock._session_metadata = {
            "session-invalid": {
                "user_id": "user-1",
                "project_id": "project-1",
                "expires_at": "invalid-timestamp",
            }
        }

        result = await adapter_with_mock.cleanup_expired_sessions()

        assert result == 0
        assert "session-invalid" in adapter_with_mock._session_metadata

    async def test_cleanup_expired_sessions_delete_failure(self, adapter_with_mock):
        """Test cleanup continues even if delete fails for a session."""
        now = datetime.now()
        past_time = (now - timedelta(days=1)).isoformat()

        adapter_with_mock._session_metadata = {
            "session-expired-1": {
                "user_id": "user-1",
                "project_id": "project-1",
                "expires_at": past_time,
            },
            "session-expired-2": {
                "user_id": "user-2",
                "project_id": "project-2",
                "expires_at": past_time,
            },
        }
        # First delete succeeds, second fails
        adapter_with_mock._storage.delete_session = AsyncMock(
            side_effect=[True, Exception("Delete failed")]
        )

        result = await adapter_with_mock.cleanup_expired_sessions()

        # Only one successful delete counted
        assert result == 1


class TestServerlessStorageAdapterIsAvailable:
    """Test is_available method."""

    @pytest.fixture
    def mock_session_storage_adapter(self):
        """Create a mock SessionStorageAdapter."""
        mock = AsyncMock()
        mock.store_session = AsyncMock()
        mock.load_session = AsyncMock(return_value=None)
        mock.delete_session = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def adapter_with_mock(self, mock_session_storage_adapter):
        """Create adapter with mocked storage."""
        adapter = ServerlessStorageAdapter(backend="memory")
        adapter._storage = mock_session_storage_adapter
        return adapter

    async def test_is_available_success(self, adapter_with_mock):
        """Test is_available returns True when storage works."""
        adapter_with_mock._storage.store_session = AsyncMock()
        adapter_with_mock._storage.load_session = AsyncMock(return_value={"test": True})
        adapter_with_mock._storage.delete_session = AsyncMock(return_value=True)

        result = await adapter_with_mock.is_available()

        assert result is True
        adapter_with_mock._storage.store_session.assert_called_once()
        adapter_with_mock._storage.load_session.assert_called_once()
        adapter_with_mock._storage.delete_session.assert_called_once()

    async def test_is_available_returns_false_when_store_fails(self, adapter_with_mock):
        """Test is_available returns False when store fails."""
        adapter_with_mock._storage.store_session = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        result = await adapter_with_mock.is_available()

        assert result is False

    async def test_is_available_returns_false_when_load_fails(self, adapter_with_mock):
        """Test is_available returns False when load fails."""
        adapter_with_mock._storage.store_session = AsyncMock()
        adapter_with_mock._storage.load_session = AsyncMock(
            side_effect=Exception("Read error")
        )
        adapter_with_mock._storage.delete_session = AsyncMock(return_value=True)

        result = await adapter_with_mock.is_available()

        assert result is False

    async def test_is_available_returns_false_when_delete_fails(self, adapter_with_mock):
        """Test is_available returns False when delete fails."""
        adapter_with_mock._storage.store_session = AsyncMock()
        adapter_with_mock._storage.load_session = AsyncMock(return_value={"test": True})
        adapter_with_mock._storage.delete_session = AsyncMock(
            side_effect=Exception("Delete error")
        )

        result = await adapter_with_mock.is_available()

        assert result is False


class TestCreateServerlessStorageFactory:
    """Test create_serverless_storage factory function."""

    def test_create_with_default_backend(self):
        """Test factory creates adapter with default 'file' backend."""
        result = create_serverless_storage()

        assert isinstance(result, ServerlessStorageAdapter)
        assert result.backend == "file"

    def test_create_with_memory_backend(self):
        """Test factory creates adapter with 'memory' backend."""
        result = create_serverless_storage(backend="memory")

        assert isinstance(result, ServerlessStorageAdapter)
        assert result.backend == "memory"

    def test_create_with_config(self):
        """Test factory passes config to adapter."""
        config = {"host": "localhost", "port": 6379}
        result = create_serverless_storage(config=config, backend="memory")

        assert isinstance(result, ServerlessStorageAdapter)
        assert result.config == config

    def test_create_with_s3_backend(self):
        """Test factory creates adapter with 's3' backend."""
        result = create_serverless_storage(backend="s3")

        assert isinstance(result, ServerlessStorageAdapter)
        assert result.backend == "s3"


class TestServerlessStorageAdapterProtocolCompliance:
    """Test that ServerlessStorageAdapter properly implements SessionStorage protocol."""

    def test_implements_session_storage_protocol(self):
        """Test that ServerlessStorageAdapter is a subclass of SessionStorage."""
        from session_buddy.backends.base import SessionStorage

        assert issubclass(ServerlessStorageAdapter, SessionStorage)

    def test_has_all_required_methods(self):
        """Test that all required abstract methods are implemented."""
        adapter = ServerlessStorageAdapter()

        assert hasattr(adapter, "store_session")
        assert hasattr(adapter, "retrieve_session")
        assert hasattr(adapter, "delete_session")
        assert hasattr(adapter, "list_sessions")
        assert hasattr(adapter, "cleanup_expired_sessions")
        assert hasattr(adapter, "is_available")

    @pytest.mark.asyncio
    async def test_store_session_is_async(self):
        """Test store_session is an async method."""
        adapter = ServerlessStorageAdapter()
        session_state = SessionState(
            session_id="test",
            user_id="user",
            project_id="project",
            created_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat(),
        )

        # Mock the internal storage
        mock_storage = AsyncMock()
        mock_storage.store_session = AsyncMock()
        adapter._storage = mock_storage

        # Should be awaitable
        result = await adapter.store_session(session_state)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_retrieve_session_is_async(self):
        """Test retrieve_session is an async method."""
        adapter = ServerlessStorageAdapter()
        mock_storage = AsyncMock()
        mock_storage.load_session = AsyncMock(return_value=None)
        adapter._storage = mock_storage

        # Should be awaitable
        result = await adapter.retrieve_session("test-session")
        assert result is None or isinstance(result, SessionState)

    @pytest.mark.asyncio
    async def test_delete_session_is_async(self):
        """Test delete_session is an async method."""
        adapter = ServerlessStorageAdapter()
        mock_storage = AsyncMock()
        mock_storage.delete_session = AsyncMock(return_value=True)
        adapter._storage = mock_storage

        # Should be awaitable
        result = await adapter.delete_session("test-session")
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_list_sessions_is_async(self):
        """Test list_sessions is an async method."""
        adapter = ServerlessStorageAdapter()

        # Should be awaitable
        result = await adapter.list_sessions()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_is_async(self):
        """Test cleanup_expired_sessions is an async method."""
        adapter = ServerlessStorageAdapter()

        # Should be awaitable
        result = await adapter.cleanup_expired_sessions()
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_is_available_is_async(self):
        """Test is_available is an async method."""
        adapter = ServerlessStorageAdapter()
        mock_storage = AsyncMock()
        mock_storage.store_session = AsyncMock()
        mock_storage.load_session = AsyncMock(return_value={})
        mock_storage.delete_session = AsyncMock(return_value=True)
        adapter._storage = mock_storage

        # Should be awaitable
        result = await adapter.is_available()
        assert isinstance(result, bool)