# Phase 4 V4 Schema Migration Summary

## Overview

This document summarizes the V4 schema extensions for Session-Buddy Phase 4, which adds enterprise-grade analytics, real-time monitoring, cross-session learning, and multi-modal skill support.

**Migration Files:**
- `V4__phase4_extensions__up.sql` - Apply V4 changes
- `V4__phase4_extensions__down.sql` - Rollback to V3

## Schema Extensions

### 1. Real-Time Monitoring

#### `skill_metrics_cache`
Real-time cache for dashboard metrics, updated via triggers.

```sql
CREATE TABLE skill_metrics_cache (
    skill_name TEXT PRIMARY KEY,
    last_invocation_at TEXT NOT NULL,
    invocation_count_1h INTEGER DEFAULT 0,
    invocation_count_24h INTEGER DEFAULT 0,
    avg_completion_rate_24h REAL,
    is_anomalous BOOLEAN DEFAULT 0,
    anomaly_score REAL,
    updated_at TEXT NOT NULL
);
```

**Use Cases:**
- Live dashboards showing top skills
- Real-time performance monitoring
- Anomaly detection alerts

**View:** `v_realtime_skill_dashboard` - Pre-joined dashboard view

#### `skill_time_series`
Hourly time-series data for trend analysis.

```sql
CREATE TABLE skill_time_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,  -- ISO format, hourly
    invocation_count INTEGER DEFAULT 0,
    completion_rate REAL,
    avg_duration_seconds REAL,
    unique_sessions INTEGER DEFAULT 0
);
```

**Use Cases:**
- Time-series plotting (Grafana, Prometheus)
- Trend detection (improving/declining)
- Seasonality analysis

**View:** `v_skill_effectiveness_trend` - 7-day trend with slope

#### `skill_anomalies`
Anomaly detection results (performance drops/spikes).

```sql
CREATE TABLE skill_anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,  -- 'drop', 'spike', 'pattern_shift'
    baseline_value REAL,
    observed_value REAL,
    deviation_score REAL,
    resolved_at TEXT
);
```

**Detection Method:**
- Z-score threshold (default: 2.0 = 2 standard deviations)
- Compares current performance vs 7-day baseline

### 2. Cross-Session Learning

#### `skill_community_baselines`
Aggregated metrics across all users.

```sql
CREATE TABLE skill_community_baselines (
    skill_name TEXT PRIMARY KEY,
    total_users INTEGER DEFAULT 0,
    total_invocations INTEGER DEFAULT 0,
    global_completion_rate REAL,
    global_avg_duration_seconds REAL,
    most_common_workflow_phase TEXT,
    effectiveness_percentile REAL,  -- 0-100
    last_updated TEXT NOT NULL
);
```

**Use Cases:**
- Compare user performance vs community
- Identify above/below-average skills
- Calculate effectiveness percentiles

**View:** `v_community_baseline_comparison` - User vs baseline deltas

#### `skill_user_interactions`
Collaborative filtering matrix (user-skill interactions).

```sql
CREATE TABLE skill_user_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,  -- Anonymous identifier
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invoked_at TEXT NOT NULL,
    completed BOOLEAN NOT NULL,
    rating REAL,  -- Optional 1-5 feedback
    alternatives_considered TEXT  -- JSON array
);
```

**Use Cases:**
- Find similar users (Jaccard similarity)
- Collaborative filtering recommendations
- User-specific skill effectiveness

**Algorithm:**
```python
# Jaccard similarity for user similarity
similarity = |user_skills ∩ other_skills| / |user_skills ∪ other_skills|

# Recommendation score
score = similarity × skill_completion_rate
```

#### `skill_clusters` & `skill_cluster_membership`
Skill clustering for recommendations.

```sql
CREATE TABLE skill_clusters (
    cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_name TEXT NOT NULL,
    description TEXT,
    centroid_embedding BLOB,  -- Packed 384-dim
    created_at TEXT NOT NULL
);

CREATE TABLE skill_cluster_membership (
    skill_name TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    membership_score REAL,  -- 0-1
    PRIMARY KEY (skill_name, cluster_id)
);
```

**Use Cases:**
- Cluster-based recommendations
- Discover related skills
- Visualize skill landscape

### 3. A/B Testing Framework

#### `ab_test_configs`
A/B test configurations.

```sql
CREATE TABLE ab_test_configs (
    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_name TEXT NOT NULL UNIQUE,
    description TEXT,
    control_strategy TEXT NOT NULL,
    treatment_strategy TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    min_sample_size INTEGER DEFAULT 100,
    metrics TEXT,  -- JSON array
    assignment_ratio REAL DEFAULT 0.5,
    status TEXT DEFAULT 'running'
);
```

