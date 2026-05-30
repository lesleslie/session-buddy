"""Unit tests for fingerprint-based duplicate detection tools.

Tests MinHash-based duplicate detection including:
- find_duplicates() function
- fingerprint_search() function
- deduplicate_content() function
- threshold validation and Jaccard similarity logic
- edge cases: empty content, threshold boundaries (0.85, 0.95)
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch, AsyncMock

import pytest

# Import the tools under test
from session_buddy.mcp.tools.advanced.fingerprint_tools import (
    find_duplicates,
    fingerprint_search,
    deduplicate_content,
    deduplication_stats,
    _search_by_token_overlap,
    _is_duplicate_fingerprint,
    _check_if_duplicate,
    _format_stats_result,
    _format_dedup_dry_run_result,
    _format_deduplication_error,
    _format_stats_error,
)

# Import MinHashSignature for direct testing
from session_buddy.utils.fingerprint import MinHashSignature


# =====================================
# Fixtures
# =====================================


@pytest.fixture
def mock_db():
    """Create a mock ReflectionDatabaseAdapterOneiric instance."""
    mock = MagicMock()
    mock._check_for_duplicates = Mock(return_value=[])
    mock.conn = MagicMock()
    return mock


@pytest.fixture
def sample_signature():
    """Create a sample MinHashSignature for testing."""
    return MinHashSignature.from_text("Python async programming patterns")


@pytest.fixture
def signature_with_content():
    """Create signatures with specific content for similarity testing."""
    sig1 = MinHashSignature.from_text("Python async patterns for async/await")
    sig2 = MinHashSignature.from_text("Python async patterns")
    return sig1, sig2


# =====================================
# MinHashSignature Unit Tests
# =====================================


class TestMinHashSignature:
    """Tests for MinHashSignature class used by fingerprint tools."""

    def test_from_text_creates_valid_signature(self):
        """Test that from_text creates a valid MinHashSignature."""
        sig = MinHashSignature.from_text("Test content for fingerprinting")
        assert sig is not None
        assert sig.num_hashes == 128
        assert len(sig.signature) == 128

    def test_from_text_normalizes_content(self):
        """Test that from_text normalizes content before fingerprinting."""
        sig1 = MinHashSignature.from_text("Python  async\npatterns")
        sig2 = MinHashSignature.from_text("python async patterns")
        # Normalized content should produce same or very similar signatures
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity > 0.8  # High similarity after normalization

    def test_identical_content_produces_identical_signatures(self):
        """Test that identical content produces identical signatures."""
        sig1 = MinHashSignature.from_text("Python async programming")
        sig2 = MinHashSignature.from_text("Python async programming")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity == 1.0

    def test_empty_content_produces_empty_signature(self):
        """Test that empty content doesn't crash."""
        sig = MinHashSignature.from_text("")
        assert len(sig.signature) == 128
        # All zeros for empty content
        assert all(s == 0 for s in sig.signature)

    def test_short_content_produces_valid_signature(self):
        """Test that very short content produces valid signature."""
        sig = MinHashSignature.from_text("ai")
        assert len(sig.signature) == 128

    def test_estimate_jaccard_similarity_same_content(self):
        """Test Jaccard similarity estimation for identical content."""
        sig1 = MinHashSignature.from_text("Python async patterns for web services")
        sig2 = MinHashSignature.from_text("Python async patterns for web services")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity >= 0.95  # Should be very high for identical

    def test_estimate_jaccard_similarity_different_content(self):
        """Test Jaccard similarity estimation for different content."""
        sig1 = MinHashSignature.from_text("Python async programming")
        sig2 = MinHashSignature.from_text("Rust ownership borrowing")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity < 0.5  # Should be low for different content

    def test_estimate_jaccard_similarity_similar_content(self):
        """Test Jaccard similarity estimation for similar content."""
        sig1 = MinHashSignature.from_text("Python async programming patterns")
        sig2 = MinHashSignature.from_text("Python async patterns for programming")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Similar content should have moderate to high similarity
        assert 0.5 < similarity < 1.0

    def test_to_bytes_and_from_bytes_roundtrip(self):
        """Test that to_bytes and from_bytes preserve signature."""
        original = MinHashSignature.from_text("Test content for roundtrip")
        bytes_data = original.to_bytes()
        restored = MinHashSignature.from_bytes(bytes_data)
        # Signatures should be identical after roundtrip
        for i in range(original.num_hashes):
            assert original.signature[i] == restored.signature[i]

    def test_signature_validation_on_post_init(self):
        """Test that signature length is validated."""
        with pytest.raises(ValueError):
            MinHashSignature(signature=[1, 2, 3], num_hashes=128)


