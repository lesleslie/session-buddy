"""Phase B Task 5 — Cross-namespace ACL for sb caller.

REQ-OSUB-B-004: an sb.caller (Session-Buddy) MUST NOT read akosha.* collections
by default. Without an explicit cross_namespace_grant the PgvectorAdapter raises
PermissionError before issuing SQL.

These tests run against a fake pool (mirroring oneiric/tests/adapters/
test_pgvector_adapter.py). When SB_TEST_PGVECTOR_URL is set the same assertions
apply against a live Postgres stack — see test_search_against_live_stack.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from oneiric.adapters.vector.pgvector import PgvectorAdapter, PgvectorSettings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.req("REQ-OSUB-B-004"),
]


class _FakePgConnection:
    """Minimal asyncpg stub that records every executed statement."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.search_results: list[dict[str, Any]] = []

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query.strip()))
        return "OK"

    async def fetch(self, query: str, *args: Any):
        self.calls.append(("fetch", query.strip()))
        if "ORDER BY distance" in query:
            return self.search_results
        return []

    async def fetchrow(self, query: str, *args: Any):
        self.calls.append(("fetchrow", query.strip()))
        return {"id": args[0] if args else "row"}

    async def fetchval(self, query: str, *args: Any):
        self.calls.append(("fetchval", query.strip()))
        return 0


class _FakePgPool:
    def __init__(self) -> None:
        self.connection = _FakePgConnection()
        self.closed = False

    async def acquire(self) -> _FakePgConnection:
        return self.connection

    async def release(self, _conn: _FakePgConnection) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


def _make_adapter(
    *,
    caller_namespace: str = "sb",
    cross_namespace_grant: bool = False,
) -> tuple[PgvectorAdapter, _FakePgPool]:
    pool = _FakePgPool()

    async def pool_factory(**kwargs: Any) -> _FakePgPool:
        return pool

    async def register_vector(_conn: Any) -> None:
        return None

    adapter = PgvectorAdapter(
        PgvectorSettings(
            caller_namespace=caller_namespace,
            cross_namespace_grant=cross_namespace_grant,
            dsn="postgresql://stub/sb",
        ),
        pool_factory=pool_factory,
        register_vector=register_vector,
    )
    return adapter, pool


async def test_sb_caller_cannot_read_akosha_namespace_by_default() -> None:
    """Per spec §6.2 — sb without grant MUST NOT read akosha.* (PermissionError)."""
    adapter, pool = _make_adapter(caller_namespace="sb", cross_namespace_grant=False)

    with pytest.raises(PermissionError, match=r"target_namespace='akosha'"):
        await adapter.search(
            collection="reflections",
            query_vector=[0.0] * 4,
            limit=5,
            namespace="akosha",
        )

    # ACL MUST short-circuit before any SQL touches the connection — proves the
    # denial is enforcement, not after-the-fact failure.
    assert pool.connection.calls == [], (
        "ACL bypassed: search() ran SQL despite default-deny"
    )


async def test_sb_caller_can_read_own_namespace() -> None:
    """Same-namespace reads are always allowed — the ACL grants no extra."""
    adapter, pool = _make_adapter(caller_namespace="sb")
    pool.connection.search_results = [
        {
            "id": "refl1",
            "metadata": {"topic": "self-read"},
            "embedding": [0.1, 0.2, 0.3, 0.4],
            "distance": 0.05,
        }
    ]

    # Explicit namespace matches caller → allowed.
    results = await adapter.search(
        collection="reflections",
        query_vector=[0.1, 0.2, 0.3, 0.4],
        limit=5,
        namespace="sb",
    )
    assert [r.id for r in results] == ["refl1"]

    # Omitting namespace defaults to caller_namespace — also allowed.
    results = await adapter.search(
        collection="reflections",
        query_vector=[0.1, 0.2, 0.3, 0.4],
        limit=5,
    )
    assert [r.id for r in results] == ["refl1"]


async def test_sb_caller_cannot_read_akosha_collection_explicit_namespace() -> None:
    """Even with a different collection name, namespace= is the ACL key."""
    adapter, pool = _make_adapter(caller_namespace="sb", cross_namespace_grant=False)

    with pytest.raises(PermissionError):
        await adapter.search(
            collection="vectors_akosha_steal",
            query_vector=[0.0] * 4,
            limit=10,
            namespace="akosha",
        )
    assert pool.connection.calls == []


# Live-stack opt-in: skip unless SB_TEST_PGVECTOR_URL is set. This keeps the
# suite green in environments without local pgvector, while still exercising
# the real connection when one is available (matches akosha's existing
# AKOSHA_TEST_PGVECTOR_URL pattern).
LIVE_PGVECTOR_URL = os.environ.get("SB_TEST_PGVECTOR_URL", "").strip()
live_stack_required = pytest.mark.skipif(
    not LIVE_PGVECTOR_URL,
    reason="SB_TEST_PGVECTOR_URL not set — skipping live-stack assertion",
)


@live_stack_required
async def test_sb_caller_default_deny_against_live_pgvector() -> None:
    """Same default-deny assertion against a real Postgres + pgvector stack."""
    settings = PgvectorSettings(
        dsn=LIVE_PGVECTOR_URL,
        caller_namespace="sb",
        cross_namespace_grant=False,
    )
    adapter = PgvectorAdapter(settings)
    with pytest.raises(PermissionError, match=r"target_namespace='akosha'"):
        await adapter.search(
            collection="reflections",
            query_vector=[0.0] * 4,
            limit=5,
            namespace="akosha",
        )
    await adapter.cleanup()
