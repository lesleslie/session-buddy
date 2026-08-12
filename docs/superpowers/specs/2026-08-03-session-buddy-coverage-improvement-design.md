# Session-Buddy Coverage Improvement (Wave 1) — Design (v2)

> **Status:** v2 patches v1 per 3-agent review. Substantive design changes — v1 is superseded.

**Date:** 2026-08-03 (v2)
**Date of v1:** 2026-08-03 (commit `1437fb29`, superseded)
**Owner:** Session-Buddy maintainers
**Repo:** `/Users/les/Projects/session-buddy`

## What changed from v1

v1 was reviewed by three agents (general-purpose/random, test-coverage-review-specialist, qa-strategist) and surfaced 35 unique findings, with **1 Critical, 9 High, and many Important** issues that would have failed the wave at execution time:

| Issue (sources) | Source agents | v2 fix |
|---|---|---|
| **N1 contradicted CLAUDE.md's documented `--cov-fail-under=85` gate** | qa-st #9 | Reframe: this wave *prepares* 10 modules so the gate becomes locally achievable. N1 now states "the wave does not change the *threshold value* (CLAUDE.md mandates 85%) but does **not** raise the gate per-module — the wave runs with measurement-only and reports deltas against 85%." |
| **Concrete pick table included fabricated paths** (`coordinator.py`, `team_cli.py`, `mcp/tools/.../usage_tools.py` etc. — none exist) | qa-st closing note | Remove the candidate table; replace with "implementation plan enumerates real candidates by running coverage-driven selection" as a hard prerequisite. |
| **Branch coverage not pinned in check (b)** | cov #1, #3, #12; qa-st #11 | Pin `branch = true` in pyproject.toml `[tool.coverage.run]`; brief check (b) asserts ≥95% line AND ≥90% branch; verify in Phase 0. |
| **Check (b) runs only one test file — % can lie via import cascade** | cov #2 | Restructure: check (b) runs the full suite with `--cov=session_buddy.<module>` filter so the denominator matches the backlog script. |
| **Check (c) "smoke check" is unverifiable** | cov #4, #5; gp #2, #3; qa-st #10 | Pin the proof: `inspect.iscoroutinefunction` runtime assertion + grep for `asyncio.run`/`run_until_complete`/`get_event_loop().run` blocking. Promote Phase-2 grep to per-subagent gate. |
| **Check (d) `-x` is fragile on flaky pre-existing tests** | cov #6; qa-st #1 | Drop `-x`. Compare against Phase-0 baseline manifest of known failures (`docs/baselines/wave1-baseline.json`). Block on zero *new* failures. |
| **G5 ("any regression reverted") vs Rollback (>3 broken auto-reverts) — different thresholds** | gp #1; qa-st #2 | Unify: zero new failures per batch is the gate; rollback is per-commit, never blanket. Auto-revert path is documented but never silent. |
| **5 parallel agents race on shared `coverage.json`/`htmlcov`** | qa-st #3, #5 | Per-agent isolated worktree; per-agent `COVERAGE_FILE=.coverage.<agent>`; combine coverage in one serialized pass after merge. |
| **No BLOCKED / lost-context state machine for subagents** | qa-st #4; gp #4 | Per-agent state machine: BLOCKED → re-pick or escalate. Phase 0 logs agent IDs and re-pick candidates. |
| **Audit script "exit 0" can mask pytest failures (set -e reflex)** | qa-st #7; cov #10 | Explicit implementation: `set +e`, wrap pytest with `|| true`, then `exit 0` regardless; pytest failures appear in audit output and the meta-test (`scripts/run_coverage_audit.sh` smoke) verifies a forced failure exits 0 with non-empty FAIL lines. |
| **`pragma: no cover` rule for the 95%/90% gap not specified** | cov #7; qa-st #11 | Reviewer cross-check: any new `# pragma: no cover` must be paired with a one-line justification; unreviewed pragma additions are auto-rejected. |
| **Audit script collides with existing `scripts/analyze_coverage.py` and `scripts/run_with_coverage.sh`** | qa-st #14 | Reuse/extend `scripts/analyze_coverage.py` instead of new `coverage_backlog.py`; canonical entry point = `scripts/run_coverage_audit.sh`. |
| **`docs/completion-reports/` doesn't exist; history uses `docs/archive/completion-reports/`** | qa-st #13 | Pin destination = `docs/archive/completion-reports/2026-08-03-session-buddy-coverage-wave1.md`. Update Critical files table. |
| **`coverage.json` not durable; wave-start diff not machine-comparable** | qa-st #8 | Phase 0 writes `docs/baselines/wave1-baseline.json` (commit SHA, full pytest invocation, fail signatures, per-file line/branch metrics). Phase 2 emits delta from baseline. |
| **Backlog doc verification was manual eyeball (top 5 entries read against coverage.json)** | qa-st #16 (peer follow-up) | Add deterministic validator `scripts/verify_backlog.py coverage.json docs/coverage-backlog.md`: every backlog row's path/tier/percentage must match `coverage.json` exactly; fails on missing, duplicate, stale, or mis-tiered entries. Phase 0 + Phase 2 both run it. |
| **14% module too aggressive for one subagent** | cov #9 | Hard floor: skip modules \<30% in wave-1 (wave-2 candidate). Cap lines-added-per-module ≤400. |
| **Sync/async hit count metric undefined** | cov #11; gp #6; qa-st #15 | Pin metric: `sync_async_hit_count = new occurrences of asyncio.run / run_until_complete / get_event_loop().run in tests/unit/test_<module>.py authored by wave 1 (post-wave grep)`. Report verbatim. |
| **Primary vs sibling tie-breaker missing** | gp #5 | New tie-breaker #5: prefer the candidate whose module path appears in the crackerjack-fallback commit `188d7fd0`'s diff (recently touched). |
| **>600 LOC handling in BLOCKED** | cov #13 | Brief adds: "If `wc -l session_buddy/<module>.py` exceeds 600, BLOCKED with the line count; do not split." |
| **No public-function coverage requirement** | cov #14 | New check (e): every public function in target (`def [a-z]` excluding `_`-prefixed) has at least one test that names it in the REPORT table. |
| **>3 pre-existing tests broken threshold not scope-aware** | qa-st #2 | Threshold is per-batch (5 modules), not per-wave. >1 new failure in a batch blocks that batch's merge. |
| **MCP/CLI mocks don't exercise registration** | qa-st #12 | Add minimal non-coverage smoke for each public MCP/CLI target: tool-registration smoke (importable, listed in registry) and CLI command-help smoke (subprocess `python -m session_buddy.cli <cmd> --help` exits 0). |
| **Architecture didn't pin the partial-batch resolution** | gp #4 | Add explicit rule: if any subagent in a batch BLOCKED, the wave lead re-picks against the same slot criteria; batches run sequentially; no partial batch proceeds. |
| **Narrative line 13 said 100%, line 22 said ≥95%** | self-review | Tighten to one number (≥95% line + ≥90% branch) with explicit `pragma` rule and the rationale (crackerjack pattern was 100% on 5 tiny modules; this wave scales to 10 with a defensible gap). |
| **N6 referenced `188d7fd0`, but spec's own commit is `1437fb29`** | self-review | Rewrite N6 to anchor on current HEAD at execution time (re-validated at plan start). |
| **Candidate picks annotated as illustrative but no explicit revalidation requirement** | self-review | Add "Phase 0.5: machine-validated candidate enumeration" as a hard pre-Phase-1 gate. |

