from __future__ import annotations

import typing as t
from types import SimpleNamespace

import duckdb
from session_buddy.memory.entity_extractor import ProcessedMemory
from session_buddy.memory.persistence import insert_processed_memory
from session_buddy.memory.schema_v2 import SCHEMA_V2_SQL


def test_insert_processed_memory_inserts_all(
    tmp_path: t.Any, monkeypatch: t.Any
) -> None:
    # Prepare isolated DuckDB path via settings monkeypatch
    db_path = tmp_path / "persistence.duckdb"
    # New shape (Phase 3a): settings.database.path (nested).
    fake_settings = SimpleNamespace(
        database=SimpleNamespace(path=str(db_path))
    )

    # Patch the symbol used inside persistence module
    import session_buddy.memory.persistence as persistence_mod

    monkeypatch.setattr(persistence_mod, "get_settings", lambda: fake_settings)

    # Create v2 schema tables
    conn = duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})
    conn.execute(SCHEMA_V2_SQL)
    conn.close()

    # Build a minimal ProcessedMemory with one entity and one relationship
    pm = ProcessedMemory.model_validate(
        {
            "category": "facts",
            "importance_score": 0.7,
            "summary": "sum",
            "searchable_content": "x",
            "reasoning": "r",
            "entities": [
                {"entity_type": "file", "entity_value": "README.md", "confidence": 0.9}
            ],
            "relationships": [
                {
                    "from_entity": "README.md",
                    "to_entity": "README.md",
                    "relationship_type": "related_to",
                    "strength": 1.0,
                }
            ],
            "suggested_tier": "long_term",
            "tags": ["t"],
        }
    )

    insert_processed_memory(pm, content="c")

    # Verify rows present
    conn = duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})
    c2 = conn.execute("SELECT COUNT(*) FROM conversations_v2").fetchone()[0]
    e2 = conn.execute("SELECT COUNT(*) FROM memory_entities").fetchone()[0]
    r2 = conn.execute("SELECT COUNT(*) FROM memory_relationships").fetchone()[0]
    assert int(c2) == 1
    assert int(e2) == 1
    assert int(r2) == 1
    conn.close()
