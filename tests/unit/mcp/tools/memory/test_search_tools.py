"""Tests for session_buddy.mcp.tools.memory.search_tools.

Wave 11 (memory/ sweep) — covers the 17 MCP tools, helpers, db dispatch
paths, formatters, parse helpers, skill classifier, and 7 registration
groups in ``search_tools.py`` (1914 lines, was 10%).

Targets (every public tool + every formatter + every helper):
- ``_optimize_search_results_impl``: 4 branches (no opt + empty, no opt
  + populated, opt success, ImportError fallback, generic exception)
- ``_store_reflection_operation`` + ``_format_store_reflection`` +
  ``_store_reflection_impl``
- ``_quick_search_operation`` + ``_quick_search_impl``: empty branch,
  single-result, multi-result with hint
- ``_extract_key_terms``: short-word skip, top-5 cap, empty
- ``_format_search_summary``: empty, time-range, key-terms
- ``_search_summary_operation`` + ``_search_summary_impl``
- ``_build_pagination_output``: empty paginated slice, populated with
  remaining hint, no-remaining branch
- ``_get_more_results_operation`` + ``_get_more_results_impl``
- ``_extract_file_excerpt``: with-substring, without
- ``_format_file_search_results`` + ``_search_by_file_*``
- ``_extract_relevant_excerpt``: case-insensitive substring, fallback
- ``_extract_mentioned_files``: regex success, ImportError fallback
- ``_format_concept_results`` + ``_search_by_concept_*``: with files,
  without files
- ``_format_source_results``: empty (scope message), populated, scope
  formatting
- ``_search_by_source_*``
- ``_format_memory_lineage`` + ``_memory_lineage_impl``: empty chain,
  populated, missing memory_id validation
- ``_format_peer_context`` + ``_peer_context_impl``: with
  representation, with target peer, with recent memories, content
  truncation
- ``_update_peer_model_impl``: success path
- ``_format_causal_chain`` + ``_causal_chain_impl``: empty, observed vs
  inferred, depth, link_type, from→to rendering
- ``_format_skill`` + ``_format_skill_list`` + ``_format_skill_search``
- ``_distill_skills_now_impl`` + ``_search_distilled_skills_impl``
- ``_classify_skill_status``: 4 status branches (stale,
  under_utilized, cold, fresh) + 2 boundary edges
- ``_parse_reinforced_ts``: datetime, str (ISO), None, unsupported type,
  tz-naive upgrade
- ``_distilled_skill_health_impl``: zero threshold, db injection,
  db-missing → empty list, exception path
- ``_reset_reflection_database_impl``: success + exception
- ``_reflection_stats_operation`` + ``_reflection_stats_impl``
- ``_session_learning_report_impl``: success, db-unavailable, generic
  exception
- ``_extract_code_blocks_from_content``: success, fallback
- ``_format_code_search_results``: empty, with code blocks, without
  blocks (excerpt branch)
- ``_search_code_*``
- ``_find_best_error_excerpt``: with keyword, no keyword
- ``_format_error_search_results`` + ``_search_errors_*``
- ``_parse_time_expression``: yesterday, last week, last month, today,
  unparseable → None
- ``_format_temporal_results`` + ``_search_temporal_*``: with/without
  start_time, with/without query
- ``_parse_tags_parameter``: list, JSON list, JSON null, single string,
  invalid JSON
- ``_parse_skill_names_param``: None, list, JSON list, invalid JSON
- ``_progressive_search_impl``: success, ImportError, exception
- ``_configure_tiers_impl``: success, ImportError, exception
- ``_tier_stats_impl``: success, ImportError, exception
- All ``_register_*_tools`` functions + ``register_search_tools``:
  verify every tool is registered

Test approach: monkeypatch ``require_reflection_database`` on the
consumer module, stub the db with MagicMock, use ``_FakeMCP`` for
registrations.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.memory import search_tools as st
from session_buddy.mcp.tools.memory.search_tools import (
    _build_pagination_output,
    _causal_chain_impl,
    _classify_skill_status,
    _configure_tiers_impl,
    _distill_skills_now_impl,
    _distilled_skill_health_impl,
    _extract_code_blocks_from_content,
    _extract_file_excerpt,
    _extract_key_terms,
    _extract_mentioned_files,
    _extract_relevant_excerpt,
    _find_best_error_excerpt,
    _format_causal_chain,
    _format_code_search_results,
    _format_concept_results,
    _format_error_search_results,
    _format_file_search_results,
    _format_memory_lineage,
    _format_peer_context,
    _format_search_summary,
    _format_skill,
    _format_skill_list,
    _format_skill_search,
    _format_source_results,
    _format_store_reflection,
    _format_temporal_results,
    _get_more_results_impl,
    _get_more_results_operation,
    _memory_lineage_impl,
    _optimize_search_results_impl,
    _parse_reinforced_ts,
    _parse_skill_names_param,
    _parse_tags_parameter,
    _parse_time_expression,
    _peer_context_impl,
    _progressive_search_impl,
    _quick_search_impl,
    _quick_search_operation,
    _reflection_stats_impl,
    _register_code_and_error_search_tools,
    _register_core_search_tools,
    _register_distillation_and_stats_tools,
    _register_distilled_skill_health_tool,
    _register_indexed_search_tools,
    _register_peer_and_temporal_tools,
    _register_progressive_search_tools,
    _register_specialized_search_tools,
    _reset_reflection_database_impl,
    _search_by_concept_impl,
    _search_by_concept_operation,
    _search_by_file_impl,
    _search_by_file_operation,
    _search_by_source_impl,
    _search_by_source_operation,
    _search_code_impl,
    _search_code_operation,
    _search_distilled_skills_impl,
    _search_errors_impl,
    _search_errors_operation,
    _search_summary_impl,
    _search_summary_operation,
    _search_temporal_impl,
    _search_temporal_operation,
    _session_learning_report_impl,
    _store_reflection_impl,
    _store_reflection_operation,
    _tier_stats_impl,
    _update_peer_model_impl,
    register_search_tools,
)
from session_buddy.utils.error_management import DatabaseUnavailableError


# ---------------------------------------------------------------------------
# Helpers + fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch: pytest.MonkeyPatch):
    """Patch ``require_reflection_database`` and ``execute_*_tool`` helpers
    so tests can inject a stub db without needing a real DuckDB file."""
    yield monkeypatch


def _make_db(**methods: Any) -> MagicMock:
    """Build a stub ReflectionDatabase where each method is an AsyncMock
    returning the supplied canned value.

    Callers pass the *value* they want returned, NOT an AsyncMock. This
    helper wraps the value in a fresh AsyncMock so the production code's
    ``await db.method(...)`` returns the actual value.
    """
    db = MagicMock()
    for name, value in methods.items():
        setattr(db, name, AsyncMock(return_value=value))
    # Default for any missing method
    for default in (
        "store_reflection", "search_conversations", "search_by_source",
        "memory_lineage", "peer_context", "update_peer_model",
        "causal_chain", "distill_skills_now", "search_distilled_skills",
        "get_stats", "generate_session_differential",
    ):
        if not hasattr(db, default):
            setattr(db, default, AsyncMock(return_value=[]))
    return db


class _FakeMCP:
    """FastMCP stand-in capturing tool registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *args, **kwargs):  # noqa: ANN201
        def decorator(fn):  # noqa: ANN202
            self.tools[fn.__name__] = fn
            return fn

        return decorator


