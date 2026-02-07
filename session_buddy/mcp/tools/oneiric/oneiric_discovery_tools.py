"""Oneiric storage discovery tools for Session-Buddy.

This module provides MCP tools that Session-Buddy exposes for discovering
and resolving Oneiric storage backends via the Oneiric MCP server.

These tools enable dynamic storage backend selection at runtime.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def oneiric_discover_storage(
    server_path: str | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Discover all available Oneiric storage backends.

    This tool queries Oneiric MCP to list all registered storage adapters
    that can be used for session persistence.

    Args:
        server_path: Optional path to Oneiric MCP server directory
        timeout_seconds: Timeout for MCP tool calls (default: 10)

    Returns:
        Dictionary with available storage adapters and metadata

    Example:
        >>> result = await oneiric_discover_storage()
        >>> print(f"Found {result['count']} storage backends")
        >>> for adapter in result["adapters"]:
        ...     print(f"  - {adapter['provider']} (priority: {adapter['priority']})")

    Note:
        Requires Oneiric MCP server to be running and accessible via stdio.
    """
    from session_buddy.mcp_clients import OneiricMCPClient

    try:
        async with OneiricMCPClient(
            server_path=server_path,
            timeout_seconds=timeout_seconds,
        ) as client:
            adapters = await client.list_storage_adapters()

            # Group adapters by provider for better organization
            providers = {}
            for adapter in adapters:
                provider = adapter.get("provider", "unknown")
                if provider not in providers:
                    providers[provider] = []
                providers[provider].append(adapter)

            return {
                "success": True,
                "count": len(adapters),
                "adapters": adapters,
                "providers": list(providers.keys()),
                "note": "Storage backends discovered via Oneiric MCP",
                "server_path": str(client.server_path),
            }

    except ImportError as e:
        logger.error(f"Failed to import OneiricMCPClient: {e}")
        return {
            "success": False,
            "error": f"MCP package not available: {e}",
            "adapters": [],
            "count": 0,
        }
    except RuntimeError as e:
        logger.error(f"Failed to connect to Oneiric MCP: {e}")
        return {
            "success": False,
            "error": str(e),
            "adapters": [],
            "count": 0,
            "note": "Ensure Oneiric MCP server is available",
        }
    except Exception as e:
        logger.exception(f"Unexpected error discovering storage backends: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "adapters": [],
            "count": 0,
        }


async def oneiric_resolve_storage(
    provider: str,
    server_path: str | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Resolve a specific Oneiric storage backend.

    This tool resolves a specific storage provider via Oneiric, returning
    information about whether the adapter was selected and its health status.

    Args:
        provider: Storage provider name (e.g., "s3", "local", "azure", "gcs")
        server_path: Optional path to Oneiric MCP server directory
        timeout_seconds: Timeout for MCP tool calls (default: 10)

    Returns:
        Resolved adapter information with selection status

    Example:
        >>> result = await oneiric_resolve_storage("s3")
        >>> if result["selected"]:
        ...     print("S3 storage backend resolved successfully")
        ...     print(f"Provider: {result['provider']}")
        ...     print(f"Healthy: {result.get('healthy', 'unknown')}")

    Note:
        Requires Oneiric MCP server to be running and accessible via stdio.
    """
    from session_buddy.mcp_clients import OneiricMCPClient

    if not provider or not provider.strip():
        return {
            "success": False,
            "error": "Provider cannot be empty",
            "provider": provider,
            "selected": False,
        }

    try:
        async with OneiricMCPClient(
            server_path=server_path,
            timeout_seconds=timeout_seconds,
        ) as client:
            result = await client.resolve_storage_backend(provider.strip())

            # Add metadata
            result["server_path"] = str(client.server_path)
            result["success"] = result.get("selected", False)

            if "error" in result:
                result["success"] = False

            return result

    except ImportError as e:
        logger.error(f"Failed to import OneiricMCPClient: {e}")
        return {
            "success": False,
            "error": f"MCP package not available: {e}",
            "provider": provider,
            "selected": False,
        }
    except RuntimeError as e:
        logger.error(f"Failed to connect to Oneiric MCP: {e}")
        return {
            "success": False,
            "error": str(e),
            "provider": provider,
            "selected": False,
            "note": "Ensure Oneiric MCP server is available",
        }
    except Exception as e:
        logger.exception(f"Unexpected error resolving storage backend {provider}: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "provider": provider,
            "selected": False,
        }


async def oneiric_storage_health(
    provider: str,
    server_path: str | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Check health status of a Oneiric storage backend.

    This tool performs a health check on a specific storage provider to
    verify it is available and functioning correctly.

    Args:
        provider: Storage provider name to check
        server_path: Optional path to Oneiric MCP server directory
        timeout_seconds: Timeout for MCP tool calls (default: 10)

    Returns:
        Health check result with healthy status

    Example:
        >>> result = await oneiric_storage_health("s3")
        >>> if result["healthy"]:
        ...     print("S3 backend is healthy and available")
        >>> elif result.get("has_health_check"):
        ...     print(f"S3 backend is unhealthy: {result.get('error', 'Unknown error')}")
        >>> else:
        ...     print("S3 backend does not implement health checks")

    Note:
        Requires Oneiric MCP server to be running and accessible via stdio.
        Not all storage backends implement health checks.
    """
    from session_buddy.mcp_clients import OneiricMCPClient

    if not provider or not provider.strip():
        return {
            "success": False,
            "error": "Provider cannot be empty",
            "provider": provider,
            "healthy": False,
        }

    try:
        async with OneiricMCPClient(
            server_path=server_path,
            timeout_seconds=timeout_seconds,
        ) as client:
            health = await client.check_storage_health(provider.strip())

            # Add metadata
            health["server_path"] = str(client.server_path)
            health["success"] = health.get("healthy", False)

            if "error" in health:
                health["success"] = False

            return health

    except ImportError as e:
        logger.error(f"Failed to import OneiricMCPClient: {e}")
        return {
            "success": False,
            "error": f"MCP package not available: {e}",
            "provider": provider,
            "healthy": False,
        }
    except RuntimeError as e:
        logger.error(f"Failed to connect to Oneiric MCP: {e}")
        return {
            "success": False,
            "error": str(e),
            "provider": provider,
            "healthy": False,
            "note": "Ensure Oneiric MCP server is available",
        }
    except Exception as e:
        logger.exception(
            f"Unexpected error checking storage health for {provider}: {e}"
        )
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "provider": provider,
            "healthy": False,
        }


