"""Oneiric-compatible storage adapters using native implementations.

Provides Oneiric-compatible storage adapters that maintain the existing StorageBase
API while using native implementations instead of ACB storage adapters.

Phase 5: Oneiric Adapter Conversion - Storage Registry

Key Features:
    - Native file system storage implementation
    - Oneiric settings and lifecycle management
    - Backward-compatible API with existing StorageBase
    - No ACB dependencies
    - Support for multiple backends (file, memory)

"""

from __future__ import annotations

import typing as t
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from session_buddy.adapters.settings import StorageAdapterSettings

if t.TYPE_CHECKING:
    pass


class StorageProtocol(t.Protocol):
    """Protocol for storage backend implementations."""

    async def init(self) -> None: ...

    async def upload(self, bucket: str, path: str, data: bytes) -> None: ...

    async def download(self, bucket: str, path: str) -> bytes: ...

    async def delete(self, bucket: str, path: str) -> None: ...

    async def exists(self, bucket: str, path: str) -> bool: ...


# Supported storage backend types
SUPPORTED_BACKENDS = ("file", "memory")


class StorageBaseOneiric:
    """Base class for Oneiric storage adapters.

    This class provides the same interface as ACB's StorageBase but uses
    native implementations instead of ACB dependencies.

    """

    def __init__(self, backend: str):
        """Initialize storage adapter.

        Args:
            backend: Storage backend type (file, memory)

        """
        self.backend = backend
        self.settings = StorageAdapterSettings.from_settings()
        self.buckets: dict[str, str] = self.settings.buckets
        self._initialized = False
        self._memory_store: dict[str, bytes] = {}

    async def init(self) -> None:
        """Initialize storage adapter."""
        if self._initialized:
            return

        # Create base directory for file storage
        if self.backend == "file":
            base_path = self.settings.local_path
            base_path.mkdir(parents=True, exist_ok=True)

            # Create bucket directories
            for bucket_path in self.buckets.values():
                if bucket_path.startswith("/"):
                    # Absolute path
                    bucket_dir = Path(bucket_path)
                else:
                    # Relative path
                    bucket_dir = base_path / bucket_path
                bucket_dir.mkdir(parents=True, exist_ok=True)

        self._initialized = True

    def _initialize_sync(self) -> None:
        """Synchronous version of init for use in synchronous contexts."""
        if self._initialized:
            return

        # Create base directory for file storage
        if self.backend == "file":
            base_path = self.settings.local_path
            base_path.mkdir(parents=True, exist_ok=True)

            # Create bucket directories
            for bucket_path in self.buckets.values():
                if bucket_path.startswith("/"):
                    # Absolute path
                    bucket_dir = Path(bucket_path)
                else:
                    # Relative path
                    bucket_dir = base_path / bucket_path
                bucket_dir.mkdir(parents=True, exist_ok=True)

        self._initialized = True

    async def aclose(self) -> None:
        """Clean up storage adapter."""
        # No cleanup needed for file storage

    async def upload(self, bucket: str, path: str, data: bytes) -> None:
        """Upload data to storage.

        Args:
            bucket: Bucket name
            path: Storage path within bucket
            data: Data to upload

        """
        if not self._initialized:
            await self.init()

        if self.backend == "file":
            await self._file_upload(bucket, path, data)
        elif self.backend == "memory":
            await self._memory_upload(bucket, path, data)
        else:
            msg = f"Unsupported backend: {self.backend}"
            raise ValueError(msg)

    async def download(self, bucket: str, path: str) -> bytes:
        """Download data from storage.

        Args:
            bucket: Bucket name
            path: Storage path within bucket

        Returns:
            Downloaded data as bytes

        """
        if not self._initialized:
            await self.init()

        if self.backend == "file":
            return await self._file_download(bucket, path)
        if self.backend == "memory":
            return await self._memory_download(bucket, path)
        msg = f"Unsupported backend: {self.backend}"
        raise ValueError(msg)

    async def delete(self, bucket: str, path: str) -> None:
        """Delete data from storage.

        Args:
            bucket: Bucket name
            path: Storage path within bucket

        """
        if not self._initialized:
            await self.init()

        if self.backend == "file":
            await self._file_delete(bucket, path)
        elif self.backend == "memory":
            await self._memory_delete(bucket, path)
        else:
            msg = f"Unsupported backend: {self.backend}"
            raise ValueError(msg)

    async def exists(self, bucket: str, path: str) -> bool:
        """Check if data exists in storage.

        Args:
            bucket: Bucket name
            path: Storage path within bucket

        Returns:
            True if data exists, False otherwise

        """
        if not self._initialized:
            await self.init()

        if self.backend == "file":
            return await self._file_exists(bucket, path)
        if self.backend == "memory":
            return await self._memory_exists(bucket, path)
        msg = f"Unsupported backend: {self.backend}"
        raise ValueError(msg)

    async def stat(self, bucket: str, path: str) -> dict[str, t.Any]:
        """Get file statistics.

        Args:
            bucket: Bucket name
            path: Storage path within bucket

        Returns:
            Dictionary with file statistics

        """
        if not self._initialized:
            await self.init()

        if self.backend == "file":
            return await self._file_stat(bucket, path)
        if self.backend == "memory":
            return await self._memory_stat(bucket, path)
        msg = f"Unsupported backend: {self.backend}"
        raise ValueError(msg)

    # File storage implementation
    async def _file_upload(self, bucket: str, path: str, data: bytes) -> None:
        """Upload data to file storage."""
        file_path = self._get_file_path(bucket, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)

    async def _file_download(self, bucket: str, path: str) -> bytes:
        """Download data from file storage."""
        file_path = self._get_file_path(bucket, path)
        if not file_path.exists():
            msg = f"File not found: {path} in bucket {bucket}"
            raise FileNotFoundError(msg)
        return file_path.read_bytes()

    async def _file_delete(self, bucket: str, path: str) -> None:
        """Delete data from file storage."""
        file_path = self._get_file_path(bucket, path)
        if file_path.exists():
            file_path.unlink()

    async def _file_exists(self, bucket: str, path: str) -> bool:
        """Check if data exists in file storage."""
        file_path = self._get_file_path(bucket, path)
        return file_path.exists()

    async def _file_stat(self, bucket: str, path: str) -> dict[str, t.Any]:
        """Get file statistics for file storage."""
        file_path = self._get_file_path(bucket, path)
        if not file_path.exists():
            msg = f"File not found: {path} in bucket {bucket}"
            raise FileNotFoundError(msg)

        stat_info = file_path.stat()
        return {
            "size": stat_info.st_size,
            "mtime": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
        }

    def _get_file_path(self, bucket: str, path: str) -> Path:
        """Get full file path for storage."""
        if bucket not in self.buckets:
            msg = f"Bucket not configured: {bucket}"
            raise ValueError(msg)

        bucket_path = self.buckets[bucket]
        if bucket_path.startswith("/"):
            # Absolute path
            base_path = Path(bucket_path)
        else:
            # Relative path
            base_path = self.settings.local_path / bucket_path

        return base_path / path

    async def _memory_upload(self, bucket: str, path: str, data: bytes) -> None:
        """Upload data to memory storage."""
        key = self._get_memory_key(bucket, path)
        self._memory_store[key] = data

    async def _memory_download(self, bucket: str, path: str) -> bytes:
        """Download data from memory storage."""
        key = self._get_memory_key(bucket, path)
        if key not in self._memory_store:
            msg = f"File not found: {path} in bucket {bucket}"
            raise FileNotFoundError(msg)
        return self._memory_store[key]

    async def _memory_delete(self, bucket: str, path: str) -> None:
        """Delete data from memory storage."""
        key = self._get_memory_key(bucket, path)
        if key in self._memory_store:
            del self._memory_store[key]

    async def _memory_exists(self, bucket: str, path: str) -> bool:
        """Check if data exists in memory storage."""
        key = self._get_memory_key(bucket, path)
        return key in self._memory_store

    async def _memory_stat(self, bucket: str, path: str) -> dict[str, t.Any]:
        """Get file statistics for memory storage."""
        key = self._get_memory_key(bucket, path)
        if key not in self._memory_store:
            msg = f"File not found: {path} in bucket {bucket}"
            raise FileNotFoundError(msg)

        data = self._memory_store[key]
        return {
            "size": len(data),
            "mtime": datetime.now().isoformat(),
            "created": datetime.now().isoformat(),
        }

    def _get_memory_key(self, bucket: str, path: str) -> str:
        """Get memory storage key."""
        return f"{bucket}/{path}"