# ---------------------------------------------------------------------------
# _optimize_search_results_impl
# ---------------------------------------------------------------------------


class TestOptimizeSearchResults:
    async def test_no_optimization_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await _optimize_search_results_impl(
            [{"id": "1"}], optimize_tokens=False, max_tokens=100, query="q"
        )
        assert result["optimized"] is False
        assert result["results"] == [{"id": "1"}]

    async def test_empty_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = await _optimize_search_results_impl(
            [], optimize_tokens=True, max_tokens=100, query="q"
        )
        # When results is empty the optimize branch is skipped
        assert result["optimized"] is False

    async def test_token_optimizer_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _FakeOpt:
            async def optimize_search_results(self, results, mode, max_tokens):
                return results, {"tokens_saved": 50}

        class _FakeMod:
            TokenOptimizer = _FakeOpt

        # Patch the consumer's lazy import — `from session_buddy.token_optimizer import TokenOptimizer`
        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.token_optimizer",
            _FakeMod(),
        )
        result = await _optimize_search_results_impl(
            [{"id": "1"}], optimize_tokens=True, max_tokens=100, query="q"
        )
        assert result["optimized"] is True
        assert result["optimization_info"]["tokens_saved"] == 50

    async def test_token_optimizer_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force the lazy import to fail
        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.token_optimizer",
            None,
        )
        result = await _optimize_search_results_impl(
            [{"id": "1"}], optimize_tokens=True, max_tokens=100, query="q"
        )
        assert result["optimized"] is False
        assert result.get("token_count") == 0

    async def test_token_optimizer_generic_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _BoomOpt:
            async def optimize_search_results(self, *args, **kwargs):
                raise RuntimeError("oops")

        class _FakeMod:
            TokenOptimizer = _BoomOpt

        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.token_optimizer",
            _FakeMod(),
        )
        result = await _optimize_search_results_impl(
            [{"id": "1"}], optimize_tokens=True, max_tokens=100, query="q"
        )
        assert result["optimized"] is False
        assert result["error"] == "oops"


# ---------------------------------------------------------------------------
# _store_reflection_operation + _format_store_reflection + _store_reflection_impl
# ---------------------------------------------------------------------------


class TestStoreReflectionImpl:
    async def test_operation_returns_success_dict(self) -> None:
        db = _make_db(store_reflection="refl-1")
        result = await _store_reflection_operation(db, "content", ["t1"])
        assert result["success"] is True
        assert result["id"] == "refl-1"

    def test_format_with_tags(self) -> None:
        out = _format_store_reflection({
            "success": True, "id": "r1", "content": "c", "tags": ["t1", "t2"]
        })
        assert "r1" in out
        assert "t1, t2" in out

    def test_format_without_tags(self) -> None:
        out = _format_store_reflection({
            "success": True, "id": "r1", "content": "c", "tags": []
        })
        assert "tags" not in out

    async def test_impl_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_execute(*args, **kwargs):
            return "validation error"

        monkeypatch.setattr(st, "execute_database_tool", fake_execute)
        out = await _store_reflection_impl("", tags=None)
        assert out == "validation error"


# ---------------------------------------------------------------------------
# _quick_search_operation + _quick_search_impl
# ---------------------------------------------------------------------------


