"""Unit tests for the Oneiric secrets adapter wrapper.

Tracks A-ext1 of the serverless-tiering plan: the wrapper must read
``ONEIRIC_SECRET_<KEY>`` (preferred) or fall back to the legacy ``<KEY>``
env var so existing BIFROST_API_KEY / MINIMAX_API_KEY exports continue to
work.
"""

from __future__ import annotations

from oneiric.adapters.secrets.env import EnvSecretSettings

from session_buddy.secrets_oneiric import get_secret


async def test_get_secret_env_oneiric_prefix(monkeypatch) -> None:
    """EnvSecretAdapter looks up ONEIRIC_SECRET_<KEY>."""
    monkeypatch.setenv("ONEIRIC_SECRET_BIFROST_API_KEY", "oneiric-key")
    assert (
        await get_secret("BIFROST_API_KEY", settings=EnvSecretSettings())
        == "oneiric-key"
    )


async def test_get_secret_env_legacy_fallback(monkeypatch) -> None:
    """Legacy BIFROST_API_KEY (no prefix) still works for backward compat."""
    monkeypatch.delenv("ONEIRIC_SECRET_BIFROST_API_KEY", raising=False)
    monkeypatch.setenv("BIFROST_API_KEY", "legacy-key")
    assert (
        await get_secret(
            "BIFROST_API_KEY",
            settings=EnvSecretSettings(),
            legacy_fallback=True,
        )
        == "legacy-key"
    )


async def test_get_secret_returns_none_when_missing(monkeypatch) -> None:
    """Missing in both ONEIRIC_SECRET_<KEY> and legacy <KEY> returns None."""
    monkeypatch.delenv("ONEIRIC_SECRET_TEST_MISSING", raising=False)
    monkeypatch.delenv("TEST_MISSING", raising=False)
    assert (
        await get_secret(
            "TEST_MISSING",
            settings=EnvSecretSettings(),
            legacy_fallback=True,
        )
        is None
    )
