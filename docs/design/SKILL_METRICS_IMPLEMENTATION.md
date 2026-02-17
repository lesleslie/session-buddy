# Skill Metrics Aggregation - Implementation Plan

**Status:** Ready for Implementation
**Priority:** High (Workflow Intelligence Enhancement)
**Estimated Effort:** 3-4 weeks

## Quick Start Guide

This plan provides specific implementation steps for adding cross-project skill metrics aggregation to Mahavishnu.

## Implementation Checklist

### Week 1: Data Layer Foundation

#### Step 1: Create Database Schema

**File:** `session_buddy/mahavishnu/db.py`

```python
"""
Database schema and initialization for Mahavishnu metrics.
"""
from pathlib import Path
import duckdb

MAHAVISHNU_DB_DIR = Path.home() / ".claude/data/mahavishnu"
MAHAVISHNU_DB_DIR.mkdir(parents=True, exist_ok=True)


def init_skill_metrics_db() -> duckdb.DuckDBPyConnection:
    """Initialize skill metrics database with schema."""
    db_path = MAHAVISHNU_DB_DIR / "skill_metrics.duckdb"

    conn = duckdb.connect(str(db_path))

    # Projects registry
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            project_path TEXT UNIQUE NOT NULL,
            project_name TEXT,
            project_type TEXT,
            metadata JSON,
            registered_at TIMESTAMP DEFAULT NOW(),
            last_sync_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)

    # Skill usage records
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_usage (
            id INTEGER PRIMARY KEY,
            project_id TEXT REFERENCES projects(project_id),
            skill_name TEXT NOT NULL,
            invoked_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            duration_ms REAL,
            success BOOLEAN,
            followup_actions INTEGER,
            session_id TEXT,
            metadata JSON
        )
    """)

    # Pre-computed aggregates
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_aggregates (
            skill_name TEXT NOT NULL,
            project_id TEXT,
            time_window TEXT NOT NULL,
            total_invocations INTEGER,
            successful_completions INTEGER,
            avg_duration_ms REAL,
            avg_followup_actions REAL,
            first_used TIMESTAMP,
            last_used TIMESTAMP,
            UNIQUE(skill_name, project_id, time_window)
        )
    """)

    # Workflow telemetry
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_executions (
            workflow_id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(project_id),
            workflow_name TEXT NOT NULL,
            started_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            status TEXT,
            skills_used JSON,
            total_duration_ms REAL,
            metadata JSON
        )
    """)

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_usage_project_time ON skill_usage(project_id, invoked_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_usage_skill_time ON skill_usage(skill_name, invoked_at)")

    return conn
```

#### Step 2: Implement Metrics Collector

**File:** `session_buddy/mahavishnu/collector.py`

