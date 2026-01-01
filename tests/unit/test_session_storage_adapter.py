"""Unit tests for SessionStorageAdapter.

Tests the session storage adapter facade with memory backend for fast,
isolated testing without external dependencies.

Phase 1, Day 1: Storage adapter foundation
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from session_buddy.adapters import (
    SessionStorageAdapter,
    get_default_storage_adapter,
)
from session_buddy.adapters.session_storage_adapter import DEFAULT_SESSION_BUCKET


class TestSessionStorageAdapterInitialization:
    """Test SessionStorageAdapter initialization and configuration."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        adapter = SessionStorageAdapter()

        assert adapter.backend == "file"
        assert adapter.bucket == DEFAULT_SESSION_BUCKET
        assert adapter._adapter is None
        assert adapter._initialized is False

    def test_init_with_custom_backend(self):
        """Test initialization with custom backend."""
        adapter = SessionStorageAdapter(backend="memory")

        assert adapter.backend == "memory"
        assert adapter.bucket == DEFAULT_SESSION_BUCKET

    def test_init_with_custom_bucket(self):
        """Test initialization with custom bucket."""
        adapter = SessionStorageAdapter(bucket="custom_sessions")

        assert adapter.backend == "file"
        assert adapter.bucket == "custom_sessions"

    def test_get_session_path_default(self):
        """Test session path construction with default filename."""
        adapter = SessionStorageAdapter()
        path = adapter._get_session_path("session_123")

        assert path == "session_123/state.json"

    def test_get_session_path_custom(self):
        """Test session path construction with custom filename."""
        adapter = SessionStorageAdapter()
        path = adapter._get_session_path("session_123", "checkpoint.json")

        assert path == "session_123/checkpoint.json"


