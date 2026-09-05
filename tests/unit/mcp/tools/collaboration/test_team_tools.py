"""Tests for session_buddy.mcp.tools.collaboration.team_tools.

Covers the 4 MCP tools (``create_team``, ``search_team_knowledge``,
``get_team_statistics``, ``vote_on_reflection``), the formatting
helpers, the per-operation impls, and the registration entry point.

Targets:
- ``_format_search_result``: with/without metadata, tags, votes
- ``_format_search_scope``: only team, only project, both, neither
- ``_format_basic_stats``: default zero values
- ``_format_activity_stats``: empty list, populated list (truncated to 5)
- ``_format_contributor_stats``: empty, populated (truncated to 5)
- ``_format_popular_tags``: empty, populated (truncated to 10)
- ``_format_team_statistics``: composes all of the above
- ``_create_team_operation`` / ``_create_team_impl``: happy path, kwargs
  forwarding, error envelope (RuntimeError, generic exception)
- ``_search_team_knowledge_operation`` / ``_search_team_knowledge_impl``:
  no results, results, kwargs forwarding, error envelope
- ``_get_team_statistics_operation`` / ``_get_team_statistics_impl``:
  None stats, populated stats, error envelope
- ``_vote_on_reflection_operation`` / ``_vote_on_reflection_impl``:
  success (truthy result), failure (falsy result), error envelope
- ``register_team_tools``: registers all 4 tools

Test approach: monkeypatch ``_require_team_manager`` to return an
``AsyncMock`` manager with AsyncMock methods.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.collaboration import team_tools as tt
from session_buddy.mcp.tools.collaboration.team_tools import (
    _create_team_impl,
    _create_team_operation,
    _execute_team_operation,
    _format_activity_stats,
    _format_basic_stats,
    _format_contributor_stats,
    _format_popular_tags,
    _format_search_result,
    _format_search_scope,
    _format_team_statistics,
    _get_team_statistics_impl,
    _get_team_statistics_operation,
    _require_team_manager,
    _search_team_knowledge_impl,
    _search_team_knowledge_operation,
    _vote_on_reflection_impl,
    _vote_on_reflection_operation,
    register_team_tools,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    """FastMCP stand-in recording tool registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _make_manager(**methods: Any) -> MagicMock:
    """Build a stub TeamKnowledgeManager.

    Each kwarg becomes an AsyncMock on the manager with that return value.
    """
    manager = MagicMock()
    for name, return_value in methods.items():
        setattr(manager, name, AsyncMock(return_value=return_value))
    return manager


def _patch_manager(
    monkeypatch: pytest.MonkeyPatch, manager: MagicMock | None = None
) -> MagicMock:
    """Patch ``_require_team_manager`` to return ``manager``."""
    manager = manager if manager is not None else _make_manager()

    async def fake_require() -> MagicMock:
        return manager

    monkeypatch.setattr(tt, "_require_team_manager", fake_require)
    return manager


@pytest.fixture(autouse=True)
def _patch_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``_get_logger`` so log calls accept arbitrary kwargs."""
    fake_logger = MagicMock()
    monkeypatch.setattr(tt, "_get_logger", lambda: fake_logger)


# ---------------------------------------------------------------------------
# _require_team_manager
# ---------------------------------------------------------------------------


class TestRequireTeamManager:
    async def test_returns_team_knowledge_manager_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the real path: import TeamKnowledgeManager, call it."""
        instance = MagicMock()
        klass = MagicMock(return_value=instance)

        fake_module = MagicMock()
        fake_module.TeamKnowledgeManager = klass

        # Reset the cache so we re-enter the try-block each call
        import importlib

        module = importlib.import_module(
            "session_buddy.mcp.tools.collaboration.team_tools"
        )
        # Patch __import__ via sys.modules isn't ideal; use a direct patch
        # by replacing the module after the import succeeds.
        monkeypatch.setattr(
            "session_buddy.team_knowledge.TeamKnowledgeManager",
            klass,
            raising=False,
        )
        # Patch the import statement by injecting a fake attribute the
        # ``from ... import TeamKnowledgeManager`` can find.
        sys_modules_patch = monkeypatch.setitem(
            __import__("sys").modules, "session_buddy.team_knowledge", fake_module
        )

        out = await _require_team_manager()
        assert out is instance
        klass.assert_called_once_with()


# ---------------------------------------------------------------------------
# _format_search_result
# ---------------------------------------------------------------------------


