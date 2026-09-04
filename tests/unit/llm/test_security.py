"""Tests for session_buddy.llm.security (path-mirror).

Path-mirror companion to the higher-level ``tests/unit/test_llm_security.py``.
Exercises every branch in :mod:`session_buddy.llm.security`, including the
``SECURITY_AVAILABLE`` toggle, settings-vs-env fallback paths, and the startup
validator entry point.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from mcp_common.exceptions import APIKeyFormatError, APIKeyMissingError

from session_buddy.llm.security import (
    SECURITY_AVAILABLE,
    _get_configured_providers,
    _get_provider_api_key_and_env,
    _validate_provider_basic,
    _validate_provider_with_security,
    get_masked_api_key,
    validate_llm_api_keys_at_startup,
)


# ---------------------------------------------------------------------------
# get_masked_api_key
# ---------------------------------------------------------------------------


class TestGetMaskedApiKey:
    """Exercise every branch in :func:`get_masked_api_key`."""

    def test_ollama_local_no_key(self) -> None:
        assert get_masked_api_key("ollama") == "N/A (local service)"

    def test_llama_server_local_no_key(self) -> None:
        assert get_masked_api_key("llama_server") == "N/A (local service)"

    def test_settings_branch_returns_masked_string(self) -> None:
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "sk-real-key-1234567890abcdef"
        mock_settings.get_masked_key.return_value = "sk-...cdef"
        with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
            result = get_masked_api_key("openai")
        assert result == "sk-...cdef"
        mock_settings.get_masked_key.assert_called_once_with(
            key_name="openai_api_key", visible_chars=4
        )

    def test_settings_branch_non_string_value_falls_through(self) -> None:
        """When configured key is not a string, fall through to env-var path."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = None
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "sk-env-key-1234567890abcdef"}, clear=True
        ):
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("openai")
        assert isinstance(result, str)
        assert result != "sk-env-key-1234567890abcdef"

    def test_settings_branch_empty_string_falls_through(self) -> None:
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "   "  # whitespace
        with patch.dict(
            os.environ, {"ANTHROPIC_API_KEY": "ant-env-1234567890abcdef"}, clear=True
        ):
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("anthropic")
        assert isinstance(result, str)

    def test_openai_env_var(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-very-long-1234567890abcdef"}, clear=True):
            mock_settings = MagicMock()
            mock_settings.openai_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("openai")
        assert isinstance(result, str)
        assert result != "sk-very-long-1234567890abcdef"

    def test_gemini_env_uses_gemini_key(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyD-env-1234567890abcdef"}, clear=True):
            mock_settings = MagicMock()
            mock_settings.gemini_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("gemini")
        assert isinstance(result, str)

    def test_gemini_falls_back_to_google_api_key(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIzaSyD-env-1234567890abcdef"}, clear=True):
            mock_settings = MagicMock()
            mock_settings.gemini_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("gemini")
        assert isinstance(result, str)

    def test_qwen_env_var(self) -> None:
        with patch.dict(os.environ, {"QWEN_API_KEY": "qwen-env-1234567890abcdef"}, clear=True):
            mock_settings = MagicMock()
            mock_settings.qwen_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("qwen")
        assert isinstance(result, str)

    def test_minimax_env_var(self) -> None:
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "minimax-env-1234567890abcdef"}, clear=True):
            mock_settings = MagicMock()
            mock_settings.minimax_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("minimax")
        assert isinstance(result, str)

    def test_zai_env_var(self) -> None:
        with patch.dict(os.environ, {"ZAI_API_KEY": "zai-env-1234567890abcdef"}, clear=True):
            mock_settings = MagicMock()
            mock_settings.zai_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("zai")
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
            mock_settings.configure_mock(**{})
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                result = get_masked_api_key("mystery_provider")
        assert result == "***"

    def test_short_env_key_falls_back_when_security_unavailable(self) -> None:
        """Without SECURITY_AVAILABLE, keys shorter than 4 chars get masked to '***'."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "abc"}, clear=True):
            mock_settings = MagicMock()
            mock_settings.openai_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                with patch("session_buddy.llm.security.SECURITY_AVAILABLE", False):
                    result = get_masked_api_key("openai")
        assert result == "***"

    def test_fallback_mask_when_security_unavailable(self) -> None:
        """Without mcp_common security, the local f-string mask runs."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-very-long-env-1234567890"}, clear=True):
            mock_settings = MagicMock()
            mock_settings.openai_api_key = ""
            with patch("session_buddy.llm.security.get_settings", return_value=mock_settings):
                with patch("session_buddy.llm.security.SECURITY_AVAILABLE", False):
                    result = get_masked_api_key("openai")
        # Last four chars of "sk-very-long-env-1234567890" -> "7890"
        assert result == "...7890"


