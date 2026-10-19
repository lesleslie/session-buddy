"""REQ-BIFROST-009 structural tests for LLMManager ↔ BifrostLLMRouter.

Phase 4 of the bifrost plan (``docs/plans/2026-10-17-bifrost-oneiric-gateway-adapter.md``)
replaces the legacy ``BIFROST_BASE_URL`` env-var read in
``session_buddy/llm_providers.py`` with a oneiric ``BifrostLLMRouter``
lookup. The OPENAI-compatible provider in the chain
(``minimax``) sources its ``base_url`` from the router when the
router is enabled; otherwise the chain falls back to the
existing direct-cloud URL.

These tests are the **structural** layer of the proof — they
pin the contract that ``LLMManager._build_chain`` consults the
oneiric router and that the OPENAI-provider ``base_url`` is
correctly threaded into the ``FallbackChain`` settings.

The runtime behavior is mirrored by
``tests/unit/test_worker_backends.py::test_llm_backend_calls_bifrost``
(the worker backends exercise the same router) and
``tests/unit/memory/test_entity_extractor.py::test_bifrost_url_triggers_default_model_replacement``
(the entity extractor). This file focuses on the LLMManager
specifically so a future refactor that breaks the manager
without breaking the backends still trips a test.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from oneiric.adapters.llm.bifrost import reset_router_for_tests


class _FakeRouter:
    """Stand-in for the oneiric ``BifrostLLMRouter`` singleton.

    The real router returns ``None`` for unmapped providers or
    when disabled; the LLMManager's ``_build_chain`` treats
    ``None`` as "use the direct-cloud URL".
    """

    def __init__(self, *, openai: str | None = None) -> None:
        self._openai = openai

    def resolve(self, provider: object) -> str | None:
        if getattr(provider, "name", None) == "OPENAI" or getattr(
            provider, "value", None
        ) == "openai":
            return self._openai
        return None


@pytest.fixture(autouse=True)
def _reset_bifrost_router(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test router reset so oneiric env-var state doesn't leak."""
    for env_key in (
        "ONEIRIC_BIFROST_ENABLED",
        "ONEIRIC_BIFROST_BASE_URL",
        "ONEIRIC_BIFROST_ROUTES",
        "BIFROST_BASE_URL",
        "ONEIRIC_BIFROST_ANTHROPIC_BASE_URL",
    ):
        monkeypatch.delenv(env_key, raising=False)
    reset_router_for_tests()
    yield
    reset_router_for_tests()


def test_manager_uses_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-BIFROST-009: the OPENAI-compatible provider in
    ``LLMManager._build_chain`` sources its ``base_url`` from
    the oneiric router when the router is enabled.

    This is the canonical evidence path cited by the bifrost
    plan (``docs/plans/2026-10-17-bifrost-oneiric-gateway-adapter.md``
    line 251, 563) and the plan-tracking checkpoint. Renamed
    from the longer ``test_manager_uses_router_for_openai_provider``
    so the plan's evidence string resolves to a real test
    (the prior name lived in this dedicated file because the
    existing ``test_llm_providers.py`` is 751 lines — the
    function symbol is what the plan tracks).

    Captures the ``LLMSettings`` instance handed to
    ``FallbackChain.from_settings`` and asserts the
    ``minimax`` provider's ``base_url`` matches the router's
    resolved URL.
    """
    from mcp_common.llm import LLMSettings

    from session_buddy.llm_providers import LLMManager

    monkeypatch.setenv("ONEIRIC_BIFROST_ENABLED", "true")
    monkeypatch.setenv("ONEIRIC_BIFROST_ROUTES", "qwen_route")
    monkeypatch.setenv("ONEIRIC_BIFROST_BASE_URL", "http://bifrost:8471")
    reset_router_for_tests()

    captured: dict[object, object] = {}

    def fake_from_settings(settings: LLMSettings) -> object:
        captured["settings"] = settings
        return object()  # FallbackChain stand-in (not used in this test)

    with (
        patch("session_buddy.llm_providers.get_router", lambda: _FakeRouter(openai="http://bifrost:8471")),
        patch("session_buddy.llm_providers.FallbackChain.from_settings", fake_from_settings),
    ):
        LLMManager()

    settings = captured["settings"]
    assert isinstance(settings, LLMSettings)
    minimax = settings.providers["minimax"]
    assert minimax["base_url"] == "http://bifrost:8471", (
        "REQ-BIFROST-009: LLMManager must source minimax's base_url "
        "from the oneiric BifrostLLMRouter singleton."
    )


def test_manager_falls_back_to_direct_cloud_when_router_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-BIFROST-002 (transparent-proxy): when the router is
    disabled (``resolve(LLMProvider.OPENAI) returns None``),
    the OPENAI-compatible provider falls back to the
    direct-cloud URL (``MINIMAX_BASE_URL`` env or the
    public ``api.minimax.io`` default).

    This pins the no-bifrost regression path: an operator who
    has not enabled the router must still get a working
    LLM call surface (the FallbackChain posts to
    ``https://api.minimax.io/v1`` directly).
    """
    from mcp_common.llm import LLMSettings

    from session_buddy.llm_providers import LLMManager

    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    reset_router_for_tests()
    captured: dict[object, object] = {}

    def fake_from_settings(settings: LLMSettings) -> object:
        captured["settings"] = settings
        return object()

    with (
        patch("session_buddy.llm_providers.get_router", lambda: _FakeRouter(openai=None)),
        patch("session_buddy.llm_providers.FallbackChain.from_settings", fake_from_settings),
    ):
        LLMManager()

    settings = captured["settings"]
    assert isinstance(settings, LLMSettings)
    minimax = settings.providers["minimax"]
    assert minimax["base_url"] == "https://api.minimax.io/v1", (
        "REQ-BIFROST-002: with the router disabled, the manager must "
        "fall back to the public direct-cloud URL."
    )


