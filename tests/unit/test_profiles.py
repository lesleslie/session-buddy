"""Unit tests for MCP tool profiles.

Updated for W0 (mcp-common>=0.18.0) refactor:
- ``FULL_REGISTRATIONS`` removed; FULL uses ``ALL_TOOLS`` sentinel and
  ``REGISTRATION_MAP`` keys define the actual full set.
- ``MANDATORY_REGISTRATIONS`` list replaced with ``SESSION_BUDDY_MANDATORY_GROUPS``
  set; mandatory groups are NOT in MINIMAL_REGISTRATIONS to avoid duplicate
  registration (the W0 helper re-registers them at every profile).
- MINIMAL_REGISTRATIONS no longer contains ``register_health_tools_sb``
  (moved to SESSION_BUDDY_MANDATORY_GROUPS).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from mcp_common.tools import ToolProfile
from mcp_common.tools.dispatch import ALL_TOOLS

from session_buddy.mcp.tools.profiles import (
    PROFILE_REGISTRATIONS,
    REGISTRATION_MAP,
    SESSION_BUDDY_MANDATORY_GROUPS,
    MINIMAL_REGISTRATIONS,
    STANDARD_REGISTRATIONS,
    get_active_profile,
)


class TestProfileConstants:
    """Test suite for profile registration constants."""

    def test_minimal_registrations_count(self):
        """MINIMAL has the 3 base registrations (health moved to mandatory)."""
        assert len(MINIMAL_REGISTRATIONS) == 3

    def test_minimal_excludes_health(self):
        """MINIMAL must NOT include health (the W0 helper would double-register)."""
        assert "register_health_tools_sb" not in MINIMAL_REGISTRATIONS

    def test_minimal_contains_session_tools(self):
        """MINIMAL includes session lifecycle tools."""
        assert "register_session_tools" in MINIMAL_REGISTRATIONS

    def test_minimal_contains_search_tools(self):
        """MINIMAL includes basic search tools."""
        assert "register_search_tools" in MINIMAL_REGISTRATIONS

    def test_minimal_contains_hooks_tools(self):
        """MINIMAL includes pre-compact hooks tools."""
        assert "register_hooks_tools" in MINIMAL_REGISTRATIONS

    def test_standard_registrations_count(self):
        """STANDARD = MINIMAL + 12 additional."""
        assert len(STANDARD_REGISTRATIONS) == len(MINIMAL_REGISTRATIONS) + 12

    def test_standard_includes_minimal(self):
        """STANDARD includes all MINIMAL registrations."""
        for reg in MINIMAL_REGISTRATIONS:
            assert reg in STANDARD_REGISTRATIONS

    def test_standard_excludes_health(self):
        """STANDARD must NOT include health (same dedup rule as MINIMAL)."""
        assert "register_health_tools_sb" not in STANDARD_REGISTRATIONS

    def test_standard_has_conversation_tools(self):
        assert "register_conversation_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_extraction_tools(self):
        assert "register_extraction_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_knowledge_graph_tools(self):
        assert "register_knowledge_graph_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_cache_tools(self):
        assert "register_cache_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_intent_tools(self):
        assert "register_intent_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_crackerjack_tools(self):
        assert "register_crackerjack_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_feature_flags_tools(self):
        assert "register_feature_flags_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_monitoring_tools(self):
        assert "register_monitoring_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_access_log_tools(self):
        assert "register_access_log_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_channel_tracking_tools(self):
        assert "register_channel_tracking_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_channel_session_state_tools(self):
        assert "register_channel_session_state_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_cross_repo_work_tools(self):
        assert "register_cross_repo_work_tools" in STANDARD_REGISTRATIONS


class TestRegistrationMap:
    """REGISTRATION_MAP must contain every group key consumed by the W0 helper."""

    def test_registration_map_includes_minimal_groups(self):
        """Every MINIMAL registration key must resolve in REGISTRATION_MAP."""
        for reg in MINIMAL_REGISTRATIONS:
            assert reg in REGISTRATION_MAP, (
                f"MINIMAL registration {reg!r} missing from REGISTRATION_MAP"
            )

    def test_registration_map_includes_standard_groups(self):
        """Every STANDARD registration key must resolve in REGISTRATION_MAP."""
        for reg in STANDARD_REGISTRATIONS:
            assert reg in REGISTRATION_MAP, (
                f"STANDARD registration {reg!r} missing from REGISTRATION_MAP"
            )

    def test_registration_map_includes_mandatory_groups(self):
        """Every mandatory group must resolve in REGISTRATION_MAP."""
        for reg in SESSION_BUDDY_MANDATORY_GROUPS:
            assert reg in REGISTRATION_MAP, (
                f"Mandatory group {reg!r} missing from REGISTRATION_MAP"
            )

    def test_registration_map_values_are_callables(self):
        """Every REGISTRATION_MAP value must be a callable the W0 helper can invoke."""
        for name, fn in REGISTRATION_MAP.items():
            assert callable(fn), f"REGISTRATION_MAP[{name!r}] is not callable: {fn!r}"

    def test_full_expected_keys_present(self):
        """FULL groups (all the legacy FULL_REGISTRATIONS entries) are in REGISTRATION_MAP.

        After the W0 refactor, FULL is the union of REGISTRATION_MAP minus the
        mandatory groups (the helper re-registers mandatory groups separately).
        We assert the FULL-only additions are present so a future drop is caught.
        """
        expected_full_additions = {
            "register_admin_shell_tracking_tools",
            "register_akosha_tools",
            "register_bottleneck_tools",
            "register_code_analysis_tools",
            "register_code_graph_tools",
            "register_conscious_agent_tools",
            "register_export_tools",
            "register_llm_tools",
            "register_memory_health_tools",
            "register_migration_tools",
            "register_phase3_knowledge_graph_tools",
            "register_phase4_tools",
            "register_pool_tools",
            "register_prometheus_metrics_tools",
            "register_prompt_tools",
            "register_serverless_tools",
            "register_session_analytics_tools",
            "register_team_tools",
            "register_workflow_metrics_tools",
            "register_worktree_tools",
        }
        missing = expected_full_additions - set(REGISTRATION_MAP.keys())
        assert not missing, f"FULL-only registration keys missing: {missing}"


class TestProfileRegistrationsMapping:
    """PROFILE_REGISTRATIONS mapping is well-formed."""

    def test_profile_registrations_has_three_entries(self):
        assert len(PROFILE_REGISTRATIONS) == 3

    def test_minimal_mapping(self):
        assert PROFILE_REGISTRATIONS[ToolProfile.MINIMAL] == MINIMAL_REGISTRATIONS

    def test_standard_mapping(self):
        assert PROFILE_REGISTRATIONS[ToolProfile.STANDARD] == STANDARD_REGISTRATIONS

    def test_full_mapping_uses_all_tools(self):
        """FULL must use the ALL_TOOLS sentinel so register_all_fn drives the loop."""
        assert PROFILE_REGISTRATIONS[ToolProfile.FULL] is ALL_TOOLS

    def test_minimal_registrations_is_shortest(self):
        assert len(MINIMAL_REGISTRATIONS) < len(STANDARD_REGISTRATIONS)


class TestMandatoryRegistrations:
    """Mandatory registrations use the W0 helper's mandatory_groups parameter."""

    def test_mandatory_groups_count(self):
        """MANDATORY_GROUPS has exactly one registration (health)."""
        assert len(SESSION_BUDDY_MANDATORY_GROUPS) == 1

    def test_mandatory_contains_health_tools(self):
        assert "register_health_tools_sb" in SESSION_BUDDY_MANDATORY_GROUPS

    def test_mandatory_not_in_minimal(self):
        """MANDATORY groups must NOT be duplicated in MINIMAL_REGISTRATIONS."""
        overlap = SESSION_BUDDY_MANDATORY_GROUPS & set(MINIMAL_REGISTRATIONS)
        assert not overlap, (
            f"MANDATORY groups {overlap} duplicated in MINIMAL_REGISTRATIONS"
        )

    def test_mandatory_not_in_standard(self):
        """MANDATORY groups must NOT be duplicated in STANDARD_REGISTRATIONS."""
        overlap = SESSION_BUDDY_MANDATORY_GROUPS & set(STANDARD_REGISTRATIONS)
        assert not overlap


