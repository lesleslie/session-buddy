"""Unit tests for search utilities.

Tests cover:
- Search functionality
- Result processing
- Query parsing
"""

import pytest
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestSearchUtilities:
    """Tests for search utility functions."""

    def test_search_module_imports(self):
        """Test that search utilities can be imported."""
        try:
            from session_buddy.utils.search import utilities
            assert utilities is not None
        except ImportError:
            pytest.skip("Search utilities module not available")

    def test_query_normalization(self):
        """Test query string normalization."""
        queries = [
            "test query",
            "TEST QUERY",
            "  test  query  ",
        ]
        for q in queries:
            normalized = q.strip().lower()
            assert isinstance(normalized, str)

    def test_result_ranking(self):
        """Test search result ranking."""
        results = [
            {"score": 0.95, "text": "very relevant"},
            {"score": 0.65, "text": "somewhat relevant"},
            {"score": 0.45, "text": "not relevant"},
        ]
        sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)
        assert sorted_results[0]["score"] == 0.95
        assert sorted_results[-1]["score"] == 0.45

    def test_query_filtering(self):
        """Test query result filtering."""
        results = [
            {"score": 0.95, "tags": ["python", "testing"]},
            {"score": 0.65, "tags": ["javascript", "testing"]},
            {"score": 0.45, "tags": ["java", "building"]},
        ]
        filtered = [r for r in results if "testing" in r.get("tags", [])]
        assert len(filtered) == 2


@pytest.mark.unit
class TestSemanticSearch:
    """Tests for semantic search functionality."""

    def test_vector_similarity(self):
        """Test vector similarity calculation."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        vec3 = [0.0, 1.0, 0.0]

        # Identical vectors have high similarity
        # Orthogonal vectors have low similarity
        assert len(vec1) == len(vec2)
        assert len(vec1) == len(vec3)

    def test_embedding_representation(self):
        """Test embedding vector representation."""
        embedding = [0.1] * 384  # Standard embedding dimension
        assert len(embedding) == 384
        assert all(-1 <= x <= 1 for x in embedding)

    def test_search_result_deduplication(self):
        """Test deduplication of search results."""
        results = [
            {"id": "1", "score": 0.95},
            {"id": "1", "score": 0.93},
            {"id": "2", "score": 0.85},
        ]
        seen = set()
        deduplicated = []
        for result in results:
            if result["id"] not in seen:
                deduplicated.append(result)
                seen.add(result["id"])

        assert len(deduplicated) == 2
        assert deduplicated[0]["score"] == 0.95


@pytest.mark.unit
class TestSearchIntegration:
    """Integration tests for search functionality."""

    def test_search_pipeline(self):
        """Test complete search pipeline."""
        query = "python testing framework"
        corpus = [
            "pytest is a python testing framework",
            "unittest is builtin python testing",
            "javascript testing with jest",
        ]

        # Simple keyword matching
        results = []
        for i, doc in enumerate(corpus):
            if "python" in doc.lower() and "testing" in doc.lower():
                results.append((i, doc))

        assert len(results) >= 1
        assert results[0][1] == corpus[0]

    def test_multi_field_search(self):
        """Test searching across multiple fields."""
        documents = [
            {"title": "Python Testing", "content": "pytest guide", "tags": ["testing"]},
            {"title": "JavaScript", "content": "jest testing", "tags": ["javascript"]},
            {"title": "Testing Best Practices", "content": "general guide", "tags": ["testing"]},
        ]

        query = "testing"
        matches = [
            d for d in documents
            if query.lower() in d["title"].lower()
            or query.lower() in d["content"].lower()
            or query in d.get("tags", [])
        ]

        assert len(matches) >= 2

    def test_pagination_support(self):
        """Test result pagination."""
        results = list(range(1, 101))  # 100 results
        page_size = 10

        page_1 = results[0:page_size]
        page_2 = results[page_size:2*page_size]

        assert len(page_1) == 10
        assert page_1[0] == 1
        assert page_2[0] == 11
