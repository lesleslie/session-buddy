#!/usr/bin/env python3
"""Tests for LLM provider helper functions.

Tests helper functions created during complexity refactoring of llm_providers.py,
including API key validation and provider availability checking.

Phase 2: Core Coverage (30% → 70%) - Helper Function Tests
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetProviderApiKeyAndEnv:
    """Test _get_provider_api_key_and_env helper function.

    Phase 2: Core Coverage - llm_providers.py (30% → 70%)
    """

    def test_get_openai_api_key_and_env(self) -> None:
        """Should return OpenAI API key and environment variable name."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"}):
            api_key, env_var = _get_provider_api_key_and_env("openai")

            assert api_key == "sk-test123"
            assert env_var == "OPENAI_API_KEY"

    def test_get_openai_api_key_when_not_set(self) -> None:
        """Should return None when OpenAI API key not set."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        with patch.dict(os.environ, {}, clear=True):
            api_key, env_var = _get_provider_api_key_and_env("openai")

            assert api_key is None
            assert env_var == "OPENAI_API_KEY"

    def test_get_gemini_api_key_from_gemini_api_key(self) -> None:
        """Should return Gemini API key from GEMINI_API_KEY."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-test-key"}):
            api_key, env_var = _get_provider_api_key_and_env("gemini")

            assert api_key == "gemini-test-key"
            assert env_var == "GEMINI_API_KEY"

    def test_get_gemini_api_key_from_google_api_key(self) -> None:
        """Should return Gemini API key from GOOGLE_API_KEY when GEMINI_API_KEY not set."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "google-test-key"}, clear=True):
            api_key, env_var = _get_provider_api_key_and_env("gemini")

            assert api_key == "google-test-key"
            assert env_var == "GOOGLE_API_KEY"

    def test_get_gemini_api_key_prefers_gemini_api_key(self) -> None:
        """Should prefer GEMINI_API_KEY over GOOGLE_API_KEY when both set."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        with patch.dict(
            os.environ, {"GEMINI_API_KEY": "gemini-key", "GOOGLE_API_KEY": "google-key"}
        ):
            api_key, env_var = _get_provider_api_key_and_env("gemini")

            assert api_key == "gemini-key"
            assert env_var == "GEMINI_API_KEY"

    def test_get_unknown_provider(self) -> None:
        """Should return None for unknown providers."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        api_key, env_var = _get_provider_api_key_and_env("unknown_provider")

        assert api_key is None
        assert env_var is None

    def test_get_ollama_provider(self) -> None:
        """Should return None for Ollama (local service, no API key)."""
        from session_buddy.llm_providers import _get_provider_api_key_and_env

        api_key, env_var = _get_provider_api_key_and_env("ollama")

        assert api_key is None
        assert env_var is None


class TestGetConfiguredProviders:
    """Test _get_configured_providers helper function.

    Phase 2: Core Coverage - llm_providers.py (30% → 70%)
    """

    def test_get_configured_providers_with_openai(self) -> None:
        """Should return OpenAI when OPENAI_API_KEY is set."""
        from session_buddy.llm_providers import _get_configured_providers

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            providers = _get_configured_providers()

            assert "openai" in providers
            assert "gemini" not in providers

    def test_get_configured_providers_with_gemini(self) -> None:
        """Should return Gemini when GEMINI_API_KEY is set."""
        from session_buddy.llm_providers import _get_configured_providers

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-test"}, clear=True):
            providers = _get_configured_providers()

            assert "gemini" in providers
            assert "openai" not in providers

    def test_get_configured_providers_with_google_api_key(self) -> None:
        """Should return Gemini when GOOGLE_API_KEY is set."""
        from session_buddy.llm_providers import _get_configured_providers

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "google-test"}, clear=True):
            providers = _get_configured_providers()

            assert "gemini" in providers

    def test_get_configured_providers_with_both(self) -> None:
        """Should return both providers when both API keys are set."""
        from session_buddy.llm_providers import _get_configured_providers

        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "sk-test", "GEMINI_API_KEY": "gemini-test"}
        ):
            providers = _get_configured_providers()

            assert "openai" in providers
            assert "gemini" in providers
            # Note: ZAI_API_KEY may also be configured in the environment
            assert len(providers) >= 2

    def test_get_configured_providers_with_none(self) -> None:
        """Should return empty list when no API keys are set."""
        from session_buddy.llm_providers import _get_configured_providers

        with patch.dict(os.environ, {}, clear=True):
            providers = _get_configured_providers()

            assert len(providers) == 0
            assert isinstance(providers, list)


class TestValidateProviderBasic:
    """Test _validate_provider_basic helper function.

    Phase 2: Core Coverage - llm_providers.py (30% → 70%)
    """

    def test_validate_short_api_key_warns(self, capsys: pytest.CaptureFixture) -> None:
        """Should warn when API key is shorter than 16 characters."""
        from session_buddy.llm_providers import _validate_provider_basic

        status = _validate_provider_basic("openai", "short-key")

        assert status == "basic_check"
        captured = capsys.readouterr()
        assert "API Key Warning" in captured.err
        assert "appears very short" in captured.err

    def test_validate_long_api_key_no_warning(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should not warn when API key is long enough."""
        from session_buddy.llm_providers import _validate_provider_basic

        status = _validate_provider_basic("openai", "sk-" + "x" * 40)

        assert status == "basic_check"
        captured = capsys.readouterr()
        # Should have minimal output (no warnings)
        assert "Warning" not in captured.err

    def test_validate_returns_basic_check_status(self) -> None:
        """Should always return 'basic_check' status."""
        from session_buddy.llm_providers import _validate_provider_basic

        status = _validate_provider_basic("gemini", "x" * 32)

        assert status == "basic_check"


