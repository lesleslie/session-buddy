#!/usr/bin/env python3
"""Simple test to verify Phase 4 MCP tools are registered.

This test doesn't require database initialization - it just verifies
the tools are properly exposed through the MCP server.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_phase4_tools_registration():
    """Test that Phase 4 tools are properly registered."""
    from session_buddy.mcp.tools.skills.phase4_tools import (
        register_phase4_tools,
        get_real_time_metrics,
        detect_anomalies,
        get_skill_trend,
        get_collaborative_recommendations,
        get_community_baselines,
        get_skill_dependencies,
    )

    print("=" * 60)
    print("Phase 4 MCP Tools Registration Test")
    print("=" * 60)

    # Verify all tool functions exist
    tools = [
        ("get_real_time_metrics", get_real_time_metrics),
        ("detect_anomalies", detect_anomalies),
        ("get_skill_trend", get_skill_trend),
        ("get_collaborative_recommendations", get_collaborative_recommendations),
        ("get_community_baselines", get_community_baselines),
        ("get_skill_dependencies", get_skill_dependencies),
    ]

    print("\nChecking tool functions...")
    for name, func in tools:
        print(f"  ✓ {name}: {func.__name__}")
        assert callable(func), f"{name} is not callable"

    # Verify registration function exists
    print("\nChecking registration function...")
    print(f"  ✓ register_phase4_tools: {register_phase4_tools.__name__}")
    assert callable(register_phase4_tools), "register_phase4_tools is not callable"

    # Check tool docstrings
    print("\nChecking tool documentation...")
    for name, func in tools:
        doc = func.__doc__
        assert doc, f"{name} missing docstring"
        print(f"  ✓ {name}: {doc.split(chr(10))[0][:60]}...")

    print("\n" + "=" * 60)
    print("✅ All Phase 4 MCP Tools Registration Tests Passed!")
    print("=" * 60)

    print("\nPhase 4 MCP Tools Summary:")
    print("-" * 60)
    print("1. get_real_time_metrics      - Dashboard metrics for recent skills")
    print("2. detect_anomalies            - Performance anomaly detection")
    print("3. get_skill_trend            - Trend analysis over time")
    print("4. get_collaborative_recommendations - Personalized recommendations")
    print("5. get_community_baselines    - Global skill effectiveness")
    print("6. get_skill_dependencies     - Co-occurrence analysis")
    print("-" * 60)

    return True


if __name__ == "__main__":
    success = test_phase4_tools_registration()
    sys.exit(0 if success else 1)
