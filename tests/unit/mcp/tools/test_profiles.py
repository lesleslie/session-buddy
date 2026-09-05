"""Tests for ``session_buddy.mcp.tools.profiles``.

Covers:
- ``MINIMAL_REGISTRATIONS``, ``STANDARD_REGISTRATIONS``, ``ALL_TOOLS``
  membership invariants
- ``PROFILE_REGISTRATIONS`` mapping for ``ToolProfile.MINIMAL/STANDARD/FULL``
- ``SESSION_BUDDY_MANDATORY_GROUPS`` contents
- ``REGISTRATION_MAP`` keys/values
- ``get_active_profile`` env-var resolution
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from mcp_common.tools import ToolProfile
from mcp_common.tools.dispatch import ALL_TOOLS

from session_buddy.mcp.tools import profiles as profiles_mod


# ---------------------------------------------------------------------------
# Constants — content invariants
# ---------------------------------------------------------------------------


def test_minimal_registrations_contains_expected_core() -> None:
    """MINIMAL_REGISTRATIONS contains session/search/hooks."""
    items = list(profiles_mod.MINIMAL_REGISTRATIONS)
    assert "register_session_tools" in items
    assert "register_search_tools" in items
    assert "register_hooks_tools" in items


def test_standard_registrations_superset_of_minimal() -> None:
    """STANDARD_REGISTRATIONS starts with the minimal list."""
    minimal = list(profiles_mod.MINIMAL_REGISTRATIONS)
    standard = list(profiles_mod.STANDARD_REGISTRATIONS)
    assert standard[: len(minimal)] == minimal


def test_standard_registrations_adds_more_groups() -> None:
    """STANDARD_REGISTRATIONS adds additional register_* functions."""
    extras = set(profiles_mod.STANDARD_REGISTRATIONS) - set(
        profiles_mod.MINIMAL_REGISTRATIONS
    )
    # At least one expected non-minimal entry
    assert "register_conversation_tools" in extras
    assert "register_cache_tools" in extras
    assert "register_monitoring_tools" in extras


def test_full_profile_uses_all_tools_sentinel() -> None:
    """FULL profile uses the ALL_TOOLS sentinel rather than a per-tool list."""
    assert profiles_mod.PROFILE_REGISTRATIONS[ToolProfile.FULL] is ALL_TOOLS


def test_profile_registrations_keys_match_toolprofile_members() -> None:
    """PROFILE_REGISTRATIONS keys include every ToolProfile value."""
    keys = set(profiles_mod.PROFILE_REGISTRATIONS)
    assert ToolProfile.MINIMAL in keys
    assert ToolProfile.STANDARD in keys
    assert ToolProfile.FULL in keys


def test_minimal_and_standard_are_lists() -> None:
    """MINIMAL/STANDARD profiles map to list-typed registration lists."""
    assert isinstance(profiles_mod.PROFILE_REGISTRATIONS[ToolProfile.MINIMAL], list)
    assert isinstance(profiles_mod.PROFILE_REGISTRATIONS[ToolProfile.STANDARD], list)


# ---------------------------------------------------------------------------
# REGISTRATION_MAP
# ---------------------------------------------------------------------------


def test_registration_map_is_a_dict() -> None:
    """REGISTRATION_MAP is a dict."""
    assert isinstance(profiles_mod.REGISTRATION_MAP, dict)


def test_registration_map_contains_all_known_register_functions() -> None:
    """Every register_* listed in REGISTRATION_MAP is callable."""
    # Spot-check a few well-known entries
    assert "register_session_tools" in profiles_mod.REGISTRATION_MAP
    assert "register_search_tools" in profiles_mod.REGISTRATION_MAP
    assert "register_cache_tools" in profiles_mod.REGISTRATION_MAP
    assert "register_pool_tools" in profiles_mod.REGISTRATION_MAP
    assert "register_serverless_tools" in profiles_mod.REGISTRATION_MAP
    assert "register_health_tools_sb" in profiles_mod.REGISTRATION_MAP


def test_registration_map_values_are_callable() -> None:
    """Every value in REGISTRATION_MAP is a callable (per type annotation)."""
    for key, fn in profiles_mod.REGISTRATION_MAP.items():
        assert callable(fn), f"{key} is not callable"


def test_registration_map_has_baseline_wrapper() -> None:
    """register_baseline_tools is wired into REGISTRATION_MAP."""
    assert "register_baseline_tools" in profiles_mod.REGISTRATION_MAP
    assert callable(profiles_mod.REGISTRATION_MAP["register_baseline_tools"])


def test_registration_map_channel_tracking_uses_wrapper() -> None:
    """register_channel_tracking_tools is wrapped via _register_channel_tracking."""
    from session_buddy.mcp.tools.session.channel_tracking_tools import (
        register_channel_tracking_tools,
    )

    wrapper = profiles_mod.REGISTRATION_MAP["register_channel_tracking_tools"]
    # The wrapper pre-binds a Dhara publisher so it accepts just the server
    assert wrapper is not register_channel_tracking_tools
    assert wrapper is profiles_mod._register_channel_tracking


# ---------------------------------------------------------------------------
# Mandatory groups
# ---------------------------------------------------------------------------


def test_mandatory_groups_are_a_set() -> None:
    """SESSION_BUDDY_MANDATORY_GROUPS is a set per the spec."""
    assert isinstance(profiles_mod.SESSION_BUDDY_MANDATORY_GROUPS, set)


def test_mandatory_groups_include_baseline_and_health() -> None:
    """Health and baseline tools are always registered."""
    assert "register_baseline_tools" in profiles_mod.SESSION_BUDDY_MANDATORY_GROUPS
    assert "register_health_tools_sb" in profiles_mod.SESSION_BUDDY_MANDATORY_GROUPS


def test_mandatory_groups_subset_of_registration_map_keys() -> None:
    """Every mandatory group key must exist in REGISTRATION_MAP."""
    for group in profiles_mod.SESSION_BUDDY_MANDATORY_GROUPS:
        assert group in profiles_mod.REGISTRATION_MAP


# ---------------------------------------------------------------------------
# Dhara publisher wrapper
# ---------------------------------------------------------------------------


def test_dhara_publisher_built_at_module_load() -> None:
    """_dhara_publisher is created at module load time (may be None or an object)."""
    # The publisher is created via _make_dhara_publisher() at import time.
    # The factory is error-tolerant and may return None (no HTTP service configured).
    # We only verify the attribute exists; the value depends on environment.
    assert hasattr(profiles_mod, "_dhara_publisher")


def test_register_channel_tracking_wrapper_invokes_underlying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_register_channel_tracking forwards to register_channel_tracking_tools
    with the module-load Dhara publisher."""
    captured: dict[str, object] = {}

    class _ToolCapturingMCP:
        def tool(self):
            def decorator(fn):
                return fn

            return decorator

    def fake_register(server, dhara_publisher):
        captured["server"] = server
        captured["publisher"] = dhara_publisher

    # Patch the symbol bound in profiles' module namespace, not the original
    monkeypatch.setattr(profiles_mod, "register_channel_tracking_tools", fake_register)
    profiles_mod._register_channel_tracking(server=_ToolCapturingMCP())
    assert isinstance(captured["server"], _ToolCapturingMCP)
    # The publisher passed in is the one created at module load
    assert captured["publisher"] is profiles_mod._dhara_publisher


