"""Unit tests for MCP tool profiles."""

import os
from unittest.mock import patch

import pytest
from mcp_common.tools import ToolProfile

from session_buddy.mcp.tools.profiles import (
    FULL_REGISTRATIONS,
    MANDATORY_REGISTRATIONS,
    MINIMAL_REGISTRATIONS,
    PROFILE_REGISTRATIONS,
    STANDARD_REGISTRATIONS,
    get_active_profile,
)


class TestProfileConstants:
    """Test suite for profile registration constants."""

    def test_minimal_registrations_count(self):
        """Test MINIMAL has expected number of registrations."""
        assert len(MINIMAL_REGISTRATIONS) == 4

    def test_minimal_contains_health_tools(self):
        """Test MINIMAL includes health tools registration."""
        assert "register_health_tools_sb" in MINIMAL_REGISTRATIONS

    def test_minimal_contains_session_tools(self):
        """Test MINIMAL includes session tools registration."""
        assert "register_session_tools" in MINIMAL_REGISTRATIONS

    def test_minimal_contains_search_tools(self):
        """Test MINIMAL includes search tools registration."""
        assert "register_search_tools" in MINIMAL_REGISTRATIONS

    def test_minimal_contains_hooks_tools(self):
        """Test MINIMAL includes hooks tools registration."""
        assert "register_hooks_tools" in MINIMAL_REGISTRATIONS

    def test_standard_registrations_count(self):
        """Test STANDARD has expected number of registrations."""
        # STANDARD = MINIMAL + 9 additional
        assert len(STANDARD_REGISTRATIONS) == len(MINIMAL_REGISTRATIONS) + 9

    def test_standard_includes_minimal(self):
        """Test STANDARD includes all MINIMAL registrations."""
        for reg in MINIMAL_REGISTRATIONS:
            assert reg in STANDARD_REGISTRATIONS

    def test_standard_has_conversation_tools(self):
        """Test STANDARD includes conversation tools."""
        assert "register_conversation_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_extraction_tools(self):
        """Test STANDARD includes extraction tools."""
        assert "register_extraction_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_knowledge_graph_tools(self):
        """Test STANDARD includes knowledge graph tools."""
        assert "register_knowledge_graph_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_cache_tools(self):
        """Test STANDARD includes cache tools."""
        assert "register_cache_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_intent_tools(self):
        """Test STANDARD includes intent tools."""
        assert "register_intent_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_crackerjack_tools(self):
        """Test STANDARD includes crackerjack tools."""
        assert "register_crackerjack_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_feature_flags_tools(self):
        """Test STANDARD includes feature flags tools."""
        assert "register_feature_flags_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_monitoring_tools(self):
        """Test STANDARD includes monitoring tools."""
        assert "register_monitoring_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_access_log_tools(self):
        """Test STANDARD includes access log tools."""
        assert "register_access_log_tools" in STANDARD_REGISTRATIONS

    def test_standard_has_channel_tracking_tools(self):
        """Test STANDARD includes channel tracking tools."""
        assert "register_channel_tracking_tools" in STANDARD_REGISTRATIONS

    def test_full_registrations_count(self):
        """Test FULL has expected number of registrations."""
        # FULL = STANDARD + 16 additional
        expected_full_count = len(STANDARD_REGISTRATIONS) + 16
        assert len(FULL_REGISTRATIONS) == expected_full_count

    def test_full_includes_standard(self):
        """Test FULL includes all STANDARD registrations."""
        for reg in STANDARD_REGISTRATIONS:
            assert reg in FULL_REGISTRATIONS

    def test_full_has_bottleneck_tools(self):
        """Test FULL includes bottleneck tools."""
        assert "register_bottleneck_tools" in FULL_REGISTRATIONS

    def test_full_has_session_analytics_tools(self):
        """Test FULL includes session analytics tools."""
        assert "register_session_analytics_tools" in FULL_REGISTRATIONS

    def test_full_has_workflow_metrics_tools(self):
        """Test FULL includes workflow metrics tools."""
        assert "register_workflow_metrics_tools" in FULL_REGISTRATIONS

    def test_full_has_memory_health_tools(self):
        """Test FULL includes memory health tools."""
        assert "register_memory_health_tools" in FULL_REGISTRATIONS

    def test_full_has_phase3_knowledge_graph_tools(self):
        """Test FULL includes phase3 knowledge graph tools."""
        assert "register_phase3_knowledge_graph_tools" in FULL_REGISTRATIONS

    def test_full_has_phase4_tools(self):
        """Test FULL includes phase4 tools."""
        assert "register_phase4_tools" in FULL_REGISTRATIONS

    def test_full_has_conscious_agent_tools(self):
        """Test FULL includes conscious agent tools."""
        assert "register_conscious_agent_tools" in FULL_REGISTRATIONS

    def test_full_has_migration_tools(self):
        """Test FULL includes migration tools."""
        assert "register_migration_tools" in FULL_REGISTRATIONS

    def test_full_has_pool_tools(self):
        """Test FULL includes pool tools."""
        assert "register_pool_tools" in FULL_REGISTRATIONS

    def test_full_has_serverless_tools(self):
        """Test FULL includes serverless tools."""
        assert "register_serverless_tools" in FULL_REGISTRATIONS

    def test_full_has_team_tools(self):
        """Test FULL includes team tools."""
        assert "register_team_tools" in FULL_REGISTRATIONS

    def test_full_has_llm_tools(self):
        """Test FULL includes LLM tools."""
        assert "register_llm_tools" in FULL_REGISTRATIONS

    def test_full_has_prompt_tools(self):
        """Test FULL includes prompt tools."""
        assert "register_prompt_tools" in FULL_REGISTRATIONS

    def test_full_has_code_graph_tools(self):
        """Test FULL includes code graph tools."""
        assert "register_code_graph_tools" in FULL_REGISTRATIONS

    def test_full_has_code_analysis_tools(self):
        """Test FULL includes code analysis tools."""
        assert "register_code_analysis_tools" in FULL_REGISTRATIONS

    def test_full_has_admin_shell_tracking_tools(self):
        """Test FULL includes admin shell tracking tools."""
        assert "register_admin_shell_tracking_tools" in FULL_REGISTRATIONS

    def test_full_has_akosha_tools(self):
        """Test FULL includes akosha tools."""
        assert "register_akosha_tools" in FULL_REGISTRATIONS

    def test_full_has_prometheus_metrics_tools(self):
        """Test FULL includes prometheus metrics tools."""
        assert "register_prometheus_metrics_tools" in FULL_REGISTRATIONS