# =====================================
# find_duplicates() Tests
# =====================================


class TestFindDuplicates:
    """Tests for the find_duplicates() function."""

    @pytest.mark.asyncio
    async def test_find_duplicates_empty_content(self):
        """Test find_duplicates with empty content."""
        result = await find_duplicates(
            content="",
            threshold=0.85,
            limit=10,
            collection_name="default",
        )
        # Should handle empty content gracefully
        assert "success" in result
        assert "duplicates" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_find_duplicates_threshold_0_85(self):
        """Test find_duplicates with threshold=0.85."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await find_duplicates(
                content="Test content for duplicate detection",
                content_type="reflection",
                threshold=0.85,
                limit=10,
                collection_name="default",
            )

            assert result["success"] is True
            assert "threshold_used" in result
            assert result["threshold_used"] == 0.85

    @pytest.mark.asyncio
    async def test_find_duplicates_threshold_0_95(self):
        """Test find_duplicates with threshold=0.95 (near-identical)."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = [
                {"id": "dup1", "content": "Similar content", "similarity": 0.97}
            ]
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await find_duplicates(
                content="Python async programming patterns",
                content_type="conversation",
                threshold=0.95,
                limit=5,
                collection_name="test_collection",
            )

            assert result["success"] is True
            assert result["threshold_used"] == 0.95
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_find_duplicates_no_duplicates(self):
        """Test find_duplicates when no duplicates found."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await find_duplicates(
                content="Unique content not in database",
                threshold=0.85,
            )

            assert result["success"] is True
            assert result["count"] == 0
            assert result["duplicates"] == []

    @pytest.mark.asyncio
    async def test_find_duplicates_respects_limit(self):
        """Test that find_duplicates respects the limit parameter."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            # Return more than limit items
            mock_instance._check_for_duplicates.return_value = [
                {"id": f"dup{i}", "content": f"Duplicate {i}", "similarity": 0.9}
                for i in range(20)
            ]
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await find_duplicates(
                content="Test content",
                threshold=0.85,
                limit=5,
            )

            assert result["count"] == 5
            assert len(result["duplicates"]) == 5

    @pytest.mark.asyncio
    async def test_find_duplicates_error_handling(self):
        """Test find_duplicates error handling."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            MockDB.return_value.__aenter__.side_effect = Exception("Database error")

            result = await find_duplicates(
                content="Test content",
                threshold=0.85,
            )

            assert result["success"] is False
            assert result["count"] == 0
            assert "error" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_find_duplicates_conversation_type(self):
        """Test find_duplicates with conversation content type."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await find_duplicates(
                content="Conversation content",
                content_type="conversation",
                threshold=0.85,
            )

            assert result["content_type"] == "conversation"
            mock_instance._check_for_duplicates.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_duplicates_reflection_type(self):
        """Test find_duplicates with reflection content type."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await find_duplicates(
                content="Reflection content",
                content_type="reflection",
                threshold=0.85,
            )

            assert result["content_type"] == "reflection"


# =====================================
# fingerprint_search() Tests
# =====================================


class TestFingerprintSearch:
    """Tests for the fingerprint_search() function."""

    @pytest.mark.asyncio
    async def test_fingerprint_search_empty_query(self):
        """Test fingerprint_search with empty query."""
        result = await fingerprint_search(
            query="",
            threshold=0.70,
            limit=10,
            collection_name="default",
        )
        # Should handle empty gracefully
        assert "success" in result
        assert "results" in result

    @pytest.mark.asyncio
    async def test_fingerprint_search_threshold_0_70(self):
        """Test fingerprint_search with default threshold."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await fingerprint_search(
                query="Python async patterns",
                threshold=0.70,
            )

            assert result["success"] is True
            assert "threshold_used" in result
            assert result["threshold_used"] == 0.70

    @pytest.mark.asyncio
    async def test_fingerprint_search_high_threshold(self):
        """Test fingerprint_search with high threshold (0.95)."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await fingerprint_search(
                query="Rust ownership borrowing lifetimes",
                threshold=0.95,
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_fingerprint_search_conversation_filter(self):
        """Test fingerprint_search with conversation filter."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await fingerprint_search(
                query="Web development Django REST",
                content_type="conversation",
            )

            assert result["success"] is True
            # Should only call _check_for_duplicates for conversation

    @pytest.mark.asyncio
    async def test_fingerprint_search_reflection_filter(self):
        """Test fingerprint_search with reflection filter."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await fingerprint_search(
                query="Database schema design",
                content_type="reflection",
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_fingerprint_search_no_results(self):
        """Test fingerprint_search when no results found."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            mock_instance.conn.execute.return_value.fetchall.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await fingerprint_search(
                query="Completely unique query content xyz123",
                threshold=0.90,
            )

            assert result["success"] is True
            assert result["total_results"] == 0

    @pytest.mark.asyncio
    async def test_fingerprint_search_with_results(self):
        """Test fingerprint_search returning results."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = [
                {"id": "conv1", "content": "Python async patterns", "similarity": 0.92}
            ]
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await fingerprint_search(
                query="Python async",
                threshold=0.70,
            )

            assert result["success"] is True
            assert result["total_results"] >= 1

    @pytest.mark.asyncio
    async def test_fingerprint_search_error_handling(self):
        """Test fingerprint_search error handling."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            MockDB.return_value.__aenter__.side_effect = Exception("Database error")

            result = await fingerprint_search(
                query="Test query",
                threshold=0.85,
            )

            assert result["success"] is False
            assert result["total_results"] == 0


