from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.adapters import reflection_adapter_oneiric as reflection_module
from session_buddy.adapters.settings import ReflectionAdapterSettings

pytest.importorskip("duckdb")


@pytest.mark.asyncio
async def test_shared_connection_survives_sibling_aclose(tmp_path: Path) -> None:
    """Closing one adapter must not close a connection shared by another."""
    db_path = tmp_path / "shared.duckdb"
    settings = ReflectionAdapterSettings(
        database_path=db_path,
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )
    first = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    second = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)

    try:
        await first.initialize()
        await second.initialize()
        cache_key = str(db_path.resolve())
        cached = reflection_module._typed_connection_cache[cache_key]
        assert cached.ref_count == 2
        assert first.conn is second.conn

        await first.aclose()

        assert cached.ref_count == 1
        assert second.conn is not None
        assert second.conn.execute("SELECT 1").fetchone() == (1,)
        await second.store_conversation("shared lifecycle marker")
        results = await second.search_conversations(
            "shared lifecycle marker", use_cache=True
        )
        assert any(result["content"] == "shared lifecycle marker" for result in results)
    finally:
        await first.aclose()
        await second.aclose()

    assert cache_key not in reflection_module._typed_connection_cache

    replacement = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    try:
        await replacement.initialize()
        assert replacement.conn is not None
        assert replacement.conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        await replacement.aclose()


@pytest.mark.asyncio
async def test_aclose_is_idempotent_for_cached_connection(tmp_path: Path) -> None:
    """Repeated close calls must not decrement another adapter's reference."""
    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "idempotent.duckdb",
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )
    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()
    cache_key = str(Path(settings.database_path).resolve())

    await adapter.aclose()
    await adapter.aclose()

    assert cache_key not in reflection_module._typed_connection_cache
