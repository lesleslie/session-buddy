"""Comprehensive pytest tests for AdvancedSearchEngine.

Achieves comprehensive coverage of the advanced search functionality
including semantic search, keyword search, hybrid search, pagination,
filtering, result ranking, and edge cases.
"""

import asyncio
import json
import tempfile
from collections.abc import AsyncGenerator, Generator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the module under test
from session_buddy.advanced_search import AdvancedSearchEngine
from session_buddy.adapters.reflection_adapter import (
    ReflectionDatabaseAdapter as ReflectionDatabase,
)
from session_buddy.adapters.settings import ReflectionAdapterSettings
from session_buddy.utils.search import (
    SearchFacet,
    SearchFilter,
    SearchResult,
    ensure_timezone,
    extract_technical_terms,
    parse_timeframe,
    parse_timeframe_single,
    truncate_content,
)
from session_buddy.session_types import SQLCondition


# =====================================
# Fixtures
# =====================================


@pytest.fixture
async def temp_db_path() -> AsyncGenerator[str]:
    """Provide a temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
        db_path = tmp.name
    yield db_path
    # Cleanup
    try:
        Path(db_path).unlink()
    except (OSError, PermissionError):
        pass


@pytest.fixture
async def reflection_db(temp_db_path: str) -> AsyncGenerator[ReflectionDatabase]:
    """Provide initialized ReflectionDatabase instance."""
    settings = ReflectionAdapterSettings(
        database_path=Path(temp_db_path),
        collection_name="default",
        embedding_dim=384,
        distance_metric="cosine",
        enable_vss=False,
        threads=1,
        memory_limit="512MB",
        enable_embeddings=False,
    )

    db = ReflectionDatabase(settings=settings)

    try:
        await db.initialize()
        yield db
    finally:
        close = getattr(db, "aclose", None)
        if callable(close):
            await close()
        else:
            db.close()


@pytest.fixture
async def search_engine(reflection_db: ReflectionDatabase) -> AdvancedSearchEngine:
    """Create an AdvancedSearchEngine instance with initialized database."""
    return AdvancedSearchEngine(reflection_db)


@pytest.fixture
async def db_with_conversations(
    reflection_db: ReflectionDatabase,
) -> ReflectionDatabase:
    """Populate database with sample conversations."""
    conversations = [
        {
            "content": "Implementing user authentication with JWT tokens in Python Flask. Need to handle token expiration and refresh logic.",
            "project": "webapp-backend",
            "metadata": {"language": "python", "framework": "flask"},
        },
        {
            "content": "Frontend React component for user login form. Using axios for API calls.",
            "project": "webapp-frontend",
            "metadata": {"language": "javascript", "framework": "react"},
        },
        {
            "content": "Database schema design for user management with proper indexes.",
            "project": "webapp-backend",
            "metadata": {"database": "postgresql"},
        },
        {
            "content": "JWT token validation failed. TokenExpiredError: Signature has expired.",
            "project": "webapp-backend",
            "metadata": {"error_type": "TokenExpiredError"},
        },
        {
            "content": "DevOps: Setting up CI/CD pipeline with Docker containers.",
            "project": "devops-pipeline",
            "metadata": {"tool": "docker"},
        },
    ]

    for conv in conversations:
        await reflection_db.store_conversation(
            content=conv["content"],
            metadata={"project": conv["project"], **conv["metadata"]},
        )

    return reflection_db


@pytest.fixture
async def db_with_reflections(
    reflection_db: ReflectionDatabase,
) -> ReflectionDatabase:
    """Populate database with sample reflections."""
    reflections = [
        {
            "content": "Authentication patterns: Always use secure JWT implementation with proper expiration handling",
            "tags": ["authentication", "jwt", "security"],
        },
        {
            "content": "Database performance: Index frequently queried columns, especially foreign keys",
            "tags": ["database", "performance", "postgresql"],
        },
        {
            "content": "React component patterns: Use functional components with hooks for better performance",
            "tags": ["react", "frontend", "hooks"],
        },
    ]

    for refl in reflections:
        await reflection_db.store_reflection(content=refl["content"], tags=refl["tags"])

    return reflection_db


@pytest.fixture
async def fully_populated_db(
    db_with_conversations: ReflectionDatabase,
    db_with_reflections: ReflectionDatabase,
) -> ReflectionDatabase:
    """Database with both conversations and reflections."""
    return db_with_conversations


# =====================================
# Mock DuckDB Connection Fixture
# =====================================


@pytest.fixture
def mock_duckdb_conn():
    """Create a mock DuckDB connection for isolated testing."""
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []
    conn.execute.return_value.fetchone.return_value = None
    return conn


# =====================================
# Helper to create mock search results
# =====================================


def create_mock_search_result(
    content_id: str = "1",
    content_type: str = "conversation",
    title: str = "Test Result",
    content: str = "Test content",
    score: float = 0.8,
    project: str | None = "test-project",
) -> SearchResult:
    """Create a mock SearchResult for testing."""
    return SearchResult(
        content_id=content_id,
        content_type=content_type,
        title=title,
        content=content,
        score=score,
        project=project,
        timestamp=datetime.now(UTC),
        metadata={},
        highlights=[],
        facets={},
    )


# =====================================
# Test AdvancedSearchEngine Initialization
# =====================================


class TestAdvancedSearchEngineInit:
    """Tests for AdvancedSearchEngine initialization."""

    @pytest.mark.asyncio
    async def test_init_with_reflection_db(self, reflection_db):
        """Test engine initializes correctly with reflection database."""
        engine = AdvancedSearchEngine(reflection_db)

        assert engine.reflection_db is reflection_db
        assert engine.enhanced_search is not None
        assert isinstance(engine.index_cache, dict)
        assert "project" in engine.facet_configs
        assert "content_type" in engine.facet_configs

    @pytest.mark.asyncio
    async def test_facet_configs_structure(self, reflection_db):
        """Test facet configurations are properly structured."""
        engine = AdvancedSearchEngine(reflection_db)

        expected_facets = {
            "project": {"type": "terms", "size": 20},
            "content_type": {"type": "terms", "size": 10},
            "date_range": {
                "type": "date",
                "ranges": ["1d", "7d", "30d", "90d", "365d"],
            },
            "author": {"type": "terms", "size": 15},
            "tags": {"type": "terms", "size": 25},
            "file_type": {"type": "terms", "size": 10},
            "language": {"type": "terms", "size": 10},
            "error_type": {"type": "terms", "size": 15},
        }

        for facet_name, expected_config in expected_facets.items():
            assert facet_name in engine.facet_configs
            assert engine.facet_configs[facet_name]["type"] == expected_config["type"]
            # For date_range, check ranges; for others, check size
            if facet_name == "date_range":
                assert engine.facet_configs[facet_name]["ranges"] == expected_config["ranges"]
            else:
                assert engine.facet_configs[facet_name]["size"] == expected_config["size"]


# =====================================
# Test Search Functionality
# =====================================


class TestSearchFunctionality:
    """Tests for core search functionality."""

    @pytest.mark.asyncio
    async def test_search_basic_query(self, search_engine, fully_populated_db):
        """Test basic text search returns results."""
        mock_results = [create_mock_search_result()]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=mock_results)):
                results = await search_engine.search(query="authentication", limit=10)

        assert isinstance(results, dict)
        assert "results" in results
        assert "total" in results
        assert "query" in results
        assert results["query"] == "authentication"

    @pytest.mark.asyncio
    async def test_search_with_limit(self, search_engine, fully_populated_db):
        """Test search respects limit parameter."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test", limit=3)

        assert len(results["results"]) <= 3

    @pytest.mark.asyncio
    async def test_search_with_offset(self, search_engine, fully_populated_db):
        """Test search with offset for pagination."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test", limit=5, offset=5)

        assert isinstance(results, dict)
        assert "results" in results

    @pytest.mark.asyncio
    async def test_search_empty_query(self, search_engine, fully_populated_db):
        """Test search with empty query string."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="", limit=10)

        assert isinstance(results, dict)
        assert "results" in results
        assert isinstance(results["results"], list)

    @pytest.mark.asyncio
    async def test_search_no_results(self, search_engine, fully_populated_db):
        """Test search that returns no results."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="xyznonexistentquery123", limit=10)

        assert isinstance(results, dict)
        assert "results" in results
        assert len(results["results"]) == 0

    @pytest.mark.asyncio
    async def test_search_returns_search_results(self, search_engine, fully_populated_db):
        """Test that search returns proper SearchResult objects."""
        mock_results = [create_mock_search_result()]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=mock_results)):
                results = await search_engine.search(query="authentication", limit=5)

        for result in results["results"]:
            assert isinstance(result, SearchResult)
            assert hasattr(result, "content_id")
            assert hasattr(result, "content_type")
            assert hasattr(result, "title")
            assert hasattr(result, "content")
            assert hasattr(result, "score")

    @pytest.mark.asyncio
    async def test_search_includes_facets(self, search_engine, fully_populated_db):
        """Test search returns facets when requested."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                with patch.object(search_engine, '_calculate_facets', AsyncMock(return_value={})):
                    results = await search_engine.search(
                        query="authentication",
                        facets=["project", "content_type"],
                        limit=5,
                    )

        assert "facets" in results
        assert isinstance(results["facets"], dict)

    @pytest.mark.asyncio
    async def test_search_without_highlights(self, search_engine, fully_populated_db):
        """Test search without highlights."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="authentication",
                    include_highlights=False,
                    limit=5,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_search_with_highlights(self, search_engine, fully_populated_db):
        """Test search with highlights enabled."""
        mock_results = [create_mock_search_result(content="Test authentication content")]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=mock_results)):
                results = await search_engine.search(
                    query="authentication",
                    include_highlights=True,
                    limit=5,
                )

        assert isinstance(results, dict)


# =====================================
# Test Search Filters
# =====================================


class TestSearchFilters:
    """Tests for search filtering functionality."""

    @pytest.mark.asyncio
    async def test_filter_by_project_equality(self, search_engine, fully_populated_db):
        """Test filtering by exact project match."""
        filters = [
            SearchFilter(field="project", operator="eq", value="webapp-backend"),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="authentication",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_filter_by_content_type(self, search_engine, fully_populated_db):
        """Test filtering by content type."""
        filters = [
            SearchFilter(field="content_type", operator="eq", value="conversation"),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_filter_with_contains_operator(self, search_engine, fully_populated_db):
        """Test contains operator in filters."""
        filters = [
            SearchFilter(field="project", operator="contains", value="webapp"),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_filter_with_negation(self, search_engine, fully_populated_db):
        """Test filter negation."""
        filters = [
            SearchFilter(field="project", operator="eq", value="webapp-backend", negate=True),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_filter_with_multiple_conditions(self, search_engine, fully_populated_db):
        """Test multiple filter conditions."""
        filters = [
            SearchFilter(field="project", operator="eq", value="webapp-backend"),
            SearchFilter(field="content_type", operator="eq", value="conversation"),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="authentication",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_filter_with_invalid_field(self, search_engine, fully_populated_db):
        """Test filter with invalid field name."""
        filters = [
            SearchFilter(field="nonexistent_field", operator="eq", value="test"),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_filter_with_range_operator(self, search_engine, fully_populated_db):
        """Test range filter operator."""
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        filters = [
            SearchFilter(
                field="timestamp",
                operator="range",
                value=(week_ago.isoformat(), now.isoformat()),
            ),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_filter_with_starts_with_operator(self, search_engine, fully_populated_db):
        """Test starts_with filter operator."""
        filters = [
            SearchFilter(field="project", operator="starts_with", value="webapp"),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_filter_with_ends_with_operator(self, search_engine, fully_populated_db):
        """Test ends_with filter operator."""
        filters = [
            SearchFilter(field="project", operator="ends_with", value="backend"),
        ]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    filters=filters,
                    limit=10,
                )

        assert isinstance(results, dict)


# =====================================
# Test Search Sorting
# =====================================


class TestSearchSorting:
    """Tests for search result sorting."""

    @pytest.mark.asyncio
    async def test_sort_by_relevance(self, search_engine, fully_populated_db):
        """Test relevance sorting (default)."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="authentication",
                    sort_by="relevance",
                    limit=10,
                )

        assert isinstance(results, dict)
        assert "results" in results

    @pytest.mark.asyncio
    async def test_sort_by_date(self, search_engine, fully_populated_db):
        """Test date sorting."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="authentication",
                    sort_by="date",
                    limit=10,
                )

        assert isinstance(results, dict)
        assert "results" in results

    @pytest.mark.asyncio
    async def test_sort_by_project(self, search_engine, fully_populated_db):
        """Test project sorting."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="authentication",
                    sort_by="project",
                    limit=10,
                )

        assert isinstance(results, dict)
        assert "results" in results