# =====================================
# deduplicate_content() Tests
# =====================================


class TestDeduplicateContent:
    """Tests for the deduplicate_content() function."""

    @pytest.mark.asyncio
    async def test_deduplicate_content_dry_run_true(self):
        """Test deduplicate_content with dry_run=True."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance.conn.execute.return_value.fetchall.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await deduplicate_content(
                content_type="both",
                threshold=0.85,
                dry_run=True,
                collection_name="default",
            )

            assert result["success"] is True
            assert "DRY RUN" in result["message"]

    @pytest.mark.asyncio
    async def test_deduplicate_content_dry_run_false(self):
        """Test deduplicate_content with dry_run=False (actual deletion)."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance.conn.execute.return_value.fetchall.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await deduplicate_content(
                content_type="both",
                threshold=0.85,
                dry_run=False,
                collection_name="default",
            )

            assert result["success"] is True
            assert "DRY RUN" not in result["message"]

    @pytest.mark.asyncio
    async def test_deduplicate_content_conversation_only(self):
        """Test deduplicate_content with conversation type only."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance.conn.execute.return_value.fetchall.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await deduplicate_content(
                content_type="conversation",
                threshold=0.85,
                dry_run=True,
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_deduplicate_content_reflection_only(self):
        """Test deduplicate_content with reflection type only."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance.conn.execute.return_value.fetchall.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await deduplicate_content(
                content_type="reflection",
                threshold=0.85,
                dry_run=True,
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_deduplicate_content_threshold_0_85(self):
        """Test deduplicate_content with threshold=0.85."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance.conn.execute.return_value.fetchall.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await deduplicate_content(
                threshold=0.85,
                dry_run=True,
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_deduplicate_content_threshold_0_95(self):
        """Test deduplicate_content with threshold=0.95."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance.conn.execute.return_value.fetchall.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await deduplicate_content(
                threshold=0.95,
                dry_run=True,
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_deduplicate_content_error_handling(self):
        """Test deduplicate_content error handling."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            MockDB.return_value.__aenter__.side_effect = Exception("Database error")

            result = await deduplicate_content(
                threshold=0.85,
                dry_run=True,
            )

            assert result["success"] is False
            assert result["duplicates_removed"] == 0


# =====================================
# deduplication_stats() Tests
# =====================================


class TestDeduplicationStats:
    """Tests for the deduplication_stats() function."""

    @pytest.mark.asyncio
    async def test_deduplication_stats_empty_database(self):
        """Test deduplication_stats with empty database."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            # Empty tables
            mock_instance.conn.execute.return_value.fetchone.return_value = (0,)
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await deduplication_stats(
                collection_name="default",
                threshold=0.85,
            )

            assert result["success"] is True
            assert result["total_items"] == 0

    @pytest.mark.asyncio
    async def test_deduplication_stats_with_data(self):
        """Test deduplication_stats with data in database."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()

            def execute_side_effect(query, params=None):
                mock_result = MagicMock()
                if "COUNT(*)" in query:
                    mock_result.fetchone.return_value = (100,)
                elif "fingerprint" in query:
                    mock_result.fetchall.return_value = []
                return mock_result

            mock_instance.conn.execute.side_effect = execute_side_effect
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await deduplication_stats(
                collection_name="default",
                threshold=0.85,
            )

            assert result["success"] is True
            assert "total_items" in result
            assert "duplicate_rate" in result

    @pytest.mark.asyncio
    async def test_deduplication_stats_error_handling(self):
        """Test deduplication_stats error handling."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            MockDB.return_value.__aenter__.side_effect = Exception("Database error")

            result = await deduplication_stats(threshold=0.85)

            assert result["success"] is False
            assert "error" in result["message"].lower()


