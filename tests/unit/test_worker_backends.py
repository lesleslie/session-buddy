"""Unit tests for the Worker backend strategy interface.

Phase 4 (REQ-BIFROST-009) replaced the legacy ``BifrostClient`` shim
with a module-level ``_post_bifrost_chat`` helper + the oneiric
``BifrostLLMRouter`` singleton. The tests patch both
``session_buddy.worker.get_router`` and
``session_buddy.worker._post_bifrost_chat`` instead of the
(deleted) ``BifrostClient`` symbol — same monkeypatching surface,
new implementation under test.
"""

from __future__ import annotations

from typing import Any

import pytest


class _FakeRouter:
    """Stand-in for the oneiric ``BifrostLLMRouter`` singleton.

    The real router returns ``None`` when disabled or the OPENAI
    route is unconfigured; the real ``_resolve_bifrost_base_url``
    helper surfaces that ``None`` as ``RuntimeError``. Both paths
    need test coverage, so the fake lets each test pick which
    return it wants.
    """

    def __init__(self, *, openai: str | None = "http://bifrost:8471") -> None:
        self._openai = openai

    def resolve(self, provider: Any) -> str | None:
        if getattr(provider, "name", None) == "OPENAI" or getattr(
            provider, "value", None
        ) == "openai":
            return self._openai
        return None


async def test_placeholder_backend_returns_processed() -> None:
    from session_buddy.worker import PlaceholderBackend, Task

    backend = PlaceholderBackend()
    task = Task(task_id="t", prompt="hello", context={})
    result = await backend.execute("w0", "p1", task)
    assert result["response"] == "Processed task: hello"
    assert result["worker_id"] == "w0"
    assert result["pool_id"] == "p1"
    assert result["prompt"] == "hello"


