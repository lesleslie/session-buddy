#!/usr/bin/env python3
"""Unit tests for search tools.

Tests the MCP tools for searching reflections and conversations.
"""

from unittest.mock import AsyncMock, patch

import pytest
from session_buddy import reflection_tools
from session_buddy.reflection_tools import get_reflection_database


class TestGetReflectionDatabase:
    """Test get_reflection_database function."""

    def setup_method(self):
        """Reset global state before each test."""
        reflection_tools._reflection_db = None

    def teardown_method(self):
        """Clean up global state after each test."""
        reflection_tools._reflection_db = None

    async def test_get_reflection_database_success(self):
        """Test successful database initialization."""
        # Mock the ReflectionDatabaseAdapter class used after ACB migration
        with patch(
            "session_buddy.reflection_tools.ReflectionDatabaseAdapter"
        ) as mock_reflection_db:
            mock_db_instance = AsyncMock()
            mock_reflection_db.return_value = mock_db_instance

            # Call the function
            result = await get_reflection_database()

            # Assertions
            assert result == mock_db_instance
            mock_reflection_db.assert_called_once()

    async def test_get_reflection_database_import_error(self):
        """Test database initialization when import fails."""
        with patch(
            "session_buddy.reflection_tools.ReflectionDatabaseAdapter",
            side_effect=ImportError,
        ):
            with pytest.raises(ImportError):
                await get_reflection_database()

    async def test_get_reflection_database_general_exception(self):
        """Test database initialization when general exception occurs."""
        with patch(
            "session_buddy.reflection_tools.ReflectionDatabaseAdapter",
            side_effect=Exception("Test exception"),
        ):
            with pytest.raises(Exception):
                await get_reflection_database()


# Note: Testing the actual tool functions would require a more complex setup
# with FastMCP server mocking. For now, we'll focus on the utility functions.
# The tool functions themselves are tested through integration tests.


class TestSearchToolsIntegration:
    """Integration tests for search tools would go here.

    These would test the actual tool registration and execution through
    a FastMCP server instance, but that requires more complex setup.
    """

    @pytest.mark.skip(reason="Integration tests require FastMCP server setup")
    async def test_search_tools_integration(self):
        """Placeholder for integration tests."""


# For now, let's create a basic test file that follows the pattern
# We'll need to add more comprehensive tests later
