"""MCP tools for workflow bottleneck detection and analysis.

This module provides Model Context Protocol tools for:
- Quality bottleneck detection and analysis
- Velocity bottleneck identification
- Session pattern bottleneck analysis
- Actionable bottleneck insights and recommendations
"""

from __future__ import annotations

import typing as t

from session_buddy.core.bottleneck_detector import get_bottleneck_detector


def register_bottleneck_tools(server: t.Any) -> None:
    """Register bottleneck detection MCP tools.

    Args:
        server: SessionBuddyServer instance to register tools on
    """

    @server.tool()  # type: ignore[misc]
    async def detect_quality_bottlenecks(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Detect quality-related workflow bottlenecks."""
        try:
            detector = get_bottleneck_detector()
            await detector.initialize()

            bottlenecks = await detector.detect_quality_bottlenecks(
                project_path=project_path,
                days_back=days_back,
            )

            result = bottlenecks.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_quality_bottleneck_insights(bottlenecks)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to detect quality bottlenecks",
            }

    @server.tool()  # type: ignore[misc]
    async def detect_velocity_bottlenecks(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Detect velocity-related workflow bottlenecks."""
        try:
            detector = get_bottleneck_detector()
            await detector.initialize()

            bottlenecks = await detector.detect_velocity_bottlenecks(
                project_path=project_path,
                days_back=days_back,
            )

            result = bottlenecks.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_velocity_bottleneck_insights(bottlenecks)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to detect velocity bottlenecks",
            }

    @server.tool()  # type: ignore[misc]
    async def detect_session_pattern_bottlenecks(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Detect session pattern workflow bottlenecks."""
        try:
            detector = get_bottleneck_detector()
            await detector.initialize()

            bottlenecks = await detector.detect_session_pattern_bottlenecks(
                project_path=project_path,
                days_back=days_back,
            )

            result = bottlenecks.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_pattern_bottleneck_insights(bottlenecks)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to detect session pattern bottlenecks",
            }

    @server.tool()  # type: ignore[misc]
    async def get_bottleneck_insights(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Get comprehensive bottleneck insights and recommendations."""
        try:
            detector = get_bottleneck_detector()
            await detector.initialize()

            insights = await detector.get_bottleneck_insights(
                project_path=project_path,
                days_back=days_back,
            )

            result = insights.to_dict()
            result["success"] = True

            # Add synthesized insights
            result["insights"] = _synthesize_bottleneck_insights(insights)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to generate bottleneck insights",
            }

    @server.prompt()  # type: ignore[misc]
    def bottleneck_help() -> str:
        """Get help for bottleneck detection and analysis.""" ""
        return """# Bottleneck Detection - Workflow Optimization Guide

## Available Tools

### detect_quality_bottlenecks
Quality-related bottleneck analysis:
- **Sudden quality drops**: >10 point quality declines
- **Consecutive low-quality sessions**: Sustained quality issues
- **Low quality periods**: Time ranges with quality < 60
- **Recovery time**: Average time to bounce back from quality drops
- **Root cause analysis**: Common tools associated with quality drops

**Usage:**
```python
# Default 30-day analysis
detect_quality_bottlenecks()

# Custom time window
detect_quality_bottlenecks(days_back=14)

# Project-specific analysis
detect_quality_bottlenecks(project_path="/path/to/project")
```

**Key Metrics:**
- `sudden_quality_drops`: Count of significant quality declines
- `consecutive_low_quality_sessions`: Maximum streak of low-quality sessions
- `avg_recovery_time_hours`: Average time to recover from drops
- `most_common_quality_drop_cause`: Primary tool during drops

### detect_velocity_bottlenecks
Velocity-related bottleneck analysis:
- **Low velocity sessions**: <2 commits/hour
- **Zero-commit sessions**: Planning or debugging phases
- **Long sessions without progress**: >60min with 0 commits
- **Velocity during bottlenecks**: Commits/hour during slow periods
- **Stagnation days**: Days with declining velocity

**Usage:**
```python
result = await detect_velocity_bottlenecks(days_back=7)
print(f"Zero-commit sessions: {result['zero_commit_sessions']}")
print(f"Stagnation days: {result['velocity_stagnation_days']}")
```

**Key Metrics:**
- `low_velocity_sessions`: Count of slow-progress sessions
- `zero_commit_sessions`: Sessions with no commits
- `long_sessions_without_commits`: Long sessions without progress
- `velocity_stagnation_days`: Days with declining velocity

### detect_session_pattern_bottlenecks
Session pattern bottleneck analysis:
- **Marathon sessions**: >4 hours without breaks
- **Fragmented work**: <15 minutes occurring frequently
- **Infrequent checkpoints**: Long sessions with few checkpoints
- **Session gaps**: Average time between sessions
- **Schedule consistency**: 0-100 score (higher = more inconsistent)

**Usage:**
```python
result = await detect_session_pattern_bottlenecks()
print(f"Marathon sessions: {result['marathon_sessions']}")
print(f"Inconsistency score: {result['inconsistent_schedule_score']:.0}/100")
```

**Key Metrics:**
- `marathon_sessions`: Count of extended sessions
- `fragmented_work_sessions': Count of very short sessions
- `inconsistent_schedule_score`: Schedule variability (0-100)

### get_bottleneck_insights
Comprehensive bottleneck synthesis:
- **Critical bottlenecks**: High-impact issues requiring attention
- **Improvement recommendations**: Specific actionable suggestions
- **Optimization opportunities**: Process improvement ideas
- **Impact estimation**: Expected improvement magnitude

**Usage:**
```python
result = await get_bottleneck_insights()

# Focus on critical issues
for bottleneck in result['critical_bottlenecks']:
    print(f"⚠️  {bottleneck}")

# Review recommendations
for rec in result['improvement_recommendations']:
    print(f"→ {rec}")

# Understand impact potential
print(f"Impact: {result['estimated_impact_if_resolved']}")
```

**Priority Levels:**
- **Critical**: High-impact issues affecting velocity or quality
- **Moderate**: Important improvements for workflow optimization
- **Minor**: Nice-to-have optimizations

## Common Bottleneck Patterns

### Quality Drop Pattern

**Symptoms:**
- Multiple sudden quality drops
- Consecutive low-quality sessions
- Long recovery times

**Diagnosis:**
```python
quality = await detect_quality_bottlenecks()
# Look for: sudden_quality_drops > 3
# Look for: consecutive_low_quality_sessions >= 3
```

**Solutions:**
- Take breaks during quality decline streaks
- Switch tasks or context when quality drops
- Review and address root cause from quality patterns

### Velocity Stagnation Pattern

**Symptoms:**
- Many zero-commit sessions
- Low commits/hour during sessions
- Long sessions without progress

**Diagnosis:**
```python
velocity = await detect_velocity_bottlenecks()
# Look for: zero_commit_sessions > 5
# Look for: long_sessions_without_commits > 2
```

**Solutions:**
- Break larger tasks into smaller commit-ready units
- Set checkpoints to track progress during long sessions
- Focus on completing atomic units of work

### Session Pattern Issues

**Symptoms:**
- Frequent marathon sessions
- Highly fragmented work
- Inconsistent schedule

**Diagnosis:**
```python
patterns = await detect_session_pattern_bottlenecks()
# Look for: marathon_sessions > 2
# Look for: fragmented_work_sessions > 5
# Look for: inconsistent_schedule_score > 70
```

**Solutions:**
- Implement forced breaks after 2-3 hours of focused work
- Block dedicated focus time (60-90 minutes) for deep work
- Establish regular session schedule for improved momentum

## Best Practices

### Proactive Bottleneck Monitoring

**Weekly Check-ins:**
```python
# Comprehensive bottleneck review
insights = await get_bottleneck_insights(days_back=7)
print(f"Critical issues: {len(insights['critical_bottlenecks'])}")

# Address high-priority issues first
for rec in insights['improvement_recommendations']:
    print(f"Priority: {rec}")
```

**Post-Session Review:**
```python
# Check for bottlenecks after long sessions
patterns = await detect_session_pattern_bottlenecks()
if patterns['marathon_sessions'] > 0:
    print("⚠️  Consider taking more breaks during long sessions")
```

### Workflow Optimization

**Quality Improvement:**
- Review quality bottlenecks weekly
- Address root causes of quality drops
- Implement break reminders during decline streaks

**Velocity Enhancement:**
- Commit frequently and consistently
- Break tasks into atomic units
- Use checkpoints to track progress

**Session Scheduling:**
- Maintain consistent session schedule
- Balance session lengths (60-120 minutes ideal)
- Take breaks after 2-3 hours of focused work

## Interpreting Bottleneck Metrics

### Quality Benchmarks
- **Excellent**: <1 sudden quality drop per week
- **Good**: 1-2 quality drops per week
- **Concerning**: >3 quality drops per week

### Velocity Benchmarks
- **Excellent**: <10% zero-commit sessions
- **Good**: 10-25% zero-commit sessions
- **Concerning**: >25% zero-commit sessions

### Session Pattern Benchmarks
- **Healthy**: <2 marathon sessions per week
- **Warning**: 2-4 marathon sessions per week
- **Critical**: >4 marathon sessions per week

### Consistency Benchmarks
- **Excellent**: Inconsistency score <40
- **Good**: Inconsistency score 40-60
- **Concerning**: Inconsistency score >60
"""


