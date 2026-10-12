"""Substrate adoption contract (Phase E2, Plan 2 Task 2).

These tests pin the atomic per-file migration of
``session_buddy/settings.py`` to ``OneiricSettings.substrate.*``.
The atomic-per-file rule forbids partial state — for every migrated
key, the local declaration is deleted AND the default is replaced
with a ``default_factory`` reading from substrate. The test
authoritative surface is ``session_buddy.settings.get_settings``.

Auth short-circuit (Phase E2 spec §2): when
``ONEIRIC__SUBSTRATE__AUTH__ENABLED`` is ``true``, the settings object
exposes ``auth_enabled == True``; when ``false`` (the substrate
default), ``auth_enabled == False``. ``auth_loopback_trusted`` mirrors
``ONEIRIC__SUBSTRATE__AUTH__LOOPBACK_TRUSTED``.

Test isolation: every test calls ``reload_settings()`` (forces a
fresh ``SessionBuddySettings.load()``) and clears the
module-level substrate cache so ``monkeypatch.setenv`` propagation
into the substrate defaults is deterministic.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def _reset_settings_and_substrate_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear module-level cache + force reload between tests.

    Phase E2 atomic rule: a substrate override must produce a fresh
    field value on the next ``get_settings()`` call. The cached
    ``OneiricSettings().substrate`` would otherwise hide env-var
    changes that ``monkeypatch.setenv`` introduces mid-test. We
    reload the settings module + drop the substrate cache before
    each test, then let the test bootstrap a fresh load via
    ``reload_settings()``.
    """
    import session_buddy.settings as sb_settings

    sb_settings._settings = None
    sb_settings._substrate_cache = None  # type: ignore[attr-defined]
    # Reload so any test-time monkeypatching of session_buddy.settings
    # members resolves consistently across runs.
    importlib.reload(sb_settings)
    yield
    sb_settings._settings = None
    sb_settings._substrate_cache = None  # type: ignore[attr-defined]


def test_embedding_model_via_substrate(monkeypatch: pytest.MonkeyPatch) -> None:
    """``search.embedding_model`` defaults from ``substrate.embedding__model``."""
    monkeypatch.setenv("ONEIRIC__SUBSTRATE__EMBEDDING__MODEL", "test-embed-model")
    from session_buddy.settings import reload_settings

    s = reload_settings()

    assert s.search.embedding_model == "test-embed-model"


def test_auth_enabled_via_substrate(monkeypatch: pytest.MonkeyPatch) -> None:
    """``auth_enabled`` defaults from ``substrate.auth__enabled``.

    The setting is loopback-default false (``ONEIRIC__SUBSTRATE__AUTH__
    ENABLED=False``). Auth short-circuit MUST continue to bypass
    middleware + decorator gates when the substrate says
    ``auth__enabled=False`` (per ``feedback-bodai-localhost-no-auth.md``).
    """
    monkeypatch.setenv("ONEIRIC__SUBSTRATE__AUTH__ENABLED", "true")
    from session_buddy.settings import reload_settings

    s = reload_settings()

    assert s.auth_enabled is True


def test_auth_loopback_trusted_via_substrate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``auth_loopback_trusted`` defaults from substrate; required for
    the localhost-no-auth escape hatch."""
    monkeypatch.setenv(
        "ONEIRIC__SUBSTRATE__AUTH__LOOPBACK_TRUSTED", "false"
    )
    from session_buddy.settings import reload_settings

    s = reload_settings()

    assert s.auth_loopback_trusted is False


def test_substrate_default_does_not_overload_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no ``ONEIRIC__SUBSTRATE__EMBEDDING__MODEL`` env is set, the
    substrate default (``nomic-embed-text`` per Phase E1) flows
    through — i.e. the search field no longer carries the legacy
    hardcoded ``all-MiniLM-L6-v2`` string."""
    monkeypatch.delenv("ONEIRIC__SUBSTRATE__EMBEDDING__MODEL", raising=False)
    from session_buddy.settings import reload_settings

    s = reload_settings()

    assert s.search.embedding_model == "nomic-embed-text"


def test_get_settings_signature_unchanged() -> None:
    """Public-surface contract: ``get_settings()`` returns a
    ``SessionBuddySettings`` instance — never ``OneiricSettings``
    directly. Existing callers (CLI, mcp/server.py) keep working
    without changes."""
    from session_buddy.settings import (
        SessionBuddySettings,
        get_settings,
    )

    s = get_settings()

    assert isinstance(s, SessionBuddySettings)