class TestFormatSearchResult:
    def test_full_metadata_with_tags_and_votes(self) -> None:
        out = _format_search_result(
            {
                "team_id": "t1",
                "author": "alice",
                "timestamp": "2026-09-05",
                "content": "hello world " * 20,
                "tags": ["python", "mcp"],
                "votes": 3,
            },
            1,
        )
        assert "**1.**" in out
        assert "[t1]" in out
        assert "alice" in out
        assert "2026-09-05" in out
        assert "Tags: python, mcp" in out
        assert "Votes: 3" in out
        # Content is truncated to 200 chars
        assert "hello world" in out
        assert "..." in out

    def test_short_content_has_no_ellipsis(self) -> None:
        # Pin the post-fix behavior: short content (≤200 chars) is rendered
        # verbatim without a trailing "...". The old buggy code appended "..."
        # unconditionally, producing misleading output like "hi...".
        out = _format_search_result({"content": "hi"}, 1)
        assert "hi" in out
        assert "..." not in out

    def test_minimal_result(self) -> None:
        out = _format_search_result({"content": "hi"}, 5)
        assert "**5.**" in out
        assert "[None]" not in out
        assert "by None" not in out
        assert "Tags" not in out
        assert "Votes" not in out
        assert "hi" in out

    def test_only_tags(self) -> None:
        out = _format_search_result(
            {"content": "x", "tags": ["a", "b"]},
            2,
        )
        assert "Tags: a, b" in out
        assert "Votes" not in out


# ---------------------------------------------------------------------------
# _format_search_scope
# ---------------------------------------------------------------------------


class TestFormatSearchScope:
    def test_both(self) -> None:
        assert (
            _format_search_scope("t1", "p1")
            == "team knowledge (team: t1) (project: p1)"
        )

    def test_team_only(self) -> None:
        assert _format_search_scope("t1", None) == "team knowledge (team: t1)"

    def test_project_only(self) -> None:
        assert _format_search_scope(None, "p1") == "team knowledge (project: p1)"

    def test_neither(self) -> None:
        assert _format_search_scope(None, None) == "team knowledge"


# ---------------------------------------------------------------------------
# _format_basic_stats
# ---------------------------------------------------------------------------


class TestFormatBasicStats:
    def test_populated(self) -> None:
        out = _format_basic_stats(
            {
                "member_count": 4,
                "reflection_count": 12,
                "project_count": 3,
                "total_votes": 17,
            }
        )
        assert "**Members**: 4" in out
        assert "**Reflections**: 12" in out
        assert "**Projects**: 3" in out
        assert "**Total Votes**: 17" in out

    def test_defaults_to_zero(self) -> None:
        out = _format_basic_stats({})
        assert "**Members**: 0" in out
        assert "**Reflections**: 0" in out
        assert "**Projects**: 0" in out
        assert "**Total Votes**: 0" in out


# ---------------------------------------------------------------------------
# _format_activity_stats
# ---------------------------------------------------------------------------


class TestFormatActivityStats:
    def test_empty_returns_empty_string(self) -> None:
        assert _format_activity_stats({}) == ""
        assert _format_activity_stats({"recent_activity": []}) == ""

    def test_populated(self) -> None:
        out = _format_activity_stats(
            {
                "recent_activity": [
                    {"timestamp": "2026-09-01", "description": "ship"},
                    {"timestamp": "2026-09-02", "description": "merge"},
                ]
            }
        )
        assert "Recent Activity" in out
        assert "2026-09-01: ship" in out
        assert "2026-09-02: merge" in out

    def test_truncates_to_five(self) -> None:
        acts = [
            {"timestamp": f"t{i}", "description": f"d{i}"} for i in range(8)
        ]
        out = _format_activity_stats({"recent_activity": acts})
        assert "d0" in out
        assert "d4" in out
        assert "d5" not in out
        assert "d7" not in out


# ---------------------------------------------------------------------------
# _format_contributor_stats
# ---------------------------------------------------------------------------


class TestFormatContributorStats:
    def test_empty(self) -> None:
        assert _format_contributor_stats({}) == ""
        assert _format_contributor_stats({"top_contributors": []}) == ""

    def test_populated(self) -> None:
        out = _format_contributor_stats(
            {
                "top_contributors": [
                    {"username": "alice", "contributions": 5},
                    {"username": "bob", "contributions": 2},
                ]
            }
        )
        assert "Top Contributors" in out
        assert "alice: 5 contributions" in out
        assert "bob: 2 contributions" in out

    def test_truncates_to_five(self) -> None:
        contribs = [
            {"username": f"u{i}", "contributions": i} for i in range(7)
        ]
        out = _format_contributor_stats({"top_contributors": contribs})
        assert "u0" in out
        assert "u4" in out
        assert "u5" not in out
        assert "u6" not in out


