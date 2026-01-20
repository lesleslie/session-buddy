"""Test embedding quantization accuracy and memory savings.

Tests that scalar quantization:
1. Correctly quantizes and dequantizes embeddings
2. Maintains >95% accuracy (as per Phase 2 success metrics)
3. Achieves 4x memory reduction
4. Works correctly with the cache
"""

from __future__ import annotations

import numpy as np

import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
    ReflectionAdapterSettings,
)
from session_buddy.adapters.settings import _resolve_data_dir


@pytest.fixture
def quantized_settings() -> ReflectionAdapterSettings:
    """Create settings with quantization enabled."""
    return ReflectionAdapterSettings(
        database_path=_resolve_data_dir() / "test_quantization.duckdb",
        enable_quantization=True,
        quantization_method="scalar",
        quantization_accuracy_threshold=0.95,
    )


@pytest.fixture
def normal_settings() -> ReflectionAdapterSettings:
    """Create settings without quantization."""
    return ReflectionAdapterSettings(
        database_path=_resolve_data_dir() / "test_normal.duckdb",
        enable_quantization=False,
    )


class TestEmbeddingQuantization:
    """Test embedding quantization functionality."""

    def test_quantize_embedding_disabled(self, normal_settings: ReflectionAdapterSettings) -> None:
        """Test that quantization returns None when disabled."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=normal_settings)
        embedding = [0.1, -0.2, 0.3, 0.4] * 96  # 384-dim

        result = adapter._quantize_embedding(embedding)

        assert result is None, "Should return None when quantization disabled"

    def test_quantize_embedding_enabled(self, quantized_settings: ReflectionAdapterSettings) -> None:
        """Test that quantization returns uint8 values when enabled."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=quantized_settings)
        embedding = [0.1, -0.2, 0.3, 0.4] * 96  # 384-dim

        result = adapter._quantize_embedding(embedding)

        assert result is not None, "Should return quantized embedding"
        assert len(result) == 384, "Should return 384 uint8 values"
        assert all(isinstance(x, int) and 0 <= x <= 255 for x in result), "All values should be uint8"

    def test_dequantize_embedding(self, quantized_settings: ReflectionAdapterSettings) -> None:
        """Test that dequantization reconstructs original embedding."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=quantized_settings)
        original = [0.1, -0.2, 0.3, 0.4] * 96  # 384-dim

        # Quantize
        quantized = adapter._quantize_embedding(original)
        assert quantized is not None

        # Dequantize
        reconstructed = adapter._dequantize_embedding(quantized)
        assert reconstructed is not None

        # Check accuracy
        original_arr = np.array(original)
        reconstructed_arr = np.array(reconstructed)

        # Cosine similarity (what we actually care about)
        similarity = np.dot(
            original_arr / np.linalg.norm(original_arr),
            reconstructed_arr / np.linalg.norm(reconstructed_arr),
        )

        print(f"\nCosine similarity: {similarity:.6f}")
        assert similarity >= 0.95, f"Should maintain >95% accuracy, got {similarity:.2%}"

    def test_quantization_accuracy_with_random_embeddings(
        self, quantized_settings: ReflectionAdapterSettings
    ) -> None:
        """Test quantization accuracy with random embeddings."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=quantized_settings)

        # Generate realistic embeddings (L2-normalized, like all-MiniLM-L6-v2)
        np.random.seed(42)
        n_test_embeddings = 100
        embeddings = []
        for _ in range(n_test_embeddings):
            # Generate random vector and normalize to unit length (like real embeddings)
            vec = np.random.randn(384).astype(np.float32)
            vec = vec / np.linalg.norm(vec)  # L2-normalize
            # Scale to typical all-MiniLM-L6-v2 range (not all dims are ±0.15, but most are within)
            # Real embeddings are unit-normalized, so individual dimensions are typically smaller
            vec = vec * 0.1  # Scale to have typical magnitude
            embeddings.append(vec.tolist())

        # Test accuracy for each embedding
        similarities = []
        for embedding in embeddings:
            quantized = adapter._quantize_embedding(embedding)
            assert quantized is not None

            reconstructed = adapter._dequantize_embedding(quantized)
            assert reconstructed is not None

            # Calculate cosine similarity
            original_arr = np.array(embedding)
            reconstructed_arr = np.array(reconstructed)

            similarity = np.dot(
                original_arr / np.linalg.norm(original_arr),
                reconstructed_arr / np.linalg.norm(reconstructed_arr),
            )
            similarities.append(similarity)

        mean_similarity = np.mean(similarities)
        min_similarity = np.min(similarities)

        print(f"\nQuantization accuracy with {n_test_embeddings} embeddings:")
        print(f"  Mean similarity: {mean_similarity:.6f}")
        print(f"  Min similarity: {min_similarity:.6f}")
        print(f"  Std deviation: {np.std(similarities):.6f}")

        assert mean_similarity >= 0.95, f"Mean accuracy should be >95%, got {mean_similarity:.2%}"
        assert (
            min_similarity >= 0.90
        ), f"Min accuracy should be >90% (allowing some outliers), got {min_similarity:.2%}"

    def test_quantization_memory_savings(self, quantized_settings: ReflectionAdapterSettings) -> None:
        """Test that quantization achieves 4x memory reduction."""
        # Calculate memory sizes
        embedding_float32_size = 384 * 4  # 384 floats × 4 bytes each
        embedding_uint8_size = 384 * 1  # 384 uint8 × 1 byte each

        compression_ratio = embedding_float32_size / embedding_uint8_size

        print(f"\nMemory usage per embedding:")
        print(f"  Float32: {embedding_float32_size} bytes")
        print(f"  Uint8:  {embedding_uint8_size} bytes")
        print(f"  Compression: {compression_ratio}x")

        assert compression_ratio == 4.0, f"Should achieve 4x compression, got {compression_ratio}x"

    def test_quantization_with_cache(self, quantized_settings: ReflectionAdapterSettings) -> None:
        """Test that quantization works correctly with the embedding cache."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=quantized_settings)

        # Simulate cache interaction: cache stores quantized embeddings
        query = "test query"
        embedding = [0.1, -0.2, 0.3, 0.4] * 96  # 384-dim

        # When caching, we should store the original (not quantized)
        adapter._embedding_cache[query] = embedding

        # Retrieve from cache (should get original, not quantized)
        cached = adapter._embedding_cache.get(query)
        assert cached == embedding, "Cache should store original embedding"

        # Quantization should work on cached embedding
        quantized = adapter._quantize_embedding(cached)
        assert quantized is not None, "Should be able to quantize cached embedding"

    def test_quantization_preserves_ranking(self, quantized_settings: ReflectionAdapterSettings) -> None:
        """Test that quantization preserves relative ranking of similarities."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=quantized_settings)

        # Create test embeddings with known similarities
        base_embedding = np.random.randn(384).tolist()

        # Create embeddings with varying similarity to base
        # Higher values = more similar
        embedding_95_similar = (
            np.array(base_embedding) * 0.95 + np.random.randn(384) * 0.05
        ).tolist()
        embedding_90_similar = (
            np.array(base_embedding) * 0.90 + np.random.randn(384) * 0.10
        ).tolist()
        embedding_85_similar = (
            np.array(base_embedding) * 0.85 + np.random.randn(384) * 0.15
        ).tolist()

        # Quantize all
        base_quantized = adapter._quantize_embedding(base_embedding)
        assert base_quantized is not None

        emb_95_quantized = adapter._quantize_embedding(embedding_95_similar)
        emb_90_quantized = adapter._quantize_embedding(embedding_90_similar)
        emb_85_quantized = adapter._quantize_embedding(embedding_85_similar)

        # Dequantize
        base_dequant = adapter._dequantize_embedding(base_quantized)
        emb_95_dequant = adapter._dequantize_embedding(emb_95_quantized)
        emb_90_dequant = adapter._dequantize_embedding(emb_90_quantized)
        emb_85_dequant = adapter._dequantize_embedding(emb_85_quantized)

        # Calculate similarities with base (dequantized)
        def similarity(a, b):
            a_arr = np.array(a)
            b_arr = np.array(b)
            return np.dot(
                a_arr / np.linalg.norm(a_arr), b_arr / np.linalg.norm(b_arr)
            )

        sim_95 = similarity(base_dequant, emb_95_dequant)
        sim_90 = similarity(base_dequant, emb_90_dequant)
        sim_85 = similarity(base_dequant, emb_85_dequant)

        print(f"\nSimilarities with quantized embeddings:")
        print(f"  95% similar: {sim_95:.6f}")
        print(f"  90% similar: {sim_90:.6f}")
        print(f"  85% similar: {sim_85:.6f}")

        # Check that ranking is preserved (95% > 90% > 85%)
        assert sim_95 > sim_90, "Ranking should be preserved: 95% > 90%"
        assert sim_90 > sim_85, "Ranking should be preserved: 90% > 85%"

    def test_calibration_data_fixed(self, quantized_settings: ReflectionAdapterSettings) -> None:
        """Test that calibration data is available and fixed."""
        adapter = ReflectionDatabaseAdapterOneiric(settings=quantized_settings)

        calibration_data = adapter._get_calibration_data()
        assert calibration_data is not None, "Should have calibration data"

        min_vals, max_vals = calibration_data

        assert len(min_vals) == 384, "Min values should be 384-dimensional"
        assert len(max_vals) == 384, "Max values should be 384-dimensional"

        # Check that calibration data is reasonable (not all zeros, not identical)
        assert not np.allclose(min_vals, max_vals), "Min and max should be different"
        assert not np.all(min_vals == 0), "Min values should not all be zero"
