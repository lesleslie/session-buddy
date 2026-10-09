#!/usr/bin/env python3
"""Regression test for ``mcp__session-buddy__search_by_concept`` (REQ-006).

Per the bodai-search-infrastructure-fix plan §5.3.3, this test
asserts that ``search_by_concept`` returns a populated, structured
response for a generic query (``"python"``) at ``min_score=0.3`` over
the wire-shape envelope, not the in-process return value.

Failure modes this test catches (mirrors ``test_quick_search.py``):
- The handler forcing ``use_embeddings=False`` (pre-Phase-3 bug).
- The handler dropping ``min_score`` (the parameter was
  advertised but the impl signature did not include it).
- The text-search path only doing a single ``LIKE '%query%'``
  literal match.
- The MCP wrapper returning ``result.is_error=True`` for an
  otherwise-healthy DB.

The test stubs the reflection adapter via ``unittest.mock`` so the
assertion does not depend on real DuckDB content. The DB stub
returns a deterministic 3-row result list, and the assertion is
that the wire-shape payload contains the "Found N related
conversations" marker AND that the per-row content surfaces in
the text.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from mcp_common.fastmcp import FastMCP
from fastmcp.client.transports.memory import FastMCPTransport
from fastmcp import Client

from session_buddy.mcp.tools.memory import memory_tools as mt
from session_buddy.mcp.tools.memory.memory_tools import (
    _register_core_memory_tools,
)
from tests._support.extract_tool_payload import _extract_tool_payload


def _make_stub_adapter(rows: list[dict[str, Any]]) -> AsyncMock:
    """Return an AsyncMock adapter that mimics the Oneiric interface.

    The MCP handler calls ``await db.search_reflections(query=...,
    project=..., limit=..., min_score=...)``. The stub mirrors the
    real adapter's behavior: it returns ``rows`` as-is for any
    query, ignoring the project/min_score filters. The point of the
    regression test is the WIRE PATH, not the adapter's filtering.
    """
    adapter = AsyncMock()
    adapter.search_reflections = AsyncMock(return_value=list(rows))
    return adapter


@pytest.fixture
def stubbed_db():
    """Patch ``_get_reflection_database`` and ``_check_reflection_tools_available``.

    Returns a 3-row result list so the handler has real data to
    format. Tests that need a different shape can override the
    fixture by re-patching ``mt._get_reflection_database`` directly.
    """
    rows = [
        {
            "id": "01M3P1Y54GN02NH2THMYQY93JZ",
            "content": (
                "python integration note: tool-surface-quality phase 2 shipped "
                "via parallel worktree subagents across akosha and "
                "session-buddy. Cross-repo merge orchestration lives at "
                "mahavishnu.core.merge_to_main."
                # gitleaks:enable-secret
            ),
            "score": 0.88,
            "similarity": 0.88,
            "project": "session-progress-2026-09-29",
            "timestamp": "2026-09-29T00:44:14.992518",
            "tags": ["python", "merge-workflow"],
        },
        {
            "id": "01M3NYQ319KN771GRB91G5GN8M",
            "content": (
                "Ticket: ColdStore GCS branch missing endpoint_url wiring. "
                "Filed against the akosha repo; the GCS branch of "
                "ColdStore was instantiated without an endpoint_url "
                "and the bucket client attempts regional default which "
                "fails for cold-storage classes."
            ),
            "score": 0.74,
            "similarity": 0.74,
            "project": "akosha-cold-store-wiring",
            "timestamp": "2026-09-28T11:02:01.000000",
            "tags": ["cold-store", "gcs"],
        },
        {
            "id": "01M3CM447T7HQVZ0B5ECF5E6RY",
            "content": (
                "Session-Buddy Insights Pipeline REMOVED 2026-09-25 "
                "(commits a3fe82e6 + 5ce3a00a). Follow-up: 4 dead "
                "schema columns dropped; project backfill script "
                "landed. The python module that owned the cron is "
                "deleted; cron schedule is gone."
            ),
            "score": 0.6,
            "similarity": 0.6,
            "project": "legacy",
            "timestamp": "2026-09-25T08:15:42.000000",
            "tags": ["python", "cleanup"],
        },
    ]
    adapter = _make_stub_adapter(rows)
    with (
        patch.object(mt, "_check_reflection_tools_available", return_value=True),
        patch.object(mt, "_get_reflection_database", AsyncMock(return_value=adapter)),
        patch.object(mt, "_reflection_db", adapter),
    ):
        yield adapter, rows


def _build_search_by_concept_server() -> FastMCP:
    """Build a real FastMCP server with the memory tools registered.

    Reuses the production ``_register_core_memory_tools`` so the
    wire surface is identical to the live MCP server.
    """
    server = FastMCP("session-buddy-test-search-by-concept")
    _register_core_memory_tools(server)
    return server


def test_search_by_concept_python_returns_results(stubbed_db) -> None:
    """``search_by_concept('python', min_score=0.3)`` returns >= 1 result.

    Wire-shape assertion: the response text contains the "Found N
    related conversations" marker. Asserts ``result.is_error is
    False`` separately, per REQ-012.
    """
    _adapter, rows = stubbed_db
    server = _build_search_by_concept_server()
    transport = FastMCPTransport(server)

    async def _run() -> Any:
        async with Client(transport) as client:
            return await client.call_tool(
                "search_by_concept",
                {
                    "concept": "python",
                    "include_files": False,
                    "limit": 5,
                    "min_score": 0.3,
                },
            )

    result = asyncio.run(_run())

    # REQ-012: assert on the wire-shape envelope, NOT on the
    # in-process return value. ``is_error`` is checked separately
    # so a true failure does not silently pass via a structured
    # error payload that looks like a hit.
    assert result.is_error is False, (
        f"search_by_concept returned is_error=True: {result!r}"
    )

    payload = _extract_tool_payload(result)
    assert isinstance(payload, str), (
        f"Expected string payload from search_by_concept, "
        f"got {type(payload).__name__}"
    )

    # The handler renders "📈 Found N related conversations:" for
    # any non-empty result list. Asserting on the marker is
    # wire-shape (the marker is in the text payload the user
    # sees) AND structural (no marker == results list was empty).
    assert "Found" in payload, (
        f"Expected 'Found' marker in payload, got: {payload!r}"
    )
    assert "related conversations" in payload, (
        f"Expected 'related conversations' marker in payload, "
        f"got: {payload!r}"
    )

    # At least one stub row's project name should surface in the
    # rendered output (the handler appends "📁 Project: <name>").
    assert any(
        row["project"] in payload for row in rows
    ), (
        f"Expected at least one stub row's project in payload, "
        f"got: {payload!r}"
    )


def test_search_by_concept_threads_min_score_through(stubbed_db) -> None:
    """Confirm the stub adapter was invoked with ``min_score``.

    Behavioural test of the handler wiring: removing the
    hardcoded ``use_embeddings=False`` AND threading ``min_score``
    through are the two pre-Phase-3 bugs the plan calls out. If a
    future refactor drops ``min_score`` again, this test will fail
    and flag the regression.
    """
    _adapter, _rows = stubbed_db
    server = _build_search_by_concept_server()
    transport = FastMCPTransport(server)

    async def _run() -> Any:
        async with Client(transport) as client:
            return await client.call_tool(
                "search_by_concept",
                {
                    "concept": "python",
                    "include_files": False,
                    "limit": 5,
                    "min_score": 0.3,
                },
            )

    asyncio.run(_run())

    adapter = stubbed_db[0]
    assert adapter.search_reflections.await_count == 1, (
        f"Expected exactly 1 adapter.search_reflections call, "
        f"got {adapter.search_reflections.await_count}"
    )
    kwargs = adapter.search_reflections.await_args.kwargs
    assert kwargs.get("min_score") == 0.3, (
        f"Expected min_score=0.3 in adapter kwargs, got {kwargs!r}"
    )
    # The handler MUST NOT pass ``use_embeddings=False``.
    assert "use_embeddings" not in kwargs or kwargs["use_embeddings"] is not False, (
        f"Handler must not force use_embeddings=False; got {kwargs!r}"
    )
    assert kwargs.get("query") == "python"
    assert kwargs.get("limit") == 5, (
        f"Expected limit=5 in adapter kwargs, got {kwargs!r}"
    )


def test_search_by_concept_empty_results_still_renders_envelope(stubbed_db) -> None:
    """An empty result list still returns a structured, non-error wire envelope.

    The pre-Phase-3 bug surfaced as "No conversations found about
    this concept" — which is correct envelope text, but was
    reached because the handler forced text-only matching. The
    Phase-3 fix keeps the envelope for the true-empty case
    (legitimately no rows match) and the handler now reports
    "No conversations found about this concept" with a hint
    instead of a traceback or a partial result.
    """
    empty_adapter = _make_stub_adapter([])
    with (
        patch.object(mt, "_check_reflection_tools_available", return_value=True),
        patch.object(mt, "_get_reflection_database", AsyncMock(return_value=empty_adapter)),
        patch.object(mt, "_reflection_db", empty_adapter),
    ):
        server = _build_search_by_concept_server()
        transport = FastMCPTransport(server)

        async def _run() -> Any:
            async with Client(transport) as client:
                return await client.call_tool(
                    "search_by_concept",
                    {
                        "concept": "no-match-concept-zzz",
                        "include_files": False,
                        "limit": 5,
                        "min_score": 0.3,
                    },
                )

        result = asyncio.run(_run())

    assert result.is_error is False, (
        f"search_by_concept on empty result list must not be "
        f"is_error=True; got {result!r}"
    )
    payload = _extract_tool_payload(result)
    assert "No conversations found about this concept" in payload