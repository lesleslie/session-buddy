"""MCP tools for memory health monitoring and maintenance.

This module provides Model Context Protocol tools for:
- Reflection database health analysis
- Error pattern and hot-spot detection
- Cleanup and optimization recommendations
- Memory system maintenance insights
"""

from __future__ import annotations

import typing as t

from session_buddy.core.memory_health import get_memory_health_analyzer


def register_memory_health_tools(server: t.Any) -> None:
    """Register memory health MCP tools.

    Args:
        server: SessionBuddyServer instance to register tools on
    """

    @server.tool()  # type: ignore[misc]
    async def get_reflection_health(stale_threshold_days: int = 90) -> dict[str, t.Any]:
        """Get reflection database health metrics."""
        try:
            analyzer = get_memory_health_analyzer()
            await analyzer.initialize()

            metrics = await analyzer.get_reflection_health(
                stale_threshold_days=stale_threshold_days
            )

            result = metrics.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_reflection_health_insights(metrics)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve reflection health metrics",
            }

    @server.tool()  # type: ignore[misc]
    async def get_error_hotspots() -> dict[str, t.Any]:
        """Get error pattern and hot-spot metrics."""
        try:
            analyzer = get_memory_health_analyzer()
            await analyzer.initialize()

            metrics = await analyzer.get_error_hotspots()

            result = metrics.to_dict()
            result["success"] = True

            # Add insights
            result["insights"] = _generate_error_hotspot_insights(metrics)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve error hot-spot metrics",
            }

    @server.tool()  # type: ignore[misc]
    async def get_cleanup_recommendations() -> dict[str, t.Any]:
        """Get cleanup and optimization recommendations."""
        try:
            analyzer = get_memory_health_analyzer()
            await analyzer.initialize()

            recommendations = await analyzer.get_cleanup_recommendations()

            # Group by priority
            by_priority = {
                "high": [r for r in recommendations if r["priority"] == "high"],
                "medium": [r for r in recommendations if r["priority"] == "medium"],
                "low": [r for r in recommendations if r["priority"] == "low"],
            }

            # Group by category
            by_category: dict[str, list[dict[str, t.Any]]] = {}
            for rec in recommendations:
                category = rec["category"]
                if category not in by_category:
                    by_category[category] = []
                by_category[category].append(rec)

            return {
                "success": True,
                "recommendations": recommendations,
                "total_recommendations": len(recommendations),
                "by_priority": by_priority,
                "by_category": by_category,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to generate cleanup recommendations",
            }

    @server.prompt()  # type: ignore[misc]
    def memory_health_help() -> str:
        """Get help for memory health monitoring and maintenance."""
        return """# Memory Health Monitoring - Maintenance Guide

## Available Tools

### get_reflection_health
Reflection database health analysis:
- **Staleness detection**: Identifies old reflections for cleanup
- **Storage tracking**: Monitors database size and growth
- **Tag distribution**: Shows reflection categorization
- **Age analysis**: Average and timestamp ranges

**Usage:**
```python
# Default 90-day staleness threshold
get_reflection_health()

# Custom threshold (60 days)
get_reflection_health(stale_threshold_days=60)
```

**Key Metrics:**
- `stale_reflections`: Count of reflections older than threshold
- `storage_size_mb`: Database storage size in megabytes
- `avg_reflection_age_days`: Average reflection age
- `tags_distribution`: Reflection count per tag

### get_error_hotspots
Error pattern and hot-spot analysis:
- **Error type frequency**: Most common error types
- **Resolution time**: Average, fastest, slowest fix times
- **Unresolved errors**: Errors without documented fixes
- **Error rate**: Recent error frequency (30-day window)

**Usage:**
```python
result = await get_error_hotspots()
print(f"Recent error rate: {result['recent_error_rate']:.1f}/day")
```

**Key Metrics:**
- `most_common_error_types`: Top error types by frequency
- `avg_resolution_time_minutes`: Mean time to fix errors
- `unresolved_errors`: Errors needing documentation
- `recent_error_rate`: Errors/day over last 30 days

### get_cleanup_recommendations
Actionable maintenance and optimization recommendations:
- **Stale reflection cleanup**: Remove outdated reflections
- **Storage optimization**: Archive old data to reduce size
- **Error pattern investigation**: Address recurring issues
- **Unresolved error review**: Document missing solutions

**Usage:**
```python
result = await get_cleanup_recommendations()

# High-priority items first
for rec in result['by_priority']['high']:
    print(f"[{rec['category']}] {rec['action']}")
    print(f"  {rec['details']}")
    print(f"  Impact: {rec['estimated_impact']}")
```

**Priority Levels:**
- **high**: Urgent issues affecting quality or performance
- **medium**: Important maintenance tasks
- **low**: Nice-to-have optimizations

## Common Maintenance Workflows

### Routine Health Check

1. **Check reflection health**:
   ```python
   health = await get_reflection_health()
   # Look for: stale_pct > 20%, storage_size_mb > 100
   ```

2. **Review error patterns**:
   ```python
   errors = await get_error_hotspots()
   # Look for: recent_error_rate > 2.0, unresolved_errors > 5
   ```

3. **Get recommendations**:
   ```python
   cleanup = await get_cleanup_recommendations()
   # Focus on high-priority items first
   ```

### Quality Improvement

**High Error Rate** (>2 errors/day):
- Use `get_error_hotspots()` to identify common types
- Review `most_common_error_types` for patterns
- Consider systemic fixes for recurring issues

**Unresolved Errors** (>5):
- Review documentation gaps
- Document successful solutions
- Build debugging intelligence knowledge base

### Storage Optimization

**Large Database** (>100MB):
- Check stale reflection percentage
- Archive old reflections (>90 days)
- Consider tag-based filtering for search optimization

**Stale Reflections** (>20%):
- Reduce staleness threshold to identify more outdated content
- Archive older reflections to separate storage
- Improve reflection quality with better tagging

## Best Practices

- **Weekly health checks**: Run `get_reflection_health()` weekly to monitor trends
- **Post-error review**: Use `get_error_hotspots()` after fixing errors to track patterns
- **Pre-cleanup**: Always run `get_cleanup_recommendations()` before manual cleanup
- **Proactive maintenance**: Address high-priority recommendations promptly

## Interpreting Metrics

### Reflection Health Benchmarks
- **Healthy**: <10% stale reflections, <50MB storage
- **Warning**: 10-20% stale, 50-100MB storage
- **Critical**: >20% stale, >100MB storage

### Error Rate Benchmarks
- **Excellent**: <0.5 errors/day
- **Good**: 0.5-2.0 errors/day
- **Concerning**: >2.0 errors/day

### Resolution Time Benchmarks
- **Fast**: <5 minutes average
- **Normal**: 5-15 minutes average
- **Slow**: >15 minutes average (may indicate complexity gaps)
"""


