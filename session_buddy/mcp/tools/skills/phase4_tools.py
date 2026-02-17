"""MCP tools for Phase 4 Skills Analytics.

This module provides tools for:
- Real-time skill metrics and monitoring
- Performance anomaly detection
- Skill trend analysis over time
- Collaborative filtering recommendations
- Community baseline comparisons
- Skill dependency analysis

Phase 4 adds advanced analytics capabilities for the skills tracking system.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def register_phase4_tools(mcp: Any) -> None:
    """Register all Phase 4 skills tools with the MCP server.

    Args:
        mcp: FastMCP instance to register tools with
    """
    mcp.tool()(get_real_time_metrics)
    mcp.tool()(detect_anomalies)
    mcp.tool()(get_skill_trend)
    mcp.tool()(get_collaborative_recommendations)
    mcp.tool()(get_community_baselines)
    mcp.tool()(get_skill_dependencies)


async def get_real_time_metrics(
    limit: int = 10,
    time_window_hours: float = 1.0,
) -> dict[str, Any]:
    """Get real-time skill metrics for dashboard.

    Returns the most frequently used skills within the specified time window,
    along with their completion rates and average durations.

    Args:
        limit: Maximum number of skills to return (default: 10)
        time_window_hours: Time window in hours (default: 1.0)
                           - 1.0 = last hour
                           - 24.0 = last day
                           - 168.0 = last week

    Returns:
        Dictionary with:
        - success: True if metrics retrieved
        - top_skills: List of skill metrics:
            - skill_name: Name of the skill
            - invocation_count: Number of times invoked
            - completed_count: Number of successful completions
            - avg_duration: Average duration in seconds
            - last_invocation_at: ISO timestamp of last use
        - timestamp: ISO timestamp of query
        - message: Human-readable summary

    Examples:
        >>> await get_real_time_metrics(limit=5, time_window_hours=1.0)
        {
            "success": True,
            "top_skills": [
                {
                    "skill_name": "pytest-run",
                    "invocation_count": 42,
                    "completed_count": 38,
                    "avg_duration": 45.2,
                    "last_invocation_at": "2026-02-10T12:00:00Z"
                }
            ],
            "timestamp": "2026-02-10T12:00:00Z",
            "message": "Found 5 skills in the last 1.0 hours"
        }
    """
    try:
        # Import here to avoid circular imports
        from session_buddy.storage.skills_storage import get_storage

        storage = get_storage()

        # Get real-time metrics
        metrics = storage.get_real_time_metrics(
            limit=limit, time_window_hours=time_window_hours
        )

        return {
            "success": True,
            "top_skills": metrics,
            "timestamp": datetime.now().isoformat(),
            "message": f"Found {len(metrics)} skills in the last {time_window_hours} hours",
        }

    except Exception as e:
        logger.error(f"Failed to get real-time metrics: {e}")
        return {
            "success": False,
            "top_skills": [],
            "timestamp": datetime.now().isoformat(),
            "message": f"Error: {str(e)}",
        }


async def detect_anomalies(
    threshold: float = 2.0,
    time_window_hours: float = 24.0,
) -> dict[str, Any]:
    """Detect performance anomalies in skill usage.

    Uses Z-score analysis to identify skills with significant performance
    deviations from their baseline. Detects both performance drops (failures)
    and performance spikes (unusual improvements).

    Args:
        threshold: Z-score threshold (default: 2.0)
                   - 2.0 = 2 standard deviations (95% confidence)
                   - 2.5 = higher confidence, fewer alerts
                   - 1.5 = lower confidence, more alerts
        time_window_hours: Time window for baseline (default: 24.0)

    Returns:
        Dictionary with:
        - success: True if detection completed
        - anomalies: List of detected anomalies:
            - skill_name: Name of the skill
            - anomaly_type: "performance_drop" or "performance_spike"
            - baseline_value: Expected performance (0.0 to 1.0)
            - observed_value: Actual performance (0.0 to 1.0)
            - deviation_score: Z-score (how many std deviations from mean)
        - timestamp: ISO timestamp of analysis
        - message: Human-readable summary

    Examples:
        >>> await detect_anomalies(threshold=2.0, time_window_hours=24.0)
        {
            "success": True,
            "anomalies": [
                {
                    "skill_name": "ruff-check",
                    "anomaly_type": "performance_drop",
                    "baseline_value": 0.92,
                    "observed_value": 0.65,
                    "deviation_score": -2.7
                }
            ],
            "timestamp": "2026-02-10T12:00:00Z",
            "message": "Detected 1 anomaly(ies) with Z-score >= 2.0"
        }
    """
    try:
        # Import here to avoid circular imports
        from session_buddy.storage.skills_storage import get_storage

        storage = get_storage()

        # Detect anomalies
        anomalies = storage.detect_anomalies(
            threshold=threshold, time_window_hours=time_window_hours
        )

        return {
            "success": True,
            "anomalies": anomalies,
            "timestamp": datetime.now().isoformat(),
            "message": f"Detected {len(anomalies)} anomaly(ies) with Z-score >= {threshold}",
        }

    except Exception as e:
        logger.error(f"Failed to detect anomalies: {e}")
        return {
            "success": False,
            "anomalies": [],
            "timestamp": datetime.now().isoformat(),
            "message": f"Error: {str(e)}",
        }


async def get_skill_trend(
    skill_name: str,
    days: int = 7,
) -> dict[str, Any]:
    """Get skill effectiveness trend over time.

    Analyzes historical performance to determine if a skill is improving,
    declining, or stable using linear regression and statistical testing.

    Args:
        skill_name: Name of the skill to analyze
        days: Number of days to analyze (default: 7)
              - 7 = last week
              - 30 = last month
              - 90 = last quarter

    Returns:
        Dictionary with:
        - success: True if trend analysis completed
        - skill_name: Name of the analyzed skill
        - trend: Trend direction:
            - "improving": Performance getting better
            - "declining": Performance getting worse
            - "stable": No significant change
            - "insufficient_data": Not enough data points
        - slope: Linear regression slope (change per day)
        - start_value: Performance at start of window
        - end_value: Performance at end of window
        - change_percent: Percentage change from start to end
        - confidence: Statistical confidence (p-value)
        - timestamp: ISO timestamp of analysis

    Examples:
        >>> await get_skill_trend("pytest-run", days=7)
        {
            "success": True,
            "skill_name": "pytest-run",
            "trend": "improving",
            "slope": 0.0123,
            "start_value": 0.75,
            "end_value": 0.82,
            "change_percent": 9.3,
            "confidence": 0.04,
            "timestamp": "2026-02-10T12:00:00Z"
        }
    """
    try:
        # Import here to avoid circular imports
        from session_buddy.analytics.time_series import TimeSeriesAnalyzer
        from session_buddy.storage.skills_storage import get_storage

        storage = get_storage()
        analyzer = TimeSeriesAnalyzer(storage.db_path)

        # Detect trend
        trend_analysis = analyzer.detect_trend(
            skill_name=skill_name, metric="completion_rate", window_days=days
        )

        return {
            "success": True,
            "skill_name": skill_name,
            "trend": trend_analysis.trend,
            "slope": trend_analysis.slope,
            "start_value": trend_analysis.start_value,
            "end_value": trend_analysis.end_value,
            "change_percent": trend_analysis.change_percent,
            "confidence": trend_analysis.confidence,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get skill trend: {e}")
        return {
            "success": False,
            "skill_name": skill_name,
            "trend": "error",
            "slope": 0.0,
            "start_value": 0.0,
            "end_value": 0.0,
            "change_percent": 0.0,
            "confidence": 1.0,
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
        }


async def get_collaborative_recommendations(
    user_id: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Get personalized skill recommendations using collaborative filtering.

    Finds users with similar skill usage patterns and recommends skills
    they used successfully that you haven't tried yet.

    Args:
        user_id: User identifier for recommendations
        limit: Maximum number of recommendations (default: 5)

    Returns:
        Dictionary with:
        - success: True if recommendations generated
        - user_id: User identifier
        - recommendations: List of recommendations:
            - skill_name: Name of recommended skill
            - score: Recommendation score (0.0 to 1.0)
            - completion_rate: Success rate among similar users
            - source: "collaborative_filtering"
        - timestamp: ISO timestamp of generation
        - message: Human-readable summary

    Examples:
        >>> await get_collaborative_recommendations("user-123", limit=5)
        {
            "success": True,
            "user_id": "user-123",
            "recommendations": [
                {
                    "skill_name": "coverage-report",
                    "score": 0.87,
                    "completion_rate": 0.91,
                    "source": "collaborative_filtering"
                }
            ],
            "timestamp": "2026-02-10T12:00:00Z",
            "message": "Generated 5 recommendations for user-123"
        }
    """
    try:
        # Import here to avoid circular imports
        from session_buddy.analytics.collaborative_filtering import (
            get_collaborative_engine,
        )
        from session_buddy.storage.skills_storage import get_storage

        storage = get_storage()
        engine = get_collaborative_engine(db_path=storage.db_path)

        # Get collaborative filtering recommendations
        recommendations = engine.recommend_from_similar_users(
            user_id=user_id, limit=limit
        )

        # Remove similar_user_id from recommendations (internal detail)
        clean_recommendations = []
        for rec in recommendations:
            clean_rec = {
                "skill_name": rec["skill_name"],
                "score": rec["score"],
                "completion_rate": rec["completion_rate"],
                "source": rec["source"],
            }
            clean_recommendations.append(clean_rec)

        # Fall back to global recommendations if no collaborative results
        if not clean_recommendations:
            fallback = engine.get_global_fallback_recommendations(limit=limit)
            clean_recommendations = fallback

        return {
            "success": True,
            "user_id": user_id,
            "recommendations": clean_recommendations,
            "timestamp": datetime.now().isoformat(),
            "message": f"Generated {len(clean_recommendations)} recommendations for {user_id}",
        }

    except Exception as e:
        logger.error(f"Failed to get collaborative recommendations: {e}")
        return {
            "success": False,
            "user_id": user_id,
            "recommendations": [],
            "timestamp": datetime.now().isoformat(),
            "message": f"Error: {str(e)}",
        }


