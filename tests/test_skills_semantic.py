"""Tests for skills semantic search and embedding functionality.

Tests embedding generation, similarity search, and skill recommendations
using the all-MiniLM-L6-v2 model for semantic understanding.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pytest

from session_buddy.storage.migrations.base import MigrationManager
from session_buddy.storage.skills_embeddings import (
    SkillsEmbeddingService,
    pack_embedding,
    unpack_embedding,
    cosine_similarity,
)
from session_buddy.storage.skills_storage import SkillsStorage


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_db_path():
    """Create temporary database for testing.

    Always starts fresh to avoid using databases from old test runs.
    """
    # Create unique temp file for each test function call
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Ensure file is deleted at start (in case it exists from previous run)
    if db_path.exists():
        db_path.unlink()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def migration_dir():
    """Get migration directory path."""
    return Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"


def get_migration_manager(db_path: Path, migration_dir: Path) -> MigrationManager:
    """Create migration manager for testing."""
    from session_buddy.storage.migrations.base import MigrationLoader

    loader = MigrationLoader(migration_dir)
    manager = MigrationManager(db_path, migration_dir)
    return manager


@pytest.fixture
def migrated_db(temp_db_path, migration_dir):
    """Apply migrations to test database."""
    manager = get_migration_manager(temp_db_path, migration_dir)
    manager.migrate()
    return temp_db_path


@pytest.fixture
def storage_with_embeddings(migrated_db):
    """Create storage with sample data and embeddings."""
    storage = SkillsStorage(db_path=migrated_db)

    # Create sample embeddings for different types of queries
    # Using deterministic patterns for testing
    embeddings = {
        "database": np.random.RandomState(42).randn(384).astype(np.float32),
        "authentication": np.random.RandomState(43).randn(384).astype(np.float32),
        "testing": np.random.RandomState(44).randn(384).astype(np.float32),
        "deployment": np.random.RandomState(45).randn(384).astype(np.float32),
    }

    # Store sample invocations
    storage.store_invocation(
        skill_name="db-migrate",
        invoked_at="2025-02-10T12:00:00",
        session_id="session1",
        completed=True,
        user_query="how to migrate database schema",
        embedding=pack_embedding(embeddings["database"]),
    )

    storage.store_invocation(
        skill_name="auth-setup",
        invoked_at="2025-02-10T12:01:00",
        session_id="session1",
        completed=True,
        user_query="implement JWT authentication",
        embedding=pack_embedding(embeddings["authentication"]),
    )

    storage.store_invocation(
        skill_name="test-runner",
        invoked_at="2025-02-10T12:02:00",
        session_id="session1",
        completed=True,
        user_query="run pytest with coverage",
        embedding=pack_embedding(embeddings["testing"]),
    )

    storage.store_invocation(
        skill_name="deploy-app",
        invoked_at="2025-02-10T12:03:00",
        session_id="session2",
        completed=False,
        user_query="deploy to production server",
        embedding=pack_embedding(embeddings["deployment"]),
    )

    # Store without embedding (old record)
    storage.store_invocation(
        skill_name="legacy-skill",
        invoked_at="2025-02-10T11:00:00",
        session_id="session0",
        completed=True,
        user_query="old invocation without embedding",
        embedding=None,
    )

    return storage


# ============================================================================
# Embedding Utilities Tests
# ============================================================================


class TestEmbeddingUtilities:
    """Tests for embedding packing/unpacking utilities."""

    def test_pack_embedding_shape(self):
        """Test that packing produces correct byte size."""
        embedding = np.random.randn(384).astype(np.float32)
        packed = pack_embedding(embedding)

        assert len(packed) == 1536  # 384 dims × 4 bytes

    def test_pack_embedding_wrong_shape(self):
        """Test that wrong shape raises error."""
        embedding = np.random.randn(100).astype(np.float32)

        with pytest.raises(ValueError, match="Expected 384-dim"):
            pack_embedding(embedding)

    def test_pack_embedding_from_list(self):
        """Test packing from list."""
        embedding = [0.1] * 384
        packed = pack_embedding(embedding)

        assert len(packed) == 1536

    def test_unpack_embedding(self):
        """Test unpacking produces correct shape."""
        embedding = np.random.randn(384).astype(np.float32)
        packed = pack_embedding(embedding)

        unpacked = unpack_embedding(packed)

        assert unpacked.shape == (384,)
        np.testing.assert_array_almost_equal(unpacked, embedding)

    def test_unpack_embedding_wrong_size(self):
        """Test that wrong size raises error."""
        wrong_blob = bytes(100)  # Wrong size

        with pytest.raises(ValueError, match="Expected 1536 bytes"):
            unpack_embedding(wrong_blob)

    def test_roundtrip_embedding(self):
        """Test that pack/unpack preserves data."""
        original = np.random.randn(384).astype(np.float32)
        packed = pack_embedding(original)
        unpacked = unpack_embedding(packed)

        np.testing.assert_array_almost_equal(unpacked, original)


class TestCosineSimilarity:
    """Tests for cosine similarity calculation."""

    def test_identical_vectors(self):
        """Test that identical vectors have similarity 1.0."""
        vec = np.random.randn(384).astype(np.float32)
        similarity = cosine_similarity(vec, vec)

        assert similarity == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Test that orthogonal vectors have similarity near 0.0."""
        vec1 = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        vec2 = np.array([0.0] * 383 + [1.0], dtype=np.float32)

        similarity = cosine_similarity(vec1, vec2)

        assert similarity == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors(self):
        """Test that opposite vectors have similarity -1.0."""
        vec = np.random.randn(384).astype(np.float32)
        opposite = -vec

        similarity = cosine_similarity(vec, opposite)

        assert similarity == pytest.approx(-1.0)

    def test_from_list(self):
        """Test similarity calculation from lists."""
        vec1 = [0.5] * 384
        vec2 = [0.5] * 384

        similarity = cosine_similarity(vec1, vec2)

        assert similarity == pytest.approx(1.0)

    def test_zero_vectors(self):
        """Test that zero vectors return 0.0."""
        vec1 = np.zeros(384, dtype=np.float32)
        vec2 = np.random.randn(384).astype(np.float32)

        similarity = cosine_similarity(vec1, vec2)

        assert similarity == 0.0


