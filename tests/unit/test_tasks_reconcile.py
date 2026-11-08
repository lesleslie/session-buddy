"""Tests for the task/reflection-store reconciliation helpers.

Task metadata lives in the SQLModel sidecar; task content lives in the
DuckDB reflection store. These helpers enumerate the rows where the two
stores disagree, so a divergence is reportable instead of silent.

Proven on 2026-11-07: two tasks went invisible to every read path while
both stores still held their rows, because a DuckDB WAL-poison recovery
dropped them from the live connection's view.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from session_buddy.mcp.tools import tasks_storage


@pytest.fixture
def _engine() -> Any:
    """Yield a fresh in-memory sidecar engine; reset the singleton after."""
    e = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(e)
    try:
        yield e
    finally:
        tasks_storage.set_engine(None)


def _seed_task(engine: Any, reflection_id: str, task_id: str, **extra: Any) -> None:
    """Write one task row into the sidecar, as ``tasks_create`` would."""
    tasks_storage.persist_task_metadata(
        engine,
        reflection_id,
        {
            "kind": "task",
            "task_id": task_id,
            "owner": "user:les@example.com",
            "visibility": "private",
            **extra,
        },
    )


def _reader(readable: set[str]) -> Any:
    """Build an ``_read_reflection`` stand-in: None for unreadable ids."""

    async def _read(reflection_id: str) -> dict[str, Any] | None:
        if reflection_id not in readable:
            return None
        return {
            "id": reflection_id,
            "content": "body",
            "tags": ["task"],
        }

    return AsyncMock(side_effect=_read)


@pytest.mark.asyncio
async def test_find_unreadable_task_reflections_lists_only_the_broken_rows(
    _engine: Any,
) -> None:
    """Only the rows whose reflection is unreadable are reported."""
    from session_buddy.mcp.tools import tasks_reconcile

    _seed_task(_engine, "readable_reflection", "t-" + "0" * 32)
    _seed_task(_engine, "unreadable_reflection", "t-" + "1" * 32)

    with patch(
        "session_buddy.mcp.tools.tasks_tools._read_reflection",
        new=_reader({"readable_reflection"}),
    ):
        result = await tasks_reconcile.find_unreadable_task_reflections(_engine)

    assert result == ["unreadable_reflection"]


@pytest.mark.asyncio
async def test_find_unreadable_task_reflections_returns_sorted_ids(
    _engine: Any,
) -> None:
    """The report is sorted, so two runs produce the same output."""
    from session_buddy.mcp.tools import tasks_reconcile

    _seed_task(_engine, "zzz_broken", "t-" + "1" * 32)
    _seed_task(_engine, "aaa_broken", "t-" + "2" * 32)

    with patch(
        "session_buddy.mcp.tools.tasks_tools._read_reflection",
        new=_reader(set()),
    ):
        result = await tasks_reconcile.find_unreadable_task_reflections(_engine)

    assert result == ["aaa_broken", "zzz_broken"]


@pytest.mark.asyncio
async def test_find_unreadable_task_reflections_is_empty_when_all_readable(
    _engine: Any,
) -> None:
    """The happy path reports nothing — no false alarms."""
    from session_buddy.mcp.tools import tasks_reconcile

    _seed_task(_engine, "readable_reflection", "t-" + "0" * 32)

    with patch(
        "session_buddy.mcp.tools.tasks_tools._read_reflection",
        new=_reader({"readable_reflection"}),
    ):
        result = await tasks_reconcile.find_unreadable_task_reflections(_engine)

    assert result == []


@pytest.mark.asyncio
async def test_find_unreadable_task_reflections_ignores_non_task_rows(
    _engine: Any,
) -> None:
    """Only ``kind=task`` rows are task rows; other reflections are not tasks."""
    from session_buddy.mcp.tools import tasks_reconcile

    tasks_storage.persist_task_metadata(
        _engine,
        "ordinary_reflection",
        {"kind": "note", "owner": "user:les@example.com"},
    )

    with patch(
        "session_buddy.mcp.tools.tasks_tools._read_reflection",
        new=_reader(set()),
    ):
        result = await tasks_reconcile.find_unreadable_task_reflections(_engine)

    assert result == []


@pytest.mark.asyncio
async def test_find_task_metadata_drift_reports_differing_keys(
    _engine: Any,
) -> None:
    """A task whose two stores hold different values is reported."""
    from session_buddy.mcp.tools import tasks_reconcile

    task_id = "t-" + "0" * 32
    _seed_task(_engine, "drifted_reflection", task_id, priority="normal")

    async def _read(reflection_id: str) -> dict[str, Any] | None:
        return {
            "id": reflection_id,
            "content": "body",
            "tags": ["task"],
            "metadata": {
                "kind": "task",
                "task_id": task_id,
                "owner": "user:les@example.com",
                "visibility": "private",
                "priority": "high",
            },
        }

    with patch(
        "session_buddy.mcp.tools.tasks_tools._read_reflection",
        new=AsyncMock(side_effect=_read),
    ):
        drift = await tasks_reconcile.find_task_metadata_drift(_engine)

    assert len(drift) == 1
    assert drift[0]["reflection_id"] == "drifted_reflection"
    assert drift[0]["task_id"] == task_id
    assert drift[0]["fields"] == ["priority"]


@pytest.mark.asyncio
async def test_find_task_metadata_drift_is_empty_when_the_stores_agree(
    _engine: Any,
) -> None:
    """Identical metadata in both stores is not drift."""
    from session_buddy.mcp.tools import tasks_reconcile

    task_id = "t-" + "0" * 32
    blob = {
        "kind": "task",
        "task_id": task_id,
        "owner": "user:les@example.com",
        "visibility": "private",
        "priority": "normal",
    }
    _seed_task(_engine, "agreed_reflection", task_id, priority="normal")

    async def _read(reflection_id: str) -> dict[str, Any] | None:
        return {
            "id": reflection_id,
            "content": "body",
            "tags": ["task"],
            "metadata": dict(blob),
        }

    with patch(
        "session_buddy.mcp.tools.tasks_tools._read_reflection",
        new=AsyncMock(side_effect=_read),
    ):
        drift = await tasks_reconcile.find_task_metadata_drift(_engine)

    assert drift == []
