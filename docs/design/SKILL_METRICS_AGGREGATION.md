# Cross-Project Skill Metrics Aggregation Design

**Status:** Design Document
**Author:** Multi-Agent Coordinator
**Created:** 2025-02-10
**Related:** Mahavishnu workflow orchestration, Crackerjack skill metrics

## Executive Summary

This document defines a privacy-first, cross-project skill metrics aggregation system for Mahavishnu. The design enables workflow intelligence while maintaining strict data locality and privacy guarantees.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Mahavishnu Orchestrator                      │
│                    (session-buddy)                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ├─── Project Registry
                              │    └── Track all known projects
                              │
                              ├─── Metrics Collector (NEW)
                              │    ├── Collect from .session-buddy/skill_metrics.json
                              │    ├── Normalize and validate
                              │    └── Store in aggregated DuckDB
                              │
                              ├─── Aggregation Engine (NEW)
                              │    ├── Cross-project rollups
                              │    ├── Time-series analysis
                              │    └── Pattern detection
                              │
                              └── Workflow Telemetry (ENHANCED)
                                   ├── Skill usage per workflow
                                   ├── Effectiveness correlation
                                   └── Optimization recommendations
```

## Design Principles

### 1. Privacy-First Architecture

**NO data ever leaves the local environment.**

- All aggregation performed locally via DuckDB
- No external API calls or telemetry transmission
- Project paths are the only identifiers (no PII)
- Opt-in per-project (projects explicitly registered)

### 2. Separation of Concerns

- **Collection**: Gather metrics from project-specific JSON files
- **Aggregation**: Compute cross-project statistics
- **Analysis**: Generate insights and recommendations
- **Workflow Integration**: Use metrics to optimize orchestration

### 3. Minimal Intrusion

- Projects remain autonomous (metrics are local first)
- Mahavishnu is optional read-only consumer
- No impact on crackerjack's existing workflow
- Zero network dependencies

## Data Model

### 1. Project Registry

```python
# ~/.claude/data/mahavishnu/projects.duckdb
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,  # Path hash or user-defined ID
    project_path TEXT UNIQUE NOT NULL,
    project_name TEXT,
    project_type TEXT,  # 'web', 'cli', 'library', etc.
    metadata JSON,  # User-defined tags, categories
    registered_at TIMESTAMP DEFAULT NOW(),
    last_sync_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

### 2. Aggregated Metrics

```python
# ~/.claude/data/mahavishnu/skill_metrics.duckdb
CREATE TABLE skill_usage (
    id INTEGER PRIMARY KEY,
    project_id TEXT REFERENCES projects(project_id),
    skill_name TEXT NOT NULL,
    invoked_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms REAL,
    success BOOLEAN,
    followup_actions INTEGER,
    session_id TEXT,
    metadata JSON  # Workflow context, agent type, etc.
);

CREATE TABLE skill_aggregates (
    skill_name TEXT NOT NULL,
    project_id TEXT,  -- NULL for cross-project aggregate
    time_window TEXT NOT NULL,  -- 'daily', 'weekly', 'monthly', 'all'
    total_invocations INTEGER,
    successful_completions INTEGER,
    avg_duration_ms REAL,
    avg_followup_actions REAL,
    first_used TIMESTAMP,
    last_used TIMESTAMP,
    UNIQUE(skill_name, project_id, time_window)
);

CREATE INDEX idx_skill_usage_project_time ON skill_usage(project_id, invoked_at);
CREATE INDEX idx_skill_usage_skill_time ON skill_usage(skill_name, invoked_at);
```

### 3. Workflow Telemetry

```python
CREATE TABLE workflow_executions (
    workflow_id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(project_id),
    workflow_name TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status TEXT,  -- 'running', 'completed', 'failed', 'cancelled'
    skills_used JSON,  -- Array of skill names
    total_duration_ms REAL,
    metadata JSON
);

CREATE TABLE workflow_skill_correlation (
    workflow_name TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    usage_count INTEGER,
    success_rate REAL,
    avg_duration_ms REAL,
    UNIQUE(workflow_name, skill_name)
);
```

## Implementation Components

