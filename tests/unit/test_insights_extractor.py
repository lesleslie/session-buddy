"""
Unit tests for insight extraction logic.

Tests all extractor functionality:
- extract_insights_from_response()
- extract_insights_from_context()
- detect_insight_type()
- extract_topics()
- calculate_confidence_score()
"""

from datetime import UTC, datetime

import pytest
from session_buddy.insights.extractor import (
    INSIGHT_DELIMITER_END,
    INSIGHT_DELIMITER_START,
    ExtractedInsight,
    calculate_confidence_score,
    detect_insight_type,
    extract_insights_from_context,
    extract_insights_from_response,
    extract_topics,
    filter_duplicate_insights,
    generate_insight_hash,
    normalize_insight_content,
)


class TestExtractInsightsFromResponse:
    """Test insight extraction from individual responses."""

    def test_extract_basic_insight(self):
        """Test extracting a basic insight with delimiters."""
        response = f"""
Some explanation text.

{INSIGHT_DELIMITER_START}
Always use async/await for database operations to prevent blocking the event loop
{INSIGHT_DELIMITER_END}

More text here.
"""

        insights = extract_insights_from_response(response)

        assert len(insights) == 1
        assert "async/await" in insights[0].content
        assert insights[0].confidence > 0.5  # Should have decent confidence

    def test_extract_multiple_insights(self):
        """Test extracting multiple insights from one response."""
        response = f"""
{INSIGHT_DELIMITER_START}
First insight about async patterns
{INSIGHT_DELIMITER_END}

Some explanation.

{INSIGHT_DELIMITER_START}
Second insight about database optimization
{INSIGHT_DELIMITER_END}

More text.
"""

        insights = extract_insights_from_response(response)

        assert len(insights) == 2
        assert "async patterns" in insights[0].content
        assert "database optimization" in insights[1].content

    def test_extract_no_insights_when_delimiters_absent(self):
        """Test that regular text without delimiters yields no insights."""
        response = "This is just regular text without any special delimiters."

        insights = extract_insights_from_response(response)

        assert len(insights) == 0

    def test_extract_with_conversation_id(self):
        """Test extraction with conversation ID tracking."""
        response = f"""
{INSIGHT_DELIMITER_START}
Test insight content about async patterns and database operations
{INSIGHT_DELIMITER_END}
"""

        insights = extract_insights_from_response(
            response,
            conversation_id="test-conv-123",
        )

        assert len(insights) == 1
        assert insights[0].source_conversation_id == "test-conv-123"

    def test_extract_with_reflection_id(self):
        """Test extraction with reflection ID tracking."""
        response = f"""
{INSIGHT_DELIMITER_START}
Test insight content about async patterns and database operations
{INSIGHT_DELIMITER_END}
"""

        insights = extract_insights_from_response(
            response,
            reflection_id="test-refl-456",
        )

        assert len(insights) == 1
        assert insights[0].source_reflection_id == "test-refl-456"

    def test_min_confidence_threshold(self):
        """Test minimum confidence threshold filtering."""
        # Create insight with very weak patterns (should have low confidence)
        response = f"""
{INSIGHT_DELIMITER_START}
Maybe consider something sometimes
{INSIGHT_DELIMITER_END}
"""

        insights_high = extract_insights_from_response(response, min_confidence=0.5)
        insights_low = extract_insights_from_response(response, min_confidence=0.2)

        # High threshold should filter out weak insights
        assert len(insights_high) == 0
        # Low threshold should include weak insights
        assert len(insights_low) >= 1

    def test_skip_too_short_insights(self):
        """Test that very short content is skipped."""
        response = f"""
{INSIGHT_DELIMITER_START}
Too short
{INSIGHT_DELIMITER_END}
"""

        insights = extract_insights_from_response(response)

        assert len(insights) == 0  # Too short to qualify

    def test_skip_too_long_insights(self):
        """Test that excessively long content is skipped."""
        # Create content exceeding MAX_INSIGHT_LENGTH (10000)
        long_content = "x" * 11000

        response = f"""
{INSIGHT_DELIMITER_START}
{long_content}
{INSIGHT_DELIMITER_END}
"""

        insights = extract_insights_from_response(response)

        assert len(insights) == 0  # Too long, security limit

    def test_whitespace_trimmed(self):
        """Test that leading/trailing whitespace is trimmed."""
        response = f"""
{INSIGHT_DELIMITER_START}

    Test insight with extra whitespace

{INSIGHT_DELIMITER_END}
"""

        insights = extract_insights_from_response(response)

        assert len(insights) == 1
        assert insights[0].content == "Test insight with extra whitespace"


