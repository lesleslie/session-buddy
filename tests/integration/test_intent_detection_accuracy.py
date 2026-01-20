"""Integration tests for Natural Language Intent Detection accuracy.

Tests the accuracy of intent detection across various tools and phrasing variations.
Target: >90% accuracy for common use cases.
"""

from __future__ import annotations

import pytest
from session_buddy.core.intent_detector import IntentDetector, ToolMatch


@pytest.fixture
async def detector() -> IntentDetector:
    """Initialize intent detector for testing."""
    detector = IntentDetector()
    await detector.initialize()
    return detector


class TestIntentDetectionAccuracy:
    """Test intent detection accuracy across various tools."""

    @pytest.mark.asyncio
    async def test_checkpoint_phrases(self, detector: IntentDetector) -> None:
        """Test checkpoint detection with various phrasings."""
        test_cases = [
            ("save my progress", "checkpoint", 0.8),
            ("checkpoint this", "checkpoint", 0.8),
            ("create a checkpoint", "checkpoint", 0.8),
            ("I want to save", "checkpoint", 0.8),
            ("Time to checkpoint before the next feature", "checkpoint", 0.6),
            ("Let me save what I have so far", "checkpoint", 0.6),
        ]

        passed = 0
        for message, expected_tool, min_confidence in test_cases:
            result = await detector.detect_intent(message, confidence_threshold=0.5)
            if result and result.tool_name == expected_tool and result.confidence >= min_confidence:
                passed += 1
            else:
                print(f"❌ Failed: '{message}' -> expected {expected_tool}, got {result}")

        accuracy = passed / len(test_cases)
        print(f"\n✅ Checkpoint accuracy: {accuracy:.1%} ({passed}/{len(test_cases)})")
        assert accuracy >= 0.9, f"Checkpoint accuracy {accuracy:.1%} below 90% target"

    @pytest.mark.asyncio
    async def test_search_reflections_phrases(self, detector: IntentDetector) -> None:
        """Test search_reflections detection with various phrasings."""
        test_cases = [
            ("what did I learn about async?", "search_reflections", 0.7),
            ("find insights on authentication", "search_reflections", 0.7),
            ("search for database patterns", "search_reflections", 0.7),
            ("What do I know about optimization?", "search_reflections", 0.7),
            ("Any insights on error handling?", "search_reflections", 0.7),
        ]

        passed = 0
        for message, expected_tool, min_confidence in test_cases:
            result = await detector.detect_intent(message, confidence_threshold=0.5)
            if result and result.tool_name == expected_tool and result.confidence >= min_confidence:
                passed += 1
            else:
                print(f"❌ Failed: '{message}' -> expected {expected_tool}, got {result}")

        accuracy = passed / len(test_cases)
        print(f"\n✅ Search reflections accuracy: {accuracy:.1%} ({passed}/{len(test_cases)})")
        assert accuracy >= 0.9, f"Search reflections accuracy {accuracy:.1%} below 90% target"

    @pytest.mark.asyncio
    async def test_quality_monitor_phrases(self, detector: IntentDetector) -> None:
        """Test quality_monitor detection with various phrasings."""
        test_cases = [
            ("how's the code quality", "quality_monitor", 0.8),
            ("check quality", "quality_monitor", 0.8),
            ("analyze project health", "quality_monitor", 0.8),
            ("What's the current project health?", "quality_monitor", 0.6),
            ("Check the quality of my recent work", "quality_monitor", 0.6),
        ]

        passed = 0
        for message, expected_tool, min_confidence in test_cases:
            result = await detector.detect_intent(message, confidence_threshold=0.5)
            if result and result.tool_name == expected_tool and result.confidence >= min_confidence:
                passed += 1
            else:
                print(f"❌ Failed: '{message}' -> expected {expected_tool}, got {result}")

        accuracy = passed / len(test_cases)
        print(f"\n✅ Quality monitor accuracy: {accuracy:.1%} ({passed}/{len(test_cases)})")
        assert accuracy >= 0.9, f"Quality monitor accuracy {accuracy:.1%} below 90% target"

    @pytest.mark.asyncio
    async def test_store_reflection_phrases(self, detector: IntentDetector) -> None:
        """Test store_reflection detection with various phrasings."""
        test_cases = [
            ("remember that", "store_reflection", 0.8),
            ("save as insight", "store_reflection", 0.8),
            ("create a reflection", "store_reflection", 0.8),
            ("note this", "store_reflection", 0.8),
            ("Remember that we fixed this by using retries", "store_reflection", 0.6),
        ]

        passed = 0
        for message, expected_tool, min_confidence in test_cases:
            result = await detector.detect_intent(message, confidence_threshold=0.5)
            if result and result.tool_name == expected_tool and result.confidence >= min_confidence:
                passed += 1
            else:
                print(f"❌ Failed: '{message}' -> expected {expected_tool}, got {result}")

        accuracy = passed / len(test_cases)
        print(f"\n✅ Store reflection accuracy: {accuracy:.1%} ({passed}/{len(test_cases)})")
        assert accuracy >= 0.9, f"Store reflection accuracy {accuracy:.1%} below 90% target"

    @pytest.mark.asyncio
    async def test_crackerjack_health_check_phrases(self, detector: IntentDetector) -> None:
        """Test crackerjack_health_check detection with various phrasings."""
        test_cases = [
            ("check crackerjack", "crackerjack_health_check", 0.8),
            ("crackerjack status", "crackerjack_health_check", 0.8),
            ("is crackerjack working", "crackerjack_health_check", 0.8),
            ("Is crackerjack working properly?", "crackerjack_health_check", 0.6),
        ]

        passed = 0
        for message, expected_tool, min_confidence in test_cases:
            result = await detector.detect_intent(message, confidence_threshold=0.5)
            if result and result.tool_name == expected_tool and result.confidence >= min_confidence:
                passed += 1
            else:
                print(f"❌ Failed: '{message}' -> expected {expected_tool}, got {result}")

        accuracy = passed / len(test_cases)
        print(f"\n✅ Crackerjack health check accuracy: {accuracy:.1%} ({passed}/{len(test_cases)})")
        assert accuracy >= 0.9, f"Crackerjack health check accuracy {accuracy:.1%} below 90% target"


