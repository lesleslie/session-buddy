"""
Feature flags for Memori-inspired features and staged rollout.

Flags default to False for safe rollouts and can be enabled via:
- Environment variables (e.g., SESSION_BUDDY_ENABLE_CONSCIOUS_AGENT=true)
- YAML settings (settings/session-buddy.yaml or local.yaml)

Usage:
    from session_buddy.config.feature_flags import get_feature_flags
    flags = get_feature_flags()
    if flags.enable_conscious_agent:
        ...
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from session_buddy.settings import get_settings


@dataclass(slots=True)
class FeatureFlags:
    """Typed feature flags for staged enablement."""

    # Extraction cascade
    enable_llm_entity_extraction: bool = False
    enable_anthropic: bool = False
    enable_ollama: bool = False

    # Background optimization
    enable_conscious_agent: bool = False

    # Filesystem integration
    enable_filesystem_extraction: bool = False

    # === Quality scoring (crackerjack CLI fallback) ===
    enable_crackerjack_fallback: bool = False


_ENV_BOOL = {
    "true": True,
    "1": True,
    "yes": True,
    "on": True,
    "false": False,
    "0": False,
    "no": False,
    "off": False,
}


def _get_env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return _ENV_BOOL.get(val.strip().lower(), default)


def get_feature_flags() -> FeatureFlags:
    """Load flags from settings with env overrides.

    Order of precedence:
    1) Environment variables (SESSION_BUDDY_*)
    2) YAML settings via MCPBaseSettings
    3) Defaults (all False)
    """
    settings = get_settings()

    # Base flags from settings if present (fallback False).
    # Reads from the nested groups on SessionBuddySettings
    # (added 2026-10-04). The legacy flat
    # ``getattr(settings, "enable_<flag>", False)`` pattern silently
    # returned False after the schema reshape.
    base = FeatureFlags(
        enable_llm_entity_extraction=bool(
            settings.entity_extraction.enable
        ),
        enable_anthropic=bool(settings.feature_flags.enable_anthropic),
        enable_ollama=bool(settings.feature_flags.enable_ollama),
        enable_conscious_agent=bool(
            settings.feature_flags.enable_conscious_agent
        ),
        enable_filesystem_extraction=bool(
            settings.feature_flags.enable_filesystem_extraction
        ),
        enable_crackerjack_fallback=bool(
            settings.feature_flags.enable_crackerjack_fallback
        ),
    )

    # Env overrides
    return FeatureFlags(
        enable_llm_entity_extraction=_get_env_bool(
            "SESSION_BUDDY_ENABLE_LLM_ENTITY_EXTRACTION",
            base.enable_llm_entity_extraction,
        ),
        enable_anthropic=_get_env_bool(
            "SESSION_BUDDY_ENABLE_ANTHROPIC", base.enable_anthropic
        ),
        enable_ollama=_get_env_bool("SESSION_BUDDY_ENABLE_OLLAMA", base.enable_ollama),
        enable_conscious_agent=_get_env_bool(
            "SESSION_BUDDY_ENABLE_CONSCIOUS_AGENT", base.enable_conscious_agent
        ),
        enable_filesystem_extraction=_get_env_bool(
            "SESSION_BUDDY_ENABLE_FILESYSTEM_EXTRACTION",
            base.enable_filesystem_extraction,
        ),
        enable_crackerjack_fallback=_get_env_bool(
            "SESSION_BUDDY_CRACKERJACK_FALLBACK", base.enable_crackerjack_fallback
        ),
    )


__all__ = ["FeatureFlags", "get_feature_flags"]
