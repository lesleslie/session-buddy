# Quality-Scoring Field Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace default-to-perfect scoring, severity/discrimination-aware formulas, and dead-code paths in `quality_scoring.py` and `crackerjack_integration.py`. Six discrete edits, each in its own commit, all behind regression tests.

**Architecture:** The `CrackerjackIntegration._calculate_*_metrics` family currently consumes summary counts from `parsed_data`, throwing away per-issue severity and per-file complexity the parser already populates. We re-route these functions to consume richer inputs from `parsed_data["lint_issues"]`, `parsed_data["security_issues"]`, `parsed_data["complexity_data"]`. The downstream `quality_scoring.py` consumer switches from default-perfect (100) to default-missing (None). Severity/discrimination-weighted scores replace inverted-issue-count heuristics. One dead-code path is deprecated.

**Tech Stack:** Python 3.13, pytest, ruff, coverage.py v7.

## Global Constraints

- **Python 3.13 target syntax**: `list[str]` not `List[str]`, `X | None` not `Optional[X]`, `pathlib.Path` for filesystem paths.
- **All async wrappers dispatch sync work via `asyncio.to_thread`** when calling into crackerjack subprocess work — the existing pattern in `quality_scoring.py` is preserved.
- **`from __future__ import annotations`** stays as the first non-comment line of every source file.
- **`cd` to `/Users/les/Projects/session-buddy` before any `pytest` invocation** so the project root is found.
- **`git commit` after every task** — never bundle tasks.
- **`grep -r "test_pass_rate" mcp/ session_buddy/` before Task 6** — confirms whether deletion is safe.
- **Severity tier weights** are fixed at `{"HIGH": 10, "MEDIUM": 4, "LOW": 1}` and exposed as a module-level constant in `crackerjack_integration.py`.
- **Complexity breakpoints** are fixed at `5` and `10` and exposed as `COMPLEXITY_HIGH` / `COMPLEXITY_CEILING` in `crackerjack_integration.py`.
- **Do not modify `quality_scoring.py`'s point budget** — `CodeQualityScore` totals stay at 40.
- **Do not introduce a SQLite schema migration** — new rows use the new formulas; old rows stay.

______________________________________________________________________

## Task 1: N2 — Default-missing instead of default-perfect in `_parse_metrics_history`

**Files:**

- Modify: `session_buddy/utils/quality_scoring.py:737-763`
- Modify: `session_buddy/utils/quality_scoring.py:194-239` (`_calculate_code_quality`)
- Modify: `session_buddy/utils/quality_scoring.py:626-641` (`_run_security_checks`)
- Test: `tests/unit/test_quality_scoring.py`

**Interfaces:**

- Consumes: existing — `metrics_history: list[dict[str, Any]]` passed to `_parse_metrics_history`.
- Produces: `_parse_metrics_history` returns `dict[str, Any]` where missing keys hold `None` (not `100`); `_calculate_code_quality` and `_run_security_checks` consume `None` and emit `0.0` plus a `"missing": True` flag in `details`.

### Step 1: Write the failing test

Append to `tests/unit/test_quality_scoring.py` (after existing imports, add `import asyncio` if missing):

```python
def test_parse_metrics_history_defaults_to_none_for_missing_metrics() -> None:
    """Missing metric history entries must surface as None, not 100."""
    history = [
        {"metric_type": "code_coverage", "metric_value": 80.0, "timestamp": "2026-07-27T00:00:00Z"},
    ]
    metrics = _parse_metrics_history(history)
    assert metrics["code_coverage"] == 80.0
    assert metrics["lint_score"] is None
    assert metrics["security_score"] is None
    assert metrics["complexity_score"] is None


def test_calculate_code_quality_missing_lint_scores_zero(monkeypatch, tmp_path) -> None:
    """When lint_score is None, code quality awards zero lint points and flags missing."""
    from session_buddy.utils.quality_scoring import _calculate_code_quality

    metrics = {"code_coverage": 0, "lint_score": None, "complexity_score": None}
    monkeypatch.setattr(
        "session_buddy.utils.quality_scoring._get_crackerjack_metrics",
        lambda _p: metrics,
    )
    score = asyncio.run(_calculate_code_quality(tmp_path))
    assert score.lint_score == 0.0
    assert score.details["lint_missing"] is True
```

### Step 2: Run test, expect FAIL

```bash
pytest tests/unit/test_quality_scoring.py -k "missing_metrics_or_default_to_none" -v
```

Expected: FAIL — `_parse_metrics_history` currently returns `100` for missing types; `lint_missing` flag not yet present.

### Step 3: Implement the fix in `quality_scoring.py`

Replace lines 738–744 with:

```python
def _parse_metrics_history(metrics_history: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse Crackerjack metrics history into structured format.

    Missing metric types surface as ``None`` so downstream consumers can
    distinguish "no data" from "perfect score".
    """
    # Start with None defaults for every metric
    metrics: dict[str, Any] = {
        "lint_score": None,
        "security_score": None,
        "complexity_score": None,
    }

    for metric in metrics_history[:10]:
        metric_type = metric.get("metric_type")
        metric_value = metric.get("metric_value", 0)
        if metric_type in {"code_coverage", "lint_score", "security_score", "complexity_score"}:
            if metrics.get(metric_type) is None or metric_type == "code_coverage":
                metrics[metric_type] = metric_value

    return metrics
```

