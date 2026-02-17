# Crackerjack Metrics Monitoring

## Overview

The Crackerjack Metrics Monitoring system provides comprehensive insights into your code quality trends, test execution patterns, and development workflow efficiency. It analyzes historical execution data from the Crackerjack integration database to generate actionable reports.

## Features

- **Quality Trend Analysis**: Track code quality metrics over time (lint, security, complexity, coverage)
- **Alert System**: Automatic detection of quality degradation events (configurable thresholds)
- **Command Statistics**: Execution patterns, success rates, and performance metrics
- **Project Insights**: Per-project analysis of development activity
- **Performance Monitoring**: Identify slow commands and optimization opportunities
- **Multiple Output Formats**: Markdown reports for human review, JSON for automation
- **Flexible Time Ranges**: Analyze any period from 1 day to 1 year

## Installation

The monitoring script is included with Session Buddy:

```bash
# Located at: scripts/monitor_crackerjack_metrics.py
# No additional installation required
```

## Quick Start

### Basic Usage

Generate a comprehensive 30-day report:

```bash
python scripts/monitor_crackerjack_metrics.py
```

### Recent Activity (7 days)

```bash
python scripts/monitor_crackerjack_metrics.py --days 7
```

### Save Report to File

```bash
python scripts/monitor_crackerjack_metrics.py --output metrics_report.md
```

### JSON Output for Automation

```bash
python scripts/monitor_crackerjack_metrics.py --format json --output metrics.json
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--days DAYS` | Number of days to analyze | 30 |
| `--project PATH` | Filter by project path | All projects |
| `--format {markdown,json}` | Output format | markdown |
| `--output, -o FILE` | Save to file instead of stdout | stdout |
| `--alert-threshold PCT` | Percentage change to trigger alerts | 10.0 |
| `--db-path PATH` | Custom database path | ~/.claude/data/crackerjack_integration.db |

## Understanding the Report

### Executive Summary

High-level overview of your development activity:

- **Total Executions**: Number of crackerjack commands run
- **Success Rate**: Percentage of successful executions
- **Unique Commands**: Variety of commands used
- **Avg Execution Time**: Average time per command
- **Metric Records**: Total quality metrics collected

### Quality Alerts

Automatic alerts for quality issues:

| Severity | Threshold | Description |
|----------|-----------|-------------|
| Critical | ≥20% change | Immediate action required |
| Warning | ≥15% change | Investigate soon |
| Info | ≥10% change | Monitor closely |

Example alert:

```markdown
### 🔴 CRITICAL: build_status

- **Message:** build_status has declined by 100.0% (from 88.65 to 0)
- **Current Value:** 0
- **Previous Value:** 88.65
- **Change:** 100.0%
```

### Metric Trends

Track quality metrics over time:

| Metric | Direction | Strength | Meaning |
|--------|----------|----------|---------|
| `build_status` | 📈 improving | ⚡ strong | More builds passing |
| `lint_score` | 📉 declining | 🔄 moderate | More lint issues |
| `security_score` | ➡️ stable | 📍 weak | No significant change |

**Direction Indicators**:

- 📈 Improving: Metric getting better
- 📉 Declining: Metric getting worse
- ➡️ Stable: No significant change

**Strength Indicators**:

- ⚡ Strong: >5% change
- 🔄 Moderate: 1-5% change
- 📍 Weak: \<1% change

### Command Statistics

Execution patterns per command type:

| Command | Executions | Success Rate | Avg Time | Failures |
|---------|------------|--------------|----------|----------|
| test | 76 | 57.9% | 7.710s | 32 |
| lint | 75 | 65.3% | 0.132s | 26 |
| check | 30 | 60.0% | 20.380s | 12 |

**Key Insights**:

- High failure rates indicate test instability or environment issues
- Long execution times suggest performance optimization opportunities
- Low execution counts might indicate infrequent quality checks

### Performance Metrics

Command execution performance:

