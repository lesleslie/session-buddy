# Quality Tracking Integration with Crackerjack

**Proposal Date**: 2026-02-03
**Status**: 📋 Proposal for Discussion

## Overview

Integrate Session Buddy's quality tracking with Crackerjack's pattern-based quality system for unified CI/CD quality monitoring.

## Current State

### Crackerjack Quality Tracking

Crackerjack tracks quality metrics in `.crackerjack/` directory:

```json
{
  "lint_error_trend": [0, 154, 143, 124, ...],
  "test_coverage_trend": [],
  "dependency_age": {},
  "config_completeness": 0.95
}
```

**Components**:

- `patterns.json` - Solution patterns with outcome scores
- `health_metrics.json` - Health trends over time
- `agent_audit_report.json` - Agent quality assessment

### Session Buddy Quality Tracker

Current implementation: `scripts/quality_tracker.py`

- Calculates quality score (0-100)
- Tracks 4 components: coverage, quality, type_hints, security
- Saves to `.quality_history.json`

**Issue**: Not integrated with crackerjack's ecosystem

______________________________________________________________________

## Proposed Integration

### Option 1: Crackerjack Pattern Registration (Recommended)

Session Buddy registers quality patterns with crackerjack:

**1. Create Crackerjack Integration Script**

`scripts/crackerjack_quality_reporter.py`:

```python
#!/usr/bin/env python3
"""Report Session Buddy quality metrics to Crackerjack."""

import json
from pathlib import Path
from session_buddy.utils.quality_utils_v2 import QualityAssessmentV2

def report_quality_to_crackerjack():
    """Calculate quality and report to crackerjack patterns."""
    # Calculate quality score
    qa = QualityAssessmentV2()
    score = qa.calculate_quality_score(Path.cwd())

    # Load crackerjack patterns
    crackerjack_dir = Path("../crackerjack/.crackerjack")
    patterns_file = crackerjack_dir / "patterns.json"

    if patterns_file.exists():
        patterns = json.loads(patterns_file.read_text())
    else:
        patterns = {"patterns": []}

    # Add Session Buddy quality pattern
    quality_pattern = {
        "pattern_type": "quality_gate",
        "category": "session_buddy",
        "context": {
            "quality_score": score["overall_score"],
            "maturity_score": score["maturity_score"],
            "test_coverage": score["test_coverage"] / 100,
            "code_quality": score["code_quality"] / 100,
            "session_optimization": score["session_optimization"] / 100,
        },
        "solution": {
            "description": f"Quality score: {score['overall_score']}/100",
            "recommendations": score.get("recommendations", [])
        },
        "outcome_score": score["overall_score"] / 100,
        "created_at": datetime.now().isoformat(),
        "application_count": 0,
        "feedback_score": 0.0
    }

    patterns["patterns"].append(quality_pattern)
    patterns_file.write_text(json.dumps(patterns, indent=2))

if __name__ == "__main__":
    report_quality_to_crackerjack()
```

**2. Add to Pre-commit Hook**

`.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Run Session Buddy quality check
python scripts/crackerjack_quality_reporter.py

# Check if quality score >= threshold
# ... (validation logic)
```

**3. Update Crackerjack Health Metrics**

Extend `.crackerjack/health_metrics.json`:

```json
{
  "lint_error_trend": [...],
  "test_coverage_trend": [...],
  "dependency_age": {},
  "config_completeness": 0.95,
  "session_buddy_quality_trend": [85.0, 87.5, 90.0, 88.5],
  "session_buddy_security_tests": 109,
  "session_buddy_type_hint_coverage": 0.987
}
```

______________________________________________________________________

### Option 2: Standalone Quality Gate (Simpler)

Session Buddy runs quality checks independently, with optional crackerjack reporting:

**`scripts/quality_gate.py`**:

```python
#!/usr/bin/env python3
"""Quality gate enforcement for CI/CD."""

import sys
from pathlib import Path

# Minimum quality thresholds
THRESHOLDS = {
    "overall_score": 80,
    "test_coverage": 85,
    "type_hints": 95,
    "security_tests": 100  # Must have security tests
}

def enforce_quality_gate() -> bool:
    """Enforce quality gate for CI/CD."""
    from scripts.quality_tracker import QualityTracker

    tracker = QualityTracker()
    score = tracker.calculate_quality_score()

    # Check thresholds
    failures = []

    if score["overall"] < THRESHOLDS["overall_score"]:
        failures.append(f"Overall score {score['overall']} < {THRESHOLDS['overall_score']}")

    if score["metrics"]["coverage"]["coverage_pct"] < THRESHOLDS["test_coverage"]:
        failures.append(f"Coverage {score['metrics']['coverage']['coverage_pct']}% < {THRESHOLDS['test_coverage']}%")

    if score["metrics"]["type_hints"]["coverage_pct"] < THRESHOLDS["type_hints"]:
        failures.append(f"Type hints {score['metrics']['type_hints']['coverage_pct']}% < {THRESHOLDS['type_hints']}%")

    if score["metrics"]["security"]["test_count"] < THRESHOLDS["security_tests"]:
        failures.append(f"Security tests {score['metrics']['security']['test_count']} < {THRESHOLDS['security_tests']}")

    if failures:
        print("❌ Quality Gate Failed:")
        for failure in failures:
            print(f"  • {failure}")
        return False

    print(f"✅ Quality Gate Passed: {score['overall']}/100")
    return True

if __name__ == "__main__":
    success = enforce_quality_gate()
    sys.exit(0 if success else 1)
```

**Usage in CI/CD**:

```bash
# Pre-commit
python scripts/quality_gate.py || exit 1

# Pre-merge (GitHub Actions, etc.)
python scripts/quality_gate.py
```

______________________________________________________________________

## Recommendation

**Adopt Option 2** (Standalone Quality Gate) for the following reasons:

1. **Simplicity**: No crackerjack dependency required
1. **Flexibility**: Easy to customize thresholds per project
1. **CI/CD Integration**: Works with any CI system (GitHub Actions, GitLab CI, etc.)
1. **Clear Failures**: Explicit error messages for failed checks
1. **Optional Crackerjack**: Can add crackerjack reporting later if needed

### Implementation Plan

**Phase 1** (Immediate):

- ✅ Create `scripts/quality_gate.py` with thresholds
- ✅ Add to pre-commit workflow
- ✅ Test locally with development workflow

**Phase 2** (Optional, Future):

- Add crackerjack pattern registration
- Create `.crackerjack/health_metrics.json` integration
- Track quality trends over time

______________________________________________________________________

## CI/CD Integration Examples

### GitHub Actions

`.github/workflows/quality.yml`:

```yaml
name: Quality Gate

on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: uv sync --group dev
      - name: Run quality gate
        run: python scripts/quality_gate.py
```

### GitLab CI

`.gitlab-ci.yml`:

```yaml
quality_gate:
  stage: test
  script:
    - uv sync --group dev
    - python scripts/quality_gate.py
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
```

### Pre-commit Hook

`.git/hooks/pre-commit`:

```bash
#!/bin/bash
echo "🔍 Running quality gate..."
python scripts/quality_gate.py
if [ $? -ne 0 ]; then
    echo "❌ Quality gate failed. Commit aborted."
    exit 1
fi
```

______________________________________________________________________

## Next Steps

1. **Create `scripts/quality_gate.py`** with configurable thresholds
1. **Add to Session Buddy CLI**: `python -m session_buddy quality-check`
1. **Test in development workflow** before committing
1. **Document in CONTRIBUTING.md** for contributors

______________________________________________________________________

## Conclusion

Session Buddy can leverage its existing quality tracker with a simple quality gate script that integrates seamlessly with any CI/CD system. Optional crackerjack integration can be added later for unified quality tracking across projects.