class TestGetActiveProfile:
    """get_active_profile() reads the env var correctly."""

    def test_get_active_profile_default_full(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_active_profile() == ToolProfile.FULL

    def test_get_active_profile_minimal(self):
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "minimal"}):
            assert get_active_profile() == ToolProfile.MINIMAL

    def test_get_active_profile_standard(self):
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "standard"}):
            assert get_active_profile() == ToolProfile.STANDARD

    def test_get_active_profile_full(self):
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "full"}):
            assert get_active_profile() == ToolProfile.FULL

    def test_get_active_profile_case_insensitive(self):
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "MINIMAL"}):
            assert get_active_profile() == ToolProfile.MINIMAL

    def test_get_active_profile_invalid_value_falls_back_to_full(self):
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "invalid_profile"}):
            assert get_active_profile() == ToolProfile.FULL

    def test_get_active_profile_empty_string_falls_back_to_full(self):
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": ""}):
            assert get_active_profile() == ToolProfile.FULL

    def test_get_active_profile_custom_env_var(self):
        with patch.dict(os.environ, {"MY_CUSTOM_PROFILE": "standard"}):
            assert get_active_profile(env_var="MY_CUSTOM_PROFILE") == ToolProfile.STANDARD

    def test_get_active_profile_whitespace_value_falls_back_to_full(self):
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "   "}):
            assert get_active_profile() == ToolProfile.FULL


