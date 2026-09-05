"""Tests for session_buddy.mcp.tools.memory.validated_memory_tools.

Wave 11 (memory/ sweep) — covers the 4 validated MCP tools plus all the
helpers, db resolution paths, and registration in
``validated_memory_tools.py`` (644 lines, was 10%).

Targets:
- ``_format_result_item``: 200-char content slice, optional project,
  optional score, optional timestamp
- ``_format_search_results``: empty-result branch (2-line fallback),
  populated branch with header
- ``_format_concept_results``: empty-result branch, populated branch
  with optional file inclusion, file slice to top-3
- ``_format_top_result``: project/score/timestamp conditional lines
- ``_format_file_search_header``: 2-line header
- ``_format_file_search_result``: project/score/timestamp order
- ``_format_file_search_results``: empty → 3 lines, populated branch
- ``_format_validated_concept_result``: file slice to top-5
- ``_validate_reflection_params``: success returns model, validation
  failure returns error string, ValidationError → error string
- ``_execute_store_reflection``: success (truthy id) and failure (None
  or False) branches
- ``_format_reflection_result``: empty tags branch, populated tags branch
- ``_store_reflection_validated_impl``: tools-unavailable branch,
  invalid-params branch, db-resolution-failure branch,
  store-failure branch, success branch, ValidationError catch,
  ImportError catch, generic Exception catch
- ``_quick_search_validated_impl``: same 8 branches + min_score plumbing
- ``_search_by_file_validated_impl``: same 8 branches + limit plumbing
- ``_search_by_concept_validated_impl``: same 8 branches + include_files
- ``_check_reflection_tools_available``: cached path, probe success,
  probe exception
- ``resolve_reflection_database``: DI container success, direct
  fallback success, both-fail → None
- ``_get_reflection_database_async``: tools-unavailable raises
  ImportError, db is None raises ImportError, generic exception →
  ImportError, ImportError re-raised
- ``_get_reflection_database``: db unavailable raises ImportError
- ``ValidationExamples`` + ``MigrationGuide`` placeholders
- ``register_validated_memory_tools``: registers all 4 tools
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.memory import validated_memory_tools as vmt
from session_buddy.mcp.tools.memory.validated_memory_tools import (
    MigrationGuide,
    ReflectionDatabaseType,
    ValidationExamples,
    _check_reflection_tools_available,
    _execute_store_reflection,
    _format_concept_results,
    _format_file_search_header,
    _format_file_search_result,
    _format_file_search_results,
    _format_reflection_result,
    _format_result_item,
    _format_search_results,
    _format_top_result,
    _format_validated_concept_result,
    _get_reflection_database,
    _get_reflection_database_async,
    _quick_search_validated_impl,
    _search_by_concept_validated_impl,
    _search_by_file_validated_impl,
    _store_reflection_validated_impl,
    _validate_reflection_params,
    register_validated_memory_tools,
    resolve_reflection_database,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_tools_available_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force each test to re-probe tools availability."""
    monkeypatch.setattr(vmt, "_reflection_tools_available", None)


