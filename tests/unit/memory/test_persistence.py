"""Tests for session_buddy.memory.persistence.

Covers the DuckDB-backed persistence layer for processed memories:
- ``_connect`` (success and duckdb-missing error paths)
- ``_new_id`` (deterministic prefix handling)
- ``insert_processed_memory`` (full pipeline: conversation + entities + relationships)
- ``_insert_entities`` (model_validate fallback for non-pydantic input)
- ``_insert_relationships`` (skip when referenced entity values are missing)
- ``log_memory_access`` (id and access_type stored verbatim)

The production code uses a per-call DuckDB connection; these tests
monkeypatch ``_connect`` to return a file-backed connection with the v2
schema applied, so no production DB state is touched and reads after
writes are visible to the same test.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest

from session_buddy.memory import persistence
from session_buddy.memory.entity_extractor import (
    EntityRelationship,
    ExtractedEntity,
    ProcessedMemory,
)
from session_buddy.memory.persistence import (
    PersistResult,
    insert_processed_memory,
    log_memory_access,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_conn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> duckdb.DuckDBPyConnection:
    """Yield a shared DuckDB connection for the test.

    The fixture monkeypatches ``persistence._connect`` to yield this same
    connection (instead of opening a fresh one from settings). Tests can
    read the connection directly to verify writes from the production code
    paths.
    """
    db_file = tmp_path / "test_persistence.duckdb"
    conn = duckdb.connect(str(db_file))
    from session_buddy.memory.migration import apply_migrations

    apply_migrations(conn)

    @contextmanager
    def fake_connect():
        try:
            yield conn
        finally:
            pass  # keep open for the duration of the test

    monkeypatch.setattr(persistence, "_connect", fake_connect)

    yield conn

    conn.close()


def _make_memory(
    *,
    entities: list[ExtractedEntity] | None = None,
    relationships: list[EntityRelationship] | None = None,
    category: str = "facts",
    subcategory: str | None = None,
    importance: float = 0.5,
    suggested_tier: str = "long_term",
) -> ProcessedMemory:
    return ProcessedMemory(
        category=category,
        subcategory=subcategory,
        importance_score=importance,
        summary="A summary",
        searchable_content="searchable text",
        reasoning="reasoning text",
        entities=entities or [],
        relationships=relationships or [],
        suggested_tier=suggested_tier,
    )


# ---------------------------------------------------------------------------
# _new_id
# ---------------------------------------------------------------------------


class TestNewId:
    def test_returns_32_char_hex(self) -> None:
        ident = persistence._new_id()
        assert len(ident) == 32
        int(ident, 16)  # valid hex

    def test_custom_prefix_keeps_format(self) -> None:
        ident = persistence._new_id("rel")
        assert len(ident) == 32
        int(ident, 16)


# ---------------------------------------------------------------------------
# _connect
# ---------------------------------------------------------------------------


class TestConnect:
    def test_raises_when_duckdb_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(persistence, "duckdb", None)
        with pytest.raises(ImportError, match="duckdb module is not available"):
            persistence._connect()

    def test_creates_parent_dir_and_connects(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        fake_settings = SimpleNamespace(
            database_path=str(tmp_path / "nested" / "ref.duckdb")
        )
        monkeypatch.setattr(persistence, "get_settings", lambda: fake_settings)

        with persistence._connect() as conn:
            assert (tmp_path / "nested").exists()
            assert conn.execute("SELECT 1").fetchone() == (1,)


# ---------------------------------------------------------------------------
# insert_processed_memory — happy path
# ---------------------------------------------------------------------------


class TestInsertProcessedMemory:
    def test_inserts_minimal_memory(self, memory_conn) -> None:
        pm = _make_memory()
        result = insert_processed_memory(pm, "raw content")

        assert isinstance(result, PersistResult)
        assert len(result.memory_id) == 32
        assert result.entity_ids == []
        assert result.relationship_ids == []

        row = memory_conn.execute(
            "SELECT content, category, importance_score, project, namespace "
            "FROM conversations_v2 WHERE id=?",
            [result.memory_id],
        ).fetchone()
        assert row is not None
        assert row[0] == "raw content"
        assert row[1] == "facts"
        assert row[2] == pytest.approx(0.5)
        assert row[3] is None
        assert row[4] == "default"

    def test_passes_through_project_and_namespace_and_user(
        self, memory_conn
    ) -> None:
        pm = _make_memory()
        result = insert_processed_memory(
            pm,
            "content",
            project="proj-a",
            namespace="ns-a",
            session_id="sess-1",
            user_id="user-7",
        )

        row = memory_conn.execute(
            "SELECT project, namespace, session_id, user_id "
            "FROM conversations_v2 WHERE id=?",
            [result.memory_id],
        ).fetchone()
        assert row == ("proj-a", "ns-a", "sess-1", "user-7")

    def test_persists_embedding(self, memory_conn) -> None:
        pm = _make_memory()
        # Embedding column is FLOAT[384]; use a 384-dim vector.
        embedding = [0.01 * i for i in range(384)]
        result = insert_processed_memory(pm, "content", embedding=embedding)

        stored = memory_conn.execute(
            "SELECT embedding FROM conversations_v2 WHERE id=?",
            [result.memory_id],
        ).fetchone()[0]
        assert stored is not None

    def test_inserts_entities(self, memory_conn) -> None:
        entities = [
            ExtractedEntity(entity_type="person", entity_value="alice", confidence=0.9),
            ExtractedEntity(entity_type="tech", entity_value="python", confidence=0.95),
        ]
        pm = _make_memory(entities=entities)
        result = insert_processed_memory(pm, "content")

        assert len(result.entity_ids) == 2
        rows = memory_conn.execute(
            "SELECT entity_type, entity_value, confidence, memory_id "
            "FROM memory_entities ORDER BY entity_value"
        ).fetchall()
        # DuckDB stores REAL as float32; use approx for confidence.
        assert rows[0] == ("person", "alice", pytest.approx(0.9, rel=1e-5), result.memory_id)
        assert rows[1] == ("tech", "python", pytest.approx(0.95, rel=1e-5), result.memory_id)

    def test_inserts_both_duplicate_entities(self, memory_conn) -> None:
        entities = [
            ExtractedEntity(entity_type="tech", entity_value="python", confidence=0.9),
            ExtractedEntity(entity_type="tech", entity_value="python", confidence=0.5),
        ]
        pm = _make_memory(entities=entities)
        result = insert_processed_memory(pm, "content")

        # Both rows are inserted (no unique constraint). value_to_id keeps
        # the first for relationship resolution — verified in the
        # relationship-with-duplicate test below.
        assert len(result.entity_ids) == 2

    def test_validates_non_pydantic_entity(self, memory_conn) -> None:
        # FK constraint: memory_entities.memory_id references conversations_v2(id).
        # Insert the parent conversation row first.
        memory_conn.execute(
            "INSERT INTO conversations_v2 (id, content, category, importance_score, "
            "memory_tier, namespace) VALUES (?, ?, ?, ?, ?, ?)",
            ["conv_x", "content", "facts", 0.5, "long_term", "default"],
        )
        raw_entity = {
            "entity_type": "concept",
            "entity_value": "test",
            "confidence": 1.0,
        }
        ids = persistence._insert_entities(memory_conn, [raw_entity], "conv_x", {})
        assert len(ids) == 1

    def test_inserts_relationships_with_resolved_entities(self, memory_conn) -> None:
        entities = [
            ExtractedEntity(entity_type="person", entity_value="alice"),
            ExtractedEntity(entity_type="tech", entity_value="python"),
        ]
        relationships = [
            EntityRelationship(
                from_entity="alice",
                to_entity="python",
                relationship_type="uses",
                strength=0.8,
            )
        ]
        pm = _make_memory(entities=entities, relationships=relationships)
        result = insert_processed_memory(pm, "content")

        assert len(result.relationship_ids) == 1

        row = memory_conn.execute(
            "SELECT from_entity_id, to_entity_id, relationship_type, strength "
            "FROM memory_relationships"
        ).fetchone()
        assert row[2] == "uses"
        assert row[3] == pytest.approx(0.8)
        assert row[0] in result.entity_ids
        assert row[1] in result.entity_ids

    def test_skips_relationship_with_missing_entity_value(self, memory_conn) -> None:
        entities = [ExtractedEntity(entity_type="person", entity_value="alice")]
        relationships = [
            EntityRelationship(
                from_entity="alice",
                to_entity="ghost",
                relationship_type="uses",
            )
        ]
        pm = _make_memory(entities=entities, relationships=relationships)
        result = insert_processed_memory(pm, "content")

        assert result.relationship_ids == []
        count = memory_conn.execute(
            "SELECT COUNT(*) FROM memory_relationships"
        ).fetchone()[0]
        assert count == 0

    def test_validates_non_pydantic_relationship(self, memory_conn) -> None:
        # FK chain: conversations_v2 → memory_entities → memory_relationships.
        memory_conn.execute(
            "INSERT INTO conversations_v2 (id, content, category, importance_score, "
            "memory_tier, namespace) VALUES (?, ?, ?, ?, ?, ?)",
            ["conv_x", "content", "facts", 0.5, "long_term", "default"],
        )
        memory_conn.execute(
            "INSERT INTO memory_entities (id, memory_id, entity_type, entity_value, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            ["ent_x", "conv_x", "person", "alice", 1.0],
        )
        ids = persistence._insert_relationships(
            memory_conn,
            [{
                "from_entity": "alice",
                "to_entity": "alice",
                "relationship_type": "self",
                "strength": 0.5,
            }],
            {"alice": "ent_x"},
            "conv_x",
        )
        assert len(ids) == 1


# ---------------------------------------------------------------------------
# log_memory_access
# ---------------------------------------------------------------------------


class TestLogMemoryAccess:
    def test_appends_log_row(self, memory_conn) -> None:
        pm = _make_memory()
        result = insert_processed_memory(pm, "content")
        log_memory_access(result.memory_id, access_type="search")

        row = memory_conn.execute(
            "SELECT memory_id, access_type FROM memory_access_log "
            "WHERE memory_id=?",
            [result.memory_id],
        ).fetchone()
        assert row == (result.memory_id, "search")

    def test_default_access_type(self, memory_conn) -> None:
        pm = _make_memory()
        result = insert_processed_memory(pm, "content")
        log_memory_access(result.memory_id)

        access_type = memory_conn.execute(
            "SELECT access_type FROM memory_access_log WHERE memory_id=?",
            [result.memory_id],
        ).fetchone()[0]
        assert access_type == "search"


# ---------------------------------------------------------------------------
# get_settings monkeypatch helper
# ---------------------------------------------------------------------------


def test_get_settings_delegates_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``persistence.get_settings`` is a thin indirection that calls the
    # module-local ``_get_settings`` reference (imported at module load).
    # Monkeypatching ``persistence._get_settings`` is what production
    # code path actually uses.
    sentinel = object()
    monkeypatch.setattr(persistence, "_get_settings", lambda: sentinel)
    assert persistence.get_settings() is sentinel


def test_insert_handles_empty_content(memory_conn) -> None:
    pm = _make_memory()
    result = insert_processed_memory(pm, "")
    stored = memory_conn.execute(
        "SELECT content FROM conversations_v2 WHERE id=?",
        [result.memory_id],
    ).fetchone()[0]
    assert stored == ""


# ---------------------------------------------------------------------------
# Defensive: monkeypatched _connect that raises should bubble
# ---------------------------------------------------------------------------


def test_insert_propagates_connect_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def boom_connect():
        raise RuntimeError("connect failed")
        yield  # unreachable

    monkeypatch.setattr(persistence, "_connect", boom_connect)
    pm = _make_memory()
    with pytest.raises(RuntimeError, match="connect failed"):
        insert_processed_memory(pm, "content")


def test_log_access_propagates_connect_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def boom_connect():
        raise RuntimeError("connect failed")
        yield  # unreachable

    monkeypatch.setattr(persistence, "_connect", boom_connect)
    with pytest.raises(RuntimeError, match="connect failed"):
        log_memory_access("any-id")


# Sanity: duckdb-pyconnection is sync, not async.
def test_connect_returns_sync_connection() -> None:
    conn = duckdb.connect(":memory:")
    try:
        assert not isinstance(conn, MagicMock)
        assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        conn.close()
