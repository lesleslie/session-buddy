"""Akosha sync MCP tools.

This module provides MCP tools for manually triggering memory synchronization
with Akosha, supporting both cloud and HTTP sync methods.

Example:
    >>> await sync_to_akosha()
    {'method': 'cloud', 'success': True, ...}

    >>> await sync_to_akosha(method='http')
    {'method': 'http', 'success': True, ...}
"""

from __future__ import annotations

from typing import Any, Literal

from session_buddy.settings import get_settings
from session_buddy.storage.akosha_config import AkoshaSyncConfig
from session_buddy.storage.akosha_sync import HybridAkoshaSync
from session_buddy.utils.error_management import _get_logger

logger = _get_logger()


async def sync_to_akosha(
    method: Literal["auto", "cloud", "http"] = "auto",
    enable_fallback: bool = True,
) -> dict[str, Any]:
    """Sync memories to Akosha with automatic fallback.

    This tool uploads Session-Buddy memories to Akosha using the specified
    sync method. The default "auto" mode tries cloud sync first, then falls
    back to HTTP sync if cloud is unavailable.

    Args:
        method: Sync method to use
            - "auto": Try cloud, fall back to HTTP (recommended)
            - "cloud": Force cloud sync only (fails if unavailable)
            - "http": Force HTTP sync only (dev/testing)
        enable_fallback: Allow cloud → HTTP fallback (default: true)

    Returns:
        Sync result dictionary with:
            - method: str - Method used ("cloud" or "http")
            - success: bool - Whether sync succeeded
            - files_uploaded: list[str] - Uploaded file paths
            - bytes_transferred: int - Total bytes transferred
            - duration_seconds: float - Upload duration
            - upload_id: str - Unique upload identifier
            - error: str | None - Error message if failed

    Examples:
        >>> # Auto: cloud → HTTP fallback
        >>> await sync_to_akosha()
        {'method': 'cloud', 'success': True, ...}

        >>> # Force HTTP (dev/testing)
        >>> await sync_to_akosha(method="http")
        {'method': 'http', 'success': True, ...}

        >>> # Force cloud (no fallback)
        >>> await sync_to_akosha(method="cloud", enable_fallback=False)
        {'method': 'cloud', 'success': True, ...}
    """
    try:
        # Load settings
        settings = get_settings()

        # Create Akosha configuration
        config = AkoshaSyncConfig.from_settings(settings)

        # Override fallback if specified
        if not enable_fallback:
            config = AkoshaSyncConfig(
                cloud_bucket=config.cloud_bucket,
                cloud_endpoint=config.cloud_endpoint,
                cloud_region=config.cloud_region,
                system_id=config.system_id,
                upload_on_session_end=config.upload_on_session_end,
                enable_fallback=False,  # Override
                force_method=config.force_method,
                upload_timeout_seconds=config.upload_timeout_seconds,
                max_retries=config.max_retries,
                retry_backoff_seconds=config.retry_backoff_seconds,
                enable_compression=config.enable_compression,
                enable_deduplication=config.enable_deduplication,
                chunk_size_mb=config.chunk_size_mb,
            )

        # Create hybrid sync orchestrator
        sync = HybridAkoshaSync(config)

        # Perform sync
        logger.info(f"Manual sync triggered: method={method}")
        result = await sync.sync_memories(force_method=method)

        # Add metadata
        result["triggered_by"] = "manual"

        return result

    except Exception as e:
        logger.error(f"Akasha sync failed: {e}")

        return {
            "method": method,
            "success": False,
            "error": str(e),
            "triggered_by": "manual",
        }


async def akosha_sync_status() -> dict[str, Any]:
    """Get Akosha sync configuration and status.

    Returns:
        Status dictionary with:
            - cloud_configured: bool - Whether cloud sync is configured
            - system_id: str - Resolved system ID
            - should_use_cloud: bool - Whether cloud sync will be used
            - should_use_http: bool - Whether HTTP sync will be used
            - force_method: str - Forced method setting
            - enable_fallback: bool - Fallback enabled setting
            - upload_on_session_end: bool - Auto-upload setting
            - configuration: dict - Full configuration details

    Example:
        >>> await akosha_sync_status()
        {
            'cloud_configured': True,
            'system_id': 'macbook-pro-les',
            'should_use_cloud': True,
            'should_use_http': True,
            'force_method': 'auto',
            'enable_fallback': True,
            'upload_on_session_end': True,
            'configuration': {...}
        }
    """
    settings = get_settings()
    config = AkoshaSyncConfig.from_settings(settings)

    return {
        "cloud_configured": config.cloud_configured,
        "system_id": config.system_id_resolved,
        "should_use_cloud": config.should_use_cloud,
        "should_use_http": config.should_use_http,
        "force_method": config.force_method,
        "enable_fallback": config.enable_fallback,
        "upload_on_session_end": config.upload_on_session_end,
        "configuration": {
            "cloud_bucket": config.cloud_bucket,
            "cloud_endpoint": config.cloud_endpoint,
            "cloud_region": config.cloud_region,
            "system_id": config.system_id,
            "enable_compression": config.enable_compression,
            "enable_deduplication": config.enable_deduplication,
            "chunk_size_mb": config.chunk_size_mb,
            "upload_timeout_seconds": config.upload_timeout_seconds,
            "max_retries": config.max_retries,
            "retry_backoff_seconds": config.retry_backoff_seconds,
        },
    }


def register_akosha_tools(mcp_instance: Any) -> None:
    """Register Akosha sync tools with MCP server.

    Args:
        mcp_instance: FastMCP server instance

    Example:
        >>> from session_buddy.mcp.server import mcp
        >>> register_akosha_tools(mcp)
    """
    # Register tools using the mcp instance
    mcp_instance.tool()(sync_to_akosha)
    mcp_instance.tool()(akosha_sync_status)

    logger.info("Akosha sync tools registered")


__all__ = [
    "sync_to_akosha",
    "akosha_sync_status",
    "register_akosha_tools",
]