def _generate_reflection_health_insights(metrics: t.Any) -> list[str]:
    """Generate human-readable insights from reflection health metrics.

    Args:
        metrics: ReflectionHealthMetrics instance

    Returns:
        List of insight strings
    """
    insights = []

    # Staleness insights
    if metrics.total_reflections > 0:
        stale_pct = metrics.stale_reflections / metrics.total_reflections * 100
        if stale_pct > 20:
            insights.append(
                f"⚠️ High staleness: {stale_pct:.1f}% of reflections are "
                f"older than {metrics.stale_threshold_days} days"
            )
        elif stale_pct > 10:
            insights.append(
                f"📊 Growing staleness: {stale_pct:.1f}% of reflections are "
                f"older than {metrics.stale_threshold_days} days"
            )
        else:
            insights.append(
                f"✅ Healthy staleness: Only {stale_pct:.1f}% stale reflections"
            )

    # Storage size insights
    storage_mb = metrics.storage_size_bytes / 1024 / 1024
    if storage_mb > 100:
        insights.append(
            f"💾 Large database: {storage_mb:.1f}MB - consider archiving old reflections"
        )
    elif storage_mb > 50:
        insights.append(f"📦 Moderate storage: {storage_mb:.1f}MB used")
    else:
        insights.append(f"✅ Efficient storage: {storage_mb:.1f}MB")

    # Age distribution insights
    if metrics.avg_reflection_age_days > 60:
        insights.append(
            f"⏰ Aging content: Average reflection is "
            f"{metrics.avg_reflection_age_days:.0f} days old"
        )
    elif metrics.avg_reflection_age_days < 14:
        insights.append(
            f"🆕 Fresh content: Average reflection is "
            f"{metrics.avg_reflection_age_days:.0f} days old"
        )

    # Tag distribution insights
    if metrics.tags_distribution:
        top_tag = max(metrics.tags_distribution, key=metrics.tags_distribution.get)  # type: ignore[arg-type]
        top_count = metrics.tags_distribution[top_tag]
        insights.append(f"🏷️ Most common tag: '{top_tag}' ({top_count} reflections)")

    return insights


def _generate_error_hotspot_insights(metrics: t.Any) -> list[str]:
    """Generate insights from error hot-spot metrics.

    Args:
        metrics: ErrorHotSpotMetrics instance

    Returns:
        List of insight strings
    """
    insights = []

    # Error rate insights
    if metrics.recent_error_rate > 2.0:
        insights.append(
            f"🚨 High error rate: {metrics.recent_error_rate:.1f} errors/day over last 30 days"
        )
    elif metrics.recent_error_rate > 1.0:
        insights.append(
            f"⚠️ Elevated error rate: {metrics.recent_error_rate:.1f} errors/day"
        )
    elif metrics.recent_error_rate > 0.5:
        insights.append(
            f"📊 Moderate error rate: {metrics.recent_error_rate:.1f} errors/day"
        )
    else:
        insights.append(
            f"✅ Low error rate: {metrics.recent_error_rate:.1f} errors/day"
        )

    # Unresolved errors insights
    if metrics.unresolved_errors > 10:
        insights.append(
            f"❌ Many unresolved errors: {metrics.unresolved_errors} errors lack documentation"
        )
    elif metrics.unresolved_errors > 5:
        insights.append(
            f"⚠️ Unresolved errors: {metrics.unresolved_errors} errors need documentation"
        )

    # Resolution time insights
    if metrics.avg_resolution_time_minutes:
        if metrics.avg_resolution_time_minutes < 5:
            insights.append(
                f"⚡ Fast resolution: {metrics.avg_resolution_time_minutes:.1f}min average fix time"
            )
        elif metrics.avg_resolution_time_minutes > 15:
            insights.append(
                f"🐌 Slow resolution: {metrics.avg_resolution_time_minutes:.1f}min average - "
                "may indicate knowledge gaps"
            )

    # Common error types insights
    if metrics.most_common_error_types:
        top_error_type, top_count = metrics.most_common_error_types[0]
        if top_count >= 5:
            insights.append(
                f"🔄 Recurring issue: '{top_error_type}' occurs {top_count} times - "
                "consider systemic fix"
            )
        elif top_count >= 3:
            insights.append(
                f"📋 Pattern detected: '{top_error_type}' occurs {top_count} times"
            )

    return insights