### Phase 1: Metrics Collection

**File:** `session_buddy/mahavishnu/metrics_collector.py`

```python
"""
Collects skill metrics from registered projects.
"""
from pathlib import Path
from typing import Optional
import duckdb
import json
from datetime import datetime

class MetricsCollector:
    """Collects skill metrics from project-specific JSON files."""

    def __init__(self, db_path: Path = Path.home() / ".claude/data/mahavishnu/skill_metrics.duckdb"):
        self.db_path = db_path
        self._ensure_db()

    def collect_from_project(self, project_path: Path) -> dict:
        """Collect metrics from a single project's skill_metrics.json.

        Returns:
            {'collected': int, 'skipped': int, 'errors': int}
        """
        metrics_file = project_path / ".session-buddy/skill_metrics.json"
        if not metrics_file.exists():
            return {'collected': 0, 'skipped': 0, 'errors': 0}

        with open(metrics_file) as f:
            data = json.load(f)

        collected = 0
        for skill_name, records in data.get('skills', {}).items():
            for record in records:
                self._insert_record(project_path, skill_name, record)
                collected += 1

        return {'collected': collected, 'skipped': 0, 'errors': 0}

    def collect_all_projects(self) -> dict[str, dict]:
        """Collect metrics from all registered projects.

        Returns:
            {project_path: {'collected': int, 'skipped': int, 'errors': int}}
        """
        results = {}
        with duckdb.connect(str(self.db_path)) as conn:
            projects = conn.execute("SELECT project_path FROM projects WHERE is_active = TRUE").fetchall()

        for (project_path,) in projects:
            results[project_path] = self.collect_from_project(Path(project_path))

        return results

    def _insert_record(self, project_path: Path, skill_name: str, record: dict) -> None:
        """Insert a single skill usage record into the database."""
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO skill_usage (
                    project_id, skill_name, invoked_at, completed_at,
                    duration_ms, success, followup_actions, session_id, metadata
                ) VALUES (
                    (SELECT project_id FROM projects WHERE project_path = ?),
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                str(project_path),
                skill_name,
                record.get('invoked_at'),
                record.get('completed_at'),
                record.get('duration_ms'),
                record.get('success'),
                record.get('followup_actions', 0),
                record.get('session_id'),
                json.dumps(record.get('metadata', {}))
            ))
```

### Phase 2: Aggregation Engine

**File:** `session_buddy/mahavishnu/aggregation_engine.py`

