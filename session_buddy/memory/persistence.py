from __future__ import annotations

import hashlib
import time
import typing as t
from dataclasses import dataclass
from pathlib import Path

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

from session_buddy.memory.entity_extractor import (
    EntityRelationship,
    ExtractedEntity,
    ProcessedMemory,
)
from session_buddy.settings import get_settings as _get_settings


def get_settings() -> t.Any:
    """Local indirection for tests to monkeypatch."""
    return _get_settings()


def _connect() -> duckdb.DuckDBPyConnection:
    """Create a new DuckDB connection.

    Returns:
        Active DuckDB connection

    Raises:
        ImportError: If duckdb module is not available
    """
    if duckdb is None:
        msg = "duckdb module is not available"
        raise ImportError(msg)
    settings = get_settings()
    db_path = Path(
        str(getattr(settings, "database_path", "~/.claude/data/reflection.duckdb"))
    ).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})


def _new_id(prefix: str = "mem") -> str:
    return hashlib.md5(
        f"{prefix}_{time.time()}".encode(),
        usedforsecurity=False,
    ).hexdigest()


@dataclass(slots=True)
class PersistResult:
    memory_id: str
    entity_ids: list[str]
    relationship_ids: list[str]


def insert_processed_memory(
    pm: ProcessedMemory,
    content: str,
    *,
    project: str | None = None,
    namespace: str = "default",
    embedding: list[float] | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> PersistResult:
    """Insert a processed memory into v2 tables.

    Returns ids for the memory and inserted entities/relationships.
    """
    memory_id = _new_id("conv")
    entity_ids: list[str] = []
    relationship_ids: list[str] = []

    with _connect() as conn:
        # conversations_v2
        _insert_conversation(
            conn,
            memory_id,
            content,
            embedding,
            pm,
            project,
            namespace,
            session_id,
            user_id,
        )

        # Insert entities
        value_to_id: dict[str, str] = {}
        entity_ids = _insert_entities(conn, pm.entities, memory_id, value_to_id)

        # Insert relationships
        relationship_ids = _insert_relationships(
            conn, pm.relationships, value_to_id, memory_id
        )

    return PersistResult(
        memory_id=memory_id,
        entity_ids=entity_ids,
        relationship_ids=relationship_ids,
    )


def _insert_conversation(
    conn: duckdb.DuckDBPyConnection,
    memory_id: str,
    content: str,
    embedding: list[float] | None,
    pm: ProcessedMemory,
    project: str | None,
    namespace: str,
    session_id: str | None,
    user_id: str | None,
) -> None:
    """Insert main conversation record."""
    conn.execute(
        """
        INSERT INTO conversations_v2 (
            id, content, embedding, category, subcategory, importance_score,
            memory_tier, access_count, last_accessed, project, namespace,
            timestamp, session_id, user_id, searchable_content, reasoning
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
        """,
        [
            memory_id,
            content,
            embedding,
            pm.category,
            pm.subcategory,
            pm.importance_score,
            pm.suggested_tier,
            project,
            namespace,
            session_id,
            user_id,
            pm.searchable_content,
            pm.reasoning,
        ],
    )


def _insert_entities(
    conn: duckdb.DuckDBPyConnection,
    entities: list[ExtractedEntity],
    memory_id: str,
    value_to_id: dict[str, str],
) -> list[str]:
    """Insert entities and return their IDs."""
    entity_ids: list[str] = []
    for ent in entities:
        if not isinstance(ent, ExtractedEntity):
            # When validated from JSON, Pydantic ensures type; guard anyway
            ent = ExtractedEntity.model_validate(ent)  # type: ignore[assignment]
        ent_id = _new_id("ent")
        conn.execute(
            """
            INSERT INTO memory_entities (
                id, memory_id, entity_type, entity_value, confidence
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [ent_id, memory_id, ent.entity_type, ent.entity_value, ent.confidence],
        )
        entity_ids.append(ent_id)
        value_to_id.setdefault(ent.entity_value, ent_id)
    return entity_ids


def _insert_relationships(
    conn: duckdb.DuckDBPyConnection,
    relationships: list[EntityRelationship],
    value_to_id: dict[str, str],
    memory_id: str,
) -> list[str]:
    """Insert relationships and return their IDs."""
    relationship_ids: list[str] = []
    for rel in relationships:
        if not isinstance(rel, EntityRelationship):
            rel = EntityRelationship.model_validate(rel)  # type: ignore[assignment]
        from_id = value_to_id.get(rel.from_entity)
        to_id = value_to_id.get(rel.to_entity)
        if not (from_id and to_id):
            # Skip if referenced entity values are missing
            continue
        rel_id = _new_id("rel")
        conn.execute(
            """
            INSERT INTO memory_relationships (
                id, from_entity_id, to_entity_id, relationship_type, strength
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [rel_id, from_id, to_id, rel.relationship_type, rel.strength],
        )
        relationship_ids.append(rel_id)
    return relationship_ids


def log_memory_access(memory_id: str, access_type: str = "search") -> None:
    """Append an access log entry for later analysis by the Conscious Agent."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO memory_access_log (id, memory_id, access_type, timestamp) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            [_new_id("acc"), memory_id, access_type],
        )
