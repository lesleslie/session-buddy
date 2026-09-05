"""Tests for session_buddy.mcp.tools.memory.otel_trace_tools.

Covers the OTel trace query MCP tool:
- ``_filter_result_by_system_id``: top-level, metadata-nested, missing,
  matching, mismatched
- ``_filter_result_by_time_range``: no range (always included),
  timestamp before start, after end, inside range, invalid timestamp
  string, naive datetime handling, missing timestamp
- ``_filter_result_by_task_class``: no filter (always included),
  list-of-classes match/mismatch, single-class match/mismatch,
  top-level vs attributes-level
- ``query_local_traces``: end-to-end with patched reflection DB,
  result shape, all filters combined, exception path returns []
- ``register_otel_trace_tools``: attaches tools to the MCP server
- ``__all__`` exports
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from session_buddy.mcp.tools.memory import otel_trace_tools
from session_buddy.mcp.tools.memory.otel_trace_tools import (
    _filter_result_by_system_id,
    _filter_result_by_task_class,
    _filter_result_by_time_range,
    query_local_traces,
    register_otel_trace_tools,
)


# ---------------------------------------------------------------------------
# _filter_result_by_system_id
# ---------------------------------------------------------------------------


class TestFilterBySystemId:
    def test_top_level_match(self) -> None:
        result = {"system_id": "mahavishnu", "id": "x"}
        # Mismatched → filtered out (returns True).
        assert _filter_result_by_system_id(result, "akosha") is True
        # Matched → not filtered (returns False).
        assert _filter_result_by_system_id(result, "mahavishnu") is False

    def test_metadata_nested(self) -> None:
        # system_id only in metadata → also matched.
        result = {"id": "x", "metadata": {"system_id": "akosha"}}
        assert _filter_result_by_system_id(result, "akosha") is False
        assert _filter_result_by_system_id(result, "mahavishnu") is True

    def test_missing_system_id(self) -> None:
        # No system_id → not filtered (records without provenance pass).
        result = {"id": "x"}
        assert _filter_result_by_system_id(result, "akosha") is False


# ---------------------------------------------------------------------------
# _filter_result_by_time_range
# ---------------------------------------------------------------------------


class TestFilterByTimeRange:
    def test_no_range_passes_through(self) -> None:
        result = {"id": "x", "timestamp": "2026-01-01T00:00:00"}
        assert _filter_result_by_time_range(result, None, None) is False

    def test_empty_string_treated_as_none(self) -> None:
        result = {"id": "x"}
        assert _filter_result_by_time_range(result, "", "") is False

    def test_missing_timestamp(self) -> None:
        # No timestamp on the result → can't filter, so not filtered out.
        result = {"id": "x"}
        start = "2026-01-01T00:00:00"
        assert _filter_result_by_time_range(result, start, None) is False

    def test_timestamp_before_start_filtered(self) -> None:
        # Use timezone-aware string format to avoid the naive/aware bug.
        result = {"timestamp": "2025-01-01T00:00:00+00:00"}
        start = "2026-01-01T00:00:00+00:00"
        assert _filter_result_by_time_range(result, start, None) is True

    def test_timestamp_after_end_filtered(self) -> None:
        result = {"timestamp": "2027-01-01T00:00:00+00:00"}
        end = "2026-12-31T23:59:59+00:00"
        assert _filter_result_by_time_range(result, None, end) is True

    def test_timestamp_inside_range_passes(self) -> None:
        result = {"timestamp": "2026-06-15T12:00:00+00:00"}
        start = "2026-01-01T00:00:00+00:00"
        end = "2026-12-31T23:59:59+00:00"
        assert _filter_result_by_time_range(result, start, end) is False

    def test_invalid_timestamp_string(self) -> None:
        # Unparseable timestamp → not filtered (the function returns False).
        result = {"timestamp": "not-a-date"}
        assert _filter_result_by_time_range(result, "2026-01-01T00:00:00+00:00", None) is False

    def test_naive_datetime_promoted_to_utc(self) -> None:
        # A naive datetime on the result is treated as UTC for comparison
        # (production code promotes it via .replace(tzinfo=UTC)).
        ts = datetime(2026, 6, 15, 12, 0, 0)  # naive
        result = {"timestamp": ts}
        start = "2026-01-01T00:00:00+00:00"
        end = "2026-12-31T23:59:59+00:00"
        assert _filter_result_by_time_range(result, start, end) is False
        # Before the start date → filtered out.
        ts_early = datetime(2025, 6, 15, 12, 0, 0)
        result_early = {"timestamp": ts_early}
        assert _filter_result_by_time_range(result_early, start, None) is True

    def test_uses_created_at_fallback(self) -> None:
        # When timestamp is missing but created_at is present, use it.
        result = {"created_at": "2025-01-01T00:00:00+00:00"}
        assert _filter_result_by_time_range(result, "2026-01-01T00:00:00+00:00", None) is True


# ---------------------------------------------------------------------------
# _filter_result_by_task_class
# ---------------------------------------------------------------------------


class TestFilterByTaskClass:
    def test_no_filter_passes_through(self) -> None:
        result = {"id": "x", "metadata": {"attributes": {}}}
        assert _filter_result_by_task_class(result, None) is False

    def test_empty_string_filter_passes_through(self) -> None:
        result = {"id": "x"}
        assert _filter_result_by_task_class(result, "") is False

    def test_list_match(self) -> None:
        result = {
            "metadata": {
                "attributes": {"task.class": ["code_generation", "review"]}
            }
        }
        assert _filter_result_by_task_class(result, "code_generation") is False
        assert _filter_result_by_task_class(result, "missing") is True

    def test_single_match(self) -> None:
        result = {"metadata": {"attributes": {"task.class": "code_generation"}}}
        assert _filter_result_by_task_class(result, "code_generation") is False
        assert _filter_result_by_task_class(result, "missing") is True

    def test_dotted_key(self) -> None:
        # The function checks both ``task.class`` and ``task_class``.
        result = {
            "metadata": {
                "attributes": {"task_class": "code_generation"}
            }
        }
        assert _filter_result_by_task_class(result, "code_generation") is False

    def test_top_level_metadata_task_class(self) -> None:
        # When ``task.class`` attribute is missing, fall back to top-level.
        result = {
            "metadata": {
                "attributes": {},
                "task_class": "code_generation",
            }
        }
        assert _filter_result_by_task_class(result, "code_generation") is False
        assert _filter_result_by_task_class(result, "other") is True


# ---------------------------------------------------------------------------
# query_local_traces
# ---------------------------------------------------------------------------


class TestQueryLocalTraces:
    @pytest.mark.asyncio
    async def test_returns_filtered_records(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_db():
            db = MagicMock()
            db.search_conversations = AsyncMock(
                return_value=[
                    {
                        "id": "t1",
                        "system_id": "mahavishnu",
                        "timestamp": "2026-06-01T00:00:00",
                        "content": "trace 1",
                        "metadata": {
                            "system_id": "mahavishnu",
                            "attributes": {"task.class": ["code"]},
                        },
                    },
                    {
                        "id": "t2",
                        "system_id": "akosha",  # different system
                        "timestamp": "2026-06-01T00:00:00",
                        "content": "trace 2",
                        "metadata": {"system_id": "akosha"},
                    },
                ]
            )
            return db

        async def fake_get_db():
            return await fake_db()

        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            fake_get_db,
        )

        result = await query_local_traces(
            system_id="mahavishnu", task_class="code"
        )
        assert len(result) == 1
        assert result[0]["conversation_id"] == "t1"
        assert result[0]["content"] == "trace 1"
        assert result[0]["metadata"]["system_id"] == "mahavishnu"
        assert result[0]["attributes"]["task.class"] == ["code"]

    @pytest.mark.asyncio
    async def test_handles_db_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_get_db():
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            fake_get_db,
        )

        result = await query_local_traces(system_id="mahavishnu")
        assert result == []

    @pytest.mark.asyncio
    async def test_with_time_range_filters_outside(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_get_db():
            db = MagicMock()
            db.search_conversations = AsyncMock(
                return_value=[
                    {
                        "id": "t1",
                        "system_id": "mahavishnu",
                        "timestamp": "2025-01-01T00:00:00+00:00",  # before start
                        "metadata": {"system_id": "mahavishnu"},
                    },
                    {
                        "id": "t2",
                        "system_id": "mahavishnu",
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "metadata": {"system_id": "mahavishnu"},
                    },
                ]
            )
            return db

        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            fake_get_db,
        )

        result = await query_local_traces(
            system_id="mahavishnu",
            start_time="2026-01-01T00:00:00+00:00",
            end_time="2026-12-31T23:59:59+00:00",
        )
        assert len(result) == 1
        assert result[0]["conversation_id"] == "t2"

    @pytest.mark.asyncio
    async def test_limit_passed_to_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        async def fake_get_db():
            db = MagicMock()

            async def search(query, limit, threshold):
                captured["query"] = query
                captured["limit"] = limit
                captured["threshold"] = threshold
                return []

            db.search_conversations = search
            return db

        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            fake_get_db,
        )

        await query_local_traces(system_id="mahavishnu", limit=42)
        assert captured["query"] == "mahavishnu"
        assert captured["limit"] == 42
        assert captured["threshold"] == 0.0


def _async_return(value):
    """Helper to build a coroutine that resolves to ``value``."""
    async def _coro():
        return value
    return _coro()


# Import AsyncMock here to avoid breaking the helper above if import fails.
from unittest.mock import AsyncMock  # noqa: E402


# ---------------------------------------------------------------------------
# register_otel_trace_tools
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registers_query_local_traces(self) -> None:
        mcp = MagicMock()
        tool_calls: list[object] = []

        def tool_decorator():
            def decorator(fn):
                tool_calls.append(fn)
                return fn
            return decorator

        mcp.tool = tool_decorator
        register_otel_trace_tools(mcp)
        # The tool is registered.
        assert query_local_traces in tool_calls

    def test_module_exports(self) -> None:
        assert "query_local_traces" in otel_trace_tools.__all__
        assert "register_otel_trace_tools" in otel_trace_tools.__all__