```markdown
## Performance Metrics

- **Average Execution Time:** 10.852s
- **Min Execution Time:** 0.000s
- **Max Execution Time:** 374.833s

### Slowest Commands
| Command | Avg Time |
|---------|----------|
| all | 117.334s |
| check | 20.380s |
| test | 7.710s |
```

**Recommendations**:

- Commands averaging >30s should be optimized
- Consider parallel execution for test suites
- Use `--fast` mode for quick feedback during development

### Project Insights

Per-project development activity:

| Project | Executions | Success Rate | Avg Time | Active Days |
|---------|------------|--------------|----------|------------|
| . | 219 | 69.0% | 3.340s | 17 |
| /tmp | 13 | 100.0% | 0.001s | 13 |
| /Users/les/Projects/session-buddy | 6 | 0.0% | 207.616s | 4 |

**Analysis**:

- High execution count with low success rate: Investigate failing tests
- Long average time: Performance optimization needed
- Few active days: Sporadic development activity

### Recommendations

Actionable insights based on analysis:

1. **CRITICAL: Build success rate declining by 100.0%** - investigate failing builds
1. **High failure rate for 'test' command (32/76 failed)** - investigate
1. **Performance: 'all' averaging 117.3s** - consider optimization

## Use Cases

### Weekly Quality Review

```bash
# Generate weekly report for team standup
python scripts/monitor_crackerjack_metrics.py --days 7 --output weekly_metrics.md
```

### Monthly Executive Summary

```bash
# Comprehensive monthly report
python scripts/monitor_crackerjack_metrics.py --days 30 --output monthly_report.md
```

### CI/CD Integration

```bash
# Check for quality degradation in pipeline
python scripts/monitor_crackerjack_metrics.py --days 1 --format json > metrics.json

# Parse with jq to check for critical alerts
jq '.quality_alerts[] | select(.severity == "critical")' metrics.json
```

### Project-Specific Analysis

```bash
# Analyze specific project
python scripts/monitor_crackerjack_metrics.py \
  --project /Users/les/Projects/myproject \
  --days 14 \
  --output project_metrics.md
```

### Custom Alert Thresholds

```bash
# More sensitive alerts (5% threshold)
python scripts/monitor_crackerjack_metrics.py --alert-threshold 5

# Less sensitive alerts (20% threshold)
python scripts/monitor_crackerjack_metrics.py --alert-threshold 20
```

## Automation Examples

### Cron Job for Weekly Reports

```bash
# Add to crontab (crontab -e)
0 9 * * 1 cd /Users/les/Projects/session-buddy && python scripts/monitor_crackerjack_metrics.py --days 7 --output ~/weekly_metrics.md
```

### GitHub Actions Integration

```yaml
name: Weekly Metrics Report

on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9am

jobs:
  metrics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Generate metrics report
        run: |
          python scripts/monitor_crackerjack_metrics.py \
            --days 7 \
            --format json \
            --output metrics.json
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: weekly-metrics
          path: metrics.json
```

### Slack Integration

```bash
#!/bin/bash
# Post metrics summary to Slack

REPORT=$(python scripts/monitor_crackerjack_metrics.py --days 7 --format json)

# Extract critical alerts
ALERTS=$(echo "$REPORT" | jq -r '.quality_alerts[] | select(.severity == "critical") | .message')

if [ -n "$ALERTS" ]; then
  curl -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"🚨 *Quality Alerts*\n$ALERTS\"}" \
    "$SLACK_WEBHOOK_URL"
fi
```

## Data Source

The monitoring script analyzes data from:

**Database**: `~/.claude/data/crackerjack_integration.db`

**Tables**:

- `crackerjack_results`: Command execution history
- `quality_metrics_history`: Quality metric snapshots
- `test_results`: Individual test results
- `progress_snapshots`: Progress tracking data

**Data Collection**: Automatically populated by the Crackerjack MCP integration during normal development workflows.

## Interpreting Trends

### Quality Metrics