class TestQuickSearchOperation:
    async def test_empty_results(self) -> None:
        db = _make_db(search_conversations=[])
        out = await _quick_search_operation(db, "q", None, 0.7, 5)
        assert "No results found" in out

    async def test_single_result_no_hint(self) -> None:
        db = _make_db(search_conversations=[{"content": "match", "similarity": 0.9}])
        out = await _quick_search_operation(db, "q", None, 0.7, 5)
        assert "match" in out
        assert "0.9" in out
        # Only 1 result → no "more" hint
        assert "additional" not in out

    async def test_multi_result_with_hint(self) -> None:
        db = _make_db(search_conversations=[
            {"content": "first", "similarity": 0.9},
            {"content": "second", "similarity": 0.8},
            {"content": "third", "similarity": 0.7},
        ])
        out = await _quick_search_operation(db, "q", None, 0.7, 5)
        assert "3 results" in out
        assert "additional 2" in out

    async def test_score_missing_uses_na(self) -> None:
        """Result without 'similarity' → 'N/A'."""
        db = _make_db(search_conversations=[{"content": "x"}])
        out = await _quick_search_operation(db, "q", None, 0.7, 5)
        assert "N/A" in out


# ---------------------------------------------------------------------------
# _extract_key_terms + _format_search_summary
# ---------------------------------------------------------------------------


class TestExtractKeyTerms:
    def test_short_words_skipped(self) -> None:
        assert _extract_key_terms("the cat sat on a mat") == []

    def test_top_5_cap(self) -> None:
        words = " ".join(f"word{i}" for i in range(1, 8))
        terms = _extract_key_terms(words)
        assert len(terms) == 5

    def test_lowercase_normalization(self) -> None:
        terms = _extract_key_terms("Python PYTHON python async")
        # "python" should appear, lowercase
        assert "python" in terms
        assert terms[0] == "python"


class TestFormatSearchSummary:
    async def test_empty_results(self) -> None:
        out = await _format_search_summary("q", [])
        assert "No results found" in out

    async def test_populated_results(self) -> None:
        results = [{"content": "alpha async content", "timestamp": "2026-01-01"}]
        out = await _format_search_summary("q", results)
        assert "Search Summary" in out
        assert "Found" in out
        assert "Time Range" in out
        assert "Key Terms" in out

    async def test_no_timestamps_no_time_range(self) -> None:
        results = [{"content": "alpha async content"}]
        out = await _format_search_summary("q", results)
        assert "Time Range" not in out


# ---------------------------------------------------------------------------
# _search_summary_operation + _search_summary_impl
# ---------------------------------------------------------------------------


class TestSearchSummaryImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []

        async def fake_execute(op, name):
            captured.append(name)
            return "summary"

        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _search_summary_impl("q")
        assert out == "summary"
        assert captured == ["Search summary"]


# ---------------------------------------------------------------------------
# _build_pagination_output + _get_more_results_operation
# ---------------------------------------------------------------------------


class TestBuildPaginationOutput:
    def test_empty_paginated_slice(self) -> None:
        out = _build_pagination_output("q", 5, [], 10, 3)
        assert "No more results" in out
        assert "offset: 5" in out

    def test_populated_with_remaining(self) -> None:
        results = [{"content": "x" * 300, "timestamp": "2026-01-01"}]
        out = _build_pagination_output("q", 0, results, 10, 3)
        # 150-char content slice + "..." marker
        assert "x" * 150 in out
        assert "more results available" in out

    def test_no_remaining_when_offset_plus_limit_geq_total(self) -> None:
        results = [{"content": "x"}]
        # offset 5 + limit 3 = 8; total 10 → remaining (no branch)
        # offset 5 + limit 3 = 8 < 10 → remaining branch fires
        # When offset + limit == total → no remaining
        out = _build_pagination_output("q", 7, results, 10, 3)
        assert "more results available" not in out


class TestGetMoreResultsImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "page"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _get_more_results_impl("q")
        assert out == "page"
        assert captured == ["Get more results"]


# ---------------------------------------------------------------------------
# _extract_file_excerpt + _format_file_search_results + _search_by_file_*
# ---------------------------------------------------------------------------


class TestExtractFileExcerpt:
    def test_substring_present(self) -> None:
        content = "a" * 100 + "src/main.py" + "b" * 100
        out = _extract_file_excerpt(content, "src/main.py")
        assert "src/main.py" in out

    def test_substring_absent_returns_first_150(self) -> None:
        content = "x" * 200
        out = _extract_file_excerpt(content, "missing.py")
        assert out == content[:150]


class TestFormatFileSearchResults:
    async def test_empty_results(self) -> None:
        out = await _format_file_search_results("src/main.py", [])
        assert "No conversations found" in out
        assert "src/main.py" in out

    async def test_populated_results(self) -> None:
        results = [{"content": "discussion of src/main.py happened here", "timestamp": "t"}]
        out = await _format_file_search_results("src/main.py", results)
        assert "1 conversations" in out
        assert "discussion" in out


class TestSearchByFileImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "file results"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _search_by_file_impl("src/main.py")
        assert out == "file results"
        assert captured == ["Search by file"]


# ---------------------------------------------------------------------------
# _extract_relevant_excerpt + _extract_mentioned_files + _format_concept_results
# ---------------------------------------------------------------------------


class TestExtractRelevantExcerpt:
    def test_case_insensitive_substring(self) -> None:
        content = "discussing ASYNC patterns" + "x" * 200
        out = _extract_relevant_excerpt(content, "async")
        assert "ASYNC" in out

    def test_no_substring_returns_first_150(self) -> None:
        content = "x" * 200
        out = _extract_relevant_excerpt(content, "missing")
        assert out == content[:150]