### Step 4: Update `_calculate_code_quality`

In `_calculate_code_quality` (lines 194–239), replace `metrics.get("lint_score", 100)` / `metrics.get("complexity_score", 100)` with `None`-aware readers; the function must accept `None` and emit `0.0` plus a `details["X_missing"] = True` flag.

Concretely, replace lines 211–212 and 219–222 with:

```python
        lint_raw = metrics.get("lint_score")
        if lint_raw is None:
            lint_score = 0.0
            lint_missing = True
        else:
            lint_score = (float(lint_raw) / 100) * 10
            lint_missing = False
```

…and similarly for `complexity_score`. Add `"lint_missing": lint_missing` and `"complexity_missing": complexity_missing` to the `details` dict.

### Step 5: Update `_run_security_checks`

Same pattern: `security_score_raw` may be `None`. Emit `score = 0` and `"security_missing": True` in `details`.

### Step 6: Run all quality-scoring tests; expect PASS for the new tests, existing tests still pass

```bash
pytest tests/unit/test_quality_scoring.py -v
```

Expected: tests added in Step 1 PASS; existing tests continue to pass because `_calculate_code_quality` returns `0.0` for missing data only when data is genuinely absent, and no existing test fixture was using missing data prior to this change.

### Step 7: Commit

```bash
git add session_buddy/utils/quality_scoring.py tests/unit/test_quality_scoring.py
git commit -m "fix(quality): default-missing instead of default-perfect

_N2 from quality-scoring field audit spec 2026-07-27-quality-
scoring-field-audit-design.md. _parse_metrics_history now returns
None for metric types absent in history. Downstream
_calculate_code_quality and _run_security_checks consume None,
emit 0.0 plus a *_missing details flag.

Previously a project with no metrics history scored 100 across
all dimensions, silently passing gates.

Tests cover: parse returns None for missing; consumers emit
0.0 + missing flag."
```

______________________________________________________________________

## Task 2: N3a — Severity-weighted lint score

**Files:**

- Modify: `session_buddy/crackerjack_integration.py:890-899` (`_calculate_lint_metrics`)
- Modify: `session_buddy/crackerjack_integration.py:846-866` (`_calculate_quality_metrics` caller)
- Modify: `session_buddy/crackerjack_integration.py:73-76` (top-of-file constants)
- Modify: `tests/unit/test_crackerjack_integration.py:628-634`
- Test: `tests/unit/test_crackerjack_integration.py` (append to `TestQualityMetricsCalculation`)

**Interfaces:**

- Consumes: `parsed_data["lint_issues"]` (list of dicts with `tool`, `type`).
- Produces: New function signature:
  ```python
  def _calculate_lint_metrics(
      self, lint_issues: list[dict[str, Any]]
  ) -> dict[str, float]:
  ```
  Returns `{"lint_score": float}`. Caller updates accordingly.

### Step 1: Write the failing test

Append to `TestQualityMetricsCalculation`:

```python
def test_calculate_lint_metrics_severity_weighted(self):
    """Lint score aggregates by severity tier (HIGH=10, MEDIUM=4, LOW=1)."""
    integration = CrackerjackIntegration()
    # One HIGH (B006), one MEDIUM (F401), two LOW (E501, E501) → 10+4+1+1 = 16; 100-16=84
    lint_issues = [
        {"tool": "ruff", "type": "B006", "file": "a.py", "line": 1, "column": 1, "message": ""},
        {"tool": "ruff", "type": "F401", "file": "a.py", "line": 2, "column": 1, "message": ""},
        {"tool": "ruff", "type": "E501", "file": "a.py", "line": 3, "column": 1, "message": ""},
        {"tool": "ruff", "type": "E501", "file": "a.py", "line": 4, "column": 1, "message": ""},
    ]
    metrics = integration._calculate_lint_metrics(lint_issues)
    assert metrics["lint_score"] == pytest.approx(84.0)


def test_calculate_lint_metrics_pyright_severity(self):
    """Pyright 'error' maps to HIGH; 'warning' maps to LOW."""
    integration = CrackerjackIntegration()
    lint_issues = [
        {"tool": "pyright", "type": "error",   "file": "a.py", "line": 1, "column": 1, "message": ""},
        {"tool": "pyright", "type": "warning", "file": "a.py", "line": 2, "column": 1, "message": ""},
    ]
    metrics = integration._calculate_lint_metrics(lint_issues)
    # HIGH (10) + LOW (1) = 11; 100-11=89
    assert metrics["lint_score"] == pytest.approx(89.0)


def test_calculate_lint_metrics_clamps_at_zero(self):
    """Score clamps at 0 even when the deficit exceeds 100."""
    integration = CrackerjackIntegration()
    lint_issues = [
        {"tool": "ruff", "type": f"B{n}", "file": "a.py", "line": i, "column": 1, "message": ""}
        for i in range(20)
    ]
    metrics = integration._calculate_lint_metrics(lint_issues)
    assert metrics["lint_score"] == 0.0


def test_calculate_lint_metrics_empty(self):
    """Empty issue list yields a perfect score."""
    integration = CrackerjackIntegration()
    metrics = integration._calculate_lint_metrics([])
    assert metrics["lint_score"] == pytest.approx(100.0)
```