## Context

Session-Buddy has pytest coverage configured (`pyproject.toml` `[tool.coverage]`) and **CLAUDE.md mandates `--cov-fail-under=85`** (lines 61, 71, 512). Currently that gate is failing: 2 pre-existing test failures on main (verified post crackerjack-fallback merge at `188d7fd0`), many modules at 0% coverage.

Two sibling Bodai repos have established a coverage-recipe pattern this spec ports with one adaptation:

- **`mahavishnu`** has `docs/coverage-backlog.md` (4-tier categorization) plus three fan-out waves (`4deefabb` 10 modules → `97d77b78` 8 → `786d96cc` 8), each using 5 parallel subagents targeting 100% per module.
- **`crackerjack`** has `docs/TEST_COVERAGE_PLAN_CORE.md` (status: complete) and `scripts/run_coverage_audit.sh`. Its `5ecbe9ff` commit documents the **sync/async gotcha** (sync wrappers around coroutines pass pytest but `coverage.py` misses the async branch).

**The adaptation:** session-buddy's gate is global (85%), so this wave *prepares* a curated 10-module set to locally exceed 85% line + 90% branch, demonstrating wave-1 satisfaction of the gate on a per-file basis. Wave-2 lifts the rest. The audit script and backlog doc remain measurement-only (they never *fail* the build); the global gate stays as-is.

