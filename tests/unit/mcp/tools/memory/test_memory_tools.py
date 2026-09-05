"""Tests for session_buddy.mcp.tools.memory.memory_tools.

Wave 11 (memory/ sweep) — covers the 7 MCP tools, helpers, db
resolution paths, two formatters, and registration in
``memory_tools.py`` (782 lines, was 11%).

Targets:
- ``_check_reflection_tools_available``: cached paths, probe with duckdb
  spec present, probe exception → False
- ``_get_reflection_database``: cached singleton, fresh resolve
- ``_execute_database_tool``: validator path, all 3 exception branches
- ``_execute_simple_database_tool``: 2 exception branches
- ``_format_score``: float formatting to 2 decimals
- ``_store_reflection_operation``: returns success dict
- ``_format_store_reflection_result``: success/failure via format_reflection_result
- ``_store_reflection_impl``: tools-unavailable, validation error,
  memory-guard block, db-unavailable, generic exception, success
- ``_quick_search_operation``: empty-results + populated branch
- ``_quick_search_impl``: tools-unavailable, db path
- ``_analyze_project_distribution``: missing project → Unknown
- ``_analyze_relevance_scores``: empty scores → 0.0 avg
- ``_extract_common_themes``: short-word skip, top-5 cap, empty
- ``_format_search_summary``: empty results branch, populated with all
  sections (multi-project distribution, time range, relevance, themes)
- ``_search_summary_operation``: db delegate
- ``_search_summary_impl``: 3 branches
- ``_format_file_search_results``: empty, populated with project/score/timestamp
- ``_search_by_file_operation`` + ``_search_by_file_impl``: 3 branches
- ``_format_concept_search_results``: empty, populated with files slice
- ``_search_by_concept_operation`` + ``_search_by_concept_impl``: 3 branches
- ``_format_stats_new``: healthy (>0), empty
- ``_format_stats_old``: with date_range, with recent_activity, healthy
- ``_format_new_stats`` + ``_format_old_stats``: aliases
- ``_reflection_stats_operation``: new format, old format, error case
- ``_reflection_stats_impl``: tools-unavailable, db path
- ``_close_db_connection``: no close method, sync close, async close
- ``_close_db_object``: aclose (sync/async), close fallback, none
- ``_close_reflection_db_safely``: with conn, without conn
- ``_reset_reflection_database_impl``: success, exception
- ``_register_core_memory_tools`` + ``register_memory_tools``: registers 7 tools

Test approach: monkeypatch ``_reflection_tools_available`` to True,
stub ``MemoryGuardAdapter`` to passthrough, mock the db on
``_get_reflection_database``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.memory import memory_tools as mt
from session_buddy.mcp.tools.memory.memory_tools import (
    _analyze_project_distribution,
    _analyze_relevance_scores,
    _check_reflection_tools_available,
    _close_db_connection,
    _close_db_object,
    _close_reflection_db_safely,
    _execute_database_tool,
    _execute_simple_database_tool,
    _extract_common_themes,
    _format_concept_search_results,
    _format_file_search_results,
    _format_old_stats,
    _format_score,
    _format_search_summary,
    _format_stats_new,
    _format_stats_old,
    _format_store_reflection_result,
    _quick_search_impl,
    _quick_search_operation,
    _reflection_stats_impl,
    _reflection_stats_operation,
    _reset_reflection_database_impl,
    _search_by_concept_impl,
    _search_by_concept_operation,
    _search_by_file_impl,
    _search_by_file_operation,
    _search_summary_impl,
    _search_summary_operation,
    _store_reflection_impl,
    _store_reflection_operation,
    register_memory_tools,
)
from session_buddy.utils.error_management import (
    DatabaseUnavailableError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Helpers + fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset module-level caches before each test."""
    monkeypatch.setattr(mt, "_reflection_tools_available", True)
    monkeypatch.setattr(mt, "_reflection_db", None)


def _make_db(**store_kwargs: Any) -> MagicMock:
    """Stub reflection db adapter."""
    db = MagicMock()
    db.store_reflection = AsyncMock(return_value=store_kwargs.get("store_id", True))
    db.search_reflections = AsyncMock(
        return_value=store_kwargs.get("search_results", [])
    )
    db.get_stats = AsyncMock(return_value=store_kwargs.get("stats", {}))
    return db


