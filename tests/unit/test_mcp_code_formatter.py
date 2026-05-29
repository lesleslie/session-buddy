"""Unit tests for code_formatter module.

Tests:
- MCPCodeFormatter class
- CodeFormatter interface compliance
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestMCPCodeFormatter:
    """Tests for MCPCodeFormatter class."""

    @pytest.mark.asyncio
    async def test_format_file_returns_false(self) -> None:
        """Test that format_file returns False (placeholder implementation)."""
        from session_buddy.mcp.code_formatter import MCPCodeFormatter

        formatter = MCPCodeFormatter()

        # The current implementation returns False
        result = await formatter.format_file(Path("test.py"), timeout=30)

        assert result is False

    @pytest.mark.asyncio
    async def test_format_file_with_different_timeout(self) -> None:
        """Test format_file accepts different timeout values."""
        from session_buddy.mcp.code_formatter import MCPCodeFormatter

        formatter = MCPCodeFormatter()

        # Different timeout values should all return False
        result = await formatter.format_file(Path("test.py"), timeout=60)
        assert result is False

        result = await formatter.format_file(Path("test.py"), timeout=5)
        assert result is False

    @pytest.mark.asyncio
    async def test_format_file_with_various_paths(self) -> None:
        """Test format_file works with various path types."""
        from session_buddy.mcp.code_formatter import MCPCodeFormatter

        formatter = MCPCodeFormatter()

        # Test with different path patterns
        paths = [
            Path("test.py"),
            Path("src/module/file.py"),
            Path("/absolute/path/to/file.py"),
        ]

        for path in paths:
            result = await formatter.format_file(path, timeout=30)
            assert result is False


class TestCodeFormatterInterface:
    """Tests for CodeFormatter interface compliance."""

    def test_mcp_code_formatter_inherits_from_code_formatter(self) -> None:
        """Test that MCPCodeFormatter properly inherits from CodeFormatter."""
        from session_buddy.core.hooks import CodeFormatter
        from session_buddy.mcp.code_formatter import MCPCodeFormatter

        assert issubclass(MCPCodeFormatter, CodeFormatter)

    def test_format_file_method_exists(self) -> None:
        """Test that format_file method exists and is callable."""
        from session_buddy.mcp.code_formatter import MCPCodeFormatter

        formatter = MCPCodeFormatter()

        assert hasattr(formatter, "format_file")
        assert callable(formatter.format_file)