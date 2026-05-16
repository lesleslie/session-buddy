"""Integration tests for LLMManager FallbackChain routing.

Validates the three-tier fallback: MiniMax (primary) → llama-server → Ollama.
Exercises the real LLMManager routing logic end-to-end with mocked FallbackChain.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.llm.models import LLMMessage, LLMResponse
from session_buddy.llm_providers import LLMManager


# ============================================================================
# Helpers
# ============================================================================


def _make_provider(name: str, available: bool = True) -> MagicMock:
    p = MagicMock()
    p.name = name
    p._config = MagicMock()
    p._config.base_url = f"http://{name}.local"
    p._config.require_auth = name == "minimax"
    p._config.task_routing = {"chat": f"{name}-default"}
    p.health_check = AsyncMock(return_value=available)
    p.execute = AsyncMock(
        return_value={
            "content": f"response from {name}",
            "provider": name,
            "model": f"{name}-default",
            "usage": {},
        }
    )
    return p


def _make_chain(
    providers: list[str] | None = None,
    execute_result: dict | None = None,
    execute_error: Exception | None = None,
) -> MagicMock:
    names = providers or ["minimax", "llama_server", "ollama"]
    chain = MagicMock()
    chain._providers = [_make_provider(n) for n in names]
    if execute_error:
        chain.execute = AsyncMock(side_effect=execute_error)
    else:
        chain.execute = AsyncMock(
            return_value=execute_result
            or {
                "content": "OK",
                "provider": names[0],
                "model": "MiniMax-M2.7",
                "usage": {},
            }
        )
    return chain


@pytest.fixture
def messages():
    return [LLMMessage(role="user", content="Hello, respond with just OK")]


# ============================================================================
# Test: Default provider is MiniMax
# ============================================================================


class TestDefaultProviderIsMiniMax:
    def test_fallback_chain_order(self):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        providers = manager.list_providers()
        assert providers[0] == "minimax"

    def test_fallback_chain_includes_llama_server(self):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        assert "llama_server" in manager.list_providers()

    def test_fallback_chain_includes_ollama(self):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        assert "ollama" in manager.list_providers()

    def test_minimax_config_base_url(self):
        """Verify _build_chain passes the correct minimax base URL to LLMSettings."""
        with patch("session_buddy.llm_providers.FallbackChain.from_settings") as mock_fs:
            mock_fs.return_value = _make_chain()
            LLMManager()
            llm_settings_arg = mock_fs.call_args[0][0]
        minimax_raw = llm_settings_arg.providers.get("minimax", {})
        assert "minimax.io" in minimax_raw.get("base_url", "")

    def test_llama_server_url_from_env(self):
        """LLAMA_SERVER_URL env var is picked up by _build_chain."""
        chain = _make_chain()
        with (
            patch.dict(os.environ, {"LLAMA_SERVER_URL": "http://myserver:9000"}),
            patch("session_buddy.llm_providers.FallbackChain.from_settings") as mock_fs,
        ):
            mock_fs.return_value = chain
            LLMManager()
            llm_settings_arg = mock_fs.call_args[0][0]
        llama_raw = llm_settings_arg.providers.get("llama_server", {})
        assert llama_raw.get("base_url") == "http://myserver:9000"

    def test_ollama_url_from_env(self):
        """OLLAMA_BASE_URL env var is picked up by _build_chain."""
        chain = _make_chain()
        with (
            patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://mymac:11434/v1"}),
            patch("session_buddy.llm_providers.FallbackChain.from_settings") as mock_fs,
        ):
            mock_fs.return_value = chain
            LLMManager()
            settings_arg = mock_fs.call_args[0][0]
        assert settings_arg.providers["ollama"]["base_url"] == "http://mymac:11434/v1"


# ============================================================================
# Test: Generation delegates to chain
# ============================================================================


class TestGenerationDelegatesToChain:
    @pytest.mark.asyncio
    async def test_generate_calls_chain_execute(self, messages):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        await manager.generate(messages)
        chain.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_returns_llm_response(self, messages):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        response = await manager.generate(messages)
        assert isinstance(response, LLMResponse)
        assert response.content == "OK"
        assert response.provider == "minimax"

    @pytest.mark.asyncio
    async def test_generate_includes_task_type_in_task(self, messages):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        await manager.generate(messages, task_type="code_generation")
        call_task = chain.execute.call_args[0][0]
        assert call_task["task_type"] == "code_generation"

    @pytest.mark.asyncio
    async def test_generate_text_wraps_result(self):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        result = await manager.generate_text("ping")
        assert result["success"] is True
        assert result["content"] == "OK"


# ============================================================================
# Test: Fallback behavior when chain exhausted
# ============================================================================


class TestFallbackBehavior:
    @pytest.mark.asyncio
    async def test_all_providers_fail_raises(self, messages):
        chain = _make_chain(execute_error=RuntimeError("all failed"))
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        with pytest.raises(RuntimeError, match="No available LLM providers"):
            await manager.generate(messages)

    @pytest.mark.asyncio
    async def test_generate_text_returns_error_dict_on_failure(self):
        chain = _make_chain(execute_error=RuntimeError("network error"))
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        result = await manager.generate_text("ping")
        assert result["success"] is False
        assert "network error" in result["error"] or result["error"] != ""

    @pytest.mark.asyncio
    async def test_chat_returns_error_dict_on_failure(self):
        chain = _make_chain(execute_error=RuntimeError("down"))
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        result = await manager.chat([{"role": "user", "content": "hi"}])
        assert result["success"] is False


# ============================================================================
# Test: Available providers health check
# ============================================================================


class TestAvailableProviders:
    @pytest.mark.asyncio
    async def test_healthy_providers_returned(self):
        chain = _make_chain()
        chain._providers[1].health_check = AsyncMock(return_value=False)
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        available = await manager.get_available_providers()
        assert "minimax" in available
        assert "llama_server" not in available
        assert "ollama" in available

    @pytest.mark.asyncio
    async def test_no_providers_available(self):
        chain = _make_chain()
        for p in chain._providers:
            p.health_check = AsyncMock(return_value=False)
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        available = await manager.get_available_providers()
        assert available == []


# ============================================================================
# Test: Provider info
# ============================================================================


class TestProviderInfo:
    def test_provider_info_has_fallback_chain(self):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        info = manager.get_provider_info()
        assert info["fallback_chain"] == ["minimax", "llama_server", "ollama"]

    def test_provider_info_has_all_providers(self):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        info = manager.get_provider_info()
        assert "minimax" in info["providers"]
        assert "llama_server" in info["providers"]
        assert "ollama" in info["providers"]

    def test_provider_info_does_not_expose_api_keys(self):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        info = manager.get_provider_info()
        for _name, pinfo in info["providers"].items():
            for field_name in pinfo:
                assert "key" not in field_name.lower(), f"Exposed key field: {field_name}"
            url = pinfo.get("base_url", "")
            assert "@" not in url, f"URL may contain embedded credentials: {url}"


# ============================================================================
# Test: Streaming (non-streaming fallback)
# ============================================================================


class TestStreaming:
    @pytest.mark.asyncio
    async def test_stream_generate_yields_content(self, messages):
        chain = _make_chain()
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        chunks = []
        async for chunk in manager.stream_generate(messages):
            chunks.append(chunk)
        assert chunks == ["OK"]

    @pytest.mark.asyncio
    async def test_stream_generate_raises_on_chain_failure(self, messages):
        chain = _make_chain(execute_error=RuntimeError("network down"))
        with patch("session_buddy.llm_providers.FallbackChain.from_settings", return_value=chain):
            manager = LLMManager()
        with pytest.raises(RuntimeError, match="No available LLM providers"):
            async for _ in manager.stream_generate(messages):
                pass