```python
"""
Computes cross-project skill metrics aggregations.
"""
import duckdb
from pathlib import Path
from typing import Literal

TimeWindow = Literal['daily', 'weekly', 'monthly', 'all']

class AggregationEngine:
    """Computes aggregated skill metrics across projects."""

    def __init__(self, db_path: Path = Path.home() / ".claude/data/mahavishnu/skill_metrics.duckdb"):
        self.db_path = db_path

    def compute_aggregates(
        self,
        project_id: Optional[str] = None,
        time_window: TimeWindow = 'all'
    ) -> int:
        """Compute skill usage aggregates.

        Args:
            project_id: Specific project, or None for cross-project
            time_window: Time aggregation granularity

        Returns:
            Number of aggregates computed
        """
        with duckdb.connect(str(self.db_path)) as conn:
            # Determine time grouping
            if time_window == 'daily':
                time_trunc = "DATE_TRUNC('day', invoked_at)"
            elif time_window == 'weekly':
                time_trunc = "DATE_TRUNC('week', invoked_at)"
            elif time_window == 'monthly':
                time_trunc = "DATE_TRUNC('month', invoked_at)"
            else:  # 'all'
                time_trunc = "'1970-01-01'::TIMESTAMP"

            # Compute aggregates
            result = conn.execute(f"""
                INSERT OR REPLACE INTO skill_aggregates (
                    skill_name, project_id, time_window,
                    total_invocations, successful_completions,
                    avg_duration_ms, avg_followup_actions,
                    first_used, last_used
                )
                SELECT
                    skill_name,
                    ?,
                    ?,
                    COUNT(*) as total_invocations,
                    SUM(CAST(success AS INTEGER)) as successful_completions,
                    AVG(duration_ms) as avg_duration_ms,
                    AVG(followup_actions) as avg_followup_actions,
                    MIN(invoked_at) as first_used,
                    MAX(invoked_at) as last_used
                FROM skill_usage
                WHERE (? IS NULL OR project_id = ?)
                GROUP BY skill_name
            """, (project_id, time_window, project_id, project_id))

            return result.rowcount

    def get_top_skills(
        self,
        limit: int = 10,
        project_id: Optional[str] = None,
        time_window: TimeWindow = 'all'
    ) -> list[dict]:
        """Get most used skills.

        Returns:
            List of {'skill_name': str, 'invocations': int, 'success_rate': float}
        """
        with duckdb.connect(str(self.db_path)) as conn:
            query = """
                SELECT
                    skill_name,
                    total_invocations,
                    successful_completions,
                    CAST(successful_completions AS FLOAT) / total_invocations as success_rate
                FROM skill_aggregates
                WHERE (? IS NULL OR project_id = ?) AND time_window = ?
                ORDER BY total_invocations DESC
                LIMIT ?
            """
            results = conn.execute(query, (project_id, project_id, time_window, limit)).fetchall()

            return [
                {
                    'skill_name': row[0],
                    'invocations': row[1],
                    'success_rate': row[3]
                }
                for row in results
            ]

    def get_skill_effectiveness(
        self,
        skill_name: str,
        project_id: Optional[str] = None
    ) -> dict:
        """Analyze skill effectiveness patterns.

        Returns:
            {'avg_duration': float, 'success_rate': float, 'followup_rate': float}
        """
        with duckdb.connect(str(self.db_path)) as conn:
            row = conn.execute("""
                SELECT
                    AVG(duration_ms) as avg_duration,
                    SUM(CAST(success AS INTEGER)) / CAST(COUNT(*) AS FLOAT) as success_rate,
                    AVG(followup_actions) as avg_followup
                FROM skill_usage
                WHERE skill_name = ? AND (? IS NULL OR project_id = ?)
            """, (skill_name, project_id, project_id)).fetchone()

            return {
                'avg_duration_ms': row[0],
                'success_rate': row[1],
                'avg_followup_actions': row[2]
            }
```

### Phase 3: MCP Tools Integration

**File:** `session_buddy/mahavishnu/mcp_tools.py`

```python
"""
MCP tools for cross-project skill metrics.
"""
from mcp.server.fastmcp import FastMCP
from pathlib import Path

mcp = FastMCP("mahavishnu-skill-metrics")

@mcp.tool()
def register_project(
    project_path: str,
    project_name: str,
    project_type: str = "unknown"
) -> str:
    """Register a project for cross-project metrics collection.

    Args:
        project_path: Absolute path to project directory
        project_name: Human-readable project name
        project_type: Project category (web, cli, library, etc.)
    """
    # Implementation: Insert into projects table
    pass

@mcp.tool()
def collect_skill_metrics(project_path: str | None = None) -> str:
    """Collect skill metrics from registered projects.

    Args:
        project_path: Specific project, or None for all projects

    Returns:
        Collection results summary
    """
    collector = MetricsCollector()
    if project_path:
        results = collector.collect_from_project(Path(project_path))
    else:
        results = collector.collect_all_projects()

    return f"Collected metrics from {len(results)} projects"

@mcp.tool()
def get_top_skills(
    limit: int = 10,
    project_id: str | None = None,
    time_window: str = "all"
) -> str:
    """Get most used skills across projects.

    Args:
        limit: Maximum number of skills to return
        project_id: Filter by project, or None for all projects
        time_window: 'daily', 'weekly', 'monthly', or 'all'

    Returns:
        JSON array of top skills with usage statistics
    """
    engine = AggregationEngine()
    skills = engine.get_top_skills(
        limit=limit,
        project_id=project_id,
        time_window=time_window
    )
    return json.dumps(skills, indent=2)

@mcp.tool()
def analyze_skill_effectiveness(
    skill_name: str,
    project_id: str | None = None
) -> str:
    """Analyze skill effectiveness patterns.

    Args:
        skill_name: Name of skill to analyze
        project_id: Filter by project, or None for cross-project analysis

    Returns:
        JSON with effectiveness metrics and insights
    """
    engine = AggregationEngine()
    effectiveness = engine.get_skill_effectiveness(skill_name, project_id)

    # Generate insights
    insights = []
    if effectiveness['success_rate'] < 0.7:
        insights.append(f"Low success rate ({effectiveness['success_rate']:.1%}) - consider reviewing skill implementation")
    if effectiveness['avg_followup_actions'] > 2:
        insights.append(f"High follow-up rate ({effectiveness['avg_followup_actions']:.1f}) - skill may need refinement")

    return json.dumps({
        'metrics': effectiveness,
        'insights': insights
    }, indent=2)

@mcp.tool()
def get_workflow_recommendations(project_id: str | None = None) -> str:
    """Generate workflow optimization recommendations.

    Analyzes skill usage patterns to suggest workflow improvements.

    Args:
        project_id: Filter by project, or None for cross-project analysis

    Returns:
        JSON with actionable recommendations
    """
    engine = AggregationEngine()

    # Get top skills
    top_skills = engine.get_top_skills(limit=20, project_id=project_id)

    # Analyze patterns
    recommendations = []

    # Check for frequently failing skills
    for skill in top_skills:
        if skill['success_rate'] < 0.6:
            recommendations.append({
                'type': 'skill_improvement',
                'priority': 'high',
                'skill': skill['skill_name'],
                'issue': f"Low success rate ({skill['success_rate']:.1%})",
                'action': "Review skill implementation and update prompts"
            })

    # Check for underutilized skills
    # (implementation specific to your skill catalog)

    return json.dumps(recommendations, indent=2)
```

