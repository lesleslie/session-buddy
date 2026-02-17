# Skill Metrics Aggregation - Architecture Reference

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Local Environment                           │
│                                                                      │
│  ┌──────────────────┐      ┌──────────────────┐                    │
│  │  Crackerjack     │      │  Session Buddy   │                    │
│  │  Project         │      │  Project         │                    │
│  │                  │      │                  │                    │
│  │  .session-buddy/ │      │  .session-buddy/ │                    │
│  │  └─ skill_metrics│      │  └─ skill_metrics│                    │
│  │       .json      │      │       .json      │                    │
│  └────────┬─────────┘      └────────┬─────────┘                    │
│           │                         │                               │
│           └────────────┬────────────┘                               │
│                        │                                            │
│                        ▼                                            │
│           ┌─────────────────────────┐                               │
│           │  Mahavishnu Collector   │                               │
│           │  (read-only access)     │                               │
│           └────────────┬────────────┘                               │
│                        │                                            │
│                        ▼                                            │
│           ┌─────────────────────────┐                               │
│           │  ~/.claude/data/        │                               │
│           │  mahavishnu/            │                               │
│           │  └─ skill_metrics.duckdb│                               │
│           └────────────┬────────────┘                               │
│                        │                                            │
│                        ▼                                            │
│           ┌─────────────────────────┐                               │
│           │  Aggregation Engine     │                               │
│           │  - Compute rollups      │                               │
│           │  - Pattern detection    │                               │
│           │  - Effectiveness analysis│                              │
│           └────────────┬────────────┘                               │
│                        │                                            │
│                        ▼                                            │
│           ┌─────────────────────────┐                               │
│           │  MCP Tools              │                               │
│           │  - Top skills           │                               │
│           │  - Effectiveness        │                               │
│           │  - Cross-project comp   │                               │
│           └────────────┬────────────┘                               │
│                        │                                            │
│                        ▼                                            │
│           ┌─────────────────────────┐                               │
│           │  Workflow Orchestrator  │                               │
│           │  - Skill recommendations│                               │
│           │  - Optimization         │                               │
│           └─────────────────────────┘                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

    ❌ NO EXTERNAL CONNECTIONS
    ✅ ALL DATA LOCAL
    ✅ PRIVACY GUARANTEED
```

## Data Flow

### Collection Phase

```
1. User registers projects
   └─> register_project("/path/to/crackerjack", "Crackerjack", "cli")

2. Collector reads project JSON files
   └─> .session-buddy/skill_metrics.json

3. Records inserted into DuckDB
   └─> skill_usage table (raw data)
```

### Aggregation Phase

```
4. User triggers aggregation
   └─> compute_aggregates(time_window="monthly")

5. Aggregator computes rollups
   └─> skill_aggregates table (pre-computed)

6. Queries answered from aggregates
   └─> get_top_skills() (fast OLAP queries)
```

### Analysis Phase

```
7. User requests analysis
   └─> analyze_skill_effectiveness("code-review")

8. Aggregator generates insights
   └─> Success rate, follow-up rate, recommendations

9. Workflow orchestrator uses insights
   └─> Optimize skill selection, recommend improvements
```

## Schema Relationships

```
projects (registry)
    ├── project_id (PK)
    ├── project_path (unique)
    ├── project_name
    └── is_active
        │
        │ 1:N
        ▼
skill_usage (raw records)
    ├── id (PK)
    ├── project_id (FK)
    ├── skill_name
    ├── invoked_at
    ├── success
    └── duration_ms
        │
        │ Aggregated via
        ▼
skill_aggregates (computed)
    ├── skill_name
    ├── project_id (FK, nullable for cross-project)
    ├── time_window
    ├── total_invocations
    └── avg_duration_ms

workflow_executions (telemetry)
    ├── workflow_id (PK)
    ├── project_id (FK)
    ├── workflow_name
    ├── skills_used (JSON)
    └── status
```

## Key Design Patterns

### 1. Collector Pattern

**Responsibility:** Read project metrics, insert into database

```python
class SkillMetricsCollector:
    def collect_from_project(self, project_path: Path) -> dict
    def register_project(self, ...) -> str
```

**Characteristics:**
- Read-only access to project files
- Idempotent (safe to re-run)
- No modification of source data

### 2. Aggregator Pattern

**Responsibility:** Compute cross-project statistics

```python
class SkillMetricsAggregator:
    def compute_aggregates(self, ...) -> int
    def get_top_skills(self, ...) -> list[dict]
    def get_skill_effectiveness(self, ...) -> dict