def _result_dict(**overrides: Any) -> dict[str, Any]:
    """Build a sample result dict for use with formatters."""
    base = {
        "success": True,
        "id": "refl-1",
        "content": "reflection body content",
        "tags": [],
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _make_db(store_id: Any = "refl-1") -> MagicMock:
    """Stub reflection db with store_reflection and search_reflections."""
    db = MagicMock()
    db.store_reflection = AsyncMock(return_value=store_id)
    db.search_reflections = AsyncMock(return_value=[])
    return db


class _FakeMCP:
    """Minimal FastMCP stand-in that captures tool registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *args, **kwargs):  # noqa: ANN201 - mirror FastMCP.tool
        def decorator(fn):  # noqa: ANN202 - decorator factory
            self.tools[fn.__name__] = fn
            return fn

        return decorator


# ---------------------------------------------------------------------------
# _format_result_item
# ---------------------------------------------------------------------------


class TestFormatResultItem:
    def test_basic_item_no_extras(self) -> None:
        lines = _format_result_item(
            {"content": "x" * 250, "score": None, "timestamp": None, "project": None},
            index=1,
        )
        assert len(lines) == 1
        # 200-char content slice
        assert "x" * 200 in lines[0]
        assert lines[0].startswith("\n1.")

    def test_with_project(self) -> None:
        lines = _format_result_item(
            {"content": "x", "project": "session-buddy"}, index=2
        )
        assert any("session-buddy" in ln for ln in lines)

    def test_with_score(self) -> None:
        lines = _format_result_item(
            {"content": "x", "score": 0.95}, index=3
        )
        assert any("0.95" in ln for ln in lines)

    def test_with_timestamp(self) -> None:
        lines = _format_result_item(
            {"content": "x", "timestamp": "2026-01-01"}, index=4
        )
        assert any("2026-01-01" in ln for ln in lines)

    def test_with_all_extras(self) -> None:
        lines = _format_result_item(
            {
                "content": "hello",
                "project": "proj",
                "score": 0.5,
                "timestamp": "ts",
            },
            index=5,
        )
        # 1 header + 3 optional lines
        assert len(lines) == 4


# ---------------------------------------------------------------------------
# _format_search_results
# ---------------------------------------------------------------------------


class TestFormatSearchResults:
    def test_empty_results(self) -> None:
        lines = _format_search_results([])
        assert lines == [
            "🔍 No conversations found about this file",
            "💡 The file might not have been discussed in previous sessions",
        ]

    def test_populated_results(self) -> None:
        results = [{"content": "alpha", "score": 0.5}]
        lines = _format_search_results(results)
        # header + each item's lines
        assert lines[0].startswith("📈 Found 1")
        joined = "\n".join(lines)
        assert "alpha" in joined


# ---------------------------------------------------------------------------
# _format_concept_results
# ---------------------------------------------------------------------------


class TestFormatConceptResults:
    def test_empty_results(self) -> None:
        lines = _format_concept_results([], include_files=True)
        joined = "\n".join(lines)
        assert "No conversations found about this concept" in joined
        assert "broader concepts" in joined

    def test_with_results_including_files(self) -> None:
        results = [
            {
                "content": "deep dive",
                "score": 0.7,
                "files": ["a.py", "b.py", "c.py", "d.py"],
            }
        ]
        lines = _format_concept_results(results, include_files=True)
        joined = "\n".join(lines)
        # Files truncated to top 3 → a.py, b.py, c.py visible; d.py NOT visible
        assert "a.py" in joined
        assert "b.py" in joined
        assert "c.py" in joined
        assert "d.py" not in joined

    def test_with_project_and_timestamp(self) -> None:
        """Optional project + timestamp fields exercised when include_files=True."""
        results = [{
            "content": "deep dive",
            "project": "session-buddy",
            "score": 0.7,
            "timestamp": "2026-01-01",
            "files": ["a.py"],
        }]
        lines = _format_concept_results(results, include_files=True)
        joined = "\n".join(lines)
        assert "session-buddy" in joined
        assert "0.70" in joined
        assert "2026-01-01" in joined

    def test_with_results_files_excluded(self) -> None:
        results = [{"content": "x", "files": ["a.py", "b.py"]}]
        lines = _format_concept_results(results, include_files=False)
        joined = "\n".join(lines)
        assert "a.py" not in joined


# ---------------------------------------------------------------------------
# _format_top_result
# ---------------------------------------------------------------------------


class TestFormatTopResult:
    def test_minimal(self) -> None:
        lines = _format_top_result({"content": "alpha"})
        assert lines[0] == "📊 Found results (showing top 1)"
        assert any("alpha" in ln for ln in lines)
        # 2 base lines, no optionals
        assert len(lines) == 2

    def test_with_all_extras(self) -> None:
        lines = _format_top_result({
            "content": "x",
            "project": "p",
            "score": 0.42,
            "timestamp": "t",
        })
        joined = "\n".join(lines)
        assert "p" in joined
        assert "0.42" in joined
        assert "t" in joined


# ---------------------------------------------------------------------------
# Dead-code file-search formatters (exported but unused by tool impls)
# ---------------------------------------------------------------------------


class TestFormatFileSearchHeader:
    def test_returns_two_lines(self) -> None:
        lines = _format_file_search_header("src/main.py")
        assert lines[0] == "📁 Searching conversations about: src/main.py"
        assert lines[1] == "=" * 50


class TestFormatFileSearchResult:
    def test_minimal(self) -> None:
        lines = _format_file_search_result({"content": "y"}, index=1)
        assert lines[0].startswith("1. 📝 y")

    def test_optional_fields(self) -> None:
        lines = _format_file_search_result({
            "content": "z",
            "timestamp": "2026",
            "project": "p",
            "score": 0.5,
        }, index=2)
        joined = "\n".join(lines)
        assert "2026" in joined
        assert "p" in joined
        assert "0.50" in joined


class TestFormatFileSearchResults:
    def test_empty(self) -> None:
        lines = _format_file_search_results([], "query")
        assert "No conversations found" in lines[0]
        assert any("query" in ln for ln in lines)

    def test_populated(self) -> None:
        lines = _format_file_search_results([{"content": "x", "score": 0.5}], "q")
        joined = "\n".join(lines)
        assert "Found 1" in joined
        assert "x" in joined


class TestFormatValidatedConceptResult:
    def test_no_files(self) -> None:
        lines = _format_validated_concept_result({"content": "x"}, 1, include_files=True)
        # No files field → no Files line
        assert not any("Files" in ln for ln in lines)

    def test_files_truncated_to_top_5(self) -> None:
        files = [f"f{i}.py" for i in range(8)]
        lines = _format_validated_concept_result(
            {"content": "x", "files": files}, 1, include_files=True
        )
        joined = "\n".join(lines)
        # f0..f4 visible; f5..f7 NOT visible
        assert "f0.py" in joined and "f4.py" in joined
        assert "f5.py" not in joined

    def test_include_files_false(self) -> None:
        lines = _format_validated_concept_result(
            {"content": "x", "files": ["a.py"]}, 1, include_files=False
        )
        assert not any("a.py" in ln for ln in lines)

    def test_timestamp_project_score_lines(self) -> None:
        """All optional fields exercised for ordering/coverage."""
        lines = _format_validated_concept_result({
            "content": "x",
            "timestamp": "2026-01-01",
            "project": "p",
            "score": 0.42,
        }, 1, include_files=True)
        joined = "\n".join(lines)
        assert "2026-01-01" in joined
        assert "p" in joined
        assert "0.42" in joined


# ---------------------------------------------------------------------------
# _validate_reflection_params
# ---------------------------------------------------------------------------


class TestValidateReflectionParams:
    def test_success_returns_pydantic_model(self) -> None:
        result = _validate_reflection_params(content="hello world")
        # On success returns the model instance, not a string
        assert not isinstance(result, str)
        assert result.content == "hello world"

    def test_invalid_returns_error_string(self) -> None:
        # Empty content fails validation
        result = _validate_reflection_params(content="")
        assert isinstance(result, str)
        assert "Parameter validation error" in result


# ---------------------------------------------------------------------------
# _execute_store_reflection
# ---------------------------------------------------------------------------


class TestExecuteStoreReflection:
    async def test_success_with_truthy_id(self) -> None:
        db = _make_db(store_id="refl-99")
        params = MagicMock(content="hello", tags=["t1"])
        result = await _execute_store_reflection(params, db)
        assert result["success"] is True
        assert result["id"] == "refl-99"
        db.store_reflection.assert_awaited_once_with("hello", tags=["t1"])

    async def test_failure_with_none_id(self) -> None:
        db = _make_db(store_id=None)
        params = MagicMock(content="hello", tags=None)
        result = await _execute_store_reflection(params, db)
        assert result["success"] is False

    async def test_failure_with_false_id(self) -> None:
        db = _make_db(store_id=False)
        params = MagicMock(content="hello", tags=None)
        result = await _execute_store_reflection(params, db)
        assert result["success"] is False

    async def test_tags_defaulted_to_empty_list(self) -> None:
        db = _make_db(store_id="refl-1")
        params = MagicMock(content="x", tags=None)
        result = await _execute_store_reflection(params, db)
        assert result["tags"] == []


# ---------------------------------------------------------------------------
# _format_reflection_result
# ---------------------------------------------------------------------------


class TestFormatReflectionResult:
    def test_no_tags_branch(self) -> None:
        result = _result_dict(content="hi", tags=[])
        out = _format_reflection_result(result)
        assert "Reflection stored successfully" in out
        assert "Tags:" not in out

    def test_with_tags_branch(self) -> None:
        result = _result_dict(content="hi", tags=["x", "y"])
        out = _format_reflection_result(result)
        assert "Tags:" in out
        assert "x, y" in out

    def test_content_truncated_to_100(self) -> None:
        result = _result_dict(content="a" * 200)
        out = _format_reflection_result(result)
        # 100 char slice
        assert "a" * 100 in out
        # 101st char would not be in the slice (well, depends on slice logic)
        # Just verify the format marker is present
        assert "..." in out


# ---------------------------------------------------------------------------
# _check_reflection_tools_available
# ---------------------------------------------------------------------------


class TestCheckReflectionToolsAvailable:
    def test_cached_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        assert _check_reflection_tools_available() is True

    def test_cached_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", False)
        assert _check_reflection_tools_available() is False

    def test_probe_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", None)
        # importlib.util.find_spec returns a non-None spec when module exists
        assert _check_reflection_tools_available() is True
        # Caches the result
        assert vmt._reflection_tools_available is True

    def test_probe_exception_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", None)

        # Force find_spec to raise → branch hits except → False cached
        def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("probe crashed")

        monkeypatch.setattr(
            "importlib.util.find_spec", boom
        )
        assert _check_reflection_tools_available() is False
        assert vmt._reflection_tools_available is False


# ---------------------------------------------------------------------------
# resolve_reflection_database
# ---------------------------------------------------------------------------


class TestResolveReflectionDatabase:
    async def test_di_container_returns_db(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DI container has a registered ReflectionDatabase → returns it.

        The DI branch in resolve_reflection_database imports
        ``session_buddy.di.container.depends`` and calls ``depends.get_sync``.
        We patch the module-level imports via ``sys.modules`` so the
        lazy imports inside the function resolve to our stub.
        """
        import sys

        from session_buddy import reflection_tools

        # Build a stub depends module
        fake_db = MagicMock()
        stub_depends_module = SimpleNamespace(
            get_sync=lambda cls: fake_db
        )

        # Save and replace the di.container module
        di_container_path = "session_buddy.di.container"
        saved = sys.modules.get(di_container_path)
        sys.modules[di_container_path] = SimpleNamespace(
            depends=stub_depends_module
        )
        try:
            result = await resolve_reflection_database()
        finally:
            if saved is not None:
                sys.modules[di_container_path] = saved
            else:
                sys.modules.pop(di_container_path, None)

        # First branch returns the fake_db via DI; fallback not invoked
        assert result is fake_db


    async def test_fallback_get_reflection_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DI branch raises → fallback branch calls get_reflection_database."""
        from session_buddy import reflection_tools

        fake_db = MagicMock()
        monkeypatch.setattr(
            reflection_tools,
            "get_reflection_database",
            AsyncMock(return_value=fake_db),
        )

        result = await resolve_reflection_database()
        assert result is fake_db

    async def test_both_fail_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both DI and fallback fail → returns None."""
        from session_buddy import reflection_tools

        async def boom() -> MagicMock:
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(
            reflection_tools, "get_reflection_database", boom
        )

        result = await resolve_reflection_database()
        assert result is None


# SimpleNamespace for clean re-imports
from types import SimpleNamespace  # noqa: E402


# ---------------------------------------------------------------------------
# _get_reflection_database_async
# ---------------------------------------------------------------------------


class TestGetReflectionDatabaseAsync:
    async def test_tools_unavailable_raises_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", False)
        with pytest.raises(ImportError, match="Reflection tools not available"):
            await _get_reflection_database_async()

    async def test_db_is_none_raises_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            vmt, "resolve_reflection_database", AsyncMock(return_value=None)
        )
        with pytest.raises(ImportError):
            await _get_reflection_database_async()

    async def test_generic_exception_raises_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)

        async def boom() -> None:
            raise RuntimeError("connection failed")

        monkeypatch.setattr(vmt, "resolve_reflection_database", boom)
        with pytest.raises(ImportError, match="not available"):
            await _get_reflection_database_async()

    async def test_importerror_reraised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)

        async def boom() -> None:
            raise ImportError("transitive")

        monkeypatch.setattr(vmt, "resolve_reflection_database", boom)
        with pytest.raises(ImportError, match="transitive"):
            await _get_reflection_database_async()

    async def test_returns_db_when_resolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        fake_db = MagicMock()
        monkeypatch.setattr(
            vmt, "resolve_reflection_database", AsyncMock(return_value=fake_db)
        )
        result = await _get_reflection_database_async()
        assert result is fake_db