```python
"""
Collect skill metrics from crackerjack project JSON files.
"""
from pathlib import Path
from typing import Optional
import duckdb
import json
from datetime import datetime
from .db import init_skill_metrics_db, MAHAVISHNU_DB_DIR


class SkillMetricsCollector:
    """Collects skill metrics from registered projects."""

    def __init__(self):
        self.db_path = MAHAVISHNU_DB_DIR / "skill_metrics.duckdb"
        self._ensure_db()

    def _ensure_db(self):
        """Ensure database exists."""
        if not self.db_path.exists():
            init_skill_metrics_db()

    def register_project(
        self,
        project_path: Path,
        project_name: str,
        project_type: str = "unknown",
        metadata: Optional[dict] = None
    ) -> str:
        """Register a project for metrics collection.

        Returns:
            project_id
        """
        # Generate project ID from path hash
        project_id = hashlib.sha256(str(project_path).encode()).hexdigest()[:16]

        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO projects
                (project_id, project_path, project_name, project_type, metadata, registered_at)
                VALUES (?, ?, ?, ?, ?, NOW())
            """, (project_id, str(project_path), project_name, project_type, json.dumps(metadata or {})))

        return project_id

    def collect_from_project(self, project_path: Path) -> dict:
        """Collect metrics from a single project.

        Returns:
            {'collected': int, 'skipped': int, 'errors': int, 'error_details': list}
        """
        metrics_file = project_path / ".session-buddy/skill_metrics.json"

        if not metrics_file.exists():
            return {
                'collected': 0,
                'skipped': 0,
                'errors': 0,
                'error_details': ['Metrics file not found']
            }

        try:
            with open(metrics_file) as f:
                data = json.load(f)

            # Get project ID
            with duckdb.connect(str(self.db_path)) as conn:
                result = conn.execute(
                    "SELECT project_id FROM projects WHERE project_path = ?",
                    (str(project_path),)
                ).fetchone()

                if not result:
                    return {
                        'collected': 0,
                        'skipped': 0,
                        'errors': 1,
                        'error_details': ['Project not registered']
                    }

                project_id = result[0]

            collected = 0
            for skill_name, records in data.get('skills', {}).items():
                for record in records:
                    try:
                        self._insert_record(project_id, skill_name, record)
                        collected += 1
                    except Exception as e:
                        # Log error but continue processing
                        pass

            # Update last_sync_at
            with duckdb.connect(str(self.db_path)) as conn:
                conn.execute(
                    "UPDATE projects SET last_sync_at = NOW() WHERE project_id = ?",
                    (project_id,)
                )

            return {
                'collected': collected,
                'skipped': 0,
                'errors': 0,
                'error_details': []
            }

        except Exception as e:
            return {
                'collected': 0,
                'skipped': 0,
                'errors': 1,
                'error_details': [str(e)]
            }

    def _insert_record(self, project_id: str, skill_name: str, record: dict) -> None:
        """Insert a single skill usage record."""
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO skill_usage (
                    project_id, skill_name, invoked_at, completed_at,
                    duration_ms, success, followup_actions, session_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id,
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

#### Step 3: Implement Aggregation Engine

**File:** `session_buddy/mahavishnu/aggregator.py`

```python
"""
Aggregate skill metrics across projects.
"""
import duckdb
from pathlib import Path
from typing import Literal, Optional
from .db import MAHAVISHNU_DB_DIR

TimeWindow = Literal['daily', 'weekly', 'monthly', 'all']