class TestExtractInsightsFromContext:
    """Test insight extraction from full session context."""

    def test_extract_from_conversation_history(self):
        """Test extraction from conversation history in context."""
        context = {
            "conversation_id": "test-conv",
            "conversation_history": [
                {
                    "role": "user",
                    "content": "How do I use async patterns?",
                },
                {
                    "role": "assistant",
                    "content": f"""
{INSIGHT_DELIMITER_START}
Always use async/await for database operations
{INSIGHT_DELIMITER_END}

This prevents blocking the event loop.
""",
                },
            ],
        }

        insights = extract_insights_from_context(context)

        assert len(insights) == 1
        assert "async/await" in insights[0].content
        assert insights[0].source_conversation_id == "test-conv"

    def test_extract_from_recent_reflections(self):
        """Test extraction from recent reflections in context."""
        context = {
            "conversation_id": "test-conv",
            "recent_reflections": [
                {
                    "id": "refl-1",
                    "content": f"""
{INSIGHT_DELIMITER_START}
Use type hints for better code clarity
{INSIGHT_DELIMITER_END}
""",
                },
            ],
        }

        insights = extract_insights_from_context(context)

        assert len(insights) == 1
        assert "type hints" in insights[0].content
        assert insights[0].source_reflection_id == "refl-1"

    def test_deduplicate_insights(self):
        """Test that duplicate insights are removed."""
        context = {
            "conversation_history": [
                {
                    "role": "assistant",
                    "content": f"""
{INSIGHT_DELIMITER_START}
Use async/await for database operations
{INSIGHT_DELIMITER_END}
""",
                },
                {
                    "role": "assistant",
                    "content": f"""
{INSIGHT_DELIMITER_START}
Use async/await for database operations
{INSIGHT_DELIMITER_END}
""",
                },
            ],
        }

        insights = extract_insights_from_context(context)

        assert len(insights) == 1  # Duplicates removed

    def test_empty_context_returns_empty(self):
        """Test that empty context returns no insights."""
        context = {}

        insights = extract_insights_from_context(context)

        assert len(insights) == 0


class TestDetectInsightType:
    """Test insight type detection."""

    def test_detect_pattern_type(self):
        """Test detection of 'pattern' type."""
        content = "Use async/await pattern for I/O operations"
        insight_type = detect_insight_type(content)
        assert insight_type == "pattern"

    def test_detect_architecture_type(self):
        """Test detection of 'architecture' type."""
        content = "The system architecture uses a layered design"
        insight_type = detect_insight_type(content)
        assert insight_type == "architecture"

    def test_detect_best_practice_type(self):
        """Test detection of 'best_practice' type."""
        content = "You should always validate user input"
        insight_type = detect_insight_type(content)
        assert insight_type == "best_practice"

    def test_detect_gotcha_type(self):
        """Test detection of 'gotcha' type."""
        content = "Watch out for this common mistake"
        insight_type = detect_insight_type(content)
        assert insight_type == "gotcha"

    def test_default_to_general_type(self):
        """Test that unclassified content defaults to 'general'."""
        content = "Some generic text without specific technical guidance"
        insight_type = detect_insight_type(content)
        assert insight_type == "general"


class TestExtractTopics:
    """Test topic extraction from content."""

    def test_extract_async_topic(self):
        """Test extraction of 'async' topic."""
        topics = extract_topics("Use async/await for database operations")
        assert "async" in topics

    def test_extract_database_topic(self):
        """Test extraction of 'database' topic."""
        topics = extract_topics("SQL query optimization techniques")
        assert "database" in topics

    def test_extract_multiple_topics(self):
        """Test extraction of multiple topics."""
        topics = extract_topics("Use async/await patterns for database operations in Python")
        assert "async" in topics
        assert "database" in topics
        assert "python" in topics

    def test_no_topics_returns_empty(self):
        """Test that content without keywords returns empty list."""
        topics = extract_topics("Random text with no technical keywords")
        assert len(topics) == 0

    def test_topics_unique(self):
        """Test that each topic appears only once."""
        topics = extract_topics("async async async database database")
        # Each topic should appear only once
        assert topics.count("async") == 1
        assert topics.count("database") == 1


