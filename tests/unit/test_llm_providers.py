"""Tests for LLMManager with FallbackChain-based implementation."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.llm.models import LLMMessage, LLMResponse
from session_buddy.llm_providers import LLMManager


def _make_mock_provider(name: str, available: bool = True) -> MagicMock:
    provider = MagicMock()
    provider.name = name
    provider._config = MagicMock()
    provider._config.base_url = f"http://{name}.local"
    provider._config.require_auth = name == "minimax"
    provider._config.task_routing = {"chat": f"{name}-model"}
    provider.health_check = AsyncMock(return_value=available)
    provider.execute = AsyncMock(
        return_value={"content": "pong", "provider": name, "model": f"{name}-model", "usage": {}}
    )
    return provider


def _make_mock_chain(
    providers: list[str] | None = None,
    execute_result: dict | None = None,
) -> MagicMock:
    names = providers or ["minimax", "llama_server", "ollama"]
    chain = MagicMock()
    chain._providers = [_make_mock_provider(n) for n in names]
    chain.execute = AsyncMock(
        return_value=execute_result
        or {
            "content": "OK",
            "provider": names[0],
            "model": f"{names[0]}-model",
            "usage": {},
        }
    )
    return chain


@pytest.fixture
def mock_chain():
    return _make_mock_chain()


@pytest.fixture
def llm_manager(mock_chain):
    with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain):
        return LLMManager()


class TestLLMManagerInitialization:
    def test_builds_chain_on_init(self, mock_chain):
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain) as mock_fs:
            manager = LLMManager()
            mock_fs.assert_called_once()
            assert manager._chain is mock_chain

    def test_list_providers_returns_chain_names(self, llm_manager):
        providers = llm_manager.list_providers()
        assert providers == ["minimax", "llama_server", "ollama"]

    def test_is_valid_provider_true(self, llm_manager):
        assert llm_manager._is_valid_provider("minimax") is True

    def test_is_valid_provider_false(self, llm_manager):
        assert llm_manager._is_valid_provider("unknown") is False


class TestGetAvailableProviders:
    @pytest.mark.asyncio
    async def test_returns_healthy_providers(self, mock_chain):
        mock_chain._providers[0].health_check = AsyncMock(return_value=True)
        mock_chain._providers[1].health_check = AsyncMock(return_value=False)
        mock_chain._providers[2].health_check = AsyncMock(return_value=True)
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain):
            manager = LLMManager()
        available = await manager.get_available_providers()
        assert available == ["minimax", "ollama"]

    @pytest.mark.asyncio
    async def test_excludes_providers_that_raise(self, mock_chain):
        mock_chain._providers[0].health_check = AsyncMock(side_effect=RuntimeError("down"))
        mock_chain._providers[1].health_check = AsyncMock(return_value=True)
        mock_chain._providers[2].health_check = AsyncMock(return_value=True)
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain):
            manager = LLMManager()
        available = await manager.get_available_providers()
        assert "minimax" not in available
        assert "llama_server" in available


class TestGenerate:
    @pytest.mark.asyncio
    async def test_returns_llm_response(self, llm_manager, mock_chain):
        messages = [LLMMessage(role="user", content="hello")]
        response = await llm_manager.generate(messages)
        assert isinstance(response, LLMResponse)
        assert response.content == "OK"
        assert response.provider == "minimax"

    @pytest.mark.asyncio
    async def test_passes_task_type(self, llm_manager, mock_chain):
        messages = [LLMMessage(role="user", content="hello")]
        await llm_manager.generate(messages, task_type="code_generation")
        call_task = mock_chain.execute.call_args[0][0]
        assert call_task["task_type"] == "code_generation"

    @pytest.mark.asyncio
    async def test_passes_model_when_given(self, llm_manager, mock_chain):
        messages = [LLMMessage(role="user", content="hello")]
        await llm_manager.generate(messages, model="MiniMax-M2.7")
        call_task = mock_chain.execute.call_args[0][0]
        assert call_task["model"] == "MiniMax-M2.7"

    @pytest.mark.asyncio
    async def test_passes_max_tokens_when_given(self, llm_manager, mock_chain):
        messages = [LLMMessage(role="user", content="hello")]
        await llm_manager.generate(messages, max_tokens=512)
        call_task = mock_chain.execute.call_args[0][0]
        assert call_task["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_chain_failure(self, mock_chain):
        mock_chain.execute = AsyncMock(side_effect=RuntimeError("all failed"))
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain):
            manager = LLMManager()
        messages = [LLMMessage(role="user", content="hi")]
        with pytest.raises(RuntimeError, match="No available LLM providers"):
            await manager.generate(messages)

    @pytest.mark.asyncio
    async def test_provider_param_is_accepted(self, llm_manager):
        """provider param is accepted for compat but ignored."""
        messages = [LLMMessage(role="user", content="hi")]
        response = await llm_manager.generate(messages, provider="ollama")
        assert isinstance(response, LLMResponse)


class TestGenerateText:
    @pytest.mark.asyncio
    async def test_success_returns_dict(self, llm_manager):
        result = await llm_manager.generate_text("ping")
        assert result["success"] is True
        assert result["content"] == "OK"
        assert result["provider"] == "minimax"

    @pytest.mark.asyncio
    async def test_failure_returns_error_dict(self, mock_chain):
        mock_chain.execute = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain):
            manager = LLMManager()
        result = await manager.generate_text("ping")
        assert result["success"] is False
        assert result["error"] != ""


class TestChat:
    @pytest.mark.asyncio
    async def test_success_returns_dict(self, llm_manager):
        messages = [{"role": "user", "content": "hello"}]
        result = await llm_manager.chat(messages)
        assert result["success"] is True
        assert result["content"] == "OK"

    @pytest.mark.asyncio
    async def test_failure_returns_error_dict(self, mock_chain):
        mock_chain.execute = AsyncMock(side_effect=RuntimeError("down"))
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain):
            manager = LLMManager()
        result = await manager.chat([{"role": "user", "content": "hi"}])
        assert result["success"] is False


class TestStreamGenerate:
    @pytest.mark.asyncio
    async def test_yields_content_as_single_chunk(self, llm_manager):
        messages = [LLMMessage(role="user", content="hi")]
        chunks = []
        async for chunk in llm_manager.stream_generate(messages):
            chunks.append(chunk)
        assert chunks == ["OK"]

    @pytest.mark.asyncio
    async def test_raises_when_chain_fails(self, mock_chain):
        mock_chain.execute = AsyncMock(side_effect=RuntimeError("down"))
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain):
            manager = LLMManager()
        messages = [LLMMessage(role="user", content="hi")]
        with pytest.raises(RuntimeError, match="No available LLM providers"):
            async for _ in manager.stream_generate(messages):
                pass


class TestTestAllProviders:
    @pytest.mark.asyncio
    async def test_reports_success_per_provider(self, llm_manager, mock_chain):
        results = await llm_manager.test_all_providers()
        assert "minimax" in results
        assert results["minimax"]["success"] is True

    @pytest.mark.asyncio
    async def test_reports_failure_when_provider_raises(self, mock_chain):
        mock_chain._providers[0].execute = AsyncMock(side_effect=RuntimeError("error"))
        mock_chain._providers[1].execute = AsyncMock(
            return_value={"content": "ok", "provider": "llama_server", "model": "qwen3.5", "usage": {}}
        )
        mock_chain._providers[2].execute = AsyncMock(
            return_value={"content": "ok", "provider": "ollama", "model": "qwen2.5-coder:7b", "usage": {}}
        )
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=mock_chain):
            manager = LLMManager()
        results = await manager.test_all_providers()
        assert results["minimax"]["success"] is False
        assert results["llama_server"]["success"] is True


class TestGetProviderInfo:
    def test_returns_fallback_chain_and_providers(self, llm_manager):
        info = llm_manager.get_provider_info()
        assert "fallback_chain" in info
        assert "providers" in info
        assert info["fallback_chain"] == ["minimax", "llama_server", "ollama"]

    def test_provider_info_does_not_expose_api_keys(self, llm_manager):
        info = llm_manager.get_provider_info()
        for _name, pinfo in info["providers"].items():
            for key in pinfo:
                assert "key" not in key.lower(), f"Key field exposed: {key}"