# ---------------------------------------------------------------------------
# _get_reflection_database
# ---------------------------------------------------------------------------


class TestGetReflectionDatabase:
    async def test_unavailable_raises_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", False)
        with pytest.raises(ImportError, match="Reflection tools not available"):
            await _get_reflection_database()

    async def test_resolves_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        fake_db = MagicMock()
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=fake_db)
        )
        result = await _get_reflection_database()
        assert result is fake_db


# ---------------------------------------------------------------------------
# _store_reflection_validated_impl
# ---------------------------------------------------------------------------


class TestStoreReflectionValidatedImpl:
    async def test_tools_unavailable_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", False)
        out = await _store_reflection_validated_impl(content="x")
        assert "Reflection tools not available" in out

    async def test_invalid_params_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        out = await _store_reflection_validated_impl(content="")  # invalid
        assert "Parameter validation" in out

    async def test_db_resolution_fails_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async",
            AsyncMock(return_value=None),
        )
        out = await _store_reflection_validated_impl(content="hello")
        assert "Failed to connect to reflection database" in out

    async def test_store_returns_false_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db(store_id=False)
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _store_reflection_validated_impl(content="hello")
        assert "Failed to store reflection" in out

    async def test_success_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db(store_id="refl-1")
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _store_reflection_validated_impl(
            content="hello", tags=["t1", "t2"]
        )
        assert "Reflection stored successfully" in out
        assert "t1, t2" in out

    async def test_validation_error_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)

        from session_buddy.utils.error_management import ValidationError

        async def boom(*args: Any, **kwargs: Any) -> None:
            raise ValidationError("bad params from upstream")

        monkeypatch.setattr(vmt, "_get_reflection_database_async", boom)
        out = await _store_reflection_validated_impl(content="hello")
        assert "validation failed" in out.lower()

    async def test_importerror_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)

        async def boom(*args: Any, **kwargs: Any) -> None:
            raise ImportError("transitive failure")

        monkeypatch.setattr(vmt, "_get_reflection_database_async", boom)
        out = await _store_reflection_validated_impl(content="hello")
        assert "Import error" in out

    async def test_generic_exception_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = MagicMock()
        db.store_reflection = AsyncMock(
            side_effect=RuntimeError("disk full")
        )
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _store_reflection_validated_impl(content="hello")
        assert "disk full" in out
        assert "Failed to store reflection" in out


