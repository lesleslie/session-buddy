"""Tests for intent_tools_registration module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.advanced import intent_tools_registration as module


class TestInitializeIntentDetector:
    """Tests for initialize_intent_detector function."""

    @pytest.mark.asyncio
    async def test_initialize_intent_detector_success(self):
        """Test successful initialization of intent detector."""
        mock_detector = MagicMock()
        mock_detector.initialize = AsyncMock()

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            await module.initialize_intent_detector()

            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_intent_detector_already_initialized(self):
        """Test initialization when detector already exists."""
        mock_detector = MagicMock()

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            await module.initialize_intent_detector()

            mock_get.assert_called_once()


class TestDetectIntentImpl:
    """Tests for _detect_intent_impl function."""

    @pytest.mark.asyncio
    async def test_detect_intent_impl_with_match(self):
        """Test intent detection when a match is found."""
        mock_match = MagicMock()
        mock_match.tool_name = "search_reflections"
        mock_match.confidence = 0.85
        mock_match.extracted_args = {"query": "test"}
        mock_match.disambiguation_needed = False
        mock_match.alternatives = []

        mock_detector = MagicMock()
        mock_detector.detect_intent = AsyncMock(return_value=mock_match)

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            result = await module._detect_intent_impl("search for test", 0.7)

            assert result["detected"] is True
            assert result["tool_name"] == "search_reflections"
            assert result["confidence"] == 0.85
            assert result["extracted_args"] == {"query": "test"}
            mock_detector.detect_intent.assert_called_once_with("search for test", 0.7)

    @pytest.mark.asyncio
    async def test_detect_intent_impl_no_match_with_suggestions(self):
        """Test intent detection when no match but suggestions available."""
        mock_detector = MagicMock()
        mock_detector.detect_intent = AsyncMock(return_value=None)
        mock_detector.get_suggestions = AsyncMock(return_value=[
            {"tool": "search", "confidence": 0.6},
            {"tool": "find", "confidence": 0.4},
        ])

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            result = await module._detect_intent_impl("random text", 0.7)

            assert result["detected"] is False
            assert "suggestions" in result
            assert len(result["suggestions"]) == 2

    @pytest.mark.asyncio
    async def test_detect_intent_impl_no_match_no_suggestions(self):
        """Test intent detection when no match and no suggestions."""
        mock_detector = MagicMock()
        mock_detector.detect_intent = AsyncMock(return_value=None)
        mock_detector.get_suggestions = AsyncMock(return_value=[])

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            result = await module._detect_intent_impl("xyz123", 0.7)

            assert result["detected"] is False
            assert "suggestions" not in result or result.get("suggestions") == []


class TestFormatDetectedIntent:
    """Tests for _format_detected_intent function."""

    def test_format_detected_intent_basic(self):
        """Test formatting detected intent with basic properties."""
        mock_match = MagicMock()
        mock_match.tool_name = "checkpoint"
        mock_match.confidence = 0.92
        mock_match.extracted_args = {}
        mock_match.disambiguation_needed = False
        mock_match.alternatives = []

        result = module._format_detected_intent(mock_match)

        assert result["detected"] is True
        assert result["tool_name"] == "checkpoint"
        assert result["confidence"] == 0.92
        assert "I detected you want to use 'checkpoint'" in result["message"]

    def test_format_detected_intent_with_disambiguation(self):
        """Test formatting detected intent needing disambiguation."""
        mock_match = MagicMock()
        mock_match.tool_name = "quality_monitor"
        mock_match.confidence = 0.75
        mock_match.extracted_args = {}
        mock_match.disambiguation_needed = True
        mock_match.alternatives = ["quality_check", "health_check"]

        result = module._format_detected_intent(mock_match)

        assert result["detected"] is True
        assert result["disambiguation_needed"] is True
        assert result["alternatives"] == ["quality_check", "health_check"]


class TestFormatIntentError:
    """Tests for _format_intent_error function."""

    def test_format_intent_error_basic(self):
        """Test formatting intent error."""
        result = module._format_intent_error("Detection failed")

        assert result["detected"] is False
        assert result["error"] == "Detection failed"
        assert "encountered an error" in result["message"]


class TestGetIntentSuggestionsImpl:
    """Tests for _get_intent_suggestions_impl function."""

    @pytest.mark.asyncio
    async def test_get_intent_suggestions_impl_with_results(self):
        """Test getting suggestions when results are found."""
        mock_detector = MagicMock()
        mock_detector.get_suggestions = AsyncMock(return_value=[
            {"tool": "search", "confidence": 0.8, "match_type": "pattern"},
            {"tool": "find", "confidence": 0.6, "match_type": "semantic"},
            {"tool": "query", "confidence": 0.5, "match_type": "pattern"},
        ])

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            result = await module._get_intent_suggestions_impl("find something", 5)

            assert result["count"] == 3
            assert len(result["suggestions"]) == 3
            assert "Found 3 possible tool matches" in result["message"]

    @pytest.mark.asyncio
    async def test_get_intent_suggestions_impl_no_results(self):
        """Test getting suggestions when no results found."""
        mock_detector = MagicMock()
        mock_detector.get_suggestions = AsyncMock(return_value=[])

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            result = await module._get_intent_suggestions_impl("xyz unknown", 5)

            assert result["count"] == 0
            assert result["suggestions"] == []
            assert "No matching tools found" in result["message"]


class TestFormatSuggestionsError:
    """Tests for _format_suggestions_error function."""

    def test_format_suggestions_error_basic(self):
        """Test formatting suggestions error."""
        result = module._format_suggestions_error("Suggestions failed")

        assert result["suggestions"] == []
        assert result["error"] == "Suggestions failed"
        assert result["count"] == 0


class TestListSupportedIntentsImpl:
    """Tests for _list_supported_intents_impl function."""

    @pytest.mark.asyncio
    async def test_list_supported_intents_impl_with_tools(self):
        """Test listing supported intents when tools are available."""
        mock_detector = MagicMock()
        mock_detector.patterns = {
            "checkpoint": ["save progress", "checkpoint"],
            "search": ["search for", "find"],
        }
        mock_detector.semantic_examples = {
            "checkpoint": ["I've made progress"],
            "search": ["looking for something"],
        }
        mock_detector.argument_extraction = ["checkpoint"]

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            result = await module._list_supported_intents_impl()

            assert result["total_tools"] == 2
            assert "checkpoint" in result["tools"]
            assert "search" in result["tools"]
            assert result["tools"]["checkpoint"]["has_argument_extraction"] is True
            assert result["tools"]["search"]["has_argument_extraction"] is False

    @pytest.mark.asyncio
    async def test_list_supported_intents_impl_empty(self):
        """Test listing supported intents when no tools registered."""
        mock_detector = MagicMock()
        mock_detector.patterns = {}
        mock_detector.semantic_examples = {}
        mock_detector.argument_extraction = []

        with patch.object(module, 'get_intent_detector', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_detector

            result = await module._list_supported_intents_impl()

            assert result["total_tools"] == 0
            assert result["tools"] == {}


class TestFormatListIntentsError:
    """Tests for _format_list_intents_error function."""

    def test_format_list_intents_error_basic(self):
        """Test formatting list intents error."""
        result = module._format_list_intents_error("List failed")

        assert result["tools"] == {}
        assert result["total_tools"] == 0
        assert result["error"] == "List failed"
        assert "Failed to list supported intents" in result["message"]


class TestBuildToolsInfo:
    """Tests for _build_tools_info function."""

    def test_build_tools_info_basic(self):
        """Test building tools info dictionary."""
        mock_detector = MagicMock()
        mock_detector.patterns = {
            "test_tool": ["test pattern"],
        }
        mock_detector.semantic_examples = {
            "test_tool": ["example usage"],
        }
        mock_detector.argument_extraction = ["test_tool"]

        result = module._build_tools_info(mock_detector)

        assert "test_tool" in result
        assert result["test_tool"]["patterns"] == ["test pattern"]
        assert result["test_tool"]["semantic_examples"] == ["example usage"]
        assert result["test_tool"]["has_argument_extraction"] is True

    def test_build_tools_info_multiple_tools(self):
        """Test building tools info with multiple tools."""
        mock_detector = MagicMock()
        mock_detector.patterns = {
            "tool_a": ["pattern a"],
            "tool_b": ["pattern b"],
            "tool_c": ["pattern c"],
        }
        mock_detector.semantic_examples = {
            "tool_a": [],
            "tool_b": ["example"],
            "tool_c": [],
        }
        mock_detector.argument_extraction = ["tool_a", "tool_c"]

        result = module._build_tools_info(mock_detector)

        assert len(result) == 3
        assert result["tool_a"]["has_argument_extraction"] is True
        assert result["tool_b"]["has_argument_extraction"] is False
        assert result["tool_c"]["has_argument_extraction"] is True


class TestRegisterIntentDetectionTools:
    """Tests for register_intent_detection_tools function."""

    def test_register_intent_detection_tools(self):
        """Test registering intent detection tools on server."""
        mock_server = MagicMock()
        mock_tool_decorator = mock_server.tool.return_value

        module.register_intent_detection_tools(mock_server)

        assert mock_server.tool.call_count == 3

    def test_register_intent_detection_tools_decorator_returns_callable(self):
        """Test that decorator returns a callable for each tool."""
        mock_server = MagicMock()
        mock_tool_decorator = mock_server.tool.return_value
        mock_tool_decorator.side_effect = lambda f: f

        module.register_intent_detection_tools(mock_server)

        assert mock_server.tool.call_count == 3

    def test_register_intent_detection_tools_calls_tool_three_times(self):
        """Test that exactly three tools are registered."""
        mock_server = MagicMock()

        module.register_intent_detection_tools(mock_server)

        assert mock_server.tool.call_count == 3
        calls = mock_server.tool.call_args_list
        assert len(calls) == 3
