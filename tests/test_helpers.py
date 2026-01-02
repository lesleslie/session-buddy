"""Test helpers for session-buddy tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter_oneiric import (
        ReflectionDatabaseAdapterOneiric,
    )


def create_test_reflection_database(
    db_path: str | Path | None = None,
) -> ReflectionDatabaseAdapterOneiric:
    """Create a ReflectionDatabase instance for testing.

    Args:
        db_path: Optional path for the test database. If None, uses a temporary file.

    Returns:
        A ReflectionDatabase instance configured for testing.

    """
    from session_buddy.adapters.reflection_adapter_oneiric import ReflectionDatabase
    from session_buddy.adapters.settings import ReflectionAdapterSettings

    if db_path is None:
        # Create a temporary file for the test database
        temp_file = Path(tempfile.mktemp(suffix=".duckdb"))
        db_path = temp_file

    # Create settings with test configuration
    settings = ReflectionAdapterSettings(
        database_path=Path(db_path),
        collection_name="test",
        embedding_dim=384,
        distance_metric="cosine",
        enable_vss=False,  # Disable vector similarity search for tests
        threads=1,
        memory_limit="512MB",
        enable_embeddings=False,  # Disable embeddings for faster tests
    )

    return ReflectionDatabase(settings=settings)


def create_test_reflection_database_with_path(db_path: str | Path):
    """Create a ReflectionDatabase instance for testing with a specific path.

    Args:
        db_path: Path for the test database.

    Returns:
        A ReflectionDatabase instance configured for testing.

    """
    from session_buddy.adapters.reflection_adapter_oneiric import ReflectionDatabase
    from session_buddy.adapters.settings import ReflectionAdapterSettings

    # Create settings with test configuration
    settings = ReflectionAdapterSettings(
        database_path=Path(db_path),
        collection_name="test",
        embedding_dim=384,
        distance_metric="cosine",
        enable_vss=False,  # Disable vector similarity search for tests
        threads=1,
        memory_limit="512MB",
        enable_embeddings=False,  # Disable embeddings for faster tests
    )

    return ReflectionDatabase(settings=settings)
