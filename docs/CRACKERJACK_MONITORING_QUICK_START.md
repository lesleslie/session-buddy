# Crackerjack Metrics Monitoring - Quick Start Guide

## TL;DR

```bash
# Generate a 30-day quality report
python scripts/monitor_crackerjack_metrics.py

# Generate weekly report
python scripts/monitor_crackerjack_metrics.py --days 7 --output weekly.md

# Get JSON for automation
python scripts/monitor_crackerjack_metrics.py --format json --output metrics.json
```

## What It Does

Analyzes your Crackerjack execution history to provide:
- Quality trend analysis (improving vs declining)
- Automatic alerts for quality degradation
- Command performance metrics
- Project-specific insights
- Actionable recommendations

## Sample Output

```markdown
## Executive Summary

- **Total Executions:** 241
- **Success Rate:** 68.0%
- **Unique Commands:** 12
- **Avg Execution Time:** 10.852s

## Quality Alerts

### 🔴 CRITICAL: build_status

- **Message:** build_status has declined by 100.0% (from 88.65 to 0)
- **Current Value:** 0
- **Previous Value:** 88.65

## Recommendations

1. CRITICAL: Build success rate declining by 100.0% - investigate failing builds
2. High failure rate for 'test' command (32/76 failed) - investigate
3. Performance: 'all' averaging 117.3s - consider optimization
```

## Key Features

### 1. Trend Analysis

Tracks quality metrics over time:
- `build_status` - Build success rate
- `lint_score` - Code quality score
- `security_score` - Security scan results
- `complexity_score` - Code complexity metrics

**Indicators**:
- 📈 Improving (metric getting better)
- 📉 Declining (metric getting worse)
- ➡️ Stable (no significant change)

**Strength**:
- ⚡ Strong (>5% change)
- 🔄 Moderate (1-5% change)
- 📍 Weak (<1% change)

### 2. Alert System

Configurable alerts for quality degradation:

| Severity | Threshold | Action |
|----------|-----------|--------|
| Critical | >20% change | Immediate action |
| Warning | 10-20% change | Investigate soon |
| Info | 5-10% change | Monitor |

**Customize threshold**:
```bash
python scripts/monitor_crackerjack_metrics.py --alert-threshold 15
```

### 3. Command Statistics

Execution patterns per command:
- Total executions
- Success rate
- Average execution time
- Failure count

**Identify issues**:
- High failure rates → test instability
- Long execution times → performance problems

### 4. Performance Metrics

Execution time analysis:
- Average/Min/Max times
- Slowest commands
- Fastest commands

**Optimization targets**:
- Commands averaging >30s need optimization

### 5. Project Insights

Per-project analysis:
- Execution count
- Success rate
- Average time
- Active days

## Common Use Cases

### Weekly Quality Review

```bash
# Generate every Monday
python scripts/monitor_crackerjack_metrics.py --days 7 --output weekly_$(date +%Y%m%d).md
```

### Monthly Executive Summary

```bash
# Comprehensive monthly report
python scripts/monitor_crackerjack_metrics.py --days 30 --output monthly_$(date +%Y%m%d).md
```

### CI/CD Integration

```bash
# Check for quality degradation
python scripts/monitor_crackerjack_metrics.py --days 1 --format json > metrics.json

# Fail build on critical alerts
if jq -e '.quality_alerts[] | select(.severity == "critical")' metrics.json; then
  echo "Quality degradation detected!"
  exit 1
fi
```

### Project-Specific Analysis

```bash
# Analyze specific project
python scripts/monitor_crackerjack_metrics.py \
  --project /path/to/project \
  --days 14 \
  --output project_metrics.md
```

### Cron Job Automation

```bash
# Add to crontab (crontab -e)
0 9 * * 1 cd /Users/les/Projects/session-buddy && python scripts/monitor_crackerjack_metrics.py --days 7 --output ~/weekly_metrics.md
```

## Interpreting Results

### Quality Trends

| Metric | Good Direction | Target | Bad Sign |
|--------|---------------|--------|----------|
| build_status | ↑ Increasing | >95% | Sudden drop |
| lint_score | ↑ Increasing | >90% | Gradual decline |
| security_score | ↑ Increasing | >85% | New vulnerabilities |
| complexity_score | ↓ Decreasing | <20% | Rapid increase |