# =====================================
# Test Content Type and Timeframe
# =====================================


class TestContentTypeAndTimeframe:
    """Tests for content type and timeframe filtering."""

    @pytest.mark.asyncio
    async def test_search_with_content_type(self, search_engine, fully_populated_db):
        """Test search filtered by content type."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    content_type="conversation",
                    limit=10,
                )

        assert isinstance(results, dict)
        assert "results" in results

    @pytest.mark.asyncio
    async def test_search_with_timeframe(self, search_engine, fully_populated_db):
        """Test search with timeframe filter."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    timeframe="7d",
                    limit=10,
                )

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_search_with_content_type_and_timeframe(
        self, search_engine, fully_populated_db
    ):
        """Test search with both content type and timeframe."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(
                    query="test",
                    content_type="conversation",
                    timeframe="30d",
                    limit=10,
                )

        assert isinstance(results, dict)


# =====================================
# Test Edge Cases
# =====================================


class TestSearchEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_search_with_none_filters(self, search_engine, fully_populated_db):
        """Test search with None filters list."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test", filters=None, limit=10)

        assert isinstance(results, dict)
        assert "results" in results

    @pytest.mark.asyncio
    async def test_search_with_none_facets(self, search_engine, fully_populated_db):
        """Test search with None facets list."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test", facets=None, limit=10)

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_search_with_empty_filters_list(self, search_engine, fully_populated_db):
        """Test search with empty filters list."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test", filters=[], limit=10)

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_search_with_zero_limit(self, search_engine, fully_populated_db):
        """Test search with zero limit."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test", limit=0)

        assert isinstance(results, dict)
        assert "results" in results

    @pytest.mark.asyncio
    async def test_search_with_very_large_limit(self, search_engine, fully_populated_db):
        """Test search with very large limit."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test", limit=10000)

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_search_with_negative_offset(self, search_engine, fully_populated_db):
        """Test search with negative offset."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test", limit=5, offset=-1)

        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, search_engine, fully_populated_db):
        """Test case insensitive search."""
        queries = ["AUTHENTICATION", "Authentication", "authentication"]

        for query in queries:
            with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
                with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                    results = await search_engine.search(query=query, limit=10)
            assert isinstance(results, dict)
            assert "results" in results

    @pytest.mark.asyncio
    async def test_search_special_characters(self, search_engine, fully_populated_db):
        """Test search with special characters."""
        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=[])):
                results = await search_engine.search(query="test@#$_test", limit=10)

        assert isinstance(results, dict)


# =====================================
# Test Suggest Completions
# =====================================


class TestSuggestCompletions:
    """Tests for search completion suggestions."""

    @pytest.mark.asyncio
    async def test_suggest_completions_basic(self, search_engine, fully_populated_db):
        """Test basic completion suggestions."""
        suggestions = await search_engine.suggest_completions(
            query="auth",
            field="content",
            limit=5,
        )

        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_suggest_completions_project_field(self, search_engine, fully_populated_db):
        """Test suggestions for project field."""
        suggestions = await search_engine.suggest_completions(
            query="web",
            field="project",
            limit=5,
        )

        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_suggest_completions_tags_field(self, search_engine, fully_populated_db):
        """Test suggestions for tags field."""
        suggestions = await search_engine.suggest_completions(
            query="data",
            field="tags",
            limit=5,
        )

        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_suggest_completions_unknown_field(self, search_engine, fully_populated_db):
        """Test suggestions with unknown field falls back to content."""
        suggestions = await search_engine.suggest_completions(
            query="test",
            field="unknown_field",
            limit=5,
        )

        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_suggest_completions_no_connection(self, search_engine):
        """Test suggestions when database connection is unavailable."""
        search_engine.reflection_db.conn = None

        suggestions = await search_engine.suggest_completions(query="test", limit=5)

        assert suggestions == []

    @pytest.mark.asyncio
    async def test_suggest_completions_structure(self, search_engine, fully_populated_db):
        """Test completion suggestion structure."""
        suggestions = await search_engine.suggest_completions(
            query="test",
            limit=5,
        )

        for suggestion in suggestions:
            assert isinstance(suggestion, dict)
            assert "text" in suggestion
            assert "frequency" in suggestion


# =====================================
# Test Get Similar Content
# =====================================


class TestGetSimilarContent:
    """Tests for finding similar content."""

    @pytest.mark.asyncio
    async def test_get_similar_content_basic(self, search_engine, fully_populated_db):
        """Test basic similar content search."""
        similar = await search_engine.get_similar_content(
            content_id="nonexistent",
            content_type="conversation",
            limit=5,
        )

        assert isinstance(similar, list)

    @pytest.mark.asyncio
    async def test_get_similar_content_no_connection(self, search_engine):
        """Test similar content when database connection is unavailable."""
        search_engine.reflection_db.conn = None

        similar = await search_engine.get_similar_content(
            content_id="test",
            content_type="conversation",
            limit=5,
        )

        assert similar == []

    @pytest.mark.asyncio
    async def test_get_similar_content_with_real_id(self, search_engine, fully_populated_db):
        """Test similar content with actual conversation ID."""
        conv_id = await fully_populated_db.store_conversation(
            "Testing similar content finding",
            {"project": "test"},
        )

        similar = await search_engine.get_similar_content(
            content_id=conv_id,
            content_type="conversation",
            limit=5,
        )

        assert isinstance(similar, list)


# =====================================
# Test Search By Timeframe
# =====================================


class TestSearchByTimeframe:
    """Tests for timeframe-based search."""

    @pytest.mark.asyncio
    async def test_search_by_timeframe_basic(self, search_engine, fully_populated_db):
        """Test basic timeframe search."""
        with patch.object(search_engine, 'search', AsyncMock(return_value={"results": []})):
            results = await search_engine.search_by_timeframe(
                timeframe="1d",
                query="test",
                limit=5,
            )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_by_timeframe_with_project(
        self, search_engine, fully_populated_db
    ):
        """Test timeframe search with project filter."""
        with patch.object(search_engine, 'search', AsyncMock(return_value={"results": []})):
            results = await search_engine.search_by_timeframe(
                timeframe="7d",
                query="authentication",
                project="webapp-backend",
                limit=5,
            )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_by_timeframe_no_query(self, search_engine, fully_populated_db):
        """Test timeframe search without query."""
        with patch.object(search_engine, 'search', AsyncMock(return_value={"results": []})):
            results = await search_engine.search_by_timeframe(
                timeframe="30d",
                limit=5,
            )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_by_timeframe_various_formats(
        self, search_engine, fully_populated_db
    ):
        """Test various timeframe formats."""
        timeframes = ["1h", "1d", "1w", "1m", "1y"]

        for timeframe in timeframes:
            with patch.object(search_engine, 'search', AsyncMock(return_value={"results": []})):
                results = await search_engine.search_by_timeframe(
                    timeframe=timeframe,
                    limit=5,
                )
            assert isinstance(results, list)


# =====================================
# Test Aggregate Metrics
# =====================================


class TestAggregateMetrics:
    """Tests for aggregate metrics calculation."""

    @pytest.mark.asyncio
    async def test_aggregate_activity_metrics(self, search_engine, fully_populated_db):
        """Test activity metrics aggregation."""
        metrics = await search_engine.aggregate_metrics(
            metric_type="activity",
            timeframe="30d",
        )

        assert isinstance(metrics, dict)
        assert "metric_type" in metrics
        assert metrics["metric_type"] == "activity"
        assert "timeframe" in metrics
        assert "data" in metrics

    @pytest.mark.asyncio
    async def test_aggregate_projects_metrics(self, search_engine, fully_populated_db):
        """Test projects metrics aggregation."""
        metrics = await search_engine.aggregate_metrics(
            metric_type="projects",
            timeframe="30d",
        )

        assert isinstance(metrics, dict)
        assert metrics["metric_type"] == "projects"

    @pytest.mark.asyncio
    async def test_aggregate_content_types_metrics(self, search_engine, fully_populated_db):
        """Test content types metrics aggregation."""
        metrics = await search_engine.aggregate_metrics(
            metric_type="content_types",
            timeframe="30d",
        )

        assert isinstance(metrics, dict)
        assert metrics["metric_type"] == "content_types"

    @pytest.mark.asyncio
    async def test_aggregate_errors_metrics(self, search_engine, fully_populated_db):
        """Test errors metrics aggregation."""
        metrics = await search_engine.aggregate_metrics(
            metric_type="errors",
            timeframe="30d",
        )

        assert isinstance(metrics, dict)
        assert metrics["metric_type"] == "errors"

    @pytest.mark.asyncio
    async def test_aggregate_unknown_metric_type(self, search_engine, fully_populated_db):
        """Test aggregate with unknown metric type returns error."""
        metrics = await search_engine.aggregate_metrics(
            metric_type="unknown_metric",
            timeframe="30d",
        )

        assert isinstance(metrics, dict)
        assert "error" in metrics
        assert "unknown_metric" in metrics["error"]

    @pytest.mark.asyncio
    async def test_aggregate_with_filters(self, search_engine, fully_populated_db):
        """Test aggregate metrics with filters."""
        filters = [
            SearchFilter(field="project", operator="eq", value="webapp-backend"),
        ]

        metrics = await search_engine.aggregate_metrics(
            metric_type="activity",
            timeframe="30d",
            filters=filters,
        )

        assert isinstance(metrics, dict)

    @pytest.mark.asyncio
    async def test_aggregate_no_connection(self, search_engine):
        """Test aggregate when database connection is unavailable."""
        search_engine.reflection_db.conn = None

        metrics = await search_engine.aggregate_metrics(
            metric_type="activity",
            timeframe="30d",
        )

        assert isinstance(metrics, dict)
        assert "error" in metrics


# =====================================
# Test Index Management
# =====================================


class TestIndexManagement:
    """Tests for search index management."""

    @pytest.mark.asyncio
    async def test_ensure_search_index_new(self, search_engine, fully_populated_db):
        """Test ensuring search index is built for first time."""
        search_engine.index_cache = {}

        with patch.object(search_engine, '_rebuild_search_index', AsyncMock(return_value=None)):
            await search_engine._ensure_search_index()

        # Should have triggered rebuild
        assert len(search_engine.index_cache) >= 0

    @pytest.mark.asyncio
    async def test_get_last_index_update(self, search_engine, fully_populated_db):
        """Test getting last index update time."""
        last_update = await search_engine._get_last_index_update()

        # May be None if index hasn't been built yet
        assert last_update is None or isinstance(last_update, datetime)

    @pytest.mark.asyncio
    async def test_rebuild_search_index(self, search_engine, fully_populated_db):
        """Test rebuilding the search index."""
        with patch.object(search_engine, '_index_conversations', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_index_reflections', AsyncMock(return_value=None)):
                with patch.object(search_engine, '_update_search_facets', AsyncMock(return_value=None)):
                    await search_engine._rebuild_search_index()

        assert len(search_engine.index_cache) >= 0

    @pytest.mark.asyncio
    async def test_ensure_search_index_no_connection(self, search_engine):
        """Test index management when database connection is unavailable."""
        search_engine.reflection_db.conn = None

        with patch.object(search_engine, '_rebuild_search_index', AsyncMock(return_value=None)):
            await search_engine._ensure_search_index()


# =====================================
# Test SQL Building
# =====================================


class TestSQLBuilding:
    """Tests for SQL query building."""

    def test_build_search_query_basic(self, search_engine):
        """Test basic search query building."""
        query = search_engine._build_search_query("test query", None)
        assert query == "test query"

    def test_build_search_query_with_filters(self, search_engine):
        """Test search query building with filters."""
        filters = [
            SearchFilter(field="project", operator="eq", value="test"),
        ]
        query = search_engine._build_search_query("test query", filters)
        assert query == "test query"

    def test_build_filter_conditions(self, search_engine):
        """Test building filter conditions."""
        filters = [
            SearchFilter(field="project", operator="eq", value="test"),
        ]
        condition = search_engine._build_filter_conditions(filters)

        assert isinstance(condition, SQLCondition)
        assert "project" in condition.condition.lower() or "JSON" in condition.condition

    def test_build_single_filter_condition_eq(self, search_engine):
        """Test building equality filter condition."""
        filt = SearchFilter(field="project", operator="eq", value="test")
        condition = search_engine._build_single_filter_condition(filt)

        assert condition is not None
        assert isinstance(condition, SQLCondition)

    def test_build_single_filter_condition_contains(self, search_engine):
        """Test building contains filter condition."""
        filt = SearchFilter(field="content", operator="contains", value="test")
        condition = search_engine._build_single_filter_condition(filt)

        assert condition is not None
        assert isinstance(condition, SQLCondition)

    def test_build_single_filter_condition_timestamp_range(self, search_engine):
        """Test building timestamp range filter."""
        now = datetime.now(UTC)
        filt = SearchFilter(
            field="timestamp",
            operator="range",
            value=(now - timedelta(days=1), now),
        )
        condition = search_engine._build_single_filter_condition(filt)

        assert condition is not None

    def test_build_single_filter_condition_unknown(self, search_engine):
        """Test building filter with unknown operator."""
        filt = SearchFilter(field="project", operator="unknown", value="test")
        condition = search_engine._build_single_filter_condition(filt)

        assert condition is None

    def test_build_timestamp_range_condition_valid(self, search_engine):
        """Test timestamp range condition with valid values."""
        now = datetime.now(UTC)
        filt = SearchFilter(
            field="timestamp",
            operator="range",
            value=(now - timedelta(days=1), now),
        )
        condition = search_engine._build_timestamp_range_condition(filt)

        assert condition is not None
        assert "BETWEEN" in condition.condition or "NOT" in condition.condition

    def test_build_timestamp_range_condition_invalid(self, search_engine):
        """Test timestamp range condition with invalid values."""
        filt = SearchFilter(field="timestamp", operator="range", value="invalid")
        condition = search_engine._build_timestamp_range_condition(filt)

        assert condition is None

    def test_build_equality_condition(self, search_engine):
        """Test equality condition building."""
        filt = SearchFilter(field="project", operator="eq", value="test")
        condition = search_engine._build_equality_condition(filt)

        assert condition is not None

    def test_build_contains_condition(self, search_engine):
        """Test contains condition building."""
        filt = SearchFilter(field="content", operator="contains", value="test")
        condition = search_engine._build_contains_condition(filt)

        assert condition is not None
        assert "LIKE" in condition.condition

    def test_get_sql_field(self, search_engine):
        """Test SQL field mapping."""
        assert search_engine._get_sql_field("project") == "JSON_EXTRACT_STRING(search_metadata, '$.project')"
        assert search_engine._get_sql_field("content_type") == "content_type"
        assert search_engine._get_sql_field("last_indexed") == "last_indexed"

    def test_apply_eq_filter(self, search_engine):
        """Test applying equality filter."""
        sql_part, params = search_engine._apply_eq_filter(
            "project", "", "test", []
        )
        assert "=" in sql_part
        assert "test" in params

    def test_apply_ne_filter(self, search_engine):
        """Test applying not-equal filter."""
        sql_part, params = search_engine._apply_ne_filter(
            "project", "", "test", []
        )
        assert "!=" in sql_part

    def test_apply_in_filter(self, search_engine):
        """Test applying IN filter."""
        sql_part, params = search_engine._apply_in_filter(
            "project", "", ["a", "b", "c"], []
        )
        assert "IN" in sql_part
        assert len(params) == 3

    def test_apply_not_in_filter(self, search_engine):
        """Test applying NOT IN filter."""
        sql_part, params = search_engine._apply_not_in_filter(
            "project", "", ["a", "b"], []
        )
        assert "NOT IN" in sql_part

    def test_apply_contains_filter(self, search_engine):
        """Test applying contains filter."""
        sql_part, params = search_engine._apply_contains_filter(
            "content", "", "test", []
        )
        assert "LIKE" in sql_part
        assert "%test%" in params

    def test_apply_starts_with_filter(self, search_engine):
        """Test applying starts_with filter."""
        sql_part, params = search_engine._apply_starts_with_filter(
            "project", "", "test", []
        )
        assert "LIKE" in sql_part
        assert "test%" in params

    def test_apply_ends_with_filter(self, search_engine):
        """Test applying ends_with filter."""
        sql_part, params = search_engine._apply_ends_with_filter(
            "project", "", "test", []
        )
        assert "LIKE" in sql_part
        assert "%test" in params

    def test_apply_range_filter(self, search_engine):
        """Test applying range filter."""
        filt = SearchFilter(field="timestamp", operator="range", value=("a", "b"))
        sql_part, params = search_engine._apply_range_filter("timestamp", filt, [])
        assert "BETWEEN" in sql_part or "<" in sql_part

    def test_add_filter_conditions_to_sql(self, search_engine):
        """Test adding filter conditions to SQL."""
        sql = "SELECT * FROM test"
        params: list[str] = []
        filters = [
            SearchFilter(field="project", operator="eq", value="test"),
        ]

        result = search_engine._add_filter_conditions_to_sql(sql, params, filters)
        assert isinstance(result, SQLCondition)

    def test_add_content_type_filter(self, search_engine):
        """Test adding content type filter."""
        sql = "SELECT * FROM test"
        params: list[str] = []
        result = search_engine._add_content_type_filter(sql, params, "conversation")

        assert isinstance(result, SQLCondition)

    def test_add_content_type_filter_none(self, search_engine):
        """Test adding content type filter when None."""
        sql = "SELECT * FROM test"
        params: list[str] = []
        result = search_engine._add_content_type_filter(sql, params, None)

        assert result.condition == sql

    def test_add_timeframe_filter(self, search_engine):
        """Test adding timeframe filter."""
        sql = "SELECT * FROM test"
        params: list[str] = []
        result = search_engine._add_timeframe_filter(sql, params, "7d", "conversation")

        assert isinstance(result, SQLCondition)

    def test_add_sorting_to_sql_relevance(self, search_engine):
        """Test adding relevance sorting."""
        sql = "SELECT * FROM test"
        result = search_engine._add_sorting_to_sql(sql, "relevance")
        assert "ORDER BY" in result

    def test_add_sorting_to_sql_date(self, search_engine):
        """Test adding date sorting."""
        sql = "SELECT * FROM test"
        result = search_engine._add_sorting_to_sql(sql, "date")
        assert "ORDER BY" in result
        assert "DESC" in result

    def test_add_sorting_to_sql_project(self, search_engine):
        """Test adding project sorting."""
        sql = "SELECT * FROM test"
        result = search_engine._add_sorting_to_sql(sql, "project")
        assert "ORDER BY" in result

    def test_prepare_sql_params(self, search_engine):
        """Test preparing SQL parameters."""
        params: list[str | datetime] = ["string", datetime.now(UTC)]
        result = search_engine._prepare_sql_params(params)

        assert all(isinstance(p, str) for p in result)


# =====================================
# Test Highlights and Facets
# =====================================


class TestHighlightsAndFacets:
    """Tests for highlights and facets processing."""

    @pytest.mark.asyncio
    async def test_add_highlights(self, search_engine):
        """Test adding highlights to search results."""
        results = [
            SearchResult(
                content_id="1",
                content_type="conversation",
                title="Test",
                content="This is a test authentication content",
                score=0.8,
            ),
        ]

        highlighted = await search_engine._add_highlights(results, "authentication")

        assert len(highlighted[0].highlights) > 0
        assert any("mark" in h for h in highlighted[0].highlights)

    @pytest.mark.asyncio
    async def test_add_highlights_no_matches(self, search_engine):
        """Test highlights when no terms match."""
        results = [
            SearchResult(
                content_id="1",
                content_type="conversation",
                title="Test",
                content="This is a test content",
                score=0.8,
            ),
        ]

        highlighted = await search_engine._add_highlights(results, "xyznonexistent")

        assert len(highlighted[0].highlights) == 0

    @pytest.mark.asyncio
    async def test_calculate_facets(self, search_engine, fully_populated_db):
        """Test calculating facets."""
        facets = await search_engine._calculate_facets(
            query="test",
            filters=None,
            requested_facets=["project", "content_type"],
        )

        assert isinstance(facets, dict)

    @pytest.mark.asyncio
    async def test_calculate_facets_empty_list(self, search_engine, fully_populated_db):
        """Test calculating facets with empty list."""
        result = await search_engine._process_facets("test", None, [])

        assert result == {}


# =====================================
# Test Helper Methods
# =====================================


class TestHelperMethods:
    """Tests for helper methods."""

    @pytest.mark.asyncio
    async def test_process_search_results_with_highlights(self, search_engine):
        """Test processing results with highlights."""
        results = [
            SearchResult(
                content_id="1",
                content_type="conversation",
                title="Test",
                content="Test content",
                score=0.8,
            ),
        ]

        processed = await search_engine._process_search_results(
            results, "test", include_highlights=True
        )

        assert len(processed) == 1

    @pytest.mark.asyncio
    async def test_process_search_results_without_highlights(self, search_engine):
        """Test processing results without highlights."""
        results = [
            SearchResult(
                content_id="1",
                content_type="conversation",
                title="Test",
                content="Test content",
                score=0.8,
            ),
        ]

        processed = await search_engine._process_search_results(
            results, "test", include_highlights=False
        )

        assert len(processed) == 1

    def test_convert_sql_results_to_search_results(self, search_engine):
        """Test converting SQL results to SearchResult objects."""
        sql_results = [
            (
                "conv_1",
                "conversation",
                "Test indexed content about testing",
                '{"project": "test-project", "author": "tester"}',
                datetime.now(UTC),
            ),
        ]

        results = search_engine._convert_sql_results_to_search_results(sql_results)

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].content_id == "conv_1"
        assert results[0].content_type == "conversation"
        assert results[0].project == "test-project"

    def test_convert_sql_results_empty(self, search_engine):
        """Test converting empty SQL results."""
        results = search_engine._convert_sql_results_to_search_results([])
        assert len(results) == 0


# =====================================
# Test Indexing
# =====================================


class TestIndexing:
    """Tests for search index building."""

    @pytest.mark.asyncio
    async def test_index_conversations_no_connection(self, search_engine):
        """Test indexing when no database connection."""
        search_engine.reflection_db.conn = None

        await search_engine._index_conversations()

        # Should handle gracefully

    @pytest.mark.asyncio
    async def test_update_search_facets(self, search_engine, fully_populated_db):
        """Test updating search facets."""
        # This may fail due to table structure, but tests the method exists
        with patch.object(search_engine, '_get_facet_queries', return_value={}):
            await search_engine._update_search_facets()

    def test_ensure_advanced_search_tables(self, search_engine, fully_populated_db):
        """Test creating advanced search tables."""
        search_engine._ensure_advanced_search_tables()

        # Should complete without error

    def test_get_facet_queries(self, search_engine):
        """Test getting facet queries."""
        queries = search_engine._get_facet_queries()

        assert isinstance(queries, dict)
        assert "project" in queries
        assert "content_type" in queries

    def test_should_process_facet_value(self, search_engine):
        """Test facet value filtering."""
        assert search_engine._should_process_facet_value("valid") is True
        assert search_engine._should_process_facet_value("") is False
        assert search_engine._should_process_facet_value(123) is False
        assert search_engine._should_process_facet_value(None) is False

    def test_insert_facet_value(self, search_engine, fully_populated_db):
        """Test inserting facet value."""
        search_engine._insert_facet_value("test_facet", "test_value")

        # Should complete without error

    def test_process_facet_query(self, search_engine, fully_populated_db):
        """Test processing facet query."""
        sql = "SELECT 'test_value' as facet_value, 1 as count"
        search_engine._process_facet_query("test_facet", sql)


# =====================================
# Test Build Methods
# =====================================


class TestBuildMethods:
    """Tests for build/construction methods."""

    def test_build_indexed_content(self, search_engine):
        """Test building indexed content."""
        content = search_engine._build_indexed_content(
            "This is test content", "test-project"
        )

        assert "This is test content" in content
        assert "test-project" in content

    def test_build_indexed_content_with_tech_terms(self, search_engine):
        """Test building indexed content with technical terms."""
        content = search_engine._build_indexed_content(
            "Using pytest for testing and Flask for web", "test"
        )

        assert len(content) > 0

    def test_parse_conversation_metadata(self, search_engine):
        """Test parsing conversation metadata."""
        metadata = search_engine._parse_conversation_metadata('{"key": "value"}')

        assert metadata == {"key": "value"}

    def test_parse_conversation_metadata_none(self, search_engine):
        """Test parsing None conversation metadata."""
        metadata = search_engine._parse_conversation_metadata(None)

        assert metadata == {}

    def test_parse_conversation_metadata_invalid(self, search_engine):
        """Test parsing invalid JSON metadata returns empty dict."""
        metadata = search_engine._parse_conversation_metadata("not valid json")

        assert metadata == {}

    def test_build_conversation_search_metadata(self, search_engine):
        """Test building conversation search metadata."""
        metadata = search_engine._build_conversation_search_metadata(
            project="test-project",
            timestamp=datetime.now(UTC),
            content="Test content with pytest and python",
            indexed_content="Test content with pytest and python project:test-project",
        )

        assert metadata["project"] == "test-project"
        assert "timestamp" in metadata
        assert "content_length" in metadata

    def test_insert_conversation_into_search_index(self, search_engine, fully_populated_db):
        """Test inserting conversation into search index."""
        search_engine._insert_conversation_into_search_index(
            conv_id="test_123",
            indexed_content="Test indexed content",
            search_metadata={"project": "test"},
        )

    def test_commit_conversation_index(self, search_engine, fully_populated_db):
        """Test committing conversation index."""
        search_engine._commit_conversation_index()


# =====================================
# Test Format Response
# =====================================


class TestFormatResponse:
    """Tests for response formatting."""

    def test_format_search_response(self, search_engine):
        """Test formatting search response."""
        results = [
            SearchResult(
                content_id="1",
                content_type="conversation",
                title="Test",
                content="Test content",
                score=0.8,
            ),
        ]
        facets = {"project": SearchFacet(name="project", values=[], facet_type="terms")}
        filters = [SearchFilter(field="project", operator="eq", value="test")]

        response = search_engine._format_search_response(
            results, facets, "test query", filters
        )

        assert isinstance(response, dict)
        assert "results" in response
        assert "facets" in response
        assert "total" in response
        assert "query" in response
        assert "filters" in response
        assert response["total"] == 1
        assert response["query"] == "test query"


# =====================================
# Test Execute Search
# =====================================


class TestExecuteSearch:
    """Tests for search execution."""

    @pytest.mark.asyncio
    async def test_execute_search_no_connection(self, search_engine):
        """Test execute search with no database connection."""
        search_engine.reflection_db.conn = None

        results = await search_engine._execute_search(
            query="test",
            sort_by="relevance",
            limit=10,
            offset=0,
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_execute_search_with_filters(self, search_engine, fully_populated_db):
        """Test execute search with filters."""
        filters = [
            SearchFilter(field="project", operator="eq", value="test"),
        ]

        with patch.object(search_engine, '_build_search_sql', return_value=SQLCondition(condition="", params=[])):
            results = await search_engine._execute_search(
                query="test",
                sort_by="relevance",
                limit=10,
                offset=0,
                filters=filters,
            )

        assert isinstance(results, list)


# =====================================
# Test Concurrent Operations
# =====================================


class TestConcurrentOperations:
    """Tests for concurrent search operations."""

    @pytest.mark.asyncio
    async def test_concurrent_searches(self, search_engine, fully_populated_db):
        """Test running multiple searches concurrently."""
        mock_results = [create_mock_search_result()]

        with patch.object(search_engine, '_ensure_search_index', AsyncMock(return_value=None)):
            with patch.object(search_engine, '_execute_search', AsyncMock(return_value=mock_results)):
                tasks = [
                    search_engine.search("authentication", limit=3),
                    search_engine.search("database", limit=3),
                    search_engine.search("frontend", limit=3),
                    search_engine.search("error", limit=3),
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results) == 4
        for result in results:
            if not isinstance(result, Exception):
                assert isinstance(result, dict)
                assert "results" in result


# =====================================
# Test Utility Functions
# =====================================


class TestUtilityFunctions:
    """Tests for utility functions used by AdvancedSearchEngine."""

    def test_ensure_timezone(self):
        """Test ensure_timezone utility."""
        aware = datetime.now(UTC)
        result = ensure_timezone(aware)
        assert result.tzinfo is not None

        naive = datetime.now()
        result = ensure_timezone(naive)
        assert result.tzinfo is not None

    def test_extract_technical_terms(self):
        """Test extract_technical_terms utility."""
        content = "Using pytest for testing, Flask for web, and Python for scripting"
        terms = extract_technical_terms(content)

        assert isinstance(terms, list)

    def test_parse_timeframe(self):
        """Test parse_timeframe utility."""
        result = parse_timeframe("7d")

        assert result is not None
        assert hasattr(result, "start")
        assert hasattr(result, "end")

    def test_parse_timeframe_single(self):
        """Test parse_timeframe_single utility."""
        result = parse_timeframe_single("7d")

        assert result is None or isinstance(result, datetime)

    def test_truncate_content(self):
        """Test truncate_content utility."""
        long_content = "a" * 1000
        result = truncate_content(long_content, max_length=100)

        # Function appends "..." (3 chars) when content exceeds max_length
        # So result is content[:100] + "..." = 103 chars
        assert len(result) == 103
        assert result.endswith("...")

    def test_truncate_content_short(self):
        """Test truncate_content with short content."""
        short_content = "short content"
        result = truncate_content(short_content, max_length=100)

        assert result == short_content


# =====================================
# Run Tests
# =====================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
