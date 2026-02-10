"""Akosha sync configuration dataclass.

This module provides a dedicated configuration class for Akosha synchronization,
consolidating all Akosha-related settings and providing computed properties
for common validation checks.

Design:
    - Frozen dataclass prevents accidental mutations
    - Field validators ensure configuration consistency
    - Computed properties provide convenient accessors
    - Environment variable support with defaults

Example:
    >>> config = AkoshaSyncConfig.from_settings(settings)
    >>> config.cloud_configured
    True
    >>> config.system_id_resolved
    'macbook-pro-les'
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

from session_buddy.utils.error_management import _get_logger

logger = _get_logger()


@dataclass(frozen=True)
class AkoshaSyncConfig:
    """Configuration for Akosha synchronization.

    This dataclass consolidates all Akosha-related settings from the main
    SessionMgmtSettings class, preventing configuration sprawl and providing
    a single source of truth for Akosha configuration.

    Attributes:
        # Cloud storage settings
        cloud_bucket: S3/R2 bucket name for cloud sync
        cloud_endpoint: S3/R2 endpoint URL
        cloud_region: Storage region (default: auto)
        system_id: Unique system identifier

        # Behavior settings
        upload_on_session_end: Auto-upload on session end
        enable_fallback: Allow cloud → HTTP fallback
        force_method: Force specific sync method (auto|cloud|http)

        # Performance settings
        upload_timeout_seconds: Timeout for uploads
        max_retries: Maximum retry attempts for failed uploads
        retry_backoff_seconds: Base delay for exponential backoff

        # Feature flags
        enable_compression: Compress databases before upload
        enable_deduplication: Skip unchanged uploads
        chunk_size_mb: Upload chunk size for large files
    """

    # ==========================================================================
    # Cloud Storage Settings
    # ==========================================================================

    cloud_bucket: str = ""
    """S3/R2 bucket name for cloud storage.

    Empty string disables cloud sync. Bucket name must be 3-63 characters,
    containing only lowercase letters, numbers, dots, and hyphens.
    """

    cloud_endpoint: str = ""
    """S3/R2 API endpoint URL.

    For Cloudflare R2: https://<account>.r2.cloudflarestorage.com
    For AWS S3: https://s3.<region>.amazonaws.com
    For MinIO: http://localhost:9000

    Empty string uses provider default from credentials.
    """

    cloud_region: str = "auto"
    """Storage region for cloud operations.

    Default "auto" lets the SDK detect region automatically.
    """

    system_id: str = ""
    """Unique system identifier for this Session-Buddy instance.

    Defaults to hostname if empty. Used for organizing uploads in cloud
    storage under systems/<system_id>/ prefix.
    """

    # ==========================================================================
    # Behavior Settings
    # ==========================================================================

    upload_on_session_end: bool = True
    """Automatically upload memories on session end.

    If True, every session cleanup triggers an upload to Akosha.
    If False, uploads must be triggered manually via MCP tool.
    """

    enable_fallback: bool = True
    """Allow graceful fallback from cloud → HTTP sync.

    If True (recommended), HTTP sync is used when cloud is unavailable.
    If False, sync fails completely if cloud is unavailable.
    """

    force_method: Literal["auto", "cloud", "http"] = "auto"
    """Force specific sync method, bypassing automatic detection.

    Options:
        - "auto": Try cloud, fall back to HTTP if available
        - "cloud": Force cloud sync only (fails if unavailable)
        - "http": Force HTTP sync only (dev/testing)

    This setting overrides automatic method detection.
    """

    # ==========================================================================
    # Performance Settings
    # ==========================================================================

    upload_timeout_seconds: int = 300
    """Maximum time to wait for upload completion (default: 5 minutes).

    Large files (42MB+) may take longer on slow connections.
    """

    max_retries: int = 3
    """Maximum number of retry attempts for failed uploads.

    Retries use exponential backoff: delay = base_delay * (2 ** attempt_number).
    """

    retry_backoff_seconds: float = 2.0
    """Base delay in seconds for exponential backoff between retries.

    Actual delay: backoff * (2 ** attempt_number), with jitter.
    """

    # ==========================================================================
    # Feature Flags
    # ==========================================================================

    enable_compression: bool = True
    """Compress databases with gzip before uploading.

    DuckDB databases compress well (typically 65% size reduction).
    Adds CPU overhead but reduces bandwidth and storage costs.
    """

    enable_deduplication: bool = True
    """Skip uploads if database hasn't changed.

    Computes SHA-256 hash of local database and compares with last upload.
    Avoids redundant uploads and bandwidth usage.
    """

    chunk_size_mb: int = 5
    """Upload chunk size in MB for files > 10MB.

    Larger chunks = fewer requests but more memory usage.
    Smaller chunks = better progress tracking but more overhead.
    """

    # ==========================================================================
    # Computed Properties
    # ==========================================================================

    @property
    def cloud_configured(self) -> bool:
        """Check if cloud sync is properly configured.

        Returns:
            True if bucket is non-empty string

        Example:
            >>> config.cloud_configured
            True  # Bucket configured, cloud sync available
        """
        return bool(self.cloud_bucket)

    @property
    def system_id_resolved(self) -> str:
        """Get resolved system ID (hostname if empty).

        Returns:
            System identifier string

        Example:
            >>> config.system_id_resolved
            'macbook-pro-les'
        """
        return self.system_id or os.getenv(
            "HOSTNAME", os.getenv("COMPUTERNAME", "unknown-system")
        )

    @property
    def should_use_cloud(self) -> bool:
        """Check if cloud sync should be used based on config.

        Returns:
            True if force_method is "cloud" or ("auto" and cloud_configured)

        Example:
            >>> config.should_use_cloud
            True  # Cloud available and not forced to HTTP
        """
        if self.force_method == "http":
            return False
        if self.force_method == "cloud":
            return self.cloud_configured
        return self.cloud_configured

    @property
    def should_use_http(self) -> bool:
        """Check if HTTP sync should be used.

        Returns:
            True if forced to HTTP or fallback enabled

        Example:
            >>> config.should_use_http
            True  # Fallback enabled or forced to HTTP
        """
        if self.force_method == "cloud":
            return False
        if self.force_method == "http":
            return True
        return self.enable_fallback or not self.cloud_configured

    # ==========================================================================
    # Factory Methods
    # ==========================================================================

    @classmethod
    def from_settings(cls, settings: Any) -> AkoshaSyncConfig:
        """Create config from SessionMgmtSettings instance.

        Extracts Akosha-related fields from settings and creates a frozen
        dataclass for type-safe access and computed properties.

        Args:
            settings: SessionMgmtSettings instance

        Returns:
            Frozen AkoshaSyncConfig dataclass

        Example:
            >>> config = AkoshaSyncConfig.from_settings(settings)
            >>> config.cloud_bucket
            'session-buddy-memories'
        """
        return cls(
            # Cloud settings
            cloud_bucket=getattr(settings, "akosha_cloud_bucket", ""),
            cloud_endpoint=getattr(settings, "akosha_cloud_endpoint", ""),
            cloud_region=getattr(settings, "akosha_cloud_region", "auto"),
            system_id=getattr(settings, "akosha_system_id", ""),
            # Behavior
            upload_on_session_end=getattr(
                settings, "akosha_upload_on_session_end", True
            ),
            enable_fallback=getattr(settings, "akosha_enable_fallback", True),
            force_method=getattr(settings, "akosha_force_method", "auto"),
            # Performance
            upload_timeout_seconds=getattr(
                settings, "akosha_upload_timeout_seconds", 300
            ),
            max_retries=getattr(settings, "akosha_max_retries", 3),
            retry_backoff_seconds=getattr(
                settings, "akosha_retry_backoff_seconds", 2.0
            ),
            # Features
            enable_compression=getattr(settings, "akosha_enable_compression", True),
            enable_deduplication=getattr(settings, "akosha_enable_deduplication", True),
            chunk_size_mb=getattr(settings, "akosha_chunk_size_mb", 5),
        )

    # ==========================================================================
    # Validation
    # ==========================================================================

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors.

        Performs comprehensive validation checks:
        - Cloud bucket name format
        - Endpoint URL format and scheme
        - System ID validity
        - Consistency checks (e.g., cloud configured without system_id)

        Returns:
            List of error messages (empty if valid)

        Example:
            >>> errors = config.validate()
            >>> if errors:
            ...     for error in errors:
            ...         print(f"Configuration error: {error}")
        """
        errors: list[str] = []

        # Validate cloud bucket name
        if self.cloud_bucket:
            bucket_errors = self._validate_bucket_name(self.cloud_bucket)
            errors.extend(bucket_errors)

        # Validate endpoint URL
        if self.cloud_endpoint:
            endpoint_errors = self._validate_endpoint_url(self.cloud_endpoint)
            errors.extend(endpoint_errors)

        # Validate system_id if cloud is configured
        if self.cloud_configured and not self.system_id_resolved:
            errors.append(
                "system_id is required when cloud_bucket is configured. "
                "Set AKOSHA_SYSTEM_ID or hostname will be used."
            )

        # Validate force_method consistency
        if self.force_method == "cloud" and not self.cloud_configured:
            errors.append("force_method='cloud' requires cloud_bucket to be configured")

        return errors

    @staticmethod
    def _validate_bucket_name(bucket: str) -> list[str]:
        """Validate S3 bucket name format.

        S3 bucket names must:
        - Be 3-63 characters long
        - Contain only lowercase letters, numbers, dots, and hyphens
        - Start and end with letter or number
        - Not contain formatted IP address

        Args:
            bucket: Bucket name to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors: list[str] = []

        # Length check
        if not (3 <= len(bucket) <= 63):
            errors.append(f"Bucket name must be 3-63 characters, got {len(bucket)}")

        # Pattern check
        if not re.match(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$", bucket):
            errors.append(
                "Bucket name must contain only lowercase letters, numbers, dots, and hyphens"
            )

        # IP address check
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", bucket):
            errors.append("Bucket name cannot be an IP address")

        return errors

    @staticmethod
    def _validate_endpoint_url(endpoint: str) -> list[str]:
        """Validate cloud endpoint URL format.

        Args:
            endpoint: Endpoint URL to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors: list[str] = []

        # Must start with https://
        if not endpoint.startswith("https://"):
            errors.append(
                "Endpoint must use HTTPS for security (http:// is not allowed)"
            )

        # Basic URL format check
        if not re.match(r"^https://[a-zA-Z0-9.-]+", endpoint):
            errors.append("Invalid endpoint URL format")

        return errors


__all__ = [
    "AkoshaSyncConfig",
]
