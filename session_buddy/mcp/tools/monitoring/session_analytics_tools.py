"""MCP tools for detailed session analytics and pattern detection.

This module provides Model Context Protocol tools for:
- Session length distribution analysis
- Temporal pattern detection (time-of-day, day-of-week)
- Activity correlation analysis
- Session streak and consistency tracking
- Actionable productivity insights
"""

from __future__ import annotations

import typing as t

from session_buddy.core.session_analytics import get_session_analytics


def register_session_analytics_tools(server: t.Any) -> None:
    """Register session analytics MCP tools.

    Args:
        server: SessionBuddyServer instance to register tools on
    """

    @server.tool()  # type: ignore[misc]
    async def get_session_length_distribution(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Analyze session length distribution patterns."""
        try:
            analytics = get_session_analytics()
            await analytics.initialize()

            distribution = await analytics.get_session_length_distribution(
                project_path=project_path,
                days_back=days_back,
            )

            result = distribution.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_length_distribution_insights(distribution)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve session length distribution",
            }

    @server.tool()  # type: ignore[misc]
    async def get_temporal_patterns(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Analyze temporal patterns in session activity."""
        try:
            analytics = get_session_analytics()
            await analytics.initialize()

            patterns = await analytics.get_temporal_patterns(
                project_path=project_path,
                days_back=days_back,
            )

            result = patterns.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_temporal_patterns_insights(patterns)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve temporal patterns",
            }

    @server.tool()  # type: ignore[misc]
    async def get_activity_correlations(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Analyze correlations between session activities."""
        try:
            analytics = get_session_analytics()
            await analytics.initialize()

            correlations = await analytics.get_activity_correlations(
                project_path=project_path,
                days_back=days_back,
            )

            result = correlations.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_correlation_insights(correlations)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve activity correlations",
            }

    @server.tool()  # type: ignore[misc]
    async def get_session_streaks(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Analyze session streaks and consistency."""
        try:
            analytics = get_session_analytics()
            await analytics.initialize()

            streaks = await analytics.get_session_streaks(
                project_path=project_path,
                days_back=days_back,
            )

            result = streaks.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_streak_insights(streaks)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve session streaks",
            }

    @server.tool()  # type: ignore[misc]
    async def get_productivity_insights(
        project_path: str | None = None, days_back: int = 30
    ) -> dict[str, t.Any]:
        """Get actionable productivity insights and recommendations."""
        try:
            analytics = get_session_analytics()
            await analytics.initialize()

            insights = await analytics.get_productivity_insights(
                project_path=project_path,
                days_back=days_back,
            )

            result = insights.to_dict()
            result["success"] = True

            # Add comprehensive insights
            result["insights"] = _generate_productivity_insights(insights)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to generate productivity insights",
            }

    @server.prompt()  # type: ignore[misc]
    def session_analytics_help() -> str:
        """Get help for session analytics and pattern detection."""
        return """# Session Analytics - Comprehensive Guide

## Available Tools

### get_session_length_distribution
Session duration pattern analysis:
- **Length categorization**: Short (<30min), Medium (30-120min), Long (>120min)
- **Distribution percentages**: Understanding session length patterns
- **Duration statistics**: Average and median session lengths
- **Pattern identification**: Work session sustainability insights

**Usage:**
```python
# Last 30 days (default)
get_session_length_distribution()

# Last 7 days for specific project
get_session_length_distribution(project_path="/path/to/project", days_back=7)
```

**Key Metrics:**
- `short_percentage`: % of quick sessions (<30min)
- `medium_percentage`: % of standard sessions (30-120min)
- `long_percentage`: % of marathon sessions (>120min)
- `median_duration_minutes`: Typical session length

### get_temporal_patterns
Time-based session pattern detection:
- **Time of day distribution**: Morning/afternoon/evening/night breakdown
- **Day of week patterns**: Monday-Sunday session frequency
- **Peak productivity windows**: Best times for focused work
- **Frequency trends**: Session consistency over time

**Usage:**
```python
result = await get_temporal_patterns(days_back=14)
print(f"Peak productivity: {result['most_productive_time_slot']}")
print(f"Frequency trend: {result['session_frequency_trend']}")
```

**Key Metrics:**
- `peak_productivity_hour`: Hour (0-23) with most activity
- `peak_productivity_day`: Most productive day
- `most_productive_time_slot`: Best time slot (e.g., "Tuesday morning")
- `session_frequency_trend`: "increasing", "stable", or "decreasing"

### get_activity_correlations
Relationship analysis between session activities:
- **Duration vs Quality**: Do longer sessions produce better work?
- **Duration vs Commits**: More time = more commits?
- **Quality vs Commits**: Commit rate correlation with quality
- **High-performance sessions**: Count of exceptional sessions

**Usage:**
```python
result = await get_activity_correlations()

# Check if longer sessions correlate with quality
corr = result['duration_quality_correlation']
if corr > 0.3:
    print("Longer sessions tend to have higher quality")
elif corr < -0.3:
    print("Shorter focused sessions work better")
```

**Key Metrics:**
- `duration_quality_correlation`: -1 to 1 (positive = longer is better)
- `quality_commits_correlation`: Quality vs commit frequency
- `high_quality_sessions`: Count of sessions with quality >= 80
- `long_high_quality_sessions`: Long sessions that maintained quality

### get_session_streaks
Consistency and momentum tracking:
- **Consecutive day streaks**: Measure development consistency
- **Current streak**: Active consecutive day count
- **Session gaps**: Time between sessions
- **Consistent patterns**: Regular daily work habits

**Usage:**
```python
result = await get_session_streaks(days_back=30)
print(f"Current streak: {result['current_streak_days']} days")
print(f"Longest streak: {result['longest_streak_days']} days")
print(f"Consistent daily work: {result['consistent_daily_sessions']}")
```

**Key Metrics:**
- `longest_streak_days`: Maximum consecutive days
- `current_streak_days`: Active streak length
- `avg_gap_between_sessions_hours`: Average time between sessions
- `consistent_daily_sessions`: 5+ day streaks achieved

### get_productivity_insights
Actionable recommendations for optimization:
- **Best performance windows**: Optimal times for focused work
- **Session length recommendations**: Ideal duration for your work
- **Break interval guidance**: How often to take breaks
- **Quality improvement suggestions**: Specific actionable advice

**Usage:**
```python
result = await get_productivity_insights()

# Get comprehensive recommendations
print(f"Best window: {result['best_performance_window']}")
print(f"Recommended: {result['recommended_session_length']}")
print(f"Break every: {result['optimal_break_interval']} minutes")

# Review suggestions
for suggestion in result['improvement_suggestions']:
    print(f"- {suggestion}")
```

**Key Metrics:**
- `best_performance_window`: When you do your best work
- `recommended_session_length`: Optimal duration for you
- `optimal_break_interval`: Suggested break frequency
- `improvement_suggestions`: Personalized recommendations

## Common Analytics Workflows

### Finding Your Optimal Schedule

1. **Analyze temporal patterns**:
   ```python
   temporal = await get_temporal_patterns(days_back=30)
   print(f"Best time: {temporal['most_productive_time_slot']}")
   print(f"Trend: {temporal['session_frequency_trend']}")
   ```

2. **Check session length patterns**:
   ```python
   length = await get_session_length_distribution()
   print(f"Medium sessions: {length['medium_percentage']:.1f}%")
   print(f"Median: {length['median_duration_minutes']} min")
   ```

3. **Get personalized recommendations**:
   ```python
   insights = await get_productivity_insights()
   print(f"Recommended: {insights['recommended_session_length']}")
   ```

### Improving Session Quality

**Low Quality Correlation with Duration** (< -0.3):
- Consider shorter, more focused sessions
- Take breaks more frequently
- Avoid marathon coding sessions

**Low Quality Sessions** (>30% below 60):
- Review `get_activity_correlations()` for patterns
- Check if time of day affects quality
- Ensure adequate rest between sessions

**Inconsistent Schedule** (frequency_trend = "decreasing"):
- Use `get_session_streaks()` to track consistency
- Aim for at least one session per day
- Build streaks gradually

### Optimizing Workflow

**High Commit Rate, Low Quality**:
- Focus on code quality over quantity
- Review before committing more frequently
- Consider test-driven development

**Long Sessions, Low Productivity**:
- Try Pomodoro technique (25min work + 5min break)
- Break marathon sessions into focused blocks
- Schedule regular review points

**Peak Productivity Discovery**:
1. Run `get_temporal_patterns()` weekly
2. Identify your top 3 productive time slots
3. Schedule important work during these times
4. Reserve low-energy times for administrative tasks

## Best Practices

- **Weekly analytics review**: Run all tools weekly to track patterns
- **Before schedule changes**: Check analytics to predict impact
- **After workflow experiments**: Compare before/after metrics
- **Trend monitoring**: Watch for declining frequency or quality trends
- **Personalization**: Use insights to build your optimal schedule

## Interpreting Analytics

### Session Length Benchmarks
- **Balanced**: 40-60% medium sessions (30-120min)
- **Fragmented**: >60% short sessions (<30min) - may indicate distractions
- **Marathon-prone**: >40% long sessions (>120min) - risk of burnout

### Temporal Pattern Benchmarks
- **Consistent**: 5-7 sessions/week with stable distribution
- **Increasing**: Positive frequency trend over time
- **Peak windows**: 2-3x more sessions during best hours

### Correlation Benchmarks
- **Duration-Quality**: >0.3 means longer sessions work better for you
- **Quality-Commits**: >0.3 means more commits = better quality
- **Strong correlation**: |correlation| > 0.5 is statistically significant
"""


