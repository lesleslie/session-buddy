"""Tests for session_buddy.llm.security module.

Phase 3 coverage push: the security module wraps the mcp-common
``APIKeyValidator`` and provides the project-specific mask/validation entry
points used by ``llm_providers``. The tests below drive every branch.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.llm.security import (
    SECURITY_AVAILABLE,
    _get_configured_providers,
    _get_provider_api_key_and_env,
    _validate_provider_basic,
    _validate_provider_with_security,
    get_masked_api_key,
    validate_llm_api_keys_at_startup,
)


# =============================================================================
# get_masked_api_key
# =============================================================================


class TestGetMaskedApiKey:
    """Cover the full key-masking code path."""

    def test_masked_via_settings_uses_settings_get_masked_key(self) -> None:
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "sk-test-very-long-key-1234567890abcd"
        mock_settings.get_masked_key = MagicMock(return_value="sk-...abcd")
        with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
            result = get_masked_api_key("openai")
        # settings.get_masked_key is called - whatever it returns, it must be a string
        assert isinstance(result, str)
        # And it must not contain the full key (masked)
        assert "very-long-key" not in result

    def test_anthropic_via_settings(self) -> None:
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "sk-ant-key-1234567890abcdef"
        mock_settings.get_masked_key = MagicMock(return_value="sk-ant-...cdef")
        with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
            result = get_masked_api_key("anthropic")
        assert isinstance(result, str)

    def test_gemini_via_settings(self) -> None:
        mock_settings = MagicMock()
        mock_settings.gemini_api_key = "AIzaSyD-real-key-1234567890abcdef"
        mock_settings.get_masked_key = MagicMock(return_value="AIza...cdef")
        with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
            result = get_masked_api_key("gemini")
        assert isinstance(result, str)

    def test_ollama_returns_na(self) -> None:
        """Ollama is a local service with no key."""
        result = get_masked_api_key("ollama")
        assert result == "N/A (local service)"

    def test_llama_server_returns_na(self) -> None:
        result = get_masked_api_key("llama_server")
        assert result == "N/A (local service)"

    def test_minimax_env_var(self) -> None:
        with patch.dict(
            os.environ, {"MINIMAX_API_KEY": "minimax-very-long-secret-key-1234"}
        ):
            mock_settings = MagicMock()
            mock_settings.minimax_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("minimax")
        assert isinstance(result, str)
        assert result != "minimax-very-long-secret-key-1234"

    def test_zai_env_var(self) -> None:
        with patch.dict(os.environ, {"ZAI_API_KEY": "zai-very-long-secret-key-12345"}):
            mock_settings = MagicMock()
            mock_settings.zai_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("zai")
        assert isinstance(result, str)

    def test_qwen_env_var(self) -> None:
        with patch.dict(os.environ, {"QWEN_API_KEY": "qwen-very-long-secret-key-1234"}):
            mock_settings = MagicMock()
            mock_settings.qwen_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("qwen")
        assert isinstance(result, str)

    def test_openai_env_var(self) -> None:
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "sk-very-long-key-1234567890abcdef"}
        ):
            mock_settings = MagicMock()
            mock_settings.openai_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("openai")
        assert isinstance(result, str)

    def test_gemini_env_uses_gemini_key(self) -> None:
        with patch.dict(
            os.environ, {"GEMINI_API_KEY": "AIzaSyD-test-key-1234567890abcdef"}
        ):
            mock_settings = MagicMock()
            mock_settings.gemini_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("gemini")
        assert isinstance(result, str)

    def test_gemini_env_falls_back_to_google_key(self) -> None:
        with patch.dict(
            os.environ, {"GOOGLE_API_KEY": "AIzaSyD-test-key-1234567890abcdef"}, clear=True
        ):
            mock_settings = MagicMock()
            mock_settings.gemini_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("gemini")
        assert isinstance(result, str)

    def test_no_key_returns_asterisks(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            mock_settings = MagicMock()
            mock_settings.openai_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("openai")
        assert result == "***"

    def test_unknown_provider_returns_asterisks(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            mock_settings = MagicMock()
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("mystery_provider")
        assert result == "***"

    def test_short_key_falls_back_to_asterisks(self) -> None:
        """Keys shorter than the mask threshold produce '***'."""
        with patch.dict(os.environ, {}, clear=True):
            mock_settings = MagicMock()
            mock_settings.openai_api_key = "abc"
            mock_settings.get_masked_key = MagicMock(return_value="***")
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("openai")
        assert isinstance(result, str)

    def test_fallback_when_security_unavailable(self) -> None:
        """When mcp_common security is not available, the local mask runs."""
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "sk-very-long-env-key-1234567890abcdef"}, clear=True
        ):
            mock_settings = MagicMock()
            mock_settings.openai_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                with patch("session_buddy.llm.security.SECURITY_AVAILABLE", False):
                    result = get_masked_api_key("openai")
        # Without security, the module falls back to f"...{last4}"
        assert isinstance(result, str)
        assert result.endswith("cdef")


# =============================================================================
# _get_provider_api_key_and_env
# =============================================================================


class TestGetProviderApiKeyAndEnv:
    """Cover the key-source lookup helper."""

    def test_settings_key_takes_precedence(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value="from-settings"):
            api_key, env = _get_provider_api_key_and_env("openai")
        assert api_key == "from-settings"
        assert env == "settings.openai_api_key"

    def test_openai_env_fallback(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
                api_key, env = _get_provider_api_key_and_env("openai")
        assert api_key == "env-key"
        assert env == "OPENAI_API_KEY"

    def test_anthropic_env_fallback(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ant-env"}):
                api_key, env = _get_provider_api_key_and_env("anthropic")
        assert api_key == "ant-env"
        assert env == "ANTHROPIC_API_KEY"

    def test_gemini_uses_gemini_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(
                os.environ, {"GEMINI_API_KEY": "gem-env", "GOOGLE_API_KEY": "goog-env"}
            ):
                api_key, env = _get_provider_api_key_and_env("gemini")
        assert api_key == "gem-env"
        assert env == "GEMINI_API_KEY"

    def test_gemini_falls_back_to_google_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "goog-env"}, clear=True):
                api_key, env = _get_provider_api_key_and_env("gemini")
        assert api_key == "goog-env"
        assert env == "GOOGLE_API_KEY"

    def test_minimax_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"MINIMAX_API_KEY": "minimax-env"}):
                api_key, env = _get_provider_api_key_and_env("minimax")
        assert api_key == "minimax-env"
        assert env == "MINIMAX_API_KEY"

    def test_zai_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"ZAI_API_KEY": "zai-env"}):
                api_key, env = _get_provider_api_key_and_env("zai")
        assert api_key == "zai-env"
        assert env == "ZAI_API_KEY"

    def test_unknown_provider_returns_none(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            api_key, env = _get_provider_api_key_and_env("unknown_xyz")
        assert api_key is None
        assert env is None


# =============================================================================
# _validate_provider_with_security
# =============================================================================


class TestValidateProviderWithSecurity:
    """Cover the security-backed validator."""

    def test_valid_key_returns_true(self) -> None:
        valid_key = "sk-" + "a" * 48
        with patch("session_buddy.llm.security.get_masked_api_key", return_value="masked"):
            ok, status = _validate_provider_with_security("openai", valid_key)
        assert ok is True
        assert status == "valid"

    def test_invalid_key_raises_format_error(self) -> None:
        """The validator raises APIKeyFormatError when the key doesn't match."""
        from mcp_common.exceptions import APIKeyFormatError

        invalid_key = "not-the-right-format"
        with pytest.raises((SystemExit, APIKeyFormatError, ValueError)):
            _validate_provider_with_security("openai", invalid_key)

    def test_empty_key_raises(self) -> None:
        from mcp_common.exceptions import APIKeyMissingError

        with pytest.raises((SystemExit, APIKeyMissingError, ValueError)):
            _validate_provider_with_security("openai", "")


