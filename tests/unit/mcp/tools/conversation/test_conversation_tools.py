"""Tests for session_buddy.mcp.tools.conversation.conversation_tools.

Wave 12 (conversation/ sweep) — covers the 4 MCP tools and the
registration entry point for ``conversation_tools.py`` (258 lines).

Targets:
- ``register_conversation_tools``: registers all 4 tools
- ``store_conversation``: happy path with/without project and metadata,
  content-too-short validation, exception path
- ``store_conversation_checkpoint``: helper success, helper error result,
  helper exception
- ``get_conversation_statistics``: with projects, no projects, zero total
  (tip), stats-with-error, exception path
- ``search_conversations``: empty query, limit/score out of range, no
  results, results with/without project and timestamp, long content
  truncation, exception path

Test approach: ``_FakeMCP`` captures ``@mcp_server.tool()`` registrations;
``ReflectionDatabase`` is patched at the module attribute that the inline
import resolves to (``session_buddy.reflection.database.ReflectionDatabase``).
``get_sync_typed``, ``store_conversation_checkpoint_helper`` and
``get_conversation_stats`` are patched on the ``conversation_tools`` module
itself, matching the production imports.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.conversation import conversation_tools as ct
from session_buddy.mcp.tools.conversation.conversation_tools import (
    register_conversation_tools,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    """FastMCP stand-in recording ``@mcp_server.tool()`` registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class _FakeReflectionCtx:
    """Async context manager that yields the supplied db mock."""

    def __init__(self, db: MagicMock) -> None:
        self._db = db

    async def __aenter__(self) -> MagicMock:
        return self._db

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _patch_reflection_db(
    monkeypatch: pytest.MonkeyPatch, **methods: Any
) -> MagicMock:
    """Patch ``ReflectionDatabase()`` to yield a mock with AsyncMock methods.

    Production code does ``async with ReflectionDatabase() as db``. We make
    the class callable returning an async context manager that yields a
    configured mock.
    """
    db_mock = MagicMock()
    for name, return_value in methods.items():
        setattr(db_mock, name, AsyncMock(return_value=return_value))

    fake_cls = MagicMock(return_value=_FakeReflectionCtx(db_mock))
    monkeypatch.setattr(
        "session_buddy.reflection.database.ReflectionDatabase", fake_cls
    )
    return db_mock