def _generate_length_distribution_insights(distribution: t.Any) -> list[str]:
    """Generate insights from session length distribution."""
    insights = []

    total = distribution.total_sessions
    if total == 0:
        return ["No sessions analyzed"]

    # Session length balance
    if distribution.medium_percentage > 50:
        insights.append(
            f"✅ Balanced schedule: {distribution.medium_percentage:.1f}% standard sessions (30-120min)"
        )
    elif distribution.short_percentage > 60:
        insights.append(
            f"⚡ Fragmented work: {distribution.short_percentage:.1f}% short sessions "
            "- may indicate interruptions or context switching"
        )
    elif distribution.long_percentage > 40:
        insights.append(
            f"🔥 Marathon sessions: {distribution.long_percentage:.1f}% long sessions "
            "- consider more breaks to maintain focus"
        )

    # Duration insights
    avg = distribution.avg_duration_minutes
    if avg > 120:
        insights.append(f"⏰ Long average: {avg:.0f}min - ensure adequate rest")
    elif avg < 30:
        insights.append(f"⚡ Short average: {avg:.0f}min - good for focused tasks")

    # Median vs average comparison
    if distribution.median_duration_minutes > 0:
        diff_pct = (
            (distribution.avg_duration_minutes - distribution.median_duration_minutes)
            / distribution.median_duration_minutes
            * 100
        )
        if abs(diff_pct) > 30:
            insights.append(
                f"📊 Variability: {'+' if diff_pct > 0 else ''}{diff_pct:.0f}% difference "
                "between average and median session length"
            )

    return insights


