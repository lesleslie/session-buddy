"""Tests for session_buddy.llm.providers.gemini_provider (path-mirror).

Path-mirror companion to the higher-level ``tests/unit/test_llm_providers_gemini.py``.
Focuses on branch-level coverage of every public/private method on the
``GeminiProvider`` class. The Google Generative AI SDK is *not* a real
dependency here, so each test installs a stub module into ``sys.modules``.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.llm.models import LLMMessage
from session_buddy.llm.providers.gemini_provider import GeminiProvider


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _StubModel:
    """Replaces ``genai.GenerativeModel`` so tests can observe calls + errors."""

    def __init__(self, name: str, *, with_usage: bool = True, raise_async: bool = False) -> None:
        self.name = name
        self.calls: list[dict] = []
        self.with_usage = with_usage
        self.raise_async = raise_async
        self.stream_chunks: list[SimpleNamespace] = []

    async def generate_content_async(self, content: str, generation_config=None):
        self.calls.append(
            {"method": "generate_content_async", "content": content, "config": generation_config}
        )
        if self.raise_async:
            msg = "simulated API failure"
            raise RuntimeError(msg)
        if self.with_usage:
            return SimpleNamespace(
                text=f"echo:{content}",
                usage_metadata=SimpleNamespace(
                    prompt_token_count=11,
                    candidates_token_count=22,
                    total_token_count=33,
                ),
            )
        return SimpleNamespace(text=f"echo:{content}")

    def generate_content(self, content: str, generation_config=None, stream: bool = False):
        self.calls.append(
            {"method": "generate_content", "content": content, "config": generation_config}
        )
        if self.stream_chunks:
            return iter(self.stream_chunks)
        return iter([SimpleNamespace(text=""), SimpleNamespace(text="part"), SimpleNamespace(text="tail")])

    def start_chat(self, history=None):
        self.calls.append({"method": "start_chat", "history": history})
        chat = SimpleNamespace(name=self.name)
        chat.parent = self

        async def _send_message_async(content, generation_config=None):
            self.calls.append(
                {"method": "send_message_async", "content": content, "config": generation_config}
            )
            return SimpleNamespace(
                text=f"chat:{content}",
                usage_metadata=SimpleNamespace(
                    prompt_token_count=4,
                    candidates_token_count=5,
                    total_token_count=9,
                ),
            )

        def _send_message(content, generation_config=None, stream: bool = False):
            self.calls.append(
                {"method": "send_message", "content": content, "config": generation_config}
            )
            return iter([SimpleNamespace(text="reply "), SimpleNamespace(text="ok")])

        chat.send_message_async = _send_message_async
        chat.send_message = _send_message
        return chat


class _StubGenAI:
    """Module-level replacement for ``google.generativeai``."""

    def __init__(self) -> None:
        self.configure = MagicMock()
        self.configure_args: list[dict] = []
        self.configure.side_effect = lambda **kw: self.configure_args.append(kw)
        self.list_models = lambda: iter(
            [
                SimpleNamespace(name="gemini-pro"),
                SimpleNamespace(name="gemini-1.5-pro"),
                SimpleNamespace(name="gemini-1.5-flash"),
            ]
        )
        self.models = SimpleNamespace(list=self.list_models)
        self.last_model: _StubModel | None = None

    def GenerativeModel(self, name: str) -> _StubModel:
        model = _StubModel(name)
        self.last_model = model
        return model


@pytest.fixture
def stub_genai(monkeypatch: pytest.MonkeyPatch) -> _StubGenAI:
    """Install a fake ``google.generativeai`` module."""
    stub = _StubGenAI()
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []
    genai_module = ModuleType("google.generativeai")
    for attr in dir(stub):
        if not attr.startswith("_"):
            setattr(genai_module, attr, getattr(stub, attr))
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai_module)
    return stub


@pytest.fixture
def provider(stub_genai: _StubGenAI) -> GeminiProvider:
    """Build a provider with a valid API key and default model."""
    return GeminiProvider(
        {
            "api_key": "AIzaSyD-test-key-1234567890abcdef",
            "default_model": "gemini-1.5-pro",
        }
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_pulls_api_key_and_default_model(self) -> None:
        p = GeminiProvider({"api_key": "k", "default_model": "gemini-1.5-flash"})
        assert p.api_key == "k"
        assert p.default_model == "gemini-1.5-flash"

    def test_default_model_fallback(self) -> None:
        p = GeminiProvider({"api_key": "k"})
        assert p.default_model == "gemini-pro"

    def test_missing_api_key(self) -> None:
        p = GeminiProvider({})
        assert p.api_key is None

    def test_logger_uses_class_name(self) -> None:
        p = GeminiProvider({"api_key": "k"})
        # logger name derived from "GeminiProvider" -> "gemini"
        assert p.name == "gemini"
        assert p.logger.name == "llm_providers.gemini"


# ---------------------------------------------------------------------------
# _get_client
# ---------------------------------------------------------------------------


class TestGetClient:
    @pytest.mark.asyncio
    async def test_returns_cached_client(self, provider: GeminiProvider) -> None:
        first = await provider._get_client()
        second = await provider._get_client()
        assert first is second

    @pytest.mark.asyncio
    async def test_calls_genai_configure_with_api_key(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        await provider._get_client()
        assert stub_genai.configure_args
        assert stub_genai.configure_args[0].get("api_key") == provider.api_key

    @pytest.mark.asyncio
    async def test_raises_when_genai_import_fails(
        self, provider: GeminiProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider._client = None
        # Production uses ``importlib.import_module("google.generativeai")``
        # so patch that specific entry point.
        import importlib

        real_import_module = importlib.import_module

        def _fake_import_module(name, package=None):
            if name in ("google.generativeai", "google") or (
                package == "google" and name == "generativeai"
            ):
                msg = "no genai"
                raise ImportError(msg)
            return real_import_module(name, package=package)

        monkeypatch.setattr(importlib, "import_module", _fake_import_module)
        with pytest.raises(ImportError, match="Google Generative AI package not installed"):
            await provider._get_client()


# ---------------------------------------------------------------------------
# _convert_messages
# ---------------------------------------------------------------------------


class TestConvertMessages:
    def test_user_role(self, provider: GeminiProvider) -> None:
        out = provider._convert_messages([LLMMessage(role="user", content="hi")])
        assert out == [{"role": "user", "parts": ["hi"]}]

    def test_assistant_becomes_model(self, provider: GeminiProvider) -> None:
        out = provider._convert_messages([LLMMessage(role="assistant", content="hello")])
        assert out == [{"role": "model", "parts": ["hello"]}]

    def test_system_alone_becomes_user(self, provider: GeminiProvider) -> None:
        out = provider._convert_messages([LLMMessage(role="system", content="Be brief")])
        assert out == [{"role": "user", "parts": ["System: Be brief"]}]

    def test_system_after_user_is_prepended(self, provider: GeminiProvider) -> None:
        out = provider._convert_messages(
            [
                LLMMessage(role="user", content="Question?"),
                LLMMessage(role="system", content="Be brief"),
            ]
        )
        assert len(out) == 1
        assert out[0]["role"] == "user"
        text = out[0]["parts"][0]
        assert "System: Be brief" in text
        assert "Question?" in text

    def test_unknown_role_defaults_to_user(self, provider: GeminiProvider) -> None:
        out = provider._convert_messages([LLMMessage(role="tool", content="result")])
        assert out == [{"role": "user", "parts": ["result"]}]

    def test_mixed_conversation(self, provider: GeminiProvider) -> None:
        # When a system message arrives BEFORE any user message, it becomes
        # its own user entry. The merge-into-user behavior only triggers when
        # system follows an existing user entry.
        messages = [
            LLMMessage(role="system", content="You are a wizard."),
            LLMMessage(role="user", content="Hi"),
            LLMMessage(role="assistant", content="Hello!"),
            LLMMessage(role="user", content="Bye"),
        ]
        out = provider._convert_messages(messages)
        # system-as-user, user, model, user
        assert [entry["role"] for entry in out] == ["user", "user", "model", "user"]
        assert out[0] == {"role": "user", "parts": ["System: You are a wizard."]}
        assert out[1] == {"role": "user", "parts": ["Hi"]}
        assert out[2] == {"role": "model", "parts": ["Hello!"]}
        assert out[3] == {"role": "user", "parts": ["Bye"]}


# ---------------------------------------------------------------------------
# generate (single-message path)
# ---------------------------------------------------------------------------


class TestGenerateSingleMessage:
    @pytest.mark.asyncio
    async def test_returns_llm_response_with_usage(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        response = await provider.generate([LLMMessage(role="user", content="hi")])
        assert response.content == "echo:hi"
        assert response.provider == "gemini"
        assert response.model == "gemini-1.5-pro"
        assert response.usage == {
            "prompt_tokens": 11,
            "completion_tokens": 22,
            "total_tokens": 33,
        }
        assert response.finish_reason == "stop"
        assert response.timestamp

    @pytest.mark.asyncio
    async def test_zero_usage_when_metadata_missing(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        # Replace the last_model to drop usage_metadata
        provider._client = None

        class _NoUsageModel(_StubModel):
            def __init__(self) -> None:  # noqa: D401 - test helper
                super().__init__("gemini-1.5-pro", with_usage=False)

        no_usage = _NoUsageModel()
        sys.modules["google.generativeai"].GenerativeModel = lambda _name: no_usage
        stub_genai.last_model = no_usage
        response = await provider.generate([LLMMessage(role="user", content="hi")])
        assert response.usage == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    @pytest.mark.asyncio
    async def test_uses_explicit_model_argument(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        await provider.generate([LLMMessage(role="user", content="hi")], model="gemini-1.5-flash")
        assert stub_genai.last_model is not None
        assert stub_genai.last_model.name == "gemini-1.5-flash"

    @pytest.mark.asyncio
    async def test_passes_generation_config(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        await provider.generate(
            [LLMMessage(role="user", content="hi")],
            temperature=0.42,
            max_tokens=128,
        )
        call = next(
            c
            for c in stub_genai.last_model.calls
            if c.get("method") == "generate_content_async"
        )
        assert call["config"]["temperature"] == 0.42
        assert call["config"]["max_output_tokens"] == 128

    @pytest.mark.asyncio
    async def test_raises_runtime_when_unavailable(self) -> None:
        p = GeminiProvider({})  # no api_key
        with pytest.raises(RuntimeError, match="Gemini provider not available"):
            await p.generate([LLMMessage(role="user", content="hi")])

    @pytest.mark.asyncio
    async def test_propagates_runtime_error_and_logs(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        class _Boom(_StubModel):
            def __init__(self) -> None:
                super().__init__("gemini-1.5-pro", raise_async=True)

        boom = _Boom()
        sys.modules["google.generativeai"].GenerativeModel = lambda _name: boom
        stub_genai.last_model = boom
        with patch.object(provider.logger, "exception") as log_exc:
            with pytest.raises(RuntimeError, match="simulated API failure"):
                await provider.generate([LLMMessage(role="user", content="hi")])
        assert log_exc.called


# ---------------------------------------------------------------------------
# generate (chat history path: len(messages) > 1)
# ---------------------------------------------------------------------------


class TestGenerateChatHistory:
    @pytest.mark.asyncio
    async def test_uses_start_chat_when_multiple_messages(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        messages = [
            LLMMessage(role="user", content="Hi"),
            LLMMessage(role="assistant", content="Hello!"),
            LLMMessage(role="user", content="How are you?"),
        ]
        response = await provider.generate(messages)
        assert response.content == "chat:How are you?"
        history_call = next(
            c for c in stub_genai.last_model.calls if c.get("method") == "start_chat"
        )
        assert history_call["history"] == [
            {"role": "user", "parts": ["Hi"]},
            {"role": "model", "parts": ["Hello!"]},
        ]
        send_call = next(
            c for c in stub_genai.last_model.calls if c.get("method") == "send_message_async"
        )
        assert send_call["content"] == "How are you?"
        assert send_call["config"]["temperature"] == pytest.approx(0.7)
        assert send_call["config"]["max_output_tokens"] is None

    @pytest.mark.asyncio
    async def test_propagates_chat_send_error(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        class _ChatBoomModel(_StubModel):
            def start_chat(self, history=None):
                chat = SimpleNamespace()
                chat.calls = []

                async def _send(*_a, **_kw):
                    msg = "chat send failure"
                    raise RuntimeError(msg)

                chat.send_message_async = _send
                return chat

        boom = _ChatBoomModel("gemini-1.5-pro")
        sys.modules["google.generativeai"].GenerativeModel = lambda _name: boom
        stub_genai.last_model = boom
        with patch.object(provider.logger, "exception"):
            with pytest.raises(RuntimeError, match="chat send failure"):
                await provider.generate(
                    [
                        LLMMessage(role="user", content="a"),
                        LLMMessage(role="assistant", content="b"),
                        LLMMessage(role="user", content="c"),
                    ]
                )


# ---------------------------------------------------------------------------
# stream_generate
# ---------------------------------------------------------------------------


class TestStreamGenerate:
    @pytest.mark.asyncio
    async def test_streams_single_message(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        chunks = []
        async for chunk in provider.stream_generate([LLMMessage(role="user", content="hi")]):
            chunks.append(chunk)
        assert chunks == ["part", "tail"]

    @pytest.mark.asyncio
    async def test_streams_with_history(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        messages = [
            LLMMessage(role="user", content="hi"),
            LLMMessage(role="assistant", content="hello"),
            LLMMessage(role="user", content="more"),
        ]
        chunks = []
        async for chunk in provider.stream_generate(messages):
            chunks.append(chunk)
        assert chunks == ["reply ", "ok"]
        # Verify history was passed
        history_call = next(
            c for c in stub_genai.last_model.calls if c.get("method") == "start_chat"
        )
        assert history_call["history"] == [
            {"role": "user", "parts": ["hi"]},
            {"role": "model", "parts": ["hello"]},
        ]
        # send_message was used (sync, not async) and stream=True was passed
        send_call = next(
            c for c in stub_genai.last_model.calls if c.get("method") == "send_message"
        )
        assert send_call["content"] == "more"

    @pytest.mark.asyncio
    async def test_raises_when_unavailable(self) -> None:
        p = GeminiProvider({})
        with pytest.raises(RuntimeError, match="Gemini provider not available"):

            async def _collect() -> None:
                async for _ in p.stream_generate([LLMMessage(role="user", content="hi")]):
                    pass

            await _collect()

    @pytest.mark.asyncio
    async def test_skips_empty_chunks(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        class _EmptyChunksModel(_StubModel):
            def __init__(self) -> None:
                super().__init__("gemini-1.5-pro")
                self.stream_chunks = [
                    SimpleNamespace(text=""),
                    SimpleNamespace(text=""),
                    SimpleNamespace(text="only-this"),
                    SimpleNamespace(text=None),
                ]

        empty = _EmptyChunksModel()
        sys.modules["google.generativeai"].GenerativeModel = lambda _name: empty
        stub_genai.last_model = empty
        chunks = []
        async for chunk in provider.stream_generate([LLMMessage(role="user", content="hi")]):
            chunks.append(chunk)
        assert chunks == ["only-this"]

    @pytest.mark.asyncio
    async def test_propagates_streaming_error(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        class _Boom(_StubModel):
            def generate_content(self, content, generation_config=None, stream: bool = False):
                msg = "stream error"
                raise RuntimeError(msg)

        boom = _Boom("gemini-1.5-pro")
        sys.modules["google.generativeai"].GenerativeModel = lambda _name: boom
        stub_genai.last_model = boom
        with patch.object(provider.logger, "exception"):
            with pytest.raises(RuntimeError, match="stream error"):

                async def _collect() -> None:
                    async for _ in provider.stream_generate(
                        [LLMMessage(role="user", content="hi")]
                    ):
                        pass

                await _collect()


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_false_when_api_key_missing(self) -> None:
        p = GeminiProvider({})
        assert await p.is_available() is False

    @pytest.mark.asyncio
    async def test_true_when_list_models_succeeds(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        assert await provider.is_available() is True
        assert stub_genai.configure_args, "configure should have been called"

    @pytest.mark.asyncio
    async def test_false_when_list_models_raises(
        self, provider: GeminiProvider, stub_genai: _StubGenAI
    ) -> None:
        def _boom() -> None:
            msg = "auth fail"
            raise RuntimeError(msg)

        sys.modules["google.generativeai"].list_models = _boom
        assert await provider.is_available() is False


# ---------------------------------------------------------------------------
# get_models
# ---------------------------------------------------------------------------


class TestGetModels:
    def test_returns_known_models(self, provider: GeminiProvider) -> None:
        models = provider.get_models()
        assert models == [
            "gemini-pro",
            "gemini-pro-vision",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.0-pro",
        ]

    def test_models_list_not_empty(self) -> None:
        p = GeminiProvider({})
        assert len(p.get_models()) >= 1
