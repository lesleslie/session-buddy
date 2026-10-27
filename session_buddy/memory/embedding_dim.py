"""Canonical embedding dimension for the memory subsystem.

Single source of truth for the DuckDB fixed-size ARRAY width shared by the
``embedding`` columns and the ``array_cosine_similarity`` casts.

The dimension MUST match the vector length returned by the configured
embedding provider. A mismatch is not a harmless type error: binding a
wrong-length vector into a fixed-size ARRAY can leave the column's child
vector in dictionary form, which later fails DuckDB's checkpoint with
``"Operation requires a flat or constant vector but a non-flat/non-constant
vector was encountered"``. That is a *fatal* error — it invalidates the
entire DuckDB instance and is persisted in the WAL, so every subsequent
process replays the poison at startup and the database is unusable until
the WAL is discarded.

Historically this was 384 (all-MiniLM-L6-v2). The llama-server now serves
Qwen3-8B, whose ``/v1/embeddings`` endpoint returns 4096-dim vectors.
"""

from __future__ import annotations

import logging

# Width of the DuckDB ``FLOAT[N]`` embedding columns. Match this to the
# embedding provider's output width (see settings: embedding_model).
DEFAULT_EMBEDDING_DIM = 4096

logger = logging.getLogger(__name__)


def coerce_embedding(
    embedding: list[float] | None,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
) -> list[float] | None:
    """Return ``embedding`` only when its width matches ``embedding_dim``.

    A wrong-width vector must never be bound into a ``FLOAT[N]`` column: it
    corrupts the column's child vector, which later fails DuckDB's checkpoint
    fatally and invalidates the whole database instance (persisted in the
    WAL, so the damage outlives the process). Dropping the vector instead
    degrades the row to "no embedding" and keeps the database usable.

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


__all__ = ["DEFAULT_EMBEDDING_DIM", "coerce_embedding"]
