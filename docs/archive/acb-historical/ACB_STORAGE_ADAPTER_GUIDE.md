# ACB Storage Adapter Usage Guide

## Understanding ACB Storage Architecture

ACB storage adapters are **directly imported** from specific backend modules, not via the `import_adapter()` function. This is a key difference from other ACB adapters.

## Correct Import Patterns

### ❌ INCORRECT - Does NOT Work

```python
from acb.adapters import import_adapter

# This will fail with "storage adapter not found"
storage_class = import_adapter("storage")  # ERROR!
storage_class = import_adapter("storage", "file")  # ERROR!
```

**Why this fails:**

- `import_adapter()` requires adapters to be registered in `adapters.yaml`
- ACB storage adapters use direct imports instead
- No `adapters.yaml` configuration is needed for storage

### ✅ CORRECT - Direct Import Pattern

```python
# Import specific storage backend directly
from acb.adapters.storage.file import Storage as FileStorage
from acb.adapters.storage.s3 import Storage as S3Storage
from acb.adapters.storage.azure import Storage as AzureStorage
from acb.adapters.storage.gcs import Storage as GCSStorage
from acb.adapters.storage.memory import Storage as MemoryStorage
```

## Dynamic Backend Selection Pattern

When you need to select a storage backend dynamically (like in `register_storage_adapter()`), use this approach:

```python
from acb.adapters.storage._base import StorageBase
from acb.config import Config
from acb.depends import depends
import typing as t

# Backend to class mapping
STORAGE_BACKENDS: dict[str, type[StorageBase]] = {
    "file": None,  # Lazy-loaded
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
    """
    if backend not in STORAGE_BACKENDS:
        raise ValueError(f"Unsupported backend: {backend}")

    # Lazy-load the class if not already loaded
    if STORAGE_BACKENDS[backend] is None:
        if backend == "file":
            from acb.adapters.storage.file import Storage

            STORAGE_BACKENDS["file"] = Storage
        elif backend == "s3":
            from acb.adapters.storage.s3 import Storage

            STORAGE_BACKENDS["s3"] = Storage
        elif backend == "azure":
            from acb.adapters.storage.azure import Storage

            STORAGE_BACKENDS["azure"] = Storage
        elif backend == "gcs":
            from acb.adapters.storage.gcs import Storage

            STORAGE_BACKENDS["gcs"] = Storage
        elif backend == "memory":
            from acb.adapters.storage.memory import Storage

            STORAGE_BACKENDS["memory"] = Storage

    return STORAGE_BACKENDS[backend]


def register_storage_adapter(
    backend: str, config_overrides: dict[str, t.Any] | None = None, force: bool = False
) -> StorageBase:
    """Register an ACB storage adapter with the given backend type.

    Args:
        backend: Storage backend type (file, s3, azure, gcs, memory)
        config_overrides: Optional configuration overrides
        force: If True, re-registers even if already registered

    Returns:
        Configured storage adapter instance
    """
    # Get the storage class for this backend
    storage_class = _get_storage_class(backend)

    # Check if already registered (unless force=True)
    if not force:
        try:
            existing = depends.get_sync(storage_class)
            if isinstance(existing, storage_class):
                return existing
        except (KeyError, AttributeError, RuntimeError):
            pass

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

    # Set logger
    try:
        from acb.adapters import import_adapter

        logger_class = import_adapter("logger")
        storage_adapter.logger = depends.get_sync(logger_class)
    except Exception:
        import logging

        storage_adapter.logger = logging.getLogger(f"acb.storage.{backend}")

    # Register with DI container
    depends.set(storage_class, storage_adapter)

    return storage_adapter
```

## Configuration via Config Object

ACB storage adapters are configured via the `Config.storage` attribute:

```python
from acb.config import Config
from acb.adapters.storage._base import StorageBaseSettings

config = Config()
config.ensure_initialized()

# Create storage settings
config.storage = StorageBaseSettings()

# Configure backend
config.storage.default_backend = "file"  # or "s3", "azure", "gcs", "memory"

# Backend-specific settings
config.storage.local_path = "~/.claude/data/sessions"  # For file backend
config.storage.bucket_name = "my-sessions"  # For S3/Azure/GCS
config.storage.endpoint_url = "https://s3.amazonaws.com"  # For S3
```

## YAML Configuration

ACB storage adapters read configuration from `settings/session-buddy.yaml`:

```yaml
storage:
  # Default backend selection
  default_backend: "file"

  # File storage settings
  file:
    local_path: "~/.claude/data/sessions"
    auto_mkdir: true

  # S3 storage settings
  s3:
    bucket_name: "${S3_BUCKET:session-buddy}"
    endpoint_url: "${S3_ENDPOINT:}"
    access_key_id: "${S3_ACCESS_KEY:}"
    secret_access_key: "${S3_SECRET_KEY:}"
    region: "${S3_REGION:us-east-1}"

  # Azure Blob storage settings
  azure:
    account_name: "${AZURE_ACCOUNT:}"
    account_key: "${AZURE_KEY:}"
    container: "${AZURE_CONTAINER:sessions}"

  # GCS settings
  gcs:
    bucket_name: "${GCS_BUCKET:}"
    credentials_path: "${GCS_CREDENTIALS:}"
    project: "${GCS_PROJECT:}"

  # Memory storage settings (testing only)
  memory:
    max_size_mb: 100
```

## Complete Example

```python
from pathlib import Path
from acb.config import Config
from acb.depends import depends
from acb.adapters.storage._base import StorageBase, StorageBaseSettings


def setup_file_storage(data_dir: Path) -> StorageBase:
    """Setup file-based storage for session management.

    Args:
        data_dir: Base directory for session data

    Returns:
        Configured file storage adapter
    """
    # Get Config singleton
    config = depends.get_sync(Config)
    config.ensure_initialized()

    # Create storage settings
    config.storage = StorageBaseSettings()
    config.storage.default_backend = "file"
    config.storage.local_path = str(data_dir / "sessions")

    # Import and create adapter
    from acb.adapters.storage.file import Storage as FileStorage

    storage = FileStorage()
    storage.config = config

    # Register with DI
    depends.set(FileStorage, storage)

    return storage


def setup_s3_storage(bucket: str, region: str = "us-east-1") -> StorageBase:
    """Setup S3-based storage for session management.

    Args:
        bucket: S3 bucket name
        region: AWS region

    Returns:
        Configured S3 storage adapter
    """
    # Get Config singleton
    config = depends.get_sync(Config)
    config.ensure_initialized()

    # Create storage settings
    config.storage = StorageBaseSettings()
    config.storage.default_backend = "s3"
    config.storage.bucket_name = bucket
    config.storage.region = region

    # Import and create adapter
    from acb.adapters.storage.s3 import Storage as S3Storage

    storage = S3Storage()
    storage.config = config

    # Register with DI
    depends.set(S3Storage, storage)

    return storage


# Usage
if __name__ == "__main__":
    import asyncio

    async def example():
        # Setup file storage
        storage = setup_file_storage(Path.home() / ".claude" / "data")

        # Initialize
        await storage.init()

        # Use storage
        await storage.upload(
            bucket="sessions",
            key="session_123/state.json",
            data=b'{"session_id": "123"}',
        )

        # Retrieve
        data = await storage.download(bucket="sessions", key="session_123/state.json")

        print("Retrieved:", data)

    asyncio.run(example())
```

## Key Differences from Other ACB Adapters

| Aspect | Storage Adapters | Other Adapters (Logger, Cache, etc.) |
|--------|------------------|--------------------------------------|
| Import Method | Direct import from backend module | `import_adapter("name")` |
| Configuration | Via `Config.storage` attribute | Via `adapters.yaml` |
| Backend Selection | Direct class import or lazy-loading | Automatic from config |
| Registration Required | No `adapters.yaml` needed | Requires `adapters.yaml` entry |

## Common Pitfalls

1. **Using `import_adapter("storage")`**: This will fail because storage adapters are not registered in `adapters.yaml`

1. **Forgetting to set `config.storage`**: Storage adapters expect `Config.storage` to be a `StorageBaseSettings` instance

1. **Not setting `default_backend`**: The backend type must be explicitly configured

1. **Mixing backend classes**: Each backend has its own `Storage` class - they're not interchangeable

## Summary

- **Direct imports only**: Use `from acb.adapters.storage.file import Storage`
- **No `import_adapter()`**: This function is not used for storage adapters
- **Configure via `Config.storage`**: Set backend and options on the config object
- **Lazy-loading pattern**: Use a mapping dict for dynamic backend selection
- **Register in DI**: Use `depends.set(storage_class, instance)` for dependency injection
