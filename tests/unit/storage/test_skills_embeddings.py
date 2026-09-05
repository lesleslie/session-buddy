"""Unit tests for session_buddy.storage.skills_embeddings module.

Targets SkillsEmbeddingService lifecycle, cache behavior, batch embedding,
and graceful degradation paths. The utility functions
(pack_embedding/unpack_embedding/cosine_similarity) are also exercised here
with edge cases beyond what tests/test_skills_semantic.py covers.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import numpy as np
import pytest

from session_buddy.storage.skills_embeddings import (
    EMBEDDING_BYTES,
    EMBEDDING_DIM,
    SkillsEmbeddingService,
    cosine_similarity,
    get_embedding_service,
    pack_embedding,
    unpack_embedding,
)


# ============================================================================
# Constant sanity
# ============================================================================


class TestModuleConstants:
    """Constants must match the documented MiniLM model spec."""

    def test_embedding_dim_is_384(self) -> None:
        # all-MiniLM-L6-v2 produces 384-dim vectors
        assert EMBEDDING_DIM == 384

    def test_embedding_bytes_is_dim_times_4(self) -> None:
        # float32 = 4 bytes
        assert EMBEDDING_BYTES == 384 * 4 == 1536


# ============================================================================
# pack_embedding / unpack_embedding — focused edge cases
# ============================================================================


class TestPackEmbeddingEdges:
    """pack_embedding validation paths not covered elsewhere."""

    def test_unsupported_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Unsupported embedding type"):
            pack_embedding("not a list")  # type: ignore[arg-type]

    def test_wrong_shape_2d_raises(self) -> None:
        too_many = np.zeros((2, 384), dtype=np.float32)
        with pytest.raises(ValueError, match="Expected 384-dim"):
            pack_embedding(too_many)

    def test_list_input_accepted(self) -> None:
        emb = [0.0] * EMBEDDING_DIM
        packed = pack_embedding(emb)
        assert len(packed) == EMBEDDING_BYTES

    def test_ndarray_input_accepted(self) -> None:
        emb = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        packed = pack_embedding(emb)
        assert len(packed) == EMBEDDING_BYTES

    def test_float64_ndarray_is_downcast(self) -> None:
        """float64 input is coerced to float32 by astype."""
        emb = np.ones(EMBEDDING_DIM, dtype=np.float64)
        packed = pack_embedding(emb)
        # Bytes length matches float32 size regardless of input dtype
        assert len(packed) == EMBEDDING_BYTES
        # And roundtrip yields float32
        unpacked = unpack_embedding(packed)
        assert unpacked.dtype == np.float32


class TestUnpackEmbeddingEdges:
    """unpack_embedding validation paths."""

    def test_correct_size_unpacks_to_1d_float32(self) -> None:
        packed = pack_embedding(np.arange(EMBEDDING_DIM, dtype=np.float32))
        out = unpack_embedding(packed)
        assert out.shape == (EMBEDDING_DIM,)
        assert out.dtype == np.float32

    def test_zero_length_blob_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected 1536 bytes"):
            unpack_embedding(b"")


# ============================================================================
# cosine_similarity — edge cases
# ============================================================================


class TestCosineSimilarityEdges:
    """Edge cases for cosine_similarity: zero norms, mixed types."""

    def test_zero_vector_returns_zero(self) -> None:
        zero = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        nonzero = np.ones(EMBEDDING_DIM, dtype=np.float32)
        assert cosine_similarity(zero, nonzero) == 0.0
        assert cosine_similarity(nonzero, zero) == 0.0

    def test_both_zero_vectors_returns_zero(self) -> None:
        zero = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        assert cosine_similarity(zero, zero) == 0.0

    def test_list_inputs_accepted(self) -> None:
        vec = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
        other = [0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2)
        sim = cosine_similarity(vec, other)
        assert sim == pytest.approx(0.0, abs=1e-6)


# ============================================================================
# SkillsEmbeddingService — lifecycle
# ============================================================================


class TestSkillsEmbeddingServiceLifecycle:
    """init/initialize/generate_embedding/shutdown contract."""

    def test_init_sets_defaults(self) -> None:
        svc = SkillsEmbeddingService()
        assert svc.cache_enabled is True
        assert svc.batch_size == 8
        assert svc._initialized is False
        assert isinstance(svc._lru_cache, dict)
        # Executor is created; shutdown it so pytest doesn't leak threads.
        svc.executor.shutdown(wait=True)

    def test_init_respects_constructor_kwargs(self) -> None:
        svc = SkillsEmbeddingService(cache_enabled=False, batch_size=16)
        try:
            assert svc.cache_enabled is False
            assert svc.batch_size == 16
        finally:
            svc.executor.shutdown(wait=True)

    def test_initialize_is_idempotent(self) -> None:
        svc = SkillsEmbeddingService()
        try:
            first = svc.initialize()
            second = svc.initialize()
            # initialize() must not error on the second call.
            assert second == first
        finally:
            svc.executor.shutdown(wait=True)

    def test_shutdown_clears_cache_and_resets_initialized(self) -> None:
        svc = SkillsEmbeddingService()
        svc._lru_cache["x"] = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        svc._initialized = True
        svc.shutdown()
        assert svc._initialized is False
        assert svc._lru_cache == {}


# ============================================================================
# generate_embedding — graceful-degradation paths
# ============================================================================


class TestGenerateEmbeddingPaths:
    """generate_embedding branches: not initialized, empty text, embedding unavailable."""

    def test_empty_text_returns_none(self) -> None:
        svc = SkillsEmbeddingService()
        # Even uninitialized, empty text short-circuits to None after init
        svc._initialized = True
        try:
            assert svc.generate_embedding("") is None
            assert svc.generate_embedding("   ") is None
        finally:
            svc.executor.shutdown(wait=True)

    def test_generate_embedding_uninitialized_returns_none_when_init_fails(self) -> None:
        svc = SkillsEmbeddingService()
        # Force initialize() to return False to exercise the "not available" path.
        with patch.object(svc, "initialize", return_value=False):
            assert svc.generate_embedding("anything") is None
        svc.executor.shutdown(wait=True)

    def test_generate_embedding_exception_returns_none(self) -> None:
        """If the underlying provider throws, generate_embedding returns None."""
        svc = SkillsEmbeddingService()
        svc._initialized = True
        try:
            with patch.object(
                svc,
                "_generate_embedding_impl",
                side_effect=RuntimeError("boom"),
            ):
                assert svc.generate_embedding("text") is None
        finally:
            svc.executor.shutdown(wait=True)

    def test_generate_embedding_uses_cache(self) -> None:
        """use_cache=True returns the same cached ndarray on repeat calls."""
        svc = SkillsEmbeddingService()
        svc._initialized = True
        sentinel = np.full(EMBEDDING_DIM, 0.5, dtype=np.float32)
        try:
            with patch.object(
                svc, "_generate_embedding_impl", return_value=sentinel
            ) as mock_impl:
                first = svc.generate_embedding("hello", use_cache=True)
                second = svc.generate_embedding("hello", use_cache=True)
            assert first is sentinel
            assert second is sentinel
            # Cached path: only one underlying call
            assert mock_impl.call_count == 1
        finally:
            svc.executor.shutdown(wait=True)

    def test_generate_embedding_bypasses_cache_when_disabled(self) -> None:
        svc = SkillsEmbeddingService(cache_enabled=False)
        svc._initialized = True
        sentinel = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        try:
            with patch.object(
                svc, "_generate_embedding_impl", return_value=sentinel
            ) as mock_impl:
                svc.generate_embedding("hello", use_cache=True)  # cache_enabled=False
                svc.generate_embedding("hello", use_cache=True)
            assert mock_impl.call_count == 2
        finally:
            svc.executor.shutdown(wait=True)

    def test_generate_embedding_use_cache_false(self) -> None:
        """use_cache=False forces a fresh impl call even with cache enabled."""
        svc = SkillsEmbeddingService(cache_enabled=True)
        svc._initialized = True
        sentinel = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        try:
            with patch.object(
                svc, "_generate_embedding_impl", return_value=sentinel
            ) as mock_impl:
                svc.generate_embedding("hello", use_cache=False)
                svc.generate_embedding("hello", use_cache=False)
            assert mock_impl.call_count == 2
        finally:
            svc.executor.shutdown(wait=True)

    def test_lru_cache_evicts_when_full(self) -> None:
        """Cache size cap is 1024; the oldest entry is dropped on overflow."""
        svc = SkillsEmbeddingService()
        svc._initialized = True
        sentinel = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        try:
            with patch.object(
                svc, "_generate_embedding_impl", return_value=sentinel
            ):
                # Pre-fill cache to exactly 1024 entries
                for i in range(1024):
                    svc._generate_embedding_cached(f"key-{i}")
                # First entry should still be present
                assert "key-0" in svc._lru_cache
                # One more forces eviction of oldest (FIFO order via OrderedDict.popitem(last=False))
                svc._generate_embedding_cached("key-1024")
                assert "key-0" not in svc._lru_cache
                assert "key-1024" in svc._lru_cache
        finally:
            svc.executor.shutdown(wait=True)

    def test_clear_cache_empties_dict(self) -> None:
        svc = SkillsEmbeddingService()
        svc._lru_cache["x"] = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        svc.clear_cache()
        assert svc._lru_cache == {}

    def test_clear_cache_is_noop_when_disabled(self) -> None:
        svc = SkillsEmbeddingService(cache_enabled=False)
        svc._lru_cache["x"] = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        svc.clear_cache()
        # With cache_enabled=False the clear body is skipped, dict unchanged
        assert "x" in svc._lru_cache


# ============================================================================
# generate_batch
# ============================================================================


class TestGenerateBatch:
    """generate_batch returns a list aligned with the input texts."""

    def test_empty_input_returns_empty_list(self) -> None:
        svc = SkillsEmbeddingService()
        try:
            assert svc.generate_batch([]) == []
        finally:
            svc.executor.shutdown(wait=True)

    def test_batch_with_all_success(self) -> None:
        svc = SkillsEmbeddingService()
        svc._initialized = True
        sentinel = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        try:
            with patch.object(svc, "generate_embedding", return_value=sentinel):
                out = svc.generate_batch(["a", "b", "c"])
            assert len(out) == 3
            assert all(v is sentinel for v in out)
        finally:
            svc.executor.shutdown(wait=True)

    def test_batch_with_some_failures(self) -> None:
        """generate_embedding can return None; batch preserves None entries."""
        svc = SkillsEmbeddingService()
        svc._initialized = True
        sentinel = np.zeros(EMBEDDING_DIM, dtype=np.float32)

        def fake_generate(text: str, use_cache: bool = True):
            return sentinel if text != "bad" else None

        try:
            with patch.object(svc, "generate_embedding", side_effect=fake_generate):
                out = svc.generate_batch(["good", "bad", "good2"])
            assert len(out) == 3
            assert out[0] is sentinel
            assert out[1] is None
            assert out[2] is sentinel
        finally:
            svc.executor.shutdown(wait=True)


# ============================================================================
# _generate_embedding_impl — asyncio.run bridge
# ============================================================================


class TestGenerateEmbeddingImpl:
    """_generate_embedding_impl bridges sync→async via asyncio.run."""

    def test_returns_numpy_array_when_provider_returns_list(self) -> None:
        svc = SkillsEmbeddingService()
        try:
            fake_vec = [0.1] * EMBEDDING_DIM

            async def fake_async(text: str) -> list[float]:
                return fake_vec

            with patch(
                "session_buddy.storage.skills_embeddings.generate_reflection_embedding",
                fake_async,
            ):
                out = svc._generate_embedding_impl("hi")
            assert isinstance(out, np.ndarray)
            assert out.shape == (EMBEDDING_DIM,)
            assert out.dtype == np.float32
        finally:
            svc.executor.shutdown(wait=True)

    def test_returns_none_when_provider_returns_none(self) -> None:
        svc = SkillsEmbeddingService()
        try:
            async def fake_async(text: str) -> None:
                return None

            with patch(
                "session_buddy.storage.skills_embeddings.generate_reflection_embedding",
                fake_async,
            ):
                assert svc._generate_embedding_impl("hi") is None
        finally:
            svc.executor.shutdown(wait=True)

    def test_returns_none_when_provider_raises(self) -> None:
        svc = SkillsEmbeddingService()
        try:
            async def fake_async(text: str) -> None:
                raise RuntimeError("boom")

            with patch(
                "session_buddy.storage.skills_embeddings.generate_reflection_embedding",
                fake_async,
            ):
                assert svc._generate_embedding_impl("hi") is None
        finally:
            svc.executor.shutdown(wait=True)


# ============================================================================
# Module-level get_embedding_service singleton
# ============================================================================


class TestGlobalServiceSingleton:
    """get_embedding_service returns a stable shared instance."""

    def test_returns_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import session_buddy.storage.skills_embeddings as mod

        monkeypatch.setattr(mod, "_global_service", None)
        a = get_embedding_service()
        b = get_embedding_service()
        assert a is b
        # Clean up the executor before pytest leaks it.
        a.executor.shutdown(wait=True)
        monkeypatch.setattr(mod, "_global_service", None)
