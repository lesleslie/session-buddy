#!/usr/bin/env python3
"""Test script for Phase 4 MCP tools.

This script tests all 6 Phase 4 tools to ensure they work correctly:
1. get_real_time_metrics
2. detect_anomalies
3. get_skill_trend
4. get_collaborative_recommendations
5. get_community_baselines
6. get_skill_dependencies
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def test_phase4_tools():
    """Test all Phase 4 MCP tools."""
    from session_buddy.mcp.tools.skills.phase4_tools import (
        get_real_time_metrics,
        detect_anomalies,
        get_skill_trend,
        get_collaborative_recommendations,
        get_community_baselines,
        get_skill_dependencies,
    )

    print("=" * 60)
    print("Testing Phase 4 MCP Tools")
    print("=" * 60)

    # Test 1: get_real_time_metrics
    print("\n1. Testing get_real_time_metrics...")
    result = await get_real_time_metrics(limit=5, time_window_hours=24.0)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Skills found: {len(result.get('top_skills', []))}")
    if result.get('top_skills'):
        print(f"   Top skill: {result['top_skills'][0]['skill_name']}")

    # Test 2: detect_anomalies
    print("\n2. Testing detect_anomalies...")
    result = await detect_anomalies(threshold=2.0, time_window_hours=24.0)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Anomalies found: {len(result.get('anomalies', []))}")
    if result.get('anomalies'):
        anomaly = result['anomalies'][0]
        print(f"   Sample anomaly: {anomaly['skill_name']} - {anomaly['anomaly_type']}")

    # Test 3: get_skill_trend
    print("\n3. Testing get_skill_trend...")
    # Use a generic skill name for testing
    result = await get_skill_trend("pytest-run", days=7)
    print(f"   Success: {result.get('success')}")
    print(f"   Trend: {result.get('trend')}")
    print(f"   Change: {result.get('change_percent', 0):.1f}%")

    # Test 4: get_collaborative_recommendations
    print("\n4. Testing get_collaborative_recommendations...")
    result = await get_collaborative_recommendations("test-user-123", limit=5)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Recommendations: {len(result.get('recommendations', []))}")
    if result.get('recommendations'):
        rec = result['recommendations'][0]
        print(f"   Top recommendation: {rec['skill_name']} (score: {rec['score']:.2f})")

    # Test 5: get_community_baselines
    print("\n5. Testing get_community_baselines...")
    result = await get_community_baselines(limit=10)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Baselines: {len(result.get('baselines', []))}")
    if result.get('baselines'):
        baseline = result['baselines'][0]
        print(f"   Sample: {baseline['skill_name']} - {baseline['global_completion_rate']:.1%} completion")

    # Test 6: get_skill_dependencies
    print("\n6. Testing get_skill_dependencies...")
    result = await get_skill_dependencies("pytest-run", limit=5, min_lift=1.5)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Dependencies: {len(result.get('dependencies', []))}")
    if result.get('dependencies'):
        dep = result['dependencies'][0]
        print(f"   Related skill: {dep['skill_b']} (lift: {dep['lift_score']:.2f})")

    print("\n" + "=" * 60)
    print("Phase 4 MCP Tools Testing Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_phase4_tools())