#### `ab_test_assignments`
User-to-group assignments.

```sql
CREATE TABLE ab_test_assignments (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    group_name TEXT NOT NULL,  -- 'control' or 'treatment'
    assigned_at TEXT NOT NULL,
    UNIQUE(test_id, user_id)
);
```

**Assignment Method:** Deterministic hashing
```python
hash_value = md5(f"{user_id}:{test_id}")
group = "control" if hash_value % 100 < 50 else "treatment"
```

#### `ab_test_outcomes`
Test outcomes per user.

```sql
CREATE TABLE ab_test_outcomes (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    completed BOOLEAN NOT NULL,
    duration_seconds REAL,
    user_rating REAL,
    recorded_at TEXT NOT NULL
);
```

**Analysis:** Statistical t-test for significance
```python
t_stat, p_value = stats.ttest_ind(control_outcomes, treatment_outcomes)
if p_value < 0.05:
    winner = "treatment" if treatment_rate > control_rate else "control"
```

**View:** `v_ab_test_summary` - Pre-computed test statistics

### 4. Multi-Modal Skills

#### `skill_categories`
Skill taxonomy hierarchy.

```sql
CREATE TABLE skill_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE,
    parent_category_id INTEGER,
    description TEXT,
    domain TEXT,  -- 'code', 'documentation', 'testing', 'deployment'
    created_at TEXT NOT NULL
);
```

**Predefined Categories:**
- **Code Quality:** ruff-check, mypy, pylint
- **Testing:** pytest-run, coverage-report, hypothesis-test
- **Documentation:** sphinx-build, docstring-check, api-docs
- **Deployment:** docker-build, k8s-deploy, terraform-apply

#### `skill_category_mapping`
Skill-to-category assignments.

```sql
CREATE TABLE skill_category_mapping (
    skill_name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    confidence_score REAL,  -- 0-1
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (skill_name, category_id)
);
```

#### `skill_dependencies`
Co-occurrence patterns (which skills used together).

```sql
CREATE TABLE skill_dependencies (
    skill_a TEXT NOT NULL,
    skill_b TEXT NOT NULL,
    co_occurrence_count INTEGER DEFAULT 1,
    lift_score REAL,  -- >1 means used together more than expected
    last_updated TEXT NOT NULL,
    PRIMARY KEY (skill_a, skill_b)
);
```

**Lift Score Calculation:**
```
lift(A,B) = P(A and B) / (P(A) × P(B))
- lift > 1.0: Positive association (used together)
- lift = 1.0: Independent
- lift < 1.0: Negative association (rarely used together)
```

**View:** `v_skill_dependency_network` - Pre-interpreted relationships

#### `skill_modalities`
Multi-modal skill types.

```sql
CREATE TABLE skill_modalities (
    skill_name TEXT PRIMARY KEY,
    modality_type TEXT NOT NULL,
    input_format TEXT,
    output_format TEXT,
    requires_human_review BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL
);
```

**Modality Types:**
- `code` - Code analysis/generation
- `documentation` - Doc generation/checking
- `testing` - Test execution/coverage
- `deployment` - Build/deploy operations

**View:** `v_multimodal_skill_catalog` - Browse by modality/domain

## Triggers

### `trg_metrics_cache_after_insert`
Automatically updates `skill_metrics_cache` on new invocations.

```sql
CREATE TRIGGER trg_metrics_cache_after_insert
    AFTER INSERT ON skill_invocation
BEGIN
    INSERT INTO skill_metrics_cache (...)
    VALUES (...)
    ON CONFLICT(skill_name) DO UPDATE SET
        invocation_count_1h = invocation_count_1h + 1,
        invocation_count_24h = invocation_count_24h + 1,
        ...;
END;
```

**Impact:** Real-time metrics available without scheduled tasks

## Views Summary

| View | Purpose | Key Fields |
|------|---------|------------|
| `v_realtime_skill_dashboard` | Live metrics | invocation_count_1h/24h, completion_rate |
| `v_skill_effectiveness_trend` | 7-day trends | avg_completion_rate_7d, trend_slope |
| `v_community_baseline_comparison` | User vs global | user_completion_rate, delta_from_baseline |
| `v_skill_dependency_network` | Skill relationships | co_occurrence_count, lift_score, relationship_type |
| `v_ab_test_summary` | A/B test stats | control/treatment_completion_rate |
| `v_multimodal_skill_catalog` | Browse skills | modality_type, domain, completion_rate |

## Migration Steps

### 1. Backup Database
```bash
cp skills.db skills.db.v3.backup
```

### 2. Apply Migration
```python
from session_buddy.storage.migrations.base import MigrationManager

manager = MigrationManager(db_path="skills.db")
manager.migrate()  # Applies V4
```

