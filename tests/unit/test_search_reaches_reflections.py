#!/usr/bin/env python3
"""Regression test: the search tools must reach the reflection store.

Session-Buddy keeps two stores in separate tables with separate
embeddings: ``conversations_v2`` holds session-context blocks, and
``reflections_v2`` holds durable notes -- the ``project``/``reference``
half of the memory-routing table.

Every search surface used to query only ``conversations_v2``, so a
reflection could be stored and then never found again. The memory
half of the store was effectively write-only.

Two separate defects produced that, and this test pins both:

1. The adapter's query cache keyed conversations and reflections the
   same way, so the reflection search read the conversation branch's
   cached row ids out of ``reflections_v2`` and returned nothing. That
   one is pinned in
   ``tests/unit/test_reflection_search_cache_isolation.py``.
2. The MCP search implementations in
   ``session_buddy/mcp/tools/memory/search_tools.py`` called
   ``search_conversations`` only -- even though a parallel copy of the
   same tools in ``memory_tools.py`` had already been corrected to
   search reflections. The duplicate registration drift meant the
   corrected copy was shadowed by the stale one.

This test pins the second: each search surface must call
``search_reflections`` as well as ``search_conversations``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.memory.search_tools import (
    _quick_search_operation,
    _search_by_concept_operation,
    _search_summary_operation,
)

REFLECTION_TEXT = "a durable reflection about the cache key discriminator"


def _db(conversations: list[dict[str, Any]] | None = None) -> MagicMock:
    """Return a stub database with one conversation and one reflection."""
    db = MagicMock()
    db.search_conversations = AsyncMock(
        return_value=conversations
        if conversations is not None
        else [{"id": "c1", "content": "a conversation block", "score": 0.9}]
    )
    db.search_reflections = AsyncMock(
        return_value=[{"id": "r1", "content": REFLECTION_TEXT, "similarity": 0.6}]
    )
    return db


@pytest.mark.asyncio
async def test_quick_search_reaches_the_reflection_store() -> None:
    """quick_search must query both stores."""
    db = _db()

    await _quick_search_operation(db, "cache key", None, 0.15, 5)

    assert db.search_conversations.await_count == 1
    assert db.search_reflections.await_count == 1


@pytest.mark.asyncio
async def test_quick_search_surfaces_the_reflection() -> None:
    """A highly-relevant reflection must become the top result.

    quick_search renders only the top hit, so the reflection has to
    outrank the conversation for its content to be visible at all.
    """
    db = _db()
    db.search_reflections = AsyncMock(
        return_value=[{"id": "r1", "content": REFLECTION_TEXT, "similarity": 0.95}]
    )

    output = await _quick_search_operation(db, "cache key", None, 0.15, 5)

    assert REFLECTION_TEXT[:40] in output


@pytest.mark.asyncio
async def test_search_by_concept_reaches_the_reflection_store() -> None:
    """search_by_concept must query both stores."""
    db = _db()

    await _search_by_concept_operation(db, "cache key", True, 10, None)

    assert db.search_conversations.await_count == 1
    assert db.search_reflections.await_count == 1


@pytest.mark.asyncio
async def test_search_summary_reaches_the_reflection_store() -> None:
    """search_summary must query both stores."""
    db = _db()

    await _search_summary_operation(db, "cache key", None, 0.15)

    assert db.search_conversations.await_count == 1
    assert db.search_reflections.await_count == 1


@pytest.mark.asyncio
async def test_search_summary_counts_reflections_in_the_total() -> None:
    """The summary total must include reflections, not just conversations."""
    db = _db(conversations=[])

    output = await _search_summary_operation(db, "cache key", None, 0.15)

    assert "1" in output
    assert "relevant results" in output
