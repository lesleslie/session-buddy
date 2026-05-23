"""Unit tests for storage_oneiric module.

Targeting 60%+ coverage by testing:
- StorageBaseOneiric (file and memory backends)
- FileStorageOneiric, MemoryStorageOneiric
- StorageRegistryOneiric
- SessionStorageAdapter
- Module-level functions
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.adapters.settings import StorageAdapterSettings, default_session_buckets
from session_buddy.adapters import storage_oneiric


class TestStorageBaseOneiricFileBackend:
    """Test StorageBaseOneiric with file backend."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for file storage tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def storage_settings(self, temp_dir):
        """Create StorageAdapterSettings with temp directory."""
        buckets = {
            "test": str(temp_dir / "test"),
            "sessions": str(temp_dir / "sessions"),
        }
        return StorageAdapterSettings(
            default_backend="file",
            buckets=buckets,
            local_path=temp_dir,
        )

    @pytest.fixture
    def file_storage(self, storage_settings):
        """Create a file-based StorageBaseOneiric instance."""
        storage = storage_oneiric.StorageBaseOneiric("file")
        # Manually set settings to avoid _resolve_data_dir() call
        storage.settings = storage_settings
        storage.buckets = storage_settings.buckets
        return storage

    @pytest.mark.asyncio
    async def test_init_creates_bucket_directories(self, file_storage, temp_dir):
        """Test init() creates bucket directories."""
        await file_storage.init()

        assert file_storage._initialized is True
        assert (temp_dir / "test").exists()
        assert (temp_dir / "sessions").exists()

    @pytest.mark.asyncio
    async def test_init_idempotent(self, file_storage, temp_dir):
        """Test init() is idempotent."""
        await file_storage.init()
        await file_storage.init()

        assert file_storage._initialized is True

    @pytest.mark.asyncio
    async def test_upload_download_roundtrip(self, file_storage):
        """Test data can be uploaded and downloaded successfully."""
        await file_storage.init()

        test_data = b"Hello, World!"
        await file_storage.upload("test", "hello.txt", test_data)

        result = await file_storage.download("test", "hello.txt")
        assert result == test_data

    @pytest.mark.asyncio
    async def test_upload_creates_parent_dirs(self, file_storage, temp_dir):
        """Test upload creates parent directories automatically."""
        await file_storage.init()

        test_data = b"nested content"
        await file_storage.upload("test", "nested/path/file.txt", test_data)

        assert (temp_dir / "test" / "nested" / "path" / "file.txt").exists()

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_existing(self, file_storage):
        """Test exists() returns True for existing files."""
        await file_storage.init()
        await file_storage.upload("test", "exists.txt", b"data")

        result = await file_storage.exists("test", "exists.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing(self, file_storage):
        """Test exists() returns False for missing files."""
        await file_storage.init()

        result = await file_storage.exists("test", "nonexistent.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_removes_file(self, file_storage):
        """Test delete() removes a file."""
        await file_storage.init()
        await file_storage.upload("test", "to_delete.txt", b"delete me")

        await file_storage.delete("test", "to_delete.txt")

        assert await file_storage.exists("test", "to_delete.txt") is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_does_not_raise(self, file_storage):
        """Test deleting a non-existent file does not raise."""
        await file_storage.init()

        # Should not raise
        await file_storage.delete("test", "nonexistent.txt")

    @pytest.mark.asyncio
    async def test_download_raises_on_missing(self, file_storage):
        """Test download() raises FileNotFoundError for missing files."""
        await file_storage.init()

        with pytest.raises(FileNotFoundError):
            await file_storage.download("test", "missing.txt")

    @pytest.mark.asyncio
    async def test_stat_returns_metadata(self, file_storage):
        """Test stat() returns correct file metadata."""
        await file_storage.init()
        test_data = b"stat test content"
        await file_storage.upload("test", "stat_file.txt", test_data)

        stat_info = await file_storage.stat("test", "stat_file.txt")

        assert "size" in stat_info
        assert stat_info["size"] == len(test_data)
        assert "mtime" in stat_info
        assert "created" in stat_info

    @pytest.mark.asyncio
    async def test_stat_raises_on_missing(self, file_storage):
        """Test stat() raises FileNotFoundError for missing files."""
        await file_storage.init()

        with pytest.raises(FileNotFoundError):
            await file_storage.stat("test", "missing.txt")

    @pytest.mark.asyncio
    async def test_get_file_path_unknown_bucket(self, file_storage):
        """Test _get_file_path raises ValueError for unknown bucket."""
        await file_storage.init()

        with pytest.raises(ValueError, match="Bucket not configured"):
            file_storage._get_file_path("unknown_bucket", "path.txt")


class TestStorageBaseOneiricMemoryBackend:
    """Test StorageBaseOneiric with memory backend."""

    @pytest.fixture
    def memory_storage(self):
        """Create a memory-based StorageBaseOneiric instance."""
        buckets = {"memtest": "memory", "sessions": "memory"}
        settings = MagicMock(spec=StorageAdapterSettings)
        settings.buckets = buckets
        settings.local_path = Path("/tmp")

        storage = storage_oneiric.StorageBaseOneiric("memory")
        storage.settings = settings
        storage.buckets = buckets
        return storage

    @pytest.mark.asyncio
    async def test_upload_download_roundtrip(self, memory_storage):
        """Test data can be uploaded and downloaded in memory."""
        await memory_storage.init()

        test_data = b"Memory test data"
        await memory_storage.upload("memtest", "memfile.txt", test_data)

        result = await memory_storage.download("memtest", "memfile.txt")
        assert result == test_data

    @pytest.mark.asyncio
    async def test_upload_overwrites_existing(self, memory_storage):
        """Test uploading to same path overwrites existing data."""
        await memory_storage.init()

        await memory_storage.upload("memtest", "overwrite.txt", b"first")
        await memory_storage.upload("memtest", "overwrite.txt", b"second")

        result = await memory_storage.download("memtest", "overwrite.txt")
        assert result == b"second"

    @pytest.mark.asyncio
    async def test_exists_in_memory(self, memory_storage):
        """Test exists() works correctly in memory backend."""
        await memory_storage.init()

        assert await memory_storage.exists("memtest", "newfile.txt") is False

        await memory_storage.upload("memtest", "newfile.txt", b"data")
        assert await memory_storage.exists("memtest", "newfile.txt") is True

    @pytest.mark.asyncio
    async def test_delete_from_memory(self, memory_storage):
        """Test delete() removes data from memory."""
        await memory_storage.init()
        await memory_storage.upload("memtest", "delete_me.txt", b"data")

        await memory_storage.delete("memtest", "delete_me.txt")

        assert await memory_storage.exists("memtest", "delete_me.txt") is False

    @pytest.mark.asyncio
    async def test_download_raises_on_missing_memory(self, memory_storage):
        """Test download() raises FileNotFoundError for missing memory data."""
        await memory_storage.init()

        with pytest.raises(FileNotFoundError):
            await memory_storage.download("memtest", "missing.txt")

    @pytest.mark.asyncio
    async def test_stat_memory_returns_metadata(self, memory_storage):
        """Test stat() returns correct metadata for memory storage."""
        await memory_storage.init()
        test_data = b"stat memory data"
        await memory_storage.upload("memtest", "statmem.txt", test_data)

        stat_info = await memory_storage.stat("memtest", "statmem.txt")

        assert "size" in stat_info
        assert stat_info["size"] == len(test_data)
        assert "mtime" in stat_info
        assert "created" in stat_info


class TestFileStorageOneiric:
    """Test FileStorageOneiric class."""

    def test_init_sets_file_backend(self):
        """Test FileStorageOneiric initializes with file backend."""
        settings = MagicMock(spec=StorageAdapterSettings)
        settings.buckets = {"test": "/tmp/test"}
        settings.local_path = Path("/tmp")

        storage = storage_oneiric.FileStorageOneiric(settings)

        assert storage.backend == "file"
        assert storage.settings is settings

    def test_init_with_none_settings(self):
        """Test FileStorageOneiric works with None settings (uses defaults)."""
        # Mock from_settings to return a valid settings object
        with patch.object(StorageAdapterSettings, "from_settings") as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.buckets = {"default": "/tmp/default"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            storage = storage_oneiric.FileStorageOneiric(None)

            assert storage.backend == "file"


class TestMemoryStorageOneiric:
    """Test MemoryStorageOneiric class."""

    def test_init_sets_memory_backend(self):
        """Test MemoryStorageOneiric initializes with memory backend."""
        settings = MagicMock(spec=StorageAdapterSettings)
        settings.buckets = {"mem": "memory"}
        settings.local_path = Path("/tmp")

        storage = storage_oneiric.MemoryStorageOneiric(settings)

        assert storage.backend == "memory"
        assert storage.settings is settings
        assert storage._memory_store == {}


class TestStorageRegistryOneiric:
    """Test StorageRegistryOneiric class."""

    def test_init_creates_empty_adapters(self):
        """Test StorageRegistryOneiric initializes with empty adapters."""
        registry = storage_oneiric.StorageRegistryOneiric()

        assert registry._adapters == {}
        assert registry._settings is None

    @pytest.mark.asyncio
    async def test_init_sets_settings(self):
        """Test init() initializes settings."""
        registry = storage_oneiric.StorageRegistryOneiric()

        with patch.object(StorageAdapterSettings, "from_settings") as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_from.return_value = mock_settings

            await registry.init()

            assert registry._settings is not None

    def test_validate_backend_accepts_valid(self):
        """Test _validate_backend accepts valid backends."""
        registry = storage_oneiric.StorageRegistryOneiric()

        # Should not raise
        registry._validate_backend("file")
        registry._validate_backend("memory")

    def test_validate_backend_rejects_invalid(self):
        """Test _validate_backend rejects invalid backends."""
        registry = storage_oneiric.StorageRegistryOneiric()

        with pytest.raises(ValueError, match="Unsupported backend"):
            registry._validate_backend("invalid_backend")

    def test_create_adapter_file(self):
        """Test _create_adapter creates file adapter."""
        registry = storage_oneiric.StorageRegistryOneiric()
        registry._settings = MagicMock(spec=StorageAdapterSettings)

        adapter = registry._create_adapter("file")

        assert isinstance(adapter, storage_oneiric.FileStorageOneiric)

    def test_create_adapter_memory(self):
        """Test _create_adapter creates memory adapter."""
        registry = storage_oneiric.StorageRegistryOneiric()
        registry._settings = MagicMock(spec=StorageAdapterSettings)

        adapter = registry._create_adapter("memory")

        assert isinstance(adapter, storage_oneiric.MemoryStorageOneiric)

    def test_create_adapter_unknown_raises(self):
        """Test _create_adapter raises for unknown backend."""
        registry = storage_oneiric.StorageRegistryOneiric()
        registry._settings = MagicMock(spec=StorageAdapterSettings)

        with pytest.raises(ValueError, match="Unsupported backend"):
            registry._create_adapter("unknown")

    def test_register_storage_adapter_new(self):
        """Test registering a new storage adapter."""
        registry = storage_oneiric.StorageRegistryOneiric()

        with patch.object(StorageAdapterSettings, "from_settings") as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.buckets = {"test": "/tmp/test"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            adapter = registry.register_storage_adapter("memory")

            assert adapter is not None
            assert "memory" in registry._adapters

    def test_register_storage_adapter_reuses_existing(self):
        """Test registering same backend reuses existing adapter."""
        registry = storage_oneiric.StorageRegistryOneiric()

        with patch.object(StorageAdapterSettings, "from_settings") as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.buckets = {"mem": "memory"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            adapter1 = registry.register_storage_adapter("memory")
            adapter2 = registry.register_storage_adapter("memory")

            assert adapter1 is adapter2

    def test_register_storage_adapter_force(self):
        """Test force=True creates new adapter even if exists."""
        registry = storage_oneiric.StorageRegistryOneiric()

        with patch.object(StorageAdapterSettings, "from_settings") as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.buckets = {"mem": "memory"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            adapter1 = registry.register_storage_adapter("memory")
            adapter2 = registry.register_storage_adapter("memory", force=True)

            assert adapter1 is not adapter2

    def test_apply_config_overrides_with_buckets(self):
        """Test _apply_config_overrides applies bucket overrides."""
        # Create a real StorageAdapterSettings dataclass for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            buckets = {"old": str(Path(tmpdir) / "old")}
            settings = StorageAdapterSettings(
                default_backend="file",
                buckets=buckets,
                local_path=Path(tmpdir),
            )

            adapter = storage_oneiric.FileStorageOneiric(settings)
            overrides = {"buckets": {"new": str(Path(tmpdir) / "new")}}

            registry = storage_oneiric.StorageRegistryOneiric()
            registry._apply_config_overrides(adapter, overrides)

            assert adapter.buckets["new"] == str(Path(tmpdir) / "new")

    def test_prepare_overrides_converts_paths(self):
        """Test _prepare_overrides converts string paths to Path objects."""
        registry = storage_oneiric.StorageRegistryOneiric()

        adapter = MagicMock()
        adapter.settings = MagicMock(spec=StorageAdapterSettings)

        overrides = registry._prepare_overrides(
            adapter, {"local_path": "/tmp/test"}
        )

        assert overrides["local_path"] == Path("/tmp/test")

    def test_get_storage_adapter_auto_register(self):
        """Test get_storage_adapter auto-registers if not found."""
        registry = storage_oneiric.StorageRegistryOneiric()

        with patch.object(StorageAdapterSettings, "from_settings") as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.default_backend = "memory"
            mock_settings.buckets = {"mem": "memory"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            adapter = registry.get_storage_adapter("memory")

            assert adapter is not None
            assert "memory" in registry._adapters

    def test_configure_storage_buckets(self):
        """Test configure_storage_buckets updates buckets."""
        registry = storage_oneiric.StorageRegistryOneiric()

        with patch.object(StorageAdapterSettings, "from_settings") as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.buckets = {"existing": "/tmp/existing"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            new_buckets = {"new_bucket": "/tmp/new_bucket"}
            registry.configure_storage_buckets(new_buckets)

            assert registry._settings.buckets["new_bucket"] == "/tmp/new_bucket"


class TestSessionStorageAdapter:
    """Test SessionStorageAdapter class."""

    @pytest.fixture
    def mock_storage(self):
        """Create a mock storage protocol."""
        mock = AsyncMock()
        mock.init = AsyncMock()
        mock.upload = AsyncMock()
        mock.download = AsyncMock(return_value=b'{"data": "test"}')
        mock.delete = AsyncMock()
        mock.exists = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def session_adapter(self, mock_storage):
        """Create a SessionStorageAdapter with mocked storage."""
        adapter = storage_oneiric.SessionStorageAdapter(backend="memory")
        adapter._storage = mock_storage
        adapter._initialized = True
        return adapter

    @pytest.mark.asyncio
    async def test_initialize(self, mock_storage):
        """Test initialize() initializes storage."""
        with patch.object(
            storage_oneiric, "get_storage_registry"
        ) as mock_registry:
            registry = MagicMock()
            registry.get_storage_adapter.return_value = mock_storage
            mock_registry.return_value = registry

            adapter = storage_oneiric.SessionStorageAdapter(backend="memory")
            await adapter.initialize()

            mock_storage.init.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_delegates_to_storage(self, session_adapter, mock_storage):
        """Test upload() delegates to underlying storage."""
        await session_adapter.upload("bucket", "path.txt", b"data")

        mock_storage.upload.assert_called_once_with("bucket", "path.txt", b"data")

    @pytest.mark.asyncio
    async def test_download_delegates_to_storage(self, session_adapter, mock_storage):
        """Test download() delegates to underlying storage."""
        result = await session_adapter.download("bucket", "path.txt")

        mock_storage.download.assert_called_once_with("bucket", "path.txt")
        assert result == b'{"data": "test"}'

    @pytest.mark.asyncio
    async def test_delete_delegates_to_storage(self, session_adapter, mock_storage):
        """Test delete() delegates to underlying storage."""
        await session_adapter.delete("bucket", "path.txt")

        mock_storage.delete.assert_called_once_with("bucket", "path.txt")

    @pytest.mark.asyncio
    async def test_exists_delegates_to_storage(self, session_adapter, mock_storage):
        """Test exists() delegates to underlying storage."""
        result = await session_adapter.exists("bucket", "path.txt")

        mock_storage.exists.assert_called_once_with("bucket", "path.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_upload_initializes_if_needed(self, mock_storage):
        """Test upload() initializes storage if not initialized."""
        with patch.object(
            storage_oneiric, "get_storage_registry"
        ) as mock_registry:
            registry = MagicMock()
            registry.get_storage_adapter.return_value = mock_storage
            mock_registry.return_value = registry

            adapter = storage_oneiric.SessionStorageAdapter(backend="memory")
            await adapter.upload("bucket", "path.txt", b"data")

            mock_storage.init.assert_called_once()


class TestModuleFunctions:
    """Test module-level functions."""

    @pytest.fixture
    def clean_registry(self):
        """Reset the global registry before and after tests."""
        original_registry = storage_oneiric._storage_registry
        storage_oneiric._storage_registry = storage_oneiric.StorageRegistryOneiric()
        yield
        storage_oneiric._storage_registry = original_registry

    def test_init_storage_registry(self, clean_registry):
        """Test init_storage_registry() initializes the global registry."""
        with patch.object(
            StorageAdapterSettings, "from_settings"
        ) as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.buckets = {"test": "/tmp/test"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            storage_oneiric.init_storage_registry()

            assert storage_oneiric._storage_registry._settings is not None

    def test_get_storage_registry_returns_global(self, clean_registry):
        """Test get_storage_registry() returns the global registry."""
        registry = storage_oneiric.get_storage_registry()
        assert registry is storage_oneiric._storage_registry

    def test_get_storage_adapter_delegates_to_registry(self, clean_registry):
        """Test get_storage_adapter() delegates to registry."""
        with patch.object(
            StorageAdapterSettings, "from_settings"
        ) as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.default_backend = "memory"
            mock_settings.buckets = {"mem": "memory"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            adapter = storage_oneiric.get_storage_adapter("memory")
            assert adapter is not None

    def test_configure_storage_buckets_delegates_to_registry(
        self, clean_registry
    ):
        """Test configure_storage_buckets() delegates to registry."""
        with patch.object(
            StorageAdapterSettings, "from_settings"
        ) as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.buckets = {}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            storage_oneiric.configure_storage_buckets({"new": "/tmp/new"})

            assert "new" in storage_oneiric._storage_registry._settings.buckets

    def test_register_storage_adapter_delegates_to_registry(
        self, clean_registry
    ):
        """Test register_storage_adapter() delegates to registry."""
        with patch.object(
            StorageAdapterSettings, "from_settings"
        ) as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.default_backend = "memory"
            mock_settings.buckets = {"mem": "memory"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            adapter = storage_oneiric.register_storage_adapter("memory")
            assert adapter is not None

    def test_get_default_storage_adapter(self):
        """Test get_default_storage_adapter() returns SessionStorageAdapter."""
        adapter = storage_oneiric.get_default_storage_adapter()
        assert isinstance(adapter, storage_oneiric.SessionStorageAdapter)
        assert adapter.backend == "file"

    def test_get_default_session_buckets(self):
        """Test get_default_session_buckets() returns expected structure."""
        buckets = storage_oneiric.get_default_session_buckets()
        assert "default" in buckets
        assert "sessions" in buckets
        assert "cache" in buckets
        assert buckets["default"] == storage_oneiric.DEFAULT_SESSION_BUCKET

    def test_supported_backends(self):
        """Test SUPPORTED_BACKENDS contains expected backends."""
        assert "file" in storage_oneiric.SUPPORTED_BACKENDS
        assert "memory" in storage_oneiric.SUPPORTED_BACKENDS


class TestStorageBaseOneiricEdgeCases:
    """Test edge cases for StorageBaseOneiric."""

    @pytest.fixture
    def storage(self):
        """Create StorageBaseOneiric for edge case testing."""
        buckets = {"test": "/tmp/test"}
        settings = MagicMock(spec=StorageAdapterSettings)
        settings.buckets = buckets
        settings.local_path = Path("/tmp")
        storage = storage_oneiric.StorageBaseOneiric("file")
        storage.settings = settings
        storage.buckets = buckets
        return storage

    @pytest.mark.asyncio
    async def test_unsupported_backend_raises(self, storage):
        """Test unsupported backend raises ValueError."""
        storage.backend = "invalid"
        storage._initialized = True

        with pytest.raises(ValueError, match="Unsupported backend"):
            await storage.upload("test", "path.txt", b"data")

    @pytest.mark.asyncio
    async def test_init_twice_is_idempotent(self, storage):
        """Test calling init() twice is idempotent."""
        await storage.init()
        await storage.init()

        assert storage._initialized is True

    @pytest.mark.asyncio
    async def test_download_unknown_bucket_raises(self, storage):
        """Test download with unknown bucket raises ValueError."""
        await storage.init()

        with pytest.raises(ValueError, match="Bucket not configured"):
            await storage.download("unknown_bucket", "path.txt")

    @pytest.mark.asyncio
    async def test_delete_unknown_bucket_raises(self, storage):
        """Test delete with unknown bucket raises ValueError."""
        await storage.init()

        with pytest.raises(ValueError, match="Bucket not configured"):
            await storage.delete("unknown_bucket", "path.txt")

    @pytest.mark.asyncio
    async def test_exists_unknown_bucket_raises(self, storage):
        """Test exists with unknown bucket raises ValueError."""
        await storage.init()

        with pytest.raises(ValueError, match="Bucket not configured"):
            await storage.exists("unknown_bucket", "path.txt")

    @pytest.mark.asyncio
    async def test_stat_unknown_bucket_raises(self, storage):
        """Test stat with unknown bucket raises ValueError."""
        await storage.init()

        with pytest.raises(ValueError, match="Bucket not configured"):
            await storage.stat("unknown_bucket", "path.txt")


class TestInitializeSync:
    """Test synchronous initialization methods."""

    @pytest.fixture
    def storage(self):
        """Create StorageBaseOneiric for sync init testing."""
        buckets = {"test": "/tmp/test", "sessions": "/tmp/sessions"}
        settings = MagicMock(spec=StorageAdapterSettings)
        settings.buckets = buckets
        settings.local_path = Path("/tmp")
        storage = storage_oneiric.StorageBaseOneiric("file")
        storage.settings = settings
        storage.buckets = buckets
        return storage

    def test_initialize_sync(self, storage):
        """Test _initialize_sync() works synchronously."""
        storage._initialize_sync()

        assert storage._initialized is True

    def test_initialize_sync_twice_is_idempotent(self, storage):
        """Test _initialize_sync() called twice is idempotent."""
        storage._initialize_sync()
        storage._initialize_sync()

        assert storage._initialized is True

    def test_registry_initialize_sync(self):
        """Test StorageRegistryOneiric._initialize_sync()."""
        registry = storage_oneiric.StorageRegistryOneiric()

        with patch.object(StorageAdapterSettings, "from_settings") as mock_from:
            mock_settings = MagicMock(spec=StorageAdapterSettings)
            mock_settings.buckets = {"test": "/tmp/test"}
            mock_settings.local_path = Path("/tmp")
            mock_from.return_value = mock_settings

            registry._initialize_sync()

            assert registry._settings is not None


class TestAclse:
    """Test aclose() method."""

    @pytest.mark.asyncio
    async def test_aclose_no_cleanup_needed(self):
        """Test aclose() doesn't require cleanup for file storage."""
        storage = storage_oneiric.StorageBaseOneiric("file")
        # Should not raise
        await storage.aclose()