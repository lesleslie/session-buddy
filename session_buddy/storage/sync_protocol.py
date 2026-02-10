"""Sync protocol for pluggable memory synchronization methods.

This module defines the protocol interface that all sync methods must implement,
enabling a clean, extensible architecture for memory synchronization.

The protocol pattern allows:
- Easy addition of new sync methods (e.g., gRPC, message queue)
- Simplified testing with mock implementations
- Clear separation of concerns
- Type-safe method signatures

Example:
    >>> cloud_sync = CloudSyncMethod(settings)
    >>> http_sync = HttpSyncMethod(settings)
    >>>
    >>> hybrid = HybridAkoshaSync(methods=[cloud_sync, http_sync])
    >>> await hybrid.sync_memories()  # Tries each in priority order
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SyncMethod(Protocol):
    """Protocol for memory synchronization implementations.

    Any sync method must implement these two methods to be compatible
    with the HybridAkoshaSync orchestrator.

    Example:
        >>> class CloudSyncMethod:
        ...     def __init__(self, settings: SessionMgmtSettings):
        ...         self.settings = settings
        ...
        ...     async def sync(self, **kwargs) -> dict[str, Any]:
        ...         # Upload to cloud storage
        ...         return {"method": "cloud", "success": True}
        ...
        ...     def is_available(self) -> bool:
        ...         return bool(self.settings.akosha_cloud_bucket)

    Type:
        Protocol: Runtime-checkable protocol for sync methods
    """

    async def sync(
        self,
        upload_reflections: bool = True,
        upload_knowledge_graph: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Synchronize memories to the target system.

        Args:
            upload_reflections: Whether to upload reflection database
            upload_knowledge_graph: Whether to upload knowledge graph database
            **kwargs: Additional method-specific parameters

        Returns:
            Dict with sync results:
                {
                    "method": str,  # Method name (e.g., "cloud", "http")
                    "success": bool,
                    "files_uploaded": list[str],
                    "bytes_transferred": int,
                    "duration_seconds": float,
                    "error": str | None,
                    # ... method-specific fields
                }

        Raises:
            SyncError: If sync fails catastrophically
            ConnectionError: If target system unreachable
        """
        ...

    def is_available(self) -> bool:
        """Check if sync method is configured and available.

        This should be a fast, non-blocking check that verifies:
        - Required configuration is present (not empty)
        - Dependencies are installed
        - Target system is reachable (optional, can be slow)

        Returns:
            True if method can be used, False otherwise

        Example:
            >>> cloud_sync.is_available()
            True  # Bucket configured, credentials present

            >>> http_sync.is_available()
            False  # Akosha server not running
        """
        ...

    def get_method_name(self) -> str:
        """Get human-readable method name.

        Returns:
            Method name for logging and error messages

        Example:
            >>> cloud_sync.get_method_name()
            'cloud'
        """
        ...


class SyncError(Exception):
    """Base exception for sync operations.

    All sync-specific exceptions inherit from this base class,
    allowing catch-all error handling:

    try:
        await sync.sync()
    except SyncError as e:
        # Handle any sync-related error
        logger.error(f"Sync failed: {e}")
    """

    def __init__(self, message: str, method: str, original: Exception | None = None):
        self.method = method
        self.original = original
        super().__init__(f"[{method}] {message}")


class CloudUploadError(SyncError):
    """Cloud storage upload failed.

    Raised when:
    - Cloud bucket not accessible
    - Authentication failed
    - Network timeout during upload
    - Insufficient permissions

    Example:
        >>> raise CloudUploadError(
        ...     "Bucket not found: session-buddy-memories",
        ...     method="cloud",
        ...     original=S3ClientError(...)
        ... )
    """

    pass


class HTTPSyncError(SyncError):
    """HTTP sync to Akosha failed.

    Raised when:
    - Akosha server not reachable
    - Connection refused
    - Request timeout
    - Server error (5xx)

    Example:
        >>> raise HTTPSyncError(
        ...     "Connection refused: http://localhost:8682",
        ...     method="http",
        ...     original=ConnectionRefusedError(...)
        ... )
    """

    pass


class HybridSyncError(SyncError):
    """All sync methods failed.

    Raised when all available sync methods have been exhausted
    and none succeeded. Contains details about each failure.

    Attributes:
        errors: List of error dictionaries from each failed method

    Example:
        >>> raise HybridSyncError(
        ...     "All sync methods failed",
        ...     method="hybrid",
        ...     errors=[
        ...         {"method": "cloud", "error": "Auth failed"},
        ...         {"method": "http", "error": "Connection refused"},
        ...     ]
        ... )
    """

    def __init__(self, message: str, method: str, errors: list[dict[str, Any]]):
        self.errors = errors
        super().__init__(message, method)


__all__ = [
    "SyncMethod",
    "SyncError",
    "CloudUploadError",
    "HTTPSyncError",
    "HybridSyncError",
]