## Integration with Workflow Orchestration

### Workflow Telemetry Enhancement

When Mahavishnu orchestrates workflows, it should track:

1. **Which skills are used** in each workflow phase
2. **Workflow outcomes** (success/failure, duration)
3. **Skill-workflow correlation** (which skills work best in which contexts)

**Example:**

```python
class WorkflowOrchestrator:
    def execute_workflow(self, workflow_name: str, project_id: str):
        """Execute workflow with skill telemetry."""

        workflow_id = str(uuid.uuid4())
        started_at = datetime.now()

        # Track workflow start
        self._record_workflow_start(workflow_id, project_id, workflow_name, started_at)

        skills_used = []

        try:
            # Execute workflow phases
            for phase in self.workflow_phases(workflow_name):
                # Track which skill is used
                skill_name = phase.skill
                skills_used.append(skill_name)

                # Execute phase
                result = self._execute_phase(phase)

            # Record successful completion
            self._record_workflow_complete(
                workflow_id,
                status='completed',
                skills_used=skills_used,
                completed_at=datetime.now()
            )

        except Exception as e:
            # Record failure
            self._record_workflow_complete(
                workflow_id,
                status='failed',
                skills_used=skills_used,
                completed_at=datetime.now(),
                error=str(e)
            )
            raise
```

### Recommendation System

Use aggregated metrics to optimize workflow orchestration:

```python
class WorkflowOptimizer:
    def recommend_skill_sequence(self, workflow_name: str, project_context: dict) -> list[str]:
        """Recommend optimal skill sequence based on historical data."""

        # Query historical workflow executions
        with duckdb.connect(self.db_path) as conn:
            successful_runs = conn.execute("""
                SELECT skills_used, total_duration_ms
                FROM workflow_executions
                WHERE workflow_name = ? AND status = 'completed'
                ORDER BY total_duration_ms ASC
                LIMIT 10
            """, (workflow_name,)).fetchall()

        # Analyze patterns
        skill_sequences = [run[0] for run in successful_runs]

        # Return most common successful sequence
        # (implementation depends on your skill representation)

        return recommended_sequence
```

## Privacy Guarantees

### Data Locality

✅ **All data stored locally** in `~/.claude/data/mahavishnu/`
✅ **No external API calls** - aggregation uses DuckDB locally
✅ **No PII** - project paths are only identifiers, can be hashed

### Opt-In Model

