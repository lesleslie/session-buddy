"""Integration tests for Oneiric discovery tools.

Tests the MCP tools that Session-Buddy exposes for Oneiric integration.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.oneiric.oneiric_discovery_tools import (
    check_storage_health,
    discover_storage_backends,
    explain_storage_resolution,
    resolve_storage_backend,
)


# Test fixtures
@pytest.fixture
def mock_oneiric_client():
    """Mock OneiricMCPClient."""
    with patch("session_buddy.mcp.tools.oneiric.oneiric_discovery_tools.OneiricMCPClient") as mock:
        client_instance = MagicMock()
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=None)
        client_instance.server_path = MagicMock()
        client_instance.server_path.__str__ = lambda self: "/mock/path"

        # Setup client methods
        client_instance.list_storage_adapters = AsyncMock()
        client_instance.resolve_storage_backend = AsyncMock()
        client_instance.check_storage_health = AsyncMock()
        client_instance._ensure_connected = MagicMock()

        mock.return_value = client_instance
        yield client_instance


class TestDiscoverStorageBackends:
    """Test suite for discover_storage_backends tool."""

    @pytest.mark.asyncio
    async def test_discover_success(self, mock_oneiric_client):
        """Test discovering storage backends returns results."""
        mock_oneiric_client.list_storage_adapters.return_value = [
            {"provider": "local", "priority": 100, "stack_level": 0},
            {"provider": "s3", "priority": 90, "stack_level": 0},
        ]

        result = await discover_storage_backends()

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["adapters"]) == 2
        assert "local" in result["providers"]
        assert "s3" in result["providers"]

    @pytest.mark.asyncio
    async def test_discover_empty(self, mock_oneiric_client):
        """Test discovering handles empty results."""
        mock_oneiric_client.list_storage_adapters.return_value = []

        result = await discover_storage_backends()

        assert result["success"] is True
        assert result["count"] == 0
        assert result["adapters"] == []

    @pytest.mark.asyncio
    async def test_discover_import_error(self):
        """Test discovering handles import error."""
        with patch(
            "session_buddy.mcp.tools.oneiric.oneiric_discovery_tools.OneiricMCPClient",
            side_effect=ImportError("mcp package not available"),
        ):
            result = await discover_storage_backends()

            assert result["success"] is False
            assert "error" in result
            assert "MCP package not available" in result["error"]

    @pytest.mark.asyncio
    async def test_discover_connection_error(self, mock_oneiric_client):
        """Test discovering handles connection error."""
        mock_oneiric_client.__aenter__.side_effect = RuntimeError("Connection failed")

        result = await discover_storage_backends()

        assert result["success"] is False
        assert "error" in result


class TestResolveStorageBackend:
    """Test suite for resolve_storage_backend tool."""

    @pytest.mark.asyncio
    async def test_resolve_success(self, mock_oneiric_client):
        """Test resolving storage backend succeeds."""
        mock_oneiric_client.resolve_storage_backend.return_value = {
            "domain": "adapter",
            "key": "storage",
            "provider": "s3",
            "selected": True,
            "healthy": True,
        }

        result = await resolve_storage_backend("s3")

        assert result["success"] is True
        assert result["selected"] is True
        assert result["provider"] == "s3"
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_resolve_not_selected(self, mock_oneiric_client):
        """Test resolving backend when not selected."""
        mock_oneiric_client.resolve_storage_backend.return_value = {
            "selected": False,
            "error": "Adapter not found",
        }

        result = await resolve_storage_backend("nonexistent")

        assert result["success"] is False
        assert result["selected"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_resolve_empty_provider(self, mock_oneiric_client):
        """Test resolving with empty provider."""
        result = await resolve_storage_backend("")

        assert result["success"] is False
        assert "error" in result
        assert "cannot be empty" in result["error"]

    @pytest.mark.asyncio
    async def test_resolve_whitespace_provider(self, mock_oneiric_client):
        """Test resolving with whitespace provider."""
        result = await resolve_storage_backend("  ")

        assert result["success"] is False
        # Client should strip whitespace, making it empty
        mock_oneiric_client.resolve_storage_backend.assert_not_called()


class TestCheckStorageHealth:
    """Test suite for check_storage_health tool."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_oneiric_client):
        """Test health check returns status."""
        mock_oneiric_client.check_storage_health.return_value = {
            "healthy": True,
            "has_health_check": True,
            "provider": "local",
        }

        result = await check_storage_health("local")

        assert result["success"] is True
        assert result["healthy"] is True
        assert result["has_health_check"] is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_oneiric_client):
        """Test health check handles unhealthy backend."""
        mock_oneiric_client.check_storage_health.return_value = {
            "healthy": False,
            "has_health_check": True,
            "error": "Connection refused",
        }

        result = await check_storage_health("s3")

        assert result["success"] is False
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_empty_provider(self, mock_oneiric_client):
        """Test health check with empty provider."""
        result = await check_storage_health("")

        assert result["success"] is False
        assert result["healthy"] is False
        assert "error" in result


class TestExplainStorageResolution:
    """Test suite for explain_storage_resolution tool."""

    @pytest.mark.asyncio
    async def test_explain_success(self, mock_oneiric_client):
        """Test explaining resolution returns candidates."""
        mock_session = MagicMock()
        mock_session.call_tool = AsyncMock(
            return_value={
                "domain": "adapter",
                "key": "storage",
                "selected_provider": "local",
                "candidates": [
                    {
                        "provider": "local",
                        "priority": 100,
                        "score": 100,
                        "reason": "Highest priority",
                    },
                ],
            }
        )
        mock_oneiric_client._ensure_connected.return_value = mock_session

        result = await explain_storage_resolution("local")

        assert result["success"] is True
        assert result["selected_provider"] == "local"
        assert len(result["candidates"]) == 1

    @pytest.mark.asyncio
    async def test_explain_empty_provider(self, mock_oneiric_client):
        """Test explaining with empty provider."""
        result = await explain_storage_resolution("")

        assert result["success"] is False
        assert "error" in result


class TestOneiricDiscoveryToolsIntegration:
    """Integration tests for Oneiric discovery tools."""

    @pytest.mark.asyncio
    async def test_end_to_end_discovery_workflow(self, mock_oneiric_client):
        """Test complete workflow: discover -> resolve -> health check."""
        # Setup mock responses
        mock_oneiric_client.list_storage_adapters.return_value = [
            {"provider": "local", "priority": 100},
            {"provider": "s3", "priority": 90},
        ]
        mock_oneiric_client.resolve_storage_backend.return_value = {
            "selected": True,
            "provider": "local",
            "healthy": True,
        }
        mock_oneiric_client.check_storage_health.return_value = {
            "healthy": True,
            "has_health_check": True,
        }

        # Step 1: Discover
        discover_result = await discover_storage_backends()
        assert discover_result["success"] is True
        assert len(discover_result["adapters"]) == 2

        # Step 2: Resolve
        resolve_result = await resolve_storage_backend("local")
        assert resolve_result["success"] is True
        assert resolve_result["selected"] is True

        # Step 3: Health check
        health_result = await check_storage_health("local")
        assert health_result["success"] is True
        assert health_result["healthy"] is True
