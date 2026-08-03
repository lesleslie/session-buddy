# Session-Buddy Coverage Improvement (Wave 1) — Design (v1)

**Date:** 2026-08-03 (v1)
**Owner:** Session-Buddy maintainers
**Repo:** `/Users/les/Projects/session-buddy`

## Context

Session-Buddy has pytest coverage configured (`pyproject.toml` `[tool.coverage]`) but currently has **no `--cov-fail-under` gate**, no canonical coverage report, and no wave plan. The crackerjack-fallback work that just shipped (merged at `188d7fd0` via `7b368963`) added ~3,089 insertions across 19 files but used its own per-module tests without contributing to any umbrella coverage metric.

Two sibling Bodai repos have established a coverage-recipe pattern that this spec ports:

- **`mahavishnu`** has `docs/coverage-backlog.md` (4-tier categorization: untested 0% / low 1-49% / partial 50-79% / good 80%+) generated from `coverage.xml`, plus three fan-out waves (`4deefabb` 10 modules → `97d77b78` 8 modules → `786d96cc` 8 modules), each using 5 parallel subagents targeting 100% per module — not raising the global gate.
- **`crackerjack`** has `docs/TEST_COVERAGE_PLAN_CORE.md` (status: complete) and `scripts/run_coverage_audit.sh` — runs full-coverage but does NOT fail the build. Its `5ecbe9ff` commit explicitly documents the gotcha: **sync test wrappers around async functions pass coverage but `coverage.py` doesn't see the async branches**.

This spec ports that recipe — coverage as observability, wave-by-wave lift, no global gate — to session-buddy.

## Goals