async def oneiric_explain_storage(
    provider: str,
    server_path: str | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Explain why a specific storage adapter was selected.

    This tool provides detailed information about why Oneiric selected
    a particular storage adapter, including priority scores and alternatives.

    Args:
        provider: Storage provider name to explain (e.g., "local")
        server_path: Optional path to Oneiric MCP server directory
        timeout_seconds: Timeout for MCP tool calls (default: 10)

    Returns:
        Resolution explanation with ranked candidates

    Example:
        >>> result = await oneiric_explain_storage("local")
        >>> print(f"Selected: {result['selected_provider']}")
        >>> for candidate in result['candidates']:
        ...     print(f"  - {candidate['provider']}: score={candidate['score']}")

    Note:
        Requires Oneiric MCP server to be running and accessible via stdio.
    """
    from session_buddy.mcp_clients import OneiricMCPClient

    if not provider or not provider.strip():
        return {
            "success": False,
            "error": "Provider cannot be empty",
            "provider": provider,
        }

    try:
        async with OneiricMCPClient(
            server_path=server_path,
            timeout_seconds=timeout_seconds,
        ) as client:
            # Explain resolution for storage adapter
            session = client._ensure_connected()

            import asyncio

            result = await asyncio.wait_for(
                session.call_tool(
                    "explain_resolution",
                    {
                        "domain": "adapter",
                        "key": "storage",
                    },
                ),
                timeout=timeout_seconds,
            )

            # Add metadata
            result["server_path"] = str(client.server_path)
            result["success"] = "error" not in result

            return result

    except ImportError as e:
        logger.error(f"Failed to import OneiricMCPClient: {e}")
        return {
            "success": False,
            "error": f"MCP package not available: {e}",
            "provider": provider,
        }
    except RuntimeError as e:
        logger.error(f"Failed to connect to Oneiric MCP: {e}")
        return {
            "success": False,
            "error": str(e),
            "provider": provider,
            "note": "Ensure Oneiric MCP server is available",
        }
    except Exception as e:
        logger.exception(f"Unexpected error explaining storage resolution: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "provider": provider,
        }


def register_oneiric_discovery_tools(mcp_instance: Any) -> None:
    """Register Oneiric discovery tools with MCP server.

    Args:
        mcp_instance: FastMCP server instance

    Example:
        >>> from session_buddy.mcp.server import mcp
        >>> from session_buddy.mcp.tools.oneiric import (
        ...     register_oneiric_discovery_tools,
        ... )
        >>> register_oneiric_discovery_tools(mcp)
    """
    mcp_instance.tool()(oneiric_discover_storage)
    mcp_instance.tool()(oneiric_resolve_storage)
    mcp_instance.tool()(oneiric_storage_health)
    mcp_instance.tool()(oneiric_explain_storage)

    logger.info("Registered Oneiric storage discovery tools")


__all__ = [
    "oneiric_discover_storage",
    "oneiric_resolve_storage",
    "oneiric_storage_health",
    "oneiric_explain_storage",
    "register_oneiric_discovery_tools",
]