✅ **Projects explicitly registered** via `register_project` tool
✅ **Read-only collection** - metrics JSON files never modified
✅ **Unregister anytime** - delete project from registry

### Transparency

✅ **Raw metrics preserved** - always available in project's `.session-buddy/`
✅ **Audit trail** - all collection operations logged
✅ **User controls** - can disable collection, clear aggregated data

## Usage Examples

### Example 1: Cross-Project Skill Analysis

```bash
# Register multiple projects
/register_project project_path="/Users/les/Projects/crackerjack" project_name="Crackerjack" project_type="cli"
/register_project project_path="/Users/les/Projects/session-buddy" project_name="Session Buddy" project_type="mcp-server"

# Collect metrics from all projects
/collect_skill_metrics

# Get top skills across all projects
/get_top_skills limit=20 time_window="monthly"

# Analyze effectiveness of a specific skill
/analyze_skill_effectiveness skill_name="code-review"
```

### Example 2: Workflow Optimization

```bash
# Get recommendations for a specific project
/get_workflow_recommendations project_id="crackerjack"

# View which skills work best in "feature-dev" workflow
# (requires workflow telemetry integration)
```

### Example 3: Team-Level Insights

```bash
# Most used skills across all team projects
/get_top_skills limit=50 time_window="all"

# Compare skill usage between projects
/analyze_skill_effectiveness skill_name="test-generation" project_id="crackerjack"
/analyze_skill_effectiveness skill_name="test-generation" project_id="session-buddy"
```

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Create DuckDB schema for skill metrics
- [ ] Implement `MetricsCollector` class
- [ ] Implement `AggregationEngine` class
- [ ] Create project registry table
- [ ] Unit tests for collection and aggregation

### Phase 2: MCP Tools (Week 2)
- [ ] Implement `register_project` tool
- [ ] Implement `collect_skill_metrics` tool
- [ ] Implement `get_top_skills` tool
- [ ] Implement `analyze_skill_effectiveness` tool
- [ ] Integration tests

### Phase 3: Workflow Telemetry (Week 3)
- [ ] Add workflow execution tracking
- [ ] Implement skill-workflow correlation
- [ ] Create `get_workflow_recommendations` tool
- [ ] End-to-end workflow tests

### Phase 4: Analysis & Insights (Week 4)
- [ ] Implement pattern detection algorithms
- [ ] Add time-series trend analysis
- [ ] Create visualization data exports
- [ ] Documentation and examples

## Key Design Decisions

### Why DuckDB?

✅ **Local-first** - no server required
✅ **Fast analytics** - columnar storage optimized for aggregations
✅ **SQL interface** - familiar query language
✅ **Zero dependencies** - single binary, no external services
✅ **Already in use** - Session Buddy uses DuckDB for reflections

### Why Opt-In Registration?

✅ **Respects project autonomy** - projects are independent
✅ **Privacy control** - user decides what to include
✅ **Scalability** - can aggregate across any number of projects
✅ **Flexibility** - can add/remove projects dynamically

### Why Separate Aggregates Table?

✅ **Performance** - pre-computed aggregations are fast
✅ **Time windows** - supports daily/weekly/monthly views
✅ **Cross-project queries** - unified view without complex joins
✅ **Historical tracking** - preserves trends over time

## Future Enhancements

1. **Skill Relationship Analysis**
   - Which skills are commonly used together?
   - Skill co-occurrence patterns
   - Optimal skill sequences

2. **Predictive Recommendations**
   - Predict which skills will be needed next
   - Suggest skill improvements based on failure patterns
   - Workflow optimization based on historical performance

3. **Team Collaboration**
   - Share skill metrics across team members (optional)
   - Aggregate team-level insights
   - Collaborative skill refinement

4. **Visualization**
   - Export data for external visualization tools
   - Built-in charts for skill usage trends
   - Workflow performance dashboards

## References

- **Session Buddy:** `/Users/les/Projects/session-buddy/`
- **Crackerjack Skill Metrics:** `crackerjack/skill_metrics.py` (assumed location)
- **DuckDB Documentation:** https://duckdb.org/docs/
- **Mahavishnu Architecture:** See Session Buddy README for workflow orchestration details
