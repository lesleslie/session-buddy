"""The fleet contract for session-buddy's ``query_local_traces``.

Every Bodai server exposes ``query_local_traces`` with the same parameter
names, requiredness and defaults, so a caller can issue one query against
whichever server holds the answer. This file pins that contract for
session-buddy: what the tool forwards to the store, and how the two
"every system" sentinels and the dry-run flag behave.

The store-side behaviour (record shape, the SQL the query runs) lives in
``tests/unit/mcp/tools/memory/test_otel_trace_tools.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from session_buddy.mcp.tools.memory.otel_trace_tools import (
    query_local_traces,
    register_otel_trace_tools,
)


class RecordingDB:
    """Captures the arguments the tool forwards to the store."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def query_conversations_by_classification(self, **kwargs) -> list[dict]:
        self.calls.append(kwargs)
        return []


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> RecordingDB:
    recording = RecordingDB()

    async def fake_get_db():
        return recording

    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        fake_get_db,
    )
    return recording


class TestForwardedContract:
    @pytest.mark.asyncio
    async def test_the_filters_reach_the_store(self, db: RecordingDB) -> None:
        await query_local_traces(
            task_class="facts",
            system_id="mahavishnu",
            start_time="2026-06-01T00:00:00",
            end_time="2026-06-30T00:00:00",
            limit=42,
        )

        assert db.calls == [
            {
                "classification": "facts",
                "project": "mahavishnu",
                "start_time": datetime(2026, 6, 1, tzinfo=UTC),
                "end_time": datetime(2026, 6, 30, tzinfo=UTC),
                "limit": 42,
            }
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sentinel", [None, "", "*"])
    async def test_the_all_systems_sentinel_means_every_project(
        self, db: RecordingDB, sentinel: str | None
    ) -> None:
        """``None``, ``""`` and ``"*"`` all mean "every project"."""
        await query_local_traces(task_class="facts", system_id=sentinel)

        assert db.calls[0]["project"] is None

    @pytest.mark.asyncio
    async def test_an_offset_bound_is_converted_to_utc(self, db: RecordingDB) -> None:
        await query_local_traces(
            task_class="facts", start_time="2026-06-15T14:00:00+02:00"
        )

        assert db.calls[0]["start_time"] == datetime(2026, 6, 15, 12, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_an_unparseable_bound_is_rejected_not_widened(
        self, db: RecordingDB
    ) -> None:
        """A bad bound must be rejected, not treated as absent.

        Treating it as absent drops that side of the window and returns
        MORE records than the caller asked for. Mahavishnu's tool rejects
        it the same way.
        """
        assert await query_local_traces(task_class="facts", start_time="nope") == []
        assert db.calls == []

    @pytest.mark.asyncio
    async def test_dry_run_clamps_the_limit_and_keeps_the_filters(
        self, db: RecordingDB
    ) -> None:
        """``dry_run`` changes the output shape; the filters stay in force."""
        await query_local_traces(
            task_class="facts",
            system_id="mahavishnu",
            limit=500,
            dry_run=True,
        )

        assert db.calls[0]["limit"] == 20
        assert db.calls[0]["project"] == "mahavishnu"
        assert db.calls[0]["classification"] == "facts"


class TestGuards:
    @pytest.mark.asyncio
    async def test_an_empty_task_class_never_queries(self, db: RecordingDB) -> None:
        """An empty filter must not widen the query to the whole store."""
        assert await query_local_traces(task_class="") == []
        assert db.calls == []

    @pytest.mark.asyncio
    async def test_a_store_failure_returns_an_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_get_db():
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            fake_get_db,
        )

        assert await query_local_traces(task_class="facts") == []


def test_the_tool_is_registered_on_the_server() -> None:
    class FakeMCP:
        def __init__(self) -> None:
            self.tools: list[object] = []

        def tool(self):
            def decorator(func):
                self.tools.append(func)
                return func

            return decorator

    mcp = FakeMCP()
    register_otel_trace_tools(mcp)
    assert mcp.tools == [query_local_traces]
