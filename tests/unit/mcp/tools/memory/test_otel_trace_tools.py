"""Store-side behaviour for session-buddy's ``query_local_traces``.

The fleet contract -- what the tool forwards and how the sentinels and
the dry-run flag behave -- lives in ``tests/unit/test_otel_trace_tools.py``.
This file covers what comes back: the record shape, the dry-run output
shape, the profile wiring, and the store query the tool depends on.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from session_buddy.mcp.tools.memory import otel_trace_tools
from session_buddy.mcp.tools.memory.otel_trace_tools import (
    _parse_window_bound,
    query_local_traces,
    register_otel_trace_tools,
)


class FakeDB:
    """Returns canned rows and records the arguments it was called with."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows if rows is not None else []
        self.calls: list[dict] = []

    async def query_conversations_by_classification(self, **kwargs) -> list[dict]:
        self.calls.append(kwargs)
        return self.rows


def _patch_db(monkeypatch: pytest.MonkeyPatch, db: FakeDB) -> None:
    async def fake_get_db():
        return db

    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        fake_get_db,
    )


def _row(**overrides) -> dict:
    row = {
        "id": "t1",
        "content": "the record body",
        "metadata": {"checkpoint_type": "auto"},
        "timestamp": datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        "project": "mahavishnu",
        "classification": "facts",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# _parse_window_bound
# ---------------------------------------------------------------------------


class TestParseWindowBound:
    def test_naive_bound_is_read_as_utc(self) -> None:
        assert _parse_window_bound("2026-06-15T12:00:00") == datetime(
            2026, 6, 15, 12, 0, tzinfo=UTC
        )

    def test_offset_bound_is_converted_to_utc(self) -> None:
        assert _parse_window_bound("2026-06-15T14:00:00+02:00") == datetime(
            2026, 6, 15, 12, 0, tzinfo=UTC
        )

    def test_unparseable_bound_is_absent(self) -> None:
        assert _parse_window_bound("not-a-timestamp") is None


# ---------------------------------------------------------------------------
# The record the tool returns
# ---------------------------------------------------------------------------


class TestRecordShape:
    @pytest.mark.asyncio
    async def test_returns_the_fleet_record_shape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = FakeDB([_row()])
        _patch_db(monkeypatch, db)

        result = await query_local_traces(task_class="facts", system_id="mahavishnu")

        assert len(result) == 1
        record = result[0]
        assert record["conversation_id"] == "t1"
        assert record["system_id"] == "mahavishnu"
        assert record["project"] == "mahavishnu"
        assert record["task_class"] == "facts"
        assert record["metadata"] == {"checkpoint_type": "auto"}
        assert record["content"] == "the record body"
        # An absolute, offset-bearing timestamp -- not the store's naive
        # local wall-clock, which a caller cannot compare against its own
        # window.
        assert record["timestamp"] == "2026-06-01T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_dry_run_omits_the_record_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``dry_run`` returns the stored metadata, not the body."""
        db = FakeDB([_row()])
        _patch_db(monkeypatch, db)

        result = await query_local_traces(task_class="facts", dry_run=True)

        assert "content" not in result[0]
        assert result[0]["metadata"] == {"checkpoint_type": "auto"}


# ---------------------------------------------------------------------------
# The tool group is wired into the profile dispatch
# ---------------------------------------------------------------------------


class TestProfileWiring:
    def test_the_group_is_in_the_registration_map(self) -> None:
        """The tool must go through REGISTRATION_MAP, not a direct call.

        A direct registration in server_optimized.py would sit outside the
        tier gating, so a MINIMAL/STANDARD deployment would still expose
        it -- and the map's own bookkeeping would not know about it.
        """
        from session_buddy.mcp.tools import profiles

        assert "register_otel_trace_tools" in profiles.REGISTRATION_MAP
        assert (
            profiles.REGISTRATION_MAP["register_otel_trace_tools"]
            is register_otel_trace_tools
        )

    def test_the_group_is_not_mandatory(self) -> None:
        """It is a FULL-tier diagnostic, not an always-on group."""
        from session_buddy.mcp.tools import profiles

        assert "register_otel_trace_tools" not in profiles.SESSION_BUDDY_MANDATORY_GROUPS


# ---------------------------------------------------------------------------
# The store-side query
# ---------------------------------------------------------------------------


class TestQueryConversationsByClassification:
    """The adapter method the tool depends on."""

    @pytest.fixture
    async def adapter(self, tmp_path):
        from session_buddy.adapters import (
            reflection_adapter_oneiric as reflection_module,
        )
        from session_buddy.adapters.settings import ReflectionAdapterSettings

        settings = ReflectionAdapterSettings(
            database_path=tmp_path / "test.duckdb",
            enable_embeddings=False,
            enable_vss=False,
            enable_hnsw_index=False,
        )
        adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
        await adapter.initialize()
        yield adapter
        await adapter.aclose()

    async def _store(self, adapter, **kwargs) -> None:
        """Store one conversation row.

        ``project`` rides in the metadata -- the writer lifts it out to the
        dedicated column, and it is the only allowlisted key that carries a
        component name.
        """
        project = kwargs.pop("project", "mahavishnu")
        content = kwargs.pop("content", f"body {project}")
        await adapter.store_conversation(
            content=content,
            metadata={"project": project},
            category=kwargs.pop("category", "facts"),
            **kwargs,
        )

    @pytest.mark.asyncio
    async def test_filters_by_category(self, adapter) -> None:
        await self._store(adapter, category="facts", content="a")
        await self._store(adapter, category="context", content="b")

        rows = await adapter.query_conversations_by_classification(
            classification="facts"
        )

        assert len(rows) == 1
        assert rows[0]["classification"] == "facts"

    @pytest.mark.asyncio
    async def test_the_category_match_is_case_insensitive(self, adapter) -> None:
        await self._store(adapter)

        rows = await adapter.query_conversations_by_classification(
            classification="FACTS"
        )

        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_filters_by_project(self, adapter) -> None:
        await self._store(adapter, project="mahavishnu", content="a")
        await self._store(adapter, project="session-buddy", content="b")

        rows = await adapter.query_conversations_by_classification(
            classification="facts", project="session-buddy"
        )

        assert len(rows) == 1
        assert rows[0]["project"] == "session-buddy"

    @pytest.mark.asyncio
    async def test_omitting_the_project_filter_returns_every_project(
        self, adapter
    ) -> None:
        await self._store(adapter, project="mahavishnu", content="a")
        await self._store(adapter, project="session-buddy", content="b")

        rows = await adapter.query_conversations_by_classification(
            classification="facts"
        )

        assert len(rows) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sentinel", ["", "*"])
    async def test_the_all_projects_sentinel_is_honoured_here_too(
        self, adapter, sentinel: str
    ) -> None:
        """The adapter's own contract promises this, not just the tool's.

        The tool normalises the sentinel before calling, so without this
        the promise would live only in a docstring.
        """
        await self._store(adapter, project="mahavishnu", content="a")
        await self._store(adapter, project="session-buddy", content="b")

        rows = await adapter.query_conversations_by_classification(
            classification="facts", project=sentinel
        )

        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_an_empty_classification_matches_nothing(self, adapter) -> None:
        """An empty filter must never widen the query to the whole table."""
        await self._store(adapter)

        rows = await adapter.query_conversations_by_classification(classification="")

        assert rows == []

    @pytest.mark.asyncio
    async def test_filters_by_the_time_window(self, adapter) -> None:
        await self._store(adapter)

        rows = await adapter.query_conversations_by_classification(
            classification="facts",
            start_time=datetime(2000, 1, 1, tzinfo=UTC),
            end_time=datetime(2000, 1, 2, tzinfo=UTC),
        )

        assert rows == []

    @pytest.mark.asyncio
    async def test_a_window_around_now_matches(self, adapter) -> None:
        """An absolute window selects the record by its true instant.

        The column holds host-local wall-clock; DuckDB re-attaches the
        session time zone when comparing it against an aware value, so
        the window still selects the right records.
        """
        await self._store(adapter)

        rows = await adapter.query_conversations_by_classification(
            classification="facts",
            start_time=datetime(2000, 1, 1, tzinfo=UTC),
            end_time=datetime(2100, 1, 1, tzinfo=UTC),
        )

        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_the_returned_timestamp_is_an_instant(self, adapter) -> None:
        """Not the store's naive local wall-clock."""
        await self._store(adapter)

        rows = await adapter.query_conversations_by_classification(
            classification="facts"
        )

        assert isinstance(rows[0]["timestamp"], datetime)
        assert rows[0]["timestamp"].tzinfo is not None

    @pytest.mark.asyncio
    async def test_honours_the_limit(self, adapter) -> None:
        for index in range(3):
            await self._store(adapter, content=f"body {index}")

        rows = await adapter.query_conversations_by_classification(
            classification="facts", limit=2
        )

        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_a_negative_limit_is_clamped_not_taken_as_unlimited(
        self, adapter
    ) -> None:
        """DuckDB reads ``LIMIT -1`` as "no limit" -- clamp it."""
        await self._store(adapter)

        rows = await adapter.query_conversations_by_classification(
            classification="facts", limit=-1
        )

        assert rows == []

    @pytest.mark.asyncio
    async def test_a_zero_limit_returns_no_rows(self, adapter) -> None:
        """A zero limit is zero rows, the way the other servers' stores do."""
        await self._store(adapter)

        rows = await adapter.query_conversations_by_classification(
            classification="facts", limit=0
        )

        assert rows == []

    @pytest.mark.asyncio
    async def test_an_unmatched_classification_returns_nothing(self, adapter) -> None:
        await self._store(adapter)

        rows = await adapter.query_conversations_by_classification(
            classification="code_generation"
        )

        assert rows == []

    @pytest.mark.asyncio
    async def test_a_corrupt_metadata_row_does_not_take_down_the_read(
        self, adapter
    ) -> None:
        """One bad row must not empty the whole result set."""
        await self._store(adapter, content="a")
        await self._store(adapter, content="b")
        adapter.conn.execute(
            "UPDATE conversations_v2 SET metadata = '{not json' "
            "WHERE id = (SELECT id FROM conversations_v2 ORDER BY timestamp LIMIT 1)"
        )

        rows = await adapter.query_conversations_by_classification(
            classification="facts"
        )

        assert len(rows) == 2
        assert any(row["metadata"] == {} for row in rows)


def test_the_module_exports_the_expected_names() -> None:
    assert "query_local_traces" in otel_trace_tools.__all__
    assert "register_otel_trace_tools" in otel_trace_tools.__all__
