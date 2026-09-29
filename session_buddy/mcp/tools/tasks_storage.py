"""SQLModel-backed task metadata persistence.

T4 fix round 2 (2026-09-29): introduces SQLModel for the task system
ONLY. The rest of session-buddy keeps its existing raw-SQL adapter;
broader SQLModel adoption is a separate decision.

Architecture
------------
The task system needs to attach a ``metadata`` JSON blob to a stored
reflection so downstream ``tasks_list`` (T5) can filter by discriminator
fields like ``kind=task`` or ``owner=user:les``. The existing
``reflection_adapter_oneiric.store_reflection`` does not accept a
``metadata=`` kwarg, and the ``reflections`` table already has a
``metadata`` JSON column that the adapter never writes.

This module adds a *sidecar* SQLModel-managed SQLite table keyed by
reflection_id. We use SQLite (rather than extending the DuckDB adapter)
because SQLAlchemy has no in-tree DuckDB dialect and the brief scopes
this fix to ``sqlmodel>=0.0.16`` only — adding ``duckdb-engine`` is out
of scope.

The sidecar is logically "the metadata for the reflections table": each
row's ``id`` column mirrors a reflection_id in the canonical DuckDB
``reflections_v2`` table, and ``metadata_json`` holds the JSON blob the
caller passed to ``store_reflection(metadata=...)``. Cross-DB
consistency: a reflection row in DuckDB without a sidecar row simply
has no metadata; a sidecar row whose reflection was deleted from DuckDB
is orphaned and ignored by ``find_tasks_by_metadata`` consumers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine
from sqlmodel import JSON, Field, Session, SQLModel, create_engine, select


class ReflectionMetadata(SQLModel, table=True):
    """Sidecar row mapping a reflection_id to its metadata JSON blob.

    ``__tablename__`` is ``"reflections"`` so the SQLModel schema mirrors
    the conceptual name from the brief. The physical database is a
    separate SQLite file (``tasks_metadata.sqlite`` by default) — this
    table is NOT the same physical table as the DuckDB ``reflections_v2``
    table managed by the reflection adapter. See the module docstring for
    the cross-DB consistency model.

    Only the columns the task system needs are declared; the underlying
    DuckDB ``reflections_v2`` table has many other columns (content,
    tags, embedding, etc.) that are invisible to this model. Inserting a
    row here does NOT create a reflection in DuckDB — it only attaches
    metadata to an already-stored reflection id.
    """

    __tablename__ = "reflections"

    # VARCHAR PK mirrors the reflection_id (a ULID string) written by
    # the existing reflection adapter. The brief's illustrative code used
    # ``id: int``; we use ``str`` because the production adapter emits
    # ``str(ULID())`` and the tests use the same shape.
    id: str = Field(primary_key=True)
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        sa_column_kwargs={"name": "metadata"},
        sa_type=JSON,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
    )


_DEFAULT_DB_PATH = Path("tasks_metadata.sqlite")

# Module-level singleton engine. Lazy-initialized on first ``get_engine()``
# call; tests inject a per-test engine via ``set_engine``. The default is
# an in-memory SQLite engine so dev/test never accidentally writes to the
# production on-disk sidecar.
_engine: Engine | None = None


def get_engine() -> Engine:
    """Return the module-level metadata engine, creating one if needed.

    First-call default is an in-memory SQLite engine. Production callers
    that want persistence should call ``set_engine(create_metadata_engine(db_path))``
    at process start; tests should reset to in-memory between cases via
    ``set_engine(None)`` followed by ``get_engine()`` (or pass their own).
    """
    global _engine
    if _engine is None:
        _engine = create_metadata_engine()
    return _engine


def set_engine(engine: Engine | None) -> None:
    """Replace the module-level engine.

    Pass ``None`` to reset to the in-memory default on the next
    ``get_engine()`` call. Tests call this between cases so a previous
    test's SQLite file or in-memory state does not leak.
    """
    global _engine
    _engine = engine


def create_metadata_engine(db_path: str | Path | None = None) -> Engine:
    """Create (or open) the SQLite engine for the metadata sidecar.

    Pass ``db_path=None`` for an in-memory engine (used by tests).
    Pass ``db_path=":memory:"`` for the same effect via SQLAlchemy URL.
    """
    if db_path is None or str(db_path) == ":memory:":
        url = "sqlite:///:memory:"
    else:
        url = f"sqlite:///{Path(db_path)}"
    return create_engine(url, echo=False)


def ensure_metadata_schema(engine: Engine) -> None:
    """Idempotent schema bootstrap.

    Creates the ``reflections`` sidecar table (and any future
    ``SQLModel.metadata``-registered tables) if absent. Safe to call on
    every process start; matches the brief's migration option (a)
    (``create_all`` for dev/test) — option (c) (idempotent
    ``ALTER TABLE``) is unnecessary here because the sidecar schema
    starts empty.
    """
    SQLModel.metadata.create_all(engine)


def persist_task_metadata(
    engine: Engine,
    reflection_id: str,
    metadata: dict[str, Any],
) -> None:
    """Upsert the metadata JSON blob for a stored reflection.

    If a sidecar row already exists for ``reflection_id``, the metadata
    is replaced and ``updated_at`` is refreshed. Otherwise a new row is
    inserted. Uses ``Session.exec`` with a SQLAlchemy 2.x-style ``select``
    + ``update_or_create`` pattern so the same call shape works against
    SQLite (dev/test) and any future SQLAlchemy-supported backend.
    """
    ensure_metadata_schema(engine)
    with Session(engine) as session:
        existing = session.exec(
            select(ReflectionMetadata).where(ReflectionMetadata.id == reflection_id),
        ).first()
        if existing is None:
            session.add(
                ReflectionMetadata(
                    id=reflection_id,
                    metadata_json=metadata,
                    updated_at=datetime.now(tz=UTC),
                ),
            )
        else:
            existing.metadata_json = metadata
            existing.updated_at = datetime.now(tz=UTC)
            session.add(existing)
        session.commit()


def read_task_metadata(
    engine: Engine,
    reflection_id: str,
) -> dict[str, Any] | None:
    """Return the metadata JSON blob for ``reflection_id`` or ``None``."""
    ensure_metadata_schema(engine)
    with Session(engine) as session:
        row = session.exec(
            select(ReflectionMetadata).where(ReflectionMetadata.id == reflection_id),
        ).first()
        return dict(row.metadata_json) if row and row.metadata_json else None


def find_tasks_by_metadata(
    engine: Engine,
    metadata_filter: dict[str, Any],
    limit: int = 100,
) -> list[str]:
    """Return reflection_ids whose metadata JSON contains every filter pair.

    Uses a Python-side filter for portability — works against SQLite
    (dev/test) without depending on JSON1 extensions. Each candidate
    row's ``metadata_json`` dict is checked with ``all(md.get(k) == v)``
    so partial overlap returns nothing (matches the spec's "contains all
    key/value pairs" semantics).
    """
    ensure_metadata_schema(engine)
    with Session(engine) as session:
        rows = session.exec(select(ReflectionMetadata)).all()
        matching: list[str] = []
        for row in rows:
            md = dict(row.metadata_json) if row.metadata_json else {}
            if all(md.get(k) == v for k, v in metadata_filter.items()):
                matching.append(row.id)
                if len(matching) >= limit:
                    break
        return matching


__all__ = [
    "ReflectionMetadata",
    "create_metadata_engine",
    "ensure_metadata_schema",
    "find_tasks_by_metadata",
    "get_engine",
    "persist_task_metadata",
    "read_task_metadata",
    "set_engine",
]
