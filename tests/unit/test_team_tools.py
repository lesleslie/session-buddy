"""Unit tests for team collaboration tools."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.collaboration import team_tools as module


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_db_path() -> Path:
    """Create temporary database path."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_team.db"


@pytest.fixture
def mock_manager(temp_db_path: Path) -> MagicMock:
    """Create mock TeamKnowledgeManager."""
    manager = MagicMock()
    manager.db_path = str(temp_db_path)
    return manager


@pytest.fixture
def sample_team_data() -> dict:
    """Sample team data for tests."""
    return {
        "team_id": "team-123",
        "name": "Test Team",
        "description": "A team for testing",
        "owner_id": "user-001",
    }


@pytest.fixture
def sample_stats_data() -> dict:
    """Sample statistics data."""
    return {
        "member_count": 3,
        "reflection_count": 15,
        "project_count": 2,
        "total_votes": 42,
        "recent_activity": [
            {"timestamp": "2026-05-24T10:00:00", "description": "New reflection added"},
            {"timestamp": "2026-05-23T15:30:00", "description": "Team member joined"},
        ],
        "top_contributors": [
            {"username": "alice", "contributions": 10},
            {"username": "bob", "contributions": 5},
        ],
        "popular_tags": ["python", "testing", "collab"],
    }


# ============================================================================
# Test: _require_team_manager
# ============================================================================