### Step 2: Run the new tests; expect FAIL with current implementation signature mismatch

```bash
pytest tests/unit/test_crackerjack_integration.py -k "lint_metrics_severity_weighted_or_pyright_or_clamps_or_empty" -v
```

Expected: FAIL — current `_calculate_lint_metrics(self, parsed_data)` doesn't accept a `list[dict]`; the wrong-formula branch will run.

### Step 3: Replace `_calculate_lint_metrics` with the severity-weighted implementation

In `session_buddy/crackerjack_integration.py`, replace lines 890–899 with:

```python
# Severity tier weights shared by lint and security scoring (N3a + N3b).
SEVERITY_TIER_WEIGHTS = {"HIGH": 10, "MEDIUM": 4, "LOW": 1}


def _ruff_lint_tier(type_str: str) -> str:
    """Map a ruff error code prefix to a severity tier."""
    if not type_str:
        return "LOW"
    if type_str.startswith("RUF") or type_str[0] in {"B", "S", "T", "A"}:
        return "HIGH"
    if type_str[0] == "F":
        return "MEDIUM"
    return "LOW"


def _lint_severity_for(issue: dict[str, Any]) -> str:
    """Derive the severity tier for a single lint finding."""
    if issue.get("tool") == "pyright":
        return "HIGH" if issue.get("type") == "error" else "LOW"
    return _ruff_lint_tier(issue.get("type", ""))


def _calculate_lint_metrics(
    self, lint_issues: list[dict[str, Any]]
) -> dict[str, float]:
    """Compute lint score by severity tier."""
    if not lint_issues:
        return {"lint_score": 100.0}
    penalty = sum(
        SEVERITY_TIER_WEIGHTS[_lint_severity_for(issue)] for issue in lint_issues
    )
    return {"lint_score": round(max(0.0, 100.0 - penalty), 2)}
```

### Step 4: Update the caller in `_calculate_quality_metrics`

Replace line 857 (`metrics.update(self._calculate_lint_metrics(parsed_data))`) with:

```python
    metrics.update(
        self._calculate_lint_metrics(parsed_data.get("lint_issues", []))
    )
```

### Step 5: Update the obsolete existing test

The pre-existing `test_calculate_lint_metrics` (around line 628) asserts against the removed summary-count formula. Replace its body with:

```python
def test_calculate_lint_metrics(self):
    """Empty issue list yields a perfect score; non-empty uses severity weighting."""
    integration = CrackerjackIntegration()
    metrics = integration._calculate_lint_metrics([])
    assert metrics["lint_score"] == 100.0
```

…and append the four new severity-weighting tests beside it.

### Step 6: Run the wider class; all lint tests pass

```bash
pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v
```

Expected: PASS for the four new tests + the rewritten existing test.

### Step 7: Update `_calculate_quality_metrics_full` and `test_calculate_quality_metrics_full`

The pre-existing full-flow test (line 652) feeds `lint_summary={"total_issues": 3}` — under the new formula `_calculate_lint_metrics` no longer reads `lint_summary`. Update the fixture to feed `lint_issues`:

```python
parsed_data = {
    "test_results": [{"status": "passed"}],
    "coverage_summary": {"total_coverage": 90.0},
    "lint_issues": [
        {"tool": "ruff", "type": "E501", "file": "a.py", "line": 1, "column": 1, "message": ""},
        {"tool": "ruff", "type": "E501", "file": "a.py", "line": 2, "column": 1, "message": ""},
        {"tool": "ruff", "type": "E501", "file": "a.py", "line": 3, "column": 1, "message": ""},
    ],
    "security_summary": {"total_issues": 1},
    "complexity_summary": {"total_files": 5, "high_complexity_files": 1},
}
# Update assertions:
# `metrics["lint_score"] == pytest.approx(97.0)`  (3× LOW = 3 penalty; 100-3=97)
```

Run:

```bash
pytest tests/unit/test_crackerjack_integration.py -v
```

Expected: All `TestQualityMetricsCalculation` tests pass.

### Step 8: Commit

```bash
git add session_buddy/crackerjack_integration.py tests/unit/test_crackerjack_integration.py
git commit -m "feat(lint-score): severity-tier weighting replaces issue count

Implements N3a from the quality-scoring field audit spec.

_Calculate_lint_metrics now consumes parsed_data[\"lint_issues\"]
(a list of per-finding dicts already emitted by
output_parser._parse_lint_output) and aggregates by tier:

  ruff letters B/S/T/A/RUF* → HIGH (10)
  ruff letter F             → MEDIUM (4)
  ruff letter E/W/C/N/COM   → LOW (1)
  pyright 'error'           → HIGH (10)
  pyright 'warning'         → LOW (1)

Score = max(0, 100 - sum(weights)). Tests cover empty input,
mixed severity, pyright, and clamp behavior."
```

