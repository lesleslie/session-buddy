"""Tests for session_buddy.llm.providers.openai_provider.

Phase 3 coverage push. The OpenAI provider uses the official
``openai.AsyncOpenAI`` client. Tests mock the client directly.
"""

from __future__ import annotations

import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.llm.models import LLMMessage
from session_buddy.llm.providers.openai_provider import OpenAIProvider


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def provider() -> OpenAIProvider:
    return OpenAIProvider(
        {
            "api_key": "sk-" + "a" * 48,
            "default_model": "gpt-4",
            "base_url": "https://api.openai.com/v1",
        }
    )


def _openai_response(
    text: str = "Hello!",
    prompt_tokens: int = 4,
    completion_tokens: int = 6,
    finish_reason: str = "stop",
    response_id: str = "chatcmpl-123",
) -> SimpleNamespace:
    """Build a mock openai chat.completions response."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(
        message=message, finish_reason=finish_reason, delta=SimpleNamespace(content=None)
    )
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(
        id=response_id,
        choices=[choice],
        usage=usage,
    )


class _AsyncStream:
    """Async iterator stand-in for the openai SDK's AsyncStream.

    Production code does
        response = await client.chat.completions.create(..., stream=True)
        async for chunk in response: ...
    so the mock must support both ``await`` (via the wrapping async
    ``_create``) and async iteration. A bare async generator is NOT
    awaitable, which is the typical gotcha.
    """

    def __init__(self, chunks: list[object]) -> None:
        self._chunks = iter(chunks)

    def __aiter__(self) -> _AsyncStream:
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


# =============================================================================
# Init
# =============================================================================


class TestOpenAIInit:
    def test_default_base_url(self) -> None:
        p = OpenAIProvider({"api_key": "sk-x"})
        assert p.base_url == "https://api.openai.com/v1"

    def test_custom_base_url(self) -> None:
        p = OpenAIProvider({"api_key": "sk-x", "base_url": "https://proxy.example/v1"})
        assert p.base_url == "https://proxy.example/v1"

    def test_default_model(self) -> None:
        p = OpenAIProvider({"api_key": "sk-x"})
        assert p.default_model == "gpt-4"

    def test_custom_model(self) -> None:
        p = OpenAIProvider({"api_key": "sk-x", "default_model": "gpt-4o-mini"})
        assert p.default_model == "gpt-4o-mini"


# =============================================================================
# _get_client
# =============================================================================


class TestGetClient:
    @pytest.mark.asyncio
    async def test_returns_cached_client(self, provider: OpenAIProvider) -> None:
        fake = MagicMock()
        with patch("openai.AsyncOpenAI", return_value=fake) as ctor:
            c1 = await provider._get_client()
            c2 = await provider._get_client()
        assert c1 is c2
        assert ctor.call_count == 1

    @pytest.mark.asyncio
    async def test_uses_api_key_and_base_url(self, provider: OpenAIProvider) -> None:
        with patch("openai.AsyncOpenAI") as ctor:
            await provider._get_client()
        kwargs = ctor.call_args.kwargs
        assert kwargs["api_key"] == provider.api_key
        assert kwargs["base_url"] == provider.base_url

    @pytest.mark.asyncio
    async def test_raises_when_openai_missing(
        self, provider: OpenAIProvider
    ) -> None:
        provider._client = None
        # Make the openai import fail
        import builtins

        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("openai not installed")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=_fake_import):
            with pytest.raises(ImportError, match="OpenAI package not installed"):
                await provider._get_client()


# =============================================================================
# _convert_messages
# =============================================================================


class TestConvertMessages:
    def test_basic(self, provider: OpenAIProvider) -> None:
        msgs = [
            LLMMessage(role="system", content="Be brief"),
            LLMMessage(role="user", content="hi"),
        ]
        out = provider._convert_messages(msgs)
        assert out == [
            {"role": "system", "content": "Be brief"},
            {"role": "user", "content": "hi"},
        ]


# =============================================================================
# generate
# =============================================================================


class TestGenerate:
    @pytest.mark.asyncio
    async def test_successful_generation(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_openai_response(text="Hi back", prompt_tokens=3, completion_tokens=2)
        )

        # is_available() awaits client.models.list() which fails on a plain
        # MagicMock; stub it out so the request path under test is exercised.
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            response = await provider.generate([LLMMessage(role="user", content="Hello")])

        assert response.content == "Hi back"
        assert response.provider == "openai"
        assert response.model == "gpt-4"
        assert response.usage["prompt_tokens"] == 3
        assert response.usage["completion_tokens"] == 2
        assert response.usage["total_tokens"] == 5
        assert response.finish_reason == "stop"
        assert response.metadata["response_id"] == "chatcmpl-123"
        datetime.fromisoformat(response.timestamp)

    @pytest.mark.asyncio
    async def test_uses_explicit_model(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_openai_response()
        )
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            await provider.generate(
                [LLMMessage(role="user", content="hi")], model="gpt-3.5-turbo"
            )
        kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_passes_temperature_and_max_tokens(
        self, provider: OpenAIProvider
    ) -> None:
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_openai_response()
        )
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            await provider.generate(
                [LLMMessage(role="user", content="hi")],
                temperature=0.1,
                max_tokens=256,
            )
        kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.1
        assert kwargs["max_tokens"] == 256

    @pytest.mark.asyncio
    async def test_extra_kwargs_forwarded(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_openai_response()
        )
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            await provider.generate(
                [LLMMessage(role="user", content="hi")],
                top_p=0.9,
                frequency_penalty=0.5,
            )
        kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert kwargs["top_p"] == 0.9
        assert kwargs["frequency_penalty"] == 0.5

    @pytest.mark.asyncio
    async def test_handles_missing_usage(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()
        # No usage attribute
        choice = SimpleNamespace(message=SimpleNamespace(content="hi"), finish_reason="stop")
        provider._client.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(id="x", choices=[choice], usage=None)
        )
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            response = await provider.generate([LLMMessage(role="user", content="hi")])
        assert response.usage == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    @pytest.mark.asyncio
    async def test_raises_when_unavailable(self) -> None:
        p = OpenAIProvider({})  # no api_key
        with pytest.raises(RuntimeError, match="OpenAI provider not available"):
            await p.generate([LLMMessage(role="user", content="hi")])

    @pytest.mark.asyncio
    async def test_propagates_api_error(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("rate limit")
        )
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            with pytest.raises(RuntimeError, match="rate limit"):
                await provider.generate([LLMMessage(role="user", content="hi")])

    @pytest.mark.asyncio
    async def test_preserves_finish_reason(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_openai_response(finish_reason="length")
        )
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            response = await provider.generate([LLMMessage(role="user", content="hi")])
        assert response.finish_reason == "length"


# =============================================================================
# stream_generate
# =============================================================================


class TestStreamGenerate:
    @pytest.mark.asyncio
    async def test_streams_chunks(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()

        chunks = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=content),
                        finish_reason=None,
                    )
                ]
            )
            for content in ["part ", "of ", "stream"]
        ]

        async def _create(**_kwargs):
            return _AsyncStream(chunks)

        provider._client.chat.completions.create = _create
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            out = []
            async for c in provider.stream_generate(
                [LLMMessage(role="user", content="hi")]
            ):
                out.append(c)
        assert out == ["part ", "of ", "stream"]

    @pytest.mark.asyncio
    async def test_skips_empty_delta_content(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()

        chunks = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=content),
                        finish_reason=None,
                    )
                ]
            )
            for content in ["a", None, "", "b"]
        ]

        async def _create(**_kwargs):
            return _AsyncStream(chunks)

        provider._client.chat.completions.create = _create
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            out = []
            async for c in provider.stream_generate(
                [LLMMessage(role="user", content="hi")]
            ):
                out.append(c)
        # None and empty are skipped
        assert out == ["a", "b"]

    @pytest.mark.asyncio
    async def test_raises_when_unavailable(self) -> None:
        p = OpenAIProvider({})
        with pytest.raises(RuntimeError, match="OpenAI provider not available"):
            async for _ in p.stream_generate([LLMMessage(role="user", content="hi")]):
                pass

    @pytest.mark.asyncio
    async def test_propagates_api_error(self, provider: OpenAIProvider) -> None:
        provider._client = MagicMock()

        async def _create(**_kwargs):
            raise RuntimeError("api error")

        provider._client.chat.completions.create = _create
        with patch.object(
            OpenAIProvider, "is_available", AsyncMock(return_value=True)
        ):
            with pytest.raises(RuntimeError, match="api error"):
                async for _ in provider.stream_generate(
                    [LLMMessage(role="user", content="hi")]
                ):
                    pass


# =============================================================================
# is_available
# =============================================================================


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_false_without_api_key(self) -> None:
        p = OpenAIProvider({})
        assert await p.is_available() is False

    @pytest.mark.asyncio
    async def test_true_when_models_list_succeeds(
        self, provider: OpenAIProvider
    ) -> None:
        provider._client = MagicMock()
        provider._client.models.list = AsyncMock(return_value=SimpleNamespace(data=[]))
        assert await provider.is_available() is True

    @pytest.mark.asyncio
    async def test_false_when_models_list_raises(
        self, provider: OpenAIProvider
    ) -> None:
        provider._client = MagicMock()
        provider._client.models.list = AsyncMock(side_effect=RuntimeError("auth fail"))
        assert await provider.is_available() is False


# =============================================================================
# get_models
# =============================================================================


class TestGetModels:
    def test_returns_known_models(self, provider: OpenAIProvider) -> None:
        models = provider.get_models()
        assert "gpt-4" in models
        assert "gpt-4o" in models
        assert "gpt-3.5-turbo" in models
