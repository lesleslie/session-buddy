"""Unit tests for utils.search.models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from session_buddy.utils.search.models import (
    SearchFacet,
    SearchFilter,
    SearchResult,
)


class TestSearchFilter:
    """Tests for SearchFilter dataclass."""

    def test_equality_operator_field(self):
        """Verify 'eq' operator is properly stored."""
        f = SearchFilter(field="status", operator="eq", value="active")
        assert f.operator == "eq"
        assert f.value == "active"

    def test_not_equal_operator(self):
        """Verify 'ne' operator is properly stored."""
        f = SearchFilter(field="status", operator="ne", value="deleted")
        assert f.operator == "ne"

    def test_in_operator_with_list(self):
        """Verify 'in' operator works with list values."""
        f = SearchFilter(field="tag", operator="in", value=["python", "testing"])
        assert f.operator == "in"
        assert f.value == ["python", "testing"]

    def test_not_in_operator(self):
        """Verify 'not_in' operator works with list values."""
        f = SearchFilter(field="tag", operator="not_in", value=["deprecated"])
        assert f.operator == "not_in"

    def test_contains_operator(self):
        """Verify 'contains' operator works for substring matching."""
        f = SearchFilter(field="content", operator="contains", value="error")
        assert f.operator == "contains"

    def test_starts_with_operator(self):
        """Verify 'starts_with' operator."""
        f = SearchFilter(field="name", operator="starts_with", value="test_")
        assert f.operator == "starts_with"

    def test_ends_with_operator(self):
        """Verify 'ends_with' operator."""
        f = SearchFilter(field="name", operator="ends_with", value="_backup")
        assert f.operator == "ends_with"

    def test_range_operator_with_tuple(self):
        """Verify 'range' operator works with tuple values."""
        f = SearchFilter(field="score", operator="range", value=(0.5, 1.0))
        assert f.operator == "range"
        assert f.value == (0.5, 1.0)

    def test_negate_flag_default_false(self):
        """Verify negate defaults to False."""
        f = SearchFilter(field="active", operator="eq", value=True)
        assert f.negate is False

    def test_negate_flag_can_be_true(self):
        """Verify negate can be set to True."""
        f = SearchFilter(field="active", operator="eq", value=True, negate=True)
        assert f.negate is True

    def test_string_value(self):
        """Verify string values work."""
        f = SearchFilter(field="name", operator="eq", value="my-search")
        assert f.value == "my-search"

    def test_numeric_value(self):
        """Verify numeric values work (stored as str | list | tuple)."""
        f = SearchFilter(field="priority", operator="eq", value="42")
        assert f.value == "42"


class TestSearchFacet:
    """Tests for SearchFacet dataclass."""

    def test_facet_with_terms_type(self):
        """Verify default 'terms' facet type."""
        values = [("python", 10), ("testing", 5)]
        facet = SearchFacet(name="language", values=values)

        assert facet.name == "language"
        assert facet.values == values
        assert facet.facet_type == "terms"

    def test_facet_with_range_type(self):
        """Verify 'range' facet type."""
        values = [("low", 3), ("medium", 7), ("high", 2)]
        facet = SearchFacet(name="priority", values=values, facet_type="range")

        assert facet.facet_type == "range"

    def test_facet_with_date_type(self):
        """Verify 'date' facet type."""
        values = [("2024-01", 15), ("2024-02", 22)]
        facet = SearchFacet(name="created", values=values, facet_type="date")

        assert facet.facet_type == "date"

    def test_empty_values_list(self):
        """Verify empty values list is allowed."""
        facet = SearchFacet(name="empty", values=[])
        assert facet.values == []

    def test_values_are_tuples(self):
        """Verify values must be (string, int) tuples."""
        values = [("category1", 100), ("category2", 50)]
        facet = SearchFacet(name="category", values=values)

        # Verify structure - each tuple has string and count
        for value, count in facet.values:
            assert isinstance(value, str)
            assert isinstance(count, int)


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_required_fields(self):
        """Verify all required fields are present."""
        result = SearchResult(
            content_id="id-123",
            content_type="conversation",
            title="Test Title",
            content="This is the content",
            score=0.95,
        )

        assert result.content_id == "id-123"
        assert result.content_type == "conversation"
        assert result.title == "Test Title"
        assert result.content == "This is the content"
        assert result.score == 0.95

    def test_optional_project_default_none(self):
        """Verify project defaults to None."""
        result = SearchResult(
            content_id="id-456",
            content_type="reflection",
            title="Reflection",
            content="...",
            score=0.8,
        )

        assert result.project is None

    def test_optional_project_set(self):
        """Verify project can be set."""
        result = SearchResult(
            content_id="id-789",
            content_type="conversation",
            title="Test",
            content="...",
            score=0.7,
            project="my-project",
        )

        assert result.project == "my-project"

    def test_optional_timestamp_default_none(self):
        """Verify timestamp defaults to None."""
        result = SearchResult(
            content_id="id-t",
            content_type="reflection",
            title="T",
            content="...",
            score=0.6,
        )

        assert result.timestamp is None

    def test_optional_timestamp_set(self):
        """Verify timestamp can be set with datetime."""
        now = datetime.now()
        result = SearchResult(
            content_id="id-t2",
            content_type="conversation",
            title="T2",
            content="...",
            score=0.65,
            timestamp=now,
        )

        assert result.timestamp == now

    def test_metadata_default_empty_dict(self):
        """Verify metadata defaults to empty dict."""
        result = SearchResult(
            content_id="id-m",
            content_type="conversation",
            title="M",
            content="...",
            score=0.5,
        )

        assert result.metadata == {}

    def test_metadata_can_store_complex_data(self):
        """Verify metadata can store nested data."""
        complex_meta = {
            "author": "test-user",
            "version": 1,
            "tags": ["important", "archived"],
            "extra": {"nested": True},
        }

        result = SearchResult(
            content_id="id-m2",
            content_type="reflection",
            title="M2",
            content="...",
            score=0.55,
            metadata=complex_meta,
        )

        assert result.metadata == complex_meta

    def test_highlights_default_empty_list(self):
        """Verify highlights defaults to empty list."""
        result = SearchResult(
            content_id="id-h",
            content_type="conversation",
            title="H",
            content="...",
            score=0.4,
        )

        assert result.highlights == []

    def test_highlights_can_store_strings(self):
        """Verify highlights can store matched text snippets."""
        highlights = [
            "the <em>error</em> was fixed",
            "matching <em>search</em> term",
        ]

        result = SearchResult(
            content_id="id-h2",
            content_type="conversation",
            title="H2",
            content="...",
            score=0.45,
            highlights=highlights,
        )

        assert result.highlights == highlights

    def test_facets_default_empty_dict(self):
        """Verify facets defaults to empty dict."""
        result = SearchResult(
            content_id="id-f",
            content_type="conversation",
            title="F",
            content="...",
            score=0.3,
        )

        assert result.facets == {}

    def test_facets_can_store_facet_data(self):
        """Verify facets can store facet name to values mapping."""
        facets = {
            "language": [("python", 5), ("rust", 2)],
            "category": [("bug", 3), ("feature", 4)],
        }

        result = SearchResult(
            content_id="id-f2",
            content_type="conversation",
            title="F2",
            content="...",
            score=0.35,
            facets=facets,
        )

        assert result.facets == facets

    def test_all_fields_together(self):
        """Verify all fields can be set simultaneously."""
        now = datetime.now()
        result = SearchResult(
            content_id="id-all",
            content_type="conversation",
            title="All Fields",
            content="Full content here",
            score=0.99,
            project="test-project",
            timestamp=now,
            metadata={"key": "value"},
            highlights=["match 1", "match 2"],
            facets={"tag": [("python", 10)]},
        )

        assert result.content_id == "id-all"
        assert result.content_type == "conversation"
        assert result.title == "All Fields"
        assert result.content == "Full content here"
        assert result.score == 0.99
        assert result.project == "test-project"
        assert result.timestamp == now
        assert result.metadata == {"key": "value"}
        assert result.highlights == ["match 1", "match 2"]
        assert result.facets == {"tag": [("python", 10)]}