def _generate_quality_bottleneck_insights(bottlenecks: t.Any) -> list[str]:
    """Generate insights from quality bottlenecks."""
    insights = []

    # Quality drop frequency
    if bottlenecks.sudden_quality_drops == 0:
        insights.append("✅ No sudden quality drops detected")
    elif bottlenecks.sudden_quality_drops <= 2:
        insights.append(
            f"📊 Occasional quality drops: {bottlenecks.sudden_quality_drops} instances"
        )
    else:
        insights.append(
            f"🚨 Frequent quality drops: {bottlenecks.sudden_quality_drops} instances - "
            "review patterns to identify root causes"
        )

    # Consecutive low quality
    if bottlenecks.consecutive_low_quality_sessions >= 3:
        insights.append(
            f"⚠️  Sustained low quality: {bottlenecks.consecutive_low_quality_sessions}+ "
            "consecutive sessions - consider breaks or task switching"
        )

    # Recovery time
    if bottlenecks.avg_recovery_time_hours > 24:
        insights.append(
            f"🐌 Slow recovery: {bottlenecks.avg_recovery_time_hours:.1f}h average recovery time"
        )
    elif bottlenecks.avg_recovery_time_hours > 0:
        insights.append(
            f"⚡ Quick recovery: {bottlenecks.avg_recovery_time_hours:.1f}h average recovery time"
        )

    # Common cause
    if bottlenecks.most_common_quality_drop_cause:
        insights.append(
            f"🔍 Common drop trigger: '{bottlenecks.most_common_quality_drop_cause}' tool usage"
        )

    # Low quality periods
    if bottlenecks.low_quality_periods:
        period_count = len(bottlenecks.low_quality_periods)
        insights.append(
            f"📅 {period_count} low-quality period(s) identified - "
            "review for patterns and triggers"
        )

    return insights