class TestCalculateConfidenceScore:
    """Test confidence score calculation."""

    def test_base_confidence_score(self):
        """Test that base confidence is 0.3."""
        confidence = calculate_confidence_score(
            "Random content",
            "general",
            [],
        )
        assert confidence == 0.3

    def test_topic_coverage_bonus(self):
        """Test confidence bonus for topic coverage."""
        # No topics
        confidence_no_topics = calculate_confidence_score(
            "Random content",
            "general",
            [],
        )

        # With topics
        confidence_with_topics = calculate_confidence_score(
            "Use async/await for database operations",
            "pattern",
            ["async", "database"],
        )

        assert confidence_with_topics > confidence_no_topics

    def test_strong_pattern_bonus(self):
        """Test confidence bonus for strong patterns."""
        # Strong pattern
        confidence_strong = calculate_confidence_score(
            "Always use async/await for database operations",
            "pattern",
            ["async"],
        )

        # Weak pattern
        confidence_weak = calculate_confidence_score(
            "Sometimes consider async patterns",
            "pattern",
            ["async"],
        )

        assert confidence_strong > confidence_weak

    def test_length_factor(self):
        """Test confidence factor for optimal length."""
        # Good length (50-500 chars)
        confidence_good = calculate_confidence_score(
            "x" * 100,
            "general",
            [],
        )

        # Too short
        confidence_short = calculate_confidence_score(
            "x" * 20,
            "general",
            [],
        )

        assert confidence_good > confidence_short

    def test_confidence_capped_at_1_0(self):
        """Test that confidence never exceeds 1.0."""
        confidence = calculate_confidence_score(
            "Always use async/await for database operations. This is the best practice for high performance applications.",
            "pattern",
            ["async", "database", "performance", "best_practice"],
        )

        assert confidence <= 1.0

    def test_specific_type_bonus(self):
        """Test confidence bonus for specific types."""
        # Specific type
        confidence_specific = calculate_confidence_score(
            "Use async/await for I/O operations",
            "pattern",
            ["async"],
        )

        # General type
        confidence_general = calculate_confidence_score(
            "Use async/await for I/O operations",
            "general",
            ["async"],
        )

        assert confidence_specific > confidence_general


class TestExtractedInsight:
    """Test ExtractedInsight dataclass."""

    def test_create_valid_insight(self):
        """Test creating a valid insight."""
        insight = ExtractedInsight(
            content="Use async/await for database operations",
            insight_type="pattern",
            topics=["async", "database"],
            confidence=0.8,
        )

        assert insight.content == "Use async/await for database operations"
        assert insight.insight_type == "pattern"
        assert insight.topics == ["async", "database"]
        assert insight.confidence == 0.8

    def test_whitespace_trimmed(self):
        """Test that content whitespace is trimmed."""
        insight = ExtractedInsight(
            content="  Use async/await for database operations  ",
        )

        assert insight.content == "Use async/await for database operations"

    def test_extracted_at_defaults_to_now(self):
        """Test that extracted_at defaults to current time."""
        before = datetime.now(UTC)
        insight = ExtractedInsight(
            content="Test insight content about async patterns and database operations"
        )
        after = datetime.now(UTC)

        assert before <= insight.extracted_at <= after

    def test_invalid_confidence_raises(self):
        """Test that invalid confidence score raises error."""
        with pytest.raises(ValueError):
            ExtractedInsight(
                content="Test content",
                confidence=1.5,  # Invalid: > 1.0
            )

    def test_invalid_quality_score_raises(self):
        """Test that invalid quality score raises error."""
        with pytest.raises(ValueError):
            ExtractedInsight(
                content="Test content",
                quality_score=-0.1,  # Invalid: < 0.0
            )

    def test_too_short_content_raises(self):
        """Test that too short content raises error."""
        with pytest.raises(ValueError):
            ExtractedInsight(
                content="Too short",  # Less than MIN_INSIGHT_LENGTH (30)
            )

    def test_too_long_content_raises(self):
        """Test that too long content raises error."""
        with pytest.raises(ValueError):
            ExtractedInsight(
                content="x" * 11000,  # More than MAX_INSIGHT_LENGTH (10000)
            )


class TestNormalizeInsightContent:
    """Test insight content normalization for deduplication."""

    def test_lowercase_conversion(self):
        """Test that content is converted to lowercase."""
        normalized = normalize_insight_content("Use Async/Await for Database")
        assert normalized == "use asyncawait for database"

    def test_punctuation_removal(self):
        """Test that common punctuation is removed."""
        normalized = normalize_insight_content("Use async/await, for I/O!")
        assert normalized == "use asyncawait for io"

    def test_whitespace_normalization(self):
        """Test that extra whitespace is collapsed."""
        normalized = normalize_insight_content("Use  async/await  for  database")
        assert normalized == "use asyncawait for database"

    def test_leading_trailing_whitespace_trim(self):
        """Test that leading/trailing whitespace is removed."""
        normalized = normalize_insight_content("  Use async/await for database  ")
        assert normalized == "use asyncawait for database"

    def test_combined_normalization(self):
        """Test that all normalization rules work together."""
        normalized = normalize_insight_content("  Use Async/Await for I/O,  Database!  ")
        assert normalized == "use asyncawait for io database"


