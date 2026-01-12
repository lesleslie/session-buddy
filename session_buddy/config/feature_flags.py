"""
Feature flags for Memori-inspired features and staged rollout.

Flags default to False for safe rollouts and can be enabled via:
- Environment variables (e.g., SESSION_BUDDY_USE_SCHEMA_V2=true)
- YAML settings (settings/session-buddy.yaml or local.yaml)

Usage:
    from session_buddy.config.feature_flags import get_feature_flags
    flags = get_feature_flags()
    if flags.use_schema_v2:
        ...
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from session_buddy.settings import get_settings


@dataclass(slots=True)
class FeatureFlags:
    """Typed feature flags for staged enablement."""

    # Storage + schema
    use_schema_v2: bool = False

    # Extraction cascade
    enable_llm_entity_extraction: bool = False
    enable_anthropic: bool = False
    enable_ollama: bool = False

    # Background optimization
    enable_conscious_agent: bool = False

    # Filesystem integration
    enable_filesystem_extraction: bool = False


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
    1) Environment variables (SESSION_MGMT_*)
    2) YAML settings via MCPBaseSettings
    3) Defaults (all False)
    """
    settings = get_settings()

    # Base flags from settings if present (fallback False)
    base = FeatureFlags(
        use_schema_v2=bool(getattr(settings, "use_schema_v2", False)),
        enable_llm_entity_extraction=bool(
            getattr(settings, "enable_llm_entity_extraction", False)
        ),
        enable_anthropic=bool(getattr(settings, "enable_anthropic", False)),
        enable_ollama=bool(getattr(settings, "enable_ollama", False)),
        enable_conscious_agent=bool(getattr(settings, "enable_conscious_agent", False)),
        enable_filesystem_extraction=bool(
            getattr(settings, "enable_filesystem_extraction", False)
        ),
    )

    # Env overrides
    return FeatureFlags(
        use_schema_v2=_get_env_bool("SESSION_MGMT_USE_SCHEMA_V2", base.use_schema_v2),
        enable_llm_entity_extraction=_get_env_bool(
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            base.enable_llm_entity_extraction,
        ),
        enable_anthropic=_get_env_bool(
            "SESSION_MGMT_ENABLE_ANTHROPIC", base.enable_anthropic
        ),
        enable_ollama=_get_env_bool("SESSION_MGMT_ENABLE_OLLAMA", base.enable_ollama),
        enable_conscious_agent=_get_env_bool(
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT", base.enable_conscious_agent
        ),
        enable_filesystem_extraction=_get_env_bool(
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
            base.enable_filesystem_extraction,
        ),
    )


__all__ = ["FeatureFlags", "get_feature_flags"]