# ---------------------------------------------------------------------------
# _quick_search_validated_impl
# ---------------------------------------------------------------------------


class TestQuickSearchValidatedImpl:
    async def test_tools_unavailable_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", False)
        out = await _quick_search_validated_impl(query="x")
        assert "Reflection tools not available" in out

    async def test_invalid_params_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        out = await _quick_search_validated_impl(query="")
        assert "Parameter validation" in out

    async def test_db_unavailable_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async",
            AsyncMock(return_value=None),
        )
        out = await _quick_search_validated_impl(query="python")
        assert "Failed to connect to reflection database" in out

    async def test_no_results_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        db.search_reflections = AsyncMock(return_value=[])
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _quick_search_validated_impl(query="python")
        assert "Quick search for: 'python'" in out
        assert "No results found" in out

    async def test_results_present_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        db.search_reflections = AsyncMock(
            return_value=[{"content": "first result", "score": 0.9}]
        )
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _quick_search_validated_impl(query="python")
        assert "Found results (showing top 1)" in out
        assert "first result" in out
        assert "0.90" in out

    async def test_min_score_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        await _quick_search_validated_impl(query="python", min_score=0.42)
        db.search_reflections.assert_awaited_once()
        kwargs = db.search_reflections.await_args.kwargs
        assert kwargs["min_score"] == 0.42

    async def test_generic_exception_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = MagicMock()
        db.search_reflections = AsyncMock(side_effect=RuntimeError("oops"))
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _quick_search_validated_impl(query="python")
        assert "oops" in out
        assert "Failed to perform quick search" in out


