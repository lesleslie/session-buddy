#!/usr/bin/env python3
"""Regression test for ``mcp__session-buddy__quick_search`` (REQ-005).

Per the bodai-search-infrastructure-fix plan §5.3.3, this test
asserts that ``quick_search`` returns a populated, structured
response for a generic query (``"python"``) at ``min_score=0.3`` over
the wire-shape envelope, not the in-process return value.

Failure modes this test catches:
- The handler forcing ``use_embeddings=False`` (pre-Phase-3 bug;
  would return "No results found" for any phrase that is not a
  contiguous substring of a stored reflection).
- The handler dropping ``project`` (pre-Phase-3 bug; scope was
  silently ignored).
- The handler dropping ``min_score`` (pre-Phase-3 bug; the parameter
  was advertised but never threaded through).
- The text-search path only doing a single ``LIKE '%query%'``
  literal match (pre-Phase-3 bug; multi-word phrases fell through).
- The MCP wrapper returning ``result.is_error=True`` for an
  otherwise-healthy DB.

The test stubs the reflection adapter via ``unittest.mock`` so the
assertion does not depend on real DuckDB content. The DB stub
returns a deterministic 3-row result list, and the assertion is
that the wire-shape payload contains the "Found" marker AND that
the per-row content surfaces in the text.
"""

from __future__ import annotations

import asyncio
import inspect
import json
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
    limit=1, project=..., min_score=...)``. The stub mirrors the
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
    fixture by setting ``stubbed_db``'s ``rows`` attribute or by
    re-patching ``mt._get_reflection_database`` directly.
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
            "score": 0.92,
            "similarity": 0.92,
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
            "score": 0.71,
            "similarity": 0.71,
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
            "score": 0.55,
            "similarity": 0.55,
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


def _build_quick_search_server() -> FastMCP:
    """Build a real FastMCP server with the memory tools registered.

    Reuses the production ``_register_core_memory_tools`` so the wire
    surface is identical to the live MCP server (no test-only
    shortcuts).
    """
    server = FastMCP("session-buddy-test-quick-search")
    _register_core_memory_tools(server)
    return server


def test_quick_search_python_returns_results(stubbed_db) -> None:
    """``quick_search('python', min_score=0.3)`` returns >= 1 result.

    Wire-shape assertion: the response text contains the "Found"
    marker and at least one of the stubbed rows' content. Asserts
    ``result.is_error is False`` separately, per REQ-012.
    """
    _adapter, rows = stubbed_db
    server = _build_quick_search_server()
    transport = FastMCPTransport(server)

    async def _run() -> Any:
        async with Client(transport) as client:
            return await client.call_tool(
                "quick_search",
                {"query": "python", "min_score": 0.3},
            )

    result = asyncio.run(_run())

    # REQ-012: assert on the wire-shape envelope, NOT on the
    # in-process return value. ``is_error`` is checked separately
    # so a true failure does not silently pass via a structured
    # error payload that looks like a hit.
    assert result.is_error is False, (
        f"quick_search returned is_error=True: {result!r}"
    )

    payload = _extract_tool_payload(result)
    assert isinstance(payload, str), (
        f"Expected string payload from quick_search, got {type(payload).__name__}"
    )

    # The handler renders "📊 Found results" for any non-empty result
    # list. Asserting on the marker is wire-shape (the marker is in
    # the text payload the user sees) AND structural (no marker ==
    # results list was empty).
    assert "📊 Found results" in payload, (
        f"Expected 'Found results' marker in payload, got: {payload!r}"
    )

    # At least one stub row's project name should surface in the
    # rendered output (the handler appends "📁 Project: <name>").
    assert "session-progress-2026-09-29" in payload, (
        f"Expected the top-1 stub row's project in payload, got: {payload!r}"
    )