```

**Characteristics:**
- Pre-computed aggregates for performance
- Multiple time windows (daily/weekly/monthly/all)
- Support for both project-specific and cross-project queries

### 3. Repository Pattern

**Responsibility:** Database abstraction

```python
def init_skill_metrics_db() -> duckdb.DuckDBPyConnection
```

**Characteristics:**
- Centralized schema definition
- Connection management
- Index creation for query performance

## Performance Considerations

### Query Optimization

1. **Indexes on frequently queried columns**
   ```sql
   CREATE INDEX idx_skill_usage_project_time ON skill_usage(project_id, invoked_at);
   CREATE INDEX idx_skill_usage_skill_time ON skill_usage(skill_name, invoked_at);
   ```

2. **Pre-computed aggregates**
   - Avoid repeated full-table scans
   - Fast OLAP queries on aggregated data
   - Refreshed on-demand or scheduled

3. **Time-based partitioning** (future enhancement)
   ```sql
   -- Partition by month for faster time-range queries
   CREATE TABLE skill_usage_2025_02 PARTITION OF skill_usage
   FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
   ```

### Scalability Targets

- **Small:** 10 projects, 1000 records per project → <1s queries
- **Medium:** 50 projects, 10000 records per project → <5s queries
- **Large:** 100+ projects, 100000 records per project → <10s queries

DuckDB's columnar storage makes these targets achievable.

## Privacy & Security Model

### Data Classification

```
┌─────────────────────────────────────────────────────────┐
│ PUBLIC (Safe to Share)                                  │
│ - Skill names (e.g., "code-review")                     │
│ - Aggregate statistics (counts, averages)               │
│ - Effectiveness insights                                │
├─────────────────────────────────────────────────────────┤
│ SENSITIVE (Local Only)                                  │
│ - Project paths (or hashed IDs)                         │
│ - Session IDs                                           │
│ - Timestamps (can reveal work patterns)                 │
├─────────────────────────────────────────────────────────┤
│ PRIVATE (Never Shared)                                  │
│ - File contents, code snippets                          │
│ - User prompts/responses                                │
│ - PII (none present in metrics)                         │
└─────────────────────────────────────────────────────────┘
```

### Access Control

```python
# Projects must be explicitly registered
@register_project(project_path="/path", project_name="My Project")

# User can unregister anytime
@unregister_project(project_path="/path")

# Aggregation respects is_active flag
SELECT * FROM projects WHERE is_active = TRUE
```

### Data Retention

```python
# Future enhancement: Automatic cleanup
def cleanup_old_records(retention_days: int = 90):
    """Remove records older than retention period."""
    # Implementation
    pass
```

## Integration with Existing Systems

### Crackerjack Integration

**Current State:** Crackerjack writes `.session-buddy/skill_metrics.json`

**Mahavishnu Enhancement:** Read and aggregate across projects

**No changes required to Crackerjack** - Mahavishnu is read-only consumer.

### Session Buddy Integration

**Current State:** Session Buddy manages session lifecycle and reflections

**Mahavishnu Enhancement:** Add skill metrics to session insights

**Synergy Opportunities:**

1. **Session Start:** Show top skills for project
2. **Checkpoint:** Recommend skill improvements
3. **Session End:** Capture skill usage patterns

### Workflow Orchestration Integration

**Current State:** Mahavishnu orchestrates multi-agent workflows

**Mahavishnu Enhancement:** Use skill metrics to optimize workflows

**Example Optimization:**

```python
# Before: Fixed skill sequence
workflow = ["analyze", "design", "implement", "test"]

# After: Data-driven optimization
if skill_effectiveness("code-review")['success_rate'] > 0.9:
    workflow = ["analyze", "design", "code-review", "implement", "test"]
else:
    workflow = ["analyze", "design", "implement", "test"]  # Skip ineffective review
```

## Testing Strategy

### Unit Tests

```python
def test_project_registration():
    # Test project registration
    pass

def test_metrics_collection():
    # Test collection from JSON file
    pass

def test_aggregation_computation():
    # Test aggregate computation
    pass
```

### Integration Tests

```python
def test_full_workflow():
    # Register → Collect → Aggregate → Analyze
    pass

def test_cross_project_analysis():
    # Multiple projects → cross-project aggregates
    pass
```

### Performance Tests

```python
def test_aggregation_performance():
    # Large dataset → ensure <10s queries
    pass

def test_concurrent_collection():
    # Multiple projects collected in parallel
    pass
```

## Monitoring & Observability

### Metrics to Track

1. **Collection Metrics**
   - Records collected per project
   - Collection duration
   - Error rates

2. **Aggregation Metrics**
   - Aggregation computation time
   - Number of aggregates computed
   - Query response times

3. **Usage Metrics**
   - Most requested skills
   - Most effective skills
   - Skills needing improvement

### Health Checks

```python
@mcp.tool()
def health_check() -> str:
    """Check skill metrics system health."""
    # Database connectivity
    # Recent collection activity
    # Aggregate freshness
    pass
```

## Future Enhancements

### Phase 4: Advanced Analytics

1. **Skill Relationship Graph**
   - Which skills are commonly used together?
   - Optimal skill sequences
   - Skill dependencies

2. **Predictive Recommendations**
   - "You usually use skill X after Y"
   - "Projects like yours benefit from skill Z"
   - Workflow optimization suggestions

3. **Trend Analysis**
   - Skill usage over time
   - Seasonal patterns
   - Adoption rates for new skills

### Phase 5: Team Collaboration (Optional)

1. **Shared Skill Catalogs**
   - Team-wide skill best practices
   - Consensus on effective prompts
   - Skill versioning and evolution

2. **Collaborative Filtering**
   - "Teams using X also use Y"
   - Cross-team skill sharing
   - Privacy-preserving aggregation

3. **Quality Metrics**
   - Skill refinement tracking
   - A/B testing for skill variations
   - Effectiveness benchmarking

## Conclusion

This architecture provides:

✅ **Privacy-first**: All data local, no external transmission
✅ **Performance**: Fast queries via pre-computed aggregates
✅ **Scalability**: Handles 100+ projects with 100K+ records
✅ **Flexibility**: Project-specific and cross-project views
✅ **Extensibility**: Clear patterns for future enhancements

The design maintains project autonomy while enabling powerful cross-project insights for workflow optimization.