# ---------------------------------------------------------------------------
# _format_popular_tags
# ---------------------------------------------------------------------------


class TestFormatPopularTags:
    def test_empty(self) -> None:
        assert _format_popular_tags({}) == ""
        assert _format_popular_tags({"popular_tags": []}) == ""

    def test_populated(self) -> None:
        out = _format_popular_tags({"popular_tags": ["python", "mcp"]})
        assert "**Popular Tags**: python, mcp" in out

    def test_truncates_to_ten(self) -> None:
        tags = [f"t{i}" for i in range(15)]
        out = _format_popular_tags({"popular_tags": tags})
        assert "t0" in out
        assert "t9" in out
        assert "t10" not in out
        assert "t14" not in out


# ---------------------------------------------------------------------------
# _format_team_statistics
# ---------------------------------------------------------------------------


class TestFormatTeamStatistics:
    def test_minimal(self) -> None:
        out = _format_team_statistics("t1", {})
        assert "Team Statistics: t1" in out
        assert "**Members**: 0" in out

    def test_full(self) -> None:
        out = _format_team_statistics(
            "t1",
            {
                "member_count": 2,
                "reflection_count": 3,
                "project_count": 1,
                "total_votes": 7,
                "recent_activity": [
                    {"timestamp": "ts", "description": "did"}
                ],
                "top_contributors": [
                    {"username": "alice", "contributions": 3}
                ],
                "popular_tags": ["python"],
            },
        )
        assert "Team Statistics: t1" in out
        assert "**Members**: 2" in out
        assert "**Reflections**: 3" in out
        assert "Recent Activity" in out
        assert "Top Contributors" in out
        assert "alice: 3 contributions" in out
        assert "**Popular Tags**: python" in out


# ---------------------------------------------------------------------------
# create_team flow
# ---------------------------------------------------------------------------


class TestCreateTeamOperation:
    async def test_success_returns_check(self) -> None:
        manager = _make_manager(create_team=None)
        out = await _create_team_operation(
            manager, "t1", "Team One", "the team", "owner-1"
        )
        assert out == "✅ Team created successfully: Team One"
        kwargs = manager.create_team.await_args.kwargs
        assert kwargs["team_id"] == "t1"
        assert kwargs["name"] == "Team One"
        assert kwargs["description"] == "the team"
        assert kwargs["owner_id"] == "owner-1"