class FileStorageOneiric(StorageBaseOneiric):
    """Oneiric-compatible file storage adapter."""

    def __init__(self, settings: StorageAdapterSettings | None = None):
        self.backend = "file"
        self.settings = settings or StorageAdapterSettings.from_settings()
        self.buckets: dict[str, str] = self.settings.buckets
        self._initialized = False


class MemoryStorageOneiric(StorageBaseOneiric):
    """Oneiric-compatible memory storage adapter."""

    def __init__(self, settings: StorageAdapterSettings | None = None):
        self.backend = "memory"
        self.settings = settings or StorageAdapterSettings.from_settings()
        self.buckets: dict[str, str] = self.settings.buckets
        self._initialized = False
        self._memory_store: dict[str, bytes] = {}


class StorageRegistryOneiric:
    """Oneiric-compatible storage registry.

    This registry provides the same interface as the ACB storage registry
    but uses native Oneiric implementations instead of ACB adapters.

    """

    def __init__(self) -> None:
        self._adapters: dict[str, StorageBaseOneiric] = {}
        self._settings: StorageAdapterSettings | None = None

    async def init(self) -> None:
        """Initialize storage registry."""
        self._settings = StorageAdapterSettings.from_settings()

    def _initialize_sync(self) -> None:
        """Synchronous version of init for storage registry."""
        self._settings = StorageAdapterSettings.from_settings()

    def register_storage_adapter(
        self,
        backend: str,
        config_overrides: dict[str, t.Any] | None = None,
        force: bool = False,
    ) -> StorageBaseOneiric:
        """Register a storage adapter.

        Args:
            backend: Storage backend type (file, memory)
            config_overrides: Configuration overrides
            force: Force re-registration even if adapter exists

        Returns:
            Configured storage adapter

        """
        self._validate_backend(backend)

        # Return cached adapter if exists and not forcing re-registration
        if not force and backend in self._adapters:
            return self._adapters[backend]

        # Ensure settings are initialized
        if self._settings is None:
            self._settings = StorageAdapterSettings.from_settings()

        # Create and configure adapter
        adapter = self._create_adapter(backend)
        self._apply_config_overrides(adapter, config_overrides)

        # Cache and return
        self._adapters[backend] = adapter
        return adapter

    def _validate_backend(self, backend: str) -> None:
        """Validate backend type.

        Args:
            backend: Backend type to validate

        Raises:
            ValueError: If backend is not supported

        """
        if backend not in SUPPORTED_BACKENDS:
            msg = f"Unsupported backend: {backend}. Must be one of {SUPPORTED_BACKENDS}"
            raise ValueError(msg)

    def _create_adapter(self, backend: str) -> StorageBaseOneiric:
        """Create a storage adapter instance.

        Args:
            backend: Backend type to create

        Returns:
            New adapter instance

        Raises:
            ValueError: If backend type is unknown

        """
        adapter_map: dict[str, type[StorageBaseOneiric]] = {
            "file": FileStorageOneiric,
            "memory": MemoryStorageOneiric,
        }

        adapter_class = adapter_map.get(backend)
        if adapter_class is None:
            msg = f"Unsupported backend: {backend}"
            raise ValueError(msg)

        # Concrete adapters accept StorageAdapterSettings | None
        # Base class signature differs from concrete classes
        return adapter_class(self._settings)  # type: ignore[arg-type]

    def _apply_config_overrides(
        self,
        adapter: StorageBaseOneiric,
        config_overrides: dict[str, t.Any] | None,
    ) -> None:
        """Apply configuration overrides to adapter.

        Args:
            adapter: Adapter to configure
            config_overrides: Optional configuration overrides

        """
        if not config_overrides:
            return

        overrides = self._prepare_overrides(adapter, config_overrides)
        if overrides:
            adapter.settings = replace(adapter.settings, **overrides)
            if "buckets" in overrides and overrides["buckets"] is not None:
                adapter.buckets = dict(overrides["buckets"])

    def _prepare_overrides(
        self,
        adapter: StorageBaseOneiric,
        config_overrides: dict[str, t.Any],
    ) -> dict[str, t.Any]:
        """Prepare configuration overrides with type conversion.

        Args:
            adapter: Adapter being configured
            config_overrides: Raw override values

        Returns:
            Processed overrides dictionary

        """
        overrides: dict[str, t.Any] = {}
        for key, value in config_overrides.items():
            # Convert string paths to Path objects
            if key == "local_path" and isinstance(value, str):
                value = Path(value)

            # Only include if adapter has this attribute
            if hasattr(adapter.settings, key):
                overrides[key] = value

        return overrides

    def get_storage_adapter(self, backend: str | None = None) -> StorageBaseOneiric:
        """Get a storage adapter.

        Args:
            backend: Storage backend type. If None, uses default.

        Returns:
            Storage adapter instance

        """
        if backend is None:
            backend = self._settings.default_backend if self._settings else "file"

        if backend not in self._adapters:
            # Auto-register if not found
            adapter = self.register_storage_adapter(backend)
            # Initialize the adapter synchronously
            adapter._initialize_sync()
            return adapter

        return self._adapters[backend]

    def configure_storage_buckets(self, buckets: dict[str, str]) -> None:
        """Configure storage buckets.

        Args:
            buckets: Mapping of bucket names to paths/identifiers

        """
        if self._settings is None:
            self._settings = StorageAdapterSettings.from_settings()

        # Update settings with new buckets
        self._settings.buckets.update(buckets)

        # Update all registered adapters
        for adapter in self._adapters.values():
            adapter.buckets.update(buckets)