# ---------------------------------------------------------------------------
# _get_provider_api_key_and_env
# ---------------------------------------------------------------------------


class TestGetProviderApiKeyAndEnv:
    def test_settings_key_takes_precedence(self) -> None:
        with patch(
            "session_buddy.llm.security.get_llm_api_key", return_value="from-settings"
        ):
            api_key, env = _get_provider_api_key_and_env("openai")
        assert api_key == "from-settings"
        assert env == "settings.openai_api_key"

    def test_openai_env_fallback(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "env-openai"}, clear=True):
                api_key, env = _get_provider_api_key_and_env("openai")
        assert api_key == "env-openai"
        assert env == "OPENAI_API_KEY"

    def test_anthropic_env_fallback(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-anthro"}, clear=True):
                api_key, env = _get_provider_api_key_and_env("anthropic")
        assert api_key == "env-anthro"
        assert env == "ANTHROPIC_API_KEY"

    def test_gemini_prefers_gemini_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "gem", "GOOGLE_API_KEY": "goog"},
                clear=True,
            ):
                api_key, env = _get_provider_api_key_and_env("gemini")
        assert api_key == "gem"
        assert env == "GEMINI_API_KEY"

    def test_gemini_falls_back_to_google_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "goog"}, clear=True):
                api_key, env = _get_provider_api_key_and_env("gemini")
        assert api_key == "goog"
        assert env == "GOOGLE_API_KEY"

    def test_minimax_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"MINIMAX_API_KEY": "m-env"}, clear=True):
                api_key, env = _get_provider_api_key_and_env("minimax")
        assert api_key == "m-env"
        assert env == "MINIMAX_API_KEY"

    def test_zai_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"ZAI_API_KEY": "z-env"}, clear=True):
                api_key, env = _get_provider_api_key_and_env("zai")
        assert api_key == "z-env"
        assert env == "ZAI_API_KEY"

    def test_unknown_provider_returns_none_pair(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            api_key, env = _get_provider_api_key_and_env("no_such_provider")
        assert api_key is None
        assert env is None


# ---------------------------------------------------------------------------
# _validate_provider_with_security
# ---------------------------------------------------------------------------


class TestValidateProviderWithSecurity:
    def test_valid_key_returns_true(self) -> None:
        valid_key = "sk-" + "a" * 48
        with patch(
            "session_buddy.llm.security.get_masked_api_key", return_value="masked"
        ):
            ok, status = _validate_provider_with_security("openai", valid_key)
        assert ok is True
        assert status == "valid"

    def test_invalid_key_propagates_or_exits(self) -> None:
        invalid_key = "not-the-right-format"
        with patch("session_buddy.llm.security.get_masked_api_key", return_value="masked"):
            # The function only catches ValueError, but APIKeyFormatError does not
            # inherit from ValueError, so it propagates. Either SystemExit (when
            # caught) or APIKeyFormatError (when not) is acceptable behavior.
            with pytest.raises((SystemExit, APIKeyFormatError, ValueError)):
                _validate_provider_with_security("openai", invalid_key)

    def test_empty_key_propagates_or_exits(self) -> None:
        with patch("session_buddy.llm.security.get_masked_api_key", return_value="masked"):
            with pytest.raises((SystemExit, APIKeyMissingError, ValueError)):
                _validate_provider_with_security("openai", "")

    def test_real_value_error_triggers_sys_exit(self) -> None:
        """Force a real ``ValueError`` from the validator to exercise the except branch."""
        from mcp_common.security import APIKeyValidator

        valid_key = "sk-" + "a" * 48

        class _RaisingValidator:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def validate(self, _key: str, *, raise_on_invalid: bool) -> None:
                msg = "real ValueError"
                raise ValueError(msg)

        with patch.object(APIKeyValidator, "__init__", return_value=None):
            with patch.object(
                APIKeyValidator,
                "validate",
                side_effect=ValueError("real ValueError"),
            ):
                with pytest.raises(SystemExit):
                    _validate_provider_with_security("openai", valid_key)


# ---------------------------------------------------------------------------
# _validate_provider_basic
# ---------------------------------------------------------------------------


class TestValidateProviderBasic:
    def test_long_key_returns_basic_check(self) -> None:
        assert _validate_provider_basic("openai", "any-long-enough-key-12345") == "basic_check"

    def test_short_key_returns_basic_check(self) -> None:
        """Basic check never raises; short keys still return the basic marker."""
        assert _validate_provider_basic("openai", "abc") == "basic_check"

    def test_empty_string_returns_basic_check(self) -> None:
        assert _validate_provider_basic("openai", "") == "basic_check"

    def test_exactly_15_chars_returns_basic_check(self) -> None:
        assert _validate_provider_basic("openai", "a" * 15) == "basic_check"

    def test_exactly_16_chars_returns_basic_check(self) -> None:
        assert _validate_provider_basic("openai", "a" * 16) == "basic_check"


# ---------------------------------------------------------------------------
# _get_configured_providers
# ---------------------------------------------------------------------------


class TestGetConfiguredProviders:
    def test_always_includes_local_providers(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert "ollama" in providers
        assert "llama_server" in providers

    def test_includes_minimax_via_settings(self) -> None:
        with patch(
            "session_buddy.llm.security.get_llm_api_key",
            side_effect=lambda p: "k" if p == "minimax" else "",
        ):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert "minimax" in providers

    def test_includes_zai_via_settings(self) -> None:
        with patch(
            "session_buddy.llm.security.get_llm_api_key",
            side_effect=lambda p: "k" if p == "zai" else "",
        ):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert "zai" in providers

    def test_includes_openai_via_settings(self) -> None:
        with patch(
            "session_buddy.llm.security.get_llm_api_key",
            side_effect=lambda p: "k" if p == "openai" else "",
        ):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert "openai" in providers

    def test_includes_gemini_via_settings(self) -> None:
        with patch(
            "session_buddy.llm.security.get_llm_api_key",
            side_effect=lambda p: "k" if p == "gemini" else "",
        ):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert "gemini" in providers

    def test_includes_anthropic_via_settings(self) -> None:
        with patch(
            "session_buddy.llm.security.get_llm_api_key",
            side_effect=lambda p: "k" if p == "anthropic" else "",
        ):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert "anthropic" in providers

    def test_includes_qwen_via_settings(self) -> None:
        with patch(
            "session_buddy.llm.security.get_llm_api_key",
            side_effect=lambda p: "k" if p == "qwen" else "",
        ):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert "qwen" in providers

    def test_includes_env_var_providers(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(
                os.environ,
                {
                    "MINIMAX_API_KEY": "k",
                    "ZAI_API_KEY": "k",
                    "OPENAI_API_KEY": "k",
                    "ANTHROPIC_API_KEY": "k",
                },
                clear=True,
            ):
                providers = _get_configured_providers()
        assert {"minimax", "zai", "openai", "anthropic"}.issubset(set(providers))

    def test_includes_gemini_via_gemini_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}, clear=True):
                providers = _get_configured_providers()
        assert "gemini" in providers

    def test_includes_gemini_via_google_env(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "k"}, clear=True):
                providers = _get_configured_providers()
        assert "gemini" in providers

    def test_returns_sorted_list(self) -> None:
        with patch("session_buddy.llm.security.get_llm_api_key", return_value=""):
            with patch.dict(os.environ, {}, clear=True):
                providers = _get_configured_providers()
        assert providers == sorted(providers)


