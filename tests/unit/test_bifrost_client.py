"""Unit tests for the Bifrost LLM gateway client."""

from __future__ import annotations

from typing import Any

import pytest


class FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


class FakeAsyncClient:
    def __init__(self, captured: dict[str, Any], body: dict[str, Any]) -> None:
        self._captured = captured
        self._body = body

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *a: object) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self._captured["url"] = url
        self._captured["json"] = json
        self._captured["headers"] = headers
        return FakeResponse(self._body)


async def test_bifrost_async_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """BifrostClient.chat posts to /chat/completions and parses response."""
    import httpx2

    from session_buddy.bifrost_client import BifrostClient

    captured: dict[str, Any] = {}
    body = {
        "choices": [{"message": {"content": "async-echoed"}}],
        "usage": {"total_tokens": 7},
        "model": "minimax/MiniMax-M3",
    }

    def factory(**kw: Any) -> FakeAsyncClient:
        return FakeAsyncClient(captured, body)

    monkeypatch.setattr(httpx2, "AsyncClient", factory)

    client = BifrostClient(base_url="http://test:9999/v1")
    try:
        result = await client.chat("hi async", model="minimax/MiniMax-M3")
    finally:
        await client.aclose()

    assert result["content"] == "async-echoed"
    assert result["usage"]["total_tokens"] == 7
    assert result["model"] == "minimax/MiniMax-M3"
    assert captured["url"] == "http://test:9999/v1/chat/completions"
    assert captured["json"]["model"] == "minimax/MiniMax-M3"
    assert captured["headers"]["Content-Type"] == "application/json"


async def test_bifrost_chat_with_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """system param must be sent as the first system message in the payload."""
    import httpx2

    from session_buddy.bifrost_client import BifrostClient

    captured: dict[str, Any] = {}
    body = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"total_tokens": 1},
        "model": "minimax/MiniMax-M3",
    }

    def factory(**kw: Any) -> FakeAsyncClient:
        return FakeAsyncClient(captured, body)

    monkeypatch.setattr(httpx2, "AsyncClient", factory)

    client = BifrostClient(base_url="http://test:9999/v1")
    try:
        await client.chat(
            "prompt", model="minimax/MiniMax-M3", system="be terse"
        )
    finally:
        await client.aclose()

    messages = captured["json"]["messages"]
    assert messages[0] == {"role": "system", "content": "be terse"}
    assert messages[-1] == {"role": "user", "content": "prompt"}


async def test_bifrost_chat_with_api_key_adds_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """api_key parameter must be forwarded as ``Authorization: Bearer`` header."""
    import httpx2

    from session_buddy.bifrost_client import BifrostClient

    captured: dict[str, Any] = {}
    body = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {},
        "model": "x",
    }

    def factory(**kw: Any) -> FakeAsyncClient:
        return FakeAsyncClient(captured, body)

    monkeypatch.setattr(httpx2, "AsyncClient", factory)

    client = BifrostClient(
        base_url="http://test:9999/v1", api_key="secret-key"
    )
    try:
        await client.chat("hi", model="x")
    finally:
        await client.aclose()

    assert captured["headers"]["Authorization"] == "Bearer secret-key"


async def test_bifrost_uses_oneiric_secrets_for_api_key(monkeypatch) -> None:
    """BifrostClient reads BIFROST_API_KEY via Oneiric secrets (env backend)."""
    monkeypatch.setenv("ONEIRIC_SECRETS_BACKEND", "env")
    monkeypatch.setenv("ONEIRIC_SECRET_BIFROST_API_KEY", "test-key-from-oneiric")
    monkeypatch.delenv("BIFROST_API_KEY", raising=False)
    monkeypatch.delenv("BIFROST_BASE_URL", raising=False)

    from session_buddy.bifrost_client import BifrostClient

    client = BifrostClient()
    try:
        assert await client._resolve_api_key() == "test-key-from-oneiric"
        assert (
            client._headers()["Authorization"] == "Bearer test-key-from-oneiric"
        )
    finally:
        # _resolve_api_key does not allocate httpx resources; no aclose needed.
        await client.aclose() if client._client is not None else None


async def test_bifrost_legacy_env_fallback(monkeypatch) -> None:
    """Legacy BIFROST_API_KEY (no prefix) still resolves when ONEIRIC prefix absent."""
    monkeypatch.setenv("ONEIRIC_SECRETS_BACKEND", "env")
    monkeypatch.delenv("ONEIRIC_SECRET_BIFROST_API_KEY", raising=False)
    monkeypatch.setenv("BIFROST_API_KEY", "legacy-key")
    monkeypatch.delenv("BIFROST_BASE_URL", raising=False)

    from session_buddy.bifrost_client import BifrostClient

    client = BifrostClient()
    try:
        assert await client._resolve_api_key() == "legacy-key"
        assert client._headers()["Authorization"] == "Bearer legacy-key"
    finally:
        await client.aclose() if client._client is not None else None


async def test_bifrost_explicit_api_key_short_circuits_secrets(
    monkeypatch,
) -> None:
    """An explicit api_key argument must skip the Oneiric lookup entirely."""
    monkeypatch.setenv("ONEIRIC_SECRETS_BACKEND", "env")
    monkeypatch.setenv("ONEIRIC_SECRET_BIFROST_API_KEY", "should-not-be-used")
    monkeypatch.delenv("BIFROST_API_KEY", raising=False)

    from session_buddy.bifrost_client import BifrostClient

    client = BifrostClient(api_key="explicit-key")
    try:
        assert await client._resolve_api_key() == "explicit-key"
        assert client._headers()["Authorization"] == "Bearer explicit-key"
    finally:
        await client.aclose() if client._client is not None else None