def _generate_temporal_patterns_insights(patterns: t.Any) -> list[str]:
    """Generate insights from temporal patterns."""
    insights = []

    # Frequency trend
    if patterns.session_frequency_trend == "increasing":
        insights.append("📈 Increasing session frequency - building momentum")
    elif patterns.session_frequency_trend == "decreasing":
        insights.append("📉 Decreasing session frequency - consider schedule review")

    # Peak productivity
    if patterns.most_productive_time_slot:
        insights.append(f"⭐ Peak productivity: {patterns.most_productive_time_slot}")

    # Session frequency
    avg_sessions = patterns.avg_sessions_per_day
    if avg_sessions >= 2:
        insights.append(f"🔄 High frequency: {avg_sessions:.1f} sessions/day avg")
    elif avg_sessions < 0.5:
        insights.append(f"📅 Low frequency: {avg_sessions:.1f} sessions/day avg")

    # Time of day distribution
    if patterns.time_of_day_distribution:
        total = sum(patterns.time_of_day_distribution.values())
        if total > 0:
            top_period = max(
                patterns.time_of_day_distribution,
                key=patterns.time_of_day_distribution.get,  # type: ignore[arg-type]
            )
            top_pct = patterns.time_of_day_distribution[top_period] / total * 100
            insights.append(
                f"🌅 Primary work time: {top_period} ({top_pct:.0f}% of sessions)"
            )

    return insights


