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
    # (added 2026-10-04). Uses ``getattr`` with a default so tests
    # that pass a SimpleNamespace with only some attributes don't
    # raise AttributeError (the legacy flat ``getattr`` pattern
    # silently returned False for missing keys; preserve that
    # fallback behavior at the nested level too).
    def _read_attr(obj, *names: str, default: bool = False) -> bool:
        """Read nested attribute or fall back to default.

        ``names`` is a chain like ``"feature_flags"``, ``"enable_anthropic"`` —
        walks the path, returns ``default`` at the first miss. If the
        nested walk fails, fall back to the legacy flat-name lookup
        (``obj.enable_anthropic`` — the last name only) so tests
        that pass a SimpleNamespace with the old flat shape still
        work.
    """
        cur = obj
        for name in names:
            cur = getattr(cur, name, default)
            if cur is default:
                # Fall back: try the leaf name as a flat attribute.
                return bool(getattr(obj, names[-1], default))
        return bool(cur)

    base = FeatureFlags(
        enable_llm_entity_extraction=_read_attr(
            settings, "entity_extraction", "enable"
        ),
        enable_anthropic=_read_attr(
            settings, "feature_flags", "enable_anthropic"
        ),
        enable_ollama=_read_attr(
            settings, "feature_flags", "enable_ollama"
        ),
        enable_conscious_agent=_read_attr(
            settings, "feature_flags", "enable_conscious_agent"
        ),
        enable_filesystem_extraction=_read_attr(
            settings, "feature_flags", "enable_filesystem_extraction"
        ),
        enable_crackerjack_fallback=_read_attr(
            settings, "feature_flags", "enable_crackerjack_fallback"
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