class TestValidateProviderWithSecurity:
    """Test _validate_provider_with_security helper function.

    Phase 2: Core Coverage - llm_providers.py (30% → 70%)
    """

    def test_validate_with_security_success(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should validate API key using security module when available."""
        from session_buddy.llm_providers import SECURITY_AVAILABLE

        if not SECURITY_AVAILABLE:
            pytest.skip("Security module not available")

        from session_buddy.llm_providers import _validate_provider_with_security

        # Mock validator to avoid actual API key validation
        with patch("session_buddy.llm_providers.APIKeyValidator") as mock_validator:
            mock_instance = MagicMock()
            mock_instance.validate.return_value = None  # Success (no exception)
            mock_validator.return_value = mock_instance

            success, status = _validate_provider_with_security("openai", "sk-test123")

            assert success is True
            assert status == "valid"
            captured = capsys.readouterr()
            assert "✅" in captured.err
            assert "API Key validated" in captured.err

    def test_validate_with_security_failure_exits(self) -> None:
        """Should exit on validation failure."""
        from session_buddy.llm_providers import SECURITY_AVAILABLE

        if not SECURITY_AVAILABLE:
            pytest.skip("Security module not available")

        from session_buddy.llm_providers import _validate_provider_with_security

        with patch("session_buddy.llm_providers.APIKeyValidator") as mock_validator:
            mock_instance = MagicMock()
            mock_instance.validate.side_effect = ValueError("Invalid API key format")
            mock_validator.return_value = mock_instance

            with pytest.raises(SystemExit) as exc_info:
                _validate_provider_with_security("openai", "invalid-key")

            assert exc_info.value.code == 1


class TestValidateLlmApiKeysAtStartup:
    """Test validate_llm_api_keys_at_startup function.

    Phase 2: Core Coverage - llm_providers.py (30% → 70%)
    """

    def test_validate_no_providers_configured_warns(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should warn when no providers are configured."""
        from session_buddy.llm_providers import validate_llm_api_keys_at_startup

        with patch.dict(os.environ, {}, clear=True):
            result = validate_llm_api_keys_at_startup()

            assert len(result) == 0
            captured = capsys.readouterr()
            assert "No LLM Provider API Keys Configured" in captured.err

    def test_validate_with_security_module(self, capsys: pytest.CaptureFixture) -> None:
        """Should use security module when available."""
        from session_buddy.llm_providers import (
            SECURITY_AVAILABLE,
            validate_llm_api_keys_at_startup,
        )

        if not SECURITY_AVAILABLE:
            pytest.skip("Security module not available")

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-" + "x" * 40}),
            patch("session_buddy.llm_providers.APIKeyValidator") as mock_validator,
        ):
            mock_instance = MagicMock()
            mock_instance.validate.return_value = None
            mock_validator.return_value = mock_instance

            result = validate_llm_api_keys_at_startup()

            assert "openai" in result
            assert result["openai"] == "valid"

    def test_validate_without_security_module(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should use basic validation when security module unavailable."""
        from session_buddy.llm_providers import validate_llm_api_keys_at_startup

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-" + "x" * 40}),
            patch("session_buddy.llm_providers.SECURITY_AVAILABLE", False),
        ):
            result = validate_llm_api_keys_at_startup()

            assert "openai" in result
            assert result["openai"] == "basic_check"

    def test_validate_empty_api_key_exits(self) -> None:
        """Should exit when API key is empty or whitespace."""
        from session_buddy.llm_providers import validate_llm_api_keys_at_startup

        with patch.dict(os.environ, {"OPENAI_API_KEY": "   "}):
            with pytest.raises(SystemExit) as exc_info:
                validate_llm_api_keys_at_startup()

            assert exc_info.value.code == 1

    def test_validate_multiple_providers(self, capsys: pytest.CaptureFixture) -> None:
        """Should validate all configured providers."""
        from session_buddy.llm_providers import validate_llm_api_keys_at_startup

        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "sk-" + "x" * 40,
                    "GEMINI_API_KEY": "gem-" + "y" * 40,
                },
            ),
            patch("session_buddy.llm_providers.SECURITY_AVAILABLE", False),
        ):
            result = validate_llm_api_keys_at_startup()

            assert "openai" in result
            assert "gemini" in result
            assert result["openai"] == "basic_check"
            assert result["gemini"] == "basic_check"


class TestGetMaskedApiKey:
    """Test get_masked_api_key helper function.

    Phase 2: Core Coverage - llm_providers.py (30% → 70%)
    """

    def test_get_masked_openai_api_key_with_security(self) -> None:
        """Should mask OpenAI API key using security module."""
        from session_buddy.llm_providers import (
            SECURITY_AVAILABLE,
            get_masked_api_key,
        )

        if not SECURITY_AVAILABLE:
            pytest.skip("Security module not available")

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test1234567890"}),
            patch("session_buddy.llm_providers.APIKeyValidator") as mock_validator,
        ):
            mock_validator.mask_key.return_value = "sk-...7890"

            result = get_masked_api_key("openai")

            assert "..." in result
            mock_validator.mask_key.assert_called_once()

    def test_get_masked_openai_api_key_without_security(self) -> None:
        """Should mask OpenAI API key using fallback method."""
        from session_buddy.llm_providers import get_masked_api_key

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test1234567890"}),
            patch("session_buddy.llm_providers.SECURITY_AVAILABLE", False),
        ):
            result = get_masked_api_key("openai")

            assert result == "...7890"

    def test_get_masked_gemini_api_key(self) -> None:
        """Should mask Gemini API key."""
        from session_buddy.llm_providers import get_masked_api_key

        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-key-12345"}),
            patch("session_buddy.llm_providers.SECURITY_AVAILABLE", False),
        ):
            result = get_masked_api_key("gemini")

            assert result == "...2345"

    def test_get_masked_api_key_for_ollama(self) -> None:
        """Should return N/A for Ollama (local service)."""
        from session_buddy.llm_providers import get_masked_api_key

        result = get_masked_api_key("ollama")

        assert result == "N/A (local service)"

    def test_get_masked_api_key_when_not_set(self) -> None:
        """Should return *** when API key not set."""
        from session_buddy.llm_providers import get_masked_api_key

        with patch.dict(os.environ, {}, clear=True):
            result = get_masked_api_key("openai")

            assert result == "***"

    def test_get_masked_api_key_short_key(self) -> None:
        """Should return *** for very short keys."""
        from session_buddy.llm_providers import get_masked_api_key

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "abc"}),
            patch("session_buddy.llm_providers.SECURITY_AVAILABLE", False),
        ):
            result = get_masked_api_key("openai")

            assert result == "***"


class TestOllamaProviderHelperFunctions:
    """Test Ollama provider helper functions for streaming and availability.

    Phase 2: Core Coverage - llm_providers.py (30% → 70%)
    """

    @pytest.mark.asyncio
    async def test_check_with_aiohttp_success(self) -> None:
        """Should check availability using aiohttp and return True on success."""
        from session_buddy.llm_providers import OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})

        # Mock aiohttp response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"models": [{"name": "llama2"}, {"name": "mistral"}]}
        )

        # Create async context manager for session.get()
        mock_get_cm = AsyncMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_get_cm)

        # Wrap mock_session in async context manager for ClientSession()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await provider._check_with_aiohttp(
                "http://localhost:11434/api/tags"
            )

            assert result is True
            assert provider._available_models == ["llama2", "mistral"]

    @pytest.mark.asyncio
    async def test_check_with_aiohttp_failure(self) -> None:
        """Should check availability using aiohttp and return False on failure."""
        from session_buddy.llm_providers import OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})

        # Mock aiohttp response with 500 error
        mock_response = AsyncMock()
        mock_response.status = 500

        # Create async context manager for session.get()
        mock_get_cm = AsyncMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_get_cm)

        # Wrap mock_session in async context manager for ClientSession()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await provider._check_with_aiohttp(
                "http://localhost:11434/api/tags"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_check_with_aiohttp_connection_error(self) -> None:
        """Should return False when connection fails."""
        from session_buddy.llm_providers import OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})

        with patch(
            "aiohttp.ClientSession", side_effect=Exception("Connection refused")
        ):
            result = await provider._check_with_aiohttp(
                "http://localhost:11434/api/tags"
            )

            assert result is False

    def test_extract_chunk_content_valid_json(self) -> None:
        """Should extract content from valid JSON chunk."""
        from session_buddy.llm_providers import OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})

        chunk_line = b'{"message": {"content": "Hello world"}}'

        result = provider._extract_chunk_content(chunk_line)

        assert result == "Hello world"

    def test_extract_chunk_content_empty_line(self) -> None:
        """Should return None for empty line."""
        from session_buddy.llm_providers import OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})

        result = provider._extract_chunk_content(b"")

        assert result is None

    def test_extract_chunk_content_invalid_json(self) -> None:
        """Should return None for invalid JSON."""
        from session_buddy.llm_providers import OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})

        result = provider._extract_chunk_content(b"not valid json")

        assert result is None

    def test_extract_chunk_content_missing_message(self) -> None:
        """Should return None when message field is missing."""
        from session_buddy.llm_providers import OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})

        result = provider._extract_chunk_content(b'{"data": "test"}')

        assert result is None

    def test_prepare_stream_data_basic(self) -> None:
        """Should prepare streaming data with basic options."""
        from session_buddy.llm_providers import LLMMessage, OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})
        messages = [LLMMessage(role="user", content="Hello")]

        data = provider._prepare_stream_data("llama2", messages, 0.7, None)

        assert data["model"] == "llama2"
        assert data["stream"] is True
        assert data["options"]["temperature"] == 0.7
        assert "num_predict" not in data["options"]

    def test_prepare_stream_data_with_max_tokens(self) -> None:
        """Should include num_predict when max_tokens provided."""
        from session_buddy.llm_providers import LLMMessage, OllamaProvider

        provider = OllamaProvider({"base_url": "http://localhost:11434"})
        messages = [LLMMessage(role="user", content="Hello")]

        data = provider._prepare_stream_data("llama2", messages, 0.8, 100)

        assert data["options"]["num_predict"] == 100
        assert data["options"]["temperature"] == 0.8
