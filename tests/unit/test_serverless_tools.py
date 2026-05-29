"""Unit tests for serverless session management tools."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.infrastructure.serverless_tools import (
    _require_serverless_manager,
    _execute_serverless_operation,
    _create_serverless_session_impl,
    _create_serverless_session_operation,
    _delete_serverless_session_impl,
    _delete_serverless_session_operation,
    _get_serverless_session_impl,
    _get_serverless_session_operation,
    _cleanup_serverless_sessions_impl,
    _cleanup_serverless_sessions_operation,
    _list_serverless_sessions_impl,
    _list_serverless_sessions_operation,
    register_serverless_tools,
    _format_storage_test_results,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_manager():
    """Create a mock serverless manager."""
    manager = MagicMock()
    manager.create_session = AsyncMock(return_value="sess_abc123")
    manager.get_session = AsyncMock(return_value={
        "session_id": "sess_abc123",
        "user_id": "user_1",
        "project_id": "proj_1",
        "created_at": "2026-05-25T10:00:00Z",
        "expires_at": "2026-05-26T10:00:00Z",
        "session_data": {"key": "value"},
    })
    manager.update_session = AsyncMock(return_value=True)
    manager.delete_session = AsyncMock(return_value=True)
    manager.list_sessions = AsyncMock(return_value=[
        {
            "session_id": "sess_abc123",
            "user_id": "user_1",
            "project_id": "proj_1",
            "expires_at": "2026-05-26T10:00:00Z",
        },
        {
            "session_id": "sess_def456",
            "user_id": "user_1",
            "project_id": "proj_2",
            "expires_at": "2026-05-27T10:00:00Z",
        },
    ])
    manager.cleanup_expired_sessions = AsyncMock(return_value=3)
    manager.test_storage_backends = AsyncMock(return_value={
        "redis": {"available": True, "latency_ms": 1.5, "status": "OK"},
        "s3": {"available": False, "error": "Connection refused"},
        "local": {"available": True, "latency_ms": 0.8, "status": "OK"},
    })
    manager.configure_storage = AsyncMock(return_value=True)
    return manager


# ============================================================================
# _require_serverless_manager Tests
# ============================================================================


class TestRequireServerlessManager:
    """Tests for _require_serverless_manager()."""

    @pytest.mark.asyncio
    async def test_returns_manager_when_available(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools.resolve_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _require_serverless_manager()
            assert result is mock_manager

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_manager_none(self) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools.resolve_serverless_manager",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                await _require_serverless_manager()
            assert "Serverless mode not available" in str(exc_info.value)
            assert "redis" in str(exc_info.value)
            assert "boto3" in str(exc_info.value)


# ============================================================================
# _execute_serverless_operation Tests
# ============================================================================


class TestExecuteServerlessOperation:
    """Tests for _execute_serverless_operation()."""

    @pytest.mark.asyncio
    async def test_successful_operation(self, mock_manager) -> None:
        async def fake_op(manager):
            return "success"

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _execute_serverless_operation("Test op", fake_op)
            assert result == "success"

    @pytest.mark.asyncio
    async def test_runtime_error_returns_formatted_message(self, mock_manager) -> None:
        async def fake_op(manager):
            raise RuntimeError("Serverless mode not available. Install redis")

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _execute_serverless_operation("Test op", fake_op)
            assert "❌" in result
            assert "Serverless mode not available" in result

    @pytest.mark.asyncio
    async def test_generic_exception_returns_operation_failed(self, mock_manager) -> None:
        async def fake_op(manager):
            raise ValueError("Some error")

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            with patch(
                "session_buddy.mcp.tools.infrastructure.serverless_tools._get_logger"
            ) as mock_logger:
                result = await _execute_serverless_operation("Test op", fake_op)
                assert "❌" in result
                assert "Test op failed" in result
                mock_logger.return_value.exception.assert_called_once()


# ============================================================================
# _create_serverless_session_operation Tests
# ============================================================================


class TestCreateServerlessSessionOperation:
    """Tests for _create_serverless_session_operation()."""

    @pytest.mark.asyncio
    async def test_creates_session_with_ttl(self, mock_manager) -> None:
        result = await _create_serverless_session_operation(
            mock_manager,
            user_id="user_1",
            project_id="proj_1",
            session_data={"foo": "bar"},
            ttl_hours=48,
        )
        assert "✅" in result
        assert "sess_abc123" in result
        assert "48" in result
        assert "hours" in result
        mock_manager.create_session.assert_awaited_once_with(
            user_id="user_1",
            project_id="proj_1",
            session_data={"foo": "bar"},
            ttl_hours=48,
        )

    @pytest.mark.asyncio
    async def test_creates_session_with_default_ttl(self, mock_manager) -> None:
        result = await _create_serverless_session_operation(
            mock_manager,
            user_id="user_1",
            project_id="proj_1",
            session_data=None,
            ttl_hours=24,
        )
        assert "✅" in result
        assert "24" in result


# ============================================================================
# _create_serverless_session_impl Tests
# ============================================================================


class TestCreateServerlessSessionImpl:
    """Tests for _create_serverless_session_impl()."""

    @pytest.mark.asyncio
    async def test_creates_session_successfully(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _create_serverless_session_impl(
                user_id="user_1",
                project_id="proj_1",
                session_data={"test": True},
                ttl_hours=12,
            )
            assert "✅" in result
            assert "sess_abc123" in result
            assert "12 hours" in result

    @pytest.mark.asyncio
    async def test_creates_session_without_session_data(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _create_serverless_session_impl(
                user_id="user_1",
                project_id="proj_1",
            )
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_returns_error_when_manager_unavailable(self) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(side_effect=RuntimeError("Serverless mode not available")),
        ):
            result = await _create_serverless_session_impl(
                user_id="user_1",
                project_id="proj_1",
            )
            assert "❌" in result
            assert "Serverless mode not available" in result

    @pytest.mark.asyncio
    async def test_ttl_behavior_custom_hours(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _create_serverless_session_impl(
                user_id="user_1",
                project_id="proj_1",
                ttl_hours=72,
            )
            mock_manager.create_session.assert_awaited()
            call_kwargs = mock_manager.create_session.call_args.kwargs
            assert call_kwargs["ttl_hours"] == 72


# ============================================================================
# _get_serverless_session_operation Tests
# ============================================================================


class TestGetServerlessSessionOperation:
    """Tests for _get_serverless_session_operation()."""

    @pytest.mark.asyncio
    async def test_returns_session_details(self, mock_manager) -> None:
        result = await _get_serverless_session_operation(mock_manager, "sess_abc123")
        assert "📦" in result
        assert "sess_abc123" in result
        assert "user_1" in result
        assert "proj_1" in result

    @pytest.mark.asyncio
    async def test_returns_not_found_for_missing_session(self, mock_manager) -> None:
        mock_manager.get_session = AsyncMock(return_value=None)
        result = await _get_serverless_session_operation(mock_manager, "nonexistent")
        assert "❌" in result
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_displays_session_data(self, mock_manager) -> None:
        result = await _get_serverless_session_operation(mock_manager, "sess_abc123")
        assert "key" in result
        assert "value" in result


# ============================================================================
# _get_serverless_session_impl Tests
# ============================================================================


class TestGetServerlessSessionImpl:
    """Tests for _get_serverless_session_impl()."""

    @pytest.mark.asyncio
    async def test_gets_session_successfully(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _get_serverless_session_impl("sess_abc123")
            assert "sess_abc123" in result

    @pytest.mark.asyncio
    async def test_handles_manager_unavailable(self) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(side_effect=RuntimeError("Serverless mode not available")),
        ):
            result = await _get_serverless_session_impl("sess_abc123")
            assert "❌" in result


# ============================================================================
# _delete_serverless_session_operation Tests
# ============================================================================


class TestDeleteServerlessSessionOperation:
    """Tests for _delete_serverless_session_operation()."""

    @pytest.mark.asyncio
    async def test_deletes_session_successfully(self, mock_manager) -> None:
        result = await _delete_serverless_session_operation(mock_manager, "sess_abc123")
        assert "✅" in result
        assert "sess_abc123" in result
        mock_manager.delete_session.assert_awaited_once_with("sess_abc123")

    @pytest.mark.asyncio
    async def test_returns_not_found_when_delete_fails(self, mock_manager) -> None:
        mock_manager.delete_session = AsyncMock(return_value=False)
        result = await _delete_serverless_session_operation(mock_manager, "nonexistent")
        assert "❌" in result
        assert "not found" in result.lower()


# ============================================================================
# _delete_serverless_session_impl Tests
# ============================================================================


class TestDeleteServerlessSessionImpl:
    """Tests for _delete_serverless_session_impl()."""

    @pytest.mark.asyncio
    async def test_deletes_session_successfully(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _delete_serverless_session_impl("sess_abc123")
            assert "✅" in result
            assert "sess_abc123" in result

    @pytest.mark.asyncio
    async def test_handles_manager_unavailable(self) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(side_effect=RuntimeError("Serverless mode not available")),
        ):
            result = await _delete_serverless_session_impl("sess_abc123")
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_handles_nonexistent_session(self, mock_manager) -> None:
        mock_manager.delete_session = AsyncMock(return_value=False)
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _delete_serverless_session_impl("nonexistent")
            assert "❌" in result
            assert "not found" in result.lower()


# ============================================================================
# _list_serverless_sessions_operation Tests
# ============================================================================


class TestListServerlessSessionsOperation:
    """Tests for _list_serverless_sessions_operation()."""

    @pytest.mark.asyncio
    async def test_lists_sessions(self, mock_manager) -> None:
        result = await _list_serverless_sessions_operation(
            mock_manager,
            user_id=None,
            project_id=None,
            include_expired=False,
        )
        assert "📦" in result
        assert "2" in result
        assert "sess_abc123" in result
        assert "sess_def456" in result

    @pytest.mark.asyncio
    async def test_empty_list(self, mock_manager) -> None:
        mock_manager.list_sessions = AsyncMock(return_value=[])
        result = await _list_serverless_sessions_operation(
            mock_manager,
            user_id=None,
            project_id=None,
            include_expired=False,
        )
        assert "No sessions found" in result

    @pytest.mark.asyncio
    async def test_lists_with_user_filter(self, mock_manager) -> None:
        await _list_serverless_sessions_operation(
            mock_manager,
            user_id="user_1",
            project_id=None,
            include_expired=False,
        )
        mock_manager.list_sessions.assert_awaited_once_with(
            user_id="user_1",
            project_id=None,
            include_expired=False,
        )


# ============================================================================
# _list_serverless_sessions_impl Tests
# ============================================================================


class TestListServerlessSessionsImpl:
    """Tests for _list_serverless_sessions_impl()."""

    @pytest.mark.asyncio
    async def test_lists_all_sessions(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _list_serverless_sessions_impl()
            assert "sess_abc123" in result

    @pytest.mark.asyncio
    async def test_filters_by_user(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _list_serverless_sessions_impl(user_id="user_1")
            assert "sess_abc123" in result

    @pytest.mark.asyncio
    async def test_handles_manager_unavailable(self) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(side_effect=RuntimeError("Serverless mode not available")),
        ):
            result = await _list_serverless_sessions_impl()
            assert "❌" in result


# ============================================================================
# _cleanup_serverless_sessions_operation Tests
# ============================================================================


class TestCleanupServerlessSessionsOperation:
    """Tests for _cleanup_serverless_sessions_operation()."""

    @pytest.mark.asyncio
    async def test_cleans_up_expired_sessions(self, mock_manager) -> None:
        result = await _cleanup_serverless_sessions_operation(mock_manager)
        assert "✅" in result
        assert "3" in result
        mock_manager.cleanup_expired_sessions.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleans_up_zero_sessions(self, mock_manager) -> None:
        mock_manager.cleanup_expired_sessions = AsyncMock(return_value=0)
        result = await _cleanup_serverless_sessions_operation(mock_manager)
        assert "0" in result


# ============================================================================
# _cleanup_serverless_sessions_impl Tests
# ============================================================================


class TestCleanupServerlessSessionsImpl:
    """Tests for _cleanup_serverless_sessions_impl()."""

    @pytest.mark.asyncio
    async def test_cleans_up_successfully(self, mock_manager) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await _cleanup_serverless_sessions_impl()
            assert "✅" in result
            assert "3" in result

    @pytest.mark.asyncio
    async def test_handles_manager_unavailable(self) -> None:
        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(side_effect=RuntimeError("Serverless mode not available")),
        ):
            result = await _cleanup_serverless_sessions_impl()
            assert "❌" in result


# ============================================================================
# _format_storage_test_results Tests
# ============================================================================


class TestFormatStorageTestResults:
    """Tests for _format_storage_test_results()."""

    def test_formats_available_backend(self) -> None:
        results = {
            "redis": {"available": True, "latency_ms": 1.5, "status": "OK"},
        }
        lines = _format_storage_test_results(results)
        # lines[0] = header, lines[1] = "", lines[2] = "✅ REDIS:"
        assert "✅" in lines[2]
        assert "REDIS" in lines[2]
        assert "1.5" in lines[3]  # latency line

    def test_formats_unavailable_backend(self) -> None:
        results = {
            "s3": {"available": False, "error": "Connection refused"},
        }
        lines = _format_storage_test_results(results)
        # lines[0] = header, lines[1] = "", lines[2] = "❌ S3:"
        assert "❌" in lines[2]
        assert "S3" in lines[2]
        assert "Connection refused" in lines[3]


# ============================================================================
# register_serverless_tools Tests
# ============================================================================


class TestRegisterServerlessTools:
    """Tests for register_serverless_tools()."""

    def _make_mock_server(self):
        """Create a mock FastMCP server and collect registered tools."""
        tools = {}

        class MockServer:
            def tool(self):
                def decorator(fn):
                    tools[fn.__name__] = fn
                    return fn
                return decorator

        return MockServer(), tools

    def test_registers_all_tools(self) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]
        expected = [
            "create_serverless_session",
            "get_serverless_session",
            "update_serverless_session",
            "delete_serverless_session",
            "list_serverless_sessions",
            "cleanup_serverless_sessions",
            "test_serverless_storage",
            "configure_serverless_storage",
        ]
        for name in expected:
            assert name in tools, f"Missing tool: {name}"

    @pytest.mark.asyncio
    async def test_create_serverless_session_tool(self, mock_manager) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await tools["create_serverless_session"](
                user_id="user_1",
                project_id="proj_1",
                session_data={"test": True},
                ttl_hours=48,
            )
            assert "✅" in result
            assert "sess_abc123" in result
            assert "48" in result

    @pytest.mark.asyncio
    async def test_delete_serverless_session_tool(self, mock_manager) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await tools["delete_serverless_session"](
                session_id="sess_abc123",
            )
            assert "✅" in result
            assert "sess_abc123" in result

    @pytest.mark.asyncio
    async def test_get_serverless_session_tool(self, mock_manager) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await tools["get_serverless_session"](
                session_id="sess_abc123",
            )
            assert "sess_abc123" in result
            assert "user_1" in result

    @pytest.mark.asyncio
    async def test_list_serverless_sessions_tool(self, mock_manager) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await tools["list_serverless_sessions"](
                user_id="user_1",
            )
            assert "📦" in result
            assert "sess_abc123" in result

    @pytest.mark.asyncio
    async def test_cleanup_serverless_sessions_tool(self, mock_manager) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await tools["cleanup_serverless_sessions"]()
            assert "✅" in result
            assert "3" in result

    @pytest.mark.asyncio
    async def test_tool_returns_error_when_manager_unavailable(self) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(side_effect=RuntimeError("Serverless mode not available")),
        ):
            result = await tools["create_serverless_session"](
                user_id="user_1",
                project_id="proj_1",
            )
            assert "❌" in result
            assert "Serverless mode not available" in result

    @pytest.mark.asyncio
    async def test_update_serverless_session_tool(self, mock_manager) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await tools["update_serverless_session"](
                session_id="sess_abc123",
                session_data={"updated": True},
                extend_ttl_hours=24,
            )
            assert "✅" in result
            assert "sess_abc123" in result
            assert "24" in result

    @pytest.mark.asyncio
    async def test_test_serverless_storage_tool(self, mock_manager) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await tools["test_serverless_storage"]()
            assert "🧪" in result
            assert "redis" in result.lower()
            assert "s3" in result.lower()

    @pytest.mark.asyncio
    async def test_configure_serverless_storage_tool(self, mock_manager) -> None:
        server, tools = self._make_mock_server()
        register_serverless_tools(server)  # type: ignore[arg-type]

        with patch(
            "session_buddy.mcp.tools.infrastructure.serverless_tools._require_serverless_manager",
            new=AsyncMock(return_value=mock_manager),
        ):
            result = await tools["configure_serverless_storage"](
                backend="redis",
                config={"host": "localhost", "port": 6379},
            )
            assert "✅" in result
            assert "REDIS" in result
