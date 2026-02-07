"""Oneiric MCP client for storage adapter discovery.

This module provides an MCP client wrapper that Session-Buddy can use to
communicate with Oneiric MCP server for storage adapter discovery and resolution.

Example:
    >>> from session_buddy.mcp_clients import OneiricMCPClient
    >>> async with OneiricMCPClient() as client:
    ...     adapters = await client.list_storage_adapters()
    ...     print(f"Found {len(adapters)} storage adapters")
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from mcp import ClientSession, StdioServerParameters

logger = logging.getLogger(__name__)


class OneiricMCPClient:
    """MCP client for communicating with Oneiric MCP server.

    This client provides a simplified interface for querying Oneiric MCP
    for storage adapter discovery, resolution, and health checks.

    Attributes:
        server_path: Path to Oneiric MCP server directory
        timeout_seconds: Timeout for MCP tool calls

    Example:
        >>> async with OneiricMCPClient() as client:
        ...     adapters = await client.list_storage_adapters()
        ...     for adapter in adapters:
        ...         print(f"Provider: {adapter['provider']}")
    """

    def __init__(
        self,
        server_path: str | Path | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        """Initialize Oneiric MCP client.

        Args:
            server_path: Path to Oneiric MCP server directory
            timeout_seconds: Timeout for MCP tool calls in seconds
        """
        self.server_path = (
            Path(server_path) if server_path else self._default_server_path()
        )
        self.timeout_seconds = timeout_seconds
        self._session: ClientSession | None = None
        self._initialized = False

    def _default_server_path(self) -> Path:
        """Get default Oneiric MCP server path."""
        # Try common locations
        candidates = [
            Path.home() / "Projects" / "oneiric-mcp",
            Path("/Users/les/Projects/oneiric-mcp"),
            Path.cwd().parent / "oneiric-mcp",
        ]

        for path in candidates:
            if (path / "oneiric_mcp" / "__init__.py").exists():
                return path

        # Fallback to home directory
        return Path.home() / "Projects" / "oneiric-mcp"

    def _create_server_params(self) -> StdioServerParameters:
        """Create stdio server parameters for Oneiric MCP.

        Returns:
            StdioServerParameters configured for Oneiric MCP

        Raises:
            ImportError: If mcp package is not available
        """
        try:
            from mcp import StdioServerParameters
        except ImportError as e:
            msg = "mcp package is required. Install with: pip install mcp"
            raise ImportError(msg) from e

        return StdioServerParameters(
            command="uv",
            args=[
                "--directory",
                str(self.server_path),
                "run",
                "python",
                "-m",
                "oneiric_mcp",
            ],
        )

    async def __aenter__(self) -> OneiricMCPClient:
        """Enter context manager and connect to MCP server.

        Returns:
            Self for fluent chaining

        Raises:
            RuntimeError: If connection fails
        """
        try:
            from mcp import ClientSession
        except ImportError as e:
            msg = "mcp package is required. Install with: pip install mcp"
            raise ImportError(msg) from e

        server_params = self._create_server_params()
        self._session = ClientSession(server_params)

        try:
            await self._session.__aenter__()
            await self._session.initialize()
            self._initialized = True
            logger.info(f"Connected to Oneiric MCP at {self.server_path}")
        except Exception as e:
            logger.error(f"Failed to connect to Oneiric MCP: {e}")
            self._session = None
            self._initialized = False
            raise

        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit context manager and close connection."""
        if self._session:
            try:
                await self._session.__aexit__(*args)
                logger.info("Disconnected from Oneiric MCP")
            except Exception as e:
                logger.warning(f"Error closing Oneiric MCP connection: {e}")
            finally:
                self._session = None
                self._initialized = False

    def _ensure_connected(self) -> ClientSession:
        """Ensure client is connected.

        Returns:
            The MCP client session

        Raises:
            RuntimeError: If client is not connected
        """
        if not self._initialized or not self._session:
            msg = (
                "Client not connected. Use async context manager: "
                "'async with OneiricMCPClient() as client:'"
            )
            raise RuntimeError(msg)
        return self._session

    async def list_storage_adapters(self) -> list[dict[str, Any]]:
        """List all available storage adapters from Oneiric.

        Returns:
            List of storage adapter dictionaries with provider, priority, etc.

        Raises:
            RuntimeError: If client is not connected
            asyncio.TimeoutError: If request times out

        Example:
            >>> async with OneiricMCPClient() as client:
            ...     adapters = await client.list_storage_adapters()
            ...     for adapter in adapters:
            ...         print(f"{adapter['provider']}: priority={adapter['priority']}")
        """
        session = self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                session.call_tool("list_adapters", {"category": "storage"}),
                timeout=self.timeout_seconds,
            )

            # Cast to dict for dict-like access
            result_dict = cast(dict[str, Any], result)  # type: ignore[assignment]
            adapters = result_dict.get("adapters", [])  # type: ignore[attr-defined]
            logger.info(f"Listed {len(adapters)} storage adapters")
            return result_dict.get("adapters", [])  # type: ignore[return-value]

        except TimeoutError:
            logger.error(
                f"Timeout listing storage adapters after {self.timeout_seconds}s"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to list storage adapters: {e}")
            return []

    async def resolve_storage_backend(
        self,
        provider: str,
    ) -> dict[str, Any]:
        """Resolve a specific storage backend via Oneiric.

        Args:
            provider: Storage provider name (e.g., "s3", "local", "azure")

        Returns:
            Resolved adapter information with selected status

        Raises:
            RuntimeError: If client is not connected
            asyncio.TimeoutError: If request times out

        Example:
            >>> async with OneiricMCPClient() as client:
            ...     result = await client.resolve_storage_backend("s3")
            ...     if result["selected"]:
            ...         print("S3 storage backend resolved successfully")
        """
        session = self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                session.call_tool(
                    "resolve_adapter",
                    {
                        "domain": "adapter",
                        "key": "storage",
                        "provider": provider,
                    },
                ),
                timeout=self.timeout_seconds,
            )

            # Cast to dict for dict-like access
            result_dict = cast(dict[str, Any], result)  # type: ignore[assignment]
            logger.info(
                f"Resolved storage backend: {provider}, selected={result_dict.get('selected', False)}"  # type: ignore[attr-defined]
            )
            return result_dict  # type: ignore[return-value]

        except TimeoutError:
            logger.error(
                f"Timeout resolving {provider} backend after {self.timeout_seconds}s"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to resolve storage backend {provider}: {e}")
            return {
                "error": str(e),
                "provider": provider,
                "selected": False,
                "healthy": False,
            }

    async def check_storage_health(self, provider: str) -> dict[str, Any]:
        """Check health status of a storage backend.

        Args:
            provider: Storage provider name to check

        Returns:
            Health check result with healthy status

        Raises:
            RuntimeError: If client is not connected
            asyncio.TimeoutError: If request times out

        Example:
            >>> async with OneiricMCPClient() as client:
            ...     health = await client.check_storage_health("s3")
            ...     if health["healthy"]:
            ...         print("S3 backend is healthy")
        """
        session = self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                session.call_tool(
                    "get_adapter_health",
                    {
                        "domain": "adapter",
                        "key": "storage",
                        "provider": provider,
                    },
                ),
                timeout=self.timeout_seconds,
            )

            # Cast to dict for dict-like access
            result_dict = cast(dict[str, Any], result)  # type: ignore[assignment]
            logger.info(
                f"Health check for {provider}: healthy={result_dict.get('healthy', False)}"  # type: ignore[attr-defined]
            )
            return result_dict  # type: ignore[return-value]

        except TimeoutError:
            logger.error(
                f"Timeout checking {provider} health after {self.timeout_seconds}s"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to check storage health for {provider}: {e}")
            return {
                "error": str(e),
                "provider": provider,
                "healthy": False,
                "has_health_check": False,
            }

    async def list_adapter_categories(self) -> dict[str, Any]:
        """List all available adapter categories.

        Returns:
            Dictionary with categories list

        Example:
            >>> async with OneiricMCPClient() as client:
            ...     categories = await client.list_adapter_categories()
            ...     print(f"Available: {categories['categories']}")
        """
        session = self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                session.call_tool("list_adapter_categories", {}),
                timeout=self.timeout_seconds,
            )

            # Cast to dict for dict-like access
            result_dict = cast(dict[str, Any], result)  # type: ignore[assignment]
            logger.info(f"Listed {result_dict.get('count', 0)} adapter categories")  # type: ignore[attr-defined]
            return result_dict  # type: ignore[return-value]

        except TimeoutError:
            logger.error(f"Timeout listing categories after {self.timeout_seconds}s")
            raise
        except Exception as e:
            logger.error(f"Failed to list adapter categories: {e}")
            return {"count": 0, "categories": []}


__all__ = ["OneiricMCPClient"]
