"""LLM provider API key security and validation utilities.

This module provides security utilities for validating and masking LLM provider
API keys during server startup (Phase 3 Security Hardening).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from session_buddy.settings import get_llm_api_key, get_settings

if TYPE_CHECKING:
    from mcp_common.security import APIKeyValidator

# Import mcp-common security utilities for API key validation (Phase 3 Security Hardening)
try:
    from mcp_common.security import APIKeyValidator

    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False


def get_masked_api_key(provider: str = "openai") -> str:
    """Get masked API key for safe logging.

    Args:
        provider: Provider name ('openai', 'gemini', 'ollama')

    Returns:
        Masked API key string (e.g., "sk-...abc1") for safe display in logs

    """
    settings = get_settings()
    key_field_map = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
        "qwen": "qwen_api_key",
    }
    key_field = key_field_map.get(provider)
    if key_field:
        configured = getattr(settings, key_field, None)
        if isinstance(configured, str) and configured.strip():
            return settings.get_masked_key(key_name=key_field, visible_chars=4)

    api_key = None

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    elif provider == "qwen":
        api_key = os.getenv("QWEN_API_KEY")
    elif provider == "ollama":
        # Ollama is local, no API key needed
        return "N/A (local service)"

    if not api_key:
        return "***"

    if SECURITY_AVAILABLE:
        return APIKeyValidator.mask_key(api_key, visible_chars=4)

    # Fallback masking without security module
    if len(api_key) <= 4:
        return "***"
    return f"...{api_key[-4:]}"


def _get_provider_api_key_and_env(provider: str) -> tuple[str | None, str | None]:
    """Get API key and environment variable name for provider."""
    configured_key = get_llm_api_key(provider)
    if configured_key:
        return configured_key, f"settings.{provider}_api_key"
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY"
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY"
    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        env_var_name = (
            "GEMINI_API_KEY" if os.getenv("GEMINI_API_KEY") else "GOOGLE_API_KEY"
        )
        return api_key, env_var_name
    return None, None


def _validate_provider_with_security(provider: str, api_key: str) -> tuple[bool, str]:
    """Validate provider API key using mcp-common security module.

    Returns:
        Tuple of (success, status_message)

    """
    import sys

    validator = APIKeyValidator(provider=provider)
    try:
        validator.validate(api_key, raise_on_invalid=True)
        get_masked_api_key(provider)
        return True, "valid"
    except ValueError:
        sys.exit(1)


def _validate_provider_basic(provider: str, api_key: str) -> str:
    """Basic API key validation without security module.

    Returns:
        Status message

    """
    if len(api_key) < 16:
        pass
    return "basic_check"


def _get_configured_providers() -> list[str]:
    """Get list of configured LLM providers."""
    providers: set[str] = set()
    if get_llm_api_key("openai"):
        providers.add("openai")
    if get_llm_api_key("gemini"):
        providers.add("gemini")
    if get_llm_api_key("anthropic"):
        providers.add("anthropic")
    if os.getenv("OPENAI_API_KEY"):
        providers.add("openai")
    if os.getenv("ANTHROPIC_API_KEY"):
        providers.add("anthropic")
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        providers.add("gemini")
    return sorted(providers)


def validate_llm_api_keys_at_startup() -> dict[str, str]:
    """Validate LLM provider API keys at server startup (Phase 3 Security Hardening).

    Validates API keys for all configured LLM providers (OpenAI, Gemini).
    Ollama is skipped as it's a local service without API key requirements.

    Returns:
        Dictionary mapping provider names to validation status messages

    Raises:
        SystemExit: If required API keys are invalid or missing

    """
    import sys

    validated_providers: dict[str, str] = {}
    providers_configured = _get_configured_providers()

    # If no providers configured, warn but allow startup (Ollama might be used)
    if not providers_configured:
        return validated_providers

    # Validate each configured provider
    for provider in providers_configured:
        api_key, _env_var_name = _get_provider_api_key_and_env(provider)

        if not api_key or not api_key.strip():
            sys.exit(1)

        if SECURITY_AVAILABLE:
            _, status = _validate_provider_with_security(provider, api_key)
            validated_providers[provider] = status
        else:
            status = _validate_provider_basic(provider, api_key)
            validated_providers[provider] = status

    return validated_providers