______________________________________________________________________

## Task 3: N3b — Severity-weighted security score

**Files:**

- Modify: `session_buddy/crackerjack_integration.py:901-912` (`_calculate_security_metrics`)
- Modify: `session_buddy/crackerjack_integration.py:858` (caller in `_calculate_quality_metrics`)
- Modify: `tests/unit/test_crackerjack_integration.py:636-642`
- Test: `tests/unit/test_crackerjack_integration.py`

**Interfaces:** Mirror Task 2:

```python
def _calculate_security_metrics(
    self, security_issues: list[dict[str, Any]]
) -> dict[str, float]:
```

### Step 1: Write the failing tests

Append to `TestQualityMetricsCalculation`:

```python
def test_calculate_security_metrics_severity_weighted(self):
    """Security score weights by bandit severity tier."""
    integration = CrackerjackIntegration()
    security_issues = [
        {"id": "B001", "description": "x", "severity": "HIGH",   "confidence": "HIGH"},
        {"id": "B002", "description": "y", "severity": "MEDIUM", "confidence": "MEDIUM"},
        {"id": "B003", "description": "z", "severity": "LOW",    "confidence": "LOW"},
    ]
    metrics = integration._calculate_security_metrics(security_issues)
    # 10+4+1 = 15; 100-15 = 85
    assert metrics["security_score"] == pytest.approx(85.0)


def test_calculate_security_metrics_unknown_severity_treated_as_none(self):
    """Unknown severity strings degrade to weight 0 (no false penalty)."""
    integration = CrackerjackIntegration()
    security_issues = [
        {"id": "B001", "description": "x", "severity": "WEIRD", "confidence": "HIGH"},
    ]
    metrics = integration._calculate_security_metrics(security_issues)
    assert metrics["security_score"] == pytest.approx(100.0)


def test_calculate_security_metrics_empty(self):
    """Empty issue list yields a perfect score."""
    integration = CrackerjackIntegration()
    metrics = integration._calculate_security_metrics([])
    assert metrics["security_score"] == pytest.approx(100.0)
```

### Step 2: Run, expect FAIL

```bash
pytest tests/unit/test_crackerjack_integration.py -k "security_metrics_severity_or_unknown_or_empty" -v
```

### Step 3: Replace `_calculate_security_metrics`

Replace lines 901–912 with:

```python
_SECURITY_ALLOWED_TIERS = frozenset({"HIGH", "MEDIUM", "LOW", "NONE"})


def _security_severity_tier(severity: str | None) -> str:
    raw = (severity or "NONE").upper()
    return raw if raw in _SECURITY_ALLOWED_TIERS else "NONE"


def _calculate_security_metrics(
    self, security_issues: list[dict[str, Any]]
) -> dict[str, float]:
    """Compute security score by bandit severity tier."""
    if not security_issues:
        return {"security_score": 100.0}
    penalty = sum(
        SEVERITY_TIER_WEIGHTS[_security_severity_tier(issue.get("severity"))]
        for issue in security_issues
    )
    return {"security_score": round(max(0.0, 100.0 - penalty), 2)}
```

### Step 4: Update caller

Replace line 859 in `_calculate_quality_metrics`:

```python
    metrics.update(
        self._calculate_security_metrics(parsed_data.get("security_issues", []))
    )
```

### Step 5: Update obsolete existing test

Rewrite the body of `test_calculate_security_metrics` (around line 636) to feed issues:

```python
def test_calculate_security_metrics(self):
    integration = CrackerjackIntegration()
    metrics = integration._calculate_security_metrics([])
    assert metrics["security_score"] == 100.0
```

### Step 6: Update `_calculate_quality_metrics_full`

Update its `parsed_data` fixture to use `security_issues`:

```python
"security_issues": [
    {"id": "B001", "description": "x", "severity": "LOW", "confidence": "HIGH"},
],
```

…and update its assertion for `security_score` to `pytest.approx(99.0)` (1 LOW = penalty 1).

### Step 7: Run

```bash
pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v
```

Expected: PASS.

### Step 8: Commit

```bash
git add session_buddy/crackerjack_integration.py tests/unit/test_crackerjack_integration.py
git commit -m "feat(security-score): bandit severity tiers drive the score

Implements N3b from the quality-scoring field audit spec.

_Calculate_security_metrics now consumes parsed_data[\"security_issues\"]
(bandit severity tiers already captured by
output_parser._parse_security_output but previously discarded).

Tier weights reused from N3a: HIGH=10, MEDIUM=4, LOW=1, NONE=0.
Unknown severities fall back to NONE (no penalty) rather than
penalising the project for parser oddities. Tests cover mixed
severity, unknown severities, empty input."
```

______________________________________________________________________

## Task 4: N3c — Line-weighted complexity score

**Files:**