class TestCreateTeamImpl:
    async def test_delegates_to_manager(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _patch_manager(monkeypatch, _make_manager(create_team=None))
        out = await _create_team_impl("t1", "Team One", "desc", "owner")
        assert "Team created successfully" in out
        manager.create_team.assert_awaited_once()

    async def test_runtime_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise RuntimeError("team knowledge system not available")

        monkeypatch.setattr(tt, "_require_team_manager", boom)
        out = await _create_team_impl("t1", "Team One", "d", "o")
        assert "❌" in out
        assert "team knowledge system not available" in out

    async def test_value_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise ValueError("bad input")

        monkeypatch.setattr(tt, "_require_team_manager", boom)
        out = await _create_team_impl("t1", "Team One", "d", "o")
        assert "❌" in out
        assert "Create team failed" in out
        assert "bad input" in out

    async def test_generic_exception_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise OSError("network gone")

        monkeypatch.setattr(tt, "_require_team_manager", boom)
        out = await _create_team_impl("t1", "Team One", "d", "o")
        assert "Create team" in out
        assert "network gone" in out


# ---------------------------------------------------------------------------
# search_team_knowledge flow
# ---------------------------------------------------------------------------


class TestSearchTeamKnowledgeOperation:
    async def test_no_results(self) -> None:
        manager = _make_manager(search_team_reflections=[])
        out = await _search_team_knowledge_operation(
            manager, "missing", "u1", None, None, None, 10
        )
        assert "No results found" in out
        assert "missing" in out

    async def test_with_results(self) -> None:
        manager = _make_manager(
            search_team_reflections=[
                {
                    "team_id": "t1",
                    "author": "alice",
                    "timestamp": "ts",
                    "content": "matched content",
                    "tags": ["python"],
                    "votes": 2,
                }
            ]
        )
        out = await _search_team_knowledge_operation(
            manager, "matched", "u1", "t1", None, ["python"], 10
        )
        assert "1 team knowledge results" in out
        assert "[t1]" in out
        assert "alice" in out
        assert "Tags: python" in out

    async def test_with_project_filter_only(self) -> None:
        manager = _make_manager(search_team_reflections=[])
        out = await _search_team_knowledge_operation(
            manager, "x", "u1", None, "proj1", None, 10
        )
        assert "(project: proj1)" in out

    async def test_with_team_filter_only(self) -> None:
        manager = _make_manager(search_team_reflections=[])
        out = await _search_team_knowledge_operation(
            manager, "x", "u1", "teamX", None, None, 10
        )
        assert "(team: teamX)" in out


class TestSearchTeamKnowledgeImpl:
    async def test_delegates_kwargs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _patch_manager(monkeypatch, _make_manager(search_team_reflections=[]))
        await _search_team_knowledge_impl(
            "query", "u1", team_id="t1", project_id="p1", tags=["a"], limit=5
        )
        kwargs = manager.search_team_reflections.await_args.kwargs
        assert kwargs["query"] == "query"
        assert kwargs["user_id"] == "u1"
        assert kwargs["team_id"] == "t1"
        assert kwargs["project_id"] == "p1"
        assert kwargs["tags"] == ["a"]
        assert kwargs["limit"] == 5

    async def test_runtime_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise RuntimeError("not available")

        monkeypatch.setattr(tt, "_require_team_manager", boom)
        out = await _search_team_knowledge_impl("q", "u1")
        assert "❌" in out
        assert "not available" in out

    async def test_generic_exception_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise OSError("disk gone")

        monkeypatch.setattr(tt, "_require_team_manager", boom)
        out = await _search_team_knowledge_impl("q", "u1")
        assert "Search team knowledge" in out
        assert "disk gone" in out


# ---------------------------------------------------------------------------
# get_team_statistics flow
# ---------------------------------------------------------------------------


class TestGetTeamStatisticsOperation:
    async def test_none_stats(self) -> None:
        manager = _make_manager(get_team_stats=None)
        out = await _get_team_statistics_operation(manager, "t1", "u1")
        assert "❌" in out
        assert "Failed to retrieve team statistics" in out

    async def test_falsy_stats(self) -> None:
        manager = _make_manager(get_team_stats=False)
        out = await _get_team_statistics_operation(manager, "t1", "u1")
        assert "Failed to retrieve team statistics" in out

    async def test_populated_stats(self) -> None:
        manager = _make_manager(
            get_team_stats={
                "member_count": 2,
                "reflection_count": 3,
                "project_count": 1,
                "total_votes": 4,
            }
        )
        out = await _get_team_statistics_operation(manager, "t1", "u1")
        assert "Team Statistics: t1" in out
        assert "**Members**: 2" in out
        kwargs = manager.get_team_stats.await_args.kwargs
        assert kwargs["team_id"] == "t1"
        assert kwargs["user_id"] == "u1"


class TestGetTeamStatisticsImpl:
    async def test_delegate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_manager(
            monkeypatch,
            _make_manager(
                get_team_stats={
                    "member_count": 1,
                    "reflection_count": 0,
                    "project_count": 0,
                    "total_votes": 0,
                }
            ),
        )
        out = await _get_team_statistics_impl("t1", "u1")
        assert "Team Statistics: t1" in out

    async def test_runtime_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise RuntimeError("not available")

        monkeypatch.setattr(tt, "_require_team_manager", boom)
        out = await _get_team_statistics_impl("t1", "u1")
        assert "❌" in out
        assert "not available" in out


# ---------------------------------------------------------------------------
# vote_on_reflection flow
# ---------------------------------------------------------------------------


class TestVoteOnReflectionOperation:
    async def test_success(self) -> None:
        manager = _make_manager(vote_reflection=True)
        out = await _vote_on_reflection_operation(
            manager, "ref-1", "u1", 1
        )
        assert "✅ Reflection voted on successfully" in out
        assert "Vote recorded" in out
        kwargs = manager.vote_reflection.await_args.kwargs
        assert kwargs["reflection_id"] == "ref-1"
        assert kwargs["user_id"] == "u1"
        assert kwargs["vote_delta"] == 1

    async def test_failure(self) -> None:
        manager = _make_manager(vote_reflection=False)
        out = await _vote_on_reflection_operation(
            manager, "ref-1", "u1", 1
        )
        assert "❌ Failed to vote on reflection" in out


class TestVoteOnReflectionImpl:
    async def test_delegate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _patch_manager(monkeypatch, _make_manager(vote_reflection=True))
        out = await _vote_on_reflection_impl("ref-1", "u1")
        assert "Reflection voted on successfully" in out

    async def test_default_vote_delta(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _patch_manager(monkeypatch, _make_manager(vote_reflection=True))
        await _vote_on_reflection_impl("ref-1", "u1")
        kwargs = manager.vote_reflection.await_args.kwargs
        assert kwargs["vote_delta"] == 1

    async def test_custom_vote_delta(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _patch_manager(monkeypatch, _make_manager(vote_reflection=True))
        await _vote_on_reflection_impl("ref-1", "u1", vote_delta=-1)
        kwargs = manager.vote_reflection.await_args.kwargs
        assert kwargs["vote_delta"] == -1

    async def test_runtime_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise RuntimeError("not available")

        monkeypatch.setattr(tt, "_require_team_manager", boom)
        out = await _vote_on_reflection_impl("ref-1", "u1")
        assert "❌" in out
        assert "not available" in out

    async def test_generic_exception_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise ValueError("bad vote")

        monkeypatch.setattr(tt, "_require_team_manager", boom)
        out = await _vote_on_reflection_impl("ref-1", "u1")
        assert "Vote on reflection failed" in out
        assert "bad vote" in out


# ---------------------------------------------------------------------------
# _execute_team_operation
# ---------------------------------------------------------------------------


class TestExecuteTeamOperation:
    async def test_runtime_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise RuntimeError("not configured")

        monkeypatch.setattr(tt, "_require_team_manager", boom)

        async def op(_manager: Any) -> str:
            return "never reached"

        out = await _execute_team_operation("My op", op)
        assert "not configured" in out
        assert "❌" in out

    async def test_value_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise ValueError("bad input")

        monkeypatch.setattr(tt, "_require_team_manager", boom)

        async def op(_manager: Any) -> str:
            return "never reached"

        out = await _execute_team_operation("My op", op)
        assert "My op failed" in out
        assert "bad input" in out

    async def test_generic_exception_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise OSError("disk gone")

        monkeypatch.setattr(tt, "_require_team_manager", boom)

        async def op(_manager: Any) -> str:
            return "never reached"

        out = await _execute_team_operation("My op", op)
        assert "My op" in out
        assert "disk gone" in out


# ---------------------------------------------------------------------------
# register_team_tools
# ---------------------------------------------------------------------------


class TestRegisterTeamTools:
    def test_registers_all_four_tools(self) -> None:
        mcp = _FakeMCP()
        register_team_tools(mcp)
        expected = {
            "create_team",
            "search_team_knowledge",
            "get_team_statistics",
            "vote_on_reflection",
        }
        assert expected.issubset(set(mcp.tools))
        assert len(mcp.tools) == 4

    async def test_registered_create_team_is_callable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_manager(monkeypatch, _make_manager(create_team=None))
        mcp = _FakeMCP()
        register_team_tools(mcp)
        out = await mcp.tools["create_team"](
            "t1", "Team One", "desc", "owner"
        )
        assert "Team created successfully" in out

    async def test_registered_search_is_callable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_manager(monkeypatch, _make_manager(search_team_reflections=[]))
        mcp = _FakeMCP()
        register_team_tools(mcp)
        out = await mcp.tools["search_team_knowledge"]("q", "u1")
        assert "No results found" in out

    async def test_registered_get_stats_is_callable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_manager(
            monkeypatch,
            _make_manager(
                get_team_stats={
                    "member_count": 0,
                    "reflection_count": 0,
                    "project_count": 0,
                    "total_votes": 0,
                }
            ),
        )
        mcp = _FakeMCP()
        register_team_tools(mcp)
        out = await mcp.tools["get_team_statistics"]("t1", "u1")
        assert "Team Statistics: t1" in out

    async def test_registered_vote_is_callable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_manager(monkeypatch, _make_manager(vote_reflection=True))
        mcp = _FakeMCP()
        register_team_tools(mcp)
        out = await mcp.tools["vote_on_reflection"]("ref-1", "u1")
        assert "Reflection voted on successfully" in out