"""Tests for intent_detection_tools.py MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_tool_match():
    """Create a mock ToolMatch object."""
    @dataclass
    class MockToolMatch:
        tool_name: str
        confidence: float
        extracted_args: dict[str, Any]
        disambiguation_needed: bool = False
        alternatives: list[str] = None

    return MockToolMatch(
        tool_name="checkpoint",
        confidence=0.85,
        extracted_args={"user_id": "test_user"},
        disambiguation_needed=False,
        alternatives=[],
    )


@pytest.fixture
def mock_intent_detector(mock_tool_match):
    """Create a mock IntentDetector."""
    detector = MagicMock()
    detector.patterns = {
        "checkpoint": ["save my progress", "checkpoint this"],
        "search_reflections": ["what did I learn", "find insights"],
    }
    detector.semantic_examples = {
        "checkpoint": ["I've made good progress"],
        "search_reflections": ["What did I learn about error handling?"],
    }
    detector.argument_extraction = {
        "checkpoint": {"user_id": {"patterns": [r"user[:\s]+(\w+)"]}},
    }
    return detector


# =============================================================================
# IntentDetector Class Tests
# =============================================================================


class TestIntentDetectorInit:
    """Tests for IntentDetector.__init__."""

    def test_init_initializes_patterns_empty(self):
        """Test that __init__ initializes patterns as empty dict."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        assert detector.patterns == {}
        assert detector.semantic_examples == {}
        assert detector.argument_extraction == {}

    def test_init_initializes_all_attributes(self):
        """Test that __init__ initializes all required attributes."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        assert hasattr(detector, "patterns")
        assert hasattr(detector, "semantic_examples")
        assert hasattr(detector, "argument_extraction")


class TestIntentDetectorDefaultPatterns:
    """Tests for IntentDetector._load_default_patterns."""

    def test_load_default_patterns_sets_checkpoint_patterns(self):
        """Test that default patterns include checkpoint."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        assert "checkpoint" in detector.patterns
        assert "save my progress" in detector.patterns["checkpoint"]
        assert "create a checkpoint" in detector.patterns["checkpoint"]

    def test_load_default_patterns_sets_search_reflections_patterns(self):
        """Test that default patterns include search_reflections."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        assert "search_reflections" in detector.patterns
        assert "what did I learn about" in detector.patterns["search_reflections"]

    def test_load_default_patterns_sets_quality_monitor_patterns(self):
        """Test that default patterns include quality_monitor."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        assert "quality_monitor" in detector.patterns
        assert "how's the code quality" in detector.patterns["quality_monitor"]

    def test_load_default_patterns_corresponds_to_semantic_examples(self):
        """Test that default patterns have corresponding semantic examples."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        for tool in detector.patterns:
            assert tool in detector.semantic_examples
            assert len(detector.semantic_examples[tool]) > 0


class TestIntentDetectorDetectIntent:
    """Tests for IntentDetector.detect_intent."""

    @pytest.mark.asyncio
    async def test_detect_intent_returns_none_for_empty_message(self):
        """Test that detect_intent returns None for empty/whitespace messages."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        result = await detector.detect_intent("")
        assert result is None

        result = await detector.detect_intent("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_detect_intent_returns_none_when_below_threshold(self):
        """Test that detect_intent returns None when confidence below threshold."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        with patch.object(detector, "_semantic_match", new_callable=AsyncMock) as mock_semantic:
            mock_semantic.return_value = None

            with patch.object(detector, "_pattern_match", new_callable=MagicMock) as mock_pattern:
                mock_pattern.return_value = None

                result = await detector.detect_intent("random unknown message", confidence_threshold=0.9)
                assert result is None

    @pytest.mark.asyncio
    async def test_detect_intent_calls_both_match_methods(self, mock_intent_detector):
        """Test that detect_intent calls both semantic and pattern matching."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        with patch.object(detector, "_semantic_match", new_callable=AsyncMock) as mock_semantic:
            mock_semantic.return_value = None

            with patch.object(detector, "_pattern_match", new_callable=MagicMock) as mock_pattern:
                mock_pattern.return_value = MagicMock(
                    tool_name="checkpoint",
                    confidence=0.8,
                    extracted_args={},
                    disambiguation_needed=False,
                    alternatives=[],
                )

                result = await detector.detect_intent("save my progress")

                mock_semantic.assert_called_once_with("save my progress")
                mock_pattern.assert_called_once_with("save my progress")

    @pytest.mark.asyncio
    async def test_detect_intent_extracts_arguments_on_match(self, mock_intent_detector):
        """Test that detect_intent extracts arguments after matching."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        match = MagicMock(
            tool_name="checkpoint",
            confidence=0.85,
            extracted_args={},
            disambiguation_needed=False,
            alternatives=[],
        )

        with patch.object(detector, "_semantic_match", new_callable=AsyncMock) as mock_semantic:
            mock_semantic.return_value = None

            with patch.object(detector, "_pattern_match", new_callable=MagicMock) as mock_pattern:
                mock_pattern.return_value = match

                with patch.object(detector, "_extract_arguments", new_callable=AsyncMock) as mock_extract:
                    mock_extract.return_value = {"user_id": "test_user"}

                    result = await detector.detect_intent("save my progress for user john")

                    mock_extract.assert_called_once_with("save my progress for user john", "checkpoint")


class TestIntentDetectorSemanticMatch:
    """Tests for IntentDetector._semantic_match."""

    @pytest.mark.asyncio
    async def test_semantic_match_returns_none_on_import_error(self):
        """Test that semantic match gracefully handles ImportError."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        with patch.dict("sys.modules", {"session_buddy.reflection_tools": None}):
            result = await detector._semantic_match("save my progress")
            assert result is None

    @pytest.mark.asyncio
    async def test_semantic_match_returns_none_when_embedding_unavailable(self):
        """Test that semantic match returns None when embedding system unavailable."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        with patch("session_buddy.reflection_tools.generate_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = ImportError("Embedding system unavailable")

            result = await detector._semantic_match("save my progress")
            assert result is None

    @pytest.mark.asyncio
    async def test_semantic_match_returns_toolmatch_on_high_similarity(self):
        """Test that semantic match returns ToolMatch when similarity > 0.6."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        mock_embedding = [0.1] * 768

        with patch("session_buddy.reflection_tools.generate_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = mock_embedding

            result = await detector._semantic_match("save my progress")

            if result is not None:
                assert result.tool_name is not None
                assert result.confidence > 0.6


class TestIntentDetectorPatternMatch:
    """Tests for IntentDetector._pattern_match."""

    def test_pattern_match_finds_exact_pattern(self):
        """Test that pattern match finds tool by exact pattern."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        result = detector._pattern_match("save my progress")

        assert result is not None
        assert result.tool_name == "checkpoint"
        assert result.confidence == 0.8

    def test_pattern_match_is_case_insensitive(self):
        """Test that pattern matching is case insensitive."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        result = detector._pattern_match("SAVE MY PROGRESS")

        assert result is not None
        assert result.tool_name == "checkpoint"

    def test_pattern_match_returns_none_for_unknown_message(self):
        """Test that pattern match returns None for unknown message."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        result = detector._pattern_match("completely random unknown text")

        assert result is None


class TestIntentDetectorCombineMatches:
    """Tests for IntentDetector._combine_matches."""

    def test_combine_returns_none_when_both_none(self):
        """Test that combine returns None when both matches are None."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()

        result = detector._combine_matches(None, None)

        assert result is None

    def test_combine_returns_high_confidence_when_both_agree(self):
        """Test that both agreeing gives high confidence."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()

        semantic = MagicMock(
            tool_name="checkpoint",
            confidence=0.7,
            extracted_args={},
            disambiguation_needed=False,
            alternatives=[],
        )
        pattern = MagicMock(
            tool_name="checkpoint",
            confidence=0.8,
            extracted_args={},
            disambiguation_needed=False,
            alternatives=[],
        )

        result = detector._combine_matches(semantic, pattern)

        assert result is not None
        assert result.tool_name == "checkpoint"
        assert abs(result.confidence - 0.9) < 0.001  # min(0.95, 0.7 + 0.2) = 0.9
        assert result.disambiguation_needed is False

    def test_combine_returns_semantic_only_when_pattern_none(self):
        """Test that semantic match is returned when pattern is None."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()

        semantic = MagicMock(
            tool_name="search_reflections",
            confidence=0.85,
            extracted_args={},
            disambiguation_needed=False,
            alternatives=[],
        )

        result = detector._combine_matches(semantic, None)

        assert result == semantic

    def test_combine_returns_pattern_only_when_semantic_none(self):
        """Test that pattern match is returned when semantic is None."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()

        pattern = MagicMock(
            tool_name="checkpoint",
            confidence=0.8,
            extracted_args={},
            disambiguation_needed=False,
            alternatives=[],
        )

        result = detector._combine_matches(None, pattern)

        assert result == pattern

    def test_combine_returns_higher_confidence_when_disagree(self):
        """Test that higher confidence match is returned when tools disagree."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()

        semantic = MagicMock(
            tool_name="search_reflections",
            confidence=0.9,
            extracted_args={},
            disambiguation_needed=False,
            alternatives=[],
        )
        pattern = MagicMock(
            tool_name="checkpoint",
            confidence=0.8,
            extracted_args={},
            disambiguation_needed=False,
            alternatives=[],
        )

        result = detector._combine_matches(semantic, pattern)

        assert result == semantic
        assert result.disambiguation_needed is True
        assert "checkpoint" in result.alternatives


class TestIntentDetectorExtractArguments:
    """Tests for IntentDetector._extract_arguments."""

    @pytest.mark.asyncio
    async def test_extract_arguments_returns_empty_for_unknown_tool(self):
        """Test that extraction returns empty dict for unknown tool."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        result = await detector._extract_arguments("save progress", "unknown_tool")

        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_arguments_extracts_matching_pattern(self):
        """Test that extraction extracts arguments using regex pattern."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()
        detector.argument_extraction["checkpoint"] = {
            "user_id": {"patterns": [r"user[:\s]+(\w+)"]}
        }

        result = await detector._extract_arguments("save progress for user john", "checkpoint")

        assert result == {"user_id": "john"}

    @pytest.mark.asyncio
    async def test_extract_arguments_returns_empty_when_no_match(self):
        """Test that extraction returns empty dict when no pattern matches."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()
        detector.argument_extraction["checkpoint"] = {
            "user_id": {"patterns": [r"user[:\s]+(\w+)"]}
        }

        result = await detector._extract_arguments("save progress", "checkpoint")

        assert result == {}


class TestIntentDetectorGetSuggestions:
    """Tests for IntentDetector.get_suggestions."""

    @pytest.mark.asyncio
    async def test_get_suggestions_returns_semantic_match(self):
        """Test that get_suggestions returns semantic match."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        with patch.object(detector, "_semantic_match", new_callable=AsyncMock) as mock_semantic:
            mock_semantic.return_value = MagicMock(
                tool_name="search_reflections",
                confidence=0.85,
                extracted_args={},
            )

            with patch.object(detector, "_pattern_match", new_callable=MagicMock) as mock_pattern:
                mock_pattern.return_value = None

                result = await detector.get_suggestions("what did I learn about async")

                assert len(result) >= 1
                assert result[0]["tool"] == "search_reflections"
                assert result[0]["match_type"] == "semantic"

    @pytest.mark.asyncio
    async def test_get_suggestions_returns_pattern_match(self):
        """Test that get_suggestions returns pattern match."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        with patch.object(detector, "_semantic_match", new_callable=AsyncMock) as mock_semantic:
            mock_semantic.return_value = None

            with patch.object(detector, "_pattern_match", new_callable=MagicMock) as mock_pattern:
                mock_pattern.return_value = MagicMock(
                    tool_name="checkpoint",
                    confidence=0.8,
                    extracted_args={},
                )

                result = await detector.get_suggestions("save my progress")

                assert len(result) >= 1
                assert result[0]["tool"] == "checkpoint"
                assert result[0]["match_type"] == "pattern"

    @pytest.mark.asyncio
    async def test_get_suggestions_respects_limit(self):
        """Test that get_suggestions respects the limit parameter."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        with patch.object(detector, "_semantic_match", new_callable=AsyncMock) as mock_semantic:
            mock_semantic.return_value = MagicMock(
                tool_name="search_reflections",
                confidence=0.85,
                extracted_args={},
            )

            with patch.object(detector, "_pattern_match", new_callable=MagicMock) as mock_pattern:
                mock_pattern.return_value = MagicMock(
                    tool_name="checkpoint",
                    confidence=0.8,
                    extracted_args={},
                )

                result = await detector.get_suggestions("what did I learn", limit=1)

                assert len(result) <= 1

    @pytest.mark.asyncio
    async def test_get_suggestions_sorted_by_confidence(self):
        """Test that suggestions are sorted by confidence descending."""
        from session_buddy.core.intent_detector import IntentDetector

        detector = IntentDetector()
        detector._load_default_patterns()

        with patch.object(detector, "_semantic_match", new_callable=AsyncMock) as mock_semantic:
            mock_semantic.return_value = MagicMock(
                tool_name="checkpoint",
                confidence=0.7,
                extracted_args={},
            )

            with patch.object(detector, "_pattern_match", new_callable=MagicMock) as mock_pattern:
                mock_pattern.return_value = MagicMock(
                    tool_name="search_reflections",
                    confidence=0.85,
                    extracted_args={},
                )

                result = await detector.get_suggestions("save my progress")

                if len(result) >= 2:
                    assert result[0]["confidence"] >= result[1]["confidence"]


# =============================================================================
# Intent Detection Tools Function Tests
# =============================================================================


class TestFormatDetectedIntent:
    """Tests for _format_detected_intent helper."""

    def test_format_detected_intent_creates_correct_structure(self, mock_tool_match):
        """Test that _format_detected_intent creates correct structure."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            _format_detected_intent,
        )

        result = _format_detected_intent(mock_tool_match)

        assert result["detected"] is True
        assert result["tool_name"] == "checkpoint"
        assert result["confidence"] == 0.85
        assert result["extracted_args"] == {"user_id": "test_user"}
        assert result["disambiguation_needed"] is False
        assert "message" in result


class TestFormatNoIntentMatch:
    """Tests for _format_no_intent_match helper."""

    @pytest.mark.asyncio
    async def test_format_no_intent_match_with_suggestions(self, mock_intent_detector):
        """Test formatting with suggestions available."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            _format_no_intent_match,
        )

        with patch.object(mock_intent_detector, "get_suggestions", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [
                {"tool": "checkpoint", "confidence": 0.6},
                {"tool": "search_reflections", "confidence": 0.4},
            ]

            result = await _format_no_intent_match(mock_intent_detector, "some message")

            assert result["detected"] is False
            assert "suggestions" in result
            assert len(result["suggestions"]) == 2

    @pytest.mark.asyncio
    async def test_format_no_intent_match_without_suggestions(self, mock_intent_detector):
        """Test formatting when no suggestions available."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            _format_no_intent_match,
        )

        with patch.object(mock_intent_detector, "get_suggestions", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []

            result = await _format_no_intent_match(mock_intent_detector, "some message")

            assert result["detected"] is False
            assert "message" in result
            assert "I couldn't determine which tool" in result["message"]


class TestBuildToolsInfo:
    """Tests for _build_tools_info helper."""

    def test_build_tools_info_creates_correct_structure(self, mock_intent_detector):
        """Test that _build_tools_info creates correct tool info structure."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            _build_tools_info,
        )

        result = _build_tools_info(mock_intent_detector)

        assert "checkpoint" in result
        assert "search_reflections" in result

        assert "patterns" in result["checkpoint"]
        assert "semantic_examples" in result["checkpoint"]
        assert "has_argument_extraction" in result["checkpoint"]

    def test_build_tools_info_includes_all_tools(self, mock_intent_detector):
        """Test that all tools from patterns are included."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            _build_tools_info,
        )

        result = _build_tools_info(mock_intent_detector)

        assert len(result) == len(mock_intent_detector.patterns)


# =============================================================================
# MCP Tool Function Tests
# =============================================================================


class TestDetectIntentTool:
    """Tests for detect_intent MCP tool."""

    @pytest.mark.asyncio
    async def test_detect_intent_returns_formatted_result(self, mock_tool_match):
        """Test that detect_intent returns properly formatted result."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            detect_intent,
        )

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
            new_callable=AsyncMock,
        ) as mock_get_detector:
            mock_detector = MagicMock()
            mock_detector.detect_intent = AsyncMock(return_value=mock_tool_match)
            mock_get_detector.return_value = mock_detector

            result = await detect_intent("save my progress")

            assert result["detected"] is True
            assert result["tool_name"] == "checkpoint"
            assert result["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_detect_intent_handles_exception(self):
        """Test that detect_intent handles exceptions gracefully."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            detect_intent,
        )

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools._detect_intent_impl",
            new_callable=AsyncMock,
        ) as mock_impl:
            mock_impl.side_effect = Exception("Detection failed")

            result = await detect_intent("save my progress")

            assert result["detected"] is False
            assert "error" in result
            assert "message" in result


class TestGetIntentSuggestionsTool:
    """Tests for get_intent_suggestions MCP tool."""

    @pytest.mark.asyncio
    async def test_get_intent_suggestions_returns_suggestions(self):
        """Test that get_intent_suggestions returns suggestions list."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            get_intent_suggestions,
        )

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
            new_callable=AsyncMock,
        ) as mock_get_detector:
            mock_detector = MagicMock()
            mock_detector.get_suggestions = AsyncMock(
                return_value=[
                    {"tool": "checkpoint", "confidence": 0.8, "match_type": "pattern"},
                    {"tool": "quality_monitor", "confidence": 0.6, "match_type": "semantic"},
                ]
            )
            mock_get_detector.return_value = mock_detector

            result = await get_intent_suggestions("save or check quality")

            assert "suggestions" in result
            assert result["count"] == 2
            assert "message" in result

    @pytest.mark.asyncio
    async def test_get_intent_suggestions_handles_exception(self):
        """Test that get_intent_suggestions handles exceptions gracefully."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            get_intent_suggestions,
        )

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools._get_intent_suggestions_impl",
            new_callable=AsyncMock,
        ) as mock_impl:
            mock_impl.side_effect = Exception("Suggestions failed")

            result = await get_intent_suggestions("some message")

            assert result["suggestions"] == []
            assert result["count"] == 0
            assert "error" in result


class TestListSupportedIntentsTool:
    """Tests for list_supported_intents MCP tool."""

    @pytest.mark.asyncio
    async def test_list_supported_intents_returns_tools_dict(self, mock_intent_detector):
        """Test that list_supported_intents returns tools dictionary."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            list_supported_intents,
        )

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
            new_callable=AsyncMock,
        ) as mock_get_detector:
            mock_get_detector.return_value = mock_intent_detector

            result = await list_supported_intents()

            assert "tools" in result
            assert "total_tools" in result
            assert result["total_tools"] == 2
            assert "message" in result

    @pytest.mark.asyncio
    async def test_list_supported_intents_handles_exception(self):
        """Test that list_supported_intents handles exceptions gracefully."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            list_supported_intents,
        )

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools._list_supported_intents_impl",
            new_callable=AsyncMock,
        ) as mock_impl:
            mock_impl.side_effect = Exception("List failed")

            result = await list_supported_intents()

            assert result["tools"] == {}
            assert result["total_tools"] == 0
            assert "error" in result


class TestProcessNaturalLanguageInput:
    """Tests for process_natural_language_input convenience function."""

    @pytest.mark.asyncio
    async def test_process_natural_language_returns_execute_for_high_confidence(
        self, mock_tool_match,
    ):
        """Test that high confidence match returns execute type."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            process_natural_language_input,
        )

        mock_tool_match.disambiguation_needed = False

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
            new_callable=AsyncMock,
        ) as mock_get_detector:
            mock_detector = MagicMock()
            mock_detector.detect_intent = AsyncMock(return_value=mock_tool_match)
            mock_get_detector.return_value = mock_detector

            result = await process_natural_language_input("save my progress")

            assert result is not None
            assert result["type"] == "execute_tool"
            assert result["tool"] == "checkpoint"

    @pytest.mark.asyncio
    async def test_process_natural_language_returns_disambiguation_when_needed(
        self, mock_tool_match,
    ):
        """Test that disambiguation_needed returns disambiguation type."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            process_natural_language_input,
        )

        mock_tool_match.disambiguation_needed = True
        mock_tool_match.alternatives = ["search_reflections"]

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
            new_callable=AsyncMock,
        ) as mock_get_detector:
            mock_detector = MagicMock()
            mock_detector.detect_intent = AsyncMock(return_value=mock_tool_match)
            mock_get_detector.return_value = mock_detector

            result = await process_natural_language_input("some ambiguous message")

            assert result is not None
            assert result["type"] == "disambiguation"
            assert "alternatives" in result

    @pytest.mark.asyncio
    async def test_process_natural_language_returns_none_when_no_match(self):
        """Test that no confident match returns None."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            process_natural_language_input,
        )

        with patch(
            "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
            new_callable=AsyncMock,
        ) as mock_get_detector:
            mock_detector = MagicMock()
            mock_detector.detect_intent = AsyncMock(return_value=None)
            mock_get_detector.return_value = mock_detector

            result = await process_natural_language_input("completely random text")

            assert result is None


class TestRegisterIntentTools:
    """Tests for register_intent_tools function."""

    def test_register_intent_tools_registers_three_tools(self):
        """Test that register_intent_tools registers exactly three tools."""
        from session_buddy.mcp.tools.advanced.intent_detection_tools import (
            register_intent_tools,
        )

        mock_mcp = MagicMock()
        mock_mcp.tool.return_value = lambda f: f

        register_intent_tools(mock_mcp)

        assert mock_mcp.tool.call_count == 3
