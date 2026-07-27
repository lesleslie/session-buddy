---
title: Quality-Scoring Field Audit
date: 2026-07-27
status: draft
scope: wide
followups:
  - N6 per-file coverage summary (separate spec)
  - Promote test_pass_rate to CodeQualityScore (separate brainstorm, blocked on this spec landing)
related:
  - 2026-07-26-lifecycle-bug (shared connection lifecycle; not in scope)
  - WORKTREE_AUTOREMOVE (unrelated)
audited_files:
  - session_buddy/utils/quality_scoring.py
  - session_buddy/crackerjack_integration.py
  - session_buddy/utils/crackerjack/output_parser.py
  - session_buddy/utils/crackerjack/pattern_builder.py
---

# Quality-Scoring Field Audit — Design

## Context

Previous fix (commit `9181abce`) corrected the wrong-coverage-unit reading in two fallback helpers (`_read_coverage_json` and `_read_coverage_dotfile`) so the scoring tool reports statement coverage. A wide-scope audit extended to the rest of the scoring chain. The audit confirms the upstream Crackerjack integration already writes **statement** coverage to its metrics history, so the crackerjack integration path itself was never misreading the unit. Four other defect classes surface instead and are addressed here.

## Findings

| # | Site | Defect |
|---|---|---|
| N1 | `_calculate_coverage_metrics` → `_parse_metrics_history` | Verifies clean. Upstream emits statement coverage. |
| N2 | `_parse_metrics_history` defaults → `_calculate_code_quality`, `_run_security_checks` | Missing data defaults to `100` (perfect). Quality gates pass on no data. |
| N3a | `_calculate_lint_metrics` (crackerjack_integration.py:890) | Score = `100 − total_issues`. Severity discarded. |
| N3b | `_calculate_security_metrics` (crackerjack_integration.py:901) | Score = `100 − 10 × total_issues`. Severity discarded despite bandit populating it. |
| N3c | `_calculate_complexity_metrics` (crackerjack_integration.py:914) | Score from `high_complexity_files / total_files`. Line-weighted per-function complexity discarded. |
| N4 | `_parse_stderr_metrics` (crackerjack_integration.py:928) | First-match-wins stderr scan writes `parsed_quality`/`parsed_metric`/`parsed_score`. Not consumed today; latent foot-gun. |
| N5 | `_calculate_test_metrics` (crackerjack_integration.py:868) | Writes `test_pass_rate` to `quality_metrics` but no scoring consumer reads it. Orphan metric. |

## Goals

- Eliminate defective default-to-perfect behavior.
- Replace inverted-issue-count formulas with severity/depth-aware formulas that use data the parser already populates.
- Remove dead code that risks foot-gun inclusion in future scoring changes.
- Keep scoring semantics backward-compatible enough that existing tests' expected floors still pass within tolerance.
- Do **not** alter point totals in `CodeQualityScore`; this spec fixes wrongness, not policy.

## Non-goals

- N6: per-file coverage summary. New capability; separate spec.
- Promoting `test_pass_rate` to a scoring component. Out of scope and would require a point-budget ADR.
- Modifying `_calculate_code_quality` consumers (test thresholds, recommendations). They keep their existing assumptions.
- Touching anything outside the four files listed under `audited_files` in the front matter. In particular, no schema migrations in `crackerjack_integration.db`.

## Approach

### N2 — Default-missing instead of default-perfect

`_parse_metrics_history` builds its initial `metrics` dict with `lint_score=100`, `security_score=100`, `complexity_score=100` as fallbacks for missing history entries. Downstream readers then divide by 100 and award full points for absent data. Replace the defaults with `None`.

Consumer changes:

- `_calculate_code_quality` (quality_scoring.py:194) → when `lint_raw` is `None`, set `lint_score = 0` and add `"missing": True` to `details`.
- `_run_security_checks` (quality_scoring.py:626) → when `security_score_raw` is `None`, set `score = 0` and add `"missing": True` to `details`.
- For `complexity_score` inside `_calculate_code_quality`, same treatment.

Result: missing data produces zero points and a `"missing": True` flag in `details` so consumers and dashboards can see *why* the number is low.

### N3a — Severity-weighted lint score

Inputs (already parsed in `output_parser._parse_lint_output`, lines 150–183):