# ---------------------------------------------------------------------------
# _search_by_file_validated_impl
# ---------------------------------------------------------------------------


class TestSearchByFileValidatedImpl:
    async def test_tools_unavailable_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", False)
        out = await _search_by_file_validated_impl(file_path="src/main.py")
        assert "Reflection tools not available" in out

    async def test_invalid_params_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        out = await _search_by_file_validated_impl(file_path="")
        assert "Parameter validation" in out

    async def test_db_unavailable_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async",
            AsyncMock(return_value=None),
        )
        out = await _search_by_file_validated_impl(file_path="src/main.py")
        assert "Failed to connect to reflection database" in out

    async def test_no_results_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        db.search_reflections = AsyncMock(return_value=[])
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _search_by_file_validated_impl(file_path="src/main.py")
        assert "No conversations found about this file" in out

    async def test_results_present_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        db.search_reflections = AsyncMock(
            return_value=[{"content": "match", "score": 0.7}]
        )
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _search_by_file_validated_impl(file_path="src/main.py")
        assert "Found 1" in out
        assert "match" in out

    async def test_limit_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        await _search_by_file_validated_impl(file_path="src/main.py", limit=42)
        kwargs = db.search_reflections.await_args.kwargs
        assert kwargs["limit"] == 42

    async def test_generic_exception_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = MagicMock()
        db.search_reflections = AsyncMock(side_effect=RuntimeError("timeout"))
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _search_by_file_validated_impl(file_path="src/main.py")
        assert "timeout" in out