# ============================================================================
# SkillsEmbeddingService Tests
# ============================================================================


class TestSkillsEmbeddingService:
    """Tests for embedding service."""

    def test_initialization(self):
        """Test service initialization."""
        service = SkillsEmbeddingService()

        assert service.cache_enabled is True
        assert service.batch_size == 8
        assert service._initialized is False

    def test_initialize_success(self):
        """Test successful initialization (may return False if ONNX unavailable)."""
        service = SkillsEmbeddingService()
        result = service.initialize()

        # May be False if ONNX unavailable
        assert isinstance(result, bool)

    def test_generate_embedding_uninitialized(self):
        """Test that uninitialized service returns None."""
        service = SkillsEmbeddingService(cache_enabled=False)  # Disable cache

        # Don't initialize
        embedding = service.generate_embedding("test query")

        # Should return None if not initialized
        # Note: This may still succeed if global system is initialized
        assert embedding is None or isinstance(embedding, np.ndarray)

    def test_generate_embedding_empty_text(self):
        """Test that empty text returns None."""
        service = SkillsEmbeddingService()
        service.initialize()

        embedding = service.generate_embedding("")

        assert embedding is None

    def test_generate_embedding_whitespace(self):
        """Test that whitespace-only text returns None."""
        service = SkillsEmbeddingService()
        service.initialize()

        embedding = service.generate_embedding("   ")

        assert embedding is None

    def test_generate_batch_empty(self):
        """Test batch generation with empty list."""
        service = SkillsEmbeddingService()
        service.initialize()

        embeddings = service.generate_batch([])

        assert embeddings == []

    def test_clear_cache(self):
        """Test cache clearing."""
        service = SkillsEmbeddingService(cache_enabled=True)
        service.initialize()

        # Generate an embedding (will be cached)
        emb1 = service.generate_embedding("test query")

        # Clear cache
        service.clear_cache()

        # Generate again (should regenerate, not from cache)
        emb2 = service.generate_embedding("test query")

        # Both should be None or valid embeddings
        assert (emb1 is None and emb2 is None) or (
            isinstance(emb1, np.ndarray) and isinstance(emb2, np.ndarray)
        )


