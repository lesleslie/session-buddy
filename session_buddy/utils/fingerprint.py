"""N-gram fingerprinting for duplicate detection (Phase 4).

This module implements MinHash-based fingerprinting to detect duplicate and
near-duplicate content in conversations and reflections, reducing database bloat
and improving search quality.

Algorithm:
    1. Normalize content (lowercase, remove extra whitespace)
    2. Extract n-grams (n=3 character sequences)
    3. Generate MinHash signature (128 min-hash values)
    4. Estimate Jaccard similarity via signature comparison

Usage:
    >>> from session_buddy.utils.fingerprint import MinHashSignature, extract_ngrams
    >>> content = "Python async programming patterns"
    >>> ngrams = extract_ngrams(content, n=3)
    >>> signature = MinHashSignature.from_ngrams(ngrams)
    >>> signature.to_bytes()  # For database storage
    >>> signature.estimate_similarity(other_signature)  # Jaccard similarity
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# MinHash configuration
NUM_HASH_FUNCTIONS = 128  # Number of hash functions for MinHash signature
NGRAM_SIZE = 3  # Character n-gram size


def normalize_for_fingerprint(text: str) -> str:
    """Normalize text for fingerprinting.

    Removes formatting differences while preserving semantic content.
    Normalization includes:
    - Lowercase conversion
    - Whitespace normalization (collapses multiple spaces/tabs/newlines to single space)
    - Leading/trailing whitespace removal

    Args:
        text: Raw text content

    Returns:
        Normalized text suitable for n-gram extraction

    Examples:
        >>> normalize_for_fingerprint("  Python   async  \\n patterns  ")
        'python async patterns'
    """
    if not text:
        return ""

    # Convert to lowercase
    normalized = text.lower()

    # Normalize whitespace: collapse runs of spaces, tabs, newlines to single space
    normalized = re.sub(r"\s+", " ", normalized)

    # Strip leading/trailing whitespace
    normalized = normalized.strip()

    return normalized


def extract_ngrams(text: str, n: int = NGRAM_SIZE) -> list[str]:
    """Extract character n-grams from text.

    N-grams are overlapping sequences of n characters. For example,
    "python" with n=3 produces ["pyt", "yth", "ho", "on"].

    Args:
        text: Input text (should be normalized first)
        n: N-gram size (default: 3)

    Returns:
        List of n-gram strings

    Examples:
        >>> extract_ngrams("python", n=3)
        ['pyt', 'yth', 'ho', 'on']
        >>> extract_ngrams("ai", n=3)
        ['ai']
    """
    if not text or len(text) < n:
        # Return text as single n-gram if shorter than n
        return [text] if text else []

    ngrams = []
    for i in range(len(text) - n + 1):
        ngram = text[i : i + n]
        ngrams.append(ngram)

    return ngrams


@dataclass
class MinHashSignature:
    """MinHash signature for approximate Jaccard similarity estimation.

    MinHash compresses large sets into a fixed-size signature by hashing
    each element and keeping only the minimum hash value for each hash function.
    This allows efficient estimation of Jaccard similarity without comparing
    full sets.

    Attributes:
        signature: List of NUM_HASH_FUNCTIONS minimum hash values
        num_hashes: Number of hash functions used (for validation)

    Example:
        >>> ngrams = extract_ngrams("python async patterns")
        >>> sig = MinHashSignature.from_ngrams(ngrams)
        >>> sig.estimate_similarity(other_sig)  # 0.0 to 1.0
    """

    signature: list[int]
    num_hashes: int = NUM_HASH_FUNCTIONS

    def __post_init__(self) -> None:
        """Validate signature after initialization."""
        if len(self.signature) != self.num_hashes:
            raise ValueError(
                f"Signature length {len(self.signature)} does not match "
                f"num_hashes {self.num_hashes}"
            )

    @classmethod
    def from_text(cls, text: str, n: int = NGRAM_SIZE) -> MinHashSignature:
        """Create MinHash signature directly from text.

        Convenience method that combines normalization, n-gram extraction,
        and signature generation.

        Args:
            text: Raw text content
            n: N-gram size (default: 3)

        Returns:
            MinHashSignature instance
        """
        normalized = normalize_for_fingerprint(text)
        ngrams = extract_ngrams(normalized, n)
        return cls.from_ngrams(ngrams)

    @classmethod
    def from_ngrams(cls, ngrams: list[str], seed: int = 42) -> MinHashSignature:
        """Generate MinHash signature from n-grams.

        Uses NUM_HASH_FUNCTIONS different hash functions (simulated via
        seeded hashing) to generate the signature. For each hash function,
        we compute the hash of every n-gram and keep the minimum value.

        Args:
            ngrams: List of n-gram strings
            seed: Random seed for hash function generation

        Returns:
            MinHashSignature instance

        Algorithm:
            For i in 0..NUM_HASH_FUNCTIONS-1:
                signature[i] = min(hash_i(gram) for gram in ngrams)
        """
        if not ngrams:
            # Empty signature if no n-grams
            return cls(signature=[0] * NUM_HASH_FUNCTIONS)

        # Generate signature with NUM_HASH_FUNCTIONS hash functions
        signature = []

        for i in range(NUM_HASH_FUNCTIONS):
            # Create hash function i by combining seed with function index
            # This simulates having different hash functions
            def _hash_func(x: str, s: int = seed, idx: int = i) -> int:
                """Hash function for MinHash signature generation."""
                return int(hashlib.sha256(f"{s}:{idx}:{x}".encode()).hexdigest(), 16)

            # Find minimum hash value for this hash function across all n-grams
            min_hash = min(_hash_func(gram) for gram in ngrams)
            signature.append(min_hash)

        return cls(signature=signature, num_hashes=NUM_HASH_FUNCTIONS)

    def estimate_jaccard_similarity(self, other: MinHashSignature) -> float:
        """Estimate Jaccard similarity using MinHash signatures.

        Jaccard similarity between two sets A and B is:
            |A ∩ B| / |A ∪ B|

        MinHash property: Pr[minhash(h) == minhash(h)] = Jaccard(A,B)
        We estimate this by counting how many hash functions have the
        same minimum value between the two signatures.

        Args:
            other: Another MinHashSignature instance

        Returns:
            Estimated Jaccard similarity (0.0 to 1.0)

        Raises:
            ValueError: If signatures have different num_hashes
        """
        if self.num_hashes != other.num_hashes:
            raise ValueError(
                f"Cannot compare signatures with different num_hashes: "
                f"{self.num_hashes} vs {other.num_hashes}"
            )

        # Count matching minimum hash values
        matches = sum(
            1 for i in range(self.num_hashes) if self.signature[i] == other.signature[i]
        )

        # Estimate Jaccard similarity as fraction of matches
        return matches / self.num_hashes

    def to_bytes(self) -> bytes:
        """Convert signature to bytes for database storage.

        Packs each integer hash value into 8 bytes (little-endian),
        resulting in NUM_HASH_FUNCTIONS * 8 bytes total.

        Returns:
            Bytes representation suitable for BLOB storage

        Example:
            >>> sig = MinHashSignature.from_text("test")
            >>> blob = sig.to_bytes()
            >>> len(blob) == NUM_HASH_FUNCTIONS * 8
            True
        """
        import struct

        # Pack each int into 8 bytes (little-endian) using unsigned long long
        # Using 'Q' format for unsigned long long (8 bytes)
        # Modulo 2^64 to ensure values fit in unsigned long long
        signature_64bit = [h % (2**64) for h in self.signature]
        byte_data = struct.pack(f"{self.num_hashes}Q", *signature_64bit)
        return byte_data

    @classmethod
    def from_bytes(cls, data: bytes) -> MinHashSignature:
        """Reconstruct MinHash signature from bytes.

        Args:
            data: Bytes representation from to_bytes()

        Returns:
            MinHashSignature instance

        Raises:
            ValueError: If data length doesn't match expected size
        """
        import struct

        expected_size = NUM_HASH_FUNCTIONS * 8  # 8 bytes per int
        if len(data) != expected_size:
            raise ValueError(
                f"Expected {expected_size} bytes, got {len(data)}. "
                f"Data may be corrupted or from different configuration."
            )

        # Unpack NUM_HASH_FUNCTIONS unsigned long longs (little-endian)
        signature = list(struct.unpack(f"{NUM_HASH_FUNCTIONS}Q", data))
        return cls(signature=signature, num_hashes=NUM_HASH_FUNCTIONS)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"MinHashSignature(num_hashes={self.num_hashes}, signature=[{self.signature[0]}, ..., {self.signature[-1]}])"
