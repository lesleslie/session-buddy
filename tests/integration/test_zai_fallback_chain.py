#!/usr/bin/env python3
"""Integration tests for ZAI fallback chain.

Validates the Phase 6 LLM provider reconfiguration:
- ZAI as primary cloud provider (OpenAI-compatible API)
- Ollama as local fallback
- Correct fallback behavior when ZAI is unavailable
- Free tier model fallback (glm-4.7-flash)
- Provider configuration and initialization

These tests mock external API calls but exercise the real LLMManager
routing and fallback logic end-to-end.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.llm import LLMMessage, LLMResponse
from session_buddy.llm_providers import LLMManager


# ============================================================================
# Fixtures
# ============================================================================

_TS = "2026-04-13T12:00:00Z"


def _make_mock_provider(
    name: str,
    available: bool = True,
    generate_content: str = "OK",
    generate_model: str = "glm-4.7",
) -> AsyncMock:
    """Create a mock LLM provider instance."""
    provider = AsyncMock()
    provider.is_available.return_value = available
    provider.generate.return_value = LLMResponse(
        content=generate_content,
        model=generate_model,
        provider=name,
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        finish_reason="stop",
        timestamp=_TS,
    )

    async def _stream(*args, **kwargs):
        """Default no-op async generator for streaming."""
        return
        yield  # noqa: unreachable — makes this an async generator

    provider.stream_generate = _stream
    provider.config = {"base_url": f"https://{name}.example.com", "default_model": generate_model}
    provider.get_models.return_value = [generate_model]
    return provider


@pytest.fixture
def mock_provider_classes():
    """Patch all provider classes so LLMManager can be created without real deps."""
    mock_anthropic_module = MagicMock()
    mock_anthropic_cls = MagicMock()
    mock_anthropic_module.AnthropicProvider = mock_anthropic_cls
    mock_anthropic_cls.return_value = _make_mock_provider("anthropic")

    with (
        patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai_cls,
        patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini_cls,
        patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama_cls,
        patch("builtins.__import__", side_effect=lambda *a, _orig=__import__, **kw: (
            mock_anthropic_module
            if a and "anthropic_provider" in str(a)
            else _orig(*a, **kw)
        )),
    ):
        # Default: all providers available
        mock_openai_cls.return_value = _make_mock_provider("zai")
        mock_gemini_cls.return_value = _make_mock_provider("gemini")
        mock_ollama_cls.return_value = _make_mock_provider("ollama")

        yield {
            "openai_cls": mock_openai_cls,
            "gemini_cls": mock_gemini_cls,
            "ollama_cls": mock_ollama_cls,
            "anthropic_cls": mock_anthropic_cls,
        }


@pytest.fixture
def llm_manager(mock_provider_classes):
    """Create an LLMManager with all providers mocked."""
    return LLMManager()


@pytest.fixture
def messages():
    """Standard test messages."""
    return [LLMMessage(role="user", content="Hello, respond with just OK")]


# ============================================================================
# Test: ZAI as Default Provider
# ============================================================================


class TestZAIAsDefaultProvider:
    """Verify ZAI is configured as the primary/default LLM provider."""

    def test_default_provider_is_zai(self, mock_provider_classes):
        """LLMManager should default to ZAI provider."""
        manager = LLMManager()
        assert manager.config["default_provider"] == "zai"

    def test_fallback_providers_include_ollama(self, mock_provider_classes):
        """Fallback chain should include Ollama."""
        manager = LLMManager()
        assert "ollama" in manager.config.get("fallback_providers", [])

    def test_zai_provider_initialized(self, mock_provider_classes):
        """ZAI provider should be initialized in the manager."""
        manager = LLMManager()
        assert "zai" in manager.providers

    def test_zai_uses_openai_provider_class(self, mock_provider_classes):
        """ZAI should use OpenAIProvider (OpenAI-compatible API)."""
        manager = LLMManager()
        # OpenAIProvider is used for both zai and openai providers
        assert "zai" in manager.providers
        assert "openai" in manager.providers

    def test_zai_config_has_correct_base_url(self, mock_provider_classes):
        """ZAI config should use the coding plan endpoint."""
        manager = LLMManager()
        zai_config = manager.config["providers"].get("zai", {})
        assert "api.z.ai" in zai_config.get("base_url", "")

    def test_zai_config_has_glm_default_model(self, mock_provider_classes):
        """ZAI config should default to a GLM model."""
        manager = LLMManager()
        zai_config = manager.config["providers"].get("zai", {})
        model = zai_config.get("default_model", "")
        assert "glm" in model.lower()


# ============================================================================
# Test: Primary Provider Generation
# ============================================================================


class TestPrimaryProviderGeneration:
    """Verify generation uses ZAI as primary by default."""

    @pytest.mark.asyncio
    async def test_generate_uses_zai_by_default(self, llm_manager, messages):
        """generate() should use ZAI provider without explicit provider arg."""
        response = await llm_manager.generate(messages)

        assert response is not None
        assert response.content == "OK"
        # Verify primary provider was used
        zai_provider = llm_manager.providers["zai"]
        zai_provider.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_explicit_zai_provider(self, llm_manager, messages):
        """generate() should use ZAI when explicitly specified."""
        response = await llm_manager.generate(messages, provider="zai")

        assert response is not None
        zai_provider = llm_manager.providers["zai"]
        zai_provider.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_explicit_ollama_provider(self, llm_manager, messages):
        """generate() should use Ollama when explicitly specified."""
        response = await llm_manager.generate(messages, provider="ollama")

        assert response is not None
        ollama_provider = llm_manager.providers["ollama"]
        ollama_provider.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_explicit_model(self, llm_manager, messages):
        """generate() should pass model parameter to provider."""
        response = await llm_manager.generate(messages, model="glm-4.5-air")

        assert response is not None
        zai_provider = llm_manager.providers["zai"]
        zai_provider.generate.assert_called_once_with(
            messages, "glm-4.5-air",
        )


# ============================================================================
# Test: Fallback Chain Validation
# ============================================================================


class TestFallbackChainValidation:
    """Verify fallback behavior when ZAI is unavailable."""

    @pytest.mark.asyncio
    async def test_fallback_to_ollama_when_zai_unavailable(self, messages):
        """Should fall back to Ollama when ZAI is unavailable."""
        with (
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai_cls,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini_cls,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama_cls,
        ):
            # ZAI (OpenAI-based) is unavailable
            mock_zai = _make_mock_provider("zai", available=False)
            mock_openai_cls.return_value = mock_zai

            # Ollama is available
            mock_ollama = _make_mock_provider(
                "ollama",
                available=True,
                generate_content="Ollama response",
                generate_model="qwen2.5-coder:7b",
            )
            mock_ollama_cls.return_value = mock_ollama

            mock_gemini_cls.return_value = _make_mock_provider("gemini")

            manager = LLMManager()
            response = await manager.generate(messages, use_fallback=True)

            assert response is not None
            assert response.content == "Ollama response"
            assert response.provider == "ollama"

    @pytest.mark.asyncio
    async def test_fallback_to_ollama_on_zai_error(self, messages):
        """Should fall back to Ollama when ZAI raises an error."""
        with (
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai_cls,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini_cls,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama_cls,
        ):
            # ZAI is available but raises on generate
            mock_zai = _make_mock_provider("zai", available=True)
            mock_zai.generate.side_effect = RuntimeError("ZAI API timeout")
            mock_openai_cls.return_value = mock_zai

            # Ollama is available and works
            mock_ollama = _make_mock_provider(
                "ollama",
                available=True,
                generate_content="Fallback response",
            )
            mock_ollama_cls.return_value = mock_ollama

            mock_gemini_cls.return_value = _make_mock_provider("gemini")

            manager = LLMManager()
            response = await manager.generate(messages, use_fallback=True)

            assert response is not None
            assert response.content == "Fallback response"

    @pytest.mark.asyncio
    async def test_no_fallback_when_disabled(self, messages):
        """Should raise error when ZAI fails and fallback is disabled."""
        with (
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai_cls,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini_cls,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama_cls,
        ):
            # ZAI fails
            mock_zai = _make_mock_provider("zai", available=False)
            mock_openai_cls.return_value = mock_zai

            mock_gemini_cls.return_value = _make_mock_provider("gemini")
            mock_ollama_cls.return_value = _make_mock_provider("ollama")

            manager = LLMManager()

            with pytest.raises(RuntimeError, match="No available LLM providers"):
                await manager.generate(messages, use_fallback=False)

    @pytest.mark.asyncio
    async def test_all_providers_unavailable_raises(self, messages):
        """Should raise RuntimeError when all providers are unavailable."""
        with (
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai_cls,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini_cls,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama_cls,
        ):
            # All providers unavailable
            mock_openai_cls.return_value = _make_mock_provider("zai", available=False)
            mock_gemini_cls.return_value = _make_mock_provider("gemini", available=False)
            mock_ollama_cls.return_value = _make_mock_provider("ollama", available=False)

            manager = LLMManager()

            with pytest.raises(RuntimeError, match="No available LLM providers"):
                await manager.generate(messages, use_fallback=True)


# ============================================================================
# Test: Free Tier Fallback (credits exhausted)
# ============================================================================


class TestFreeTierFallback:
    """Verify behavior when subscription credits are exhausted.

    When ZAI credits run out, the system should:
    1. Fall back to Ollama (local)
    2. Optionally use free GLM models (glm-4.7-flash) if configured
    """

    @pytest.mark.asyncio
    async def test_zai_credits_exhausted_falls_to_ollama(self, messages):
        """Should fall back to Ollama when ZAI returns credit errors."""
        with (
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai_cls,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini_cls,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama_cls,
        ):
            # ZAI returns credit exhaustion error
            mock_zai = _make_mock_provider("zai", available=True)
            mock_zai.generate.side_effect = RuntimeError(
                "Insufficient credits. Please upgrade your plan."
            )
            mock_openai_cls.return_value = mock_zai

            # Ollama works
            mock_ollama = _make_mock_provider(
                "ollama",
                available=True,
                generate_content="Local response",
                generate_model="qwen2.5-coder:7b",
            )
            mock_ollama_cls.return_value = mock_ollama

            mock_gemini_cls.return_value = _make_mock_provider("gemini")

            manager = LLMManager()
            response = await manager.generate(messages, use_fallback=True)

            assert response is not None
            assert response.content == "Local response"
            assert response.provider == "ollama"

    @pytest.mark.asyncio
    async def test_free_flash_model_as_explicit_provider(self, messages):
        """Should work with glm-4.7-flash (free tier) when explicitly requested."""
        with (
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai_cls,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini_cls,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama_cls,
        ):
            mock_zai = _make_mock_provider(
                "zai",
                available=True,
                generate_content="Free model response",
                generate_model="glm-4.7-flash",
            )
            mock_openai_cls.return_value = mock_zai
            mock_gemini_cls.return_value = _make_mock_provider("gemini")
            mock_ollama_cls.return_value = _make_mock_provider("ollama")

            manager = LLMManager()
            response = await manager.generate(
                messages,
                provider="zai",
                model="glm-4.7-flash",
            )

            assert response is not None
            assert response.model == "glm-4.7-flash"


# ============================================================================
# Test: Provider Configuration
# ============================================================================


class TestProviderConfiguration:
    """Verify provider configuration is correct for the ZAI-first setup."""

    def test_zai_api_key_from_env(self):
        """ZAI config should pick up ZAI_API_KEY from environment."""
        mock_settings = MagicMock()
        mock_settings.zai_api_key = None

        with (
            patch.dict(os.environ, {"ZAI_API_KEY": "test-zai-key-1234567890"}),
            patch("session_buddy.llm_providers.get_settings", return_value=mock_settings),
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama,
        ):
            mock_openai.return_value = _make_mock_provider("zai")
            mock_gemini.return_value = _make_mock_provider("gemini")
            mock_ollama.return_value = _make_mock_provider("ollama")

            manager = LLMManager()
            zai_config = manager.config["providers"]["zai"]

            assert zai_config["api_key"] == "test-zai-key-1234567890"

    def test_zai_base_url_from_env(self):
        """ZAI config should use ZAI_BASE_URL from environment if set."""
        custom_url = "https://custom-zai.example.com/v4"
        mock_settings = MagicMock()
        mock_settings.zai_api_key = None

        with (
            patch.dict(
                os.environ,
                {"ZAI_API_KEY": "test-key", "ZAI_BASE_URL": custom_url},
            ),
            patch("session_buddy.llm_providers.get_settings", return_value=mock_settings),
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama,
        ):
            mock_openai.return_value = _make_mock_provider("zai")
            mock_gemini.return_value = _make_mock_provider("gemini")
            mock_ollama.return_value = _make_mock_provider("ollama")

            manager = LLMManager()
            zai_config = manager.config["providers"]["zai"]

            assert zai_config["base_url"] == custom_url

    def test_zai_default_model_from_env(self):
        """ZAI config should use ZAI_DEFAULT_MODEL from environment if set."""
        mock_settings = MagicMock()
        mock_settings.zai_api_key = None

        with (
            patch.dict(
                os.environ,
                {"ZAI_API_KEY": "test-key", "ZAI_DEFAULT_MODEL": "glm-5.1"},
            ),
            patch("session_buddy.llm_providers.get_settings", return_value=mock_settings),
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama,
        ):
            mock_openai.return_value = _make_mock_provider("zai")
            mock_gemini.return_value = _make_mock_provider("gemini")
            mock_ollama.return_value = _make_mock_provider("ollama")

            manager = LLMManager()
            zai_config = manager.config["providers"]["zai"]

            assert zai_config["default_model"] == "glm-5.1"

    def test_ollama_base_url_default(self):
        """Ollama config should default to localhost:11434."""
        with (
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama,
        ):
            mock_openai.return_value = _make_mock_provider("zai")
            mock_gemini.return_value = _make_mock_provider("gemini")
            mock_ollama.return_value = _make_mock_provider("ollama")

            manager = LLMManager()
            ollama_config = manager.config["providers"]["ollama"]

            assert "localhost:11434" in ollama_config["base_url"]


# ============================================================================
# Test: API Key Helper Functions (ZAI-aware)
# ============================================================================


class TestZAIKeyHelpers:
    """Verify API key helper functions work with ZAI provider."""

    def test_get_zai_api_key_and_env(self):
        """_get_provider_api_key_and_env should work for ZAI."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        with patch.dict(os.environ, {"ZAI_API_KEY": "test-zai-key"}):
            api_key, env_var = _get_provider_api_key_and_env("zai")

            assert api_key == "test-zai-key"
            assert env_var == "ZAI_API_KEY"

    def test_get_zai_api_key_not_set(self):
        """Should return None when ZAI_API_KEY is not set."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        with patch.dict(os.environ, {}, clear=True):
            api_key, env_var = _get_provider_api_key_and_env("zai")

            assert api_key is None
            assert env_var == "ZAI_API_KEY"

    def test_zai_in_configured_providers(self):
        """_get_configured_providers should include ZAI when key is set."""
        from session_buddy.llm_providers import _get_configured_providers

        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}, clear=True):
            providers = _get_configured_providers()

            assert "zai" in providers

    def test_zai_masked_api_key(self):
        """get_masked_api_key should mask ZAI keys properly."""
        from session_buddy.llm_providers import get_masked_api_key

        with (
            patch.dict(os.environ, {"ZAI_API_KEY": "zai-test-key-1234567890"}),
            patch("session_buddy.llm_providers.SECURITY_AVAILABLE", False),
        ):
            result = get_masked_api_key("zai")

            # Should show last 4 chars
            assert result.endswith("7890")
            assert "test-key-1234567890" not in result


# ============================================================================
# Test: get_available_providers
# ============================================================================


class TestGetAvailableProviders:
    """Verify available provider listing with ZAI."""

    @pytest.mark.asyncio
    async def test_available_providers_includes_zai(self, llm_manager):
        """get_available_providers should include ZAI."""
        available = await llm_manager.get_available_providers()

        assert "zai" in available

    @pytest.mark.asyncio
    async def test_available_providers_includes_ollama(self, llm_manager):
        """get_available_providers should include Ollama."""
        available = await llm_manager.get_available_providers()

        assert "ollama" in available

    @pytest.mark.asyncio
    async def test_available_providers_excludes_unavailable(self):
        """Should exclude providers that are not available."""
        with (
            patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai_cls,
            patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini_cls,
            patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama_cls,
        ):
            # Only Ollama available
            mock_openai_cls.return_value = _make_mock_provider("zai", available=False)
            mock_gemini_cls.return_value = _make_mock_provider("gemini", available=False)
            mock_ollama_cls.return_value = _make_mock_provider("ollama", available=True)

            manager = LLMManager()
            available = await manager.get_available_providers()

            assert "ollama" in available
            assert "zai" not in available


# ============================================================================
# Test: Provider Info
# ============================================================================


class TestProviderInfo:
    """Verify provider info reporting."""

    def test_provider_info_includes_zai(self, llm_manager):
        """get_provider_info should include ZAI configuration."""
        info = llm_manager.get_provider_info()

        assert "zai" in info["providers"]
        assert info["config"]["default_provider"] == "zai"

    def test_provider_info_shows_fallback_chain(self, llm_manager):
        """get_provider_info should show fallback chain."""
        info = llm_manager.get_provider_info()

        assert "ollama" in info["config"]["fallback_providers"]

    def test_provider_info_hides_api_keys(self, llm_manager):
        """get_provider_info should not expose API keys."""
        info = llm_manager.get_provider_info()

        for _provider_name, provider_info in info["providers"].items():
            config = provider_info.get("config", {})
            for key, value in config.items():
                if "key" in key.lower():
                    pytest.fail(
                        f"Provider info exposes key '{key}' with value '{value}'"
                    )


# ============================================================================
# Test: Streaming with ZAI
# ============================================================================


class TestStreamingWithZAI:
    """Verify streaming generation works with ZAI as primary."""

    @pytest.mark.asyncio
    async def test_stream_generate_uses_zai(self, llm_manager, messages):
        """stream_generate should use ZAI as primary provider."""
        # Mock the provider's stream_generate as an async generator
        async def mock_stream(*args, **kwargs):
            yield "Hello from ZAI"

        zai_provider = llm_manager.providers["zai"]
        zai_provider.stream_generate = mock_stream
        zai_provider.is_available.return_value = True

        # Collect streamed content
        collected = []
        async for chunk in llm_manager.stream_generate(messages):
            collected.append(chunk)

        # Verify content was streamed from ZAI
        assert len(collected) >= 1
        result = "".join(collected)
        assert "ZAI" in result