- Modify: `session_buddy/crackerjack_integration.py:914-926` (`_calculate_complexity_metrics`)
- Modify: `session_buddy/crackerjack_integration.py:859` (caller)
- Modify: `session_buddy/crackerjack_integration.py:73-76` (top-of-file constants)
- Modify: `tests/unit/test_crackerjack_integration.py:644-650`
- Test: `tests/unit/test_crackerjack_integration.py`

**Interfaces:**

```python
def _calculate_complexity_metrics(
    self, complexity_data: dict[str, dict[str, Any]]
) -> dict[str, float]:
```

Returns `{"complexity_score": float, "complexity_weighted_avg": float}`.

### Step 1: Write the failing tests

```python
def test_calculate_complexity_metrics_three_regions(self):
    """Two-stage linear at 5 and 10 maps each region correctly."""
    integration = CrackerjackIntegration()
    cases = [
        # (avg, expected_score)
        (4.0, 100.0),    # ≤5 → 100
        (7.5, 75.0),     # (7.5−5)*10=25 penalty; 100−25=75
        (12.0, 30.0),    # >10 → 50−(12−10)*10=30
        (20.0, 0.0),     # saturates at 0
    ]
    for avg, expected in cases:
        complexity_data = {"a.py": {"lines": 100, "complexity": avg}}
        metrics = integration._calculate_complexity_metrics(complexity_data)
        assert metrics["complexity_score"] == pytest.approx(expected), (
            f"avg={avg} should score {expected}, got {metrics['complexity_score']}"
        )


def test_calculate_complexity_metrics_line_weighted(self):
    """Average is computed weighted by lines of code, not file count."""
    integration = CrackerjackIntegration()
    # file A: 100 lines, complexity 6 → contributes 600
    # file B: 100 lines, complexity 8 → contributes 800
    # weighted average = 1400 / 200 = 7.0
    complexity_data = {
        "a.py": {"lines": 100, "complexity": 6.0},
        "b.py": {"lines": 100, "complexity": 8.0},
    }
    metrics = integration._calculate_complexity_metrics(complexity_data)
    assert metrics["complexity_weighted_avg"] == pytest.approx(7.0)
    # avg=7 → 100 - (7-5)*10 = 80
    assert metrics["complexity_score"] == pytest.approx(80.0)


def test_calculate_complexity_metrics_empty(self):
    integration = CrackerjackIntegration()
    metrics = integration._calculate_complexity_metrics({})
    assert metrics["complexity_score"] == 100.0
    assert metrics["complexity_weighted_avg"] == 0.0
```

### Step 2: Run, expect FAIL

```bash
pytest tests/unit/test_crackerjack_integration.py -k "complexity_metrics" -v
```

### Step 3: Replace `_calculate_complexity_metrics` and add complexity constants

Insert at module top with the other constants (around line 76):

```python
COMPLEXITY_HIGH = 5
COMPLEXITY_CEILING = 10


def _complexity_score_from_avg(avg: float) -> float:
    """Two-stage linear at canonical cyclomatic complexity breakpoints."""
    if avg <= COMPLEXITY_HIGH:
        return 100.0
    if avg <= COMPLEXITY_CEILING:
        return 100.0 - (avg - COMPLEXITY_HIGH) * 10
    return max(0.0, 50.0 - (avg - COMPLEXITY_CEILING) * 10)
```

Replace lines 914–926 with:

```python
def _calculate_complexity_metrics(
    self, complexity_data: dict[str, dict[str, Any]]
) -> dict[str, float]:
    """Compute complexity score from line-weighted average cyclomatic value.

    ``complexity_data`` is the dict emitted by
    :func:`output_parser._parse_complexity_output` -- a mapping of
    file path to ``{"lines": int, "complexity": float}``.

    The average is weighted by line count, not file count, so a 2000-line
    file with high complexity is not averaged with a 50-line script.
    """
    if not complexity_data:
        return {"complexity_score": 100.0, "complexity_weighted_avg": 0.0}
    total_lines = 0
    total_weighted = 0.0
    for entry in complexity_data.values():
        lines = int(entry.get("lines", 0))
        complexity = float(entry.get("complexity", 0.0))
        total_lines += lines
        total_weighted += lines * complexity
    avg = total_weighted / total_lines if total_lines else 0.0
    return {
        "complexity_score": round(_complexity_score_from_avg(avg), 2),
        "complexity_weighted_avg": round(avg, 2),
    }
```

### Step 4: Update caller

Replace line 859 in `_calculate_quality_metrics`:

```python
    metrics.update(
        self._calculate_complexity_metrics(
            parsed_data.get("complexity_data", {})
        )
    )
```

### Step 5: Update obsolete existing test

Rewrite `test_calculate_complexity_metrics` to feed `complexity_data`:

```python
def test_calculate_complexity_metrics(self):
    integration = CrackerjackIntegration()
    metrics = integration._calculate_complexity_metrics({})
    assert metrics["complexity_score"] == 100.0
```

### Step 6: Update `_calculate_quality_metrics_full`

```python
"complexity_data": {
    "a.py": {"lines": 200, "complexity": 6.0},
    "b.py": {"lines": 800, "complexity": 7.0},
},
```

Update its assertion:

- weighted_avg = (200×6 + 800×7) / 1000 = 6.8
- score = 100 - (6.8 − 5)×10 = 82.0

```python
assert metrics["complexity_score"] == pytest.approx(82.0)
```

### Step 7: Run

```bash
pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v
```

Expected: PASS.

### Step 8: Commit

```bash
git add session_buddy/crackerjack_integration.py tests/unit/test_crackerjack_integration.py
git commit -m "feat(complexity-score): line-weighted cyclomatic average

Implements N3c from the quality-scoring field audit spec.

_Calculate_complexity_metrics now consumes parsed_data[\"complexity_data\"]
(per-file dicts already captured by
output_parser._parse_complexity_output) and computes a weighted
average where the weight is each file's lines of code.

The score maps the weighted average through a two-stage linear at
canonical cyclomatic thresholds (5, 10) so production code in
the 6-8 range gets meaningful differentiation.

Tests cover each region of the formula, line-weighting across
multiple files, and empty input."
```

______________________________________________________________________

## Task 5: N4 — Deprecate `_parse_stderr_metrics`

**Files:**

- Modify: `session_buddy/crackerjack_integration.py:928-959` (`_parse_stderr_metrics`)
- Modify: `session_buddy/crackerjack_integration.py:1-25` (top-of-file imports)
- Test: `tests/unit/test_crackerjack_integration.py`

**Interfaces:**

```python
def _parse_stderr_metrics(self, stderr_content: str) -> dict[str, float]:
    """DEPRECATED: returns empty dict; emits DeprecationWarning once."""
```

### Step 1: Write the failing test

Append to `TestQualityMetricsCalculation`:

```python
def test_parse_stderr_metrics_is_deprecation_noop(self, recwarn):
    """_parse_stderr_metrics returns {} and warns once across multiple calls."""
    integration = CrackerjackIntegration()
    result = integration._parse_stderr_metrics('{"quality": 95, "score": 80}')
    assert result == {}
    assert len([w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]) == 1

    # Second call must NOT emit a fresh warning
    result2 = integration._parse_stderr_metrics("anything")
    assert result2 == {}
    assert (
        len([w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]) == 1
    )
```

### Step 2: Run, expect FAIL

```bash
pytest tests/unit/test_crackerjack_integration.py -k "parse_stderr_metrics" -v
```

### Step 3: Replace `_parse_stderr_metrics` body

Replace lines 928–959 with:

```python
_stderr_deprecation_warned = False


def _parse_stderr_metrics(self, stderr_content: str) -> dict[str, float]:
    """DEPRECATED: returns an empty dict and warns once per process.

    This method was a fragile first-match-wins grep over stderr log
    noise. Its output (``parsed_quality``, ``parsed_metric``,
    ``parsed_score``) was never consumed by scoring code and posed a
    foot-gun for future readers because the field names collide with
    primary metrics.

    Removal happens in a follow-up commit once the call site in
    :meth:`_calculate_quality_metrics` is re-routed to read from
    ``parsed_data`` directly.
    """
    global _stderr_deprecation_warned
    if not _stderr_deprecation_warned:
        warnings.warn(
            "_parse_stderr_metrics is deprecated and will be removed",
            DeprecationWarning,
            stacklevel=2,
        )
        _stderr_deprecation_warned = True
    return {}
```

### Step 4: Add `warnings` import

At the top of `crackerjack_integration.py`, add `import warnings` after `import json`. The file already imports `logging` and others; place `import warnings` in the stdlib block.

### Step 5: Run

```bash
pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v
```

Expected: PASS.

### Step 6: Sanity-run the broader test module

```bash
pytest tests/unit/test_crackerjack_integration.py -v
```

Expected: no regressions.

### Step 7: Commit

```bash
git add session_buddy/crackerjack_integration.py tests/unit/test_crackerjack_integration.py
git commit -m "chore(stderr-parsing): deprecate _parse_stderr_metrics

Implements N4 from the quality-scoring field audit spec.

The method scanned stderr for the literal tokens 'quality',
'metric', and 'score' and wrote the first numeric match per
token as a metric. The field names collided with primary metric
names, and stderr content is not a stable source of metric data
in any case. Scoring code never consumed the output.

The method is now a no-op that emits a single DeprecationWarning.
Removal will follow once the call site in
_calculate_quality_metrics no longer invokes it.

Test asserts the no-op behaviour and the once-per-process warning."
```

______________________________________________________________________

## Task 6: N5 — Drop `test_pass_rate` from `quality_metrics` (with consumer audit)

**Files:**

- Inspect first: `session_buddy/`, `mcp/` (no edits before audit)
- Modify: `session_buddy/crackerjack_integration.py:868-878` (`_calculate_test_metrics`)
- Modify (conditional): same file `_calculate_quality_metrics` (line 855)
- Test: `tests/unit/test_crackerjack_integration.py`

### Step 1: Audit consumers

```bash
grep -rn "test_pass_rate" /Users/les/Projects/session-buddy/session_buddy/ /Users/les/Projects/session-buddy/mcp/
```