class TestGenerateInsightHash:
    """Test SHA-256 hash generation for deduplication."""

    def test_hash_is_consistent(self):
        """Test that identical content produces identical hashes."""
        content = "Use async/await for database operations"
        hash1 = generate_insight_hash(content)
        hash2 = generate_insight_hash(content)
        assert hash1 == hash2

    def test_hash_ignores_case(self):
        """Test that hash ignores case differences."""
        hash1 = generate_insight_hash("Use async/await for I/O")
        hash2 = generate_insight_hash("use async/await for i/o")
        assert hash1 == hash2

    def test_hash_ignores_punctuation(self):
        """Test that hash ignores punctuation differences."""
        hash1 = generate_insight_hash("Use async/await for I/O!")
        hash2 = generate_insight_hash("Use async/await for I/O.")
        assert hash1 == hash2

    def test_hash_ignores_whitespace(self):
        """Test that hash ignores extra whitespace."""
        hash1 = generate_insight_hash("Use async/await for database")
        hash2 = generate_insight_hash("Use  async/await  for  database")
        assert hash1 == hash2

    def test_hash_is_unique_for_different_content(self):
        """Test that different content produces different hashes."""
        hash1 = generate_insight_hash("Use async/await for database operations")
        hash2 = generate_insight_hash("Use type hints for better code clarity")
        assert hash1 != hash2

    def test_hash_format(self):
        """Test that hash is hexadecimal string."""
        content = "Test insight content about async patterns and database operations"
        content_hash = generate_insight_hash(content)
        assert isinstance(content_hash, str)
        assert len(content_hash) == 64  # SHA-256 produces 64 hex characters
        assert all(c in "0123456789abcdef" for c in content_hash)


class TestFilterDuplicateInsights:
    """Test deduplication filtering of insights."""

    def test_no_duplicates_returns_all(self):
        """Test that all unique insights are returned."""
        insights = [
            ExtractedInsight(content="Use async/await for database operations"),
            ExtractedInsight(content="Use type hints for better code clarity"),
            ExtractedInsight(content="Always validate user input before processing"),
        ]

        unique_insights, seen_hashes = filter_duplicate_insights(insights)

        assert len(unique_insights) == 3
        assert len(seen_hashes) == 3

    def test_filters_exact_duplicates(self):
        """Test that exact duplicates are filtered out."""
        content = "Use async/await for database operations"
        insights = [
            ExtractedInsight(content=content),
            ExtractedInsight(content=content),  # Exact duplicate
            ExtractedInsight(content="Use type hints for better code clarity"),
        ]

        unique_insights, seen_hashes = filter_duplicate_insights(insights)

        assert len(unique_insights) == 2
        assert len(seen_hashes) == 2

    def test_filters_near_duplicates(self):
        """Test that near-duplicates (formatting differences) are filtered out."""
        insights = [
            ExtractedInsight(content="Use async/await for I/O operations!"),
            ExtractedInsight(content="Use async/await for I/O operations."),  # Different punctuation
            ExtractedInsight(content="USE async/await FOR I/O OPERATIONS"),  # Different case
            ExtractedInsight(content="Use type hints for better code clarity"),
        ]

        unique_insights, seen_hashes = filter_duplicate_insights(insights)

        assert len(unique_insights) == 2
        assert len(seen_hashes) == 2

    def test_empty_list_returns_empty(self):
        """Test that empty input returns empty results."""
        unique_insights, seen_hashes = filter_duplicate_insights([])

        assert unique_insights == []
        assert seen_hashes == set()

    def test_seen_hashes_persists_across_calls(self):
        """Test that seen_hashes tracking works across multiple calls."""
        # First call
        insights1 = [
            ExtractedInsight(content="Use async/await for database operations"),
            ExtractedInsight(content="Use type hints for better code clarity"),
        ]

        unique_insights1, seen_hashes = filter_duplicate_insights(insights1)
        assert len(unique_insights1) == 2
        assert len(seen_hashes) == 2

        # Second call with one duplicate and one new
        insights2 = [
            ExtractedInsight(content="Use async/await for database operations"),  # Duplicate
            ExtractedInsight(content="Always validate user input before processing"),  # New
        ]

        unique_insights2, updated_hashes = filter_duplicate_insights(
            insights2,
            seen_hashes=seen_hashes,  # Pass existing hashes
        )

        assert len(unique_insights2) == 1  # Only the new insight
        assert len(updated_hashes) == 3  # 2 from first call + 1 new
        assert updated_hashes == seen_hashes  # Same set object

    def test_none_seen_hashes_initializes_empty(self):
        """Test that None seen_hashes initializes new set."""
        insights = [
            ExtractedInsight(content="Use async/await for database operations"),
        ]

        unique_insights, seen_hashes = filter_duplicate_insights(
            insights,
            seen_hashes=None,  # Initialize new set
        )

        assert len(unique_insights) == 1
        assert isinstance(seen_hashes, set)
        assert len(seen_hashes) == 1