| Metric | Good Direction | Bad Direction | Target |
|--------|---------------|---------------|--------|
| `build_status` | Increasing | Decreasing | >95% |
| `lint_score` | Increasing | Decreasing | >90% |
| `security_score` | Increasing | Decreasing | >85% |
| `complexity_score` | Decreasing | Increasing | \<20% high complexity |
| `code_coverage` | Increasing | Decreasing | >80% |
| `test_pass_rate` | Increasing | Decreasing | >95% |

### Common Patterns

**Sudden Quality Drop**:

- Recent commits introduced issues
- Dependency changes broke tests
- Environment configuration problems

**Gradual Decline**:

- Technical debt accumulation
- Insufficient refactoring
- Test coverage gaps

**Consistent Improvement**:

- Good development practices
- Effective code review process
- Regular quality investments

## Troubleshooting

### No Data Available

```
Error: Database not found: ~/.claude/data/crackerjack_integration.db
```

**Solution**: Run some crackerjack commands first to populate data:

```bash
python -m crackerjack run --fast
python -m crackerjack run --comp
python -m crackerjack run-tests
```

### Empty Report

If the report shows no data for the selected time period:

```bash
# Try a longer time range
python scripts/monitor_crackerjack_metrics.py --days 90
```

### Path Issues

If using a custom database path:

```bash
# Use absolute path
python scripts/monitor_crackerjack_metrics.py \
  --db-path /absolute/path/to/database.db
```

## Best Practices

1. **Regular Reviews**: Run weekly or monthly reports to track trends
1. **Alert Thresholds**: Adjust based on your project's tolerance for change
1. **Historical Context**: Compare similar time periods (account for sprint cycles)
1. **Action Orientation**: Focus on recommendations with highest impact
1. **Team Visibility**: Share reports in team meetings or dashboards
1. **Trend Analysis**: Look for patterns over multiple reports, not single data points

## Integration with Session Buddy

The monitoring script works seamlessly with Session Buddy's MCP integration:

1. **Automatic Data Collection**: Session Buddy collects metrics during normal development
1. **No Additional Setup**: Monitoring uses existing data, no configuration needed
1. **Complementary Tools**: Use alongside Session Buddy's session management features

## Advanced Usage

### Custom Analysis

Export to JSON and analyze with your preferred tools:

```python
import json
import pandas as pd

# Load metrics
with open('metrics.json') as f:
    data = json.load(f)

# Convert to DataFrame
df = pd.DataFrame(data['metric_trends'])
print(df)
```

### Trend Prediction

Analyze historical trends to predict future quality:

```bash
# Generate 90-day report
python scripts/monitor_crackerjack_metrics.py --days 90 --format json > long_term.json

# Analyze trends programmatically
python -c "
import json
with open('long_term.json') as f:
    data = json.load(f)
for metric, trend in data['metric_trends'].items():
    if trend['direction'] == 'declining' and trend['strength'] == 'strong':
        print(f'WARNING: {metric} declining - predict future issues if not addressed'
)
"
```

## Contributing

To enhance the monitoring script:

1. Add new metric types to `CrackerjackMetricsMonitor._analyze_metric_trends()`
1. Create custom alert logic in `_generate_quality_alerts()`
1. Add new recommendations in `_generate_recommendations()`
1. Extend output formats in `format_markdown_report()` or `format_json_report()`

## Support

For issues or questions:

- Check existing data: `sqlite3 ~/.claude/data/crackerjack_integration.db "SELECT COUNT(*) FROM crackerjack_results;"`
- Verify database integrity: `sqlite3 ~/.claude/data/crackerjack_integration.db "PRAGMA integrity_check;"`
- Review Session Buddy logs: `~/.claude/logs/`

## Related Documentation

- [Crackerjack Integration](../README.md#crackerjack-integration)
- [MCP Server Configuration](../README.md#mcp-configuration)
- [Session Management](../README.md#session-management-workflow)

## License

Part of Session Buddy - See project LICENSE file.