## Goals

- **G1.** Generate `session-buddy/docs/coverage-backlog.md` (4-tier categorization) modeled on `mahavishnu/docs/coverage-backlog.md`, regeneratable from `coverage.json` in one shell command.
- **G2.** Add `session-buddy/scripts/run_coverage_audit.sh` modeled on crackerjack's: runs pytest --cov, prints a summary, **exits 0 regardless of pytest outcome** (does not fail the build), but surfaces pytest failures and collection errors in its output. Reuses existing `scripts/analyze_coverage.py` for the JSON→Markdown transform.
- **G3.** Wave-1 lifts 10 modules to **≥95% line coverage AND ≥90% branch coverage** each, picked by mixed-layer criteria (5 MCP-tool surface, 2 CLI, 2 core/orchestrator, 1 cross-module utility), with new focused unit tests in `tests/unit/`. Modules \<30% are deferred to wave-2.
- **G4.** Each wave-1 subagent runs an explicit sync/async pre-merge check (the crackerjack gotcha) using `inspect.iscoroutinefunction` + a blocking grep for sync event-loop bootstraps. **Sync wrappers are a blocker, not a warning.**
- **G5.** Pre-existing test pass-rate is preserved across the wave (no NEW failures on tests the wave didn't author). Any new failure is a blocker; rollback is per-commit, never blanket.
- **G6.** Completion report at `docs/archive/completion-reports/2026-08-03-session-buddy-coverage-wave1.md` records per-module before/after, `sync_async_hit_count` (defined), and any blockers hit.
- **G7.** Per-batch full-suite gate (no `-x`) is run after each of the 2 sub-batches and the delta against the baseline manifest is `0 new failures, 0 new errors`.

## Non-goals

- **N1.** Wave-1 does NOT change the global `--cov-fail-under=85` gate value (CLAUDE.md prescribes it). It does NOT raise a per-module gate either. The wave runs measurement-only and reports deltas against 85% per module. The gate remains globally failing until wave-2+.
- **N2.** No documentation coverage, MCP-tool-only coverage, or feature-flag coverage as separate sub-projects in this plan. Follow-up plans can layer those on top after wave-1 lands.
- **N3.** No unreviewed dead-code removal at 0%. A new `# pragma: no cover` line is acceptable **only** with a one-line justification comment that's reviewed by the wave-1 reviewer; unreviewed pragmas are auto-rejected.
- **N4.** No integration tests. Wave-1 is unit-only, mirroring mahavishnu's fan-out waves. MCP/CLI registration smokes are an exception — they're not integration but a `python -c "import"` plus `python -m session_buddy.cli <cmd> --help` exit-0 check.
- **N5.** Pyproject.toml `[tool.coverage]` config: only the **verification** that `branch = true` is present in `[tool.coverage.run]` is part of Phase 0; no other config changes.
- **N6.** No changes to the existing crackerjack-fallback or quality-scoring audit commits — those are stable on main. (The anchor SHA is re-verified at plan-start; specific commit IDs may move.)

## Selection criteria (for wave-1 module picks)

| Slot | Layer | Coverage cutoff |
|------|------------------------------------------|-----------------|
| 5 | `session_buddy/mcp/tools/**/*.py` | 30-94% |
| 2 | `session_buddy/cli.py`, `session_buddy/cli_with_modes.py` | 30-94% |
| 2 | `session_buddy/core/**`, `session_buddy/*coordinator*.py`, `session_buddy/*manager*.py`, `session_buddy/app_monitor.py`, `session_buddy/natural_scheduler.py` | 30-94% |
| 1 | `session_buddy/utils/**/*.py` (cross-module dependency) | 30-94% |

> **The concrete pick table from v1 is REMOVED.** Several paths in that table (`mcp/tools/.../usage_tools.py`, `coordinator.py`, `cli/team_cli.py`) do not exist in this repo. The implementation plan enumerates real candidates via a hard machine-checked Phase 0.5 step.

**Tie-breakers (applied in order) when more candidates than slots:**

1. **Recently touched in a known-buggy area** — if the candidate's diff appears in the crackerjack-fallback commit's changes (anchor SHA re-verified at plan start), prefer it (regression net needs to be solid).
1. **Smaller LOC** — easier to ship first as a wave-1 proof.
1. **Closer to 30% from below** — bigger visible delta per module.
1. **Skip modules > 600 LOC** in wave-1 — wave-2 candidate after calibration.
1. **Don't pick >400 lines of new test code per module** — cap lines-added so a single module doesn't dominate a subagent's brief.

**Anti-targets (Phase 0.5 pre-computes `docs/baselines/wave1-anti-targets.json`):**

- Any module whose existing test directory matches the **conftest pollution fingerprint**:
  > Modules whose test files do `sys.modules['session_buddy.<x>'] = <stub>` at module load time AND use `monkeypatch.setattr(..., raising=False)` against a string-form dotted path.
  > Detection grep: `grep -l "sys.modules\[" tests/unit/test_*.py` plus `grep -lE "monkeypatch\.setattr\([^,]+,[^,]+," tests/unit/test_*.py`.
- Modules explicitly whitelisted in `pyproject.toml [tool.coverage.report].exclude_also` (already excluded for a reason).
- `session_buddy/__init__.py` (not meaningful coverage target).
- Any module at \<30% current coverage (wave-2 candidate).

## Architecture & data flow

```
Phase 0 (sequential, gate)
┌──────────────────────────────────────────────────────────┐
│ Verify pyproject.toml [tool.coverage.run] branch = true  │
│   (add it if missing — only pyproject.toml change)        │
│                                                          │
│ uv run pytest tests/ --cov=session_buddy \               │
│     --cov-report=json:coverage.json \                     │
│     --cov-branch \                                        │
│     --tb=short -q --no-header                             │
│   ↓                                                      │
│ Capture every failure nodeid + signature                 │
│ Write docs/baselines/wave1-baseline.json:                │
│   { commit_sha, full_invocation,                         │
│     failure_signatures: [{nodeid, message}],             │
│     per_file_metrics: {path: {lines, branches, pct}} }  │
│   ↓                                                      │
│ scripts/analyze_coverage.py coverage.json \              │
│   --output docs/coverage-backlog.md                      │
│   ↓                                                      │
│ scripts/run_coverage_audit.sh            # meta-test     │
│   (must exit 0; FAIL must appear in output)               │
│   ↓                                                      │
│ commit phase 0                                           │
└──────────────────────────────────────────────────────────┘

Phase 0.5 (HARD pre-Phase-1 gate)
┌──────────────────────────────────────────────────────────┐
│ scripts/wave1_select_modules.py \                        │
│   --baseline docs/baselines/wave1-baseline.json \        │
│   --slots "5:mcp/tools,2:cli,2:core,1:utils" \           │
│   --anti-targets-json docs/baselines/wave1-anti-targets.json \
│   --output docs/baselines/wave1-selected.json            │
│ Exit non-zero if any slot under-filled or path missing   │
│   ↓                                                      │
│ commit phase 0.5                                         │
└──────────────────────────────────────────────────────────┘

Phase 1 batch X (sequential across batches, parallel within)
┌──────────────────────────────────────────────────────────┐
│ Each subagent:                                           │
│   Worktree at .worktrees/wave1-batch<X>-<module>/       │
│     Env: COVERAGE_FILE=.coverage.wave1.<name>            │
│     Only this subagent writes its coverage file          │
│     Subagent owns tests/unit/test_<module>.py ONLY       │
│     (plus fixture-mocking files scoped to that test)     │
│                                                          │
│ Subagent brief checks (a)(b)(c)(d)(e) — see Subagent brief│
│ Block on any failure to hit all five.                    │
│   ↓                                                      │
│ Merge subagent branch into wave-1 batch branch           │
│ Run isolated combine-coverage:                            │
│   coverage combine .worktrees/.../.coverage.wave1.* \    │
│     --keep                                           \   │
│     -a session_buddy -a paths=...                      \  │
│     → wave1-batch<X>.coverage.json                        │
│ Run full pytest (no -x) on merged branch:                │
│   Compare delta against wave1-baseline.json              │
│   Block on ANY new failure not in baseline               │
│   ↓                                                      │
│ commit phase 1 batch X                                   │
└──────────────────────────────────────────────────────────┘

Phase 1 batch 1b (after 1a passes gate)

Phase 2 (gate)
┌──────────────────────────────────────────────────────────┐
│ Re-run coverage.json on wave-1 merged branch             │
│ Compare to wave1-baseline.json → emit delta JSON         │
│ Regenerate docs/coverage-backlog.md                       │
│ Write docs/archive/completion-reports/                   │
│   2026-08-03-session-buddy-coverage-wave1.md             │
│ commit phase 2                                           │
└──────────────────────────────────────────────────────────┘
```

## Critical files

| File | Status | Owner |
|------|--------|-------|
| `pyproject.toml [tool.coverage.run]` | VERIFY (add `branch = true` if missing) | Phase 0 |
| `session-buddy/scripts/run_coverage_audit.sh` | NEW (Phase 0) | Phase 0 |
| `session-buddy/scripts/analyze_coverage.py` | REUSE / EXTEND (Phase 0) | Phase 0 |
| `session-buddy/scripts/verify_backlog.py` | NEW (Phase 0) | Phase 0 |
| `session-buddy/scripts/wave1_select_modules.py` | NEW (Phase 0.5) | Phase 0.5 |
| `session-buddy/docs/coverage-backlog.md` | NEW (Phase 0, regenerated Phase 2) | Phase 0 / Phase 2 |
| `session-buddy/docs/baselines/wave1-baseline.json` | NEW (Phase 0) | Phase 0 |
| `session-buddy/docs/baselines/wave1-anti-targets.json` | NEW (Phase 0.5) | Phase 0.5 |
| `session-buddy/docs/baselines/wave1-selected.json` | NEW (Phase 0.5) | Phase 0.5 |
| `session-buddy/docs/archive/completion-reports/2026-08-03-session-buddy-coverage-wave1.md` | NEW (Phase 2) | Phase 2 |
| `tests/unit/test_<selected-module>.py` ×10 | NEW per module (Phase 1, isolated worktree) | 10 subagents |

## Subagent brief template (each module gets this exact shape)

```markdown
## TASK BRIEF — Coverage lift for `session_buddy/<module>.py`

**GOAL:** ≥95% line + ≥90% branch coverage on this module,
verified against `docs/baselines/wave1-baseline.json` (full suite run, no -x).

**READ FIRST:**
- `session_buddy/<module>.py` (target)
- `tests/unit/test_<module>.py` if it exists
- `docs/baselines/wave1-baseline.json` (failure signatures you must not break)
- `docs/baselines/wave1-anti-targets.json` (modules to ignore)
- `.worktrees/wave1-batch<X>-<name>/COVERAGE_FILE` (.coverage.wave1.<name>)

**WORKTREE:** Operate in `.worktrees/wave1-batch<X>-<name>/`. Do not edit files
outside the worktree. Do not run pytest without setting
`COVERAGE_FILE=$PWD/.coverage.wave1.<name>` so you don't overwrite another agent's
coverage file.

**DO:**
1. Write or extend `tests/unit/test_<module>.py` with focused unit tests.
2. Cover public functions/methods AND unhappy paths.
3. MCP/CLI smoke if target is an MCP tool or CLI command: at minimum
   `python -c "from session_buddy.<path> import <X>; assert <X> is not None"`
   plus, for CLI, `python -m session_buddy.cli <cmd> --help` exit-0.

**MUST-RUN CHECKS before claiming DONE:**
(a) `uv run pytest tests/unit/test_<module>.py -v --no-header -q`
    All tests pass.
(b) `uv run pytest tests/ -q --no-header --tb=line \
       --cov=session_buddy.<module> --cov-branch \
       --cov-report=term:skip-covered`
    Line coverage ≥95% AND branch coverage ≥90% ON THE FULL SUITE REPORT.
(c) Sync/async defensiveness:
    (c1) `inspect.iscoroutinefunction(session_buddy.<module>.<fn>)` for every
         public function returning a coroutine — paste the assertion lines in
         REPORT.
    (c2) `grep -nE '(asyncio\.run|run_until_complete|get_event_loop\(\)\.run)' \
           tests/unit/test_<module>.py` → must be empty, OR each hit justified
         in REPORT with the line and reason.
    (c3) Every async function in the target appears in an `await` site under a
         test marked by `asyncio_mode = "auto"` or `@pytest.mark.asyncio`.
(d) Regression gate against baseline: `uv run pytest tests/ -q --no-header \
       --tb=no` → compare every failure nodeid against
       `docs/baselines/wave1-baseline.json::failure_signatures`.
    BLOCKED on any new failure not in the baseline.
(e) Public functions: every `def [a-z]` (excluding `_`-prefixed) in the target
    appears in the test file at least once with a corresponding test name.
    Grep `^def ` target vs test file; counts must match (modulo unused-public
    imports).

**CAPS:** If `wc -l session_buddy/<module>.py` > 600 → BLOCKED with line count;
do not split. If test-file line count > 400 added → BLOCKED with line count.

**PRAGMA:** No new `# pragma: no cover` is allowed without a one-line `# reason:`
comment that the wave-1 reviewer approves. Unreviewed pragmas are auto-rejected.

**REPORT:**
- File path, line count added, line + branch coverage before/after
- Number of tests, list of public functions covered (must satisfy check (e))
- (c1) assertion output, (c2) grep output, (c3) test-id-to-fn mapping
- (d) baseline-vs-current delta
- One-line concerns (if any)
```

## Error handling

**Pre-merge gate per module:** the five checks (a)(b)(c)(d)(e) above are hard blocks. If a subagent reports DONE without confirming all five, the task reviewer flips it to BLOCKED with the missing-check name.

**BLOCKED / lost-context state machine:**

| Subagent status | Wave-lead action |
|---|---|
| DONE with all five checks confirmed | Merge subagent branch into batch branch |
| DONE with check gaps in REPORT | Ask subagent to fill gaps; if no fix in one round, escalate |
| BLOCKED (anti-target, pollution, >600 LOC, >400 lines, missing file) | Re-pick module against same slot criteria; continue batch |
| BLOCKED, no replacement fits in slot | Drop to N-1 modules that batch; wave-1 still ships with \<10 if ≥5 |
| Lost context / subagent terminated | Re-dispatch with same brief + REPORT path; if still fails, re-pick |
| Severity flag (security / data loss / cross-tenant) | STOP, surface to user |

**Sync/async defensive smoke:** in addition to per-subagent check (c), Phase 2 runs a repo-wide grep as defense-in-depth: `grep -rnE "(asyncio\.run|run_until_complete|get_event_loop\(\)\.run)" tests/unit/test_*.py` (excluding `# reason:`-annotated lines). Any new occurrence in wave-1-authored files is a Critical row in the completion report.

**Audit script masking failures (regression-risk guardrail):**

- `run_coverage_audit.sh` MUST be written with `set +e` (not `set -e`) and `|| true` around pytest — no exception.
- The audit script ends with explicit `exit 0` regardless of pytest outcome.
- Pytest failures, collection errors, and asyncio warnings appear in the audit output stream (stderr).
- Phase 0 runs the audit script's **meta-test**: intentionally runs a failing `pytest tests/foo.py::test_nonexistent` and verifies the script still exits 0 and the FAIL line is in stdout. The meta-test is committed as a tiny driver at `scripts/run_coverage_audit.sh --self-test`.

**Coverage directory races:** per-subagent `COVERAGE_FILE=$PWD/.coverage.wave1.<name>` in their worktree. The `.coverage.wave1.*` files are tracked as test artifacts under `.coverage/` and only the wave-completion step (`scripts/combine_wave_coverage.py`) calls `coverage combine` to merge them into a single report. No two subagents ever write the same path.

**MCP/CLI smoke failures:** if a smoke fails, the subagent reports BLOCKED with the exact command and stderr. Wave lead re-picks.

## Testing strategy (this plan's deliverable IS tests)

Each wave-1 subagent owns one module and writes its tests using the patterns already in `tests/unit/`:

- Use the project pytest markers (`unit`, `integration`, `property`, `slow`) — do NOT invent new markers
- Async tests don't need `@pytest.mark.asyncio` because `asyncio_mode = "auto"`
- For tests touching module-level fixtures, prefer `tmp_path` and `monkeypatch` over global state
- For MCP-tool modules specifically: import the underlying tool, assert it's exposed on the FastMCP server's tool registry, then exercise the underlying logic at the boundary. **Don't** mock the registry itself — that's the smoke gate.

**Meta-tests at plan end:**

1. `bash scripts/run_coverage_audit.sh` exits 0, prints summary, FAIL lines visible if any
1. `bash scripts/run_coverage_audit.sh --self-test` exits 0 even when embedded pytest fails
1. Coverage diff against `wave1-baseline.json` shows `10 modules lifted`, `0 new failures`
1. Grep from "Sync/async defensive smoke" above returns 0 unannotated hits
1. Smoke tests for each of the 10 modules' public MCP/CLI surface succeed

## Verification at plan end

1. Phase 2 commits regenerate backlog with new percentages; delta JSON shows the 10 modules lifted with line + branch metrics
1. `python scripts/verify_backlog.py coverage.json docs/coverage-backlog.md` exits 0 (every row/tier/percentage matches coverage.json; no missing/dup/stale/mis-tiered entries)
1. Full `pytest -q` (no marker filter) — `current_failure_nodeids` is a SET: `current_failure_nodeids - baseline_failure_nodeids = ∅` (no NODEID shifts upward because wave-1 added tests; pass-rate ratio is irrelevant)
1. Smoke test: `bash scripts/run_coverage_audit.sh` exits 0 end-to-end
1. `bash scripts/run_coverage_audit.sh --self-test` exits 0
1. Completion report in `docs/archive/completion-reports/` contains per-module before/after, sync/async hit count (defined), baseline-delta JSON, and any blockers hit

## Rollback signal

- **Per-batch (5 modules):** the wave lead (NOT each subagent) runs ONE serialized full-suite run per merged batch and computes `current_failure_nodeids - baseline_failure_nodeids`. If that nodeid set is non-empty, the wave lead reviews the failure attribution. If wave-1 caused the failure, the responsible subagent's commit is reverted via `git revert <sha>` — never blanket across the batch — and a blocker-task is opened for wave-2. **Pass-rate-ratio is NOT the metric** (aggregate shifts whenever wave-1 adds tests; nodeid-PASS→FAIL shift is the only signal that matters).
- **Per-wave (10 modules):** if the **second** batch's gate fails, both batches are still on `feat/coverage-wave-1` (not yet merged to main). The branch is reverted via `git reset --hard` to the wave-start commit and a wave-1 retry plan is opened.
- **CLAUDE.md gate** is unchanged. Wave-2 must either lift enough modules to satisfy `--cov-fail-under=85` globally or surface a CLAUDE.md amendment.

## Open questions

### Q1 (peered from qa-strategist during v2 patch)

**Per-subagent full-suite race:** check (b) invokes the full pytest suite, and the original brief's check (d) was a second full-suite run. With 5 parallel subagents in a batch, that's ~10 concurrent full-suite runs competing for shared DB/CPU + the `coverage.json` race risk. **Action pending:** fold into v3 by moving (d) out of per-subagent briefs and into the per-batch wave-lead gate (one serialized run), and making (b) targeted to `tests/unit/test_<module>.py` with `--override-ini="addopts="` so global addopts don't pull in the full suite.

### Q2 (peered from qa-strategist during v2 patch)

**Selection minimum denominator:** the current coverage report has many 0-3 statement files. With `<80% cutoff` and `smaller LOC first`, the wave could land on trivial modules (1-statement 0%/100% lift) while leaving high-risk large low-coverage code untouched. **Action pending:** fold into v3 by adding a minimum-statements floor (e.g., ≥20 statements) plus explicit exclusion of trivial/entrypoint modules.

Both Q1 and Q2 are mechanical folds into the existing sections and don't change the design shape — they tighten criteria and serialize work. They will be applied before any plan execution against v2.

### Q3 (peered from qa-strategist during v2 patch)

**Per-batch lint/type/security gate missing from subagent brief:** the per-agent checks (a)-(e) cover pytest, coverage, async smoke, baseline diff, and public-function coverage — but never run `ruff`, `pyright`, or `crackerjack security/complexity` on the newly added test files. A wave-1 subagent can be DONE while introducing quality / type / security regressions in their new tests. **Action pending:** add a per-batch wave-lead step (alongside the (d)-replacement gate) that runs `ruff check`, `pyright`, and `crackerjack security --skip-hooks --comp` on each merged batch's diff. Defer to wave-2 if the infra cost is high.

## References

- `mahavishnu/docs/coverage-backlog.md` — reference format for tier categorization
- `mahavishnu` git history: `4deefabb`, `97d77b78`, `786d96cc` — three fan-out waves of similar shape
- `crackerjack/docs/TEST_COVERAGE_PLAN_CORE.md` (status: complete) — reference for plan-doc shape
- `crackerjack/scripts/run_coverage_audit.sh` — reference for audit script shape
- `crackerjack` git `5ecbe9ff` — sync/async gotcha precedent
- Memory: `conftest-sysmodules-pollution-pattern.md` (inlined as anti-target fingerprint above)
- `session_buddy/pyproject.toml` — `[tool.coverage]` config preserved as-is; only `branch = true` verification allowed
- `session_buddy/CLAUDE.md` lines 61, 71, 512 — `--cov-fail-under=85` gate that motivates this wave
- The crackerjack-fallback wave's anchor SHA — re-verified at plan start; it is `188d7fd0` at the time of this v2 but the spec uses anchors only where they survive plan start (CrackerjackFallback area tie-breaker)