# =====================================
# Helper Function Tests
# =====================================


class TestHelperFunctions:
    """Tests for helper functions used internally."""

    def test_is_duplicate_fingerprint_below_threshold(self):
        """Test _is_duplicate_fingerprint when similarity is below threshold."""
        sig1 = MinHashSignature.from_text("Python async programming")
        sig2 = MinHashSignature.from_text("Rust ownership model")

        seen_set = {sig1.to_bytes()}

        is_dup = _is_duplicate_fingerprint(sig2.to_bytes(), seen_set, threshold=0.9)
        # Different content should not be duplicate at high threshold
        assert is_dup is False

    def test_is_duplicate_fingerprint_above_threshold(self):
        """Test _is_duplicate_fingerprint when similarity is above threshold."""
        sig1 = MinHashSignature.from_text("Python async patterns")
        sig2 = MinHashSignature.from_text("Python async patterns")

        seen_set = {sig1.to_bytes()}

        is_dup = _is_duplicate_fingerprint(sig2.to_bytes(), seen_set, threshold=0.95)
        # Identical content should be duplicate at high threshold
        assert is_dup is True

    def test_check_if_duplicate_empty_seen_set(self):
        """Test _check_if_duplicate with empty seen set."""
        sig = MinHashSignature.from_text("New unique content")
        seen_set: set[bytes] = set()

        is_dup = _check_if_duplicate(sig.to_bytes(), seen_set, threshold=0.85)
        # Empty seen set means nothing is duplicate
        assert is_dup is False

    def test_format_stats_result(self):
        """Test _format_stats_result formatting."""
        result = _format_stats_result(
            total_conversations=50,
            total_reflections=50,
            duplicate_conversations=10,
            duplicate_reflections=15,
            threshold=0.85,
        )

        assert result["success"] is True
        assert result["total_items"] == 100
        assert result["total_duplicates"] == 25
        assert result["duplicate_rate"] == 25.0

    def test_format_stats_result_empty(self):
        """Test _format_stats_result with empty database."""
        result = _format_stats_result(
            total_conversations=0,
            total_reflections=0,
            duplicate_conversations=0,
            duplicate_reflections=0,
            threshold=0.85,
        )

        assert result["success"] is True
        assert result["total_items"] == 0
        assert result["duplicate_rate"] == 0

    def test_format_dedup_dry_run_result(self):
        """Test _format_dedup_dry_run_result formatting."""
        ids_to_remove = [
            {"id": "dup1", "type": "conversation"},
            {"id": "dup2", "type": "reflection"},
        ]

        result = _format_dedup_dry_run_result(ids_to_remove, threshold=0.85)

        assert result["success"] is True
        assert result["duplicates_removed"] == 2
        assert len(result["ids_removed"]) == 2
        assert "DRY RUN" in result["message"]

    def test_format_deduplication_error(self):
        """Test _format_deduplication_error formatting."""
        result = _format_deduplication_error("Database connection failed")

        assert result["success"] is False
        assert result["duplicates_removed"] == 0
        assert result["ids_removed"] == []
        assert "error" in result["message"].lower()

    def test_format_stats_error(self):
        """Test _format_stats_error formatting."""
        result = _format_stats_error("Database error")

        assert result["success"] is False
        assert result["total_items"] == 0
        assert "error" in result["message"].lower()


