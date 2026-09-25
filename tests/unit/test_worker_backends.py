"""Unit tests for the Worker backend strategy interface."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


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
    """LLMBackend delegates to BifrostClient.chat and shapes the envelope."""
    # Patch the symbol imported into worker.py — that's the one LLMBackend
    # uses when it does ``BifrostClient(...)``.
    from session_buddy import worker as worker_mod
    from session_buddy.worker import LLMBackend, Task

    captured: dict[str, Any] = {}

    class FakeBifrost:
        async def chat(
            self, prompt: str, *, model: str, **kw: Any
        ) -> dict[str, Any]:
            captured["prompt"] = prompt
            captured["model"] = model
            return {
                "content": "real response",
                "usage": {"total_tokens": 42},
                "model": model,
                "raw": {},
            }

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(worker_mod, "BifrostClient", lambda **kw: FakeBifrost())

    backend = LLMBackend(model="minimax/MiniMax-M3")
    task = Task(task_id="t1", prompt="real prompt", context={})
    result = await backend.execute("w0", "p1", task)
    assert result["response"] == "real response"
    assert result["usage"]["total_tokens"] == 42
    assert captured["model"] == "minimax/MiniMax-M3"


async def test_llm_backend_surfaces_errors_as_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMBackend must not raise; bifrost failures become envelope errors."""
    from session_buddy import worker as worker_mod
    from session_buddy.worker import LLMBackend, Task

    class BrokenBifrost:
        async def chat(self, *a: Any, **kw: Any) -> dict[str, Any]:
            raise RuntimeError("connection refused")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        worker_mod, "BifrostClient", lambda **kw: BrokenBifrost()
    )

    backend = LLMBackend(model="minimax/MiniMax-M3")
    task = Task(task_id="t1", prompt="hi", context={})
    result = await backend.execute("w0", "p1", task)
    assert result["response"] is None
    assert "bifrost_error" in result["error"]
    assert "RuntimeError" in result["error"]


async def test_llm_backend_uses_task_context_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If task.context supplies a model, that one wins over the default."""
    from session_buddy import worker as worker_mod
    from session_buddy.worker import LLMBackend, Task

    captured: dict[str, Any] = {}

    class FakeBifrost:
        async def chat(
            self, prompt: str, *, model: str, **kw: Any
        ) -> dict[str, Any]:
            captured["model"] = model
            return {
                "content": "ok",
                "usage": {},
                "model": model,
                "raw": {},
            }

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(worker_mod, "BifrostClient", lambda **kw: FakeBifrost())

    backend = LLMBackend(model="default-model")
    task = Task(
        task_id="t1",
        prompt="hi",
        context={"model": "override-model", "system": "be terse"},
    )
    await backend.execute("w0", "p1", task)
    assert captured["model"] == "override-model"