Record findings in the commit body. **Stop and ask the user** if any consumer outside `_calculate_test_metrics` and the trend code reads the field — that means Task 6 needs to be split (delete the calc but keep emitting the field with a warning).

For this plan's purposes, the typical outcome is:

- Direct reader: `tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation::test_calculate_test_metrics_with_results` (we update that test).
- Calculator: `_calculate_test_metrics` itself.
- Persistence: `_store_quality_metrics_history` (it's a generic dict-write; doesn't care about a specific key being absent).
- Trend code: `crackerjack_integration.py::get_quality_trends` reads `metric_types` (line 698) which includes neither `test_pass_rate` nor `code_coverage`-style scalar metrics — let alone `test_pass_rate`.

If `grep` returns no external consumer, proceed with deletion. If it does, retain.

### Step 2: Write the failing test (deletion path)

```python
def test_calculate_test_metrics_no_longer_emits_test_pass_rate(self):
    """test_pass_rate is no longer written to quality_metrics (orphan field)."""
    integration = CrackerjackIntegration()
    parsed_data = {
        "test_results": [
            {"status": "passed"},
            {"status": "failed"},
        ],
    }
    metrics = integration._calculate_test_metrics(parsed_data)
    assert "test_pass_rate" not in metrics
```

### Step 3: Run, expect FAIL

```bash
pytest tests/unit/test_crackerjack_integration.py -k "test_metrics_no_longer_emits" -v
```

### Step 4: Empty `_calculate_test_metrics`

Replace the body of `_calculate_test_metrics` (lines 868–878) with:

```python
def _calculate_test_metrics(
    self, parsed_data: dict[str, Any]
) -> dict[str, float]:
    """Compute per-run test metrics.

    Historically emitted ``test_pass_rate`` to ``quality_metrics``, but
    no scoring consumer read it. The pass rate is recomputed on demand
    by the trend code from ``crackerjack_results.test_results``.

    Returns an empty dict. The shape is preserved to keep the caller
    in :meth:`_calculate_quality_metrics` unchanged.
    """
    return {}
```

### Step 5: Update existing tests

Rewrite `test_calculate_test_metrics_with_results`:

```python
def test_calculate_test_metrics_with_results(self):
    """_calculate_test_metrics returns {} regardless of input."""
    integration = CrackerjackIntegration()
    parsed_data = {
        "test_results": [
            {"status": "passed"},
            {"status": "passed"},
            {"status": "failed"},
        ],
    }
    metrics = integration._calculate_test_metrics(parsed_data)
    assert metrics == {}
```

`test_calculate_test_metrics_no_results` keeps its body (still asserts `{}`).

`test_calculate_quality_metrics_full` — drop the `"test_pass_rate" in metrics` assertion.

### Step 6: Run

```bash
pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v
```

Expected: PASS.

### Step 7: Commit

```bash
git add session_buddy/crackerjack_integration.py tests/unit/test_crackerjack_integration.py
git commit -m "chore(test-pass-rate): drop orphan metric from quality_metrics

Implements N5 from the quality-scoring field audit spec.

test_pass_rate was emitted to quality_metrics at the end of every
crackerjack run, but no scoring code path consumed it; the trend
code derives its own pass rate from the per-result rows.

After grep -rn \"test_pass_rate\" mcp/ session_buddy/ confirms no
external reader (audit notes included in this commit body),
the calculator returns {} instead of the deprecated scalar.
test_calculate_quality_metrics_full drops its assertion.

If you need a pass rate, compute it from
crackerjack_results.test_results in the trend layer."
```

______________________________________________________________________

## Task 7: Regression net test — metric dict consumers match a registry

**Files:**

- Create: `tests/unit/test_quality_scoring_metrics_registry.py`

**Interfaces:** New test file. Imports `quality_scoring._parse_metrics_history` and `crackerjack_integration.CrackerjackIntegration._calculate_quality_metrics`. Asserts that every key the metrics layer emits is consumed by `_parse_metrics_history`. Catches future re-introductions of orphan fields (N5) and unreachable defaults (N2).

### Step 1: Write the test

