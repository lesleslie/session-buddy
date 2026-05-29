from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_FINGERPRINT_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "fingerprint.py"
_FINGERPRINT_SPEC = spec_from_file_location("session_buddy.utils.fingerprint", _FINGERPRINT_PATH)
assert _FINGERPRINT_SPEC is not None and _FINGERPRINT_SPEC.loader is not None
_fingerprint = module_from_spec(_FINGERPRINT_SPEC)
sys.modules[_FINGERPRINT_SPEC.name] = _fingerprint
_FINGERPRINT_SPEC.loader.exec_module(_fingerprint)

MAX_NGRAMS_FOR_FULL_MINHASH = _fingerprint.MAX_NGRAMS_FOR_FULL_MINHASH
MinHashSignature = _fingerprint.MinHashSignature
extract_ngrams = _fingerprint.extract_ngrams


def test_from_ngrams_truncates_large_input() -> None:
    ngrams = [f"g{i:04d}" for i in range(MAX_NGRAMS_FOR_FULL_MINHASH + 50)]

    signature = MinHashSignature.from_ngrams(ngrams, seed=7)

    assert len(signature.signature) == 128
    assert signature.num_hashes == 128


def test_signature_normalization_and_repr() -> None:
    signature = MinHashSignature(signature=[2**65 + 7] * 128)

    assert signature.signature == [7] * 128
    representation = repr(signature)
    assert "MinHashSignature" in representation
    assert "num_hashes=128" in representation
    assert "[" in representation and "..." in representation


def test_from_bytes_roundtrip_uses_exact_size() -> None:
    signature = MinHashSignature.from_ngrams(extract_ngrams("python async", n=3))
    data = signature.to_bytes()

    reconstructed = MinHashSignature.from_bytes(data)

    assert reconstructed.signature == signature.signature


def test_empty_and_invalid_signature_inputs() -> None:
    with pytest.raises(ValueError, match="Signature length"):
        MinHashSignature(signature=[1, 2, 3], num_hashes=128)

    empty = MinHashSignature.from_ngrams([])
    assert empty.signature == [0] * 128