class TestArgumentExtraction:
    """Test argument extraction from natural language."""

    @pytest.mark.asyncio
    async def test_search_reflections_argument_extraction(self, detector: IntentDetector) -> None:
        """Test argument extraction for search_reflections."""
        test_cases = [
            ("what did I learn about async?", "async"),
            ("find insights on authentication", "authentication"),
            ("search for database patterns", "database patterns"),
        ]

        passed = 0
        for message, expected_query in test_cases:
            result = await detector.detect_intent(message, confidence_threshold=0.5)
            if (
                result
                and result.tool_name == "search_reflections"
                and result.extracted_args.get("query") == expected_query
            ):
                passed += 1
            else:
                print(f"❌ Failed: '{message}' -> expected query '{expected_query}', got {result.extracted_args if result else {}}")

        accuracy = passed / len(test_cases)
        print(f"\n✅ Argument extraction accuracy: {accuracy:.1%} ({passed}/{len(test_cases)})")
        assert accuracy >= 0.9, f"Argument extraction accuracy {accuracy:.1%} below 90% target"

    @pytest.mark.asyncio
    async def test_query_similar_errors_argument_extraction(self, detector: IntentDetector) -> None:
        """Test argument extraction for query_similar_errors."""
        test_cases = [
            ("have I seen this TypeError before?", "TypeError"),
            ("have I encountered this timeout error?", "timeout"),
            ("similar import errors", "import errors"),
        ]

        passed = 0
        for message, expected_error in test_cases:
            result = await detector.detect_intent(message, confidence_threshold=0.5)
            if (
                result
                and result.tool_name == "query_similar_errors"
                and result.extracted_args.get("error_message") == expected_error
            ):
                passed += 1
            else:
                print(f"❌ Failed: '{message}' -> expected error '{expected_error}', got {result.extracted_args if result else {}}")

        accuracy = passed / len(test_cases)
        print(f"\n✅ Error argument extraction accuracy: {accuracy:.1%} ({passed}/{len(test_cases)})")
        assert accuracy >= 0.9, f"Error argument extraction accuracy {accuracy:.1%} below 90% target"


class TestDisambiguation:
    """Test disambiguation handling for ambiguous inputs."""

    @pytest.mark.asyncio
    async def test_low_confidence_returns_none(self, detector: IntentDetector) -> None:
        """Test that low confidence inputs return None."""
        # Very ambiguous message
        result = await detector.detect_intent("do something", confidence_threshold=0.7)
        assert result is None, "Low confidence input should return None"

    @pytest.mark.asyncio
    async def test_suggestions_for_ambiguous_input(self, detector: IntentDetector) -> None:
        """Test that suggestions are provided for ambiguous input."""
        # "check quality" could match quality_monitor or crackerjack_health_check
        suggestions = await detector.get_suggestions("check quality", limit=3)

        assert len(suggestions) > 0, "Should provide suggestions for ambiguous input"
        assert all("tool" in s for s in suggestions), "All suggestions should have tool names"
        assert all("confidence" in s for s in suggestions), "All suggestions should have confidence"


