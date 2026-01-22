"""MCP tools for workflow metrics and health monitoring.

This module provides Model Context Protocol tools for:
- Getting workflow metrics (velocity, quality trends)
- Analyzing session patterns
- Monitoring development productivity
- Identifying bottlenecks
"""

from __future__ import annotations

import typing as t
from typing import Any

from session_buddy.core.workflow_metrics import get_workflow_metrics_engine


def register_workflow_metrics_tools(server: Any) -> None:
    """Register workflow metrics MCP tools.

    Args:
        server: SessionBuddyServer instance to register tools on
    """

    @server.tool()  # type: ignore[misc]
    async def get_workflow_metrics(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Get comprehensive workflow metrics.

        Provides analytics about development velocity, quality trends,
        session patterns, and productivity insights.

        Args:
            project_path: Optional filter by project path
            days_back: Number of days to analyze (default: 30)

        Returns:
            Dictionary with workflow metrics including:
                - total_sessions: Number of sessions in period
                - avg_session_duration_minutes: Average session length
                - avg_checkpoints_per_session: Checkpoint frequency
                - avg_commits_per_session: Commit activity
                - avg_quality_score: Average quality across sessions
                - quality_trend: Quality direction (improving/stable/declining)
                - most_productive_time_of_day: Best working time
                - most_used_tools: Top tools with usage counts
                - avg_velocity_commits_per_hour: Development speed
                - active_projects: List of active projects

        Example:
            >>> result = await get_workflow_metrics(days_back=7)
            >>> print(f"Quality trend: {result['quality_trend']}")
            >>> print(f"Velocity: {result['avg_velocity_commits_per_hour']:.1f} commits/hour")
        """
        try:
            engine = get_workflow_metrics_engine()
            await engine.initialize()

            metrics = await engine.get_workflow_metrics(
                project_path=project_path,
                days_back=days_back,
            )

            result = metrics.to_dict()
            result["success"] = True

            # Add human-readable insights
            if metrics.total_sessions > 0:
                result["insights"] = _generate_workflow_insights(metrics)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve workflow metrics",
            }

    @server.tool()  # type: ignore[misc]
    async def get_session_analytics(
        limit: int = 20, sort_by: str = "duration"
    ) -> dict[str, t.Any]:
        """Get detailed session-level analytics.

        Provides per-session breakdown for detailed analysis
        of development patterns and productivity.

        Args:
            limit: Maximum number of sessions to return
            sort_by: Sort field - "duration", "quality", "commits", or "checkpoints"

        Returns:
            Dictionary with:
                - sessions: List of session metrics
                - total_analyzed: Total sessions in database
                - sort_field: Field used for sorting
                - insights: Analytical observations

        Example:
            >>> result = await get_session_analytics(limit=10, sort_by="quality")
            >>> for session in result["sessions"]:
            ...     print(f"{session['session_id']}: quality={session['avg_quality']:.1f}")
        """
        try:
            from session_buddy.core.workflow_metrics import WorkflowMetricsStore

            store = WorkflowMetricsStore()
            conn = store._get_conn()

            # Determine sort column
            sort_column_map = {
                "duration": "duration_minutes",
                "quality": "avg_quality",
                "commits": "commit_count",
                "checkpoints": "checkpoint_count",
            }
            sort_column = sort_column_map.get(sort_by, "duration_minutes")
            sort_direction = "DESC" if sort_by != "quality" else "DESC"

            # Query sessions with sorting
            result = conn.execute(
                f"""
                SELECT
                    session_id,
                    project_path,
                    started_at,
                    ended_at,
                    duration_minutes,
                    checkpoint_count,
                    commit_count,
                    quality_start,
                    quality_end,
                    quality_delta,
                    avg_quality,
                    files_modified,
                    tools_used,
                    primary_language,
                    time_of_day
                FROM session_metrics
                ORDER BY {sort_column} {sort_direction}
                LIMIT ?
                """,
                [limit],
            ).fetchall()

            sessions = [
                {
                    "session_id": row[0],
                    "project_path": row[1],
                    "started_at": row[2].isoformat() if row[2] else None,
                    "ended_at": row[3].isoformat() if row[3] else None,
                    "duration_minutes": row[4],
                    "checkpoint_count": row[5],
                    "commit_count": row[6],
                    "quality_start": row[7],
                    "quality_end": row[8],
                    "quality_delta": row[9],
                    "avg_quality": row[10],
                    "files_modified": row[11],
                    "tools_used": list(row[12]) if row[12] else [],
                    "primary_language": row[13],
                    "time_of_day": row[14],
                }
                for row in result
            ]

            # Get total count
            total_result = conn.execute(
                "SELECT COUNT(*) FROM session_metrics"
            ).fetchone()
            total_analyzed = total_result[0] if total_result else 0

            store.close()

            return {
                "success": True,
                "sessions": sessions,
                "total_analyzed": total_analyzed,
                "sort_field": sort_by,
                "insights": _generate_session_insights(sessions),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve session analytics",
            }

    @server.prompt()  # type: ignore[misc]
    def workflow_metrics_help() -> str:
        """Get help for workflow metrics and monitoring."""
        return """# Workflow Metrics - Monitoring Guide

## Available Tools

### get_workflow_metrics
Comprehensive workflow analytics dashboard:
- **Session velocity**: Development speed (commits/hour, checkpoints/hour)
- **Quality trends**: Tracking improvement over time
- **Time analysis**: Most productive hours of the day
- **Tool usage**: Which tools you use most frequently
- **Project tracking**: Active projects and session distribution

**Usage:**
```python
# Last 30 days (default)
get_workflow_metrics()

# Last 7 days for specific project
get_workflow_metrics(project_path="/path/to/project", days_back=7)
```

**Key Metrics:**
- `avg_velocity_commits_per_hour`: Development speed indicator
- `quality_trend`: "improving", "stable", or "declining"
- `most_productive_time_of_day`: When you're most effective
- `most_used_tools`: Your primary workflow tools

### get_session_analytics
Detailed per-session breakdown:
- Individual session performance
- Quality scores and deltas
- File modification patterns
- Tool usage per session

**Usage:**
```python
# Top 10 longest sessions
get_session_analytics(limit=10, sort_by="duration")

# Top 10 highest quality sessions
get_session_analytics(limit=10, sort_by="quality")

# Top 10 most active sessions (commits)
get_session_analytics(limit=10, sort_by="commits")
```

## Common Workflows

### Tracking Productivity Improvements

1. **Establish baseline**: Run `get_workflow_metrics(days_back=30)`
2. **Check trends**: Look at `quality_trend` field
3. **Analyze patterns**: Use `get_session_analytics` to find your best sessions
4. **Optimize**: Schedule work during `most_productive_time_of_day`

### Identifying Workflow Issues

1. **Low velocity?** Check `avg_commits_per_session` vs session duration
2. **Quality declining?** Review `quality_trend` and recent sessions
3. **Tool inefficiency?** Review `most_used_tools` for workflow optimization

### Project Comparison

```python
# Compare metrics across projects
metrics_project_a = await get_workflow_metrics(project_path="/project/a")
metrics_project_b = await get_workflow_metrics(project_path="/project/b")

print(f"Project A velocity: {metrics_project_a['avg_velocity_commits_per_hour']:.1f}")
print(f"Project B velocity: {metrics_project_b['avg_velocity_commits_per_hour']:.1f}")
```

## Best Practices

- **Track weekly**: Run metrics every 7 days to spot trends early
- **Before retrospectives**: Use metrics data to inform retrospectives
- **After changes**: Compare before/after to validate improvements
- **Multi-project**: Use project_path filter to compare different projects

## Interpreting Metrics

### Velocity Benchmarks
- **< 2 commits/hour**: Slow pace, may indicate blockers
- **2-5 commits/hour**: Healthy sustainable pace
- **> 5 commits/hour**: Very fast, may indicate small/quick commits

### Quality Trends
- **Improving**: Keep doing what you're working
- **Stable**: Good consistency, consider optimization
- **Declining**: Investigate recent changes or complexity

### Time of Day Patterns
- **Morning**: Often best for complex problem-solving
- **Afternoon**: Good for implementation and routine work
- **Evening**: May be lower energy, good for review/planning
- **Night**: Variable, know your personal patterns
"""


def _generate_workflow_insights(metrics: Any) -> list[str]:
    """Generate human-readable insights from workflow metrics.

    Args:
        metrics: WorkflowMetrics instance

    Returns:
        List of insight strings
    """
    insights = []

    # Velocity insights
    if metrics.avg_velocity_commits_per_hour > 5:
        insights.append(
            "🚀 High development velocity: "
            f"{metrics.avg_velocity_commits_per_hour:.1f} commits/hour"
        )
    elif metrics.avg_velocity_commits_per_hour < 2:
        insights.append(
            "⚠️ Low development velocity: "
            f"{metrics.avg_velocity_commits_per_hour:.1f} commits/hour - "
            "may indicate blockers or complexity"
        )

    # Quality trend insights
    if metrics.quality_trend == "improving":
        insights.append(
            f"📈 Quality improving over time (current avg: {metrics.avg_quality_score:.0f}/100)"
        )
    elif metrics.quality_trend == "declining":
        insights.append(
            f"📉 Quality declining - consider reviewing recent changes "
            f"(current avg: {metrics.avg_quality_score:.0f}/100)"
        )

    # Session length insights
    if metrics.avg_session_duration_minutes > 120:
        insights.append(
            f"⏱️ Long sessions: {metrics.avg_session_duration_minutes:.0f}min average - "
            "consider more frequent breaks"
        )
    elif metrics.avg_session_duration_minutes < 30:
        insights.append(
            f"⚡ Short sessions: {metrics.avg_session_duration_minutes:.0f}min average - "
            "good for focused work"
        )

    # Time of day insights
    time_insights = {
        "morning": "🌅 Most productive in morning hours",
        "afternoon": "☀️ Most productive in afternoon",
        "evening": "🌆 Most productive in evening hours",
        "night": "🌙 Most productive at night",
    }
    if metrics.most_productive_time_of_day in time_insights:
        insights.append(time_insights[metrics.most_productive_time_of_day])

    # Tool usage insights
    if metrics.most_used_tools:
        top_tool = metrics.most_used_tools[0]
        insights.append(f"🔧 Most used tool: {top_tool[0]} ({top_tool[1]} times)")

    return insights


def _generate_quality_insights(sessions: list[dict[str, t.Any]]) -> list[str]:
    """Generate quality-related insights from sessions."""
    insights = []

    # Analyze quality distribution
    high_quality = [s for s in sessions if s.get("avg_quality", 0) >= 80]
    low_quality = [s for s in sessions if s.get("avg_quality", 0) < 60]

    if high_quality:
        insights.append(f"✅ {len(high_quality)} high-quality sessions (≥80)")
    if low_quality:
        insights.append(f"⚠️ {len(low_quality)} sessions need attention (<60)")

    return insights


def _generate_length_insights(sessions: list[dict[str, t.Any]]) -> list[str]:
    """Generate session length insights from sessions."""
    insights = []

    # Analyze session length distribution
    long_sessions = [s for s in sessions if s.get("duration_minutes", 0) > 120]
    short_sessions = [s for s in sessions if s.get("duration_minutes", 0) < 30]

    if long_sessions:
        insights.append(f"📊 {len(long_sessions)} marathon sessions (>2 hours)")
    if short_sessions:
        insights.append(f"⚡ {len(short_sessions)} quick sessions (<30 min)")

    return insights


def _generate_commit_insights(sessions: list[dict[str, t.Any]]) -> list[str]:
    """Generate commit pattern insights from sessions."""
    insights = []

    # Analyze commit patterns
    zero_commits = [s for s in sessions if s.get("commit_count", 0) == 0]
    high_commits = [s for s in sessions if s.get("commit_count", 0) >= 10]

    if zero_commits:
        insights.append(f"📝 {len(zero_commits)} sessions with no commits")
    if high_commits:
        insights.append(
            f"🔥 {len(high_commits)} high-commitment sessions (≥10 commits)"
        )

    return insights


def _generate_language_insights(sessions: list[dict[str, t.Any]]) -> list[str]:
    """Generate language diversity insights from sessions."""
    insights = []

    # Language diversity
    languages: dict[str, int] = {}
    for s in sessions:
        lang = s.get("primary_language")
        if lang:
            languages[lang] = languages.get(lang, 0) + 1

    if languages:
        languages_dict: dict[str, int] = languages
        if languages_dict:  # Check if dict is not empty
            top_lang = max(languages_dict.keys(), key=lambda x: languages_dict[x])
            insights.append(
                f"💻 Primary language: {top_lang} ({languages[top_lang]} sessions)"
            )

    return insights


def _generate_session_insights(sessions: list[dict[str, t.Any]]) -> list[str]:
    """Generate insights from session-level analytics.

    Args:
        sessions: List of session dictionaries

    Returns:
        List of insight strings
    """
    if not sessions:
        return ["No sessions analyzed"]

    insights = []

    # Combine insights from different aspects
    insights.extend(_generate_quality_insights(sessions))
    insights.extend(_generate_length_insights(sessions))
    insights.extend(_generate_commit_insights(sessions))
    insights.extend(_generate_language_insights(sessions))

    return insights