def _make_guard(
    action: Any = None,
    content: str = "original",
    tags: list[str] | None = None,
    matched_rule: str | None = None,
) -> MagicMock:
    """Build a stub MemoryGuardAdapter where screen() returns a stub decision."""
    guard = MagicMock()
    decision = MagicMock()
    if action is not None:
        from session_buddy.security.memory_guard_adapter import GuardAction

        decision.action = action
        decision.content = content
        decision.tags = tags if tags is not None else []
        decision.matched_rule = matched_rule
    guard.screen = MagicMock(return_value=decision)
    return guard


@pytest.fixture
def patched_guard(monkeypatch: pytest.MonkeyPatch):
    """Patch MemoryGuardAdapter with an ALLOW-by-default passthrough guard.

    Tests that need a non-default action (e.g. BLOCK) should call
    ``_set_guard_action`` directly instead of trying to pass args to the
    fixture.
    """
    from session_buddy.security.memory_guard_adapter import GuardAction

    current_action = {"action": GuardAction.ALLOW, "rule": None}

    def factory() -> MagicMock:
        return _make_guard(
            action=current_action["action"], matched_rule=current_action["rule"]
        )

    monkeypatch.setattr(
        "session_buddy.security.memory_guard_adapter.MemoryGuardAdapter", factory
    )
    return current_action  # mutable dict tests can mutate


def _set_guard_action(action: Any, matched_rule: str | None = None) -> None:
    """Module-level helper for tests that need a non-default guard action.

    Use ``monkeypatch.setattr`` before calling this to install a fresh
    factory, then mutate the returned dict via this helper.
    """
    pass  # tests mutate the dict fixture directly via patched_guard["action"]