class TestProfileRegistrationLogic:
    """Registration lists are well-formed strings."""

    def test_minimal_registrations_are_all_valid_strings(self):
        for reg in MINIMAL_REGISTRATIONS:
            assert isinstance(reg, str)
            assert len(reg) > 0
            assert reg.startswith("register_")

    def test_standard_registrations_are_all_valid_strings(self):
        for reg in STANDARD_REGISTRATIONS:
            assert isinstance(reg, str)
            assert len(reg) > 0
            assert reg.startswith("register_")

    def test_no_duplicate_registrations_in_minimal(self):
        assert len(MINIMAL_REGISTRATIONS) == len(set(MINIMAL_REGISTRATIONS))

    def test_no_duplicate_registrations_in_standard(self):
        assert len(STANDARD_REGISTRATIONS) == len(set(STANDARD_REGISTRATIONS))

    def test_registrations_list_is_not_empty(self):
        assert len(MINIMAL_REGISTRATIONS) > 0
        assert len(STANDARD_REGISTRATIONS) > 0
        assert len(REGISTRATION_MAP) > 0


class TestProfileInheritance:
    """Profile tier relationships (cumulative nature)."""

    def test_minimal_is_subset_of_standard(self):
        assert set(MINIMAL_REGISTRATIONS).issubset(set(STANDARD_REGISTRATIONS))

    def test_minimal_is_subset_of_registration_map(self):
        assert set(MINIMAL_REGISTRATIONS).issubset(set(REGISTRATION_MAP.keys()))

    def test_standard_is_subset_of_registration_map(self):
        assert set(STANDARD_REGISTRATIONS).issubset(set(REGISTRATION_MAP.keys()))

    def test_profile_tier_progression(self):
        assert len(MINIMAL_REGISTRATIONS) < len(STANDARD_REGISTRATIONS)

    def test_each_higher_tier_adds_registrations(self):
        """STANDARD adds these 12 to MINIMAL."""
        standard_only = set(STANDARD_REGISTRATIONS) - set(MINIMAL_REGISTRATIONS)
        expected_standard_additions = {
            "register_conversation_tools",
            "register_extraction_tools",
            "register_knowledge_graph_tools",
            "register_cache_tools",
            "register_intent_tools",
            "register_crackerjack_tools",
            "register_feature_flags_tools",
            "register_monitoring_tools",
            "register_access_log_tools",
            "register_channel_session_state_tools",
            "register_channel_tracking_tools",
            "register_cross_repo_work_tools",
        }
        assert standard_only == expected_standard_additions