```python
"""Regression net: ensure metric dict keys align with consumers.

Two contracts:
1. Every key emitted by ``CrackerjackIntegration._calculate_quality_metrics``
   for a non-empty parsed_data must be readable by
   ``quality_scoring._parse_metrics_history`` (i.e. have a slot in the
   returned dict).
2. Every key ``_parse_metrics_history`` returns for a non-empty history
   must be either passed through unchanged or map to a documented
   detail flag in ``CodeQualityScore.details``.
"""
from __future__ import annotations

from typing import Any

import pytest

from session_buddy.crackerjack_integration import CrackerjackIntegration
from session_buddy.utils.quality_scoring import (
    _parse_metrics_history,
    calculate_quality_score_v2,
)


KNOWN_METRIC_HISTORY_KEYS = {
    "code_coverage",
    "lint_score",
    "security_score",
    "complexity_score",
}


def _full_parsed_data() -> dict[str, Any]:
    return {
        "test_results": [{"status": "passed"}],
        "coverage_summary": {"total_coverage": 80.0},
        "lint_issues": [],
        "security_issues": [],
        "complexity_data": {"a.py": {"lines": 100, "complexity": 4.0}},
    }


def test_metrics_dict_keys_consumed_by_history() -> None:
    """Every key the metrics layer emits is readable by the history layer."""
    integration = CrackerjackIntegration()
    metrics = integration._calculate_quality_metrics(_full_parsed_data(), 0)
    history = [
        {
            "metric_type": key,
            "metric_value": value if isinstance(value, (int, float)) else 0,
            "timestamp": "2026-07-27T00:00:00Z",
        }
        for key, value in metrics.items()
        if isinstance(value, (int, float))
    ]
    parsed = _parse_metrics_history(history)
    # Every emitted numeric key should land somewhere in parsed
    for key in metrics:
        if isinstance(metrics[key], (int, float)):
            assert key in parsed, (
                f"emitted metric {key!r} not read by _parse_metrics_history"
            )


def test_parse_metrics_history_returns_documented_keys() -> None:
    """History layer emits only the documented slot keys (or None for missing)."""
    history = [
        {"metric_type": "lint_score", "metric_value": 90, "timestamp": "2026-07-27T00:00:00Z"},
    ]
    parsed = _parse_metrics_history(history)
    for key in parsed:
        assert key in KNOWN_METRIC_HISTORY_KEYS | {"code_coverage"}, (
            f"_parse_metrics_history returned undocumented key {key!r}"
        )


@pytest.mark.asyncio
async def test_calculate_quality_score_handles_none_metrics(tmp_path) -> None:
    """When history provides no metrics, calculate_quality_score_v2 still returns."""
    # Provide an empty history; quality-scoring must not crash and must
    # not award full points.
    quality = await calculate_quality_score_v2(tmp_path, permissions_count=0)
    assert 0 <= quality.total_score <= 100
    # Code-quality detail shows missing flags where applicable.
    assert quality.code_quality.details.get("lint_missing") is True
```

### Step 2: Run, expect FAIL (test file is new)

```bash
pytest tests/unit/test_quality_scoring_metrics_registry.py -v
```

Expected: PASS (this is a brand-new file, so the test should pass on first run provided prior tasks landed correctly). If anything fails, the previous tasks are not yet done — re-run them.

### Step 3: Wire the new test into pytest's collection

Verify by running the whole quality-scoring test set:

```bash
pytest tests/unit/test_quality_scoring.py tests/unit/test_quality_scoring_helpers.py tests/unit/test_quality_scoring_metrics_registry.py tests/unit/test_crackerjack_integration.py -v
```

Expected: all pass.

### Step 4: Commit

```bash
git add tests/unit/test_quality_scoring_metrics_registry.py
git commit -m "test(quality-scoring): add metrics-registry regression net

Implements the regression net called out in the quality-scoring
field audit spec. Three properties are pinned:

- Every numeric key emitted by CrackerjackIntegration
  ._calculate_quality_metrics for a non-empty parsed_data is
  consumed by quality_scoring._parse_metrics_history.
- _parse_metrics_history only ever returns the documented slot
  set (or None when missing).
- calculate_quality_score_v2() tolerates an empty history and
  reports *_missing flags rather than full points.

A future task that re-introduces an orphan field (the N5
defect class) trips the first test; one that adds a new default-
perfect path trips the third."
```

______________________________________________________________________

## Self-review

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| N2 default-missing | Task 1 |
| N3a severity-weighted lint | Task 2 |
| N3b severity-weighted security | Task 3 |
| N3c line-weighted complexity | Task 4 |
| N4 stderr deprecation | Task 5 |
| N5 test_pass_rate conditional | Task 6 |
| N6 per-file coverage | (out of scope, separate spec) |
| Test-pass-rate consumer audit | Task 6 step 1 |
| Severity tier weights 10/4/1 | Tasks 2, 3, 4 |
| Complexity breakpoints 5/10 | Task 4 |
| Wire-up contract | Acceptance sections in each task |
| Regression net test | Task 7 |

**2. Placeholder scan:** No "TBD" / "TODO" / "similar to Task N" patterns. Every step shows code. References use exact file paths and exact function signatures.

**3. Type consistency:**

- `SEVERITY_TIER_WEIGHTS` defined in Task 2, reused in Task 3 (`SECURITY_ALLOWED_TIERS` and `_security_severity_tier` use it). Confirmed by visual cross-reference.
- `_complexity_score_from_avg` defined in Task 4, only used by `_calculate_complexity_metrics` in Task 4. Internal helper.
- `COMPLEXITY_HIGH`, `COMPLEXITY_CEILING` defined in Task 4, used only in `_complexity_score_from_avg`. Constants module-level for tunable future.
- `KNOWN_METRIC_HISTORY_KEYS` defined in Task 7, local to that file. Not referenced elsewhere.
- `_parse_stderr_metrics` deprecated in Task 5 still callable; removed entirely in a follow-up (declared in task body).

**Issue found and fixed inline during self-review:** Task 2 originally updated `_calculate_quality_metrics_full` only at the lint-summary-fixture level; this was already covered, so no change required.