- `data["lint_issues"]` items, each with `{"tool": "ruff"|"pyright", "file", "line", "column", "type", "message"}`.
- For ruff, `type` is the error code (e.g. `F401`, `E501`, `B006`). Map codes to severity tiers.
- For pyright, `type` *is* the severity string (`"error"` or `"warning"`).

Code-prefix mapping for ruff codes (canonical letters):

| Prefix | Examples | Tier |
|---|---|---|
| `E`, `W` | pycodestyle | LOW |
| `F` | pyflakes | MEDIUM |
| `C`, `N`, `COM` | comprehensions / naming | LOW |
| `B`, `S`, `A`, `RUF`, `T` | bugbear / bandit plugin / async / return / tidy / RUF-prefixed | HIGH |

`tier_weights = {"HIGH": 10, "MEDIUM": 4, "LOW": 1}` exposed as a module-level constant.

```python
def _lint_tier(tool: str, type_str: str) -> str:
    if tool == "pyright":
        return "HIGH" if type_str == "error" else "LOW"
    # ruff: derive from first letter
    first = type_str[0] if type_str else "E"
    if first in {"B", "S", "T"} or type_str.startswith("RUF"):
        return "HIGH"
    if first == "F":
        return "MEDIUM"
    return "LOW"
```

Score: `lint_score = max(0.0, 100.0 − Σ(weights))`. Result rounded to 2dp.

### N3b — Severity-weighted security score

Inputs (already parsed in `output_parser._parse_security_output`, lines 186–214):

- `data["security_issues"]` items, each with `{"id", "description", "severity", "confidence"}`.
- `severity` is bandit-reported (HIGH/MEDIUM/LOW/NONE).

```python
SECURITY_TIER_WEIGHTS = {"HIGH": 10, "MEDIUM": 4, "LOW": 1, "NONE": 0}
def _security_tier(severity: str | None) -> str:
    return (severity or "NONE").upper() if (severity or "").upper() in SECURITY_TIER_WEIGHTS else "NONE"
```

Score: `security_score = max(0.0, 100.0 − Σ(SECURITY_TIER_WEIGHTS[s]))`.

### N3c — Line-weighted cyclomatic complexity score

Inputs (already parsed in `output_parser._parse_complexity_output`, lines 250–276):

- `data["complexity_data"][file] = {"lines": int, "complexity": float}`.

Compute line-weighted average cyclomatic complexity:

```
total_weight = sum(lines for f in data)
total_weighted = sum(lines * complexity for f in data)
avg = total_weighted / total_weight   if total_weight > 0 else 0
```

Score mapping (two-stage linear at canonical cyclomatic thresholds 5/10):

```python
COMPLEXITY_HIGH = 5
COMPLEXITY_CEILING = 10

def _complexity_score_from_avg(avg: float) -> float:
    if avg <= COMPLEXITY_HIGH:
        return 100.0
    if avg <= COMPLEXITY_CEILING:
        return 100.0 - (avg - COMPLEXITY_HIGH) * 10  # 5→100, 10→50
    return max(0.0, 50.0 - (avg - COMPLEXITY_CEILING) * 10)  # >10, decaying to 0
```

Result rounded to 2dp.

This replaces the current "percentage of files NOT high-complexity" heuristic with a score reflective of the project's actual cyclomatic load.

### N4 — Deprecate stderr scan

Replace the body of `_parse_stderr_metrics` with a one-time deprecation warning and an empty return:

```python
_warned_stderr_deprecation = False

def _parse_stderr_metrics(self, stderr_content: str) -> dict[str, float]:
    global _warned_stderr_deprecation
    if not _warned_stderr_deprecation:
        warnings.warn(
            "_parse_stderr_metrics is deprecated; remove callers.",
            DeprecationWarning,
            stacklevel=2,
        )
        _warned_stderr_deprecation = True
    return {}
```

Keep the method callable (callers in `_calculate_quality_metrics` at crackerjack_integration.py:861 are still invoked). Removal is a separate commit because the callers need to be re-routed in tandem.

### N5 — Drop `test_pass_rate` from `quality_metrics`

`_calculate_test_metrics` currently computes and returns `{"test_pass_rate": float}`. That value is appended to `quality_metrics` in `_calculate_quality_metrics` (line 855). No scoring code path consumes it. Trend analysis (`get_quality_trends`) already derives it from `crackerjack_results.test_results` separately.