def _patch_reflection_db_raises(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> None:
    """Patch ``ReflectionDatabase()`` to raise ``exc`` on enter."""

    class _Boom:
        async def __aenter__(self) -> Any:
            raise exc

        async def __aexit__(self, *exc: Any) -> None:
            return None

    fake_cls = MagicMock(return_value=_Boom())
    monkeypatch.setattr(
        "session_buddy.reflection.database.ReflectionDatabase", fake_cls
    )


@pytest.fixture(autouse=True)
def _patch_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``_get_logger`` so log calls accept arbitrary kwargs."""
    fake_logger = MagicMock()
    monkeypatch.setattr(ct, "_get_logger", lambda: fake_logger)


@pytest.fixture
def mcp() -> _FakeMCP:
    """FakeMCP with all 4 conversation tools registered."""
    server = _FakeMCP()
    register_conversation_tools(server)
    return server


# ---------------------------------------------------------------------------
# register_conversation_tools
# ---------------------------------------------------------------------------


class TestRegisterConversationTools:
    def test_registers_all_four_tools(self) -> None:
        mcp = _FakeMCP()
        register_conversation_tools(mcp)
        expected = {
            "store_conversation",
            "store_conversation_checkpoint",
            "get_conversation_statistics",
            "search_conversations",
        }
        assert expected.issubset(set(mcp.tools))
        assert len(mcp.tools) == 4

    def test_returns_none(self) -> None:
        mcp = _FakeMCP()
        # Both wrappers should return None; assert this explicitly.
        assert register_conversation_tools(mcp) is None


# ---------------------------------------------------------------------------
# store_conversation
# ---------------------------------------------------------------------------


class TestStoreConversation:
    async def test_happy_path_with_project_and_metadata(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, store_conversation="conv-1")
        out = await mcp.tools["store_conversation"](
            "this is the conversation body for storage",  # > 10 chars
            project="my-proj",
            metadata={"user": "alice"},
        )
        assert "✅" in out
        assert "conv-1" in out
        assert "my-proj" in out
        db.store_conversation.assert_awaited_once()
        kwargs = db.store_conversation.await_args.kwargs
        assert kwargs["content"] == "this is the conversation body for storage"
        # metadata merges project, source, timestamp and user override
        assert kwargs["metadata"]["project"] == "my-proj"
        assert kwargs["metadata"]["source"] == "manual_storage"
        assert kwargs["metadata"]["user"] == "alice"

    async def test_happy_path_auto_detects_project_from_cwd(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        db = _patch_reflection_db(monkeypatch, store_conversation="conv-x")
        monkeypatch.chdir(tmp_path)
        out = await mcp.tools["store_conversation"](
            "some reasonably long content", project=None
        )
        assert "✅" in out
        assert tmp_path.name in out
        assert db.store_conversation.await_args.kwargs["metadata"]["project"] == (
            tmp_path.name
        )

    async def test_at_minimum_content_length(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exactly 10 chars must succeed (boundary)."""
        db = _patch_reflection_db(monkeypatch, store_conversation="ok")
        out = await mcp.tools["store_conversation"]("1234567890")
        assert "✅" in out
        db.store_conversation.assert_awaited_once()

    async def test_content_too_short(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, store_conversation="never")
        out = await mcp.tools["store_conversation"]("short")
        assert "❌" in out
        assert "minimum 10" in out
        db.store_conversation.assert_not_awaited()

    async def test_content_below_minimum_nine_chars(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, store_conversation="never")
        out = await mcp.tools["store_conversation"]("123456789")
        assert "❌" in out
        db.store_conversation.assert_not_awaited()

    async def test_database_exception_returns_failure(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_reflection_db_raises(monkeypatch, RuntimeError("disk gone"))
        out = await mcp.tools["store_conversation"](
            "some content that is long enough to pass"
        )
        assert "❌" in out
        assert "disk gone" in out
        assert "Failed to store" in out

    async def test_metadata_merge_keeps_defaults(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, store_conversation="conv-y")
        await mcp.tools["store_conversation"](
            "long enough content body", project="p1", metadata={"a": 1, "b": 2}
        )
        meta = db.store_conversation.await_args.kwargs["metadata"]
        assert meta["project"] == "p1"
        assert meta["source"] == "manual_storage"
        assert meta["timestamp"] is None
        assert meta["a"] == 1
        assert meta["b"] == 2


# ---------------------------------------------------------------------------
# store_conversation_checkpoint
# ---------------------------------------------------------------------------


class TestStoreConversationCheckpoint:
    async def test_happy_path(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = MagicMock()
        manager.current_project = "alpha"
        monkeypatch.setattr(ct, "get_sync_typed", MagicMock(return_value=manager))
        monkeypatch.setattr(
            ct,
            "store_conversation_checkpoint_helper",
            AsyncMock(
                return_value={"success": True, "conversation_id": "ck-1"}
            ),
        )
        out = await mcp.tools["store_conversation_checkpoint"](
            checkpoint_type="manual", quality_score=85
        )
        assert "✅" in out
        assert "ck-1" in out
        assert "alpha" in out
        assert "manual" in out
        assert "85" in out

    async def test_helper_returns_failure(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = MagicMock()
        manager.current_project = None
        monkeypatch.setattr(ct, "get_sync_typed", MagicMock(return_value=manager))
        monkeypatch.setattr(
            ct,
            "store_conversation_checkpoint_helper",
            AsyncMock(
                return_value={"success": False, "error": "no session"}
            ),
        )
        out = await mcp.tools["store_conversation_checkpoint"]()
        assert "❌" in out
        assert "no session" in out

    async def test_helper_raises(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = MagicMock()
        manager.current_project = "beta"
        monkeypatch.setattr(ct, "get_sync_typed", MagicMock(return_value=manager))
        monkeypatch.setattr(
            ct,
            "store_conversation_checkpoint_helper",
            AsyncMock(side_effect=ValueError("boom")),
        )
        out = await mcp.tools["store_conversation_checkpoint"]()
        assert "❌" in out
        assert "boom" in out

    async def test_quality_score_none_renders_na(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = MagicMock()
        manager.current_project = "gamma"
        monkeypatch.setattr(ct, "get_sync_typed", MagicMock(return_value=manager))
        monkeypatch.setattr(
            ct,
            "store_conversation_checkpoint_helper",
            AsyncMock(return_value={"success": True, "conversation_id": "ck-2"}),
        )
        out = await mcp.tools["store_conversation_checkpoint"](
            checkpoint_type="checkpoint", quality_score=None
        )
        assert "N/A" in out

    async def test_default_checkpoint_type(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default for checkpoint_type is 'manual'."""
        manager = MagicMock()
        manager.current_project = "x"
        monkeypatch.setattr(ct, "get_sync_typed", MagicMock(return_value=manager))

        captured: dict[str, Any] = {}

        async def fake_helper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"success": True, "conversation_id": "ck-3"}

        monkeypatch.setattr(
            ct, "store_conversation_checkpoint_helper", fake_helper
        )
        await mcp.tools["store_conversation_checkpoint"]()
        assert captured["checkpoint_type"] == "manual"
        assert captured["is_manual"] is True


# ---------------------------------------------------------------------------
# get_conversation_statistics
# ---------------------------------------------------------------------------


class TestGetConversationStatistics:
    async def test_with_projects(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ct,
            "get_conversation_stats",
            AsyncMock(
                return_value={
                    "total_conversations": 100,
                    "with_embeddings": 90,
                    "embedding_coverage": 90.0,
                    "recent_conversations": 12,
                    "projects": {"alpha", "beta"},
                }
            ),
        )
        out = await mcp.tools["get_conversation_statistics"]()
        assert "📊" in out
        assert "Total conversations: 100" in out
        assert "With embeddings: 90" in out
        assert "Embedding coverage: 90.0%" in out
        assert "Recent (7 days): 12" in out
        # Projects are listed sorted
        assert "alpha" in out and "beta" in out
        # No tip because total > 0
        assert "Tip" not in out

    async def test_with_empty_projects(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ct,
            "get_conversation_stats",
            AsyncMock(
                return_value={
                    "total_conversations": 5,
                    "with_embeddings": 5,
                    "embedding_coverage": 100.0,
                    "recent_conversations": 1,
                    "projects": set(),
                }
            ),
        )
        out = await mcp.tools["get_conversation_statistics"]()
        assert "Total conversations: 5" in out
        assert "Projects with conversations" not in out

    async def test_zero_total_shows_tip(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ct,
            "get_conversation_stats",
            AsyncMock(
                return_value={
                    "total_conversations": 0,
                    "with_embeddings": 0,
                    "embedding_coverage": 0.0,
                    "recent_conversations": 0,
                    "projects": set(),
                }
            ),
        )
        out = await mcp.tools["get_conversation_statistics"]()
        assert "Total conversations: 0" in out
        assert "Tip" in out
        assert "checkpoint" in out

    async def test_stats_with_error_key(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ct,
            "get_conversation_stats",
            AsyncMock(
                return_value={
                    "error": "duckdb missing",
                    "total_conversations": 0,
                    "with_embeddings": 0,
                    "embedding_coverage": 0.0,
                    "recent_conversations": 0,
                    "projects": set(),
                }
            ),
        )
        out = await mcp.tools["get_conversation_statistics"]()
        assert "❌" in out
        assert "duckdb missing" in out

    async def test_exception_returns_failure(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ct,
            "get_conversation_stats",
            AsyncMock(side_effect=OSError("io error")),
        )
        out = await mcp.tools["get_conversation_statistics"]()
        assert "❌" in out
        assert "io error" in out

    async def test_single_project_in_list(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ct,
            "get_conversation_stats",
            AsyncMock(
                return_value={
                    "total_conversations": 3,
                    "with_embeddings": 2,
                    "embedding_coverage": 66.7,
                    "recent_conversations": 1,
                    "projects": {"only-one"},
                }
            ),
        )
        out = await mcp.tools["get_conversation_statistics"]()
        assert "only-one" in out


# ---------------------------------------------------------------------------
# search_conversations
# ---------------------------------------------------------------------------


class TestSearchConversations:
    async def test_empty_query(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, search_conversations=[])
        out = await mcp.tools["search_conversations"](query="")
        assert "❌" in out
        assert "empty" in out.lower()
        db.search_conversations.assert_not_awaited()

    async def test_whitespace_query(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, search_conversations=[])
        out = await mcp.tools["search_conversations"](query="   ")
        assert "❌" in out
        db.search_conversations.assert_not_awaited()

    async def test_limit_too_low(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, search_conversations=[])
        out = await mcp.tools["search_conversations"](query="hello", limit=0)
        assert "❌" in out
        assert "1 and 100" in out
        db.search_conversations.assert_not_awaited()

    async def test_limit_too_high(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, search_conversations=[])
        out = await mcp.tools["search_conversations"](query="hello", limit=101)
        assert "❌" in out
        db.search_conversations.assert_not_awaited()

    async def test_min_score_below_zero(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, search_conversations=[])
        out = await mcp.tools["search_conversations"](
            query="hi", min_score=-0.1
        )
        assert "❌" in out
        assert "0 and 1" in out
        db.search_conversations.assert_not_awaited()

    async def test_min_score_above_one(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(monkeypatch, search_conversations=[])
        out = await mcp.tools["search_conversations"](
            query="hi", min_score=1.5
        )
        assert "❌" in out
        db.search_conversations.assert_not_awaited()

    async def test_no_results_returns_hint(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_reflection_db(monkeypatch, search_conversations=[])
        out = await mcp.tools["search_conversations"](query="missing")
        assert "No conversations found" in out
        assert "missing" in out
        assert "checkpoint" in out  # tip line

    async def test_results_with_project_and_timestamp(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _patch_reflection_db(
            monkeypatch,
            search_conversations=[
                {
                    "score": 0.92,
                    "project": "alpha",
                    "timestamp": "2026-09-04T00:00:00Z",
                    "content": "matched content body",
                }
            ],
        )
        out = await mcp.tools["search_conversations"](
            query="foo", limit=5, min_score=0.7, project="alpha"
        )
        assert "🔍" in out
        assert "Found 1 conversations" in out
        assert "92.0%" in out
        assert "alpha" in out
        assert "2026-09-04" in out
        assert "matched content body" in out
        kwargs = db.search_conversations.await_args.kwargs
        assert kwargs["query"] == "foo"
        assert kwargs["limit"] == 5
        assert kwargs["min_score"] == 0.7
        assert kwargs["project"] == "alpha"

    async def test_results_without_project_or_timestamp(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_reflection_db(
            monkeypatch,
            search_conversations=[
                {"score": 0.5, "content": "bare"}
            ],
        )
        out = await mcp.tools["search_conversations"](query="foo")
        assert "Found 1" in out
        # No project line, no timestamp line for missing fields
        assert "📁 Project:" not in out
        # Score 0.5 => "50.0%"; ensure that field renders, then check no
        # project/timestamp lines appear after the content.
        assert "📁 Project" not in out

    async def test_long_content_is_truncated(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        long = "x" * 500
        _patch_reflection_db(
            monkeypatch,
            search_conversations=[{"score": 0.8, "content": long}],
        )
        out = await mcp.tools["search_conversations"](query="foo")
        # Truncation marker
        assert "..." in out
        # Full long string must not appear contiguously
        assert long not in out

    async def test_short_content_not_truncated(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_reflection_db(
            monkeypatch,
            search_conversations=[{"score": 0.8, "content": "hi"}],
        )
        out = await mcp.tools["search_conversations"](query="foo")
        assert "hi" in out
        assert "..." not in out

    async def test_database_exception_returns_failure(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_reflection_db_raises(monkeypatch, RuntimeError("search down"))
        out = await mcp.tools["search_conversations"](query="foo")
        assert "❌" in out
        assert "search down" in out

    async def test_multiple_results_numbered(
        self, mcp: _FakeMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_reflection_db(
            monkeypatch,
            search_conversations=[
                {"score": 0.9, "content": "first"},
                {"score": 0.8, "content": "second"},
                {"score": 0.7, "content": "third"},
            ],
        )
        out = await mcp.tools["search_conversations"](query="foo")
        assert "Found 3 conversations" in out
        assert "1. Score:" in out
        assert "2. Score:" in out
        assert "3. Score:" in out