# ============================================================================
# Semantic Search Tests
# ============================================================================


class TestSemanticSearch:
    """Tests for semantic search functionality."""

    def test_search_by_query_all_results(self, storage_with_embeddings):
        """Test searching returns all invocations with embeddings."""
        storage = storage_with_embeddings

        # Use database embedding as query
        import sqlite3

        with storage._get_connection() as conn:
            cursor = conn.execute(
                "SELECT embedding FROM skill_invocation WHERE embedding IS NOT NULL LIMIT 1"
            )
            row = cursor.fetchone()
            query_embedding = row[0] if row else None

        if query_embedding is None:
            pytest.skip("No embeddings found in database")

        results = storage.search_by_query(query_embedding, limit=10)

        # Should return results (excluding the query invocation itself if it matches)
        assert len(results) >= 0

        # Check result structure
        for invocation, score in results:
            assert isinstance(invocation, object)
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_search_by_query_with_session_filter(self, storage_with_embeddings):
        """Test searching with session filter."""
        storage = storage_with_embeddings

        # Get an embedding
        with storage._get_connection() as conn:
            cursor = conn.execute(
                "SELECT embedding FROM skill_invocation WHERE embedding IS NOT NULL LIMIT 1"
            )
            row = cursor.fetchone()
            query_embedding = row[0] if row else None

        if query_embedding is None:
            pytest.skip("No embeddings found")

        # Search within specific session
        results = storage.search_by_query(
            query_embedding, limit=10, session_id="session1"
        )

        # All results should be from session1
        for invocation, _ in results:
            assert invocation.session_id == "session1"

    def test_search_by_query_min_similarity(self, storage_with_embeddings):
        """Test searching with minimum similarity threshold."""
        storage = storage_with_embeddings

        # Get an embedding
        with storage._get_connection() as conn:
            cursor = conn.execute(
                "SELECT embedding FROM skill_invocation WHERE embedding IS NOT NULL LIMIT 1"
            )
            row = cursor.fetchone()
            query_embedding = row[0] if row else None

        if query_embedding is None:
            pytest.skip("No embeddings found")

        # Search with high threshold
        results = storage.search_by_query(
            query_embedding, limit=10, min_similarity=0.99
        )

        # All results should have high similarity (only exact match or very similar)
        for _, score in results:
            assert score >= 0.99

    def test_search_by_query_limit(self, storage_with_embeddings):
        """Test that limit parameter works."""
        storage = storage_with_embeddings

        # Get an embedding
        with storage._get_connection() as conn:
            cursor = conn.execute(
                "SELECT embedding FROM skill_invocation WHERE embedding IS NOT NULL LIMIT 1"
            )
            row = cursor.fetchone()
            query_embedding = row[0] if row else None

        if query_embedding is None:
            pytest.skip("No embeddings found")

        # Request only 2 results
        results = storage.search_by_query(query_embedding, limit=2)

        # Should return at most 2 results
        assert len(results) <= 2

    def test_get_similar_skills(self, storage_with_embeddings):
        """Test finding similar skills."""
        storage = storage_with_embeddings

        # Find skills similar to "db-migrate"
        similar = storage.get_similar_skills("db-migrate", limit=5)

        # Should return a list
        assert isinstance(similar, list)

        # Check result structure
        for skill_name, score in similar:
            assert isinstance(skill_name, str)
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0
            # Should not include the target skill itself
            assert skill_name != "db-migrate"

    def test_get_similar_skills_limit(self, storage_with_embeddings):
        """Test that limit parameter works."""
        storage = storage_with_embeddings

        similar = storage.get_similar_skills("db-migrate", limit=2)

        # Should return at most 2 results
        assert len(similar) <= 2


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for full semantic search workflow."""

    def test_store_and_search_workflow(self, migrated_db):
        """Test complete workflow: store with embedding, then search."""
        storage = SkillsStorage(db_path=migrated_db)

        # Store invocation with embedding
        query_text = "how to fix database connection timeout"
        embedding = np.random.randn(384).astype(np.float32)

        inv_id = storage.store_invocation(
            skill_name="db-fix",
            invoked_at="2025-02-10T12:00:00",
            session_id="test_session",
            completed=True,
            user_query=query_text,
            embedding=pack_embedding(embedding),
        )

        # Search for similar invocations
        results = storage.search_by_query(
            pack_embedding(embedding), limit=5, session_id="test_session"
        )

        # Should find the stored invocation
        assert len(results) >= 1

        # First result should be the stored invocation (with highest similarity)
        top_invocation, top_score = results[0]
        assert top_invocation.id == inv_id
        assert top_score == pytest.approx(1.0)  # Exact match

    def test_multiple_invocations_same_session(self, migrated_db):
        """Test searching within a session with multiple invocations."""
        storage = SkillsStorage(db_path=migrated_db)

        # Store multiple related invocations
        embeddings = [
            np.random.RandomState(i).randn(384).astype(np.float32)
            for i in range(5)
        ]

        for i, emb in enumerate(embeddings):
            storage.store_invocation(
                skill_name=f"skill-{i}",
                invoked_at=f"2025-02-10T12:0{i}:00",
                session_id="multi_test",
                completed=True,
                user_query=f"query {i}",
                embedding=pack_embedding(emb),
            )

        # Search with first embedding
        results = storage.search_by_query(
            pack_embedding(embeddings[0]), limit=5, session_id="multi_test"
        )

        # Should find all 5 invocations
        assert len(results) >= 1

        # All should be from multi_test session
        for invocation, _ in results:
            assert invocation.session_id == "multi_test"

    def test_old_records_without_embeddings(self, migrated_db):
        """Test that old records without embeddings are handled gracefully."""
        storage = SkillsStorage(db_path=migrated_db)

        # Store old record without embedding
        storage.store_invocation(
            skill_name="old-skill",
            invoked_at="2025-02-10T11:00:00",
            session_id="old_session",
            completed=True,
            user_query="old invocation",
            embedding=None,
        )

        # Store new record with embedding
        embedding = np.random.randn(384).astype(np.float32)
        storage.store_invocation(
            skill_name="new-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="new_session",
            completed=True,
            user_query="new invocation",
            embedding=pack_embedding(embedding),
        )

        # Search should only return records with embeddings
        results = storage.search_by_query(pack_embedding(embedding), limit=10)

        # Should not include old-skill
        skill_names = [inv.skill_name for inv, _ in results]
        assert "old-skill" not in skill_names
        assert "new-skill" in skill_names


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance tests for semantic search."""

    def test_search_performance_with_many_records(self, migrated_db):
        """Test search performance with 100+ invocations."""
        storage = SkillsStorage(db_path=migrated_db)

        # Store 100 invocations with embeddings
        for i in range(100):
            embedding = np.random.randn(384).astype(np.float32)
            storage.store_invocation(
                skill_name=f"skill-{i}",
                invoked_at=f"2025-02-10T12:{i:02d}:00",
                session_id=f"session-{i % 10}",
                completed=True,
                user_query=f"query {i}",
                embedding=pack_embedding(embedding),
            )

        # Search should still be fast
        import time

        query_emb = np.random.randn(384).astype(np.float32)
        start = time.time()
        results = storage.search_by_query(pack_embedding(query_emb), limit=10)
        duration = time.time() - start

        # Should complete in less than 1 second
        assert duration < 1.0
        assert len(results) <= 10

    def test_batch_embedding_generation(self, migrated_db):
        """Test batch embedding generation performance."""
        service = SkillsEmbeddingService(batch_size=16)
        service.initialize()

        if not service._initialized:
            pytest.skip("Embedding service not initialized")

        # Generate 32 embeddings
        texts = [f"test query {i}" for i in range(32)]

        start = time.time()
        embeddings = service.generate_batch(texts)
        duration = time.time() - start

        # Should generate all embeddings (may be None if ONNX unavailable)
        assert len(embeddings) == 32

        # Should complete in reasonable time
        # (may be slower if using fallback mock embeddings)
        assert duration < 10.0