Change: stop appending `test_pass_rate` to `quality_metrics`. Trend analysis paths remain unaffected because they read from `test_results` directly.

This is a **breaking change** for any external caller that reads `quality_metrics["test_pass_rate"]`. Mitigations:

1. Search for `test_pass_rate` consumers in the `mcp/` sub-tree and the public MCP tools; document any direct reads.
2. If a public tool reads it, retain the field for one release with a deprecation warning rather than deleting it. Default to retaining with a `warnings.warn` DeprecationWarning.
3. If only internal code consumes it, delete cleanly.

The spec lists this as a conditional: **retain with deprecation warning by default; switch to deletion only after consumers are confirmed absent**.

### N6 — Not in this spec

Per-file coverage summary from `data["coverage_data"]` is dropped here. Separate spec when a concrete consumer requests it.

## Component changes

| Component | Change |
|---|---|
| `quality_scoring.py` `_parse_metrics_history` | Defaults of `lint_score`/`security_score`/`complexity_score` → `None`. Consumer functions consume `None` cleanly. |
| `crackerjack_integration.py` `_calculate_quality_metrics` | Add `import warnings`. Pass `data["lint_issues"]`, `data["security_issues"]`, `data["complexity_data"]` from `parsed_data` into the relevant metrics function via new parameters or computed inline. |
| `crackerjack_integration.py` `_calculate_lint_metrics` | Re-implement to take a `lint_issues: list[dict]` parameter and return a severity-weighted score. |
| `crackerjack_integration.py` `_calculate_security_metrics` | Re-implement to take a `security_issues: list[dict]` parameter; use bandit severity strings. |
| `crackerjack_integration.py` `_calculate_complexity_metrics` | Re-implement to take a `complexity_data: dict` parameter; compute line-weighted average. |
| `crackerjack_integration.py` `_calculate_test_metrics` | Return `{}` (or keep emitting `test_pass_rate` with deprecation warning — see N5 conditional). |
| `crackerjack_integration.py` `_parse_stderr_metrics` | Deprecation-warning no-op. |
| New: `_severity_tier_weights` module-level constant | `{"HIGH": 10, "MEDIUM": 4, "LOW": 1}` shared by N3a and N3b. |
| New: `_complexity_avg_score` module-level helper | Two-stage linear at 5 and 10. |

## Data flow

```
crackerjack CLI stdout
  ↓
parser.parse_output(...)
  ├─→ data["lint_issues"]      (items with tool, type)
  ├─→ data["security_issues"]  (items with severity, confidence)
  ├─→ data["complexity_data"]  (file → {lines, complexity})
  └─→ data["coverage_data"]    (file → {statements, missing, coverage})
  ↓
integration._calculate_quality_metrics(parsed_data, ...)
  ├─→ lint_score      via _calculate_lint_metrics(lint_issues)
  ├─→ security_score  via _calculate_security_metrics(security_issues)
  ├─→ complexity_score via _calculate_complexity_metrics(complexity_data)
  ├─→ code_coverage   via _calculate_coverage_metrics(coverage_summary)
  └─→ (legacy) _parse_stderr_metrics → {}     [N4 deprecation]
  ↓
sqlite INSERT into quality_metrics_history
  ↓ (later)
get_quality_metrics_history() → list of metrics dicts
  ↓
quality_scoring._parse_metrics_history()
  ├─ uses defaults of None (was 100)             [N2]
  ↓
quality_scoring.calculate_quality_score_v2(...)
  ├─ consumes None → zero score + "missing":True [N2]
```

## Error handling

- Empty/no data cases are explicit: `None` from `_parse_metrics_history` propagates to consumers, who convert to `0.0` plus a `"missing": True` detail flag. The scoring recommendation `_generate_recommendations_v2` should not emit a "low coverage → add tests" recommendation when `"missing": True` — it should emit "Coverage data unavailable for this project."
- Invalid severity strings from bandit (anything not in the `{HIGH, MEDIUM, LOW, NONE}` set) are treated as `NONE` (weight 0). The set is small and stable.
- Ruff codes that don't start with a known letter (e.g. custom plugins) default to `LOW`.
- Division-by-zero for `_complexity_score_from_avg` is guarded by the `total_weight > 0` check; if 0, `avg=0` and the score is `100.0`.