class TestProfileRegistrationsMapping:
    """Test suite for PROFILE_REGISTRATIONS mapping."""

    def test_profile_registrations_has_three_entries(self):
        """Test PROFILE_REGISTRATIONS has entries for all three profiles."""
        assert len(PROFILE_REGISTRATIONS) == 3

    def test_minimal_mapping(self):
        """Test MINIMAL profile maps to MINIMAL_REGISTRATIONS."""
        assert PROFILE_REGISTRATIONS[ToolProfile.MINIMAL] == MINIMAL_REGISTRATIONS

    def test_standard_mapping(self):
        """Test STANDARD profile maps to STANDARD_REGISTRATIONS."""
        assert PROFILE_REGISTRATIONS[ToolProfile.STANDARD] == STANDARD_REGISTRATIONS

    def test_full_mapping(self):
        """Test FULL profile maps to FULL_REGISTRATIONS."""
        assert PROFILE_REGISTRATIONS[ToolProfile.FULL] == FULL_REGISTRATIONS

    def test_minimal_registrations_is_shortest(self):
        """Test MINIMAL has fewer registrations than STANDARD."""
        assert len(MINIMAL_REGISTRATIONS) < len(STANDARD_REGISTRATIONS)

    def test_standard_registrations_is_shorter_than_full(self):
        """Test STANDARD has fewer registrations than FULL."""
        assert len(STANDARD_REGISTRATIONS) < len(FULL_REGISTRATIONS)


class TestMandatoryRegistrations:
    """Test suite for mandatory registrations."""

    def test_mandatory_registrations_count(self):
        """Test MANDATORY has exactly one registration."""
        assert len(MANDATORY_REGISTRATIONS) == 1

    def test_mandatory_contains_health_tools(self):
        """Test MANDATORY includes health tools registration."""
        assert "register_health_tools_sb" in MANDATORY_REGISTRATIONS

    def test_mandatory_is_in_minimal(self):
        """Test mandatory registration is always included in MINIMAL."""
        assert "register_health_tools_sb" in MINIMAL_REGISTRATIONS


class TestGetActiveProfile:
    """Test suite for get_active_profile() function."""

    def test_get_active_profile_default_full(self):
        """Test default profile is FULL when env var is not set."""
        with patch.dict(os.environ, {}, clear=True):
            profile = get_active_profile()
            assert profile == ToolProfile.FULL

    def test_get_active_profile_minimal(self):
        """Test profile is MINIMAL when env var is set to minimal."""
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "minimal"}):
            profile = get_active_profile()
            assert profile == ToolProfile.MINIMAL

    def test_get_active_profile_standard(self):
        """Test profile is STANDARD when env var is set to standard."""
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "standard"}):
            profile = get_active_profile()
            assert profile == ToolProfile.STANDARD

    def test_get_active_profile_full(self):
        """Test profile is FULL when env var is set to full."""
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "full"}):
            profile = get_active_profile()
            assert profile == ToolProfile.FULL

    def test_get_active_profile_case_insensitive(self):
        """Test profile parsing is case-insensitive."""
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "MINIMAL"}):
            profile = get_active_profile()
            assert profile == ToolProfile.MINIMAL

    def test_get_active_profile_invalid_value_falls_back_to_full(self):
        """Test invalid env var value falls back to FULL."""
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "invalid_profile"}):
            profile = get_active_profile()
            assert profile == ToolProfile.FULL

    def test_get_active_profile_empty_string_falls_back_to_full(self):
        """Test empty env var value falls back to FULL."""
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": ""}):
            profile = get_active_profile()
            assert profile == ToolProfile.FULL

    def test_get_active_profile_custom_env_var(self):
        """Test custom environment variable name can be used."""
        with patch.dict(os.environ, {"MY_CUSTOM_PROFILE": "standard"}):
            profile = get_active_profile(env_var="MY_CUSTOM_PROFILE")
            assert profile == ToolProfile.STANDARD

    def test_get_active_profile_whitespace_value_falls_back_to_full(self):
        """Test whitespace-only env var value falls back to FULL."""
        with patch.dict(os.environ, {"SESSION_BUDDY_TOOL_PROFILE": "   "}):
            profile = get_active_profile()
            assert profile == ToolProfile.FULL


