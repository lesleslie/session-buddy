# Session Analytics - Quick Reference

Quick reference guide for Session-Buddy analytics commands.

## CLI Commands

```bash
# Session statistics
session-buddy analytics sessions --days 7
session-buddy analytics sessions --days 30 --component admin-shell
session-buddy analytics sessions --json > stats.json

# Duration statistics
session-buddy analytics duration --days 7
session-buddy analytics duration --component ipython

# Component usage
session-buddy analytics components --days 7 --limit 10

# Error rates
session-buddy analytics errors --days 7
session-buddy analytics errors --component admin-shell

# Active sessions
session-buddy analytics active

# Comprehensive report
session-buddy analytics report --days 7
session-buddy analytics report --days 30 --output report.txt

# Export SQL queries
session-buddy analytics sql session_stats --days 30 > query.sql
session-buddy analytics sql error_rate --days 7
```

## Python API

```python
from session_buddy.analytics import SessionAnalytics

analytics = SessionAnalytics()

# Get statistics
stats = await analytics.get_session_stats(days=7)
active = await analytics.get_active_sessions()
durations = await analytics.get_average_session_duration(days=7)
components = await analytics.get_most_active_components(days=7, limit=10)
errors = await analytics.get_session_error_rate(days=7)

# Visualize
output = analytics.visualize_session_stats(stats)
print("\n".join(output))

# Generate report
from session_buddy.analytics import create_session_summary_report
report = create_session_summary_report(stats, components, errors)
```

## Query Names (for SQL Export)

- `active_sessions` - Currently active sessions
- `session_stats` - Session statistics by component
- `average_duration` - Average duration by component
- `most_active` - Most active components
- `error_rate` - Error rates by component

## Common Options

- `--days, -d` - Number of days to analyze (default: 7)
- `--component, -c` - Filter by component name
- `--limit, -l` - Maximum results to return
- `--json, -j` - Output as JSON
- `--output, -o` - Save to file

## Data Dictionary

| Field | Type | Description |
|-------|------|-------------|
| session_id | TEXT | Unique session identifier |
| component_name | TEXT | Component/shell type |
| start_time | TIMESTAMP | Session start |
| end_time | TIMESTAMP | Session end (NULL if active) |
| duration_seconds | INTEGER | Duration in seconds |
| quality_score | REAL | Quality score (0-100) |
| project | TEXT | Project name |
| error_occurred | BOOLEAN | Error flag |
| error_message | TEXT | Error details |

## Example Output

```
================================================================================
SESSION STATISTICS
================================================================================

Total Sessions by Component:
admin-shell                 150    ████████████████████████████████
ipython                     120    ████████████████████████
bash                        80     ████████████

Detailed Statistics:
| Component     | Sessions | Avg Duration | Active | Error Rate |
|---------------|----------|--------------|--------|------------|
| admin-shell   |      150 |         450s |      5 |       2.5% |
| ipython       |      120 |         600s |      3 |       1.2% |
| bash          |       80 |         180s |      2 |       0.0% |
```

## Integration Examples

### Grafana

```bash
# Install DuckDB plugin
# Export query
session-buddy analytics sql session_stats --days 30 > grafana_query.sql
# Use in Grafana panel
```

### Python + Pandas

```python
import duckdb
conn = duckdb.connect("~/.claude/data/reflection.duckdb")
df = conn.execute("SELECT * FROM sessions").df()
print(df.describe())
```

### Jupyter Notebook

```python
from session_buddy.analytics import SessionAnalytics
analytics = SessionAnalytics()
stats = await analytics.get_session_stats(days=30)
import pandas as pd
df = pd.DataFrame([s.to_dict() for s in stats])
df.plot(kind='bar', x='component_name', y='total_sessions')
```

For complete documentation, see [SESSION_ANALYTICS.md](SESSION_ANALYTICS.md).
