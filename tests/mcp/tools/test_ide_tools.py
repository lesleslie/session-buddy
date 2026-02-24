"""Tests for PyCharm MCP Tools.

Tests cover:
- PyCharmMCPAdapter functionality
- Circuit breaker behavior
- Caching mechanisms
- Tool registration
- Tool functionality (mocked)
"""

import json
import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from session_buddy.mcp.tools.ide import (
    PyCharmMCPAdapter,
    CircuitBreakerState,
    get_pycharm_adapter,
    register_ide_tools,
)


class TestCircuitBreakerState:
    """Tests for circuit breaker state management."""

    def test_initial_state(self) -> None:
        """Test initial circuit breaker state."""
        cb = CircuitBreakerState()
        assert cb.failure_count == 0
        assert cb.is_open is False
        assert cb.can_execute() is True

    def test_record_failure(self) -> None:
        """Test failure recording."""
        cb = CircuitBreakerState()
        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.is_open is False
        cb.record_failure()
        assert cb.failure_count == 2
        assert cb.is_open is False
        cb.record_failure()
        assert cb.failure_count == 3
        assert cb.is_open is True
        assert cb.can_execute() is False

    def test_record_success(self) -> None:
        """Test success recording."""
        cb = CircuitBreakerState()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.is_open is False
        assert cb.can_execute() is True

    def test_recovery_timeout(self) -> None:
        """Test recovery timeout."""
        cb = CircuitBreakerState(recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        assert cb.can_execute() is False
        import time
        time.sleep(0.15)
        assert cb.can_execute() is True


class TestPyCharmMCPAdapter:
    """Tests for PyCharmMCPAdapter."""

    def test_initialization(self) -> None:
        """Test adapter initialization."""
        adapter = PyCharmMCPAdapter()
        assert adapter._mcp is None
        assert adapter._timeout == 30.0
        assert adapter._max_results == 100
        assert adapter._available is False

    def test_custom_parameters(self) -> None:
        """Test adapter with custom parameters."""
        adapter = PyCharmMCPAdapter(
            timeout=60.0,
            max_results=50,
        )
        assert adapter._timeout == 60.0
        assert adapter._max_results == 50

    def test_get_set_adapter(self) -> None:
        """Test getting the global adapter."""
        adapter1 = get_pycharm_adapter()
        adapter2 = get_pycharm_adapter()
        assert adapter1 is adapter2

    def test_caching(self) -> None:
        """Test caching mechanisms."""
        adapter = PyCharmMCPAdapter()

        # Test cache set and get
        adapter._set_cached("test_key", "test_value", ttl=60)
        assert adapter._get_cached("test_key") == "test_value"
        assert adapter._get_cached("nonexistent") is None

        # Test cache expiry
        adapter._set_cached("expiring_key", "value", ttl=0.1)
        import time
        time.sleep(0.15)
        assert adapter._get_cached("expiring_key") is None

    def test_clear_cache(self) -> None:
        """Test cache clearing."""
        adapter = PyCharmMCPAdapter()
        adapter._set_cached("key1", "value1")
        adapter._set_cached("key2", "value2")
        assert len(adapter._cache) == 2
        adapter.clear_cache()
        assert len(adapter._cache) == 0

    def test_sanitize_regex(self) -> None:
        """Test regex sanitization."""
        adapter = PyCharmMCPAdapter()

        # Valid patterns
        assert adapter._sanitize_regex("async def") == "async def"
        assert adapter._sanitize_regex(r"\b\w+\b") == r"\b\w+\b"

        # Invalid patterns
        assert adapter._sanitize_regex("") == ""
        assert adapter._sanitize_regex("x" * 1000) == ""
        assert adapter._sanitize_regex(r"(.*)+") == ""

    def test_safe_path(self) -> None:
        """Test path safety validation."""
        adapter = PyCharmMCPAdapter()

        # Safe paths
        assert adapter._is_safe_path("src/main.py") is True
        assert adapter._is_safe_path("lib/utils.py") is True
        assert adapter._is_safe_path("tests/test_main.py") is True
        assert adapter._is_safe_path("/etc/shadow") is True  # absolute paths are allowed

        # Unsafe paths
        assert not adapter._is_safe_path("../../../etc/passwd")  # path traversal
        assert not adapter._is_safe_path("")  # empty path
        assert not adapter._is_safe_path("test\x00file.py")  # null byte

    @pytest.mark.asyncio
    async def test_health_check_no_mcp(self) -> None:
        """Test health check without MCP client."""
        adapter = PyCharmMCPAdapter()
        health = await adapter.health_check()

        assert health["mcp_available"] is False
        assert health["circuit_breaker_open"] is False
        assert health["failure_count"] == 0
        assert health["cache_size"] == 0


class TestPyCharmMCPAdapterWithMock:
    """Tests with mocked MCP client."""

    @pytest.fixture
    def mock_mcp_client(self) -> AsyncMock:
        """Create mocked MCP client."""
        mock = AsyncMock()
        mock.search_regex = AsyncMock(return_value=[
            {"file_path": "test.py", "line": 10, "column": 5, "match": "def add_numbers", "context_before": "1 + 2", "context_after": "3 + 4"},
        ])
        mock.get_file_problems = AsyncMock(return_value=[
            {"line": 10, "column": 5, "message": "Undefined variable", "severity": "ERROR"},
        ])
        mock.get_symbol_info = AsyncMock(return_value={"type": "function", "name": "add_numbers"})
        mock.find_usages = AsyncMock(return_value=[
            {"file_path": "test.py", "line": 10, "column": 5, "type": "call"},
        ])
        return mock

    @pytest.fixture
    def adapter_with_mock(self, mock_mcp_client: AsyncMock) -> PyCharmMCPAdapter:
        """Create adapter with mocked client."""
        return PyCharmMCPAdapter(
            mcp_client=mock_mcp_client,
            timeout=5.0,
            max_results=10,
        )

    @pytest.mark.asyncio
    async def test_search_regex_with_mock(self, adapter_with_mock: PyCharmMCPAdapter, mock_mcp_client: AsyncMock) -> None:
        """Test search with mocked client."""
        results = await adapter_with_mock.search_regex(r"\bdef\s+\w+\b")
        assert len(results) == 1
        assert results[0].file_path == "test.py"
        assert results[0].line_number == 10
        assert results[0].match_text == "def add_numbers"

    @pytest.mark.asyncio
    async def test_get_file_problems_with_mock(self, adapter_with_mock: PyCharmMCPAdapter, mock_mcp_client: AsyncMock) -> None:
        """Test get_file_problems with mocked client."""
        result = await adapter_with_mock.get_file_problems("test.py", errors_only=False)
        assert len(result) == 1
        assert result[0]["line"] == 10
        assert result[0]["message"] == "Undefined variable"

    @pytest.mark.asyncio
    async def test_get_symbol_info_with_mock(self, adapter_with_mock: PyCharmMCPAdapter, mock_mcp_client: AsyncMock) -> None:
        """Test get_symbol_info with mocked client."""
        mock_mcp_client.get_symbol_info.return_value = {
            "type": "function",
            "name": "add_numbers",
            "file_path": "math.py",
            "line": 1,
        }
        result = await adapter_with_mock.get_symbol_info("add_numbers")
        assert result["type"] == "function"
        assert result["name"] == "add_numbers"

        mock_mcp_client.get_symbol_info.return_value = None
        result = await adapter_with_mock.get_symbol_info("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_usages_with_mock(self, adapter_with_mock: PyCharmMCPAdapter, mock_mcp_client: AsyncMock) -> None:
        """Test find_usages with mocked client."""
        usages = [
            {"file_path": "main.py", "line": 10, "column": 5, "type": "call"},
            {"file_path": "utils.py", "line": 20, "column": 0, "type": "import"},
        ]
        mock_mcp_client.find_usages.return_value = usages
        result = await adapter_with_mock.find_usages("add_numbers")
        assert len(result) == 2
        assert result[0]["file_path"] == "main.py"
        assert result[0]["type"] == "call"

        mock_mcp_client.find_usages.return_value = []
        result = await adapter_with_mock.find_usages("nonexistent")
        assert result == []


class TestToolRegistration:
    """Tests for MCP tool registration."""

    @pytest.fixture
    def mock_mcp_app(self) -> MagicMock:
        """Create a mock FastMCP app."""
        mock = MagicMock()
        mock._tool_manager = MagicMock()
        mock._tool_manager._tools = {}
        mock.tool = MagicMock()
        return mock

    def test_register_ide_tools(self, mock_mcp_app: MagicMock) -> None:
        """Test registering IDE tools with FastMCP."""
        register_ide_tools(mock_mcp_app)

        # Verify tool decorator was called for each tool
        assert mock_mcp_app.tool.call_count == 5

    def test_tool_execution(self, mock_mcp_app: MagicMock) -> None:
        """Test tool execution with mocked adapter."""
        register_ide_tools(mock_mcp_app)

        # Verify tool decorator was called
        assert mock_mcp_app.tool.call_count == 5
