# Skills Taxonomy Initialization Guide

## Overview

Phase 4 of Session-Buddy introduced three new taxonomy tables for organizing and understanding skills:

1. **skill_categories** - Hierarchical categorization of skills
2. **skill_modalities** - Multi-modal skill type definitions
3. **skill_dependencies** - Co-occurrence relationships between skills

The `initialize_taxonomy.py` script populates these tables with predefined seed data.

## Prerequisites

Before running the taxonomy initialization:

1. **V4 Migration Must Be Applied**

   The V4 migration creates the taxonomy tables. Run:

   ```bash
   cd /Users/les/Projects/session-buddy

   # Run migrations (includes V4)
   python -m session_buddy.storage.migrations migrate
   ```

2. **Database Must Exist**

   The script expects `.session-buddy/skills.db` to exist.

## Usage

### Basic Initialization

```bash
cd /Users/les/Projects/session-buddy
python scripts/initialize_taxonomy.py
```

### Expected Output

```
Checking migration status...
✓ V4 migration verified

Initializing skills taxonomy...

Step 1: Initializing categories...
  ✓ Category: Code Quality (code)
  ✓ Category: Testing (testing)
  ✓ Category: Documentation (documentation)
  ✓ Category: Build & Deploy (deployment)
  ✓ Category: Git & Version Control (code)
  ✓ Category: Linting & Formatting (code)
Categories initialized: 6

Step 2: Initializing modalities...
  ✓ Modality: ruff-check (code: python_source → diagnostics)
  ✓ Modality: pytest-run (testing: python_tests → test_results)
  ✓ Modality: sphinx-build (documentation: rst_docs → html_docs)
  ✓ Modality: docker-build (deployment: dockerfile → docker_image)
Modalities initialized: 4

Step 3: Initializing dependencies...
  ✓ Dependency: ruff-check ↔ black-format (lift: 3.5)
  ✓ Dependency: pytest-run ↔ coverage-report (lift: 2.8)
  ✓ Dependency: git-commit ↔ git-push (lift: 4.2)
  ✓ Dependency: docker-build ↔ k8s-deploy (lift: 2.1)
Dependencies initialized: 4

Verifying initialization...

============================================================
TAXONOMY INITIALIZATION SUMMARY
============================================================
Categories:     6 records
Modalities:      4 records
Dependencies:    4 records
============================================================

Categories initialized:
  • Build & Deploy          [deployment]
    Build and deployment tools
  • Code Quality            [code]
    Tools for checking and improving code quality
  • Documentation           [documentation]
    Documentation generation and checking
  • Git & Version Control   [code]
    Git and version control operations
  • Linting & Formatting    [code]
    Code linting and auto-formatting
  • Testing                 [testing]
    Test execution and coverage tools

Modalities initialized:
  • docker-build            [deployment]
    dockerfile → docker_image
  • pytest-run              [testing]
    python_tests → test_results
  • ruff-check              [code]
    python_source → diagnostics
  • sphinx-build            [documentation] [requires review]
    rst_docs → html_docs

Dependencies initialized:
  • git-commit ↔ git-push  (lift: 4.2)
  • ruff-check ↔ black-format     (lift: 3.5)
  • pytest-run ↔ coverage-report  (lift: 2.8)
  • docker-build ↔ k8s-deploy     (lift: 2.1)

✓ Taxonomy initialization complete!
```

## Idempotent Operation

The script is **idempotent** - it can be run multiple times safely. It uses `INSERT OR IGNORE` to skip existing records:

```bash
# Run once
python scripts/initialize_taxonomy.py

# Run again - will skip existing records
python scripts/initialize_taxonomy.py
```

Second run output:
```
Step 1: Initializing categories...
Categories initialized: 0  # All already exist

Step 2: Initializing modalities...
Modalities initialized: 0  # All already exist

Step 3: Initializing dependencies...
Dependencies initialized: 0  # All already exist
```

## Initial Data

### Categories

