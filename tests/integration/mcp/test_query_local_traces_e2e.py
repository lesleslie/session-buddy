"""End-to-end check for Session-Buddy's ``query_local_traces`` tool.

The Bodai-wide wire-up contract requires every registered tool to have a
test that asserts a NON-EMPTY result against real data -- a tool that
returns nothing is indistinguishable from a tool that is registered but
not wired, and that is exactly the failure this tool's history is about
(``register_otel_trace_tools`` had no call site for five months).

This exercises the whole path: a real DuckDB store, a real row written
through the adapter, and the tool's own filter -> store -> record
mapping. No mocking of the store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.adapters.settings import ReflectionAdapterSettings
from session_buddy.mcp.tools.memory.otel_trace_tools import query_local_traces


@pytest.fixture
async def adapter(tmp_path: Path):
    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "e2e.duckdb",
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )
    adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()
    yield adapter
    await adapter.aclose()


@pytest.mark.asyncio
async def test_the_tool_returns_a_stored_record(
    adapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record written through the adapter comes back through the tool."""
    await adapter.store_conversation(
        content="the verification probe's body",
        metadata={"project": "mahavishnu"},
        category="facts",
    )

    async def fake_get_db():
        return adapter

    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        fake_get_db,
    )

    records = await query_local_traces(task_class="facts", system_id="mahavishnu")

    assert len(records) == 1, "the tool returned no rows for a row that exists"
    record = records[0]
    assert record["content"] == "the verification probe's body"
    assert record["system_id"] == "mahavishnu"
    assert record["task_class"] == "facts"
    assert record["timestamp"], "the record carries no timestamp"
    assert "metadata" in record


@pytest.mark.asyncio
async def test_the_tool_filters_by_project(adapter, monkeypatch: pytest.MonkeyPatch) -> None:
    """The project filter narrows the result, it does not widen it."""
    await adapter.store_conversation(
        content="one", metadata={"project": "mahavishnu"}, category="facts"
    )
    await adapter.store_conversation(
        content="two", metadata={"project": "session-buddy"}, category="facts"
    )

    async def fake_get_db():
        return adapter

    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        fake_get_db,
    )

    records = await query_local_traces(task_class="facts", system_id="mahavishnu")

    assert len(records) == 1
    assert records[0]["content"] == "one"


@pytest.mark.asyncio
async def test_the_redaction_bucket_is_not_returned(
    adapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's ``_redacted`` bucket must not come back through the tool.

    ``redact_metadata`` moves non-allowlisted keys there with their
    values intact; returning it would hand back exactly the metadata the
    redaction policy kept out of the allowlist.
    """
    await adapter.store_conversation(
        content="body",
        metadata={"project": "mahavishnu", "exit_code": 0, "metrics": {"ms": 12}},
        category="facts",
    )

    async def fake_get_db():
        return adapter

    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        fake_get_db,
    )

    records = await query_local_traces(task_class="facts", dry_run=True)

    assert len(records) == 1
    metadata = records[0]["metadata"]
    assert "_redacted" not in metadata
    assert "exit_code" not in metadata
    assert "metrics" not in metadata
