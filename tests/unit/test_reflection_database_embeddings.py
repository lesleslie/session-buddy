"""Tests for embedding generation in the legacy ``ReflectionDatabase``.

The ONNX removal left this class gating every embedding call on a
backward-compat stub (``onnx_session``) that always returned ``None``.
Nothing was ever stored with an embedding and semantic search never ran,
so the class silently degraded to text-only search even though the HTTP
embedding provider was reachable.

These tests pin the gate itself. The write path still targets the V1
``conversations`` table that ``reflection/schema.py`` retired on
2026-10-04 (the schema bootstrap creates the V2 tables instead), so that
table is created explicitly here. The V1/V2 mismatch is tracked
separately — it is why the class only works against a database that still
carries the retired V1 tables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from session_buddy.memory.embedding_dim import DEFAULT_EMBEDDING_DIM
from session_buddy.reflection.database import ReflectionDatabase

V1_CONVERSATIONS_DDL = """
CREATE TABLE conversations (
    id VARCHAR PRIMARY KEY,
    content VARCHAR NOT NULL,
    embedding FLOAT[{dim}],
    project VARCHAR,
    timestamp TIMESTAMP,
    metadata JSON
)
"""

V1_REFLECTIONS_DDL = """
CREATE TABLE reflections (
    id VARCHAR PRIMARY KEY,
    content VARCHAR NOT NULL,
    embedding FLOAT[{dim}],
    project VARCHAR,
    tags VARCHAR[],
    timestamp TIMESTAMP,
    metadata JSON
)
"""


def _create_v1_tables(db: Any) -> None:
    """Create the V1 tables the legacy write path targets."""
    conn = db.conn
    assert conn is not None
    conn.execute(V1_CONVERSATIONS_DDL.format(dim=DEFAULT_EMBEDDING_DIM))
    conn.execute(V1_REFLECTIONS_DDL.format(dim=DEFAULT_EMBEDDING_DIM))


@pytest.fixture
async def legacy_db(tmp_path: Path) -> Any:
    """A ``ReflectionDatabase`` over V1-shaped ``conversations``/``reflections``."""
    db = ReflectionDatabase(db_path=str(tmp_path / "legacy.duckdb"))
    await db.initialize()
    _create_v1_tables(db)
    yield db
    db.close()


@pytest.fixture
def stub_provider(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the HTTP provider with a deterministic canonical-width vector.

    Returns the list of texts the provider was asked to embed.
    """
    asked: list[str] = []

    async def fake_generate_embedding(text: str) -> list[float]:
        asked.append(text)
        return [0.5] * DEFAULT_EMBEDDING_DIM

    monkeypatch.setattr(
        "session_buddy.reflection.database.generate_embedding",
        fake_generate_embedding,
    )
    return asked


class TestEmbeddingGate:
    """The gate decides whether embeddings are generated at all."""

    async def test_store_conversation_generates_an_embedding(
        self, legacy_db: Any, stub_provider: list[str]
    ) -> None:
        """With the gate open, the provider is asked and the vector stored."""
        await legacy_db.store_conversation("hello world", {"project": "demo"})

        assert stub_provider == ["hello world"]

        conn = legacy_db.conn
        assert conn is not None
        row = conn.execute("SELECT embedding FROM conversations").fetchone()
        assert row is not None
        assert row[0] is not None, "conversation was stored without an embedding"
        assert len(row[0]) == DEFAULT_EMBEDDING_DIM

    async def test_store_conversation_skips_embeddings_when_disabled(
        self, tmp_path: Path, stub_provider: list[str]
    ) -> None:
        """With the gate closed, the provider is never called."""
        db = ReflectionDatabase(
            db_path=str(tmp_path / "disabled.duckdb"), enable_embeddings=False
        )
        await db.initialize()
        _create_v1_tables(db)
        conn = db.conn
        assert conn is not None

        await db.store_conversation("hello world", {"project": "demo"})

        assert stub_provider == []
        row = conn.execute("SELECT embedding FROM conversations").fetchone()
        assert row is not None
        assert row[0] is None

        db.close()

    async def test_provider_failure_degrades_to_text_search(
        self, legacy_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unreachable provider must not stop the conversation being stored."""

        async def failing_generate_embedding(text: str) -> list[float]:
            raise RuntimeError("embedding provider unreachable")

        monkeypatch.setattr(
            "session_buddy.reflection.database.generate_embedding",
            failing_generate_embedding,
        )

        await legacy_db.store_conversation("still stored", {"project": "demo"})

        conn = legacy_db.conn
        assert conn is not None
        row = conn.execute(
            "SELECT content, embedding FROM conversations"
        ).fetchone()
        assert row is not None
        assert row[0] == "still stored"
        assert row[1] is None, "a failed provider must not store a partial vector"

    async def test_get_stats_reports_the_embedding_provider(
        self, legacy_db: Any
    ) -> None:
        """``get_stats`` must reflect whether embeddings are enabled."""
        stats = await legacy_db.get_stats()
        assert stats["embedding_provider"] == "http-embedding-providers"
        assert stats["embedding_dimension"] == DEFAULT_EMBEDDING_DIM

    async def test_get_stats_reports_text_only_when_disabled(
        self, tmp_path: Path
    ) -> None:
        """``get_stats`` must not claim an embedding provider that is off."""
        db = ReflectionDatabase(
            db_path=str(tmp_path / "disabled_stats.duckdb"), enable_embeddings=False
        )
        await db.initialize()
        _create_v1_tables(db)

        stats = await db.get_stats()
        assert stats["embedding_provider"] == "text-search-only"

        db.close()