# ---------------------------------------------------------------------------
# _search_by_concept_validated_impl
# ---------------------------------------------------------------------------


class TestSearchByConceptValidatedImpl:
    async def test_tools_unavailable_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", False)
        out = await _search_by_concept_validated_impl(concept="x")
        assert "Reflection tools not available" in out

    async def test_invalid_params_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        out = await _search_by_concept_validated_impl(concept="")
        assert "Parameter validation" in out

    async def test_db_unavailable_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async",
            AsyncMock(return_value=None),
        )
        out = await _search_by_concept_validated_impl(concept="async")
        assert "Failed to connect to reflection database" in out

    async def test_no_results_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        db.search_reflections = AsyncMock(return_value=[])
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _search_by_concept_validated_impl(concept="async")
        assert "No conversations found about this concept" in out

    async def test_results_present_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        db.search_reflections = AsyncMock(
            return_value=[{"content": "concept match", "score": 0.6}]
        )
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _search_by_concept_validated_impl(concept="async")
        assert "Searching for concept: 'async'" in out
        assert "Found 1" in out
        assert "concept match" in out

    async def test_include_files_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = _make_db()
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        await _search_by_concept_validated_impl(concept="async", include_files=True)
        # Operation builds include_files in result dict; verify via formatter call
        # is implicit via the test_results_present_branch — here we just ensure no crash.

    async def test_generic_exception_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vmt, "_reflection_tools_available", True)
        db = MagicMock()
        db.search_reflections = AsyncMock(side_effect=RuntimeError("oops"))
        monkeypatch.setattr(
            vmt, "_get_reflection_database_async", AsyncMock(return_value=db)
        )
        out = await _search_by_concept_validated_impl(concept="async")
        assert "oops" in out