## Testing

- **Regression net:** one parametrized test asserts that the metrics dict emitted by `_calculate_quality_metrics` contains only the keys consumed by `_parse_metrics_history`. Catches future re-introductions of orphan fields.
- **N3 severity weighting:** parametrized table over `(issues, expected_score)` for each severity tier; verify aggregate.
- **N3c complexity formula:** parametrized over `(avg, expected_score)` covering the three regions (≤5, 5<x≤10, >10).
- **N2 missing-data:** test that a metrics-history row lacking a field produces `None` upstream, then `0.0` plus `"missing": True` in `CodeQualityScore.details`.
- **N4 deprecation:** verify `DeprecationWarning` is emitted exactly once across multiple calls.
- **N5 conditional:** if retained, verify `quality_metrics["test_pass_rate"]` is still present in the dict and a `DeprecationWarning` is emitted on read; otherwise, verify absence and no warning.
- **Backward floor:** existing test fixtures that read recommendation thresholds (`<10`, `<13`, `<7`, `<3` in `_generate_recommendations_v2`) must still pass for default project fixtures. Adjust only test fixtures, not thresholds.

## Rollback signal

If a CI failure shows that the severity-weighted formulas produce wildly different scores for the canonical test fixtures (`session_buddy` itself, `mahavishnu` itself) — i.e., a category that scored ≥80 before scoring <40 after — stop and verify the formula constants before continuing. Do not chase the test by re-tuning constants.

## Wire-up contract (per Bodai `docs/plans/TEMPLATE.md`)

- **Triggered from:** existing user-driven or scheduled calls to `/session-buddy:checkpoint`, the `mcp__session-buddy__checkpoint` MCP tool, and any workflow that calls `calculate_quality_score_v2`.
- **Returns to / updates:** `quality_metrics` rows in `crackerjack_integration.db`. `CodeQualityScore` instances in any caller that holds the dataclass. Recommendation strings in `_generate_recommendations_v2` if it reads the new `"missing": True` flag.
- **Demonstrable by:** running `mcp__crackerjack__crackerjack_run("check", ai_agent_mode=False)` against `session-buddy` then `mcp__session-buddy__checkpoint(working_directory="/Users/les/Projects/session-buddy")` and verifying the score breakdown shows severity-tier detail in `details["lint_severity_breakdown"]` / `["security_severity_breakdown"]` / `["complexity_weighted_avg"]`.
- **Rollback signal:** see "Rollback signal" section above.
- **Observability added:** three new keys appear in `CodeQualityScore.details`: `lint_severity_breakdown`, `security_severity_breakdown`, `complexity_weighted_avg`. Existing keys preserved.

## Acceptance criteria

1. `_parse_metrics_history` returns `None` (not `100`) for metric types absent in history.
2. `_calculate_code_quality` and `_run_security_checks` never award full points when the underlying metric was missing.
3. `_calculate_lint_metrics`, `_calculate_security_metrics`, `_calculate_complexity_metrics` consume the per-item data from `parsed_data`, not the summary counts.
4. `_calculate_complexity_metrics` reports the line-weighted average it used, in `details`.
5. `_parse_stderr_metrics` emits exactly one `DeprecationWarning` for the lifetime of the process; subsequent calls are silent.
6. `test_pass_rate` consumer audit complete; either deleted or marked deprecated with the migration path noted.
7. No `CodeQualityScore` point totals changed. Total `0-40` preserved.
8. Regression net test passes; severity-weighted tests pass; complexity formula tests pass; missing-data tests pass; deprecation test passes.
9. Manual checkpoint run for `session-buddy` produces a quality breakdown whose `details` include the three new diagnostic keys and whose `total_score` is within ±5 of the previous reading (sanity bound — if it swings further than that, something else changed).

## Out of scope

- N6: per-file coverage summary (new capability).
- test_pass_rate scoring promotion (policy + point-budget ADR).
- Adopting severity tier weights 10/4/1 across other tools (e.g., ruff_format_violations) — one unified rubric is a separate spec.
- Schema migration of `crackerjack_integration.db`. Old rows with the wrong total-issues-based values stay; only newly-stored rows use the new formulas.
- Touching `_calculate_project_health`, `_calculate_dev_velocity`, or `_calculate_security`'s hygiene subsection (those don't read crackerjack-supplied metrics).