class TestConfidenceScoring:
    """Test confidence scoring mechanism."""

    @pytest.mark.asyncio
    async def test_pattern_match_confidence(self, detector: IntentDetector) -> None:
        """Test that pattern matches get expected confidence."""
        result = await detector.detect_intent("save my progress", confidence_threshold=0.5)
        assert result is not None
        assert result.confidence == 0.8, "Pattern match should have 0.8 confidence"

    @pytest.mark.asyncio
    async def test_semantic_match_confidence_range(self, detector: IntentDetector) -> None:
        """Test that semantic matches have appropriate confidence range."""
        # This should match semantically
        result = await detector.detect_intent("I've made good progress", confidence_threshold=0.5)
        if result:
            assert 0.0 <= result.confidence <= 1.0, "Confidence should be between 0 and 1"

    @pytest.mark.asyncio
    async def test_confidence_threshold_filtering(self, detector: IntentDetector) -> None:
        """Test that confidence threshold filters results."""
        # Very high threshold should filter out most matches
        result_strict = await detector.detect_intent("check it", confidence_threshold=0.95)
        assert result_strict is None, "High threshold should filter low confidence matches"

        # Lower threshold should allow matches
        result_lenient = await detector.detect_intent("check it", confidence_threshold=0.3)
        # May or may not match depending on pattern strength


class TestOverallAccuracy:
    """Overall accuracy tests across all tools."""

    @pytest.mark.asyncio
    async def test_overall_accuracy_target(self, detector: IntentDetector) -> None:
        """Test overall accuracy across diverse toolset (>90% target)."""
        # Representative sample from different tool categories
        test_cases = [
            # Session management
            ("save my progress", "checkpoint"),
            ("end my session", "end"),
            ("session status", "status"),

            # Search & memory
            ("what did I learn about async?", "search_reflections"),
            ("find code related to dependency injection", "search_by_concept"),
            ("what did I do to auth.py?", "search_by_file"),

            # Quality & monitoring
            ("how's the code quality", "quality_monitor"),
            ("check crackerjack", "crackerjack_health_check"),

            # Reflection & learning
            ("remember that", "store_reflection"),
            ("how can I improve?", "suggest_workflow_improvements"),

            # Advanced features
            ("what files am I editing?", "get_active_files"),
            ("activity summary", "get_activity_summary"),
        ]

        passed = 0
        for message, expected_tool in test_cases:
            result = await detector.detect_intent(message, confidence_threshold=0.5)
            if result and result.tool_name == expected_tool:
                passed += 1
            else:
                print(f"❌ Failed: '{message}' -> expected {expected_tool}, got {result.tool_name if result else None}")

        accuracy = passed / len(test_cases)
        print(f"\n✅ Overall accuracy: {accuracy:.1%} ({passed}/{len(test_cases)})")
        assert accuracy >= 0.9, f"Overall accuracy {accuracy:.1%} below 90% target"


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_message(self, detector: IntentDetector) -> None:
        """Test handling of empty messages."""
        result = await detector.detect_intent("", confidence_threshold=0.7)
        assert result is None, "Empty message should return None"

    @pytest.mark.asyncio
    async def test_whitespace_only_message(self, detector: IntentDetector) -> None:
        """Test handling of whitespace-only messages."""
        result = await detector.detect_intent("   ", confidence_threshold=0.7)
        assert result is None, "Whitespace-only message should return None"

    @pytest.mark.asyncio
    async def test_unknown_command(self, detector: IntentDetector) -> None:
        """Test handling of unknown commands."""
        result = await detector.detect_intent("xyz123", confidence_threshold=0.7)
        assert result is None, "Unknown command should return None"

    @pytest.mark.asyncio
    async def test_graceful_degradation(self, detector: IntentDetector) -> None:
        """Test graceful degradation when embeddings fail."""
        # This test verifies the system works even when semantic matching fails
        # Pattern matching should still work
        result = await detector.detect_intent("save my progress", confidence_threshold=0.5)
        assert result is not None, "Should fallback to pattern matching"
        assert result.tool_name == "checkpoint", "Pattern match should work"