class SkillMetricsAggregator:
    """Computes aggregated skill metrics."""

    def __init__(self):
        self.db_path = MAHAVISHNU_DB_DIR / "skill_metrics.duckdb"

    def compute_aggregates(
        self,
        project_id: Optional[str] = None,
        time_window: TimeWindow = 'all',
        force_refresh: bool = False
    ) -> int:
        """Compute skill usage aggregates.

        Returns:
            Number of aggregates computed
        """
        with duckdb.connect(str(self.db_path)) as conn:
            # Determine time truncation
            time_trunc = self._get_time_trunc(time_window)

            # Delete existing aggregates if forcing refresh
            if force_refresh:
                conn.execute("""
                    DELETE FROM skill_aggregates
                    WHERE (? IS NULL OR project_id = ?) AND time_window = ?
                """, (project_id, project_id, time_window))

            # Compute and insert aggregates
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
        time_window: TimeWindow = 'all',
        min_success_rate: Optional[float] = None
    ) -> list[dict]:
        """Get most used skills.

        Returns:
            List of skill statistics
        """
        with duckdb.connect(str(self.db_path)) as conn:
            query = """
                SELECT
                    skill_name,
                    total_invocations,
                    successful_completions,
                    CAST(successful_completions AS FLOAT) / NULLIF(total_invocations, 0) as success_rate
                FROM skill_aggregates
                WHERE (? IS NULL OR project_id = ?) AND time_window = ?
            """

            params = [project_id, project_id, time_window]

            if min_success_rate is not None:
                query += " AND (CAST(successful_completions AS FLOAT) / NULLIF(total_invocations, 0)) >= ?"
                params.append(min_success_rate)

            query += " ORDER BY total_invocations DESC LIMIT ?"
            params.append(limit)

            results = conn.execute(query, params).fetchall()

            return [
                {
                    'skill_name': row[0],
                    'total_invocations': row[1],
                    'successful_completions': row[2],
                    'success_rate': row[3] or 0.0
                }
                for row in results
            ]

    def get_skill_effectiveness(
        self,
        skill_name: str,
        project_id: Optional[str] = None
    ) -> dict:
        """Analyze skill effectiveness.

        Returns:
            Effectiveness metrics and insights
        """
        with duckdb.connect(str(self.db_path)) as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total_uses,
                    SUM(CAST(success AS INTEGER)) as successful,
                    AVG(duration_ms) as avg_duration,
                    AVG(followup_actions) as avg_followup,
                    MIN(invoked_at) as first_used,
                    MAX(invoked_at) as last_used
                FROM skill_usage
                WHERE skill_name = ? AND (? IS NULL OR project_id = ?)
            """, (skill_name, project_id, project_id)).fetchone()

            if not row or row[0] == 0:
                return {
                    'skill_name': skill_name,
                    'found': False
                }

            total, successful, avg_duration, avg_followup, first, last = row
            success_rate = successful / total if total > 0 else 0

            # Generate insights
            insights = []
            if success_rate < 0.6:
                insights.append(f"Low success rate ({success_rate:.1%}) - review skill prompts")
            elif success_rate > 0.9:
                insights.append(f"Excellent success rate ({success_rate:.1%}) - skill is well-tuned")

            if avg_followup > 2:
                insights.append(f"High follow-up rate ({avg_followup:.1f}) - skill may need refinement")

            return {
                'skill_name': skill_name,
                'found': True,
                'total_uses': total,
                'success_rate': success_rate,
                'avg_duration_ms': avg_duration,
                'avg_followup_actions': avg_followup,
                'first_used': first,
                'last_used': last,
                'insights': insights
            }

    def get_cross_project_comparison(self, skill_name: str) -> list[dict]:
        """Compare skill usage across projects.

        Returns:
            List of per-project statistics
        """
        with duckdb.connect(str(self.db_path)) as conn:
            results = conn.execute("""
                SELECT
                    p.project_name,
                    p.project_type,
                    COUNT(*) as total_uses,
                    SUM(CAST(su.success AS INTEGER)) as successful,
                    AVG(su.duration_ms) as avg_duration
                FROM skill_usage su
                JOIN projects p ON su.project_id = p.project_id
                WHERE su.skill_name = ?
                GROUP BY p.project_id, p.project_name, p.project_type
                ORDER BY total_uses DESC
            """, (skill_name,)).fetchall()

            return [
                {
                    'project_name': row[0],
                    'project_type': row[1],
                    'total_uses': row[2],
                    'success_rate': row[3] / row[2] if row[2] > 0 else 0,
                    'avg_duration_ms': row[4]
                }
                for row in results
            ]

    def _get_time_trunc(self, time_window: TimeWindow) -> str:
        """Get SQL time truncation expression."""
        if time_window == 'daily':
            return "DATE_TRUNC('day', invoked_at)"
        elif time_window == 'weekly':
            return "DATE_TRUNC('week', invoked_at)"
        elif time_window == 'monthly':
            return "DATE_TRUNC('month', invoked_at)"
        else:  # 'all'
            return "'1970-01-01'::TIMESTAMP"
```

### Week 2: MCP Tools Integration

#### Step 4: Create MCP Tools

**File:** `session_buddy/mahavishnu/tools.py`

```python
"""
MCP tools for skill metrics aggregation.
"""
from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from typing import Optional
from .collector import SkillMetricsCollector
from .aggregator import SkillMetricsAggregator, TimeWindow

mcp = FastMCP("mahavishnu-skill-metrics")

@mcp.tool()
def register_project(
    project_path: str,
    project_name: str,
    project_type: str = "unknown",
    metadata: Optional[str] = None
) -> str:
    """Register a project for cross-project skill metrics collection.

    Args:
        project_path: Absolute path to project directory
        project_name: Human-readable project name
        project_type: Project category (web, cli, library, mcp-server, etc.)
        metadata: Optional JSON string with additional metadata

    Returns:
        Confirmation message with project ID
    """
    collector = SkillMetricsCollector()

    metadata_dict = json.loads(metadata) if metadata else None

    project_id = collector.register_project(
        project_path=Path(project_path),
        project_name=project_name,
        project_type=project_type,
        metadata=metadata_dict
    )

    return f"✅ Project registered: {project_name} (ID: {project_id})"


@mcp.tool()
def unregister_project(project_path: str) -> str:
    """Unregister a project from metrics collection.

    Args:
        project_path: Absolute path to project directory

    Returns:
        Confirmation message
    """
    collector = SkillMetricsCollector()
    db_path = collector.db_path

    import duckdb
    with duckdb.connect(str(db_path)) as conn:
        result = conn.execute(
            "UPDATE projects SET is_active = FALSE WHERE project_path = ?",
            (project_path,)
        )

        if result.rowcount == 0:
            return f"❌ Project not found: {project_path}"

        return f"✅ Project unregistered: {project_path}"


@mcp.tool()
def list_registered_projects() -> str:
    """List all registered projects.

    Returns:
        JSON array of registered projects
    """
    collector = SkillMetricsCollector()
    db_path = collector.db_path

    import duckdb
    with duckdb.connect(str(db_path)) as conn:
        results = conn.execute("""
            SELECT
                project_id,
                project_name,
                project_type,
                project_path,
                registered_at,
                last_sync_at,
                is_active
            FROM projects
            ORDER BY project_name
        """).fetchall()

        projects = [
            {
                'project_id': row[0],
                'project_name': row[1],
                'project_type': row[2],
                'project_path': row[3],
                'registered_at': str(row[4]),
                'last_sync_at': str(row[5]) if row[5] else None,
                'is_active': row[6]
            }
            for row in results
        ]

        return json.dumps(projects, indent=2)


@mcp.tool()
def collect_skill_metrics(project_path: Optional[str] = None) -> str:
    """Collect skill metrics from registered projects.

    Args:
        project_path: Specific project path, or None for all projects

    Returns:
        Collection results summary
    """
    collector = SkillMetricsCollector()

    if project_path:
        results = collector.collect_from_project(Path(project_path))
        return json.dumps(results, indent=2)
    else:
        # Collect from all active projects
        import duckdb
        with duckdb.connect(str(collector.db_path)) as conn:
            project_paths = conn.execute(
                "SELECT project_path FROM projects WHERE is_active = TRUE"
            ).fetchall()

        all_results = {}
        for (path,) in project_paths:
            all_results[path] = collector.collect_from_project(Path(path))

        total_collected = sum(r['collected'] for r in all_results.values())

        return json.dumps({
            'summary': f"Collected {total_collected} metrics from {len(all_results)} projects",
            'details': all_results
        }, indent=2)


@mcp.tool()
def compute_aggregates(
    project_id: Optional[str] = None,
    time_window: str = "all",
    force_refresh: bool = False
) -> str:
    """Compute skill usage aggregates.

    Args:
        project_id: Specific project ID, or None for cross-project
        time_window: Time granularity (daily, weekly, monthly, all)
        force_refresh: Recompute even if aggregates exist

    Returns:
        Summary of computed aggregates
    """
    aggregator = SkillMetricsAggregator()

    count = aggregator.compute_aggregates(
        project_id=project_id,
        time_window=time_window,
        force_refresh=force_refresh
    )

    return f"✅ Computed {count} skill aggregates (time_window: {time_window})"


@mcp.tool()
def get_top_skills(
    limit: int = 10,
    project_id: Optional[str] = None,
    time_window: str = "all",
    min_success_rate: Optional[float] = None
) -> str:
    """Get most used skills.

    Args:
        limit: Maximum number of skills to return
        project_id: Filter by project ID
        time_window: Time granularity (daily, weekly, monthly, all)
        min_success_rate: Filter by minimum success rate (0.0-1.0)

    Returns:
        JSON array of top skills with statistics
    """
    aggregator = SkillMetricsAggregator()

    skills = aggregator.get_top_skills(
        limit=limit,
        project_id=project_id,
        time_window=time_window,
        min_success_rate=min_success_rate
    )

    return json.dumps(skills, indent=2)


@mcp.tool()
def analyze_skill_effectiveness(
    skill_name: str,
    project_id: Optional[str] = None
) -> str:
    """Analyze skill effectiveness patterns.

    Args:
        skill_name: Name of skill to analyze
        project_id: Filter by project ID, or None for cross-project

    Returns:
        JSON with effectiveness metrics and insights
    """
    aggregator = SkillMetricsAggregator()

    effectiveness = aggregator.get_skill_effectiveness(skill_name, project_id)

    return json.dumps(effectiveness, indent=2)


@mcp.tool()
def compare_skill_across_projects(skill_name: str) -> str:
    """Compare skill usage across all registered projects.

    Args:
        skill_name: Name of skill to compare

    Returns:
        JSON array of per-project statistics
    """
    aggregator = SkillMetricsAggregator()

    comparison = aggregator.get_cross_project_comparison(skill_name)

    return json.dumps(comparison, indent=2)


@mcp.tool()
def get_skill_summary(project_id: Optional[str] = None) -> str:
    """Get comprehensive skill usage summary.

    Args:
        project_id: Filter by project ID, or None for cross-project

    Returns:
        JSON with overall statistics and top skills
    """
    aggregator = SkillMetricsAggregator()

    # Get overall stats
    import duckdb
    with duckdb.connect(str(aggregator.db_path)) as conn:
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT skill_name) as unique_skills,
                COUNT(*) as total_uses,
                SUM(CAST(success AS INTEGER)) as successful,
                AVG(duration_ms) as avg_duration
            FROM skill_usage
            WHERE (? IS NULL OR project_id = ?)
        """, (project_id, project_id)).fetchone()

    if not row or row[0] == 0:
        return json.dumps({'error': 'No data found'})

    unique_skills, total_uses, successful, avg_duration = row
    success_rate = successful / total_uses if total_uses > 0 else 0

    # Get top skills
    top_skills = aggregator.get_top_skills(limit=10, project_id=project_id)

    return json.dumps({
        'unique_skills': unique_skills,
        'total_uses': total_uses,
        'overall_success_rate': success_rate,
        'avg_duration_ms': avg_duration,
        'top_skills': top_skills
    }, indent=2)
