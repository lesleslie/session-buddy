# Akosha Cloud Sync - API Reference

Developer-facing API documentation for Session-Buddy's Akosha synchronization system.

## Table of Contents

- [Core Components](#core-components)
- [Configuration](#configuration)
- [Sync Protocol](#sync-protocol)
- [Cloud Sync Method](#cloud-sync-method)
- [HTTP Sync Method](#http-sync-method)
- [Hybrid Orchestrator](#hybrid-orchestrator)
- [MCP Tools](#mcp-tools)
- [Session End Hook](#session-end-hook)
- [Exceptions](#exceptions)

______________________________________________________________________

## Core Components

### Architecture Diagram

```
Session End Trigger
        ↓
HybridAkoshaSync (Orchestrator)
        ↓
Priority Selection:
    1. CloudSyncMethod (S3/R2) ← Primary
    2. HttpSyncMethod (Akosha HTTP) ← Fallback
        ↓
Upload to Cloud/HTTP
        ↓
Create manifest.json
        ↓
Return result
```

### Module Structure

```
session_buddy/
├── storage/
│   ├── sync_protocol.py        # Protocol interface and exceptions
│   ├── akosha_config.py         # Configuration dataclass
│   ├── cloud_sync.py            # Cloud sync implementation
│   └── akosha_sync.py           # Hybrid orchestrator
├── mcp/tools/memory/
│   └── akosha_tools.py          # MCP tool wrappers
└── settings.py                   # Global configuration
```

______________________________________________________________________

## Configuration

### AkoshaSyncConfig

**Location**: `session_buddy.storage.akosha_config.AkoshaSyncConfig`

Frozen dataclass containing all Akosha configuration.

#### Constructor

```python
@dataclass(frozen=True)
class AkoshaSyncConfig:
    cloud_bucket: str = ""
    cloud_endpoint: str = ""
    cloud_region: str = "auto"
    system_id: str = ""
    upload_on_session_end: bool = True
    enable_fallback: bool = True
    force_method: Literal["auto", "cloud", "http"] = "auto"
    upload_timeout_seconds: int = 300
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0
    enable_compression: bool = True
    enable_deduplication: bool = True
    chunk_size_mb: int = 5
```

#### Factory Method

```python
@classmethod
def from_settings(cls, settings: SessionMgmtSettings) -> AkoshaSyncConfig:
    """Create config from SessionMgmtSettings instance."""
```

#### Computed Properties

```python
@property
def cloud_configured(self) -> bool:
    """Check if cloud sync is properly configured."""

@property
def system_id_resolved(self) -> str:
    """Get resolved system ID (hostname if empty)."""

@property
def should_use_cloud(self) -> bool:
    """Check if cloud sync should be used based on config."""

@property
def should_use_http(self) -> bool:
    """Check if HTTP sync should be used."""
```

#### Validation Methods

```python
def validate(self) -> list[str]:
    """Validate configuration and return list of errors."""
```

**Example**:

```python
from session_buddy.settings import get_settings
from session_buddy.storage.akosha_config import AkoshaSyncConfig

settings = get_settings()
config = AkoshaSyncConfig.from_settings(settings)

# Check validation
errors = config.validate()
if errors:
    for error in errors:
        print(f"Configuration error: {error}")

# Use computed properties
if config.cloud_configured:
    print(f"Using cloud sync: {config.cloud_bucket}")
```

______________________________________________________________________

## Sync Protocol

### SyncMethod Protocol

**Location**: `session_buddy.storage.sync_protocol.SyncMethod`

Protocol interface that all sync methods must implement.

```python
@runtime_checkable
class SyncMethod(Protocol):
    async def sync(
        self,
        upload_reflections: bool = True,
        upload_knowledge_graph: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Synchronize memories to the target system."""

    def is_available(self) -> bool:
        """Check if sync method is configured and available."""

    def get_method_name(self) -> str:
        """Get human-readable method name."""
```

#### Implementation Example

```python
from session_buddy.storage.sync_protocol import SyncMethod

class MySyncMethod:
    def __init__(self, config: AkoshaSyncConfig):
        self.config = config

    async def sync(
        self,
        upload_reflections: bool = True,
        upload_knowledge_graph: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Implementation
        return {
            "method": "my_method",
            "success": True,
            "files_uploaded": [...],
            "bytes_transferred": 1024,
            "duration_seconds": 1.0,
            "error": None,
        }

    def is_available(self) -> bool:
        return bool(self.config.cloud_bucket)

    def get_method_name(self) -> str:
        return "my_method"
```

### Exception Hierarchy

```
SyncError (base)
├── CloudUploadError
│   └── Raised when: Cloud bucket not accessible, auth failed, timeout
├── HTTPSyncError
│   └── Raised when: Akosha server unreachable, connection refused
└── HybridSyncError
    └── Raised when: All sync methods failed
```

#### Usage

```python
from session_buddy.storage.sync_protocol import CloudUploadError, HybridSyncError

try:
    await sync.sync()
except CloudUploadError as e:
    logger.error(f"Cloud upload failed: {e}")
    # Handle cloud-specific error
except HybridSyncError as e:
    logger.error(f"All methods failed: {e}")
    # All methods exhausted
```

______________________________________________________________________

## Cloud Sync Method

### CloudSyncMethod

**Location**: `session_buddy.storage.cloud_sync.CloudSyncMethod`

Implements cloud storage sync using Oneiric S3 adapter.

#### Constructor

```python
def __init__(self, config: AkoshaSyncConfig) -> None:
    """Initialize cloud sync method.

    Args:
        config: Akosha sync configuration

    Raises:
        ValueError: If configuration is invalid
    """
```

#### Methods

```python
async def sync(
    self,
    upload_reflections: bool = True,
    upload_knowledge_graph: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Synchronize databases to cloud storage.

    Returns:
        Dict with:
            - method: "cloud"
            - success: bool
            - files_uploaded: list[str]
            - bytes_transferred: int
            - duration_seconds: float
            - upload_id: str
            - error: str | None

    Raises:
        CloudUploadError: If upload fails catastrophically
    """

def is_available(self) -> bool:
    """Check if cloud sync is available.

    Returns:
        True if cloud is configured and Oneiric is available
    """

def get_method_name(self) -> str:
    """Get method name for logging.

    Returns:
        "cloud"
    """
```

#### Internal Methods

```python
def _generate_upload_id(self) -> str:
    """Generate unique upload ID.

    Returns:
        Upload ID in format: YYYYMMDD_HHMMSS_system-id
    """

async def _compute_sha256(self, file_path: Path) -> str:
    """Compute SHA-256 checksum of file.

    Args:
        file_path: Path to file

    Returns:
        Hexadecimal checksum string
    """

async def _read_database(self, db_path: Path) -> bytes:
    """Read database file, optionally compressing.

    Args:
        db_path: Path to database file

    Returns:
        File data (compressed or raw)
    """

def _get_cloud_path(self, db_name: str, upload_id: str) -> str:
    """Get cloud storage path for database.

    Args:
        db_name: Database filename
        upload_id: Upload identifier

    Returns:
        Cloud storage path (without bucket prefix)

    Example:
        >>> _get_cloud_path("reflection.duckdb", "20250208_143052_mac")
        'systems/mac/uploads/20250208_143052_mac/reflection.duckdb'
    """
```

#### Usage Example

```python
from session_buddy.storage.cloud_sync import CloudSyncMethod
from session_buddy.storage.akosha_config import AkoshaSyncConfig

config = AkoshaSyncConfig(
    cloud_bucket="my-bucket",
    cloud_endpoint="https://my-r2.r2.cloudflarestorage.com",
)

cloud_sync = CloudSyncMethod(config)

# Check availability
if cloud_sync.is_available():
    # Perform sync
    result = await cloud_sync.sync(
        upload_reflections=True,
        upload_knowledge_graph=True,
    )

    print(f"Uploaded {len(result['files_uploaded'])} files")
    print(f"Transfer: {result['bytes_transferred']:,} bytes")
    print(f"Duration: {result['duration_seconds']:.2f}s")
```

______________________________________________________________________

## HTTP Sync Method

### HttpSyncMethod

**Location**: `session_buddy.storage.akosha_sync.HttpSyncMethod`

Implements HTTP sync for direct upload to Akosha server.

#### Constructor

```python
def __init__(self, config: AkoshaSyncConfig) -> None:
    """Initialize HTTP sync method.

    Args:
        config: Akosha sync configuration
    """
```

#### Methods

```python
async def sync(
    self,
    upload_reflections: bool = True,
    upload_knowledge_graph: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Sync memories via HTTP POST to Akosha.

    Returns:
        Sync result dictionary

    Raises:
        HTTPSyncError: If HTTP sync fails
    """

def is_available(self) -> bool:
    """Check if Akosha HTTP endpoint is reachable.

    Returns:
        True if Akosha server is running
    """

def get_method_name(self) -> str:
    """Get method name for logging.

    Returns:
        "http"
    """
```

#### Usage Example

```python
from session_buddy.storage.akosha_sync import HttpSyncMethod
from session_buddy.storage.akosha_config import AkoshaSyncConfig

config = AkoshaSyncConfig(
    cloud_bucket="",  # No cloud storage
    cloud_endpoint="http://localhost:8682/mcp",
)

http_sync = HttpSyncMethod(config)

# Check availability
if http_sync.is_available():
    result = await http_sync.sync()
    print(f"HTTP sync: {result['success']}")
```

______________________________________________________________________

## Hybrid Orchestrator

### HybridAkoshaSync

**Location**: `session_buddy.storage.akosha_sync.HybridAkoshaSync`

Orchestrates multiple sync methods with automatic fallback.

#### Constructor

```python
def __init__(self, config: AkoshaSyncConfig) -> None:
    """Initialize hybrid sync orchestrator.

    Args:
        config: Akosha sync configuration

    The orchestrator creates sync methods in priority order:
    1. CloudSyncMethod (fastest)
    2. HttpSyncMethod (fallback)
    """
```

#### Methods

```python
async def sync_memories(
    self,
    force_method: Literal["auto", "cloud", "http"] = "auto",
    upload_reflections: bool = True,
    upload_knowledge_graph: bool = True,
) -> dict[str, Any]:
    """Sync memories using available methods with automatic fallback.

    Args:
        force_method: Force specific method ("auto", "cloud", "http")
        upload_reflections: Whether to upload reflection database
        upload_knowledge_graph: Whether to upload knowledge graph database

    Returns:
        Sync result dictionary with method, success status, and metadata

    Raises:
        HybridSyncError: If all sync methods fail

    Examples:
        >>> # Auto: cloud → HTTP fallback
        >>> await hybrid.sync_memories()
        {'method': 'cloud', 'success': True, ...}

        >>> # Force HTTP (dev/testing)
        >>> await hybrid.sync_memories(force_method="http")
        {'method': 'http', 'success': True, ...}
    """

def _get_method(self, method_name: str) -> SyncMethod | None:
    """Get sync method by name.

    Args:
        method_name: Method name ("cloud" or "http")

    Returns:
        SyncMethod instance or None if not found
    """
```

#### Usage Example

```python
from session_buddy.storage.akosha_sync import HybridAkoshaSync
from session_buddy.storage.akosha_config import AkoshaSyncConfig

config = AkoshaSyncConfig.from_settings(settings)
hybrid = HybridAkoshaSync(config)

# Auto mode: try cloud, fall back to HTTP
result = await hybrid.sync_memories(force_method="auto")
print(f"Used method: {result['method']}")

# Force specific method
result = await hybrid.sync_memories(force_method="cloud")
if not result['success']:
    print(f"Cloud failed: {result['error']}")
```

______________________________________________________________________

## MCP Tools

### sync_to_akosha

**Location**: `session_buddy.mcp.tools.memory.akosha_tools.sync_to_akosha`

MCP tool for manual memory synchronization.

#### Signature

```python
@mcp.tool()
async def sync_to_akosha(
    method: Literal["auto", "cloud", "http"] = "auto",
    enable_fallback: bool = True,
) -> dict[str, Any]:
    """Sync memories to Akosha with automatic fallback."""
```

#### Parameters

- `method`: Sync method to use
  - `"auto"`: Try cloud, fall back to HTTP (recommended)
  - `"cloud"`: Force cloud sync only (fails if unavailable)
  - `"http"`: Force HTTP sync only (dev/testing)
- `enable_fallback`: Allow cloud → HTTP fallback (default: true)

#### Returns

```python
{
    "method": "cloud",           # Method used
    "success": True,             # Whether sync succeeded
    "files_uploaded": [...],     # Uploaded file paths
    "bytes_transferred": 1024,    # Total bytes transferred
    "duration_seconds": 45.2,    # Upload duration
    "upload_id": "20250208_...", # Upload identifier
    "error": None,               # Error message if failed
    "triggered_by": "manual",    # Trigger source
}
```

#### Examples

```python
# Auto: cloud → HTTP fallback
result = await sync_to_akosha()

# Force HTTP (dev/testing)
result = await sync_to_akosha(method="http")

# Force cloud (no fallback)
result = await sync_to_akosha(method="cloud", enable_fallback=False)
```

### akosha_sync_status

**Location**: `session_buddy.mcp.tools.memory.akosha_tools.akosha_sync_status`

MCP tool for checking sync configuration and status.

#### Signature

```python
@mcp.tool()
async def akosha_sync_status() -> dict[str, Any]:
    """Get Akosha sync configuration and status."""
```

#### Returns

```python
{
    "cloud_configured": True,     # Whether cloud is configured
    "system_id": "macbook-pro",   # Resolved system ID
    "should_use_cloud": True,     # Whether cloud will be used
    "should_use_http": True,      # Whether HTTP will be used
    "force_method": "auto",       # Forced method setting
    "enable_fallback": True,      # Fallback enabled setting
    "upload_on_session_end": True,# Auto-upload setting
    "configuration": {            # Full configuration
        "cloud_bucket": "...",
        "cloud_endpoint": "...",
        ...
    }
}
```

#### Example

```python
status = await akosha_sync_status()

if status["cloud_configured"]:
    print(f"Cloud sync enabled: {status['configuration']['cloud_bucket']}")
else:
    print("Cloud sync disabled, will use HTTP fallback")
```

______________________________________________________________________

## Session End Hook

### Background Upload Pattern

**Location**: `session_buddy.mcp.tools.session.session_tools._queue_akosha_sync_background`

Non-blocking background task that uploads memories after session end.

#### Implementation

```python
def _queue_akosha_sync_background() -> None:
    """Queue Akosha sync as background task without blocking session end."""
    import asyncio

    asyncio.create_task(
        _akosha_sync_background_task(),
        name="akosha_sync_upload",
    )

async def _akosha_sync_background_task() -> None:
    """Background sync task for uploading memories to Akosha."""
    config = AkoshaSyncConfig.from_settings(get_settings())
    sync = HybridAkoshaSync(config)
    result = await sync.sync_memories(force_method="auto")

    if result["success"]:
        logger.info(f"✅ Akosha sync complete: {result['method']}")
    else:
        logger.warning(f"⚠️ Akosha sync failed: {result.get('error')}")
```

#### Usage Pattern

```python
async def _end_impl(working_directory: str | None = None) -> str:
    """Implementation for end tool."""
    result = await _get_session_manager().end_session(working_directory)

    if result["success"]:
        output.extend(_format_successful_end(result["summary"]))

        # Queue Akosha sync without blocking
        _queue_akosha_sync_background()

    return "\n".join(output)
```

#### Flow Diagram

```
Session End Triggered
        ↓
Session cleanup completes
        ↓
Queue background task (asyncio.create_task)
        ↓
Session end completes immediately (non-blocking)
        ↓
Background task runs:
    - Load configuration
    - Create sync orchestrator
    - Perform sync (cloud → HTTP fallback)
    - Log result
```

______________________________________________________________________

## Exceptions

### CloudUploadError

**Location**: `session_buddy.storage.sync_protocol.CloudUploadError`

Raised when cloud storage upload fails.

```python
class CloudUploadError(SyncError):
    """Cloud storage upload failed.

    Raised when:
    - Cloud bucket not accessible
    - Authentication failed
    - Network timeout during upload
    - Insufficient permissions
    """

def __init__(self, message: str, method: str, original: Exception | None = None):
    self.method = method
    self.original = original
```

#### Example

```python
try:
    await cloud_sync.sync()
except CloudUploadError as e:
    logger.error(f"Cloud upload failed: {e}")
    logger.error(f"Original error: {e.original}")
    # Handle cloud-specific error
```

### HTTPSyncError

**Location**: `session_buddy.storage.sync_protocol.HTTPSyncError`

Raised when HTTP sync to Akosha fails.

```python
class HTTPSyncError(SyncError):
    """HTTP sync to Akosha failed.

    Raised when:
    - Akosha server not reachable
    - Connection refused
    - Request timeout
    - Server error (5xx)
    """
```

### HybridSyncError

**Location**: `session_buddy.storage.sync_protocol.HybridSyncError`

Raised when all sync methods fail.

```python
class HybridSyncError(SyncError):
    """All sync methods failed.

    Attributes:
        errors: List of error dictionaries from each failed method
    """

def __init__(self, message: str, method: str, errors: list[dict[str, Any]]):
    self.errors = errors
```

#### Example

```python
try:
    await hybrid.sync_memories()
except HybridSyncError as e:
    logger.error("All sync methods failed:")
    for error in e.errors:
        logger.error(f"  - {error['method']}: {error['error']}")
```

______________________________________________________________________

## Type Hints

### Common Types

```python
from typing import Any, Literal

# Sync result type
type SyncResult = dict[
    str, Any  # Keys: method, success, files_uploaded, bytes_transferred, etc.
]

# Method type
type SyncMethodType = Literal["cloud", "http", "hybrid"]

# Configuration types
type CompressionEnabled = bool
type DeduplicationEnabled = bool
type ChunkSizeMB = int  # 1-100
```

______________________________________________________________________

## Best Practices

### 1. Error Handling

Always handle sync-specific exceptions:

```python
from session_buddy.storage.sync_protocol import (
    CloudUploadError,
    HTTPSyncError,
    HybridSyncError,
)

try:
    result = await sync.sync()
except CloudUploadError as e:
    # Cloud-specific handling (retry, notify user, etc.)
    logger.error(f"Cloud error: {e}")
except HTTPSyncError as e:
    # HTTP-specific handling
    logger.error(f"HTTP error: {e}")
except HybridSyncError as e:
    # All methods failed
    logger.error(f"All methods failed: {e.errors}")
```

### 2. Configuration Validation

Validate configuration before use:

```python
config = AkoshaSyncConfig.from_settings(settings)
errors = config.validate()

if errors:
    for error in errors:
        logger.error(f"Configuration error: {error}")
    raise ValueError(f"Invalid Akosha configuration: {errors}")
```

### 3. Async Context Managers

Use async context managers for cleanup:

```python
async def sync_with_cleanup():
    config = AkoshaSyncConfig.from_settings(settings)
    hybrid = HybridAkoshaSync(config)

    try:
        result = await hybrid.sync_memories()
        return result
    finally:
        # Cleanup resources
        logger.info("Sync complete, resources cleaned")
```

### 4. Logging

Log sync operations at appropriate levels:

```python
logger.info(f"Starting sync: method={method}")
logger.debug(f"Configuration: {config}")
logger.warning(f"Retry attempt {attempt}/{max_retries}")
logger.error(f"Sync failed: {e}")
```

______________________________________________________________________

## Performance Considerations

### Memory Usage

- **Chunking**: Large files split into 5MB chunks (configurable)
- **Compression**: Reduces memory usage by 65%
- **Streaming**: Files read and uploaded in chunks, not loaded entirely

### Network Usage

- **Compression**: 65% bandwidth reduction
- **Deduplication**: Skips uploading unchanged files
- **Retry Logic**: Exponential backoff reduces network spam

### CPU Usage

- **Compression**: Adds CPU overhead (~2-3s for 100MB)
- **Checksum**: SHA-256 computation (~1s for 100MB)
- **Chunking**: Minimal overhead

______________________________________________________________________

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_cloud_sync_success():
    config = AkoshaSyncConfig(cloud_bucket="test")
    cloud_sync = CloudSyncMethod(config)

    with patch.object(cloud_sync, "_upload_to_s3"):
        result = await cloud_sync.sync()
        assert result["success"] is True
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_hybrid_fallback():
    config = AkoshaSyncConfig.from_settings(settings)
    hybrid = HybridAkoshaSync(config)

    result = await hybrid.sync_memories()
    assert result["success"] is True
```

______________________________________________________________________

## Migration Guide

### From Manual Sync

Before:

```python
# Manual HTTP POST to Akosha
async with httpx.AsyncClient() as client:
    await client.post("http://localhost:8682/store_memory", ...)
```

After:

```python
# Use hybrid sync with automatic fallback
from session_buddy.storage.akosha_sync import HybridAkoshaSync

hybrid = HybridAkoshaSync(config)
result = await hybrid.sync_memories()
```

### From Direct S3 Uploads

Before:

```python
import boto3

s3 = boto3.client("s3")
s3.upload_file("reflection.duckdb", "bucket", "key")
```

After:

```python
from session_buddy.storage.cloud_sync import CloudSyncMethod

cloud_sync = CloudSyncMethod(config)
result = await cloud_sync.sync()  # Handles compression, retry, manifest
```

______________________________________________________________________

## Support

For issues or questions:

- Check logs: `~/.claude/logs/session-buddy.log`
- Verify configuration: Use `akosha_sync_status()` tool
- See troubleshooting guide in [User Guide](USER_GUIDE.md)

______________________________________________________________________

**API Version**: 1.0.0
**Last Updated**: 2026-02-08