class TestRequireTeamManager:
    """Tests for _require_team_manager function."""

    @pytest.mark.asyncio
    async def test_returns_manager_when_available(self) -> None:
        """Test that manager is returned when import succeeds."""
        with patch.object(module, "_get_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            with patch("session_buddy.team_knowledge.TeamKnowledgeManager") as MockManager:
                mock_manager_instance = MagicMock()
                MockManager.return_value = mock_manager_instance
                result = await module._require_team_manager()
                assert result is mock_manager_instance

    @pytest.mark.asyncio
    async def test_raises_runtime_when_not_available(self) -> None:
        """Test that RuntimeError is raised when TeamKnowledgeManager unavailable."""
        with patch.object(module, "_get_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            # Simulate import failure by making the import raise ImportError
            with patch.dict("sys.modules", {"session_buddy.team_knowledge": None}):
                with pytest.raises(RuntimeError) as exc_info:
                    await module._require_team_manager()
                assert "not available" in str(exc_info.value)


# ============================================================================
# Test: _execute_team_operation
# ============================================================================


class TestExecuteTeamOperation:
    """Tests for _execute_team_operation function."""

    @pytest.mark.asyncio
    async def test_successful_operation(self) -> None:
        """Test successful operation execution."""
        mock_operation = AsyncMock(return_value="success")

        with patch.object(module, "_require_team_manager", AsyncMock(return_value=MagicMock())):
            result = await module._execute_team_operation("TestOp", mock_operation)
            assert result == "success"

    @pytest.mark.asyncio
    async def test_runtime_error_handling(self) -> None:
        """Test RuntimeError is caught and formatted."""
        async def failing_op(manager):
            raise RuntimeError("Service not available")

        result = await module._execute_team_operation("TestOp", failing_op)
        assert "❌" in result

    @pytest.mark.asyncio
    async def test_value_error_handling(self) -> None:
        """Test ValueError is caught and formatted."""
        async def failing_op(manager):
            raise ValueError("Invalid input")

        with patch.object(module, "_require_team_manager", AsyncMock(return_value=MagicMock())):
            result = await module._execute_team_operation("TestOp", failing_op)
            assert "❌" in result
            assert "Invalid input" in result

    @pytest.mark.asyncio
    async def test_generic_exception_handling(self) -> None:
        """Test generic Exception is caught and logged."""
        async def failing_op(manager):
            raise Exception("Unexpected error")

        with patch.object(module, "_require_team_manager", AsyncMock(return_value=MagicMock())):
            with patch.object(module, "_get_logger") as mock_logger:
                result = await module._execute_team_operation("TestOp", failing_op)
                assert "failed" in result.lower() or "❌" in result


# ============================================================================
# Test: Formatting Helpers
# ============================================================================


class TestFormattingHelpers:
    """Tests for output formatting helper functions."""

    def test_format_search_result_basic(self) -> None:
        """Test basic search result formatting."""
        result = {
            "team_id": "team-123",
            "author": "alice",
            "timestamp": "2026-05-24",
            "content": "Test content here",
            "tags": ["test", "example"],
            "votes": 5,
        }
        output = module._format_search_result(result, 1)
        assert "**1.**" in output
        assert "[team-123]" in output
        assert "by alice" in output
        assert "Test content here" in output

    def test_format_search_result_without_optional_fields(self) -> None:
        """Test formatting result with missing optional fields."""
        result = {"content": "Minimal content"}
        output = module._format_search_result(result, 2)
        assert "**2.**" in output
        assert "Minimal content" in output

    def test_format_search_scope_team_only(self) -> None:
        """Test search scope formatting with team only."""
        output = module._format_search_scope("team-123", None)
        assert "team: team-123" in output

    def test_format_search_scope_project_only(self) -> None:
        """Test search scope formatting with project only."""
        output = module._format_search_scope(None, "proj-456")
        assert "project: proj-456" in output

    def test_format_search_scope_both(self) -> None:
        """Test search scope formatting with both team and project."""
        output = module._format_search_scope("team-123", "proj-456")
        assert "team: team-123" in output
        assert "project: proj-456" in output

    def test_format_basic_stats(self, sample_stats_data: dict) -> None:
        """Test basic statistics formatting."""
        output = module._format_basic_stats(sample_stats_data)
        assert "**Members**: 3" in output
        assert "**Reflections**: 15" in output
        assert "**Projects**: 2" in output
        assert "**Total Votes**: 42" in output

    def test_format_basic_stats_empty(self) -> None:
        """Test basic stats with missing values."""
        stats = {}
        output = module._format_basic_stats(stats)
        assert "**Members**: 0" in output
        assert "**Reflections**: 0" in output

    def test_format_activity_stats(self, sample_stats_data: dict) -> None:
        """Test activity statistics formatting."""
        output = module._format_activity_stats(sample_stats_data)
        assert "**Recent Activity**:" in output
        assert "New reflection added" in output

    def test_format_activity_stats_empty(self) -> None:
        """Test activity stats with no recent activity."""
        stats = {"recent_activity": []}
        output = module._format_activity_stats(stats)
        assert output == ""

    def test_format_contributor_stats(self, sample_stats_data: dict) -> None:
        """Test contributor statistics formatting."""
        output = module._format_contributor_stats(sample_stats_data)
        assert "**Top Contributors**:" in output
        assert "alice: 10 contributions" in output
        assert "bob: 5 contributions" in output

    def test_format_contributor_stats_empty(self) -> None:
        """Test contributor stats with no contributors."""
        stats = {"top_contributors": []}
        output = module._format_contributor_stats(stats)
        assert output == ""

    def test_format_popular_tags(self, sample_stats_data: dict) -> None:
        """Test popular tags formatting."""
        output = module._format_popular_tags(sample_stats_data)
        assert "**Popular Tags**:" in output
        assert "python" in output

    def test_format_popular_tags_empty(self) -> None:
        """Test popular tags with no tags."""
        stats = {"popular_tags": []}
        output = module._format_popular_tags(stats)
        assert output == ""

    def test_format_team_statistics(self, sample_stats_data: dict) -> None:
        """Test complete team statistics formatting."""
        output = module._format_team_statistics("team-123", sample_stats_data)
        assert "📊 **Team Statistics: team-123**" in output
        assert "**Members**: 3" in output
        assert "**Recent Activity**:" in output
        assert "**Top Contributors**:" in output
        assert "**Popular Tags**:" in output


# ============================================================================
# Test: Team Operation Implementations
# ============================================================================


class TestCreateTeamOperation:
    """Tests for _create_team_operation."""

    @pytest.mark.asyncio
    async def test_creates_team_successfully(self, mock_manager: MagicMock, sample_team_data: dict) -> None:
        """Test successful team creation."""
        mock_manager.create_team = AsyncMock(return_value=MagicMock(
            team_id=sample_team_data["team_id"],
            name=sample_team_data["name"],
        ))

        result = await module._create_team_operation(
            mock_manager,
            sample_team_data["team_id"],
            sample_team_data["name"],
            sample_team_data["description"],
            sample_team_data["owner_id"],
        )
        mock_manager.create_team.assert_called_once()
        assert "✅" in result
        assert sample_team_data["name"] in result


class TestGetTeamStatisticsOperation:
    """Tests for _get_team_statistics_operation."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, mock_manager: MagicMock, sample_stats_data: dict) -> None:
        """Test successful statistics retrieval."""
        mock_manager.get_team_stats = AsyncMock(return_value=sample_stats_data)

        result = await module._get_team_statistics_operation(
            mock_manager,
            "team-123",
            "user-001",
        )

        mock_manager.get_team_stats.assert_called_once_with(team_id="team-123", user_id="user-001")
        assert "📊 **Team Statistics: team-123**" in result

    @pytest.mark.asyncio
    async def test_get_stats_returns_none(self, mock_manager: MagicMock) -> None:
        """Test statistics retrieval when no data."""
        mock_manager.get_team_stats = AsyncMock(return_value=None)

        result = await module._get_team_statistics_operation(
            mock_manager,
            "team-123",
            "user-001",
        )

        assert "❌" in result


class TestVoteOnReflectionOperation:
    """Tests for _vote_on_reflection_operation."""

    @pytest.mark.asyncio
    async def test_vote_success(self, mock_manager: MagicMock) -> None:
        """Test successful vote."""
        mock_manager.vote_reflection = AsyncMock(return_value=True)

        result = await module._vote_on_reflection_operation(
            mock_manager,
            "ref-123",
            "user-001",
            1,
        )

        mock_manager.vote_reflection.assert_called_once_with(
            reflection_id="ref-123",
            user_id="user-001",
            vote_delta=1,
        )
        assert "✅" in result

    @pytest.mark.asyncio
    async def test_vote_failure(self, mock_manager: MagicMock) -> None:
        """Test failed vote."""
        mock_manager.vote_reflection = AsyncMock(return_value=False)

        result = await module._vote_on_reflection_operation(
            mock_manager,
            "ref-123",
            "user-001",
            1,
        )

        assert "❌" in result

    @pytest.mark.asyncio
    async def test_vote_downvote(self, mock_manager: MagicMock) -> None:
        """Test downvote."""
        mock_manager.vote_reflection = AsyncMock(return_value=True)

        result = await module._vote_on_reflection_operation(
            mock_manager,
            "ref-123",
            "user-001",
            -1,
        )

        mock_manager.vote_reflection.assert_called_once_with(
            reflection_id="ref-123",
            user_id="user-001",
            vote_delta=-1,
        )


class TestSearchTeamKnowledgeOperation:
    """Tests for _search_team_knowledge_operation."""

    @pytest.mark.asyncio
    async def test_search_with_results(self, mock_manager: MagicMock) -> None:
        """Test search with results."""
        mock_results = [
            {
                "team_id": "team-123",
                "author": "alice",
                "timestamp": "2026-05-24",
                "content": "Test reflection",
                "tags": ["test"],
                "votes": 5,
            }
        ]
        mock_manager.search_team_reflections = AsyncMock(return_value=mock_results)

        result = await module._search_team_knowledge_operation(
            mock_manager,
            "test query",
            "user-001",
            "team-123",
            None,
            None,
            20,
        )

        assert "🔍" in result
        assert "1 team knowledge results" in result
        assert "Test reflection" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, mock_manager: MagicMock) -> None:
        """Test search with no results."""
        mock_manager.search_team_reflections = AsyncMock(return_value=[])

        result = await module._search_team_knowledge_operation(
            mock_manager,
            "nonexistent",
            "user-001",
            "team-123",
            None,
            None,
            20,
        )

        assert "🔍" in result
        assert "No results found" in result


# ============================================================================
# Test: Public Implementation Functions
# ============================================================================


class TestCreateTeamImpl:
    """Tests for _create_team_impl."""

    @pytest.mark.asyncio
    async def test_create_team_impl_success(self, sample_team_data: dict) -> None:
        """Test successful team creation via impl."""
        with patch.object(module, "_execute_team_operation", AsyncMock(return_value="✅ Team created")):
            result = await module._create_team_impl(
                sample_team_data["team_id"],
                sample_team_data["name"],
                sample_team_data["description"],
                sample_team_data["owner_id"],
            )
            assert result == "✅ Team created"


class TestGetTeamStatisticsImpl:
    """Tests for _get_team_statistics_impl."""

    @pytest.mark.asyncio
    async def test_get_team_statistics_impl_success(self) -> None:
        """Test successful stats retrieval via impl."""
        with patch.object(module, "_execute_team_operation", AsyncMock(return_value="📊 stats")):
            result = await module._get_team_statistics_impl("team-123", "user-001")
            assert result == "📊 stats"


class TestVoteOnReflectionImpl:
    """Tests for _vote_on_reflection_impl."""

    @pytest.mark.asyncio
    async def test_vote_on_reflection_impl_success(self) -> None:
        """Test successful vote via impl."""
        with patch.object(module, "_execute_team_operation", AsyncMock(return_value="✅ voted")):
            result = await module._vote_on_reflection_impl("ref-123", "user-001", 1)
            assert result == "✅ voted"


class TestSearchTeamKnowledgeImpl:
    """Tests for _search_team_knowledge_impl."""

    @pytest.mark.asyncio
    async def test_search_team_knowledge_impl_success(self) -> None:
        """Test successful search via impl."""
        with patch.object(module, "_execute_team_operation", AsyncMock(return_value="🔍 results")):
            result = await module._search_team_knowledge_impl(
                "test query",
                "user-001",
                "team-123",
                None,
                None,
                20,
            )
            assert result == "🔍 results"


# ============================================================================
# Test: MCP Tool Registration
# ============================================================================


class TestRegisterTeamTools:
    """Tests for register_team_tools function."""

    def test_registers_all_four_tools(self) -> None:
        """Test that all 4 tools are registered."""
        mock_mcp = MagicMock()
        mock_mcp.tool = MagicMock(return_value=lambda f: f)

        module.register_team_tools(mock_mcp)

        # Should have 4 @mcp.tool() decorators applied
        assert mock_mcp.tool.call_count == 4

    def test_create_team_tool_signature(self) -> None:
        """Test create_team tool has correct signature."""
        mock_mcp = MagicMock()

        registered_tools = []

        def capture_tool():
            def decorator(func):
                registered_tools.append(func)
                return func
            return decorator

        mock_mcp.tool = capture_tool

        module.register_team_tools(mock_mcp)

        # Find create_team function
        create_team_fn = next((t for t in registered_tools if t.__name__ == "create_team"), None)
        assert create_team_fn is not None

        # Check parameters - should have team_id, name, description, owner_id
        import inspect
        sig = inspect.signature(create_team_fn)
        params = list(sig.parameters.keys())
        assert "team_id" in params
        assert "name" in params
        assert "description" in params
        assert "owner_id" in params

    def test_vote_on_reflection_tool_signature(self) -> None:
        """Test vote_on_reflection tool has correct signature."""
        mock_mcp = MagicMock()

        registered_tools = []

        def capture_tool():
            def decorator(func):
                registered_tools.append(func)
                return func
            return decorator

        mock_mcp.tool = capture_tool

        module.register_team_tools(mock_mcp)

        # Find vote_on_reflection function
        vote_fn = next((t for t in registered_tools if t.__name__ == "vote_on_reflection"), None)
        assert vote_fn is not None

        import inspect
        sig = inspect.signature(vote_fn)
        params = list(sig.parameters.keys())
        assert "reflection_id" in params
        assert "user_id" in params
        assert "vote_delta" in params

    def test_get_team_statistics_tool_signature(self) -> None:
        """Test get_team_statistics tool has correct signature."""
        mock_mcp = MagicMock()

        registered_tools = []

        def capture_tool():
            def decorator(func):
                registered_tools.append(func)
                return func
            return decorator

        mock_mcp.tool = capture_tool

        module.register_team_tools(mock_mcp)

        # Find get_team_statistics function
        stats_fn = next((t for t in registered_tools if t.__name__ == "get_team_statistics"), None)
        assert stats_fn is not None

        import inspect
        sig = inspect.signature(stats_fn)
        params = list(sig.parameters.keys())
        assert "team_id" in params
        assert "user_id" in params

    def test_search_team_knowledge_tool_signature(self) -> None:
        """Test search_team_knowledge tool has correct signature."""
        mock_mcp = MagicMock()

        registered_tools = []

        def capture_tool():
            def decorator(func):
                registered_tools.append(func)
                return func
            return decorator

        mock_mcp.tool = capture_tool

        module.register_team_tools(mock_mcp)

        # Find search_team_knowledge function
        search_fn = next((t for t in registered_tools if t.__name__ == "search_team_knowledge"), None)
        assert search_fn is not None

        import inspect
        sig = inspect.signature(search_fn)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "user_id" in params
        assert "team_id" in params
        assert "project_id" in params
        assert "tags" in params
        assert "limit" in params


# ============================================================================
# Test: Error Message Constants
# ============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_team_not_available_msg_content(self) -> None:
        """Test TEAM_NOT_AVAILABLE_MSG constant."""
        assert "Team collaboration features not available" in module.TEAM_NOT_AVAILABLE_MSG