# Global registry instance
_storage_registry = StorageRegistryOneiric()


def init_storage_registry() -> None:
    """Initialize storage registry with Oneiric implementation."""
    # Synchronous initialization
    _storage_registry._initialize_sync()


def get_storage_registry() -> StorageRegistryOneiric:
    """Get storage registry instance."""
    return _storage_registry


def get_storage_adapter(backend: str | None = None) -> StorageBaseOneiric:
    """Get storage adapter from registry."""
    registry = get_storage_registry()
    return registry.get_storage_adapter(backend)


def configure_storage_buckets(buckets: dict[str, str]) -> None:
    """Configure storage buckets."""
    registry = get_storage_registry()
    registry.configure_storage_buckets(buckets)


def register_storage_adapter(
    backend: str,
    config_overrides: dict[str, t.Any] | None = None,
    force: bool = False,
) -> StorageBaseOneiric:
    """Register a storage adapter for a specific backend.

    Args:
        backend: Backend name to associate with the adapter
        config_overrides: Optional configuration overrides
        force: If True, re-registers even if already registered

    """
    registry = get_storage_registry()
    return registry.register_storage_adapter(
        backend,
        config_overrides=config_overrides,
        force=force,
    )


# Default session bucket constant (required by adapters module)
DEFAULT_SESSION_BUCKET = "session-buddy-default"


