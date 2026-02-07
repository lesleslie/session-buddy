# Session Analytics & Visualization Guide

Comprehensive guide to session analytics and visualization capabilities in Session-Buddy.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [CLI Commands](#cli-commands)
- [Python API](#python-api)
- [Data Dictionary](#data-dictionary)
- [Visualization](#visualization)
- [External Tools Integration](#external-tools-integration)
- [Query Reference](#query-reference)

## Overview

Session-Buddy's analytics module provides comprehensive insights into session patterns, component usage, and system performance. It enables data-driven decision making through:

- **Query Methods**: SQL-based queries for flexible data extraction
- **Python API**: Programmatic access for custom analytics
- **CLI Commands**: Quick terminal-based analytics
- **Visualizations**: ASCII charts for terminal output
- **External Integration**: SQL export for Grafana, Metabase, etc.

### Key Features

- Track active sessions in real-time
- Analyze session statistics by component/shell type
- Calculate average durations and quality scores
- Identify most active components
- Monitor error rates and patterns
- Generate comprehensive reports
- Export queries for external visualization

## Quick Start

### Installation

Analytics are included with Session-Buddy. No additional installation required.

```bash
# Session-Buddy is already installed
session-buddy --version
```

### Basic Usage

```bash
# Show session statistics for last 7 days
session-buddy analytics sessions

# Show for last 30 days
session-buddy analytics sessions --days 30

# Show component usage
session-buddy analytics components

# Show error rates
session-buddy analytics errors

# Generate comprehensive report
session-buddy analytics report --days 30
```

## CLI Commands

### sessions

Show session statistics including total sessions, average duration, active sessions, and error rate.

```bash
session-buddy analytics sessions [OPTIONS]

Options:
  --days, -d INTEGER    Number of days to analyze [default: 7]
  --component, -c TEXT  Filter by component name
  --json, -j            Output as JSON

Examples:
  session-buddy analytics sessions --days 30
  session-buddy analytics sessions --component admin-shell
  session-buddy analytics sessions --days 7 --json > stats.json
```

**Output:**

```
================================================================================
SESSION STATISTICS
================================================================================

Total Sessions by Component:
admin-shell                 150    ████████████████████████████████
ipython                     120    ████████████████████████
bash                        80     ████████████

Detailed Statistics:
| Component        | Sessions | Avg Duration | Active | Error Rate |
|------------------|----------|--------------|--------|------------|
| admin-shell      |      150 |         450s |      5 |       2.5% |
| ipython          |      120 |         600s |      3 |       1.2% |
| bash             |       80 |         180s |      2 |       0.0% |
```

### duration

Show average session duration by component.

```bash
session-buddy analytics duration [OPTIONS]

Options:
  --days, -d INTEGER    Number of days to analyze [default: 7]
  --component, -c TEXT  Filter by component name
  --json, -j            Output as JSON

Examples:
  session-buddy analytics duration --days 30
  session-buddy analytics duration --component ipython
```

**Output:**

```
================================================================================
AVERAGE SESSION DURATION
================================================================================

Time Period: Last 30 days

  ipython                        10m 0s (600s)
  admin-shell                     7m 30s (450s)
  bash                            3m 0s (180s)
```

### components

Show most active components by session count and usage.

```bash
session-buddy analytics components [OPTIONS]

Options:
  --days, -d INTEGER    Number of days to analyze [default: 7]
  --limit, -l INTEGER   Maximum components to show [default: 10]
  --json, -j            Output as JSON

Examples:
  session-buddy analytics components --days 30 --limit 20
```

**Output:**

```
================================================================================
COMPONENT USAGE
================================================================================

Sessions by Component:
admin-shell                 150    ████████████████████████████████
ipython                     120    ████████████████████████
bash                        80     ████████████

Detailed Usage:
| Component     | Sessions | Total Duration | Avg Quality | Last Active        |
|---------------|----------|----------------|-------------|-------------------|
| admin-shell   |      150 |          62.5h |        75.2 | 2025-01-15 14:30   |
| ipython       |      120 |          20.0h |        82.1 | 2025-01-15 15:45   |
| bash          |       80 |           4.0h |        70.0 | 2025-01-15 16:00   |
```

### errors

Show error rate statistics by component.

```bash
session-buddy analytics errors [OPTIONS]

Options:
  --days, -d INTEGER    Number of days to analyze [default: 7]
  --component, -c TEXT  Filter by component name
  --json, -j            Output as JSON

Examples:
  session-buddy analytics errors --days 30
  session-buddy analytics errors --component admin-shell
```

**Output:**

```
================================================================================
ERROR RATE STATISTICS
================================================================================

Time Period: Last 30 days

  admin-shell:
    Error Rate:    2.50%
    Total Sessions: 150
    Failed:        4
    Most Common:   Connection timeout to MCP server

  ipython:
    Error Rate:    1.20%
    Total Sessions: 120
    Failed:        1
    Most Common:   Kernel startup failed
```

### active

Show currently active sessions.

```bash
session-buddy analytics active [OPTIONS]

Options:
  --json, -j            Output as JSON

Examples:
  session-buddy analytics active
```

**Output:**

```
================================================================================
ACTIVE SESSIONS (5)
================================================================================

  Session: mahavishnu-20250115-143000
    Component: admin-shell
    Project:   mahavishnu
    Duration:  2h 15m 30s
    Started:   2025-01-15T14:30:00Z

  Session: crackerjack-20250115-153000
    Component: ipython
    Project:   crackerjack
    Duration:  1h 45m 15s
    Started:   2025-01-15T15:30:00Z
```

### report

Generate comprehensive analytics report.

```bash
session-buddy analytics report [OPTIONS]

Options:
  --days, -d INTEGER    Number of days to analyze [default: 7]
  --output, -o TEXT     Output file path

Examples:
  session-buddy analytics report --days 30
  session-buddy analytics report --days 7 --output report.txt
```

**Output:**

```
================================================================================
SESSION-BUDDY ANALYTICS REPORT
================================================================================

SUMMARY:
  Total Sessions: 350
  Components Analyzed: 3
  Total Errors: 5
  Average Error Rate: 1.23%

TOP COMPONENTS (by session count):
  1. admin-shell: 150 sessions (avg quality: 75.2/100)
  2. ipython: 120 sessions (avg quality: 82.1/100)
  3. bash: 80 sessions (avg quality: 70.0/100)

COMPONENTS WITH HIGH ERROR RATES:
  • admin-shell: 2.5%
    Most common: Connection timeout to MCP server

================================================================================
End of Report
================================================================================
```

### sql

Export SQL queries for external tools.

```bash
session-buddy analytics sql QUERY_NAME [OPTIONS]

Arguments:
  QUERY_NAME          Query name (see Query Reference below)

Options:
  --days, -d INTEGER    Number of days to analyze [default: 7]

Available Queries:
  - active_sessions: Currently active sessions
  - session_stats: Session statistics by component
  - average_duration: Average duration by component
  - most_active: Most active components
  - error_rate: Error rates by component

Examples:
  session-buddy analytics sql session_stats --days 30 > query.sql
  session-buddy analytics sql error_rate --days 7 | duckdb mydb.duckdb
```

## Python API

### Basic Usage

```python
from session_buddy.analytics import SessionAnalytics

# Initialize analytics
analytics = SessionAnalytics()

# Get session statistics
stats = await analytics.get_session_stats(days=7)
for stat in stats:
    print(f"{stat.component_name}: {stat.total_sessions} sessions")

# Get average duration
durations = await analytics.get_average_session_duration(days=30)
for component, duration in durations.items():
    print(f"{component}: {duration:.0f}s average")
```

### Advanced Usage

```python
from datetime import datetime, timedelta, UTC
from session_buddy.analytics import SessionAnalytics

analytics = SessionAnalytics()

# Query specific time range
start = datetime.now(UTC) - timedelta(days=30)
end = datetime.now(UTC)
sessions = await analytics.get_sessions_by_time_range(start_date=start, end_date=end)

# Filter by component
ipython_stats = await analytics.get_session_stats(
    days=30,
    component='ipython'
)

# Get most active components
components = await analytics.get_most_active_components(days=30, limit=5)

# Get error rates
error_rates = await analytics.get_session_error_rate(days=30)

# Visualize results
output = analytics.visualize_session_stats(stats)
print("\n".join(output))
```

### Custom Database Path

```python
from pathlib import Path
from session_buddy.analytics import SessionAnalytics

# Use custom database path
analytics = SessionAnalytics(
    database_path=Path("~/custom/session_data.duckdb")
)

stats = await analytics.get_session_stats(days=7)
```

### Generating Reports

```python
from session_buddy.analytics import (
    SessionAnalytics,
    create_session_summary_report
)

analytics = SessionAnalytics()

# Gather data
stats = await analytics.get_session_stats(days=30)
components = await analytics.get_most_active_components(days=30)
error_rates = await analytics.get_session_error_rate(days=30)

# Generate report
report = create_session_summary_report(
    stats=stats,
    components=components,
    error_rates=error_rates
)

print(report)
```

## Data Dictionary

### sessions Table

Core table storing session data.

| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT | Unique session identifier |
| component_name | TEXT | Component or shell type (admin-shell, ipython, bash, etc.) |
| start_time | TIMESTAMP | Session start timestamp |
| end_time | TIMESTAMP | Session end timestamp (NULL for active sessions) |
| duration_seconds | INTEGER | Session duration in seconds |
| quality_score | REAL | Session quality score (0-100) |
| project | TEXT | Associated project name |
| error_occurred | BOOLEAN | Whether an error occurred during session |
| error_message | TEXT | Error message if error occurred |

### SessionStats Object

| Field | Type | Description |
|-------|------|-------------|
| component_name | str | Component name |
| total_sessions | int | Total number of sessions |
| avg_duration | float | Average duration in seconds |
| active_sessions | int | Number of active sessions |
| error_rate | float | Error rate percentage (0-100) |
| date_range | str | Date range description |

### ComponentUsage Object

| Field | Type | Description |
|-------|------|-------------|
| component_name | str | Component name |
| session_count | int | Number of sessions |
| total_duration | int | Total duration in seconds |
| avg_quality_score | float | Average quality score |
| last_active | datetime | Last active timestamp |

## Visualization

### ASCII Charts

The analytics module provides built-in ASCII visualization for terminal output.

```python
from session_buddy.analytics import SessionAnalytics

analytics = SessionAnalytics()
stats = await analytics.get_session_stats(days=7)

# Generate visualization
output = analytics.visualize_session_stats(stats)
print("\n".join(output))
```

Output:
```
Total Sessions by Component:
admin-shell                 150    ████████████████████████████████
ipython                     120    ████████████████████████
bash                        80     ████████████
```

### Time Series Visualization

```python
sessions = await analytics.get_sessions_by_time_range(
    start_date=datetime.now(UTC) - timedelta(days=30)
)

output = analytics.visualize_time_series(sessions, bucket_size="day")
print("\n".join(output))
```

Output:
```
SESSION TIME SERIES (by day)

Activity Sparkline:
▁▃▄▆█▇▅▃▁▂▄▆█▇▆▄▂▁▁▂▃▅▆█▇▆▅▃▂▁▁

Session Counts:
| Time              | Sessions |
|-------------------|----------|
| 2025-01-01        |       12 |
| 2025-01-02        |       15 |
| 2025-01-03        |       18 |
```

### Custom Visualizations

```python
from session_buddy.analytics import ASCIIVisualizer

visualizer = ASCIIVisualizer()

# Create custom bar chart
data = [("Component A", 100), ("Component B", 75), ("Component C", 50)]
chart = visualizer.bar_chart(data, width=40)
print("\n".join(chart))

# Create custom table
headers = ["Name", "Value", "Status"]
rows = [["Item 1", "100", "Active"], ["Item 2", "75", "Pending"]]
table = visualizer.table(headers, rows)
print("\n".join(table))

# Create sparkline
values = [1, 2, 3, 5, 8, 13, 21, 13, 8, 5, 3, 2, 1]
sparkline = visualizer.sparkline(values)
print(sparkline)
```

## External Tools Integration

### Grafana

1. Install Grafana DuckDB plugin: https://github.com/matrix-org/grafana-duckdb

2. Configure data source:
   - Name: Session-Buddy Analytics
   - Database: ~/.claude/data/reflection.duckdb
   - Format: Table

3. Create dashboard panels using exported SQL queries:

```bash
# Export query for Grafana
session-buddy analytics sql session_stats --days 30 > grafana_query.sql
```

4. Copy SQL to Grafana query editor

### Metabase

1. Add DuckDB database connection in Metabase
2. Use native query mode with exported SQL:

```bash
session-buddy analytics sql error_rate --days 7 > metabase_query.sql
```

### Python Integration

```python
import duckdb
import pandas as pd
import matplotlib.pyplot as plt

# Connect to Session-Buddy database
conn = duckdb.connect("~/.claude/data/reflection.duckdb")

# Query session statistics
query = """
    SELECT
        component_name,
        COUNT(*) as total_sessions,
        AVG(duration_seconds) as avg_duration
    FROM sessions
    WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    GROUP BY component_name
"""

df = conn.execute(query).df()

# Create visualization
df.plot(kind='bar', x='component_name', y='total_sessions')
plt.title('Sessions by Component')
plt.xlabel('Component')
plt.ylabel('Total Sessions')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('sessions_by_component.png')
```

### Jupyter Notebooks

```python
# In Jupyter notebook
from session_buddy.analytics import SessionAnalytics
import pandas as pd

analytics = SessionAnalytics()

# Get data
stats = await analytics.get_session_stats(days=30)
df = pd.DataFrame([s.to_dict() for s in stats])

# Display as interactive table
df.style.background_gradient(cmap='Blues')

# Create plots
df.plot(kind='bar', x='component_name', y='total_sessions')
```

## Query Reference

### active_sessions

Returns currently active sessions (no end_time).

```sql
SELECT
    session_id,
    component_name,
    start_time,
    CAST(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time)) AS INTEGER) as duration_seconds,
    project
FROM sessions
WHERE end_time IS NULL
ORDER BY start_time DESC
```

### session_stats

Returns aggregated statistics by component.

```sql
SELECT
    component_name,
    COUNT(*) as total_sessions,
    COALESCE(AVG(duration_seconds), 0) as avg_duration,
    COUNT(CASE WHEN end_time IS NULL THEN 1 END) as active_sessions,
    COALESCE(
        COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0),
        0.0
    ) as error_rate
FROM sessions
WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY component_name
ORDER BY total_sessions DESC
```

### average_duration

Returns average duration by component for completed sessions only.

```sql
SELECT
    component_name,
    AVG(duration_seconds) as avg_duration
FROM sessions
WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
    AND end_time IS NOT NULL
    AND duration_seconds IS NOT NULL
GROUP BY component_name
ORDER BY avg_duration DESC
```

### most_active

Returns top components by session count.

```sql
SELECT
    component_name,
    COUNT(*) as session_count,
    COALESCE(SUM(duration_seconds), 0) as total_duration,
    COALESCE(AVG(quality_score), 0.0) as avg_quality_score,
    MAX(start_time) as last_active
FROM sessions
WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY component_name
ORDER BY session_count DESC
LIMIT 10
```

### error_rate

Returns error statistics by component.

```sql
SELECT
    component_name,
    COUNT(*) as total_sessions,
    COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) as failed_sessions,
    COALESCE(
        COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0),
        0.0
    ) as error_rate,
    MODE() WITHIN GROUP (ORDER BY error_message) as most_common_error
FROM sessions
WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY component_name
ORDER BY error_rate DESC
```

## Examples

### Monitor Session Health

```python
import asyncio
from session_buddy.analytics import SessionAnalytics

async def monitor_session_health():
    analytics = SessionAnalytics()

    # Get active sessions
    active = await analytics.get_active_sessions()
    print(f"Active sessions: {len(active)}")

    # Check for long-running sessions (> 2 hours)
    long_running = [s for s in active if s.get('duration_seconds', 0) > 7200]
    if long_running:
        print(f"\nLong-running sessions ({len(long_running)}):")
        for session in long_running:
            print(f"  - {session['session_id']}: {session['duration_seconds'] / 3600:.1f}h")

    # Get error rates
    error_rates = await analytics.get_session_error_rate(days=1)
    high_errors = {
        name: data
        for name, data in error_rates.items()
        if data['error_rate'] > 5.0
    }

    if high_errors:
        print(f"\nHigh error rate components:")
        for name, data in high_errors.items():
            print(f"  - {name}: {data['error_rate']:.1f}%")

asyncio.run(monitor_session_health())
```

### Weekly Report Email

```python
import asyncio
from datetime import datetime
from session_buddy.analytics import SessionAnalytics, create_session_summary_report

async def generate_weekly_report():
    analytics = SessionAnalytics()

    # Gather data
    stats = await analytics.get_session_stats(days=7)
    components = await analytics.get_most_active_components(days=7, limit=5)
    error_rates = await analytics.get_session_error_rate(days=7)

    # Generate report
    report = create_session_summary_report(stats, components, error_rates)

    # Add header
    header = f"Weekly Session Analytics Report\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    full_report = header + report

    # Save or send email
    with open('weekly_report.txt', 'w') as f:
        f.write(full_report)

    print("Weekly report generated: weekly_report.txt")

asyncio.run(generate_weekly_report())
```

### Component Performance Dashboard

```python
import asyncio
from session_buddy.analytics import SessionAnalytics

async def component_dashboard():
    analytics = SessionAnalytics()

    # Get component usage
    components = await analytics.get_most_active_components(days=30, limit=10)

    print("Component Performance Dashboard (Last 30 Days)")
    print("=" * 60)

    for comp in components:
        print(f"\n{comp.component_name}")
        print(f"  Sessions:     {comp.session_count}")
        print(f"  Total Time:   {comp.total_duration / 3600:.1f} hours")
        print(f"  Avg Quality:  {comp.avg_quality_score:.1f}/100")
        print(f"  Last Active:  {comp.last_active.strftime('%Y-%m-%d %H:%M')}")

        # Quality rating
        if comp.avg_quality_score >= 80:
            rating = "Excellent"
        elif comp.avg_quality_score >= 60:
            rating = "Good"
        else:
            rating = "Needs Improvement"
        print(f"  Rating:       {rating}")

asyncio.run(component_dashboard())
```

## Troubleshooting

### No Data Found

If queries return no data:

1. Check database path:
   ```bash
   echo $SESSION_BUDDY_DATABASE_PATH
   ls -la ~/.claude/data/reflection.duckdb
   ```

2. Verify sessions table exists:
   ```bash
   duckdb ~/.claude/data/reflection.duckdb "SHOW TABLES"
   ```

3. Check if sessions table has data:
   ```bash
   duckdb ~/.claude/data/reflection.duckdb "SELECT COUNT(*) FROM sessions"
   ```

### Database Connection Errors

If you get connection errors:

1. Install DuckDB:
   ```bash
   pip install duckdb
   ```

2. Verify database file permissions:
   ```bash
   ls -la ~/.claude/data/reflection.duckdb
   ```

3. Check database integrity:
   ```bash
   duckdb ~/.claude/data/reflection.duckdb "PRAGMA database_size"
   ```

### Performance Issues

For large databases:

1. Use time range filters:
   ```python
   # Instead of querying all data
   stats = await analytics.get_session_stats(days=7)  # Good
   ```

2. Use component filters:
   ```python
   stats = await analytics.get_session_stats(days=30, component='admin-shell')
   ```

3. Use limit for component queries:
   ```python
   components = await analytics.get_most_active_components(days=30, limit=10)
   ```

## Best Practices

1. **Use Appropriate Time Ranges**: Query only the data you need
2. **Filter Early**: Use component filters when analyzing specific components
3. **Schedule Reports**: Generate reports periodically (daily, weekly)
4. **Monitor Errors**: Track error rates to identify issues early
5. **Export for Visualization**: Use SQL export for complex dashboards
6. **Archive Old Data**: Move old sessions to archive tables to maintain performance

## Related Documentation

- [Session-Buddy CLI Guide](../README.md)
- [Database Schema](../memory/schema_v2.md)
- [MCP Tools Specification](../mcp/tools/README.md)