async def test_llm_backend_calls_bifrost(monkeypatch: pytest.MonkeyPatch) -> None:
    """``LLMBackend`` delegates to ``_post_bifrost_chat`` and shapes the envelope."""
    from session_buddy import worker as worker_mod
    from session_buddy.worker import LLMBackend, Task

    captured: dict[str, Any] = {}

    async def fake_post_bifrost_chat(
        prompt: str,
        *,
        model: str,
        base_url: str,
        system: str | None = None,
        timeout: float = 30.0,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        captured["prompt"] = prompt
        captured["model"] = model
        captured["base_url"] = base_url
        captured["system"] = system
        return {
            "content": "real response",
            "usage": {"total_tokens": 42},
            "model": model,
            "raw": {},
        }

    # Enable the router to return a known URL.
    from oneiric.adapters.llm.bifrost import reset_router_for_tests

    reset_router_for_tests()
    monkeypatch.setattr(worker_mod, "get_router", lambda: _FakeRouter())
    monkeypatch.setattr(worker_mod, "_post_bifrost_chat", fake_post_bifrost_chat)

    backend = LLMBackend(model="minimax/MiniMax-M3")
    task = Task(task_id="t1", prompt="real prompt", context={})
    result = await backend.execute("w0", "p1", task)
    assert result["response"] == "real response"
    assert result["usage"]["total_tokens"] == 42
    assert captured["model"] == "minimax/MiniMax-M3"
    assert captured["base_url"] == "http://bifrost:8471"
    reset_router_for_tests()


async def test_llm_backend_surfaces_errors_as_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LLMBackend`` must not raise; bifrost failures become envelope errors."""
    from session_buddy import worker as worker_mod
    from session_buddy.worker import LLMBackend, Task

    async def broken_post_bifrost_chat(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("connection refused")

    from oneiric.adapters.llm.bifrost import reset_router_for_tests

    reset_router_for_tests()
    monkeypatch.setattr(worker_mod, "get_router", lambda: _FakeRouter())
    monkeypatch.setattr(worker_mod, "_post_bifrost_chat", broken_post_bifrost_chat)

    backend = LLMBackend(model="minimax/MiniMax-M3")
    task = Task(task_id="t1", prompt="hi", context={})
    result = await backend.execute("w0", "p1", task)
    assert result["response"] is None
    assert "bifrost_error" in result["error"]
    assert "RuntimeError" in result["error"]
    reset_router_for_tests()


async def test_llm_backend_error_envelope_redacts_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L1 (api-security review): the envelope-error field must not
    leak the gateway URL when ``httpx`` errors embed it. ``httpx.
    HTTPStatusError`` and ``httpx.ConnectError`` include the
    request URL in their ``__str__``; the worker pool's envelope
    is the operator-log surface, so the URL is redacted via
    ``_redact_httpx_url``.
    """
    from session_buddy import worker as worker_mod
    from session_buddy.worker import LLMBackend, Task

    async def broken_post_bifrost_chat(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # Mimic httpx's ``for url '...'; For more information...`` form.
        raise RuntimeError(
            "Client error '500 Internal Server Error' for url "
            "'http://internal-bifrost:8471/chat/completions'; "
            "For more information check: https://httpstatuses.com/500"
        )

    from oneiric.adapters.llm.bifrost import reset_router_for_tests

    reset_router_for_tests()
    monkeypatch.setattr(worker_mod, "get_router", lambda: _FakeRouter())
    monkeypatch.setattr(worker_mod, "_post_bifrost_chat", broken_post_bifrost_chat)

    backend = LLMBackend(model="minimax/MiniMax-M3")
    task = Task(task_id="t1", prompt="hi", context={})
    result = await backend.execute("w0", "p1", task)
    assert "internal-bifrost:8471" not in result["error"], (
        "L1: gateway URL leaked into envelope error field — "
        "_redact_httpx_url must strip 'for url <URL>' segments."
    )
    assert "for url '<redacted>'" in result["error"]
    assert "bifrost_error" in result["error"]
    reset_router_for_tests()


async def test_llm_backend_uses_task_context_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``task.context`` supplies a model, that one wins over the default."""
    from session_buddy import worker as worker_mod
    from session_buddy.worker import LLMBackend, Task

    captured: dict[str, Any] = {}

    async def fake_post_bifrost_chat(
        prompt: str,
        *,
        model: str,
        base_url: str,
        system: str | None = None,
        timeout: float = 30.0,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        captured["model"] = model
        captured["system"] = system
        return {
            "content": "ok",
            "usage": {},
            "model": model,
            "raw": {},
        }

    from oneiric.adapters.llm.bifrost import reset_router_for_tests

    reset_router_for_tests()
    monkeypatch.setattr(worker_mod, "get_router", lambda: _FakeRouter())
    monkeypatch.setattr(worker_mod, "_post_bifrost_chat", fake_post_bifrost_chat)

    backend = LLMBackend(model="default-model")
    task = Task(
        task_id="t1",
        prompt="hi",
        context={"model": "override-model", "system": "be terse"},
    )
    await backend.execute("w0", "p1", task)
    assert captured["model"] == "override-model"
    assert captured["system"] == "be terse"
    reset_router_for_tests()


async def test_llm_backend_raises_when_router_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-BIFROST-002 structural invariant: when the router returns
    ``None`` for OPENAI (gateway disabled or route unconfigured),
    ``LLMBackend.execute`` surfaces the misconfiguration as an
    envelope error rather than a silent ``None`` response.

    The pre-Phase-4 bug shape (the review F2 finding) was a
    ``BifrostClient(base_url=None)`` that fell through to
    ``http://localhost:8471/v1`` regardless of the operator's
    disabled flag. The new path throws inside ``_resolve_bifrost_base_url``
    so the envelope-error branch can catch it and tag the failure
    as ``bifrost_error: RuntimeError: BifrostLLMRouter returns None...``.
    """
    from oneiric.adapters.llm.bifrost import reset_router_for_tests

    from session_buddy import worker as worker_mod
    from session_buddy.worker import LLMBackend, Task

    reset_router_for_tests()
    # Router disabled — resolve(OPENAI) returns None.
    monkeypatch.setattr(worker_mod, "get_router", lambda: _FakeRouter(openai=None))

    backend = LLMBackend(model="minimax/MiniMax-M3")
    task = Task(task_id="t1", prompt="hi", context={})
    result = await backend.execute("w0", "p1", task)
    assert result["response"] is None
    assert "bifrost_error" in result["error"]
    assert "BifrostLLMRouter returns None" in result["error"]
    reset_router_for_tests()


def test_resolve_bifrost_base_url_uses_router(monkeypatch: pytest.MonkeyPatch) -> None:
    """Structural test for REQ-BIFROST-009: ``_resolve_bifrost_base_url``
    delegates to the oneiric router singleton — no env-var read.

    Synchronous test (no ``async def`` / no ``await``) — the
    helper is sync, and the misleading ``async`` was a leftover
    from copy-pasting the surrounding test shape.
    """
    from oneiric.adapters.llm.bifrost import reset_router_for_tests

    from session_buddy import worker as worker_mod

    reset_router_for_tests()
    monkeypatch.setattr(worker_mod, "get_router", lambda: _FakeRouter())
    assert worker_mod._resolve_bifrost_base_url() == "http://bifrost:8471"
    reset_router_for_tests()


def test_resolve_bifrost_base_url_raises_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural test for REQ-BIFROST-002: the disabled router
    surfaces as a clear ``RuntimeError`` (caught by
    ``LLMBackend.execute``'s envelope-error branch).
    """
    from oneiric.adapters.llm.bifrost import reset_router_for_tests

    from session_buddy import worker as worker_mod

    reset_router_for_tests()
    monkeypatch.setattr(worker_mod, "get_router", lambda: _FakeRouter(openai=None))
    with pytest.raises(RuntimeError, match="BifrostLLMRouter returns None"):
        worker_mod._resolve_bifrost_base_url()
    reset_router_for_tests()