def _generate_correlation_insights(correlations: t.Any) -> list[str]:
    """Generate insights from activity correlations."""
    insights = []

    # Duration-Quality correlation
    dq_corr = correlations.duration_quality_correlation
    if abs(dq_corr) > 0.3:
        if dq_corr > 0:
            insights.append(
                f"✅ Longer sessions correlate with quality (r={dq_corr:.2f}) "
                "- take time for deep work"
            )
        else:
            insights.append(
                f"⚡ Shorter sessions correlate with quality (r={dq_corr:.2f}) "
                "- frequent focused sessions work better"
            )

    # Quality-Commits correlation
    qc_corr = correlations.quality_commits_correlation
    if abs(qc_corr) > 0.3:
        if qc_corr > 0:
            insights.append(
                f"✅ More commits correlate with quality (r={qc_corr:.2f}) "
                "- iteration improves results"
            )
        else:
            insights.append(
                f"🎯 Fewer commits correlate with quality (r={qc_corr:.2f}) "
                "- thoughtful commits over frequent ones"
            )

    # Quality session counts
    total = correlations.high_quality_sessions + correlations.low_quality_sessions
    if total > 0:
        high_pct = correlations.high_quality_sessions / total * 100
        if high_pct > 70:
            insights.append(
                f"🌟 High quality rate: {high_pct:.0f}% sessions >= 80 quality"
            )
        elif high_pct < 40:
            insights.append(
                f"⚠️ Quality challenges: {high_pct:.0f}% sessions >= 80 quality"
            )

    # Long + high quality sessions
    if correlations.long_high_quality_sessions > 0:
        insights.append(
            f"🏆 {correlations.long_high_quality_sessions} marathon sessions "
            "with high quality - excellent focus!"
        )

    return insights


def _generate_streak_insights(streaks: t.Any) -> list[str]:
    """Generate insights from session streaks."""
    insights = []

    if streaks.total_active_days == 0:
        return ["No session data available"]

    # Current streak
    if streaks.current_streak_days >= 7:
        insights.append(
            f"🔥 Strong momentum: {streaks.current_streak_days} day streak!"
        )
    elif streaks.current_streak_days >= 3:
        insights.append(
            f"📈 Building momentum: {streaks.current_streak_days} day streak"
        )

    # Longest streak
    if streaks.longest_streak_days >= 14:
        insights.append(
            f"💪 Excellent consistency: {streaks.longest_streak_days} day longest streak"
        )
    elif streaks.longest_streak_days >= 7:
        insights.append(
            f"✅ Good consistency: {streaks.longest_streak_days} day longest streak"
        )

    # Consistency
    if streaks.consistent_daily_sessions:
        insights.append("🎯 Consistent daily work habit established")

    # Session gaps
    avg_gap_hours = streaks.avg_gap_between_sessions_hours
    if avg_gap_hours > 48:
        insights.append(f"⚠️ Large gaps: {avg_gap_hours:.0f} hours between sessions avg")
    elif avg_gap_hours < 24:
        insights.append(
            f"✅ Frequent engagement: {avg_gap_hours:.0f} hours between sessions"
        )

    # Most consistent week
    if streaks.most_consistent_week:
        insights.append(f"📅 Best week: {streaks.most_consistent_week}")

    return insights


def _generate_productivity_insights(insights: t.Any) -> list[str]:
    """Generate comprehensive productivity insights."""
    all_insights = []

    # Best performance window
    if insights.best_performance_window:
        all_insights.append(f"⭐ Optimal time: {insights.best_performance_window}")

    # Session length recommendation
    if insights.recommended_session_length:
        all_insights.append(
            f"📐 Recommended length: {insights.recommended_session_length}"
        )

    # Break interval
    all_insights.append(
        f"⏱️ Break interval: Every {insights.optimal_break_interval:.0f} minutes"
    )

    # Peak periods
    if insights.peak_productivity_periods:
        all_insights.append(
            f"🎯 Peak periods: {', '.join(insights.peak_productivity_periods[:3])}"
        )

    # Quality factors
    if insights.quality_factors:
        all_insights.extend([f"💡 {factor}" for factor in insights.quality_factors])

    # Improvement suggestions
    if insights.improvement_suggestions:
        all_insights.extend(
            [f"✨ {suggestion}" for suggestion in insights.improvement_suggestions]
        )

    return all_insights
