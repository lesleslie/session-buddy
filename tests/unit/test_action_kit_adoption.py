"""Tests for Oneiric action-kit adoption in Session-Buddy.

Wave 3 (W3) migration:
- ``CrossProjectAuth.sign_message`` / ``verify_message`` now routes through
  ``oneiric.actions.security.SecuritySignatureAction`` so cross-project
  message envelopes match every other Bodai component.
- ``oneiric`` is now a direct dependency in ``pyproject.toml`` (not just
  via mcp-common transitively) so consumers import from oneiric directly.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import pytest

from session_buddy.mcp.auth import (
    CrossProjectAuth,
    _signature_action,
)


@pytest.fixture(autouse=True)
def _reset_signature_action_cache() -> None:
    _signature_action.cache_clear()
    yield
    _signature_action.cache_clear()


def _run(coro):
    return asyncio.run(coro)


def test_signature_action_uses_canonical_envelope() -> None:
    """The cached SecuritySignatureAction matches the cross-project wire format."""
    action = _signature_action()
    assert action._settings.algorithm == "sha256"
    assert action._settings.encoding == "hex"
    assert action._settings.header_name == "X-SessionBuddy-Signature"
    assert action._settings.include_timestamp is False


def test_cross_project_auth_signature_matches_legacy_hmac() -> None:
    """Wire format must stay compatible with the in-tree HMAC the kit replaced."""
    auth = CrossProjectAuth("shared-secret")
    message = {"b": 2, "a": 1}
    signature = _run(auth.sign_message(message))

    # Re-derive the legacy HMAC and assert byte-for-byte equality.
    message_str = json.dumps(message, sort_keys=True)
    legacy = hmac.new(
        b"shared-secret",
        message_str.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert signature == legacy


async def test_cross_project_auth_verify_accepts_valid_signature() -> None:
    auth = CrossProjectAuth("k")
    message = {"hello": "world", "n": 42}
    signature = await auth.sign_message(message)
    assert await auth.verify_message(message, signature) is True


async def test_cross_project_auth_verify_rejects_invalid_signature() -> None:
    auth = CrossProjectAuth("k")
    assert await auth.verify_message({"a": 1}, "0" * 64) is False


async def test_signature_uses_canonical_header_name() -> None:
    """Confirm the kit produces the canonical session-buddy header on demand."""
    from session_buddy.mcp.auth import _signature_action

    action = _signature_action()
    result = await action.execute(
        {
            "secret": "s",
            "message": "payload",
            "algorithm": "sha256",
            "encoding": "hex",
        }
    )
    assert result["header"] == "X-SessionBuddy-Signature"
    assert result["algorithm"] == "sha256"
    assert result["encoding"] == "hex"


def test_oneiric_listed_as_direct_dependency() -> None:
    """oneiric must be a direct dep (not only transitive via mcp-common)."""
    from pathlib import Path

    pyproject = (
        Path(__file__).resolve().parents[2] / "pyproject.toml"
    ).read_text()
    assert '"oneiric>=' in pyproject, (
        "W3 invariant: oneiric must be a direct dependency in pyproject.toml"
    )
