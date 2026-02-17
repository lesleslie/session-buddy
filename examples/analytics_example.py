#!/usr/bin/env python3
"""Example usage of Session-Buddy analytics module.

This example demonstrates the key features of the session analytics system:
- Query methods for session statistics
- Visualization generation
- Report creation
"""

import asyncio

from session_buddy.analytics import SessionAnalytics, create_session_summary_report


async def main():
    """Demonstrate analytics functionality."""
    print("=" * 80)
    print("Session-Buddy Analytics Example")
    print("=" * 80)
    print()

    # Initialize analytics
    analytics = SessionAnalytics()

    # Example 1: Get session statistics
    print("Example 1: Session Statistics (last 7 days)")
    print("-" * 80)
    stats = await analytics.get_session_stats(days=7)

    if stats:
        for stat in stats[:3]:  # Show top 3
            print(f"  {stat.component_name}:")
            print(f"    Total Sessions: {stat.total_sessions}")
            print(f"    Avg Duration:   {stat.avg_duration:.0f}s")
            print(f"    Active:         {stat.active_sessions}")
            print(f"    Error Rate:     {stat.error_rate:.1f}%")
    else:
        print("  No session data found")
    print()

    # Example 2: Get average durations
    print("Example 2: Average Session Durations")
    print("-" * 80)
    durations = await analytics.get_average_session_duration(days=7)

    if durations:
        for component, duration in list(durations.items())[:3]:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            print(f"  {component:30} {minutes}m {seconds}s")
    else:
        print("  No duration data found")
    print()

    # Example 3: Get most active components
    print("Example 3: Most Active Components")
    print("-" * 80)
    components = await analytics.get_most_active_components(days=7, limit=5)

    if components:
        for i, comp in enumerate(components, 1):
            print(f"  {i}. {comp.component_name}")
            print(f"     Sessions: {comp.session_count}")
            print(f"     Quality:  {comp.avg_quality_score:.1f}/100")
    else:
        print("  No component data found")
    print()

    # Example 4: Get active sessions
    print("Example 4: Currently Active Sessions")
    print("-" * 80)
    active = await analytics.get_active_sessions()

    if active:
        print(f"  Found {len(active)} active sessions")
        for session in active[:3]:
            duration_min = session.get("duration_seconds", 0) / 60
            print(f"  - {session.get('session_id', 'unknown')}")
            print(f"    Component: {session.get('component_name', 'unknown')}")
            print(f"    Duration:  {duration_min:.1f} minutes")
    else:
        print("  No active sessions")
    print()

    # Example 5: Get error rates
    print("Example 5: Error Rate Analysis")
    print("-" * 80)
    error_rates = await analytics.get_session_error_rate(days=7)

    if error_rates:
        for component, data in list(error_rates.items())[:3]:
            print(f"  {component}:")
            print(f"    Error Rate: {data['error_rate']:.2f}%")
            print(f"    Failed:     {data['failed_sessions']}/{data['total_sessions']}")
    else:
        print("  No error data found")
    print()

    # Example 6: Generate visualization
    print("Example 6: Session Statistics Visualization")
    print("-" * 80)
    if stats:
        output = analytics.visualize_session_stats(stats)
        print("\n".join(output))
    print()

    # Example 7: Export SQL
    print("Example 7: SQL Export")
    print("-" * 80)
    sql = analytics.export_sql("session_stats", days=7)
    print("  SQL query for session_stats (first 3 lines):")
    for line in sql.split("\n")[:3]:
        print(f"  {line}")
    print()

    # Example 8: Generate comprehensive report
    print("Example 8: Comprehensive Analytics Report")
    print("-" * 80)
    if stats and components and error_rates:
        report = create_session_summary_report(stats, components, error_rates)
        print(report[:500] + "...")
    print()

    print("=" * 80)
    print("Examples completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