# Session storage adapter (required by adapters module)
class SessionStorageAdapter:
    """Session storage adapter for Oneiric implementation.

    This class provides the session storage interface expected by the adapters module.
    """

    def __init__(self, backend: str = "file") -> None:
        """Initialize session storage adapter.

        Args:
            backend: Storage backend type (file, memory)

        """
        self.backend = backend
        self._storage: StorageProtocol | None = None

    async def initialize(self) -> None:
        """Initialize the storage adapter."""
        registry = get_storage_registry()
        self._storage = registry.get_storage_adapter(self.backend)
        await self._storage.init()

    async def upload(self, bucket: str, path: str, data: bytes) -> None:
        """Upload data to storage."""
        if self._storage is None:
            await self.initialize()
        assert self._storage is not None  # Type narrowing
        await self._storage.upload(bucket, path, data)

    async def download(self, bucket: str, path: str) -> bytes:
        """Download data from storage."""
        if self._storage is None:
            await self.initialize()
        assert self._storage is not None  # Type narrowing
        return await self._storage.download(bucket, path)

    async def delete(self, bucket: str, path: str) -> None:
        """Delete data from storage."""
        if self._storage is None:
            await self.initialize()
        assert self._storage is not None  # Type narrowing
        await self._storage.delete(bucket, path)

    async def exists(self, bucket: str, path: str) -> bool:
        """Check if data exists in storage."""
        if self._storage is None:
            await self.initialize()
        assert self._storage is not None  # Type narrowing
        return await self._storage.exists(bucket, path)


def get_default_storage_adapter() -> SessionStorageAdapter:
    """Get default storage adapter (required by adapters module)."""
    return SessionStorageAdapter(backend="file")


def get_default_session_buckets() -> dict[str, str]:
    """Get default session buckets (required by adapters module)."""
    return {
        "default": DEFAULT_SESSION_BUCKET,
        "sessions": "session-buddy-sessions",
        "cache": "session-buddy-cache",
    }


__all__ = [
    "DEFAULT_SESSION_BUCKET",
    "SUPPORTED_BACKENDS",
    "FileStorageOneiric",
    "MemoryStorageOneiric",
    "SessionStorageAdapter",
    "StorageBaseOneiric",
    "StorageRegistryOneiric",
    "configure_storage_buckets",
    "get_default_session_buckets",
    "get_default_storage_adapter",
    "get_storage_adapter",
    "get_storage_registry",
    "init_storage_registry",
    "register_storage_adapter",
]
