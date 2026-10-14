#!/usr/bin/env python3
"""Test script for Phase 4 MCP tools with database initialization.

This script creates sample data and tests all 6 Phase 4 tools:
1. get_real_time_metrics
2. detect_anomalies
3. get_skill_trend
4. get_collaborative_recommendations
5. get_community_baselines
6. get_skill_dependencies
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def setup_test_data():
    """Create sample skill invocation data for testing."""
    from session_buddy.storage.skills_storage import get_storage

    storage = get_storage()

    # Create sample invocations spanning the last week
    skills = [
        ("pytest-run", True, 45.2),
        ("pytest-run", True, 38.7),
        ("pytest-run", False, 120.0),
        ("ruff-check", True, 12.3),
        ("ruff-check", True, 10.1),
        ("ruff-check", True, 11.5),
        ("coverage-report", True, 8.9),
        ("coverage-report", False, 15.0),
        ("mypy-check", True, 25.4),
        ("mypy-check", True, 28.1),
    ]

    base_time = datetime.now() - timedelta(days=7)

    for i, (skill, completed, duration) in enumerate(skills):
        # Stagger times
        invoked_at = base_time + timedelta(hours=i * 6)

        storage.store_invocation(
            skill_name=skill,
            invoked_at=invoked_at.isoformat(),
            session_id="test-session-123",
            workflow_path="test",
            completed=completed,
            duration_seconds=duration,
            user_query=f"Test query for {skill}",
        )

    print(f"Created {len(skills)} test invocations")


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
    print("Testing Phase 4 MCP Tools with Sample Data")
    print("=" * 60)

    # Setup test data
    print("\nSetting up test data...")
    await setup_test_data()

    # Test 1: get_real_time_metrics
    print("\n1. Testing get_real_time_metrics...")
    result = await get_real_time_metrics(limit=5, time_window_hours=168.0)  # Last week
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Skills found: {len(result.get('top_skills', []))}")
    if result.get('top_skills'):
        for skill in result['top_skills'][:3]:
            print(f"   - {skill['skill_name']}: {skill['invocation_count']} invocations, "
                  f"{skill['completed_count']} completed")

    # Test 2: detect_anomalies
    print("\n2. Testing detect_anomalies...")
    result = await detect_anomalies(threshold=1.5, time_window_hours=168.0)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Anomalies found: {len(result.get('anomalies', []))}")
    if result.get('anomalies'):
        for anomaly in result['anomalies'][:2]:
            print(f"   - {anomaly['skill_name']}: {anomaly['anomaly_type']} "
                  f"(z-score: {anomaly['deviation_score']:.2f})")

    # Test 3: get_skill_trend
    print("\n3. Testing get_skill_trend...")
    result = await get_skill_trend("pytest-run", days=7)
    print(f"   Success: {result.get('success')}")
    print(f"   Trend: {result.get('trend')}")
    print(f"   Slope: {result.get('slope', 0):.4f} (change per day)")
    print(f"   Change: {result.get('change_percent', 0):.1f}%")

    # Test 4: get_collaborative_recommendations
    print("\n4. Testing get_collaborative_recommendations...")
    # First, create some user interaction data
    from session_buddy.storage.skills_storage import get_storage
    storage = get_storage()
    import hashlib

    # Hash the user ID
    hashed_user_id = hashlib.sha256("test-user-123".encode()).hexdigest()

    # Add user interactions
    with storage._get_connection() as conn:
        import sqlite3

        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Insert user interactions
        cursor.execute(
            """
            INSERT INTO skill_user_interactions
            (user_id, skill_name, session_id, completed, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (hashed_user_id, "pytest-run", "test-session-123", 1, datetime.now().isoformat()),
        )
        conn.commit()

    result = await get_collaborative_recommendations("test-user-123", limit=5)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Recommendations: {len(result.get('recommendations', []))}")
    if result.get('recommendations'):
        for rec in result['recommendations'][:3]:
            print(f"   - {rec['skill_name']}: score {rec['score']:.2f}, "
                  f"completion {rec['completion_rate']:.1%}")

    # Test 5: get_community_baselines
    print("\n5. Testing get_community_baselines...")
    # First update baselines
    from session_buddy.analytics.collaborative_filtering import get_collaborative_engine

    engine = get_collaborative_engine(db_path=storage.db_path)
    engine.update_community_baselines()

    result = await get_community_baselines(limit=10)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Baselines: {len(result.get('baselines', []))}")
    if result.get('baselines'):
        for baseline in result['baselines'][:3]:
            print(f"   - {baseline['skill_name']}: {baseline['global_completion_rate']:.1%} completion, "
                  f"{baseline['total_invocations']} invocations")

    # Test 6: get_skill_dependencies
    print("\n6. Testing get_skill_dependencies...")
    result = await get_skill_dependencies("pytest-run", limit=5, min_lift=0.5)
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Dependencies: {len(result.get('dependencies', []))}")
    if result.get('dependencies'):
        for dep in result['dependencies'][:3]:
            print(f"   - {dep['skill_b']}: lift {dep['lift_score']:.2f}, "
                  f"{dep['co_occurrence_count']} co-occurrences")

    print("\n" + "=" * 60)
    print("Phase 4 MCP Tools Testing Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_phase4_tools())
