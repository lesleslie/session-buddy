# Analytics Engine Usage Examples

This document provides usage examples for the Phase 4 advanced analytics engine.

## Overview

The analytics engine provides three core capabilities:

1. **Predictive Analytics** - Predict skill success probability
2. **A/B Testing** - Compare skill strategies with statistical analysis
3. **Time-Series Analysis** - Detect trends and anomalies in skill metrics

## Installation

The analytics engine is included with Session-Buddy. New dependencies have been added:

```bash
# Install dependencies (already added to pyproject.toml)
uv pip install scikit-learn scipy
```

## 1. Predictive Analytics

### Basic Usage

```python
from pathlib import Path
from session_buddy.analytics import SkillSuccessPredictor, SessionContext

# Initialize predictor
predictor = SkillSuccessPredictor(Path(".session-buddy/skills.db"))

# Train model on historical data (30-day window)
training_stats = predictor.train_model(days=30)
print(f"Trained on {training_stats['samples_used']} samples")
print(f"Overall success rate: {training_stats['success_rate']:.1%}")

# Create session context
context = SessionContext(
    session_id="session-123",
    session_start_time="2025-02-10T09:00:00",
    skills_used_in_session=["pytest-run", "ruff-check"],
    project_name="my-project"
)

# Predict success probability
probability = predictor.predict_success_probability(
    skill_name="semantic-search",
    user_query="Find similar functions",
    workflow_phase="execution",
    session_context=context
)
print(f"Success probability: {probability:.1%}")

# Get feature explanations
explanations = predictor.get_feature_explanation(
    skill_name="semantic-search",
    user_query="Find similar functions",
    workflow_phase="execution",
    session_context=context
)
for feature, info in explanations.items():
    print(f"{feature}: {info['interpretation']}")
```

### Output Example

```
Trained on 1,234 samples
Overall success rate: 78.5%
Success probability: 82.3%
hour_of_day: Current hour (0-23): 14
day_of_week: Day of week (0=Mon, 6=Sun): 1
invocation_count_24h: Recent invocations (24h): 12
avg_completion_rate_24h: Recent success rate (24h): 85.0%
workflow_phase_encoded: Workflow phase encoding: 1
session_length_minutes: Session length: 45.0 minutes
user_skill_familiarity: Previous successful uses: 3
```

## 2. A/B Testing

### Basic Usage

```python
from pathlib import Path
from session_buddy.analytics import (
    ABTestFramework,
    ABTestConfig,
    TestOutcome
)

# Initialize framework
framework = ABTestFramework(Path(".session-buddy/skills.db"))

# Create test configuration
config = ABTestConfig(
    test_name="semantic_vs_workflow_aware",
    description="Compare semantic search vs workflow-aware search",
    control_strategy="semantic_search",
    treatment_strategy="workflow_aware_search",
    start_date="2025-02-10T00:00:00",
    min_sample_size=100,
    metrics=["completion_rate", "avg_duration_seconds"]
)

# Create test
test_id = framework.create_test(config, assignment_ratio=0.5)
print(f"Created test with ID: {test_id}")

# Assign users to groups
user_id = "user-123"
group = framework.assign_user_to_group(test_id, user_id)
print(f"User assigned to: {group}")

# Record outcomes
framework.record_outcome(test_id, user_id, TestOutcome(
    skill_name="pytest-run",
    completed=True,
    duration_seconds=45.0,
    user_rating=4.5
))

# Analyze results (when you have enough samples)
results = framework.analyze_results(test_id)
print(f"Control completion rate: {results.control_metrics['completion_rate']:.1%}")
print(f"Treatment completion rate: {results.treatment_metrics['completion_rate']:.1%}")
print(f"Statistical significance: p={results.statistical_significance:.4f}")
print(f"Winner: {results.winner}")
print(f"Recommendation: {results.recommendation}")

# Get test status
status = framework.get_test_status(test_id)
print(f"Control samples: {status['control_sample_size']}")
print(f"Treatment samples: {status['treatment_sample_size']}")

# Stop test when done
framework.stop_test(test_id)
```

### Output Example

```
Created test with ID: 1
User assigned to: treatment
Control completion rate: 85.0%
Treatment completion rate: 90.0%
Statistical significance: p=0.0342
Winner: treatment
Recommendation: Ship treatment strategy (p=0.0342). Treatment improves completion rate by 5.0pp.
Control samples: 150
Treatment samples: 150
```

## 3. Time-Series Analysis

### Basic Usage