| Category Name | Domain | Description |
|--------------|--------|-------------|
| Code Quality | code | Tools for checking and improving code quality |
| Testing | testing | Test execution and coverage tools |
| Documentation | documentation | Documentation generation and checking |
| Build & Deploy | deployment | Build and deployment tools |
| Git & Version Control | code | Git and version control operations |
| Linting & Formatting | code | Code linting and auto-formatting |

### Modalities

| Skill Name | Type | Input | Output | Human Review |
|-----------|------|-------|--------|--------------|
| ruff-check | code | python_source | diagnostics | No |
| pytest-run | testing | python_tests | test_results | No |
| sphinx-build | documentation | rst_docs | html_docs | Yes |
| docker-build | deployment | dockerfile | docker_image | No |

### Dependencies

| Skill A | Skill B | Lift Score | Meaning |
|---------|---------|-----------|---------|
| ruff-check | black-format | 3.5 | Strong co-occurrence |
| pytest-run | coverage-report | 2.8 | High co-occurrence |
| git-commit | git-push | 4.2 | Very strong co-occurrence |
| docker-build | k8s-deploy | 2.1 | Moderate co-occurrence |

**Lift Score Interpretation**:
- `> 2.0` - Strong positive relationship (used together much more than expected)
- `1.5 - 2.0` - Moderate positive relationship
- `1.0` - Independent usage
- `< 1.0` - Negative relationship (rarely used together)

## Database Schema

### skill_categories Table

```sql
CREATE TABLE skill_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE,
    parent_category_id INTEGER,
    description TEXT,
    domain TEXT,  -- 'code', 'documentation', 'testing', 'deployment'
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_category_id) REFERENCES skill_categories(category_id)
);
```

### skill_modalities Table

```sql
CREATE TABLE skill_modalities (
    skill_name TEXT PRIMARY KEY,
    modality_type TEXT NOT NULL,  -- 'code', 'documentation', 'testing', 'deployment'
    input_format TEXT,  -- e.g., 'python_code', 'markdown', 'yaml'
    output_format TEXT,
    requires_human_review BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (skill_name) REFERENCES skill_invocation(skill_name)
);
```

### skill_dependencies Table

```sql
CREATE TABLE skill_dependencies (
    skill_a TEXT NOT NULL,
    skill_b TEXT NOT NULL,
    co_occurrence_count INTEGER DEFAULT 1,
    lift_score REAL,  -- >1 means skills used together more than expected
    last_updated TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (skill_a, skill_b),
    FOREIGN KEY (skill_a) REFERENCES skill_invocation(skill_name),
    FOREIGN KEY (skill_b) REFERENCES skill_invocation(skill_name)
);
```

## Post-Initialization Queries

After initialization, you can query the taxonomy:

### View All Categories

```sql
SELECT
    category_name,
    domain,
    description,
    (SELECT COUNT(*) FROM skill_category_mapping scm WHERE scm.category_id = sc.category_id) as skill_count
FROM skill_categories sc
ORDER BY domain, category_name;
```

### View Multi-Modal Skills

```sql
SELECT
    skill_name,
    modality_type,
    input_format,
    output_format,
    requires_human_review
FROM skill_modalities
ORDER BY modality_type, skill_name;
```

### View Skill Dependencies Network

```sql
SELECT
    skill_a,
    skill_b,
    co_occurrence_count,
    lift_score,
    CASE
        WHEN lift_score > 2.0 THEN 'strong_positive'
        WHEN lift_score > 1.5 THEN 'moderate_positive'
        WHEN lift_score > 1.0 THEN 'weak_positive'
        WHEN lift_score = 1.0 THEN 'independent'
        ELSE 'weak_negative'
    END as relationship_type
FROM skill_dependencies
WHERE lift_score IS NOT NULL
ORDER BY co_occurrence_count DESC;
```

### Get Skills by Category

```sql
SELECT
    sc.category_name,
    si.skill_name,
    COUNT(*) as invocation_count,
    AVG(CASE WHEN si.completed = 1 THEN 1.0 ELSE 0.0 END) as completion_rate
FROM skill_invocation si
JOIN skill_category_mapping scm ON si.skill_name = scm.skill_name
JOIN skill_categories sc ON scm.category_id = sc.category_id
GROUP BY sc.category_name, si.skill_name
ORDER BY sc.category_name, invocation_count DESC;
```