class TestSessionStorageAdapterOperations:
    """Test SessionStorageAdapter CRUD operations."""

    @pytest.fixture
    def mock_storage_adapter(self):
        """Create a mock storage adapter."""
        mock = AsyncMock()
        mock.init = AsyncMock()
        mock.upload = AsyncMock()
        mock.download = AsyncMock()
        mock.delete = AsyncMock()
        mock.exists = AsyncMock(return_value=True)
        mock.stat = AsyncMock()
        return mock

    @pytest.fixture
    def adapter_with_mock(self, mock_storage_adapter):
        """Create SessionStorageAdapter with mocked backend."""
        adapter = SessionStorageAdapter(backend="memory")
        adapter._adapter = mock_storage_adapter
        adapter._initialized = True
        return adapter

    async def test_store_session_basic(self, adapter_with_mock, mock_storage_adapter):
        """Test storing basic session state."""
        session_id = "test_session_123"
        state = {"status": "active", "user": "test_user"}

        await adapter_with_mock.store_session(session_id, state)

        # Verify upload was called
        mock_storage_adapter.upload.assert_called_once()
        call_args = mock_storage_adapter.upload.call_args

        # Check bucket and path
        assert call_args[0][0] == DEFAULT_SESSION_BUCKET
        assert call_args[0][1] == "test_session_123/state.json"

        # Check data format
        data = call_args[0][2]
        parsed = json.loads(data.decode("utf-8"))

        assert parsed["status"] == "active"
        assert parsed["user"] == "test_user"
        assert "_metadata" in parsed
        assert parsed["_metadata"]["session_id"] == session_id
        assert parsed["_metadata"]["backend"] == "memory"
        assert "stored_at" in parsed["_metadata"]

    async def test_store_session_custom_filename(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test storing session with custom filename."""
        session_id = "test_session_123"
        state = {"checkpoint": 1}

        await adapter_with_mock.store_session(
            session_id, state, filename="checkpoint_001.json"
        )

        # Verify correct path
        call_args = mock_storage_adapter.upload.call_args
        assert call_args[0][1] == "test_session_123/checkpoint_001.json"

    async def test_store_session_invalid_json(self, adapter_with_mock):
        """Test storing non-JSON-serializable state raises ValueError."""

        class NonSerializable:
            pass

        session_id = "test_session_123"
        state = {"obj": NonSerializable()}

        with pytest.raises(ValueError, match="Failed to serialize"):
            await adapter_with_mock.store_session(session_id, state)

    async def test_load_session_success(self, adapter_with_mock, mock_storage_adapter):
        """Test loading existing session."""
        session_id = "test_session_123"
        stored_state = {
            "status": "active",
            "_metadata": {"session_id": session_id},
        }

        # Mock download to return stored state
        mock_file = MagicMock()
        mock_file.read = MagicMock(
            return_value=json.dumps(stored_state).encode("utf-8")
        )
        mock_storage_adapter.download = AsyncMock(return_value=mock_file)

        result = await adapter_with_mock.load_session(session_id)

        assert result is not None
        assert result["status"] == "active"
        assert result["_metadata"]["session_id"] == session_id

    async def test_load_session_not_found(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test loading non-existent session returns None."""
        mock_storage_adapter.exists = AsyncMock(return_value=False)

        result = await adapter_with_mock.load_session("nonexistent_session")

        assert result is None

    async def test_load_session_file_not_found_exception(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test loading session that raises FileNotFoundError returns None."""
        mock_storage_adapter.exists = AsyncMock(return_value=True)
        mock_storage_adapter.download = AsyncMock(side_effect=FileNotFoundError())

        result = await adapter_with_mock.load_session("missing_session")

        assert result is None

    async def test_load_session_invalid_json(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test loading session with invalid JSON raises ValueError."""
        mock_file = MagicMock()
        mock_file.read = MagicMock(return_value=b"invalid json {]")
        mock_storage_adapter.download = AsyncMock(return_value=mock_file)

        with pytest.raises(ValueError, match="Failed to parse"):
            await adapter_with_mock.load_session("test_session")

    async def test_delete_session_success(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test deleting existing session."""
        session_id = "test_session_123"

        result = await adapter_with_mock.delete_session(session_id)

        assert result is True
        mock_storage_adapter.delete.assert_called_once_with(
            DEFAULT_SESSION_BUCKET, "test_session_123/state.json"
        )

    async def test_delete_session_not_found(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test deleting non-existent session returns False."""
        mock_storage_adapter.delete = AsyncMock(side_effect=FileNotFoundError())

        result = await adapter_with_mock.delete_session("nonexistent_session")

        assert result is False

    async def test_delete_session_specific_file(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test deleting specific session file."""
        session_id = "test_session_123"
        filename = "checkpoint_001.json"

        result = await adapter_with_mock.delete_session(session_id, filename=filename)

        assert result is True
        mock_storage_adapter.delete.assert_called_once_with(
            DEFAULT_SESSION_BUCKET, "test_session_123/checkpoint_001.json"
        )

    async def test_session_exists_true(self, adapter_with_mock, mock_storage_adapter):
        """Test session_exists returns True for existing session."""
        mock_storage_adapter.exists = AsyncMock(return_value=True)

        result = await adapter_with_mock.session_exists("test_session_123")

        assert result is True

    async def test_session_exists_false(self, adapter_with_mock, mock_storage_adapter):
        """Test session_exists returns False for non-existent session."""
        mock_storage_adapter.exists = AsyncMock(return_value=False)

        result = await adapter_with_mock.session_exists("nonexistent_session")

        assert result is False

    async def test_session_exists_error_handling(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test session_exists returns False on error."""
        mock_storage_adapter.exists = AsyncMock(side_effect=Exception("Storage error"))

        result = await adapter_with_mock.session_exists("test_session")

        assert result is False

    async def test_get_session_metadata_success(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test getting session metadata."""
        session_id = "test_session_123"
        mock_storage_adapter.stat = AsyncMock(
            return_value={
                "size": 1024,
                "updated": "2025-01-16T10:00:00Z",
                "timeCreated": "2025-01-16T09:00:00Z",
            }
        )

        metadata = await adapter_with_mock.get_session_metadata(session_id)

        assert metadata is not None
        assert metadata["session_id"] == session_id
        assert metadata["size"] == 1024
        assert metadata["modified"] == "2025-01-16T10:00:00Z"
        assert metadata["created"] == "2025-01-16T09:00:00Z"
        assert metadata["backend"] == "memory"

    async def test_get_session_metadata_not_found(
        self, adapter_with_mock, mock_storage_adapter
    ):
        """Test getting metadata for non-existent session returns None."""
        mock_storage_adapter.stat = AsyncMock(side_effect=FileNotFoundError())

        metadata = await adapter_with_mock.get_session_metadata("nonexistent_session")

        assert metadata is None

    async def test_list_sessions_placeholder(self, adapter_with_mock):
        """Test list_sessions returns empty list (placeholder implementation)."""
        sessions = await adapter_with_mock.list_sessions()

        # Current implementation returns empty list
        # TODO: Update test when list_sessions is implemented
        assert sessions == []


class TestAdapterInitialization:
    """Test adapter initialization and lifecycle."""

    @pytest.fixture
    def mock_get_storage_adapter(self):
        """Mock get_storage_adapter function."""
        with patch(
            "session_buddy.adapters.storage_registry.get_storage_adapter"
        ) as mock:
            mock_adapter = AsyncMock()
            mock_adapter.init = AsyncMock()
            mock.return_value = mock_adapter
            yield mock

    async def test_ensure_adapter_initialization(self, mock_get_storage_adapter):
        """Test adapter is initialized on first use."""
        adapter = SessionStorageAdapter(backend="file")

        assert adapter._adapter is None
        assert adapter._initialized is False

        # Trigger initialization
        await adapter._ensure_adapter()

        assert adapter._adapter is not None
        assert adapter._initialized is True
        mock_get_storage_adapter.assert_called_once_with("file")
        adapter._adapter.init.assert_called_once()

    async def test_ensure_adapter_idempotent(self, mock_get_storage_adapter):
        """Test adapter initialization is idempotent."""
        adapter = SessionStorageAdapter(backend="file")

        # Call twice
        await adapter._ensure_adapter()
        await adapter._ensure_adapter()

        # Should only initialize once
        mock_get_storage_adapter.assert_called_once()
        adapter._adapter.init.assert_called_once()


class TestDefaultStorageAdapter:
    """Test get_default_storage_adapter function."""

    def test_get_default_storage_adapter_fallback(self):
        """Test get_default_storage_adapter falls back to file."""
        adapter = get_default_storage_adapter()

        assert isinstance(adapter, SessionStorageAdapter)
        assert adapter.backend == "file"

    def test_get_default_storage_adapter_from_settings(self):
        """Test get_default_storage_adapter uses settings."""
        # This test verifies that the function works with the actual settings
        adapter = get_default_storage_adapter()

        assert isinstance(adapter, SessionStorageAdapter)
        # By default, it should use 'file' backend
        assert adapter.backend == "file"