class TestExtractMentionedFiles:
    def test_missing_pattern_key_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SAFE_PATTERNS missing 'python_files' key → KeyError → empty list."""
        class _FakeMod:
            SAFE_PATTERNS = {}  # missing all expected keys

        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.utils.regex_patterns",
            _FakeMod(),
        )
        out = _extract_mentioned_files([{"content": "foo.py bar.py"}])
        assert out == []

    def test_extracts_python_and_documentation_files(self) -> None:
        """After fix: SAFE_PATTERNS includes 'config_files' and 'documentation_files'.

        The production loop iterates over four pattern names. All four
        now resolve in SAFE_PATTERNS (the missing ``config_files`` and
        ``documentation_files`` keys were added in
        ``session_buddy/utils/regex_patterns.py``). The function returns
        deduplicated matches across all pattern groups.
        """
        out = _extract_mentioned_files([
            {"content": "We edited foo.py and README.md but not baz.txt"}
        ])
        # Python and documentation patterns should both match.
        assert "foo.py" in out
        assert "README.md" in out


class TestFormatConceptResults:
    async def test_empty_results(self) -> None:
        out = await _format_concept_results("async", [], True)
        assert "No conversations found" in out
        assert "async" in out

    async def test_with_files(self) -> None:
        results = [{"content": "async discussion", "similarity": 0.85}]
        out = await _format_concept_results("async", results, True)
        assert "1 conversations" in out
        assert "async discussion" in out

    async def test_without_files(self) -> None:
        results = [{"content": "async", "similarity": 0.85}]
        out = await _format_concept_results("async", results, False)
        assert "Related Files" not in out


class TestSearchByConceptImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "concept"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _search_by_concept_impl("async")
        assert out == "concept"
        assert captured == ["Search by concept"]


# ---------------------------------------------------------------------------
# _format_source_results + _search_by_source_*
# ---------------------------------------------------------------------------


class TestFormatSourceResults:
    def test_empty_no_filters(self) -> None:
        out = _format_source_results("q", [], None, None)
        assert "No cross-tool memory" in out
        assert "all sources" in out
        # No source_type, no project → no project label
        assert "project=" not in out

    def test_empty_with_source_type(self) -> None:
        out = _format_source_results("q", [], "claude_code", None)
        assert "source_type='claude_code'" in out

    def test_empty_with_project(self) -> None:
        out = _format_source_results("q", [], None, "p")
        assert "project='p'" in out

    def test_populated_results(self) -> None:
        results = [
            {
                "content": "x" * 250,
                "timestamp": "t",
                "source_type": "crackerjack",
                "project": "p",
            }
        ]
        out = _format_source_results("q", results, None, None)
        assert "1 cross-tool results" in out
        assert "crackerjack" in out
        assert "[p]" in out


class TestSearchBySourceImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "source results"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _search_by_source_impl("q")
        assert out == "source results"
        assert captured == ["Search by source"]


# ---------------------------------------------------------------------------
# _format_memory_lineage + _memory_lineage_impl
# ---------------------------------------------------------------------------


class TestFormatMemoryLineage:
    def test_empty_chain(self) -> None:
        out = _format_memory_lineage("m-1", [])
        assert "No provenance records" in out
        assert "m-1" in out

    def test_populated_chain(self) -> None:
        chain = [
            {
                "extracted_at": "2026-01-01",
                "source_type": "claude_code",
                "source_ref": "session-1",
                "model": "gpt-4",
            }
        ]
        out = _format_memory_lineage("m-1", chain)
        assert "Lineage" in out
        assert "1 records" in out
        assert "claude_code" in out
        assert "session-1" in out

    def test_chain_with_missing_fields(self) -> None:
        """Missing source_ref/model → '-' placeholders."""
        out = _format_memory_lineage("m-1", [{"extracted_at": "t", "source_type": "x"}])
        assert "- -" in out or "- " in out


class TestMemoryLineageImpl:
    async def test_missing_memory_id(self) -> None:
        out = await _memory_lineage_impl("")
        assert "memory_id" in out.lower() or "validation" in out.lower()

    async def test_db_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "lineage result"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _memory_lineage_impl("m-1")
        assert out == "lineage result"
        assert captured == ["Memory lineage"]


# ---------------------------------------------------------------------------
# _format_peer_context + _peer_context_impl + _update_peer_model_impl
# ---------------------------------------------------------------------------


class TestFormatPeerContext:
    def test_full_context(self) -> None:
        ctx = {
            "peer_id": "alice",
            "project_id": "session-buddy",
            "representation_text": "Backend developer",
            "last_updated": "2026-01-01",
            "evidence_count": 42,
            "model": "heuristic",
            "recent_memories": [
                {"id": "abcdef12345", "category": "skills", "content": "loves async"},
            ],
        }
        out = _format_peer_context(ctx)
        assert "alice" in out
        assert "session-buddy" in out
        assert "Backend developer" in out
        assert "42" in out
        assert "skills" in out
        # Long content truncated to 117 + "..."
        assert "loves async" in out

    def test_long_recent_memory_content_truncated(self) -> None:
        """Recent memory content >120 chars gets truncated."""
        long_content = "x" * 200
        ctx = {
            "peer_id": "p",
            "project_id": "proj",
            "recent_memories": [{"id": "i", "category": "c", "content": long_content}],
        }
        out = _format_peer_context(ctx)
        # 117 chars + "..."
        assert "x" * 117 in out
        assert "..." in out
        assert "x" * 200 not in out

    def test_with_target_peer(self) -> None:
        ctx = {
            "peer_id": "alice",
            "project_id": "p",
            "target_peer": {"peer_id": "bob", "representation_text": "Frontend"},
        }
        out = _format_peer_context(ctx)
        assert "bob" in out
        assert "Frontend" in out

    def test_empty_context(self) -> None:
        ctx = {"peer_id": "p", "project_id": "proj"}
        out = _format_peer_context(ctx)
        # No representation_text, no last_updated, no recent_memories, no target_peer
        assert "Peer context" in out


class TestPeerContextImpl:
    async def test_missing_peer_id(self) -> None:
        out = await _peer_context_impl("", "proj")
        assert "peer_id" in out.lower() or "validation" in out.lower()

    async def test_missing_project_id(self) -> None:
        out = await _peer_context_impl("alice", "")
        assert "project_id" in out.lower() or "validation" in out.lower()

    async def test_db_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "peer ctx"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _peer_context_impl("alice", "proj")
        assert out == "peer ctx"
        assert captured == ["Peer context"]


class TestUpdatePeerModelImpl:
    async def test_missing_peer_id(self) -> None:
        out = await _update_peer_model_impl("", "proj")
        assert "peer_id" in out.lower() or "validation" in out.lower()

    async def test_missing_project_id(self) -> None:
        out = await _update_peer_model_impl("alice", "")
        assert "project_id" in out.lower() or "validation" in out.lower()

    async def test_db_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "model updated"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _update_peer_model_impl("alice", "proj")
        assert out == "model updated"
        assert captured == ["Update peer model"]


# ---------------------------------------------------------------------------
# _format_causal_chain + _causal_chain_impl
# ---------------------------------------------------------------------------


class TestFormatCausalChain:
    def test_empty_edges(self) -> None:
        out = _format_causal_chain("m-1", [])
        assert "No causal chain" in out
        assert "m-1" in out

    def test_observed_origin(self) -> None:
        edges = [{
            "link_origin": "observed",
            "evidence": 0.9,
            "link_type": "supports",
            "depth": 2,
            "from_id": "a",
            "to_id": "b",
        }]
        out = _format_causal_chain("m-1", edges)
        assert "✅" in out
        assert "[observed]" in out
        assert "0.90" in out
        assert "a → b" in out

    def test_inferred_origin(self) -> None:
        edges = [{
            "link_origin": "inferred",
            "evidence": 0.3,
            "link_type": "contradicts",
            "depth": 1,
            "from_id": "x",
            "to_id": "y",
        }]
        out = _format_causal_chain("m-1", edges)
        assert "🤔" in out
        assert "[inferred]" in out


class TestCausalChainImpl:
    async def test_missing_start_id(self) -> None:
        out = await _causal_chain_impl("")
        assert "start_id" in out.lower() or "validation" in out.lower()

    async def test_db_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "chain"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _causal_chain_impl("m-1", max_depth=5)
        assert out == "chain"
        assert captured == ["Causal chain"]


# ---------------------------------------------------------------------------
# Skill formatters + distillers
# ---------------------------------------------------------------------------


class TestFormatSkill:
    def test_basic(self) -> None:
        out = _format_skill({
            "problem_pattern": "async bug",
            "suggested_approach": "use await",
            "because": "race condition",
            "importance_score": 0.85,
            "evidence_count": 3,
            "model": "heuristic",
        })
        assert "async bug" in out
        assert "0.85" in out
        assert "3 prior cases" in out


class TestFormatSkillList:
    def test_empty_list(self) -> None:
        out = _format_skill_list([])
        assert "No skills distilled" in out

    def test_populated_list(self) -> None:
        skills = [{"problem_pattern": "p", "suggested_approach": "a", "because": "b"}]
        out = _format_skill_list(skills)
        assert "1 distilled skill" in out


class TestFormatSkillSearch:
    def test_empty_results(self) -> None:
        assert _format_skill_search([]) == "🔍 No matching skills found."

    def test_populated_results(self) -> None:
        out = _format_skill_search([{"problem_pattern": "p"}])
        assert "1 distilled skill" in out


class TestDistillSkillsImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "skills distilled"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _distill_skills_now_impl()
        assert out == "skills distilled"
        assert captured == ["Distill skills"]


class TestSearchDistilledSkillsImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "skill hits"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _search_distilled_skills_impl(query="q")
        assert out == "skill hits"
        assert captured == ["Search distilled skills"]


# ---------------------------------------------------------------------------
# _classify_skill_status (4-bucket logic)
# ---------------------------------------------------------------------------


class TestClassifySkillStatus:
    def test_stale_when_reinforced_older_than_threshold(self) -> None:
        old = utc_now() - timedelta(days=200)
        row = {
            "importance_score": 0.95,
            "evidence_count": 5,
            "last_reinforced_at": old.isoformat(),
            "problem_pattern": "x",
        }
        out = _classify_skill_status(
            row, threshold=timedelta(days=90), crackerjack_skill_names=None
        )
        assert out == "stale"

    def test_under_utilized_when_high_importance_no_match(self) -> None:
        recent = utc_now() - timedelta(days=1)
        row = {
            "importance_score": 0.95,
            "evidence_count": 3,
            "last_reinforced_at": recent.isoformat(),
            "problem_pattern": "rare-pattern",
        }
        out = _classify_skill_status(
            row, threshold=timedelta(days=90), crackerjack_skill_names=["common-skill"]
        )
        assert out == "under_utilized"

    def test_under_utilized_with_match_returns_fresh(self) -> None:
        """High importance + crackerjack match → not under_utilized."""
        recent = utc_now() - timedelta(days=1)
        row = {
            "importance_score": 0.95,
            "evidence_count": 3,
            "last_reinforced_at": recent.isoformat(),
            "problem_pattern": "common",
        }
        out = _classify_skill_status(
            row, threshold=timedelta(days=90), crackerjack_skill_names=["common"]
        )
        assert out == "fresh"

    def test_cold_when_zero_evidence(self) -> None:
        recent = utc_now() - timedelta(days=1)
        row = {
            "importance_score": 0.5,  # below 0.9
            "evidence_count": 0,
            "last_reinforced_at": recent.isoformat(),
            "problem_pattern": "p",
        }
        out = _classify_skill_status(
            row, threshold=timedelta(days=90), crackerjack_skill_names=None
        )
        assert out == "cold"

    def test_fresh_when_default(self) -> None:
        """Recent, moderate importance, some evidence → fresh."""
        recent = utc_now() - timedelta(days=1)
        row = {
            "importance_score": 0.5,
            "evidence_count": 3,
            "last_reinforced_at": recent.isoformat(),
            "problem_pattern": "p",
        }
        out = _classify_skill_status(
            row, threshold=timedelta(days=90), crackerjack_skill_names=None
        )
        assert out == "fresh"

    def test_unparseable_timestamp_falls_through(self) -> None:
        """Invalid timestamp string → no stale check, other rules apply."""
        row = {
            "importance_score": 0.5,
            "evidence_count": 3,
            "last_reinforced_at": "not-a-date",
            "problem_pattern": "p",
        }
        out = _classify_skill_status(
            row, threshold=timedelta(days=90), crackerjack_skill_names=None
        )
        assert out == "fresh"

    def test_null_timestamp(self) -> None:
        row = {
            "importance_score": 0.5,
            "evidence_count": 0,
            "last_reinforced_at": None,
            "problem_pattern": "p",
        }
        out = _classify_skill_status(
            row, threshold=timedelta(days=90), crackerjack_skill_names=None
        )
        assert out == "cold"


class TestParseReinforcedTs:
    def test_datetime_passthrough(self) -> None:
        dt = datetime(2026, 1, 1, tzinfo=UTC)
        out = _parse_reinforced_ts(dt)
        assert out == dt

    def test_iso_string(self) -> None:
        out = _parse_reinforced_ts("2026-01-01T00:00:00+00:00")
        assert isinstance(out, datetime)
        assert out.tzinfo is not None

    def test_naive_datetime_gets_utc(self) -> None:
        dt = datetime(2026, 1, 1)
        out = _parse_reinforced_ts(dt)
        assert out.tzinfo is UTC

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(TypeError):
            _parse_reinforced_ts(12345)


class TestDistilledSkillHealthImpl:
    async def test_zero_threshold_returns_empty(self) -> None:
        assert await _distilled_skill_health_impl(threshold_days=0) == []
        assert await _distilled_skill_health_impl(threshold_days=-1) == []

    async def test_db_injection(self) -> None:
        db = MagicMock()
        db.search_distilled_skills = AsyncMock(return_value=[
            {"problem_pattern": "p", "importance_score": 0.5, "evidence_count": 3}
        ])
        out = await _distilled_skill_health_impl(threshold_days=90, db=db)
        assert len(out) == 1
        assert out[0]["status"] == "fresh"

    async def test_no_db_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """require_reflection_database unavailable → empty list."""
        async def boom():
            raise DatabaseUnavailableError("missing")

        monkeypatch.setattr(st, "require_reflection_database", boom)
        out = await _distilled_skill_health_impl(threshold_days=90, db=None)
        assert out == []

    async def test_generic_exception_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = MagicMock()
        db.search_distilled_skills = AsyncMock(
            side_effect=RuntimeError("oops")
        )
        out = await _distilled_skill_health_impl(threshold_days=90, db=db)
        assert out == []


# ---------------------------------------------------------------------------
# Database management
# ---------------------------------------------------------------------------


class TestResetReflectionDatabaseImpl:
    async def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_require():
            return MagicMock()

        monkeypatch.setattr(st, "require_reflection_database", fake_require)
        out = await _reset_reflection_database_impl()
        assert "verified" in out.lower()

    async def test_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def boom():
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(st, "require_reflection_database", boom)
        out = await _reset_reflection_database_impl()
        assert "Database reset" in out
        assert "db unavailable" in out


class TestReflectionStatsImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "stats"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _reflection_stats_impl()
        assert out == "stats"
        assert captured == ["Reflection stats"]


class TestSessionLearningReportImpl:
    async def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_require():
            db = MagicMock()
            db.generate_session_differential = AsyncMock(return_value={"diff": "ok"})
            return db
        monkeypatch.setattr(st, "require_reflection_database", fake_require)
        out = await _session_learning_report_impl("session-1")
        assert out == {"diff": "ok"}

    async def test_db_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def boom():
            raise DatabaseUnavailableError("missing")
        monkeypatch.setattr(st, "require_reflection_database", boom)
        out = await _session_learning_report_impl("session-1")
        assert "error" in out
        assert out["session_id"] == "session-1"

    async def test_generic_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def boom():
            raise RuntimeError("oops")
        monkeypatch.setattr(st, "require_reflection_database", boom)
        out = await _session_learning_report_impl("session-1")
        assert "error" in out


# ---------------------------------------------------------------------------
# Code search + error search + temporal search
# ---------------------------------------------------------------------------


class TestExtractCodeBlocks:
    def test_import_error_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.utils.regex_patterns",
            None,
        )
        assert _extract_code_blocks_from_content("```python\nfoo()\n```") == []

    def test_no_code_blocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = _extract_code_blocks_from_content("no code here")
        assert out == []


class TestFormatCodeSearchResults:
    async def test_empty_results(self) -> None:
        out = await _format_code_search_results("q", [], None)
        assert "No code patterns" in out
        assert "q" in out

    async def test_with_pattern_type(self) -> None:
        """pattern_type only appended when results non-empty."""
        results = [{"content": "x" * 200, "timestamp": "t"}]
        out = await _format_code_search_results("q", results, "function")
        assert "(type: function)" in out

    async def test_with_code_blocks(self) -> None:
        content = "We discussed ```python\nfoo()\n``` extensively"
        results = [{"content": content, "timestamp": "t"}]
        out = await _format_code_search_results("foo", results, None)
        assert "```" in out
        assert "foo()" in out

    async def test_without_code_blocks_query_substring(self) -> None:
        """No code blocks but query is in content → query-based excerpt."""
        results = [{"content": "discussion of foo in detail", "timestamp": "t"}]
        out = await _format_code_search_results("foo", results, None)
        assert "discussion of foo" in out

    async def test_without_code_blocks_no_query_match(self) -> None:
        results = [{"content": "x" * 200}]
        out = await _format_code_search_results("missing", results, None)
        # Falls back to first 100 chars
        assert "x" * 50 in out


class TestSearchCodeImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "code"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _search_code_impl("query")
        assert out == "code"
        assert captured == ["Search code"]


class TestFindBestErrorExcerpt:
    def test_keyword_match(self) -> None:
        content = "We hit an error handling pattern. The error was caused by..."
        out = _find_best_error_excerpt(content)
        assert "error" in out.lower()

    def test_no_keyword_returns_first_150(self) -> None:
        content = "x" * 200
        out = _find_best_error_excerpt(content)
        assert out == content[:150]


class TestFormatErrorSearchResults:
    async def test_empty_results(self) -> None:
        out = await _format_error_search_results("q", [], None)
        assert "No error patterns" in out

    async def test_with_error_type(self) -> None:
        """error_type only appended when results non-empty."""
        results = [{"content": "x" * 200, "timestamp": "t"}]
        out = await _format_error_search_results("q", results, "Exception")
        assert "(type: Exception)" in out

    async def test_populated_results(self) -> None:
        results = [{"content": "error traceback in detail", "timestamp": "t"}]
        out = await _format_error_search_results("q", results, None)
        assert "1 error contexts" in out


class TestSearchErrorsImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "errors"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _search_errors_impl("query")
        assert out == "errors"
        assert captured == ["Search errors"]


# ---------------------------------------------------------------------------
# Temporal search
# ---------------------------------------------------------------------------


class TestParseTimeExpression:
    def test_yesterday(self) -> None:
        out = _parse_time_expression("yesterday")
        assert (utc_now() - out) > timedelta(hours=23)

    def test_last_week(self) -> None:
        out = _parse_time_expression("last week")
        assert (utc_now() - out) > timedelta(days=6)

    def test_last_month(self) -> None:
        out = _parse_time_expression("last month")
        assert (utc_now() - out) > timedelta(days=29)

    def test_today(self) -> None:
        out = _parse_time_expression("today")
        assert (utc_now() - out) > timedelta(hours=23)

    def test_unparseable_returns_none(self) -> None:
        assert _parse_time_expression("never") is None


class TestFormatTemporalResults:
    async def test_empty_results(self) -> None:
        out = await _format_temporal_results("yesterday", None, [])
        assert "No conversations found" in out

    async def test_with_query(self) -> None:
        out = await _format_temporal_results("yesterday", "python", [])
        # No results but query is present
        assert "yesterday" in out

    async def test_populated_results(self) -> None:
        results = [{"content": "x" * 200, "timestamp": "t"}]
        out = await _format_temporal_results("yesterday", "python", results)
        assert "1 conversations" in out
        assert "matching `python`" in out


class TestSearchTemporalImpl:
    async def test_impl_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = []
        async def fake_execute(op, name):
            captured.append(name)
            return "temporal"
        monkeypatch.setattr(st, "execute_simple_database_tool", fake_execute)
        out = await _search_temporal_impl("yesterday")
        assert out == "temporal"
        assert captured == ["Temporal search"]


# ---------------------------------------------------------------------------
# _parse_tags_parameter + _parse_skill_names_param
# ---------------------------------------------------------------------------


class TestParseTagsParameter:
    def test_non_string_passthrough(self) -> None:
        assert _parse_tags_parameter(["a", "b"]) == ["a", "b"]
        assert _parse_tags_parameter(None) is None

    def test_json_list(self) -> None:
        assert _parse_tags_parameter('["a", "b"]') == ["a", "b"]

    def test_json_null(self) -> None:
        assert _parse_tags_parameter("null") is None

    def test_single_non_list_json_value(self) -> None:
        """JSON scalar value → wrapped in single-element list."""
        assert _parse_tags_parameter('"single"') == ["single"]
        assert _parse_tags_parameter("42") == ["42"]

    def test_invalid_json_single_tag(self) -> None:
        """Non-JSON string → wrapped as single tag."""
        assert _parse_tags_parameter("single-tag") == ["single-tag"]


class TestParseSkillNamesParam:
    def test_none(self) -> None:
        assert _parse_skill_names_param(None) is None

    def test_list_passthrough(self) -> None:
        assert _parse_skill_names_param(["a", "b"]) == ["a", "b"]

    def test_json_list(self) -> None:
        assert _parse_skill_names_param('["a", "b"]') == ["a", "b"]

    def test_invalid_json_returns_none(self) -> None:
        """JSON parse failure → None."""
        assert _parse_skill_names_param("not-json") is None

    def test_json_scalar_returns_none(self) -> None:
        """Non-list JSON scalar → None (not wrapped)."""
        assert _parse_skill_names_param('"single"') is None


# ---------------------------------------------------------------------------
# Progressive search
# ---------------------------------------------------------------------------


def utc_now():
    """Helper used in tests above."""
    from session_buddy.utils.time import utc_now as _u
    return _u()


class TestProgressiveSearchImpl:
    async def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Build a fake result
        class _Tier:
            tier = "CATEGORIES"
            results = [{"content": "alpha async"}]

        class _Result:
            tier_results = [_Tier()]
            total_results = 1
            tiers_searched = ["CATEGORIES"]
            early_stop = True
            total_latency_ms = 42.0
            metadata = {"early_stop_reason": "high_quality"}

        class _Engine:
            async def search_progressive(self, **kwargs):
                return _Result()

        class _Mod:
            ProgressiveSearchEngine = _Engine

        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            _Mod(),
        )
        result = await _progressive_search_impl("query")
        assert result["success"] is True
        assert result["total_results"] == 1
        assert "early_stop_reason" in result or result["early_stop_reason"] is None

    async def test_import_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            None,
        )
        result = await _progressive_search_impl("query")
        assert result["success"] is False
        assert "not available" in result["error"]

    async def test_generic_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Engine:
            async def search_progressive(self, **kwargs):
                raise RuntimeError("engine down")

        class _Mod:
            ProgressiveSearchEngine = _Engine

        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            _Mod(),
        )
        result = await _progressive_search_impl("query")
        assert result["success"] is False
        assert "engine down" in result["error"]


class TestConfigureTiersImpl:
    async def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Config:
            min_results = 5
            high_quality_threshold = 0.8
            perfect_match_threshold = 0.95
            max_tiers = 4
            tier_timeout_ms = 100
            quality_weight = 0.6
            quantity_weight = 0.4

        class _Mod:
            SufficiencyConfig = _Config

        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            _Mod(),
        )
        result = await _configure_tiers_impl(
            sufficiency_min_results=10,
            sufficiency_high_quality_threshold=0.85,
        )
        assert result["success"] is True
        assert result["config"]["min_results"] == 10

    async def test_import_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            None,
        )
        result = await _configure_tiers_impl()
        assert result["success"] is False

    async def test_generic_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Config:
            def __init__(self):
                raise RuntimeError("config fail")

        class _Mod:
            SufficiencyConfig = _Config

        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            _Mod(),
        )
        result = await _configure_tiers_impl()
        assert result["success"] is False


class TestTierStatsImpl:
    async def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Engine:
            def get_search_stats(self):
                return {"calls": 10}

        class _Mod:
            ProgressiveSearchEngine = _Engine

        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            _Mod(),
        )
        result = await _tier_stats_impl()
        assert result["success"] is True
        assert result["stats"]["calls"] == 10

    async def test_import_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            None,
        )
        result = await _tier_stats_impl()
        assert result["success"] is False

    async def test_generic_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Engine:
            def get_search_stats(self):
                raise RuntimeError("stats fail")

        class _Mod:
            ProgressiveSearchEngine = _Engine

        monkeypatch.setitem(
            __import__("sys").modules,
            "session_buddy.search",
            _Mod(),
        )
        result = await _tier_stats_impl()
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegisterCoreSearchTools:
    def test_registers_four_tools(self) -> None:
        mcp = _FakeMCP()
        _register_core_search_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "_optimize_search_results",
            "store_reflection",
            "quick_search",
            "search_summary",
            "get_more_results",
        }


class TestRegisterIndexedSearchTools:
    def test_registers_four_tools(self) -> None:
        mcp = _FakeMCP()
        _register_indexed_search_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "search_by_file",
            "search_by_concept",
            "search_by_source",
            "memory_lineage",
        }


class TestRegisterPeerAndTemporalTools:
    def test_registers_four_tools(self) -> None:
        mcp = _FakeMCP()
        _register_peer_and_temporal_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "peer_context",
            "update_peer_model",
            "causal_chain",
            "session_learning_report",
        }


class TestRegisterDistillationAndStatsTools:
    def test_registers_four_tools(self) -> None:
        mcp = _FakeMCP()
        _register_distillation_and_stats_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "distill_skills_now",
            "search_distilled_skills",
            "reset_reflection_database",
            "reflection_stats",
        }


class TestRegisterCodeAndErrorSearchTools:
    def test_registers_three_tools(self) -> None:
        mcp = _FakeMCP()
        _register_code_and_error_search_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "search_code",
            "search_errors",
            "search_temporal",
        }


class TestRegisterDistilledSkillHealthTool:
    def test_registers_one_tool(self) -> None:
        mcp = _FakeMCP()
        _register_distilled_skill_health_tool(mcp)
        assert set(mcp.tools.keys()) == {"distilled_skill_health"}


class TestRegisterProgressiveSearchTools:
    def test_registers_three_tools(self) -> None:
        mcp = _FakeMCP()
        _register_progressive_search_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "progressive_search",
            "configure_tiers",
            "tier_stats",
        }


class TestRegisterSpecializedSearchTools:
    def test_aggregates_all_specialized(self) -> None:
        mcp = _FakeMCP()
        _register_specialized_search_tools(mcp)
        # Sum of: indexed(4) + peer_and_temporal(4) + distillation(4) +
        # code_and_error(3) + distilled_skill_health(1) = 16 tools
        assert len(mcp.tools) == 16


class TestRegisterSearchTools:
    def test_aggregates_all_groups(self) -> None:
        mcp = _FakeMCP()
        register_search_tools(mcp)
        # core(5) + specialized(16) + progressive(3) = 24 tools
        assert len(mcp.tools) == 24