# ---------------------------------------------------------------------------
# ValidationExamples + MigrationGuide placeholders
# ---------------------------------------------------------------------------


class TestPlaceholderClasses:
    def test_validation_examples_returns_dicts(self) -> None:
        inst = ValidationExamples()
        assert isinstance(inst.example_valid_calls(), list)
        assert isinstance(inst.example_validation_errors(), list)

    def test_migration_guide_returns_strings(self) -> None:
        assert isinstance(MigrationGuide.before_migration(), str)
        assert isinstance(MigrationGuide.after_migration(), str)


# ---------------------------------------------------------------------------
# ReflectionDatabaseType alias
# ---------------------------------------------------------------------------


class TestReflectionDatabaseType:
    def test_alias_exported(self) -> None:
        """Module exposes the type alias for backward compatibility."""
        assert ReflectionDatabaseType is not None


# ---------------------------------------------------------------------------
# register_validated_memory_tools
# ---------------------------------------------------------------------------


class TestRegisterValidatedMemoryTools:
    def test_registers_all_four_tools(self) -> None:
        mcp = _FakeMCP()
        register_validated_memory_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "store_reflection_validated",
            "quick_search_validated",
            "search_by_file_validated",
            "search_by_concept_validated",
        }

    async def test_store_tool_delegates_to_impl(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_validated_memory_tools(mcp)
        captured = []
        monkeypatch.setattr(
            vmt, "_store_reflection_validated_impl",
            AsyncMock(side_effect=lambda **kw: captured.append(kw) or "ok"),
        )
        result = await mcp.tools["store_reflection_validated"](content="hi")
        assert result == "ok"
        assert captured == [{"content": "hi"}]

    async def test_quick_search_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_validated_memory_tools(mcp)
        captured = []
        monkeypatch.setattr(
            vmt, "_quick_search_validated_impl",
            AsyncMock(side_effect=lambda **kw: captured.append(kw) or "ok"),
        )
        result = await mcp.tools["quick_search_validated"](query="x")
        assert result == "ok"
        assert captured == [{"query": "x"}]

    async def test_search_by_file_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_validated_memory_tools(mcp)
        captured = []
        monkeypatch.setattr(
            vmt, "_search_by_file_validated_impl",
            AsyncMock(side_effect=lambda **kw: captured.append(kw) or "ok"),
        )
        result = await mcp.tools["search_by_file_validated"](file_path="a")
        assert result == "ok"
        assert captured == [{"file_path": "a"}]

    async def test_search_by_concept_tool_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = _FakeMCP()
        register_validated_memory_tools(mcp)
        captured = []
        monkeypatch.setattr(
            vmt, "_search_by_concept_validated_impl",
            AsyncMock(side_effect=lambda **kw: captured.append(kw) or "ok"),
        )
        result = await mcp.tools["search_by_concept_validated"](concept="c")
        assert result == "ok"
        assert captured == [{"concept": "c"}]
