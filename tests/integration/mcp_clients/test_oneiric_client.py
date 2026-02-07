"""Integration tests for Oneiric MCP client.

Tests the integration between Session-Buddy and Oneiric MCP for storage
backend discovery and resolution.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp_clients import OneiricMCPClient


# Test fixtures
@pytest.fixture
def mock_server_params():
    """Mock stdio server parameters."""
    with patch("session_buddy.mcp_clients.oneiric_client.StdioServerParameters") as mock:
        mock.return_value = MagicMock(
            command="uv",
            args=["--directory", "/path/to/oneiric-mcp", "run", "python", "-m", "oneiric_mcp"],
        )
        yield mock


@pytest.fixture
def mock_client_session():
    """Mock MCP client session."""
    with patch("session_buddy.mcp_clients.oneiric_client.ClientSession") as mock:
        session_instance = MagicMock()
        session_instance.__aenter__ = AsyncMock(return_value=session_instance)
        session_instance.__aexit__ = AsyncMock(return_value=None)
        session_instance.initialize = AsyncMock()
        session_instance.call_tool = AsyncMock()

        mock.return_value = session_instance
        yield session_instance


class TestOneiricMCPClient:
    """Test suite for OneiricMCPClient."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client can be initialized with default parameters."""
        client = OneiricMCPClient()

        assert client.timeout_seconds == 10
        assert client._session is None
        assert not client._initialized

    @pytest.mark.asyncio
    async def test_client_custom_parameters(self):
        """Test client can be initialized with custom parameters."""
        client = OneiricMCPClient(
            server_path="/custom/path",
            timeout_seconds=30,
        )

        assert str(client.server_path) == "/custom/path"
        assert client.timeout_seconds == 30

    @pytest.mark.asyncio
    async def test_context_manager_connection(self, mock_client_session):
        """Test client connects via context manager."""
        async with OneiricMCPClient() as client:
            assert client._initialized is True
            assert client._session is not None

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self, mock_client_session):
        """Test client properly cleans up connection."""
        async with OneiricMCPClient() as client:
            session = client._session

        # After exiting context, should be cleaned up
        assert client._initialized is False

    @pytest.mark.asyncio
    async def test_list_storage_adapters_success(self, mock_client_session):
        """Test listing storage adapters returns results."""
        # Mock response
        mock_client_session.call_tool.return_value = {
            "count": 2,
            "adapters": [
                {"provider": "local", "priority": 100, "stack_level": 0},
                {"provider": "s3", "priority": 90, "stack_level": 0},
            ],
        }

        async with OneiricMCPClient() as client:
            adapters = await client.list_storage_adapters()

            assert len(adapters) == 2
            assert adapters[0]["provider"] == "local"
            assert adapters[1]["provider"] == "s3"

            # Verify correct parameters
            mock_client_session.call_tool.assert_called_once_with(
                "list_adapters",
                {"category": "storage"},
            )

    @pytest.mark.asyncio
    async def test_list_storage_adapters_timeout(self, mock_client_session):
        """Test listing adapters handles timeout."""
        # Mock timeout
        mock_client_session.call_tool.side_effect = asyncio.TimeoutError()

        async with OneiricMCPClient(timeout_seconds=1) as client:
            with pytest.raises(asyncio.TimeoutError):
                await client.list_storage_adapters()

    @pytest.mark.asyncio
    async def test_list_storage_adapters_empty(self, mock_client_session):
        """Test listing adapters handles empty response."""
        mock_client_session.call_tool.return_value = {"adapters": []}

        async with OneiricMCPClient() as client:
            adapters = await client.list_storage_adapters()

            assert adapters == []

    @pytest.mark.asyncio
    async def test_resolve_storage_backend_success(self, mock_client_session):
        """Test resolving storage backend returns success."""
        mock_client_session.call_tool.return_value = {
            "domain": "adapter",
            "key": "storage",
            "provider": "s3",
            "selected": True,
            "healthy": True,
        }

        async with OneiricMCPClient() as client:
            result = await client.resolve_storage_backend("s3")

            assert result["selected"] is True
            assert result["provider"] == "s3"
            assert result["healthy"] is True

            # Verify correct parameters
            mock_client_session.call_tool.assert_called_once_with(
                "resolve_adapter",
                {
                    "domain": "adapter",
                    "key": "storage",
                    "provider": "s3",
                },
            )

    @pytest.mark.asyncio
    async def test_resolve_storage_backend_not_selected(self, mock_client_session):
        """Test resolving backend handles not selected case."""
        mock_client_session.call_tool.return_value = {
            "domain": "adapter",
            "key": "storage",
            "provider": "nonexistent",
            "selected": False,
            "error": "Adapter not found",
        }

        async with OneiricMCPClient() as client:
            result = await client.resolve_storage_backend("nonexistent")

            assert result["selected"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_check_storage_health_success(self, mock_client_session):
        """Test checking storage health returns status."""
        mock_client_session.call_tool.return_value = {
            "domain": "adapter",
            "key": "storage",
            "provider": "local",
            "healthy": True,
            "has_health_check": True,
        }

        async with OneiricMCPClient() as client:
            health = await client.check_storage_health("local")

            assert health["healthy"] is True
            assert health["has_health_check"] is True

            # Verify correct parameters
            mock_client_session.call_tool.assert_called_once_with(
                "get_adapter_health",
                {
                    "domain": "adapter",
                    "key": "storage",
                    "provider": "local",
                },
            )

    @pytest.mark.asyncio
    async def test_check_storage_health_unhealthy(self, mock_client_session):
        """Test checking health handles unhealthy backend."""
        mock_client_session.call_tool.return_value = {
            "domain": "adapter",
            "key": "storage",
            "provider": "s3",
            "healthy": False,
            "has_health_check": True,
            "error": "Connection refused",
        }

        async with OneiricMCPClient() as client:
            health = await client.check_storage_health("s3")

            assert health["healthy"] is False
            assert "error" in health

    @pytest.mark.asyncio
    async def test_list_adapter_categories(self, mock_client_session):
        """Test listing adapter categories."""
        mock_client_session.call_tool.return_value = {
            "count": 16,
            "categories": [
                "storage",
                "cache",
                "database",
                "vector",
                "secrets",
            ],
        }

        async with OneiricMCPClient() as client:
            result = await client.list_adapter_categories()

            assert result["count"] == 16
            assert "storage" in result["categories"]
            assert "cache" in result["categories"]

    @pytest.mark.asyncio
    async def test_error_not_connected(self):
        """Test error handling when client is not connected."""
        client = OneiricMCPClient()

        with pytest.raises(RuntimeError, match="Client not connected"):
            await client.list_storage_adapters()

    @pytest.mark.asyncio
    async def test_error_provider_validation(self, mock_client_session):
        """Test provider validation in resolve backend."""
        async with OneiricMCPClient() as client:
            result = await client.resolve_storage_backend("")

            assert result["selected"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_error_provider_validation_health(self, mock_client_session):
        """Test provider validation in health check."""
        async with OneiricMCPClient() as client:
            result = await client.check_storage_health("  ")

            assert result["healthy"] is False
            assert "error" in result


class TestOneiricMCPClientIntegration:
    """Integration tests requiring actual MCP server (marked as slow)."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_real_connection_fails_if_server_not_available(self):
        """Test that connection fails gracefully when server is not available."""
        # Use a path that won't exist
        client = OneiricMCPClient(server_path="/nonexistent/path")

        with pytest.raises((RuntimeError, ImportError, FileNotFoundError)):
            async with client:
                await client.list_storage_adapters()