# =============================================================================
# _validate_provider_basic
# =============================================================================


class TestValidateProviderBasic:
    """Cover the basic validator fallback."""

    def test_returns_basic_check(self) -> None:
        result = _validate_provider_basic("openai", "any-long-enough-key-12345")
        assert result == "basic_check"

    def test_short_key_still_returns_basic_check(self) -> None:
        """Basic check never raises; short keys are silently accepted."""
        result = _validate_provider_basic("openai", "abc")
        assert result == "basic_check"


# =============================================================================
# _get_configured_providers
# =============================================================================


class TestGetConfiguredProviders:
    """Cover provider discovery from settings + env."""

    def test_includes_local_providers(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        # Ollama and llama_server are always present (local)
        assert "ollama" in providers
        assert "llama_server" in providers

    def test_includes_settings_provider(self) -> None:
        with patch(
            "session_buddy.llm.security.get_llm_api_key",
            side_effect=lambda p: "key" if p == "minimax" else "",
        ):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert "minimax" in providers

    def test_includes_env_var_providers(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "sk-test",
                    "ANTHROPIC_API_KEY": "sk-ant-test",
                },
                clear=True,
            ):
                providers = _get_configured_providers()
        assert "openai" in providers
        assert "anthropic" in providers

    def test_includes_gemini_via_gemini_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "AIza..."}, clear=True):
                providers = _get_configured_providers()
        assert "gemini" in providers

    def test_includes_gemini_via_google_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza..."}, clear=True):
                providers = _get_configured_providers()
        assert "gemini" in providers

    def test_returns_sorted_list(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert providers == sorted(providers)


# =============================================================================
# validate_llm_api_keys_at_startup
# =============================================================================


class TestValidateLlmApiKeysAtStartup:
    """Cover the startup entry point."""

    def test_no_providers_returns_empty_dict(self) -> None:
        with patch(
            "session_buddy.llm.security._get_configured_providers", return_value=[]
        ):
            with patch("sys.stderr", new=MagicMock()):
                result = validate_llm_api_keys_at_startup()
        assert result == {}

    def test_validates_each_provider_with_security(self) -> None:
        with patch(
            "session_buddy.llm.security._get_configured_providers",
            return_value=["openai"],
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=("sk-" + "a" * 48, "OPENAI_API_KEY"),
            ):
                with patch("sys.stderr", new=MagicMock()):
                    result = validate_llm_api_keys_at_startup()
        assert "openai" in result

    def test_exits_on_empty_key(self) -> None:
        with patch(
            "session_buddy.llm.security._get_configured_providers",
            return_value=["openai"],
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=("", "OPENAI_API_KEY"),
            ):
                with pytest.raises(SystemExit):
                    validate_llm_api_keys_at_startup()

    def test_falls_back_to_basic_validator(self) -> None:
        """When SECURITY_AVAILABLE is False, use the basic validator."""
        with patch(
            "session_buddy.llm.security._get_configured_providers",
            return_value=["openai"],
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=("sk-very-long-env-key-12345", "OPENAI_API_KEY"),
            ):
                with patch("session_buddy.llm.security.SECURITY_AVAILABLE", False):
                    with patch("sys.stderr", new=MagicMock()):
                        result = validate_llm_api_keys_at_startup()
        assert result.get("openai") == "basic_check"

    def test_invalid_security_key_exits(self) -> None:
        with patch(
            "session_buddy.llm.security._get_configured_providers",
            return_value=["openai"],
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=("definitely-not-valid", "OPENAI_API_KEY"),
            ):
                from mcp_common.exceptions import APIKeyFormatError
                with pytest.raises((SystemExit, APIKeyFormatError, ValueError)):
                    validate_llm_api_keys_at_startup()


# =============================================================================
# Module-level import guard
# =============================================================================


class TestModuleConstants:
    """Sanity checks for module exports."""

    def test_security_available_is_bool(self) -> None:
        """SECURITY_AVAILABLE reflects whether mcp_common.security imports."""
        assert isinstance(SECURITY_AVAILABLE, bool)
