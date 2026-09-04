from __future__ import annotations

from mcp_common.tools import ToolProfile
from mcp_common.tools.dispatch import ALL_TOOLS


def test_profile_constants_and_active_profile() -> None:
    from session_buddy.mcp.tools.profiles import (
        REGISTRATION_MAP,
        SESSION_BUDDY_MANDATORY_GROUPS,
        MINIMAL_REGISTRATIONS,
        PROFILE_REGISTRATIONS,
        STANDARD_REGISTRATIONS,
        get_active_profile,
    )

    # MINIMAL no longer has health as the first entry; health moved to
    # SESSION_BUDDY_MANDATORY_GROUPS so the W0 helper re-registers it
    # at every profile.
    assert MINIMAL_REGISTRATIONS[0] == "register_session_tools"
    assert "register_feature_flags_tools" in STANDARD_REGISTRATIONS
    # FULL used to be a list of names; after the W0 refactor it is the
    # ALL_TOOLS sentinel, and the actual FULL group set is the
    # REGISTRATION_MAP keys (minus the mandatory groups).
    assert "register_prometheus_metrics_tools" in REGISTRATION_MAP
    assert SESSION_BUDDY_MANDATORY_GROUPS == {
        "register_health_tools_sb",
        "register_baseline_tools",
    }
    assert PROFILE_REGISTRATIONS[ToolProfile.MINIMAL] == MINIMAL_REGISTRATIONS
    assert PROFILE_REGISTRATIONS[ToolProfile.STANDARD] == STANDARD_REGISTRATIONS
    assert PROFILE_REGISTRATIONS[ToolProfile.FULL] is ALL_TOOLS
    assert get_active_profile.__defaults__ == ("SESSION_BUDDY_TOOL_PROFILE",)
