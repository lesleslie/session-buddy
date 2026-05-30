from __future__ import annotations

from mcp_common.tools import ToolProfile


def test_profile_constants_and_active_profile() -> None:
    from session_buddy.mcp.tools.profiles import (
        FULL_REGISTRATIONS,
        MANDATORY_REGISTRATIONS,
        MINIMAL_REGISTRATIONS,
        PROFILE_REGISTRATIONS,
        STANDARD_REGISTRATIONS,
        get_active_profile,
    )

    assert MINIMAL_REGISTRATIONS[0] == "register_health_tools_sb"
    assert "register_feature_flags_tools" in STANDARD_REGISTRATIONS
    assert "register_prometheus_metrics_tools" in FULL_REGISTRATIONS
    assert MANDATORY_REGISTRATIONS == ["register_health_tools_sb"]
    assert PROFILE_REGISTRATIONS[ToolProfile.MINIMAL] == MINIMAL_REGISTRATIONS
    assert PROFILE_REGISTRATIONS[ToolProfile.STANDARD] == STANDARD_REGISTRATIONS
    assert PROFILE_REGISTRATIONS[ToolProfile.FULL] == FULL_REGISTRATIONS
    assert get_active_profile.__defaults__ == ("SESSION_BUDDY_TOOL_PROFILE",)
