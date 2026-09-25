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