```python
from pathlib import Path
from session_buddy.analytics import TimeSeriesAnalyzer

# Initialize analyzer
analyzer = TimeSeriesAnalyzer(Path(".session-buddy/skills.db"))

# Get hourly metrics for last 24 hours
hourly = analyzer.aggregate_hourly_metrics(
    skill_name="pytest-run",
    hours=24
)
for h in hourly[-5:]:  # Last 5 hours
    print(f"{h.timestamp}: {h.completion_rate:.1%} ({h.invocation_count} invocations)")

# Detect trends
trend = analyzer.detect_trend(
    skill_name="pytest-run",
    metric="completion_rate",
    window_days=7
)
print(f"\nTrend: {trend.trend}")
print(f"Change: {trend.change_percent:+.1f}%")
print(f"Start: {trend.start_value:.1%} → End: {trend.end_value:.1%}")
print(f"Confidence: p={trend.confidence:.4f}")

# Get trends for all skills
all_trends = analyzer.get_multi_skill_trends(
    metric="completion_rate",
    window_days=7,
    min_invocations=10
)
for skill, trend in all_trends.items():
    print(f"{skill}: {trend.trend} ({trend.change_percent:+.1f}%)")

# Detect anomalies
anomalies = analyzer.get_anomaly_detection(
    skill_name="pytest-run",
    metric="completion_rate",
    window_hours=24,
    z_threshold=2.0
)
for anomaly in anomalies:
    print(f"\nAnomaly detected at {anomaly['timestamp']}")
    print(f"  Value: {anomaly['value']:.1%}")
    print(f"  Z-score: {anomaly['z_score']:.2f}")
    print(f"  Type: {anomaly['deviation_type']}")

# Get plotting data
plot_data = analyzer.get_time_series_plot_data(
    skill_name="pytest-run",
    metric="completion_rate",
    hours=168  # 7 days
)
# Use plot_data['timestamps'] and plot_data['values'] for visualization
```

### Output Example

```
2025-02-10T04:00:00: 85.0% (8 invocations)
2025-02-10T05:00:00: 88.0% (6 invocations)
2025-02-10T06:00:00: 90.0% (10 invocations)
2025-02-10T07:00:00: 87.0% (7 invocations)
2025-02-10T08:00:00: 92.0% (9 invocations)

Trend: improving
Change: +9.3%
Start: 75.0% → End: 82.0%
Confidence: p=0.0023

pytest-run: improving (+9.3%)
ruff-check: stable (+1.2%)
semantic-search: declining (-5.7%)

Anomaly detected at 2025-02-10T02:00:00
  Value: 95.0%
  Z-score: 2.34
  Type: high
```

## Integration with V4 Schema

The analytics engine integrates with the V4 database schema:

- **skill_invocation**: Training data for predictive model
- **skill_time_series**: Hourly aggregated metrics
- **skill_metrics_cache**: Real-time performance metrics
- **ab_test_configs**: A/B test configurations
- **ab_test_assignments**: User group assignments
- **ab_test_outcomes**: Test results and metrics

## Convenience Functions

Each module provides a convenience function for getting instances:

```python
from session_buddy.analytics import (
    get_predictor,
    get_ab_framework,
    get_analyzer
)

# Uses default path: .session-buddy/skills.db
predictor = get_predictor()
framework = get_ab_framework()
analyzer = get_analyzer()
```

## Error Handling

All modules handle missing data gracefully:

```python
# Insufficient training data
try:
    predictor.train_model(days=1)
except ValueError as e:
    print(f"Cannot train: {e}")

# Test not found
try:
    framework.analyze_results(999)
except ValueError as e:
    print(f"Error: {e}")

# Insufficient time-series data
trend = analyzer.detect_trend("unknown-skill", window_days=7)
if trend.trend == "insufficient_data":
    print("Not enough data to detect trend")
```

## Best Practices

### Predictive Analytics

1. **Train regularly**: Retrain model weekly with fresh data
2. **Handle missing features**: Return zeros/defaults for missing data
3. **Feature importance**: Review feature importance to understand drivers

### A/B Testing

1. **Minimum sample size**: Use at least 100 samples per group
2. **Statistical significance**: Use p < 0.05 for decision making
3. **Run duration**: Run tests for at least 7 days to capture weekly patterns
4. **One variable**: Test one change at a time

### Time-Series Analysis

1. **Trend detection**: Use 7-30 day windows for trend analysis
2. **Anomaly threshold**: Use Z-score > 2.0 for anomaly detection
3. **Hourly aggregation**: Use hourly granularity for detailed analysis
4. **Seasonality**: Be aware of daily/weekly patterns

## Files Implemented

- `/Users/les/Projects/session-buddy/session_buddy/analytics/predictive.py` (13KB)
- `/Users/les/Projects/session-buddy/session_buddy/analytics/ab_testing.py` (18KB)
- `/Users/les/Projects/session-buddy/session_buddy/analytics/time_series.py` (14KB)
- `/Users/les/Projects/session-buddy/session_buddy/analytics/__init__.py` (updated)

Total: ~45KB of production-ready analytics code
