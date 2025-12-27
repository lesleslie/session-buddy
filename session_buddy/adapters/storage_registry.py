"""Storage adapter registry for session state persistence.

This module provides registration and configuration for ACB storage adapters,
enabling multiple backend types (S3, Azure, GCS, File, Memory) for session
state persistence in serverless and distributed deployments.

The registry follows ACB's dependency injection pattern and provides:
- Type-safe adapter configuration via StorageSettings
- Runtime backend selection from config
- Automatic adapter initialization and cleanup
- Bucket management for organized storage

Example:
    >>> from session_buddy.adapters.storage_registry import get_storage_adapter
    >>> storage = get_storage_adapter("file")  # or "s3", "azure", "gcs", "memory"
    >>> await storage.upload("sessions", "session_123/state.json", data)
    >>> state = await storage.download("sessions", "session_123/state.json")

"""

from __future__ import annotations

import typing as t
from contextlib import suppress

from acb.config import Config
from acb.depends import depends

if t.TYPE_CHECKING:
    from pathlib import Path

    from acb.adapters.storage._base import StorageBase

# Supported storage backend types
SUPPORTED_BACKENDS = ("s3", "azure", "gcs", "file", "memory")

# Backend to class mapping (lazy-loaded on first use)
_STORAGE_CLASSES: dict[str, type[StorageBase] | None] = {
    "file": None,
    "s3": None,
    "azure": None,
    "gcs": None,
    "memory": None,
}


def _get_storage_class(backend: str) -> type[StorageBase]:
    """Get storage class for a backend, lazy-loading on first use.

    Args:
        backend: Storage backend type (file, s3, azure, gcs, memory)

    Returns:
        Storage class for the backend

    Raises:
        ValueError: If backend is unsupported

    Note:
        ACB storage adapters are imported directly, not via import_adapter().
        This is because they don't use adapters.yaml configuration.

    """
    if backend not in SUPPORTED_BACKENDS:
        msg = f"Unsupported backend: {backend}. Must be one of {SUPPORTED_BACKENDS}"
        raise ValueError(msg)

    # Lazy-load the class if not already loaded
    if _STORAGE_CLASSES[backend] is None:
        if backend == "file":
            from acb.adapters.storage.file import Storage as FileStorage

            _STORAGE_CLASSES["file"] = FileStorage
        elif backend == "s3":
            from acb.adapters.storage.s3 import Storage as S3Storage

            _STORAGE_CLASSES["s3"] = S3Storage
        elif backend == "azure":
            from acb.adapters.storage.azure import Storage as AzureStorage

            _STORAGE_CLASSES["azure"] = AzureStorage
        elif backend == "gcs":
            from acb.adapters.storage.gcs import Storage as GCSStorage

            _STORAGE_CLASSES["gcs"] = GCSStorage
        elif backend == "memory":
            from acb.adapters.storage.memory import Storage as MemoryStorage

            _STORAGE_CLASSES["memory"] = MemoryStorage

    return _STORAGE_CLASSES[backend]  # type: ignore[return-value]


def register_storage_adapter(
    backend: str, config_overrides: dict[str, t.Any] | None = None, force: bool = False
) -> StorageBase:
    """Register an ACB storage adapter with the given backend type.

    Args:
        backend: Storage backend type ("s3", "azure", "gcs", "file", "memory")
        config_overrides: Optional configuration overrides for the adapter
        force: If True, re-registers even if already registered

    Returns:
        Configured storage adapter instance

    Raises:
        ValueError: If backend type is not supported

    Example:
        >>> storage = register_storage_adapter("file", {"local_path": "/var/sessions"})
        >>> await storage.init()  # Initialize buckets

    Note:
        ACB storage adapters are imported directly, not via import_adapter().
        See docs/ACB_STORAGE_ADAPTER_GUIDE.md for details.

    """
    # Get the storage class for this backend (direct import, not import_adapter)
    storage_class = _get_storage_class(backend)

    # Check if already registered (unless force=True)
    if not force:
        with suppress(KeyError, AttributeError, RuntimeError):
            existing = depends.get_sync(storage_class)
            if isinstance(existing, storage_class):
                return existing

    # Get Config singleton
    config = depends.get_sync(Config)
    config.ensure_initialized()

    # Ensure storage settings exist
    if not hasattr(config, "storage"):
        from acb.adapters.storage._base import StorageBaseSettings

        config.storage = StorageBaseSettings()

    # Set default backend
    config.storage.default_backend = backend

    # Apply configuration overrides if provided
    if config_overrides:
        for key, value in config_overrides.items():
            setattr(config.storage, key, value)

    # Create adapter instance
    storage_adapter = storage_class()
    storage_adapter.config = config

    # Set logger directly to avoid DI type resolution conflicts
    import logging

    storage_adapter.logger = logging.getLogger(f"acb.storage.{backend}")

    # Register with DI container
    depends.set(storage_class, storage_adapter)

    return storage_adapter


def get_storage_adapter(backend: str | None = None) -> StorageBase:
    """Get a registered storage adapter by backend type.

    Args:
        backend: Storage backend type. If None, uses configured default.

    Returns:
        Storage adapter instance

    Raises:
        ValueError: If backend not registered or not supported
        KeyError: If adapter not found in DI container

    Example:
        >>> storage = get_storage_adapter("s3")
        >>> await storage.upload("sessions", "session_123/state.json", data)

    Note:
        ACB storage adapters are imported directly, not via import_adapter().
        See docs/ACB_STORAGE_ADAPTER_GUIDE.md for details.

    """
    # Get backend from config if not specified
    if backend is None:
        config = depends.get_sync(Config)
        backend = getattr(config.storage, "default_backend", "file")

    # Get storage class for this backend (direct import, not import_adapter)
    storage_class = _get_storage_class(backend)

    try:
        return depends.get_sync(storage_class)
    except KeyError as e:
        msg = f"Storage adapter '{backend}' not registered. Call register_storage_adapter() first."
        raise ValueError(msg) from e


def configure_storage_buckets(buckets: dict[str, str]) -> None:
    """Configure storage buckets for all registered adapters.

    Args:
        buckets: Mapping of bucket names to bucket identifiers
                 Example: {"sessions": "my-sessions-bucket", "test": "test-bucket"}

    Note:
        This should be called before initializing any storage adapters.
        Buckets are logical groupings used to organize stored files.

    Example:
        >>> configure_storage_buckets(
        ...     {
        ...         "sessions": "production-sessions",
        ...         "checkpoints": "session-checkpoints",
        ...         "test": "test-data",
        ...     }
        ... )

    """
    config = depends.get_sync(Config)
    config.ensure_initialized()

    if not hasattr(config, "storage"):
        from acb.adapters.storage._base import StorageBaseSettings

        config.storage = StorageBaseSettings()

    config.storage.buckets = buckets


def get_default_session_buckets(data_dir: Path) -> dict[str, str]:
    """Get default bucket configuration for session management.

    Args:
        data_dir: Base directory for session data storage

    Returns:
        Dictionary mapping bucket names to paths/identifiers

    Example:
        >>> buckets = get_default_session_buckets(Path.home() / ".claude" / "data")
        >>> configure_storage_buckets(buckets)

    """
    return {
        "sessions": str(data_dir / "sessions"),
        "checkpoints": str(data_dir / "checkpoints"),
        "handoffs": str(data_dir / "handoffs"),
        "test": str(data_dir / "test"),
    }


__all__ = [
    "SUPPORTED_BACKENDS",
    "configure_storage_buckets",
    "get_default_session_buckets",
    "get_storage_adapter",
    "register_storage_adapter",
]
