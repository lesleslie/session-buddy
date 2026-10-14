# Analytics Engine Implementation Plan

## Overview
Implementation of Phase 4 advanced analytics engine for Session-Buddy skills tracking system.

## Modules to Implement

### 1. `predictive.py` - Skill Success Predictor
**Class**: `SkillSuccessPredictor`

Features:
- Extract 7 features from skill invocation context
- Train RandomForest classifier on historical data
- Predict probability of skill success

Methods:
- `__init__(db_path)` - Initialize predictor
- `extract_features(skill_name, user_query, workflow_phase, session_context)` - Extract 7 features
- `train_model()` - Train on 30-day historical window
- `predict_success_probability(skill_name, user_query, workflow_phase, session_context)` - Return 0-1 probability

Features:
1. hour_of_day (0-23)
2. day_of_week (0-6)
3. invocation_count_24h
4. avg_completion_rate_24h
5. workflow_phase_encoded
6. session_length_minutes
7. user_skill_familiarity

### 2. `ab_testing.py` - A/B Testing Framework
**Classes**: `ABTestConfig`, `ABTestFramework`

Features:
- Create A/B tests with control/treatment strategies
- Assign users to groups via deterministic hashing
- Record outcomes (completion, duration, ratings)
- Analyze results with statistical t-tests

Methods:
- `create_test(config, assignment_ratio)` - Create new test
- `assign_user_to_group(test_id, user_id)` - Assign to control/treatment
- `record_outcome(test_id, user_id, skill_name, outcome)` - Record result
- `analyze_results(test_id)` - Statistical analysis with p-value

### 3. `time_series.py` - Time-Series Analyzer
**Class**: `TimeSeriesAnalyzer`

Features:
- Aggregate metrics by hour for time-series plotting
- Detect trends using linear regression
- Calculate trend slope and change percentage

Methods:
- `__init__(db_path)` - Initialize analyzer
- `aggregate_hourly_metrics(skill_name=None, hours=24)` - Hourly aggregates
- `detect_trend(skill_name, metric='completion_rate', window_days=7)` - Trend detection

## Dependencies to Add
- `scikit-learn>=1.6.0` - RandomForest, StandardScaler
- `scipy>=1.15.0` - Statistical tests (t-test)

## Implementation Steps

1. Update pyproject.toml with new dependencies
2. Create `predictive.py` with SkillSuccessPredictor
3. Create `ab_testing.py` with ABTestConfig and ABTestFramework
4. Create `time_series.py` with TimeSeriesAnalyzer
5. Update `analytics/__init__.py` to export new classes

## File Paths
- `/Users/les/Projects/session-buddy/session_buddy/analytics/predictive.py`
- `/Users/les/Projects/session-buddy/session_buddy/analytics/ab_testing.py`
- `/Users/les/Projects/session-buddy/session_buddy/analytics/time_series.py`

## V4 Schema Integration
- Query `skill_time_series` for historical data
- Query `ab_test_*` tables for A/B testing
- Use `skill_invocation` for training data
- Use `skill_metrics_cache` for real-time metrics
