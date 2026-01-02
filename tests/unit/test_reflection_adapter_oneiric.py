from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from session_buddy.adapters import reflection_adapter_oneiric as reflection_module
from session_buddy.adapters.settings import ReflectionAdapterSettings

if TYPE_CHECKING:
    from pathlib import Path


async def test_text_search_handles_quotes(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")

    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "reflection.duckdb",
        enable_embeddings=False,
        enable_vss=False,
    )
    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()

    await adapter.store_conversation("O'Reilly test", {"source": "unit"})
    results = await adapter.search_conversations("O'Reilly", limit=5)

    assert results


async def test_store_reflection_writes_vector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("duckdb")

    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "reflection.duckdb",
        enable_embeddings=False,
    )
    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()

    monkeypatch.setattr(reflection_module, "ONNX_AVAILABLE", True)
    adapter.onnx_session = object()

    async def _fake_embedding(_: str) -> list[float]:
        return [0.0] * adapter.embedding_dim

    monkeypatch.setattr(adapter, "_generate_embedding", _fake_embedding)

    reflection_id = await adapter.store_reflection("hello world", tags=["test"])
    row = adapter.conn.execute(
        f"SELECT embedding FROM {adapter.collection_name}_reflections WHERE id = ?",
        (reflection_id,),
    ).fetchone()

    assert isinstance(row[0], (list, tuple))
    assert len(row[0]) == adapter.embedding_dim
