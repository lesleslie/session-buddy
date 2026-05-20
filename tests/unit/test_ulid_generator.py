from __future__ import annotations

import sys
import types

from session_buddy.core import ulid_generator


def test_generate_ulid_uses_druva_when_available(monkeypatch) -> None:
    fake_druva = types.ModuleType("druva")
    fake_druva.generate = lambda: "druva-generated-ulid-000000"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "druva", fake_druva)

    assert ulid_generator.generate_ulid() == "druva-generated-ulid-000000"


def test_generate_ulid_fallback_is_deterministic_with_patched_entropy(
    monkeypatch,
) -> None:
    monkeypatch.delitem(sys.modules, "druva", raising=False)
    monkeypatch.setattr(ulid_generator.time, "time", lambda: 1_700_000_000.123)
    monkeypatch.setattr(ulid_generator.os, "urandom", lambda n: b"\x01" * n)

    result = ulid_generator.generate_ulid()

    assert len(result) == 26
    assert ulid_generator.is_valid_ulid(result) is True


def test_is_valid_ulid_branches() -> None:
    assert ulid_generator.is_valid_ulid("0" * 26) is True
    assert ulid_generator.is_valid_ulid("0" * 25) is False
    assert ulid_generator.is_valid_ulid("0" * 26 + "1") is False
    assert ulid_generator.is_valid_ulid("0" * 25 + "i") is False