# ---------------------------------------------------------------------------
# get_active_profile
# ---------------------------------------------------------------------------


def test_get_active_profile_default() -> None:
    """Default env var is SESSION_BUDDY_TOOL_PROFILE."""
    with patch.dict("os.environ", {}, clear=False):
        # If unset, ToolProfile.from_env falls back to FULL
        os_environ_unset = {k: v for k, v in __import__("os").environ.items() if k != "SESSION_BUDDY_TOOL_PROFILE"}
        with patch.dict("os.environ", os_environ_unset, clear=True):
            result = profiles_mod.get_active_profile()
    assert isinstance(result, ToolProfile)


def test_get_active_profile_minimal() -> None:
    """Setting SESSION_BUDDY_TOOL_PROFILE=minimal returns MINIMAL."""
    with patch.dict(
        "os.environ", {"SESSION_BUDDY_TOOL_PROFILE": "minimal"}, clear=False
    ):
        assert profiles_mod.get_active_profile() is ToolProfile.MINIMAL


def test_get_active_profile_standard() -> None:
    """Setting SESSION_BUDDY_TOOL_PROFILE=standard returns STANDARD."""
    with patch.dict(
        "os.environ", {"SESSION_BUDDY_TOOL_PROFILE": "standard"}, clear=False
    ):
        assert profiles_mod.get_active_profile() is ToolProfile.STANDARD


def test_get_active_profile_full() -> None:
    """Setting SESSION_BUDDY_TOOL_PROFILE=full returns FULL."""
    with patch.dict(
        "os.environ", {"SESSION_BUDDY_TOOL_PROFILE": "full"}, clear=False
    ):
        assert profiles_mod.get_active_profile() is ToolProfile.FULL


def test_get_active_profile_custom_env_var() -> None:
    """get_active_profile reads the env var passed in (not the default)."""
    with patch.dict(
        "os.environ", {"MY_PROFILE_VAR": "minimal"}, clear=False
    ):
        result = profiles_mod.get_active_profile(env_var="MY_PROFILE_VAR")
    assert result is ToolProfile.MINIMAL


def test_get_active_profile_invalid_value_falls_back() -> None:
    """Invalid env value falls back via ToolProfile.from_env to FULL."""
    with patch.dict(
        "os.environ", {"SESSION_BUDDY_TOOL_PROFILE": "definitely-not-valid"}, clear=False
    ):
        result = profiles_mod.get_active_profile()
    # ToolProfile.from_env behaviour: invalid → FULL
    assert result is ToolProfile.FULL


# ---------------------------------------------------------------------------
# _make_dhara_publisher import check
# ---------------------------------------------------------------------------


def test_make_dhara_publisher_callable_from_module() -> None:
    """_make_dhara_publisher is importable from channel_tracking_tools."""
    from session_buddy.mcp.tools.session.channel_tracking_tools import (
        _make_dhara_publisher,
    )

    assert callable(_make_dhara_publisher)