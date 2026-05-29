"""Unit tests for session_buddy.core.conversation_storage."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from session_buddy.core.conversation_storage import (
    capture_conversation_context,
    get_conversation_logger,
)


class TestGetConversationLogger:
    """Tests for get_conversation_logger function."""

    def test_returns_logger_instance(self) -> None:
        """Test get_conversation_logger returns a Logger."""
        logger = get_conversation_logger()

        assert logger is not None
        assert logger.name == "session_buddy.core.conversation_storage"


class TestCaptureConversationContext:
    """Tests for capture_conversation_context function."""

    @pytest.fixture
    def mock_manager(self) -> MagicMock:
        """Create a mock SessionLifecycleManager."""
        manager = MagicMock()
        manager.current_project = "test-project"
        manager._quality_history = {"test-project": [70, 75, 80]}
        manager.session_context = {
            "active_files": ["/path/to/file1.py", "/path/to/file2.py"],
            "language": "python",
        }
        return manager

    @pytest.mark.asyncio
    async def test_includes_project_name(self, mock_manager: MagicMock) -> None:
        """Test capture includes project name in header."""
        result = await capture_conversation_context(mock_manager)

        assert "test-project" in result
        assert "# Conversation Context" in result

    @pytest.mark.asyncio
    async def test_includes_timestamp(self, mock_manager: MagicMock) -> None:
        """Test capture includes timestamp."""
        result = await capture_conversation_context(mock_manager)

        assert "Timestamp:" in result

    @pytest.mark.asyncio
    async def test_includes_quality_score_when_provided(self, mock_manager: MagicMock) -> None:
        """Test capture includes quality score when provided."""
        result = await capture_conversation_context(mock_manager, quality_score=85)

        assert "Quality Score: 85/100" in result

    @pytest.mark.asyncio
    async def test_excludes_quality_score_when_none(self, mock_manager: MagicMock) -> None:
        """Test capture omits quality score when not provided."""
        result = await capture_conversation_context(mock_manager, quality_score=None)

        assert "Quality Score:" not in result

    @pytest.mark.asyncio
    async def test_includes_quality_history_for_project(self, mock_manager: MagicMock) -> None:
        """Test capture includes quality history section."""
        result = await capture_conversation_context(mock_manager)

        assert "Quality History" in result
        assert "70, 75, 80" in result  # Recent scores in chronological order

    @pytest.mark.asyncio
    async def test_includes_session_context(self, mock_manager: MagicMock) -> None:
        """Test capture includes session context section."""
        result = await capture_conversation_context(mock_manager)

        assert "Session Context" in result
        assert "language: python" in result

    @pytest.mark.asyncio
    async def test_includes_custom_metadata(self, mock_manager: MagicMock) -> None:
        """Test capture includes custom metadata."""
        result = await capture_conversation_context(
            mock_manager,
            metadata={"custom_key": "custom_value", "another": 123},
        )

        assert "Metadata" in result
        assert "custom_key: custom_value" in result

    @pytest.mark.asyncio
    async def test_handles_no_current_project(self, mock_manager: MagicMock) -> None:
        """Test capture handles missing project gracefully."""
        mock_manager.current_project = None

        result = await capture_conversation_context(mock_manager)

        assert "Unknown" in result

    @pytest.mark.asyncio
    async def test_handles_empty_quality_history(self, mock_manager: MagicMock) -> None:
        """Test capture handles no quality history."""
        mock_manager._quality_history = {}

        result = await capture_conversation_context(mock_manager)

        assert "Quality History" not in result

    @pytest.mark.asyncio
    async def test_formats_lists_as_count(self, mock_manager: MagicMock) -> None:
        """Test capture formats lists by count."""
        result = await capture_conversation_context(mock_manager)

        assert "2 items" in result  # active_files has 2 items

    @pytest.mark.asyncio
    async def test_quality_trend_improving(self, mock_manager: MagicMock) -> None:
        """Test capture shows improving trend when latest score higher."""
        result = await capture_conversation_context(mock_manager)

        assert "Trend: improving" in result

    @pytest.mark.asyncio
    async def test_quality_trend_stable(self, mock_manager: MagicMock) -> None:
        """Test capture shows stable trend when scores same."""
        mock_manager._quality_history = {"test-project": [80, 80, 80]}

        result = await capture_conversation_context(mock_manager)

        assert "Trend: stable" in result

    @pytest.mark.asyncio
    async def test_quality_trend_declining(self, mock_manager: MagicMock) -> None:
        """Test capture shows stable when latest score lower (not declining label)."""
        mock_manager._quality_history = {"test-project": [90, 85, 80]}

        result = await capture_conversation_context(mock_manager)

        # The code checks if scores[-1] > scores[0] for improving, else stable
        assert "Trend: stable" in result

    @pytest.mark.asyncio
    async def test_formats_dicts_as_key_count(self, mock_manager: MagicMock) -> None:
        """Test capture formats dicts by key count."""
        mock_manager.session_context = {"metadata": {"key1": "v1", "key2": "v2", "key3": "v3"}}

        result = await capture_conversation_context(mock_manager)

        assert "3 keys" in result