async def get_community_baselines(
    limit: int = 20,
) -> dict[str, Any]:
    """Get global skill effectiveness baselines.

    Returns community-wide performance statistics for all skills,
    useful for comparing your performance against global averages.

    Args:
        limit: Maximum number of skills to return (default: 20)

    Returns:
        Dictionary with:
        - success: True if baselines retrieved
        - baselines: List of baseline metrics:
            - skill_name: Name of the skill
            - total_users: Number of users who tried this skill
            - total_invocations: Total number of invocations
            - global_completion_rate: Community-wide success rate
            - effectiveness_percentile: Percentile ranking (0-100)
        - timestamp: ISO timestamp of query
        - message: Human-readable summary

    Examples:
        >>> await get_community_baselines(limit=20)
        {
            "success": True,
            "baselines": [
                {
                    "skill_name": "pytest-run",
                    "total_users": 15,
                    "total_invocations": 342,
                    "global_completion_rate": 0.88,
                    "effectiveness_percentile": 75.3
                }
            ],
            "timestamp": "2026-02-10T12:00:00Z",
            "message": "Retrieved 20 community baselines"
        }
    """
    try:
        # Import here to avoid circular imports
        from session_buddy.storage.skills_storage import get_storage

        storage = get_storage()

        # Get community baselines
        baselines = storage.get_community_baselines()

        # Apply limit
        baselines = baselines[:limit]

        return {
            "success": True,
            "baselines": baselines,
            "timestamp": datetime.now().isoformat(),
            "message": f"Retrieved {len(baselines)} community baselines",
        }

    except Exception as e:
        logger.error(f"Failed to get community baselines: {e}")
        return {
            "success": False,
            "baselines": [],
            "timestamp": datetime.now().isoformat(),
            "message": f"Error: {str(e)}",
        }


