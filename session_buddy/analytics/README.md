# Session-Buddy Analytics

Comprehensive session analytics and visualization system for Session-Buddy.

## Overview

The analytics module provides insights into session patterns, component usage, and system performance through:

- **Query Methods**: SQL-based queries for flexible data extraction
- **Python API**: Programmatic access for custom analytics
- **CLI Commands**: Quick terminal-based analytics
- **Visualizations**: ASCII charts for terminal output
- **External Integration**: SQL export for Grafana, Metabase, etc.

## Installation

No additional installation required - analytics are included with Session-Buddy.

## Quick Start

### CLI Usage

```bash
# Show session statistics
session-buddy analytics sessions --days 7

# Show component usage
session-buddy analytics components --days 30

# Show error rates
session-buddy analytics errors --component admin-shell

# Generate comprehensive report
session-buddy analytics report --days 7 --output report.txt
```

### Python API

```python
from session_buddy.analytics import SessionAnalytics

analytics = SessionAnalytics()

# Get statistics
stats = await analytics.get_session_stats(days=7)

# Get active sessions
active = await analytics.get_active_sessions()

# Visualize results
output = analytics.visualize_session_stats(stats)
print("\n".join(output))
```

## Features

### Query Methods

- `get_active_sessions()` - Currently active sessions
- `get_session_stats()` - Statistics by component/shell type
- `get_sessions_by_time_range()` - Sessions in date range
- `get_average_session_duration()` - Avg duration by component
- `get_most_active_components()` - Components with most sessions
- `get_session_error_rate()` - Error rate by component

### Visualization

- ASCII bar charts for session counts
- Time series sparklines
- Formatted tables for detailed statistics
- Custom visualizations with `ASCIIVisualizer`

### Export Capabilities

- SQL queries for external tools
- JSON output format
- Comprehensive text reports

## Documentation

- [Complete Guide](../../docs/SESSION_ANALYTICS.md)
- [Quick Reference](../../docs/SESSION_ANALYTICS_QUICKREF.md)
- [Example Usage](../../examples/analytics_example.py)

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

## Integration Examples

### Grafana

```bash
# Export query
session-buddy analytics sql session_stats --days 30 > grafana_query.sql

# Use with DuckDB plugin in Grafana
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

## Testing

```bash
# Run unit tests
pytest tests/unit/test_analytics_module.py -v

# Run with coverage
pytest tests/unit/test_analytics_module.py --cov=session_buddy.analytics --cov-report=html
```

## Architecture

```
session_buddy/analytics/
├── __init__.py              # Package exports
├── session_analytics.py     # Main analytics class
├── usage_tracker.py         # Usage analytics (existing)
└── README.md               # This file
```

## Contributing

When adding new analytics features:

1. Add query method to `SessionAnalytics`
1. Add corresponding CLI command in `cli.py`
1. Update documentation
1. Add unit tests
1. Update this README

## License

BSD-3-Clause - See LICENSE file for details.