class TestProfileRegistrationLogic:
    """Test suite for profile registration logic."""

    def test_minimal_registrations_are_all_valid_strings(self):
        """Test all MINIMAL registrations are non-empty strings."""
        for reg in MINIMAL_REGISTRATIONS:
            assert isinstance(reg, str)
            assert len(reg) > 0
            assert reg.startswith("register_")

    def test_standard_registrations_are_all_valid_strings(self):
        """Test all STANDARD registrations are non-empty strings."""
        for reg in STANDARD_REGISTRATIONS:
            assert isinstance(reg, str)
            assert len(reg) > 0
            assert reg.startswith("register_")

    def test_full_registrations_are_all_valid_strings(self):
        """Test all FULL registrations are non-empty strings."""
        for reg in FULL_REGISTRATIONS:
            assert isinstance(reg, str)
            assert len(reg) > 0
            assert reg.startswith("register_")

    def test_no_duplicate_registrations_in_minimal(self):
        """Test MINIMAL has no duplicate registrations."""
        assert len(MINIMAL_REGISTRATIONS) == len(set(MINIMAL_REGISTRATIONS))

    def test_no_duplicate_registrations_in_standard(self):
        """Test STANDARD has no duplicate registrations."""
        assert len(STANDARD_REGISTRATIONS) == len(set(STANDARD_REGISTRATIONS))

    def test_no_duplicate_registrations_in_full(self):
        """Test FULL has no duplicate registrations."""
        assert len(FULL_REGISTRATIONS) == len(set(FULL_REGISTRATIONS))

    def test_registrations_list_is_not_empty(self):
        """Test all registration lists contain at least one item."""
        assert len(MINIMAL_REGISTRATIONS) > 0
        assert len(STANDARD_REGISTRATIONS) > 0
        assert len(FULL_REGISTRATIONS) > 0

    def test_registrations_are_sorted_alphabetically_within_profile(self):
        """Test registrations within each profile are sorted alphabetically."""
        assert MINIMAL_REGISTRATIONS == sorted(MINIMAL_REGISTRATIONS)
        assert STANDARD_REGISTRATIONS == sorted(STANDARD_REGISTRATIONS)
        assert FULL_REGISTRATIONS == sorted(FULL_REGISTRATIONS)


class TestProfileInheritance:
    """Test suite for profile inheritance (cumulative nature)."""

    def test_minimal_is_subset_of_standard(self):
        """Test MINIMAL registrations are a subset of STANDARD."""
        minimal_set = set(MINIMAL_REGISTRATIONS)
        standard_set = set(STANDARD_REGISTRATIONS)
        assert minimal_set.issubset(standard_set)

    def test_minimal_is_subset_of_full(self):
        """Test MINIMAL registrations are a subset of FULL."""
        minimal_set = set(MINIMAL_REGISTRATIONS)
        full_set = set(FULL_REGISTRATIONS)
        assert minimal_set.issubset(full_set)

    def test_standard_is_subset_of_full(self):
        """Test STANDARD registrations are a subset of FULL."""
        standard_set = set(STANDARD_REGISTRATIONS)
        full_set = set(FULL_REGISTRATIONS)
        assert standard_set.issubset(full_set)

    def test_profile_tier_progression(self):
        """Test tier progression: MINIMAL < STANDARD < FULL in size."""
        assert len(MINIMAL_REGISTRATIONS) < len(STANDARD_REGISTRATIONS)
        assert len(STANDARD_REGISTRATIONS) < len(FULL_REGISTRATIONS)

    def test_each_higher_tier_adds_registrations(self):
        """Test each higher tier adds registrations not in lower tier."""
        # STANDARD adds these to MINIMAL
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
            "register_channel_tracking_tools",
        }
        assert standard_only == expected_standard_additions

        # FULL adds these to STANDARD
        full_only = set(FULL_REGISTRATIONS) - set(STANDARD_REGISTRATIONS)
        expected_full_additions = {
            "register_bottleneck_tools",
            "register_session_analytics_tools",
            "register_workflow_metrics_tools",
            "register_memory_health_tools",
            "register_phase3_knowledge_graph_tools",
            "register_phase4_tools",
            "register_conscious_agent_tools",
            "register_migration_tools",
            "register_pool_tools",
            "register_serverless_tools",
            "register_team_tools",
            "register_llm_tools",
            "register_prompt_tools",
            "register_code_graph_tools",
            "register_code_analysis_tools",
            "register_admin_shell_tracking_tools",
            "register_akosha_tools",
            "register_prometheus_metrics_tools",
        }
        assert full_only == expected_full_additions