def _generate_velocity_bottleneck_insights(bottlenecks: t.Any) -> list[str]:
    """Generate insights from velocity bottlenecks."""
    insights = []

    # Low velocity sessions
    if bottlenecks.low_velocity_sessions == 0:
        insights.append("✅ No low-velocity sessions detected")
    elif bottlenecks.low_velocity_sessions <= 5:
        insights.append(
            f"📊 Some low-velocity sessions: {bottlenecks.low_velocity_sessions} sessions"
        )
    else:
        insights.append(
            f"⚠️  Many slow sessions: {bottlenecks.low_velocity_sessions} sessions - "
            "consider breaking tasks into smaller units"
        )

    # Zero commit sessions
    zero_pct = (
        (bottlenecks.zero_commit_sessions / bottlenecks.low_velocity_sessions * 100)
        if bottlenecks.low_velocity_sessions > 0
        else 0
    )
    if bottlenecks.zero_commit_sessions > 5:
        insights.append(
            f"🚨 High zero-commit count: {bottlenecks.zero_commit_sessions} sessions "
            f"({zero_pct:.0f}% of slow sessions)"
        )
    elif bottlenecks.zero_commit_sessions > 0:
        insights.append(
            f"📊 Zero-commit sessions: {bottlenecks.zero_commit_sessions} sessions "
            "(planning, debugging, or research phases)"
        )

    # Long sessions without commits
    if bottlenecks.long_sessions_without_commits > 2:
        insights.append(
            f"⚠️  Unproductive marathons: {bottlenecks.long_sessions_without_commits} long sessions "
            "without commits - use checkpoints to track progress"
        )

    # Velocity stagnation
    if bottlenecks.velocity_stagnation_days > 5:
        insights.append(
            f"📉 Declining trend: {bottlenecks.velocity_stagnation_days} days with "
            "decreasing velocity - address momentum loss"
        )
    elif bottlenecks.velocity_stagnation_days > 0:
        insights.append(
            f"📊 Some stagnation: {bottlenecks.velocity_stagnation_days} days with declining velocity"
        )

    return insights


