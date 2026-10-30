"""Canonical embedding dimension for the memory subsystem.

Single source of truth for the DuckDB fixed-size ARRAY width shared by the
``embedding`` columns and the ``array_cosine_similarity`` casts.

The dimension MUST match the vector length returned by the configured
embedding provider. A mismatch is a loud failure rather than a silent
one: binding a wrong-length vector into a fixed-size ARRAY raises a
clean ``ConversionException`` ("Cannot cast list with length 1536 to
array with length 4096") and leaves the instance healthy -- the next
``CHECKPOINT`` still succeeds.

That correction matters, because the failure was previously attributed
to the wrong cause. The fatal ``"Operation requires a flat or constant
vector but a non-flat/non-constant vector was encountered"`` comes from
the HNSW index rebuild over rows replayed from a WAL sidecar -- a
DuckDB 2.0.0 regression in the ``vss`` extension, not from the width
mismatch. See ``session_buddy/memory/duckdb_open.py`` for that recovery.
The width still has to match, but because the column is a fixed-size
ARRAY, not because a mismatch corrupts the instance.

Historically this was 384 (all-MiniLM-L6-v2), then 4096 (the llama-server's
Qwen3-8B). It is now **768**, the width both current providers serve:
OpenAI's ``text-embedding-3-small`` (shortened via its ``dimensions``
parameter) and Google's EmbeddingGemma-300M (native).
"""

from __future__ import annotations

import logging
import re
from typing import Any

# Width of the DuckDB ``FLOAT[N]`` embedding columns. Match this to the
# embedding provider's output width. The provider chain in
# ``session_buddy/reflection/embeddings.py`` only admits a leg whose width
# matches this, so changing the constant switches providers as well as
# schema -- see ``docs/plans/2026-10-29-openai-embedding-provider-chain.md``.
DEFAULT_EMBEDDING_DIM = 768

logger = logging.getLogger(__name__)


def coerce_embedding(
    embedding: list[float] | None,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
) -> list[float] | None:
    """Return ``embedding`` only when its width matches ``embedding_dim``.

    A wrong-width vector cannot be bound into a ``FLOAT[N]`` column: DuckDB
    raises a ``ConversionException`` and the write fails. Dropping the
    vector here degrades the row to "no embedding" instead -- the row is
    still stored, and the instance stays healthy.

    This is the authoritative width gate for the provider chain, so it
    catches a provider that returns a vector of the wrong width even when
    that provider declared the right one.

    Args:
        embedding: Candidate vector, or ``None``.
        embedding_dim: Expected width.

    Returns:
        The vector unchanged when it matches, otherwise ``None``.
    """
    if embedding is None:
        return None
    if len(embedding) != embedding_dim:
        logger.warning(
            "Embedding width mismatch: got %d dims, expected %d — storing "
            "without a vector. Update the embedding model or embedding_dim "
            "to match.",
            len(embedding),
            embedding_dim,
        )
        return None
    return embedding


def read_live_embedding_width(
    conn: Any,
    table_name: str,
    column_name: str = "embedding",
) -> int | None:
    """Return the ``FLOAT[N]`` width of a live embedding column, or ``None``.

    A DuckDB embedding column is a fixed-size ARRAY, and DuckDB cannot
    widen one in place. A database created while the canonical width was
    some other value therefore keeps that width forever, and binding a
    canonical-width vector into it raises a ``ConversionException``.

    The live schema is the authority on what fits, so a caller that writes
    vectors reads the width from the column it is about to write to.

    Args:
        conn: An open DuckDB connection.
        table_name: The table holding the embedding column.
        column_name: The embedding column's name.

    Returns:
        The width, or ``None`` when the column does not exist, its type is
        not a fixed-size ``FLOAT[N]``, or the catalog cannot be read.
    """
    try:
        row = conn.execute(
            "SELECT data_type FROM duckdb_columns() "
            "WHERE database_name = current_database() "
            "AND table_name = ? "
            "AND column_name = ?",
            [table_name, column_name],
        ).fetchone()
    except Exception:
        logger.debug("Could not read the live embedding width", exc_info=True)
        return None
    if not row:
        return None
    match = re.fullmatch(r"FLOAT\[(\d+)\]", str(row[0]))
    if match is None:
        return None
    return int(match.group(1))


__all__ = [
    "DEFAULT_EMBEDDING_DIM",
    "coerce_embedding",
    "read_live_embedding_width",
]