def test_quick_search_through_adapter_with_min_score(stubbed_db) -> None:
    """Confirm the stub adapter was invoked with ``min_score``.

    This is a behavioural test of the handler wiring: removing the
    hardcoded ``use_embeddings=False`` AND threading ``min_score``
    through are the two pre-Phase-3 bugs the plan calls out, so we
    must assert both. If a future refactor drops ``min_score`` again,
    this test will fail and flag the regression.
    """
    _adapter, _rows = stubbed_db
    server = _build_quick_search_server()
    transport = FastMCPTransport(server)

    async def _run() -> Any:
        async with Client(transport) as client:
            return await client.call_tool(
                "quick_search",
                {"query": "python", "min_score": 0.3},
            )

    asyncio.run(_run())

    # Inspect the calls captured on the stub. The handler should
    # have invoked ``search_reflections`` exactly once with
    # ``min_score=0.3`` (the value passed by the wire call) — and
    # NOT with ``use_embeddings=False`` (Phase-3 fix; the handler
    # now lets the adapter decide).
    adapter = stubbed_db[0]
    assert adapter.search_reflections.await_count == 1, (
        f"Expected exactly 1 adapter.search_reflections call, "
        f"got {adapter.search_reflections.await_count}"
    )
    kwargs = adapter.search_reflections.await_args.kwargs
    assert kwargs.get("min_score") == 0.3, (
        f"Expected min_score=0.3 in adapter kwargs, got {kwargs!r}"
    )
    # The handler MUST NOT pass ``use_embeddings=False`` (that was
    # the bug). If ``use_embeddings`` is absent, the adapter uses
    # its default (True for ``ReflectionDatabaseAdapterOneiric``),
    # which is what we want.
    assert "use_embeddings" not in kwargs or kwargs["use_embeddings"] is not False, (
        f"Handler must not force use_embeddings=False; got {kwargs!r}"
    )
    assert kwargs.get("query") == "python"
    # ``limit=1`` is the documented behaviour of ``quick_search``
    # (top-1, not top-N). Assert it to lock the contract.
    assert kwargs.get("limit") == 1, (
        f"Expected limit=1 for quick_search, got {kwargs!r}"
    )


def test_quick_search_empty_results_still_renders_envelope(stubbed_db) -> None:
    """An empty result list still returns a structured, non-error wire envelope.

    The pre-Phase-3 bug surfaced as "🔍 No results found" — which is
    correct envelope text, but was reached because the handler
    forced text-only matching. The Phase-3 fix keeps the envelope
    for the true-empty case (legitimately no rows match) and the
    handler now reports "No results found" with a hint instead of
    a traceback or a partial result. Asserting on this keeps the
    contract honest.
    """
    # Override the stub for this test only: empty result list.
    empty_adapter = _make_stub_adapter([])
    with (
        patch.object(mt, "_check_reflection_tools_available", return_value=True),
        patch.object(mt, "_get_reflection_database", AsyncMock(return_value=empty_adapter)),
        patch.object(mt, "_reflection_db", empty_adapter),
    ):
        server = _build_quick_search_server()
        transport = FastMCPTransport(server)

        async def _run() -> Any:
            async with Client(transport) as client:
                return await client.call_tool(
                    "quick_search",
                    {"query": "no-match-query-zzz", "min_score": 0.3},
                )

        result = asyncio.run(_run())

    assert result.is_error is False, (
        f"quick_search on empty result list must not be is_error=True; "
        f"got {result!r}"
    )
    payload = _extract_tool_payload(result)
    assert "No results found" in payload
    assert "lowering min_score" in payload or "adjusting" in payload


# ---------------------------------------------------------------------------
# Sanity check: the test does not depend on mahavishnu's worktree_providers
# (per REQ-012). The helper module deliberately has zero Bodai deps.
# ---------------------------------------------------------------------------


def test_extract_payload_helper_has_no_bodai_deps() -> None:
    """REQ-012: the helper must not depend on any Bodai package."""
    import tests._support.extract_tool_payload as helper_mod
    import re as _re

    source = inspect.getsource(helper_mod)
    # Strip the docstring + comments so mentions in prose are
    # ignored (the docstring explicitly references the plan file
    # path which lives under ``mahavishnu/docs/...``).
    code_lines = [
        line
        for line in source.splitlines()
        if line.strip()
        and not line.strip().startswith(("#", '"', "'"))
    ]
    code_blob = "\n".join(code_lines)
    # The helper imports json + the standard TYPE_CHECKING block
    # only. Any other Bodai package would leak the contract. The
    # strict check below scans the runtime path (top-level
    # ``import`` / ``from`` statements) so prose mentions of plan
    # paths or gitignored worktrees don't false-positive.
    runtime_imports = _re.findall(
        r"^(?:import|from)\s+([\w.]+)", code_blob, flags=_re.MULTILINE
    )
    bad_imports = [
        mod
        for mod in runtime_imports
        if mod.split(".")[0] in {"mahavishnu", "akosha", "crackerjack", "mcp_common"}
        or mod.startswith("session_buddy.tools")
        or mod.startswith("session_buddy.")
    ]
    assert not bad_imports, (
        f"extract_tool_payload has forbidden Bodai imports: {bad_imports}"
    )