### Alert Severity

- **🔴 Critical**: Take immediate action (build failing, security issues)
- **🟡 Warning**: Investigate soon (test failures, declining quality)
- **🟢 Info**: Monitor (small changes, trends)

### Common Patterns

**Sudden Quality Drop**:
- Recent commits introduced issues
- Dependency changes broke tests
- Environment problems

**Gradual Decline**:
- Technical debt accumulation
- Insufficient refactoring
- Test coverage gaps

**Consistent Improvement**:
- Good development practices
- Effective code review
- Regular quality investments

## Command Reference

| Option | Description | Default |
|--------|-------------|---------|
| `--days N` | Analyze last N days | 30 |
| `--project PATH` | Filter by project | All projects |
| `--format json` | JSON output instead of Markdown | markdown |
| `--output, -o FILE` | Save to file | stdout |
| `--alert-threshold PCT` | Alert sensitivity (%) | 10.0 |
| `--db-path PATH` | Custom database path | ~/.claude/data/... |
| `--help` | Show help message | - |

## Data Source

**Database**: `~/.claude/data/crackerjack_integration.db`

**Automatically populated** by Session Buddy's Crackerjack integration during normal development.

**Tables analyzed**:
- `crackerjack_results` - Command execution history
- `quality_metrics_history` - Quality metric snapshots
- `test_results` - Individual test results
- `progress_snapshots` - Progress tracking data

## Troubleshooting

### No Data Available

```
Error: Database not found
```

**Solution**: Run some crackerjack commands first:
```bash
python -m crackerjack run --fast
python -m crackerjack run --comp
```

### Empty Report

**Try longer time range**:
```bash
python scripts/monitor_crackerjack_metrics.py --days 90
```

### Too Many Alerts

**Adjust threshold**:
```bash
python scripts/monitor_crackerjack_metrics.py --alert-threshold 20
```

## Best Practices

1. **Run Regularly**: Weekly or monthly reports
2. **Track Trends**: Look at multiple reports, not just one
3. **Act on Alerts**: Critical alerts need immediate attention
4. **Share with Team**: Use in standups or reviews
5. **Adjust Thresholds**: Customize for your project's tolerance

## Integration Examples

### Slack Notification

```bash
# Alert on critical issues
ALERTS=$(python scripts/monitor_crackerjack_metrics.py --days 1 --format json | \
  jq -r '.quality_alerts[] | select(.severity == "critical") | .message')

if [ -n "$ALERTS" ]; then
  curl -X POST $SLACK_WEBHOOK -d "{\"text\": \"🚨 $ALERTS\"}"
fi
```

### Email Report

```bash
# Email weekly report
python scripts/monitor_crackerjack_metrics.py --days 7 --output report.md
mail -s "Weekly Quality Report" team@example.com < report.md
```

### Dashboard Data

```bash
# Export JSON for custom dashboards
python scripts/monitor_crackerjack_metrics.py --days 30 --format json > \
  /path/to/dashboard/data/metrics.json
```

## Next Steps

1. **Generate your first report**: `python scripts/monitor_crackerjack_metrics.py`
2. **Review recommendations**: Check the recommendations section
3. **Set up automation**: Add to cron or CI/CD
4. **Customize thresholds**: Adjust for your project
5. **Track improvements**: Compare reports over time

## Further Reading

- [Full Documentation](CRACKERJACK_METRICS_MONITORING.md)
- [Visualization Guide](CRACKERJACK_DASHBOARD_VISUALIZATION.md)
- [Session Buddy README](../README.md)

## Quick Reference

```bash
# Basic report (30 days)
python scripts/monitor_crackerjack_metrics.py

# Last 7 days
python scripts/monitor_crackerjack_metrics.py --days 7

# Save to file
python scripts/monitor_crackerjack_metrics.py -o report.md

# JSON for automation
python scripts/monitor_crackerjack_metrics.py --format json

# Custom alert threshold (15%)
python scripts/monitor_crackerjack_metrics.py --alert-threshold 15

# Specific project
python scripts/monitor_crackerjack_metrics.py --project /path/to/project
```

---

**Generated by**: Session Buddy Crackerjack Integration
**Data Source**: ~/.claude/data/crackerjack_integration.db
**Analysis**: Historical execution data and quality metrics
