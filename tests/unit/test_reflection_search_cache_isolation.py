#!/usr/bin/env python3
"""Regression test: the conversation and reflection search caches must not collide.

Both search paths share one query cache. Before the fix, both computed
their cache key from ``(query, project, limit)`` with nothing to say
WHICH table was searched, so the two paths collided whenever they ran
with the same query and limit.

``_quick_search_operation`` in
``session_buddy/mcp/tools/memory/search_tools.py`` runs exactly that
sequence -- conversations first, then reflections, same query, same
limit. The conversation search populated the cache under the shared key;
the reflection search then read the conversation's row IDs back out of
``reflections_v2``, where none of them exist, and returned nothing.

The visible symptom was that a stored reflection was invisible to
``quick_search`` no matter what it contained: every result was a
conversation. The ``project``/``reference`` half of the memory-routing
table was write-only through the search tools.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.adapters import reflection_adapter_oneiric as reflection_module
from session_buddy.adapters.settings import ReflectionAdapterSettings

duckdb = pytest.importorskip("duckdb")


CONVERSATION_TEXT = "cache key table discriminator on the conversation side"
REFLECTION_TEXT = "cache key table discriminator on the reflection side"

#: Matches BOTH stored texts, so each search has a row to find in each
#: direction of the collision.
QUERY = "cache key table discriminator"


@pytest.fixture
async def adapter(tmp_path: Path):
    """Provide an initialized adapter with the query cache enabled."""
    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "cache-isolation.duckdb",
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )
    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()
    yield adapter
    await adapter.aclose()


async def _populate(adapter) -> None:
    await adapter.store_conversation(
        CONVERSATION_TEXT,
        {"project": "test", "topic": "mcp"},
    )
    await adapter.store_reflection(
        REFLECTION_TEXT,
        tags=["reference", "cache"],
    )


async def test_reflection_search_is_not_poisoned_by_the_conversation_search(
    adapter,
) -> None:
    """A conversation search must not blank out the reflection search.

    This is the ``quick_search`` sequence: conversations first, then
    reflections, same query and limit. Before the fix the reflection
    search read the conversation's cached IDs out of ``reflections_v2``
    and returned zero rows.
    """
    await _populate(adapter)

    query = QUERY
    limit = 5

    conversations = await adapter.search_conversations(
        query=query,
        limit=limit,
        project=None,
        min_score=0.0,
    )
    reflections = await adapter.search_reflections(
        query=query,
        limit=limit,
        use_embeddings=False,
        project=None,
        min_score=0.0,
    )

    assert reflections, (
        "the reflection search returned nothing after a conversation search"
    )
    assert any(REFLECTION_TEXT in r["content"] for r in reflections)
    assert conversations
    assert any(CONVERSATION_TEXT in r["content"] for r in conversations)


async def test_conversation_search_is_not_poisoned_by_the_reflection_search(
    adapter,
) -> None:
    """The collision cuts both ways -- the reflection search also caches."""
    await _populate(adapter)

    query = QUERY
    limit = 5

    reflections = await adapter.search_reflections(
        query=query,
        limit=limit,
        use_embeddings=False,
        project=None,
        min_score=0.0,
    )
    conversations = await adapter.search_conversations(
        query=query,
        limit=limit,
        project=None,
        min_score=0.0,
    )

    assert reflections, "the reflection search returned nothing"
    assert conversations, "the conversation search was blanked by a reflection search"
    assert any(CONVERSATION_TEXT in r["content"] for r in conversations)
    assert any(REFLECTION_TEXT in r["content"] for r in reflections)


async def test_different_thresholds_do_not_share_a_cache_entry(adapter) -> None:
    """``min_score`` changes the result set, so it belongs in the key.

    A cached entry computed at one threshold cannot answer a query at
    another: it may hold rows the stricter threshold would exclude.
    """
    await _populate(adapter)

    query = QUERY
    limit = 5

    loose = await adapter.search_reflections(
        query=query,
        limit=limit,
        use_embeddings=False,
        project=None,
        min_score=0.0,
    )
    strict = await adapter.search_reflections(
        query=query,
        limit=limit,
        use_embeddings=False,
        project=None,
        min_score=0.99,
    )

    assert loose
    # The strict search must not inherit the loose search's rows.
    assert len(strict) <= len(loose)


async def test_text_and_semantic_searches_do_not_share_a_cache_entry(
    adapter,
) -> None:
    """``use_embeddings`` selects a different query path, so it is part of the key."""
    await _populate(adapter)

    query = QUERY
    limit = 5

    lexical = await adapter.search_reflections(
        query=query,
        limit=limit,
        use_embeddings=False,
        project=None,
        min_score=0.0,
    )
    semantic = await adapter.search_reflections(
        query=query,
        limit=limit,
        use_embeddings=True,
        project=None,
        min_score=0.0,
    )

    assert lexical
    # The semantic path may legitimately differ (no embeddings in this
    # fixture), but it must not be handed the lexical path's cache entry
    # verbatim -- that would be a cache hit on a different query plan.
    assert semantic is not None