- **G1.** Generate `session-buddy/docs/coverage-backlog.md` (4-tier categorization) modeled on `mahavishnu/docs/coverage-backlog.md`, regeneratable from `coverage.json` in one shell command.
- **G2.** Add `session-buddy/scripts/run_coverage_audit.sh` modeled on crackerjack's: runs pytest --cov, prints a summary, exits 0 (does not fail the build).
- **G3.** Wave-1 lifts 10 modules to ≥95% line coverage each, picked by mixed-layer criteria (5 MCP-tool surface, 2 CLI, 2 core/orchestrator, 1 cross-module utility), with new focused unit tests in `tests/unit/`.
- **G4.** Each wave-1 subagent runs an explicit sync/async pre-merge check (the crackerjack gotcha), blocking themselves if they wrote a sync wrapper around a coroutine.
- **G5.** Pre-existing test pass-rate is preserved across the wave (no regressions on tests the wave didn't author). Any regression is reverted and a follow-up blocker-task is opened.
- **G6.** A short completion report at `docs/completion-reports/2026-08-03-session-buddy-coverage-wave1.md` records before/after per module, sync/async hit count, and any blockers hit.

## Non-goals

- **N1.** No `--cov-fail-under=80` global gate. Excluded per the recipe in both sibling repos (mahavishnu's gate is currently failing and not user-visible; gating pre-mature cuts iteration speed).
- **N2.** No documentation coverage, MCP-tool-only coverage, or feature-flag coverage as separate sub-projects in this plan. Follow-up plans can layer those on top after wave-1 lands.
- **N3.** No dead-code removal at 0%. A wave-N module that ships with explicit comment `pragma: no cover` is acceptable for this wave; tree-shaking is a separate cleanup plan.
- **N4.** No integration tests. Wave-1 is unit-only, mirroring mahavishnu's fan-out waves.
- **N5.** No changes to `pyproject.toml` `[tool.coverage]` configuration beyond verifying `data_file` and `omit` lists match (those already exist).
- **N6.** No changes to the existing crackerjack-fallback or quality-scoring audit commits — those are stable on main as of `188d7fd0`.

## Selection criteria (for wave-1 module picks)

| Slot | Layer                                    | Coverage cutoff |
|------|------------------------------------------|-----------------|
| 5    | `session_buddy/mcp/tools/**/*.py`        | <80%            |
| 2    | `session_buddy/cli*.py`, `session_buddy/cli/**` | <80%     |
| 2    | `session_buddy/core/**`, `session_buddy/*coordinator*.py`, `session_buddy/*manager*.py` | <80% |
| 1    | `session_buddy/utils/**/*.py` (cross-module dependency) | <80% |

**Tie-breakers when more candidates than slots:**
1. **Recently touched in a known-buggy area** — if it was in the recent crackerjack-fallback area, lift first (we just changed it; regression net needs to be solid).
2. **Smaller LOC** — easier to ship first as a wave-1 proof.
3. **Lower current %** — bigger visible delta per module.
4. **Skip modules > 600 LOC** in wave-1 — wave-2 candidate after calibration.

**Anti-targets (DO NOT pick):**
- Any module with the conftest `sys.modules` pollution fingerprint (memory: `conftest-sysmodules-pollution-pattern.md`) — picking one cascades test failures.
- Modules explicitly whitelisted in `pyproject.toml` `[tool.coverage.report].exclude_also` (already excluded for a reason).
- `session_buddy/__init__.py` (not meaningful coverage target).

**Concrete draft picks** (provisional — implementation plan re-validates against fresh `coverage.json`):

| #  | Slot | Candidate path                                  |
|----|------|-------------------------------------------------|
| 1  | MCP  | `mcp/tools/analytics/usage_tools.py` (or sibling) |
| 2  | MCP  | `mcp/tools/code/code_search_tools.py`           |
| 3  | MCP  | `mcp/tools/insights/insight_tools.py`           |
| 4  | MCP  | `mcp/tools/quality/quality_tools.py`            |
| 5  | MCP  | `mcp/tools/reflection/reflection_tools.py`      |
| 6  | CLI  | `cli.py` (or `cli_with_modes.py`)               |
| 7  | CLI  | `cli/team_cli.py` (or sibling `*_cli.py`)       |
| 8  | Core | `core/coordinator.py` (or sibling)              |
| 9  | Core | `app_monitor.py` (or `natural_scheduler.py`)    |
| 10 | Util | `utils/text_formatter.py` (currently 14%)       |

These are placeholders. The implementation plan picks the actual 10 by running `coverage.json`-driven selection against the criteria above.

## Architecture & data flow

```
Phase 0 (sequential, gate)
┌──────────────────────────────────────────────────────┐
│ uv run pytest --cov=session_buddy \                  │
│   --cov-report=json:coverage.json \                  │
│   --cov-report=term-missing:skip-covered             │
│     → coverage.json                                  │
│   ↓                                                  │
│ python scripts/coverage_backlog.py \                │
│   --coverage-json coverage.json \                    │
│   --output docs/coverage-backlog.md                  │
│   ↓                                                  │
│ commit phase 0 (audit script + backlog doc)          │
└──────────────────────────────────────────────────────┘

Phase 1 (2 sub-batches of 5, sequential)
┌──────────────────────────────────────────────────────┐
│ Batch 1a: dispatch 5 subagents in parallel           │
│   each owns ONE module                               │
│   subagent → tests/unit/test_<module>.py + ≥95% cov  │
│   ↓ (all 5 must hit DONE, not BLOCKED)               │
│ Batch 1b: dispatch 5 subagents in parallel           │
│   same shape                                         │
│   ↓                                                  │
│ uv run pytest --cov=session_buddy -q                 │
│   → verify no regression on full suite               │
└──────────────────────────────────────────────────────┘

Phase 2 (gate)
┌──────────────────────────────────────────────────────┐
│ Re-run coverage.json generation                     │
│ Regenerate docs/coverage-backlog.md                  │
│ Write docs/completion-reports/                       │
│   2026-08-03-session-buddy-coverage-wave1.md         │
│ Commit phase 2                                       │
└──────────────────────────────────────────────────────┘
```

**Subagent brief template** (each module gets this exact shape):

```markdown
## TASK BRIEF — Coverage lift for `session_buddy/<module>.py`

**GOAL:** ≥95% line coverage on this module.

**READ FIRST:**
- `session_buddy/<module>.py` (target)
- `tests/unit/test_<module>.py` if it exists
- `coverage.json` scoped to this file path

**DO:**
1. Write or extend `tests/unit/test_<module>.py` with focused unit tests.
2. Cover public functions/methods AND unhappy paths.

**MUST-RUN CHECKS before claiming DONE:**
(a) `uv run pytest tests/unit/test_<module>.py -v --no-header -q`
    All tests pass.
(b) `uv run pytest --cov=session_buddy.<module> --cov-report=term-missing`
    Coverage on this module is ≥95%.
(c) For any function that returns a coroutine, prove with a smoke check that
    it's actually async — not a sync wrapper using `asyncio.run()` (crackerjack
    wave-1 gotcha: `coverage.py` does not see async branches through sync wrappers).
(d) `uv run pytest tests/ -q --no-header -x` — full suite stays green.
    If a pre-existing test you didn't author fails, that's a regression, not yours.

**BLOCKED if:**
- (a) any of your tests fails
- (b) line coverage <95%
- (c) you wrote a sync wrapper around a coroutine
- (d) full suite regressed on a test you did not author

**REPORT:**
- File path, line count added, coverage before/after per coverage.py
- Number of tests, list of public functions covered
- Confirmation of (a)/(b)/(c)/(d)
- One-line concerns (if any)
```

## Critical files

| File | Status | Owner |
|------|--------|-------|
| `session-buddy/scripts/run_coverage_audit.sh` | NEW (Phase 0) | Phase 0 implementer |
| `session-buddy/scripts/coverage_backlog.py` | NEW (Phase 0) | Phase 0 implementer |
| `session-buddy/docs/coverage-backlog.md` | NEW (Phase 0, regenerated Phase 2) | Phase 0 / Phase 2 |
| `session-buddy/docs/completion-reports/2026-08-03-session-buddy-coverage-wave1.md` | NEW (Phase 2) | Phase 2 implementer |
| `tests/unit/test_<selected-module>.py` ×10 | NEW per module (Phase 1) | 10 subagents |

The 10 wave-1 modules are picked at execution time against the criteria above; the implementation plan produces their final paths based on a fresh `coverage.json` snapshot.

## Error handling

**Pre-merge gate per module:** the four checks (a)(b)(c)(d) in the subagent brief form a hard gate. If a subagent reports DONE without confirming (c), the task reviewer flips it to BLOCKED with a one-liner explaining the crackerjack-pattern gotcha.

**Sync/async defensive smoke:** the brief's check (c) is non-negotiable. As a backstop, the wave-completion verification (Phase 2) does a repo-wide grep `grep -rn "asyncio.run(" tests/unit/` and surfaces any new occurrences as a warning row in the completion report (not a blocker, but visible).

**Module conftest pollution:** if a chosen module's existing test file matches the `sys.modules` repointing fingerprint documented in `conftest-sysmodules-pollution-pattern.md`, the subagent excludes that module from the wave and reports BLOCKED with the rationale. The plan re-picks.

**Concurrency during coverage measurement:** `coverage.py`'s `parallel = true` is already configured (`pyproject.toml`) — preserved by Phase 0; not changed.

## Testing strategy (this plan's deliverable IS tests)

Each wave-1 subagent owns one module and writes its tests using the patterns already in `tests/unit/`:
- Use the project pytest markers (`unit`, `integration`, `property`, `slow`) — do NOT invent new markers
- Async tests don't need `@pytest.mark.asyncio` because `asyncio_mode = "auto"`
- For tests touching module-level fixtures, prefer `tmp_path` and `monkeypatch` over global state
- For the MCP-tool modules specifically: instantiate the underlying tool, mock its dependency surface (e.g. `CrackerjackIntegration`, `adapter_*`, etc.) at the boundary, assert the structured tool response

**Meta-test at plan end:** `bash scripts/run_coverage_audit.sh` runs end-to-end and exits 0. The wave-1 modules each show ≥95% in the post-wave `coverage.json`. The full suite (`pytest -q --no-header`) shows zero new failures attributable to wave-1.

## Verification at plan end

1. Phase 2 commits regenerate backlog with new percentages; diff against wave-start shows the 10 modules lifted
2. Full `pytest -q` (no marker filter, full session) stays green
3. Smoke test: `bash scripts/run_coverage_audit.sh` runs end-to-end and exits 0
4. Completion report contains per-module before/after, sync/async hit count, and any blockers hit

## Rollback signal

- Any wave-1 commit that breaks more than 3 pre-existing tests is auto-reverted via `git revert <sha>` and a blocker-task is opened for the next wave
- Backlog doc never undercounts — verified by reading top-5 entries against `coverage.json` (manual eyeball)

## Open questions

None at v1. Implementation plan execution may surface them; they get appended here as `Q1`/`Q2` blocks when they do.

## References

- `mahavishnu/docs/coverage-backlog.md` — reference format for tier categorization
- `mahavishnu` git history: `4deefabb`, `97d77b78`, `786d96cc` — three fan-out waves of similar shape
- `crackerjack/docs/TEST_COVERAGE_PLAN_CORE.md` (status: complete) — reference for plan-doc shape
- `crackerjack/scripts/run_coverage_audit.sh` — reference for audit script shape
- `crackerjack` git `5ecbe9ff` — sync/async gotcha precedent
- Memory: `conftest-sysmodules-pollution-pattern.md` — anti-target fingerprint
- `session_buddy/pyproject.toml` — `[tool.coverage]` config preserved as-is
