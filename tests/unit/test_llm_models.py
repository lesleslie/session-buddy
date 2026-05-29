from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def test_stream_generation_options_are_immutable() -> None:
    from session_buddy.llm.models import StreamGenerationOptions

    options = StreamGenerationOptions(provider="openai", model="gpt-4o")

    assert options.provider == "openai"
    assert options.use_fallback is True
    assert options.temperature == 0.7

    with pytest.raises(FrozenInstanceError):
        options.provider = "anthropic"  # type: ignore[misc]


def test_stream_chunk_and_message_and_response_defaults() -> None:
    from session_buddy.llm.models import (
        LLMMessage,
        LLMResponse,
        StreamChunk,
    )

    content = StreamChunk.content_chunk("hello", provider="openai")
    error = StreamChunk.error_chunk("boom")
    message = LLMMessage(role="user", content="hi")
    preset_message = LLMMessage(
        role="assistant",
        content="hello",
        timestamp="2026-01-01T10:00:00",
        metadata={"source": "test"},
    )
    response = LLMResponse(
        content="ok",
        model="gpt",
        provider="openai",
        usage={"prompt_tokens": 1},
        finish_reason="stop",
        timestamp="2026-01-01T10:00:00",
    )

    assert content.content == "hello"
    assert content.provider == "openai"
    assert error.is_error is True
    assert error.metadata == {"error": "boom"}
    assert message.timestamp is not None
    assert message.metadata == {}
    assert preset_message.timestamp == "2026-01-01T10:00:00"
    assert preset_message.metadata == {"source": "test"}
    assert response.metadata == {}