def test_manager_minimax_base_url_override_takes_precedence_over_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy ``MINIMAX_BASE_URL`` env-var override wins over
    the router only when the router is disabled. With the router
    enabled, the operator is explicitly opting into the gateway
    and the legacy env-var is ignored (REQ-BIFROST-009).
    """
    from mcp_common.llm import LLMSettings

    from session_buddy.llm_providers import LLMManager

    monkeypatch.setenv("ONEIRIC_BIFROST_ENABLED", "true")
    monkeypatch.setenv("ONEIRIC_BIFROST_ROUTES", "qwen_route")
    monkeypatch.setenv("ONEIRIC_BIFROST_BASE_URL", "http://bifrost:8471")
    monkeypatch.setenv("MINIMAX_BASE_URL", "http://legacy-direct:9999/v1")
    reset_router_for_tests()

    captured: dict[object, object] = {}

    def fake_from_settings(settings: LLMSettings) -> object:
        captured["settings"] = settings
        return object()

    with (
        patch("session_buddy.llm_providers.get_router", lambda: _FakeRouter(openai="http://bifrost:8471")),
        patch("session_buddy.llm_providers.FallbackChain.from_settings", fake_from_settings),
    ):
        LLMManager()

    settings = captured["settings"]
    minimax = settings.providers["minimax"]
    # Router wins — operator opted into the gateway.
    assert minimax["base_url"] == "http://bifrost:8471"


def test_manager_routes_only_openai_through_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural invariant: only the OPENAI-compatible provider
    (``minimax``) is gated by the router. ``llama_server`` keeps
    its env-var-only resolution (the router's
    ``_PROVIDER_ROUTE`` only maps ANTHROPIC + OPENAI).

    Pinning this prevents a future refactor from accidentally
    routing ``llama_server`` through the router (which would
    ``KeyError`` at runtime per the oneiric router contract).
    """
    from mcp_common.llm import LLMSettings

    from session_buddy.llm_providers import LLMManager

    monkeypatch.setenv("ONEIRIC_BIFROST_ENABLED", "true")
    monkeypatch.setenv("ONEIRIC_BIFROST_ROUTES", "qwen_route")
    monkeypatch.setenv("ONEIRIC_BIFROST_BASE_URL", "http://bifrost:8471")
    monkeypatch.setenv("LLAMA_SERVER_URL", "http://local-llama:9999")
    reset_router_for_tests()

    captured: dict[object, object] = {}

    def fake_from_settings(settings: LLMSettings) -> object:
        captured["settings"] = settings
        return object()

    with (
        patch("session_buddy.llm_providers.get_router", lambda: _FakeRouter(openai="http://bifrost:8471")),
        patch("session_buddy.llm_providers.FallbackChain.from_settings", fake_from_settings),
    ):
        LLMManager()

    settings = captured["settings"]
    # ``llama_server`` keeps its env-var URL — never reads from the router.
    assert settings.providers["llama_server"]["base_url"] == "http://local-llama:9999"
    # ``minimax`` got the router's URL.
    assert settings.providers["minimax"]["base_url"] == "http://bifrost:8471"