# =====================================
# Jaccard Similarity Boundary Tests
# =====================================


class TestJaccardSimilarityBoundaries:
    """Tests for Jaccard similarity at threshold boundaries."""

    def test_identical_content_similarity(self):
        """Test that identical content achieves ~1.0 similarity."""
        sig1 = MinHashSignature.from_text("Python async programming patterns for web services")
        sig2 = MinHashSignature.from_text("Python async programming patterns for web services")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity >= 0.95

    def test_near_identical_content_similarity_0_95_threshold(self):
        """Test content that's near-identical passes 0.95 threshold."""
        sig1 = MinHashSignature.from_text("Python async programming patterns")
        sig2 = MinHashSignature.from_text("Python async programming patterns in web development")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Near-identical should be above 0.60
        assert similarity > 0.60

    def test_completely_different_content_low_similarity(self):
        """Test that completely different content has low similarity."""
        sig1 = MinHashSignature.from_text("Python async programming patterns")
        sig2 = MinHashSignature.from_text("Rust ownership borrowing lifetimes")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity < 0.3

    def test_minor_variations_content_similarity(self):
        """Test that minor variations maintain moderate similarity."""
        sig1 = MinHashSignature.from_text("Testing async Python code")
        sig2 = MinHashSignature.from_text("Testing async Python code with pytest")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert 0.5 < similarity < 1.0

    def test_threshold_0_85_classification(self):
        """Test that 0.85 threshold correctly classifies near-duplicates."""
        sig1 = MinHashSignature.from_text("Web development with Django REST API")
        sig2 = MinHashSignature.from_text("Web development with Django REST framework")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        # These should be similar enough for 0.85 threshold
        assert similarity >= 0.70

    def test_threshold_0_95_perfect_duplicates(self):
        """Test that 0.95 threshold catches perfect duplicates."""
        sig1 = MinHashSignature.from_text("Exact same content for duplicate detection")
        sig2 = MinHashSignature.from_text("Exact same content for duplicate detection")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity >= 0.95


# =====================================
# Edge Case Tests
# =====================================