### 3. Verify
```sql
-- Check V4 tables exist
SELECT name FROM sqlite_master
WHERE type='table'
AND name IN (
    'skill_metrics_cache',
    'skill_time_series',
    'skill_anomalies',
    'skill_community_baselines',
    'skill_user_interactions',
    'ab_test_configs',
    'skill_categories',
    'skill_dependencies'
);

-- Check V4 views exist
SELECT name FROM sqlite_master
WHERE type='view'
AND name LIKE 'v_%';
```

### 4. Backfill Data (Optional)
```python
# Populate time-series from historical data
# Calculate skill_dependencies from past invocations
# Initialize skill_community_baselines
```

### 5. Rollback (If Needed)
```python
manager.rollback()  # Applies V4__down.sql
```

## Query Examples

### Real-Time Monitoring
```sql
-- Top 10 most active skills (last 24h)
SELECT * FROM v_realtime_skill_dashboard
ORDER BY invocation_count_24h DESC
LIMIT 10;

-- Find anomalies
SELECT * FROM skill_anomalies
WHERE resolved_at IS NULL
ORDER BY detected_at DESC;
```

### Cross-Session Learning
```sql
-- User's performance vs community baseline
SELECT * FROM v_community_baseline_comparison
WHERE skill_name = 'pytest-run';

-- Similar users (collaborative filtering)
WITH user_skills AS (
    SELECT DISTINCT skill_name
    FROM skill_user_interactions
    WHERE user_id = 'user123' AND completed = 1
)
SELECT other_user_id, COUNT(*) as common_skills
FROM skill_user_interactions
WHERE skill_name IN (SELECT skill_name FROM user_skills)
  AND user_id != 'user123'
GROUP BY other_user_id
HAVING common_skills >= 3
ORDER BY common_skills DESC;
```

### A/B Testing
```sql
-- Create test
INSERT INTO ab_test_configs (
    test_name, control_strategy, treatment_strategy,
    start_date, metrics
) VALUES (
    'semantic_vs_workflow_aware',
    'semantic_search',
    'workflow_aware_search',
    datetime('now'),
    '["completion_rate", "user_satisfaction"]'
);

-- Analyze results
SELECT * FROM v_ab_test_summary
WHERE test_id = 1;
```

### Multi-Modal Skills
```sql
-- Browse testing skills
SELECT * FROM v_multimodal_skill_catalog
WHERE domain = 'testing'
ORDER BY completion_rate DESC;

-- Find related skills
SELECT * FROM v_skill_dependency_network
WHERE skill_a = 'pytest-run' AND lift_score > 1.5;
```

## Performance Considerations

### Indexes
All V4 tables include appropriate indexes:
- Time-series: `(skill_name, timestamp DESC)`
- Anomalies: `(detected_at DESC)`, `(skill_name, detected_at DESC)`
- User interactions: `(user_id, invoked_at DESC)`, `(skill_name, completed)`
- A/B tests: `(test_id, user_id)`, `(test_id, group_name)`
- Dependencies: `(skill_a)`, `(lift_score DESC)`

### Triggers
- Real-time cache updated automatically on INSERT
- No scheduled tasks needed for basic metrics
- Time-series backfill requires scheduled job

### Scalability
- **Real-time:** O(1) cache lookup via indexes
- **Time-series:** O(log n) via (skill_name, timestamp) index
- **Collaborative filtering:** O(n²) user-user comparisons (consider approximate nearest neighbors for scale)
- **A/B testing:** O(1) assignment via deterministic hash

## Dependencies

### Phase 4 Features Depend On:
- ✅ V1 schema (invocations, metrics, sessions)
- ✅ V2 schema (semantic search embeddings)
- ✅ V3 schema (workflow_phase, workflow_step_id)

### No Breaking Changes
- V4 is purely additive
- All V3 features remain functional
- Rollback path available via V4__down.sql

## Next Steps

After V4 migration:
1. Implement real-time monitoring (WebSocket server, Prometheus exporter)
2. Build collaborative filtering engine
3. Create predictive models (skill success prediction)
4. Implement A/B testing framework
5. Build skill taxonomy categorization
6. Create integration layer (Crackerjack, IDE, CI/CD)
7. Write comprehensive tests
8. Update documentation

## Success Criteria

V4 migration complete when:
- ✅ All V4 tables created successfully
- ✅ All V4 views created successfully
- ✅ Triggers firing correctly
- ✅ Indexes created for performance
- ✅ No V3 functionality broken
- ✅ Rollback tested and working
- ✅ Migration recorded in `skill_migrations` table

---

**Migration Status:** ✅ COMPLETE
**Schema Version:** V4
**Date:** 2026-02-10
**Author:** Session-Buddy Phase 4 Implementation