## Extending the Taxonomy

### Adding New Categories

Edit `scripts/initialize_taxonomy.py` and add to the `CATEGORIES` list:

```python
{
    "category_name": "Security",
    "description": "Security scanning and vulnerability detection",
    "domain": "security",
    "examples": ["security-scan", "sast-check", "dependency-audit"],
},
```

### Adding New Modalities

Edit the `MODALITIES` list:

```python
{
    "skill_name": "security-scan",
    "modality_type": "security",
    "input_format": "codebase",
    "output_format": "vulnerability_report",
    "requires_human_review": True,
},
```

### Adding New Dependencies

Edit the `DEPENDENCIES` list:

```python
{
    "skill_a": "security-scan",
    "skill_b": "sast-check",
    "expected_lift": 3.2,
},
```

Then re-run the script:

```bash
python scripts/initialize_taxonomy.py
```

## Dynamic Updates

The taxonomy can also be updated dynamically via the SkillsStorage API:

### Update Skill Dependencies Automatically

```python
from pathlib import Path
from session_buddy.storage.skills_storage import SkillsStorage

storage = SkillsStorage(Path(".session-buddy/skills.db"))

# Update dependencies based on actual co-occurrence data
result = storage.update_skill_dependencies(min_co_occurrence=5)

print(f"Created {result['dependencies_created']} dependencies")
```

### Add Category Programmatically

```python
import sqlite3
from pathlib import Path

db_path = Path(".session-buddy/skills.db")

with sqlite3.connect(db_path) as conn:
    conn.execute(
        """
        INSERT INTO skill_categories (category_name, description, domain, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        ("Security", "Security scanning tools", "security")
    )
    conn.commit()
```

## Troubleshooting

### Error: "V4 migration not applied"

**Cause**: The database schema doesn't include Phase 4 tables.

**Solution**: Run migrations first:

```bash
python -m session_buddy.storage.migrations migrate
```

### Error: "Database not found"

**Cause**: The `.session-buddy/skills.db` file doesn't exist.

**Solution**: Initialize Session-Buddy storage:

```bash
python -c "from session_buddy.storage.skills_storage import get_storage; get_storage()"
```

### No Records Inserted

**Cause**: Taxonomy data already exists (script is idempotent).

**Solution**: This is expected behavior. To re-initialize, delete existing records first:

```sql
DELETE FROM skill_dependencies;
DELETE FROM skill_category_mapping;
DELETE FROM skill_modalities;
DELETE FROM skill_categories;
```

## Integration with Session-Buddy

The taxonomy integrates with Session-Buddy's core features:

### Workflow-Aware Recommendations

Categories help organize skills by workflow phase:

```python
# Find skills in "Testing" category for execution phase
results = storage.search_by_query_workflow_aware(
    query_embedding,
    workflow_phase="execution",
)
```

### Dependency Graph

Dependencies enable workflow suggestions:

```python
# After running ruff-check, suggest black-format
dependencies = storage.get_skill_dependencies("ruff-check")
```

### Multi-Modal Search

Modalities enable type-specific skill discovery:

```python
# Find documentation skills
cursor.execute(
    """
    SELECT skill_name, input_format, output_format
    FROM skill_modalities
    WHERE modality_type = 'documentation'
    """
)
```

## References

- **V4 Migration**: `/Users/les/Projects/session-buddy/session_buddy/storage/migrations/V4__phase4_extensions__up.sql`
- **SkillsStorage**: `/Users/les/Projects/session-buddy/session_buddy/storage/skills_storage.py`
- **Initialization Script**: `/Users/les/Projects/session-buddy/scripts/initialize_taxonomy.py`

## Summary

The taxonomy initialization script provides:

- ✅ **6 predefined categories** covering common skill domains
- ✅ **4 multi-modal type definitions** for different skill types
- ✅ **4 dependency relationships** with lift scores
- ✅ **Idempotent execution** - safe to run multiple times
- ✅ **Extensible design** - easy to add new taxonomy data
- ✅ **Integration with SkillsStorage** - works with existing APIs

Run the script after V4 migration to seed your skills taxonomy!