class TestEdgeCases:
    """Tests for edge cases in fingerprint tools."""

    def test_empty_signature_bytes(self):
        """Test handling of empty/minimal signatures."""
        sig = MinHashSignature(signature=[0] * 128, num_hashes=128)
        bytes_data = sig.to_bytes()
        restored = MinHashSignature.from_bytes(bytes_data)
        assert len(restored.signature) == 128

    def test_very_short_content_fingerprint(self):
        """Test fingerprinting of very short content."""
        sig = MinHashSignature.from_text("x")
        assert len(sig.signature) == 128

    def test_unicode_content_fingerprint(self):
        """Test fingerprinting of unicode content."""
        sig = MinHashSignature.from_text("Python async 编程")
        assert len(sig.signature) == 128

    def test_special_characters_content_fingerprint(self):
        """Test fingerprinting of content with special characters."""
        sig = MinHashSignature.from_text("Code@#$%^&*()!测试")
        assert len(sig.signature) == 128

    def test_whitespace_only_content(self):
        """Test fingerprinting of whitespace-only content."""
        sig = MinHashSignature.from_text("   \n\t\t   ")
        assert len(sig.signature) == 128

    @pytest.mark.asyncio
    async def test_find_duplicates_very_long_content(self):
        """Test find_duplicates with very long content."""
        long_content = "Python async programming. " * 1000

        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await find_duplicates(
                content=long_content,
                threshold=0.85,
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_fingerprint_search_special_characters_query(self):
        """Test fingerprint_search with special characters in query."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            result = await fingerprint_search(
                query="Python @#$%^& async",
                threshold=0.70,
            )

            assert result["success"] is True

    def test_signature_from_bytes_invalid_length(self):
        """Test that from_bytes raises error for invalid data length."""
        with pytest.raises(ValueError):
            MinHashSignature.from_bytes(b"too_short")

    def test_jaccard_similarity_different_num_hashes(self):
        """Test that comparing signatures with different num_hashes raises error."""
        sig1 = MinHashSignature(signature=[1] * 128, num_hashes=128)
        sig2 = MinHashSignature(signature=[1] * 64, num_hashes=64)

        with pytest.raises(ValueError):
            sig1.estimate_jaccard_similarity(sig2)


# =====================================
# Integration-ish Tests (with mocked DB)
# =====================================


class TestFingerprintToolsIntegration:
    """Integration tests that test the tools working together."""

    @pytest.mark.asyncio
    async def test_find_duplicates_then_deduplicate_flow(self):
        """Test the flow of finding duplicates then deduplicating."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = [
                {"id": "dup1", "content": "Duplicate content", "similarity": 0.95}
            ]
            mock_instance.conn.execute.return_value.fetchall.return_value = [
                ("dup1", "Duplicate content", b"\x00" * 1024)
            ]
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            # First find duplicates
            find_result = await find_duplicates(
                content="Duplicate content",
                threshold=0.85,
            )
            assert find_result["success"] is True

            # Then deduplicate (dry run)
            dedup_result = await deduplicate_content(
                content_type="reflection",
                threshold=0.85,
                dry_run=True,
            )
            assert dedup_result["success"] is True

    @pytest.mark.asyncio
    async def test_search_then_stats_flow(self):
        """Test the flow of searching then getting stats."""
        with patch(
            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
        ) as MockDB:
            mock_instance = MagicMock()
            mock_instance._check_for_duplicates.return_value = []
            mock_instance.conn.execute.return_value.fetchone.return_value = (50,)
            MockDB.return_value.__aenter__.return_value = mock_instance
            MockDB.return_value.__aexit__.return_value = AsyncMock()

            # Search for content
            search_result = await fingerprint_search(
                query="Python patterns",
                threshold=0.70,
            )
            assert search_result["success"] is True

            # Get deduplication stats
            stats_result = await deduplication_stats(
                collection_name="default",
                threshold=0.85,
            )
            assert stats_result["success"] is True
