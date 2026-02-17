# Taxonomy Initialization Quick Reference

## Command

```bash
cd /Users/les/Projects/session-buddy
python scripts/initialize_taxonomy.py
```

## Prerequisites

1. Run V4 migration:
   ```bash
   python -m session_buddy.storage.migrations migrate
   ```

2. Verify database exists:
   ```bash
   ls -la .session-buddy/skills.db
   ```

## What It Does

Initializes 3 taxonomy tables with seed data:

| Table | Records | Description |
|-------|---------|-------------|
| skill_categories | 6 | Hierarchical categories (code, testing, docs, deployment) |
| skill_modalities | 4 | Multi-modal type definitions (input/output formats) |
| skill_dependencies | 4 | Co-occurrence relationships (lift scores) |

## Seed Data Summary

**Categories:**
- Code Quality (code)
- Testing (testing)
- Documentation (documentation)
- Build & Deploy (deployment)
- Git & Version Control (code)
- Linting & Formatting (code)

**Modalities:**
- ruff-check: python_source → diagnostics
- pytest-run: python_tests → test_results
- sphinx-build: rst_docs → html_docs
- docker-build: dockerfile → docker_image

**Dependencies:**
- ruff-check ↔ black-format (lift: 3.5)
- pytest-run ↔ coverage-report (lift: 2.8)
- git-commit ↔ git-push (lift: 4.2)
- docker-build ↔ k8s-deploy (lift: 2.1)

## Idempotent

Safe to run multiple times - uses `INSERT OR IGNORE`.

## Extending

Edit `/Users/les/Projects/session-buddy/scripts/initialize_taxonomy.py`:

```python
# Add category
CATEGORIES.append({
    "category_name": "Security",
    "description": "Security scanning tools",
    "domain": "security",
    "examples": ["security-scan"],
})

# Add modality
MODALITIES.append({
    "skill_name": "security-scan",
    "modality_type": "security",
    "input_format": "codebase",
    "output_format": "vulnerability_report",
    "requires_human_review": True,
})

# Add dependency
DEPENDENCIES.append({
    "skill_a": "security-scan",
    "skill_b": "dependency-audit",
    "expected_lift": 2.5,
})
```

Then re-run: `python scripts/initialize_taxonomy.py`

## Verification

```bash
# Check records
sqlite3 .session-buddy/skills.db "SELECT COUNT(*) FROM skill_categories;"
sqlite3 .session-buddy/skills.db "SELECT COUNT(*) FROM skill_modalities;"
sqlite3 .session-buddy/skills.db "SELECT COUNT(*) FROM skill_dependencies;"
```

## Dynamic Updates

```python
from pathlib import Path
from session_buddy.storage.skills_storage import SkillsStorage

storage = SkillsStorage(Path(".session-buddy/skills.db"))

# Auto-update dependencies from actual usage
result = storage.update_skill_dependencies(min_co_occurrence=5)
print(f"Created {result['dependencies_created']} dependencies")
```

## Full Documentation

See: `/Users/les/Projects/session-buddy/docs/initialization/TAXONOMY_INITIALIZATION.md`