def _generate_pattern_bottleneck_insights(bottlenecks: t.Any) -> list[str]:
    """Generate insights from session pattern bottlenecks."""
    insights = []

    # Marathon sessions
    if bottlenecks.marathon_sessions == 0:
        insights.append("✅ No marathon sessions detected")
    elif bottlenecks.marathon_sessions <= 2:
        insights.append(
            f"📊 Occasional marathons: {bottlenecks.marathon_sessions} sessions "
            "(ensure adequate rest and hydration)"
        )
    else:
        insights.append(
            f"🔥 Frequent marathons: {bottlenecks.marathon_sessions} sessions - "
            "implement forced breaks every 2-3 hours"
        )

    # Fragmented work
    if bottlenecks.fragmented_work_sessions > 5:
        insights.append(
            f"⚡ Highly fragmented: {bottlenecks.fragmented_work_sessions} short sessions - "
            "block dedicated focus time (60-90min) for deep work"
        )
    elif bottlenecks.fragmented_work_sessions > 0:
        insights.append(
            f"📊 Some fragmentation: {bottlenecks.fragmented_work_sessions} short sessions"
        )

    # Infrequent checkpoints
    if bottlenecks.infrequent_checkpoint_sessions > 3:
        insights.append(
            f"⚠️  Infrequent checkpoints: {bottlenecks.infrequent_checkpoint_sessions} sessions - "
            "set checkpoints during long sessions to track progress"
        )

    # Session gaps
    if bottlenecks.excessive_session_gaps > 48:
        insights.append(
            f"📅 Large gaps: {bottlenecks.excessive_session_gaps:.1f}h average between sessions - "
            "consider more consistent schedule"
        )
    elif bottlenecks.excessive_session_gaps > 24:
        insights.append(
            f"📊 Moderate gaps: {bottlenecks.excessive_session_gaps:.1f}h between sessions"
        )

    # Schedule consistency
    if bottlenecks.inconsistent_schedule_score > 70:
        insights.append(
            f"🔄 Highly inconsistent: Score {bottlenecks.inconsistent_schedule_score:.0}/100 - "
            "establish regular session schedule"
        )
    elif bottlenecks.inconsistent_schedule_score > 50:
        insights.append(
            f"📊 Somewhat inconsistent: Score {bottlenecks.inconsistent_schedule_score:.0}/100"
        )
    else:
        insights.append(
            f"✅ Consistent schedule: Score {bottlenecks.inconsistent_schedule_score:.0}/100"
        )

    return insights


def _synthesize_bottleneck_insights(insights: t.Any) -> list[str]:
    """Synthesize comprehensive bottleneck insights."""
    synthesized = []

    # Overall assessment
    critical_count = len(insights.critical_bottlenecks)
    if critical_count == 0:
        synthesized.append("✅ No critical bottlenecks detected - workflow is healthy")
    elif critical_count <= 2:
        synthesized.append(
            f"📊 {critical_count} critical bottleneck(s) identified - "
            "addressing these will improve velocity 20-30%"
        )
    else:
        synthesized.append(
            f"🚨 {critical_count} critical bottlenecks - "
            "addressing these could improve velocity 50%+"
        )

    # Action categories
    if insights.improvement_recommendations:
        synthesized.append(
            f"→ {len(insights.improvement_recommendations)} improvement recommendations available"
        )

    if insights.workflow_optimization_opportunities:
        synthesized.append(
            f"⚙️  {len(insights.workflow_optimization_opportunities)} optimization opportunities"
        )

    # Priority guidance
    if insights.improvement_recommendations:
        synthesized.append("💡 Focus on highest-impact items first for maximum benefit")

    return synthesized