class _FakeMCP:
    """FastMCP stand-in recording registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *args, **kwargs):  # noqa: ANN201
        def decorator(fn):  # noqa: ANN202
            self.tools[fn.__name__] = fn
            return fn

        return decorator


# ---------------------------------------------------------------------------
# _check_reflection_tools_available
# ---------------------------------------------------------------------------


class TestCheckReflectionToolsAvailable:
    def test_cached_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        assert _check_reflection_tools_available() is True

    def test_cached_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", False)
        assert _check_reflection_tools_available() is False

    def test_probe_with_spec_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", None)
        # importlib.util.find_spec("duckdb") returns a real spec in this venv
        result = _check_reflection_tools_available()
        assert result is True
        assert mt._reflection_tools_available is True

    def test_probe_spec_none_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", None)
        monkeypatch.setattr(
            "importlib.util.find_spec", lambda name: None
        )
        result = _check_reflection_tools_available()
        assert result is False
        assert mt._reflection_tools_available is False

    def test_probe_exception_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", None)

        def boom(*args: Any, **kwargs: Any) -> None:
            raise ImportError("probe failed")

        monkeypatch.setattr("importlib.util.find_spec", boom)
        result = _check_reflection_tools_available()
        assert result is False


# ---------------------------------------------------------------------------
# _get_reflection_database
# ---------------------------------------------------------------------------


class TestGetReflectionDatabase:
    async def test_cached_singleton_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        existing = MagicMock()
        monkeypatch.setattr(mt, "_reflection_db", existing)
        # If we tried to call require_reflection_database, it would fail
        monkeypatch.setattr(
            mt, "require_reflection_database",
            AsyncMock(side_effect=RuntimeError("should not be called")),
        )
        result = await mt._get_reflection_database()
        assert result is existing

    async def test_fresh_resolve_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fresh_db = MagicMock()
        monkeypatch.setattr(
            mt, "require_reflection_database", AsyncMock(return_value=fresh_db)
        )
        result = await mt._get_reflection_database()
        assert result is fresh_db


# ---------------------------------------------------------------------------
# _execute_database_tool / _execute_simple_database_tool
# ---------------------------------------------------------------------------


class TestExecuteDatabaseTool:
    async def test_no_validator_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _make_db()
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=db)
        )

        async def op(_db: Any) -> dict[str, str]:
            return {"x": "y"}

        out = await _execute_database_tool(op, lambda r: "ok", "TestOp")
        assert out == "ok"

    async def test_validator_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = []
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=RuntimeError("validator should fail first")),
        )

        def validator() -> None:
            called.append(True)
            raise ValidationError("bad")

        async def op(_db: Any) -> None:
            return None

        out = await _execute_database_tool(op, lambda r: "ok", "TestOp", validator=validator)
        assert called
        # ValidationError → ToolMessages.validation_error
        assert "TestOp" in out
        assert "validation" in out.lower()

    async def test_database_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("no db")),
        )

        async def op(_db: Any) -> None:
            return None

        out = await _execute_database_tool(op, lambda r: "ok", "TestOp")
        assert "TestOp" in out
        assert "not available" in out.lower()

    async def test_generic_exception_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=RuntimeError("crash")),
        )

        async def op(_db: Any) -> None:
            return None

        out = await _execute_database_tool(op, lambda r: "ok", "TestOp")
        assert "TestOp" in out
        assert "crash" in out


class TestExecuteSimpleDatabaseTool:
    async def test_db_unavailable_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("no db")),
        )

        async def op(_db: Any) -> str:
            return "should not run"

        out = await _execute_simple_database_tool(op, "SimpleOp")
        assert "SimpleOp" in out
        assert "not available" in out.lower()

    async def test_generic_exception_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=RuntimeError("crash")),
        )

        async def op(_db: Any) -> str:
            return "ok"

        out = await _execute_simple_database_tool(op, "SimpleOp")
        assert "SimpleOp" in out
        assert "crash" in out

    async def test_success_returns_formatter_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _make_db()
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=db)
        )

        async def op(_db: Any) -> str:
            return "ok"

        out = await _execute_simple_database_tool(op, "SimpleOp")
        assert out == "ok"


# ---------------------------------------------------------------------------
# _format_score
# ---------------------------------------------------------------------------


class TestFormatScore:
    def test_two_decimals(self) -> None:
        assert _format_score(0.5) == "0.50"
        assert _format_score(0.95) == "0.95"
        assert _format_score(0.0) == "0.00"
        assert _format_score(1.0) == "1.00"


# ---------------------------------------------------------------------------
# _store_reflection_operation + _format_store_reflection_result
# ---------------------------------------------------------------------------


class TestStoreReflectionOperation:
    async def test_returns_success_dict(self) -> None:
        db = _make_db(store_id=True)
        result = await _store_reflection_operation(db, "content", ["a", "b"])
        assert result["success"] is True
        assert result["content"] == "content"
        assert result["tags"] == ["a", "b"]
        assert "timestamp" in result
        db.store_reflection.assert_awaited_once_with("content", tags=["a", "b"])


class TestFormatStoreReflectionResult:
    def test_success_returns_formatted_string(self) -> None:
        out = _format_store_reflection_result({
            "success": True,
            "content": "hello",
            "tags": ["x"],
            "timestamp": "2026-01-01 00:00:00",
        })
        assert "Reflection stored successfully" in out
        assert "hello" in out

    def test_failure_returns_operation_failed_envelope(self) -> None:
        out = _format_store_reflection_result({
            "success": False,
            "content": "hello",
            "tags": [],
            "timestamp": "2026-01-01 00:00:00",
        })
        # format_reflection_result returns operation_failed for success=False
        assert "Store reflection" in out


# ---------------------------------------------------------------------------
# _store_reflection_impl (uses memory guard)
# ---------------------------------------------------------------------------


class TestStoreReflectionImpl:
    async def test_tools_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, patched_guard
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", False)
        out = await _store_reflection_impl("content")
        assert "not available" in out.lower()

    async def test_empty_content_validation_error(
        self, monkeypatch: pytest.MonkeyPatch, patched_guard
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        out = await _store_reflection_impl("")  # empty → ValidationError
        # ToolMessages.validation_error("Store reflection", "content cannot be empty")
        assert "Store reflection" in out

    async def test_memory_guard_block(
        self, monkeypatch: pytest.MonkeyPatch, patched_guard
    ) -> None:
        """When guard BLOCKs, MemoryGuardBlockedError propagates (not caught)."""
        from session_buddy.security.memory_guard_adapter import (
            GuardAction,
            MemoryGuardBlockedError,
        )

        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        patched_guard["action"] = GuardAction.BLOCK
        patched_guard["rule"] = "injection-rule"

        with pytest.raises(MemoryGuardBlockedError, match="Memory guard blocked"):
            await _store_reflection_impl("evil content")

    async def test_success(
        self, monkeypatch: pytest.MonkeyPatch, patched_guard
    ) -> None:
        # patched_guard defaults to GuardAction.ALLOW
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        db = _make_db(store_id=True)
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=db)
        )

        out = await _store_reflection_impl("safe content", tags=["t1"])
        assert "stored successfully" in out

    async def test_database_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, patched_guard
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("missing")),
        )

        out = await _store_reflection_impl("content")
        assert "not available" in out.lower()

    async def test_generic_exception_caught(
        self, monkeypatch: pytest.MonkeyPatch, patched_guard
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=RuntimeError("disk error")),
        )

        out = await _store_reflection_impl("content")
        assert "disk error" in out


# ---------------------------------------------------------------------------
# _quick_search_operation + _quick_search_impl
# ---------------------------------------------------------------------------


class TestQuickSearchOperation:
    async def test_empty_results(self) -> None:
        db = _make_db(search_results=[])
        out = await _quick_search_operation(db, "query", None, 0.7)
        assert "No results found" in out
        assert "min_score" in out

    async def test_populated_results(self) -> None:
        db = _make_db(search_results=[
            {"content": "match", "score": 0.9, "project": "p", "timestamp": "t"}
        ])
        out = await _quick_search_operation(db, "query", None, 0.7)
        assert "Found results (showing top 1)" in out
        assert "match" in out
        assert "0.90" in out
        assert "p" in out
        assert "t" in out

    async def test_score_none_branch(self) -> None:
        """Result has no score → Relevance line not emitted."""
        db = _make_db(search_results=[{"content": "x", "project": "p"}])
        out = await _quick_search_operation(db, "q", None, 0.7)
        assert "Relevance" not in out

    async def test_search_reflections_called_with_correct_kwargs(self) -> None:
        db = _make_db()
        await _quick_search_operation(db, "query", None, 0.7)
        kwargs = db.search_reflections.await_args.kwargs
        assert kwargs["query"] == "query"
        assert kwargs["limit"] == 1
        assert kwargs["use_embeddings"] is False


class TestQuickSearchImpl:
    async def test_tools_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", False)
        out = await _quick_search_impl("query")
        assert "not available" in out.lower()

    async def test_db_path_with_results(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        db = _make_db(search_results=[{"content": "match"}])
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=db)
        )
        out = await _quick_search_impl("query")
        assert "match" in out


# ---------------------------------------------------------------------------
# _analyze_project_distribution
# ---------------------------------------------------------------------------


class TestAnalyzeProjectDistribution:
    async def test_missing_project_defaults_to_unknown(self) -> None:
        result = await _analyze_project_distribution([{}, {"project": "p"}])
        assert result == {"Unknown": 1, "p": 1}


# ---------------------------------------------------------------------------
# _analyze_relevance_scores
# ---------------------------------------------------------------------------


class TestAnalyzeRelevanceScores:
    async def test_empty_scores_returns_zero(self) -> None:
        avg, scores = await _analyze_relevance_scores([])
        assert avg == 0.0
        assert scores == []

    async def test_filters_none_scores(self) -> None:
        avg, scores = await _analyze_relevance_scores([
            {"score": 0.5},
            {"score": None},
            {"score": 0.7},
        ])
        assert avg == pytest.approx(0.6)
        assert scores == [0.5, 0.7]


# ---------------------------------------------------------------------------
# _extract_common_themes
# ---------------------------------------------------------------------------


class TestExtractCommonThemes:
    async def test_skips_short_words(self) -> None:
        # Words ≤4 chars skipped
        result = await _extract_common_themes([{"content": "the cat"}])
        assert result == []

    async def test_top_5_cap(self) -> None:
        # 6 long words → top 5 returned
        content = " ".join([f"word{i}" for i in range(1, 7)])
        result = await _extract_common_themes([{"content": content}])
        assert len(result) == 5

    async def test_sorted_by_frequency(self) -> None:
        content = "alpha beta alpha beta alpha gamma gamma gamma gamma"
        result = await _extract_common_themes([{"content": content}])
        # gamma (4), alpha (3), beta (2)
        assert result[0] == ("gamma", 4)
        assert result[1] == ("alpha", 3)


# ---------------------------------------------------------------------------
# _format_search_summary
# ---------------------------------------------------------------------------


class TestFormatSearchSummary:
    async def test_empty_results(self) -> None:
        out = await _format_search_summary("q", [])
        assert "No results found" in out
        assert "min_score" in out

    async def test_single_project_skips_distribution(self) -> None:
        """When all results share one project, the distribution block is skipped."""
        results = [{"content": "alpha", "score": 0.5, "project": "p", "timestamp": "t"}]
        out = await _format_search_summary("q", results)
        assert "Total results: 1" in out
        # Single project → no "Project distribution:" block
        assert "Project distribution:" not in out

    async def test_multi_project_distribution(self) -> None:
        results = [
            {"content": "x", "project": "a"},
            {"content": "y", "project": "b"},
        ]
        out = await _format_search_summary("q", results)
        assert "Project distribution:" in out
        assert "a: 1" in out and "b: 1" in out

    async def test_time_range_line(self) -> None:
        results = [
            {"content": "x", "timestamp": "2026-01-01"},
            {"content": "y", "timestamp": "2026-02-01"},
        ]
        out = await _format_search_summary("q", results)
        assert "Time range: 2 results with dates" in out

    async def test_relevance_score_line(self) -> None:
        results = [{"content": "x", "score": 0.9}]
        out = await _format_search_summary("q", results)
        assert "Average relevance: 0.90" in out

    async def test_common_themes_block(self) -> None:
        # All long words → themes block populated
        results = [{"content": "python async python await async python"}]
        out = await _format_search_summary("q", results)
        assert "Common themes:" in out
        assert "python" in out
        assert "async" in out

    async def test_no_timestamps_no_time_range(self) -> None:
        results = [{"content": "x", "score": 0.5}]
        out = await _format_search_summary("q", results)
        assert "Time range:" not in out


# ---------------------------------------------------------------------------
# _search_summary_operation + _search_summary_impl
# ---------------------------------------------------------------------------


class TestSearchSummaryOperation:
    async def test_delegate_to_db(self) -> None:
        db = _make_db(search_results=[])
        await _search_summary_operation(db, "query", None, 0.7)
        kwargs = db.search_reflections.await_args.kwargs
        assert kwargs["query"] == "query"
        assert kwargs["limit"] == 20
        assert kwargs["use_embeddings"] is False
        assert kwargs["project"] is None


class TestSearchSummaryImpl:
    async def test_tools_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", False)
        out = await _search_summary_impl("query")
        assert "not available" in out.lower()

    async def test_db_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        db = _make_db(search_results=[{"content": "match"}])
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=db)
        )
        out = await _search_summary_impl("query")
        assert "Total results: 1" in out

    async def test_database_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("missing")),
        )
        out = await _search_summary_impl("query")
        assert "not available" in out.lower()

    async def test_generic_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=RuntimeError("crash")),
        )
        out = await _search_summary_impl("query")
        assert "crash" in out


# ---------------------------------------------------------------------------
# _format_file_search_results + _search_by_file_operation + _search_by_file_impl
# ---------------------------------------------------------------------------


class TestFormatFileSearchResults:
    async def test_empty_results(self) -> None:
        out = await _format_file_search_results("src/main.py", [])
        assert "No conversations found" in out
        assert "src/main.py" in out

    async def test_populated_results_with_all_optional_fields(self) -> None:
        results = [
            {
                "content": "match",
                "score": 0.7,
                "project": "p",
                "timestamp": "2026-01-01",
            }
        ]
        out = await _format_file_search_results("src/main.py", results)
        assert "Found 1" in out
        assert "match" in out
        assert "p" in out
        assert "0.70" in out
        assert "2026-01-01" in out

    async def test_populated_results_minimal(self) -> None:
        results = [{"content": "x"}]
        out = await _format_file_search_results("p", results)
        assert "Found 1" in out
        assert "Relevance" not in out  # No score
        assert "Project" not in out  # No project


class TestSearchByFileOperation:
    async def test_delegate_to_db(self) -> None:
        db = _make_db()
        await _search_by_file_operation(db, "src/main.py", 5, "proj")
        kwargs = db.search_reflections.await_args.kwargs
        assert kwargs["query"] == "src/main.py"
        assert kwargs["limit"] == 5
        assert kwargs["use_embeddings"] is False
        assert kwargs["project"] == "proj"


class TestSearchByFileImpl:
    async def test_tools_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", False)
        out = await _search_by_file_impl("src/main.py")
        assert "not available" in out.lower()

    async def test_db_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        db = _make_db(search_results=[{"content": "match"}])
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=db)
        )
        out = await _search_by_file_impl("src/main.py")
        assert "match" in out

    async def test_database_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("missing")),
        )
        out = await _search_by_file_impl("src/main.py")
        assert "not available" in out.lower()

    async def test_generic_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=RuntimeError("crash")),
        )
        out = await _search_by_file_impl("src/main.py")
        assert "crash" in out


# ---------------------------------------------------------------------------
# _format_concept_search_results + _search_by_concept_operation + _search_by_concept_impl
# ---------------------------------------------------------------------------


class TestFormatConceptSearchResults:
    async def test_empty_results(self) -> None:
        out = await _format_concept_search_results("async", [], True)
        assert "No conversations found" in out
        assert "broader concepts" in out

    async def test_populated_with_files(self) -> None:
        results = [
            {
                "content": "deep dive",
                "score": 0.7,
                "project": "p",
                "timestamp": "t",
                "files": ["a.py", "b.py", "c.py", "d.py"],
            }
        ]
        out = await _format_concept_search_results("async", results, True)
        # Files truncated to top 3
        assert "a.py" in out and "b.py" in out and "c.py" in out
        assert "d.py" not in out

    async def test_populated_without_files(self) -> None:
        results = [{"content": "x", "files": ["a.py"]}]
        out = await _format_concept_search_results("c", results, False)
        assert "a.py" not in out

    async def test_populated_files_empty_list(self) -> None:
        """`result.get('files')` is an empty list → no Files line."""
        results = [{"content": "x", "files": []}]
        out = await _format_concept_search_results("c", results, True)
        assert "Files:" not in out


class TestSearchByConceptOperation:
    async def test_delegate_to_db(self) -> None:
        db = _make_db()
        await _search_by_concept_operation(db, "async", True, 5, "proj")
        kwargs = db.search_reflections.await_args.kwargs
        assert kwargs["query"] == "async"
        assert kwargs["limit"] == 5
        assert kwargs["use_embeddings"] is False
        assert kwargs["project"] == "proj"


class TestSearchByConceptImpl:
    async def test_tools_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", False)
        out = await _search_by_concept_impl("async")
        assert "not available" in out.lower()

    async def test_db_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        db = _make_db(search_results=[{"content": "x"}])
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=db)
        )
        out = await _search_by_concept_impl("async")
        assert "x" in out

    async def test_database_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=DatabaseUnavailableError("missing")),
        )
        out = await _search_by_concept_impl("async")
        assert "not available" in out.lower()

    async def test_generic_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            mt, "_get_reflection_database",
            AsyncMock(side_effect=RuntimeError("crash")),
        )
        out = await _search_by_concept_impl("async")
        assert "crash" in out


# ---------------------------------------------------------------------------
# Stats formatters
# ---------------------------------------------------------------------------


class TestFormatStatsNew:
    def test_healthy(self) -> None:
        lines = _format_stats_new({
            "conversations_count": 10,
            "reflections_count": 5,
            "embedding_provider": "fastembed",
        })
        joined = "\n".join(lines)
        assert "Total conversations: 10" in joined
        assert "Total reflections: 5" in joined
        assert "fastembed" in joined
        assert "Healthy" in joined

    def test_empty(self) -> None:
        lines = _format_stats_new({
            "conversations_count": 0,
            "reflections_count": 0,
        })
        joined = "\n".join(lines)
        assert "Empty" in joined
        # Defaults to "unknown" when embedding_provider is missing
        assert "unknown" in joined


class TestFormatStatsOld:
    def test_with_date_range_and_recent_activity(self) -> None:
        stats = {
            "total_reflections": 10,
            "projects": 3,
            "date_range": {"start": "2026-01-01", "end": "2026-02-01"},
            "recent_activity": ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"],
        }
        lines = _format_stats_old(stats)
        joined = "\n".join(lines)
        assert "Total reflections: 10" in joined
        assert "Projects: 3" in joined
        assert "Date range: 2026-01-01 to 2026-02-01" in joined
        assert "Recent activity" in joined
        # Top-5 cap: echo is in, foxtrot is NOT in
        assert "echo" in joined
        assert "foxtrot" not in joined
        assert "Healthy" in joined

    def test_empty(self) -> None:
        lines = _format_stats_old({"total_reflections": 0, "projects": 0})
        joined = "\n".join(lines)
        assert "Empty" in joined


class TestFormatStatsAliases:
    def test_format_new_stats_matches_new(self) -> None:
        from session_buddy.mcp.tools.memory.memory_tools import (
            _format_new_stats,
            _format_stats_new,
        )
        stats = {"conversations_count": 1, "reflections_count": 1}
        assert _format_new_stats(stats) == _format_stats_new(stats)

    def test_format_old_stats_matches_old(self) -> None:
        stats = {"total_reflections": 5, "projects": 2}
        assert _format_old_stats(stats) == _format_stats_old(stats)


# ---------------------------------------------------------------------------
# _reflection_stats_operation + _reflection_stats_impl
# ---------------------------------------------------------------------------


class TestReflectionStatsOperation:
    async def test_new_format(self) -> None:
        db = _make_db(stats={
            "conversations_count": 5,
            "reflections_count": 3,
            "embedding_provider": "fastembed",
        })
        out = await _reflection_stats_operation(db)
        assert "Total conversations: 5" in out
        assert "Total reflections: 3" in out
        assert "Healthy" in out

    async def test_old_format(self) -> None:
        db = _make_db(stats={"total_reflections": 7, "projects": 2})
        out = await _reflection_stats_operation(db)
        assert "Total reflections: 7" in out
        assert "Projects: 2" in out

    async def test_error_in_stats(self) -> None:
        db = _make_db(stats={"error": "connection lost"})
        out = await _reflection_stats_operation(db)
        assert "No statistics available" in out

    async def test_empty_stats_dict(self) -> None:
        db = _make_db(stats={})
        out = await _reflection_stats_operation(db)
        assert "No statistics available" in out


class TestReflectionStatsImpl:
    async def test_tools_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", False)
        out = await _reflection_stats_impl()
        assert "not available" in out.lower()

    async def test_db_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        db = _make_db(stats={"conversations_count": 5, "reflections_count": 3})
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=db)
        )
        out = await _reflection_stats_impl()
        assert "Total reflections: 3" in out


# ---------------------------------------------------------------------------
# _close_db_connection, _close_db_object, _close_reflection_db_safely
# ---------------------------------------------------------------------------


class TestCloseDbConnection:
    async def test_no_close_method(self) -> None:
        """Object without close attribute → no-op, no error."""
        await _close_db_connection(object())
        # No assertion needed; just verify no exception

    async def test_sync_close(self) -> None:
        conn = MagicMock()
        conn.close = MagicMock(return_value=None)
        await _close_db_connection(conn)
        conn.close.assert_called_once()

    async def test_async_close(self) -> None:
        """close() returns a coroutine → awaited."""
        close_coro = AsyncMock()
        conn = MagicMock()
        conn.close = MagicMock(return_value=close_coro())
        await _close_db_connection(conn)
        # If async, the inner coroutine was awaited
        # (no direct assertion possible; just verify no error)


class TestCloseDbObject:
    async def test_aclose_method(self) -> None:
        db_obj = MagicMock()
        db_obj.aclose = MagicMock(return_value=None)
        # Should not raise even though close exists too
        db_obj.close = MagicMock()
        await _close_db_object(db_obj)
        db_obj.aclose.assert_called_once()

    async def test_aclose_returns_coroutine(self) -> None:
        """aclose() returns a coroutine → awaited."""
        aclose_coro = AsyncMock()
        db_obj = MagicMock(spec=["aclose"])
        db_obj.aclose = MagicMock(return_value=aclose_coro())
        await _close_db_object(db_obj)
        # No direct assertion possible; verify no exception

    async def test_fallback_to_sync_close(self) -> None:
        db_obj = MagicMock(spec=["close"])
        db_obj.close = MagicMock(return_value=None)
        await _close_db_object(db_obj)
        db_obj.close.assert_called_once()

    async def test_no_close_methods(self) -> None:
        db_obj = MagicMock(spec=[])  # No attributes
        # Should not raise
        await _close_db_object(db_obj)


class TestCloseReflectionDbSafely:
    async def test_with_conn_and_object(self) -> None:
        conn = MagicMock(spec=["close"])
        conn.close = MagicMock(return_value=None)
        db_obj = MagicMock(spec=["conn", "close"])
        db_obj.conn = conn
        db_obj.close = MagicMock(return_value=None)
        await _close_reflection_db_safely(db_obj)
        conn.close.assert_called_once()
        db_obj.close.assert_called_once()

    async def test_without_conn(self) -> None:
        db_obj = MagicMock(spec=["close"])
        db_obj.close = MagicMock(return_value=None)
        await _close_reflection_db_safely(db_obj)
        db_obj.close.assert_called_once()


# ---------------------------------------------------------------------------
# _reset_reflection_database_impl
# ---------------------------------------------------------------------------


class TestResetReflectionDatabaseImpl:
    async def test_tools_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", False)
        out = await _reset_reflection_database_impl()
        assert "not available" in out.lower()

    async def test_success_no_existing_db(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)
        # No cached db → skip the close step
        fresh_db = MagicMock()
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=fresh_db)
        )

        out = await _reset_reflection_database_impl()
        assert "Reflection database connection reset" in out
        assert "New connection established" in out

    async def test_success_with_existing_db(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)

        # MagicMock auto-generates callable `aclose`, so we use spec= to
        # restrict attributes and force the `close` fallback branch to fire.
        existing = MagicMock(spec=["conn", "close"])
        existing.conn = None
        existing.close = MagicMock(return_value=None)
        monkeypatch.setattr(mt, "_reflection_db", existing)

        fresh_db = MagicMock()
        monkeypatch.setattr(
            mt, "_get_reflection_database", AsyncMock(return_value=fresh_db)
        )

        out = await _reset_reflection_database_impl()
        assert "reset" in out
        existing.close.assert_called_once()

    async def test_exception_returns_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mt, "_reflection_tools_available", True)

        async def boom() -> None:
            raise RuntimeError("re-establish failed")

        monkeypatch.setattr(mt, "_get_reflection_database", boom)
        out = await _reset_reflection_database_impl()
        assert "Reset database" in out
        assert "re-establish failed" in out


# ---------------------------------------------------------------------------
# register_memory_tools
# ---------------------------------------------------------------------------


class TestRegisterMemoryTools:
    def test_registers_seven_tools(self) -> None:
        mcp = _FakeMCP()
        register_memory_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "store_reflection",
            "quick_search",
            "search_summary",
            "search_by_file",
            "search_by_concept",
            "reflection_stats",
            "reset_reflection_database",
        }

    async def test_store_reflection_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_memory_tools(mcp)

        captured = []
        monkeypatch.setattr(
            mt, "_store_reflection_impl",
            AsyncMock(side_effect=lambda c, tags=None: captured.append((c, tags)) or "ok"),
        )
        result = await mcp.tools["store_reflection"](content="hi", tags=["a"])
        assert result == "ok"
        assert captured == [("hi", ["a"])]

    async def test_quick_search_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_memory_tools(mcp)

        captured = []
        monkeypatch.setattr(
            mt, "_quick_search_impl",
            AsyncMock(side_effect=lambda q, min_score=0.7, project=None: captured.append((q, min_score, project)) or "ok"),
        )
        result = await mcp.tools["quick_search"](query="python")
        assert result == "ok"
        assert captured == [("python", 0.7, None)]

    async def test_search_summary_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_memory_tools(mcp)

        captured = []
        monkeypatch.setattr(
            mt, "_search_summary_impl",
            AsyncMock(side_effect=lambda q, min_score=0.7, project=None: captured.append((q, min_score, project)) or "ok"),
        )
        result = await mcp.tools["search_summary"](query="python")
        assert result == "ok"
        assert captured == [("python", 0.7, None)]

    async def test_search_by_file_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_memory_tools(mcp)

        captured = []
        monkeypatch.setattr(
            mt, "_search_by_file_impl",
            AsyncMock(side_effect=lambda fp, limit=10, project=None: captured.append((fp, limit, project)) or "ok"),
        )
        result = await mcp.tools["search_by_file"](file_path="src/main.py")
        assert result == "ok"
        assert captured == [("src/main.py", 10, None)]

    async def test_search_by_concept_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_memory_tools(mcp)

        captured = []
        monkeypatch.setattr(
            mt, "_search_by_concept_impl",
            AsyncMock(side_effect=lambda c, include_files=True, limit=10, project=None: captured.append((c, include_files, limit, project)) or "ok"),
        )
        result = await mcp.tools["search_by_concept"](concept="async")
        assert result == "ok"
        assert captured == [("async", True, 10, None)]

    async def test_reflection_stats_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_memory_tools(mcp)

        monkeypatch.setattr(
            mt, "_reflection_stats_impl",
            AsyncMock(return_value="stats!"),
        )
        # reflection_stats has project parameter that isn't passed through
        result = await mcp.tools["reflection_stats"](project="proj")
        assert result == "stats!"

    async def test_reset_reflection_database_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_memory_tools(mcp)

        monkeypatch.setattr(
            mt, "_reset_reflection_database_impl",
            AsyncMock(return_value="reset!"),
        )
        result = await mcp.tools["reset_reflection_database"]()
        assert result == "reset!"