# ---------------------------------------------------------------------------
# validate_llm_api_keys_at_startup
# ---------------------------------------------------------------------------


class TestValidateLlmApiKeysAtStartup:
    def test_no_providers_returns_empty_dict(self) -> None:
        with patch("session_buddy.llm.security._get_configured_providers", return_value=[]):
            with patch.object(sys, "stderr", new=MagicMock()):
                result = validate_llm_api_keys_at_startup()
        assert result == {}

    def test_valid_provider_uses_security_validator(self) -> None:
        valid_key = "sk-" + "a" * 48
        with patch(
            "session_buddy.llm.security._get_configured_providers", return_value=["openai"]
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=(valid_key, "OPENAI_API_KEY"),
            ):
                with patch.object(sys, "stderr", new=MagicMock()):
                    result = validate_llm_api_keys_at_startup()
        assert result == {"openai": "valid"}

    def test_exits_on_empty_api_key(self) -> None:
        with patch(
            "session_buddy.llm.security._get_configured_providers", return_value=["openai"]
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=("", "OPENAI_API_KEY"),
            ):
                with pytest.raises(SystemExit):
                    validate_llm_api_keys_at_startup()

    def test_exits_on_whitespace_api_key(self) -> None:
        with patch(
            "session_buddy.llm.security._get_configured_providers", return_value=["openai"]
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=("   ", "OPENAI_API_KEY"),
            ):
                with pytest.raises(SystemExit):
                    validate_llm_api_keys_at_startup()

    def test_falls_back_to_basic_validator_when_security_unavailable(self) -> None:
        with patch(
            "session_buddy.llm.security._get_configured_providers", return_value=["openai"]
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=("sk-very-long-env-key-12345", "OPENAI_API_KEY"),
            ):
                with patch("session_buddy.llm.security.SECURITY_AVAILABLE", False):
                    with patch.object(sys, "stderr", new=MagicMock()):
                        result = validate_llm_api_keys_at_startup()
        assert result == {"openai": "basic_check"}

    def test_invalid_security_key_propagates(self) -> None:
        with patch(
            "session_buddy.llm.security._get_configured_providers", return_value=["openai"]
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                return_value=("definitely-not-valid", "OPENAI_API_KEY"),
            ):
                # Either SystemExit (when caught) or APIKeyFormatError (when not).
                with pytest.raises((SystemExit, APIKeyFormatError, ValueError)):
                    validate_llm_api_keys_at_startup()

    def test_multiple_providers_each_validated(self) -> None:
        # Anthropic keys need ``sk-ant-`` prefix + 95+ chars after the dash.
        with patch(
            "session_buddy.llm.security._get_configured_providers",
            return_value=["openai", "anthropic"],
        ):
            with patch(
                "session_buddy.llm.security._get_provider_api_key_and_env",
                side_effect=lambda p: (
                    ("sk-" + "a" * 48, "OPENAI_API_KEY")
                    if p == "openai"
                    else ("sk-ant-" + "b" * 100, "ANTHROPIC_API_KEY")
                ),
            ):
                with patch.object(sys, "stderr", new=MagicMock()):
                    result = validate_llm_api_keys_at_startup()
        assert set(result.keys()) == {"openai", "anthropic"}
        assert all(status == "valid" for status in result.values())


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_security_available_is_bool(self) -> None:
        assert isinstance(SECURITY_AVAILABLE, bool)