async def get_skill_dependencies(
    skill_name: str,
    limit: int = 10,
    min_lift: float = 1.5,
) -> dict[str, Any]:
    """Get skills commonly used together with a given skill.

    Analyzes co-occurrence patterns to identify skills that are frequently
    used together, useful for workflow optimization and recommendations.

    Args:
        skill_name: Name of the skill to find dependencies for
        limit: Maximum number of related skills (default: 10)
        min_lift: Minimum lift score (default: 1.5)
                 - 1.0 = no association (independent)
                 - 1.5 = moderate positive association
                 - 2.0+ = strong positive association
                 - 3.0+ = very strong association

    Returns:
        Dictionary with:
        - success: True if dependencies found
        - skill_name: Name of the queried skill
        - dependencies: List of related skills:
            - skill_b: Name of related skill
            - co_occurrence_count: Times used together
            - lift_score: Association strength (P(A,B) / P(A)*P(B))
            - relationship_type: "strong_positive", "moderate_positive", etc.
        - timestamp: ISO timestamp of query
        - message: Human-readable summary

    Examples:
        >>> await get_skill_dependencies("pytest-run", limit=10, min_lift=1.5)
        {
            "success": True,
            "skill_name": "pytest-run",
            "dependencies": [
                {
                    "skill_b": "ruff-check",
                    "co_occurrence_count": 45,
                    "lift_score": 2.3,
                    "relationship_type": "strong_positive"
                }
            ],
            "timestamp": "2026-02-10T12:00:00Z",
            "message": "Found 5 skills with lift >= 1.5"
        }
    """
    try:
        # Import here to avoid circular imports
        from session_buddy.storage.skills_storage import get_storage

        storage = get_storage()

        # First update dependencies (to ensure fresh data)
        storage.update_skill_dependencies(min_co_occurrence=3)

        # Query dependencies from database
        with storage._get_connection() as conn:
            import sqlite3

            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get dependencies for this skill (either direction)
            cursor.execute(
                """
                SELECT
                    CASE
                        WHEN skill_a = ? THEN skill_b
                        ELSE skill_a
                    END as related_skill,
                    co_occurrence_count,
                    lift_score
                FROM skill_dependencies
                WHERE (skill_a = ? OR skill_b = ?)
                  AND lift_score >= ?
                ORDER BY lift_score DESC
                LIMIT ?
                """,
                (skill_name, skill_name, skill_name, min_lift, limit * 2),
            )

            rows = cursor.fetchall()

        # Process and categorize relationships
        dependencies = []
        for row in rows:
            lift = row["lift_score"]

            # Categorize relationship strength
            if lift >= 3.0:
                relationship_type = "very_strong_positive"
            elif lift >= 2.0:
                relationship_type = "strong_positive"
            elif lift >= 1.5:
                relationship_type = "moderate_positive"
            else:
                relationship_type = "weak_positive"

            dependencies.append(
                {
                    "skill_b": row["related_skill"],
                    "co_occurrence_count": row["co_occurrence_count"],
                    "lift_score": lift,
                    "relationship_type": relationship_type,
                }
            )

        # Apply limit after categorization
        dependencies = dependencies[:limit]

        return {
            "success": True,
            "skill_name": skill_name,
            "dependencies": dependencies,
            "timestamp": datetime.now().isoformat(),
            "message": f"Found {len(dependencies)} skills with lift >= {min_lift}",
        }

    except Exception as e:
        logger.error(f"Failed to get skill dependencies: {e}")
        return {
            "success": False,
            "skill_name": skill_name,
            "dependencies": [],
            "timestamp": datetime.now().isoformat(),
            "message": f"Error: {str(e)}",
        }