```

#### Step 5: Register Tools with Mahavishnu Server

**File:** `session_buddy/mahavishnu/__init__.py` (update existing)

```python
"""
Mahavishnu - Workflow orchestration with skill metrics aggregation.
"""
from .tools import mcp as skill_metrics_mcp

__all__ = ['skill_metrics_mcp']
```

### Week 3: Testing & Documentation

#### Step 6: Create Test Suite

**File:** `tests/test_skill_metrics_aggregation.py`

```python
"""
Test suite for skill metrics aggregation.
"""
import pytest
from pathlib import Path
import json
import tempfile
from session_buddy.mahavishnu.collector import SkillMetricsCollector
from session_buddy.mahavishnu.aggregator import SkillMetricsAggregator


@pytest.fixture
def temp_project():
    """Create a temporary project with skill metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        session_dir = project_path / ".session-buddy"
        session_dir.mkdir()

        # Create sample metrics
        metrics = {
            'skills': {
                'code-review': [
                    {
                        'invoked_at': '2025-02-01T10:00:00',
                        'completed_at': '2025-02-01T10:01:30',
                        'duration_ms': 90000,
                        'success': True,
                        'followup_actions': 1,
                        'session_id': 'test-session-1'
                    }
                ],
                'test-generation': [
                    {
                        'invoked_at': '2025-02-01T11:00:00',
                        'completed_at': '2025-02-01T11:02:00',
                        'duration_ms': 120000,
                        'success': True,
                        'followup_actions': 0,
                        'session_id': 'test-session-1'
                    }
                ]
            }
        }

        with open(session_dir / "skill_metrics.json", 'w') as f:
            json.dump(metrics, f)

        yield project_path


def test_project_registration(temp_project):
    """Test project registration."""
    collector = SkillMetricsCollector()

    project_id = collector.register_project(
        project_path=temp_project,
        project_name="Test Project",
        project_type="test"
    )

    assert project_id is not None
    assert len(project_id) == 16  # SHA256 hash prefix


def test_metrics_collection(temp_project):
    """Test metrics collection from a project."""
    collector = SkillMetricsCollector()

    # Register project
    collector.register_project(
        project_path=temp_project,
        project_name="Test Project",
        project_type="test"
    )

    # Collect metrics
    results = collector.collect_from_project(temp_project)

    assert results['collected'] == 2
    assert results['errors'] == 0


def test_aggregation_computation(temp_project):
    """Test aggregate computation."""
    collector = SkillMetricsCollector()
    aggregator = SkillMetricsAggregator()

    # Setup
    collector.register_project(
        project_path=temp_project,
        project_name="Test Project",
        project_type="test"
    )
    collector.collect_from_project(temp_project)

    # Get project ID
    import duckdb
    with duckdb.connect(str(collector.db_path)) as conn:
        project_id = conn.execute(
            "SELECT project_id FROM projects WHERE project_path = ?",
            (str(temp_project),)
        ).fetchone()[0]

    # Compute aggregates
    count = aggregator.compute_aggregates(project_id=project_id)

    assert count == 2  # Two skills

    # Get top skills
    top_skills = aggregator.get_top_skills(project_id=project_id)

    assert len(top_skills) == 2
    assert top_skills[0]['skill_name'] in ['code-review', 'test-generation']


def test_skill_effectiveness_analysis(temp_project):
    """Test skill effectiveness analysis."""
    collector = SkillMetricsCollector()
    aggregator = SkillMetricsAggregator()

    # Setup
    collector.register_project(
        project_path=temp_project,
        project_name="Test Project",
        project_type="test"
    )
    collector.collect_from_project(temp_project)

    import duckdb
    with duckdb.connect(str(collector.db_path)) as conn:
        project_id = conn.execute(
            "SELECT project_id FROM projects WHERE project_path = ?",
            (str(temp_project),)
        ).fetchone()[0]

    # Analyze effectiveness
    effectiveness = aggregator.get_skill_effectiveness('code-review', project_id)

    assert effectiveness['found'] is True
    assert effectiveness['total_uses'] == 1
    assert effectiveness['success_rate'] == 1.0
```

#### Step 7: Documentation

**File:** `docs/features/SKILL_METRICS_AGGREGATION.md`

```markdown
# Cross-Project Skill Metrics Aggregation

## Overview

Mahavishnu provides privacy-first cross-project skill metrics aggregation, enabling workflow intelligence while keeping all data local.

## Quick Start

### 1. Register Projects

```bash
/register_project project_path="/Users/les/Projects/crackerjack" project_name="Crackerjack" project_type="cli"
/register_project project_path="/Users/les/Projects/session-buddy" project_name="Session Buddy" project_type="mcp-server"
```

### 2. Collect Metrics

```bash
# Collect from all projects
/collect_skill_metrics

# Or collect from specific project
/collect_skill_metrics project_path="/Users/les/Projects/crackerjack"
```

### 3. Analyze

```bash
# Get top skills
/get_top_skills limit=20

# Analyze specific skill
/analyze_skill_effectiveness skill_name="code-review"

# Compare across projects
/compare_skill_across_projects skill_name="code-review"
```

## MCP Tools Reference

### Project Management

- `register_project` - Register a project for metrics collection
- `unregister_project` - Unregister a project
- `list_registered_projects` - List all registered projects

### Metrics Collection

- `collect_skill_metrics` - Collect metrics from projects
- `compute_aggregates` - Compute skill usage aggregates

### Analysis & Insights

- `get_top_skills` - Get most used skills
- `analyze_skill_effectiveness` - Analyze skill effectiveness
- `compare_skill_across_projects` - Compare skill usage across projects
- `get_skill_summary` - Get comprehensive skill usage summary

## Privacy Guarantees

✅ All data stored locally in `~/.claude/data/mahavishnu/`
✅ No external API calls or data transmission
✅ Opt-in per-project registration
✅ Projects remain autonomous

## Usage Examples

See implementation design doc for detailed examples.
```

## Integration Points

### With Crackerjack

The skill metrics JSON file in crackerjack should follow this schema:

```json
{
  "version": "1.0",
  "generated_at": "2025-02-10T12:00:00Z",
  "skills": {
    "skill-name": [
      {
        "invoked_at": "2025-02-10T10:00:00Z",
        "completed_at": "2025-02-10T10:01:30Z",
        "duration_ms": 90000,
        "success": true,
        "followup_actions": 1,
        "session_id": "session-uuid",
        "metadata": {
          "workflow": "feature-dev",
          "agent": "python-pro"
        }
      }
    ]
  }
}
```

### With Mahavishnu Workflow Orchestration

Workflow execution tracking:

```python
# In workflow executor
from session_buddy.mahavishnu.collector import SkillMetricsCollector

def execute_workflow(workflow_name: str, project_id: str):
    workflow_id = str(uuid.uuid4())
    started_at = datetime.now()

    # Record start
    # ... (implementation)

    try:
        # Execute phases
        skills_used = []
        for phase in workflow_phases:
            skill_name = phase.skill
            skills_used.append(skill_name)
            result = execute_phase(phase)

        # Record completion
        record_workflow_complete(workflow_id, skills_used, started_at)

    except Exception as e:
        record_workflow_failed(workflow_id, skills_used, started_at, str(e))
```

## Success Criteria

- [ ] All tests passing
- [ ] Privacy guarantees met (no external data transmission)
- [ ] Performance: aggregation completes in <5 seconds for 1000 records
- [ ] MCP tools registered and functional
- [ ] Documentation complete
- [ ] Example workflows demonstrated

## Next Steps

After implementation:

1. **Workflow Telemetry**: Add workflow execution tracking
2. **Pattern Detection**: Implement skill co-occurrence analysis
3. **Recommendations**: Build intelligent workflow optimization
4. **Visualization**: Create skill usage trend exports
