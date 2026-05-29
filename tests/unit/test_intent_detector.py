"""Unit tests for session_buddy.core.intent_detector."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from session_buddy.core.intent_detector import IntentDetector, ToolMatch


class TestToolMatch:
    """Tests for ToolMatch dataclass."""

    def test_tool_match_creation(self) -> None:
        """Test ToolMatch can be created with required fields."""
        match = ToolMatch(
            tool_name="checkpoint",
            confidence=0.85,
            extracted_args={"project": "test"},
        )

        assert match.tool_name == "checkpoint"
        assert match.confidence == 0.85
        assert match.extracted_args == {"project": "test"}
        assert match.disambiguation_needed is False
        assert match.alternatives == []

    def test_tool_match_with_disambiguation(self) -> None:
        """Test ToolMatch can indicate disambiguation needed."""
        match = ToolMatch(
            tool_name="search",
            confidence=0.6,
            extracted_args={},
            disambiguation_needed=True,
            alternatives=["search_reflections", "search_conversations"],
        )

        assert match.disambiguation_needed is True
        assert len(match.alternatives) == 2

    def test_tool_match_defaults(self) -> None:
        """Test ToolMatch has sensible defaults."""
        match = ToolMatch(
            tool_name="checkpoint",
            confidence=0.9,
            extracted_args={},
        )

        assert match.disambiguation_needed is False
        assert match.alternatives == []


class TestIntentDetector:
    """Tests for IntentDetector class."""

    @pytest.fixture
    def detector(self) -> IntentDetector:
        """Create an IntentDetector for testing."""
        return IntentDetector()

    @pytest.mark.asyncio
    async def test_detect_intent_returns_none_for_empty_message(self, detector: IntentDetector) -> None:
        """Test detect_intent returns None for empty/whitespace message."""
        result = await detector.detect_intent("   ")

        assert result is None

    @pytest.mark.asyncio
    async def test_detect_intent_returns_none_for_empty_string(self, detector: IntentDetector) -> None:
        """Test detect_intent returns None for empty string."""
        result = await detector.detect_intent("")

        assert result is None

    @pytest.mark.asyncio
    async def test_detect_intent_below_threshold(self, detector: IntentDetector) -> None:
        """Test detect_intent returns None when confidence below threshold."""
        # Use default patterns that won't match "xyzzyywfjkwelk"
        result = await detector.detect_intent("xyzzyywfjkwelk", confidence_threshold=0.9)

        assert result is None

    def test_pattern_match_finds_exact_keyword(self, detector: IntentDetector) -> None:
        """Test pattern matching finds exact keyword matches."""
        detector._load_default_patterns()

        result = detector._pattern_match("create a checkpoint now")

        assert result is not None
        assert result.tool_name == "checkpoint"
        assert result.confidence == 0.8

    def test_pattern_match_case_insensitive(self, detector: IntentDetector) -> None:
        """Test pattern matching is case insensitive."""
        detector._load_default_patterns()

        result = detector._pattern_match("CREATE A CHECKPOINT")

        assert result is not None
        assert result.tool_name == "checkpoint"

    def test_pattern_match_none_when_no_match(self, detector: IntentDetector) -> None:
        """Test pattern matching returns None for no match."""
        detector._load_default_patterns()

        result = detector._pattern_match("unmatched gibberish xyz")

        assert result is None

    def test_combine_matches_both_none(self, detector: IntentDetector) -> None:
        """Test combine_matches returns None when both are None."""
        result = detector._combine_matches(None, None)

        assert result is None

    def test_combine_matches_only_semantic(self, detector: IntentDetector) -> None:
        """Test combine_matches returns semantic when only semantic matches."""
        semantic = ToolMatch(tool_name="search", confidence=0.7, extracted_args={})

        result = detector._combine_matches(semantic, None)

        assert result is semantic

    def test_combine_matches_only_pattern(self, detector: IntentDetector) -> None:
        """Test combine_matches returns pattern when only pattern matches."""
        pattern = ToolMatch(tool_name="checkpoint", confidence=0.8, extracted_args={})

        result = detector._combine_matches(None, pattern)

        assert result is pattern

    def test_combine_matches_agree_increases_confidence(self, detector: IntentDetector) -> None:
        """Test combine_matches gives high confidence when both agree."""
        semantic = ToolMatch(tool_name="checkpoint", confidence=0.7, extracted_args={})
        pattern = ToolMatch(tool_name="checkpoint", confidence=0.8, extracted_args={})

        result = detector._combine_matches(semantic, pattern)

        assert result is not None
        assert result.tool_name == "checkpoint"
        assert result.confidence > 0.8  # Min of 0.95

    def test_combine_matches_disagree_returns_higher(self, detector: IntentDetector) -> None:
        """Test combine_matches returns higher confidence when disagreeing."""
        semantic = ToolMatch(tool_name="checkpoint", confidence=0.7, extracted_args={})
        pattern = ToolMatch(tool_name="search", confidence=0.8, extracted_args={})

        result = detector._combine_matches(semantic, pattern)

        assert result is not None
        assert result.disambiguation_needed is True
        assert result.tool_name == "search"  # higher confidence wins

    @pytest.mark.asyncio
    async def test_extract_arguments_no_rules(self, detector: IntentDetector) -> None:
        """Test extract_arguments returns empty when no rules for tool."""
        result = await detector._extract_arguments("some message", "unknown_tool")

        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_arguments_with_patterns(self, detector: IntentDetector) -> None:
        """Test extract_arguments extracts matched groups."""
        # Set up argument extraction rules manually
        detector.argument_extraction = {
            "search": {
                "query": {
                    "patterns": [r"search for (.+)", r"find (.+)"],
                }
            }
        }

        result = await detector._extract_arguments("search for authentication", "search")

        assert "query" in result
        assert result["query"] == "authentication"

    @pytest.mark.asyncio
    async def test_get_suggestions_returns_list(self, detector: IntentDetector) -> None:
        """Test get_suggestions returns list."""
        detector.patterns = {"checkpoint": ["checkpoint"]}

        result = await detector.get_suggestions("checkpoint", limit=3)

        assert isinstance(result, list)
        assert len(result) <= 3

    def test_load_default_patterns_populates_data(self, detector: IntentDetector) -> None:
        """Test _load_default_patterns populates patterns and examples."""
        detector._load_default_patterns()

        assert "checkpoint" in detector.patterns
        assert "checkpoint" in detector.semantic_examples
        assert len(detector.patterns["checkpoint"]) > 0
        assert len(detector.semantic_examples["checkpoint"]) > 0

    @pytest.mark.asyncio
    async def test_semantic_match_handles_embedding_failure(self, detector: IntentDetector) -> None:
        """Test semantic matching gracefully handles failures."""
        # Seed semantic examples so matching can occur
        detector.semantic_examples = {"checkpoint": ["create a checkpoint"]}

        # Mock at the point of use
        with patch("session_buddy.reflection_tools.generate_embedding", side_effect=ImportError("Module not available")):
            result = await detector._semantic_match("create a checkpoint")

        assert result is None
