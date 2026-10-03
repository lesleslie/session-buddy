---
title: Ruff 0.16 Source Remediation
date: 2026-07-27
last_reviewed: 2026-07-27
status: draft
role: canonical
topic: ruff-016-source-remediation
scope: wide
followups:
  - Adopt Ruff 0.16's complete recommended rule set as a separate policy review
  - Revisit intentionally broad MCP boundary catches after production telemetry review
related:
  - 2026-07-27-quality-scoring-field-audit-design.md
---

# Ruff 0.16 Source Remediation — Design

## Context

`session-buddy` began resolving Ruff 0.16.0 after the Crackerjack dependency floor was
raised to `>=0.70.0`. Ruff 0.16 expanded its default lint set from the historical
59 rules to 413 rules. The existing source therefore began producing a large set of
new findings even though Ruff 0.15.22 reports a clean tree under the same project
configuration.

The live baseline on 2026-07-27 is 838 findings from:

```text
cd /Users/les/Projects/session-buddy
uv run ruff check session_buddy
```

The baseline is distributed across 158 source files. The largest rule families are:

| Rule | Count | Main concern |
|---|---:|---|
| BLE001 | 439 | broad catches at both real boundaries and accidental silent-failure sites |
| DTZ005/DTZ006/DTZ001 | 183 | naive timestamps and naive/aware arithmetic |
| TRY401 | 62 | exception text redundantly interpolated into `logger.exception` |
| EXE001 | 56 | shebangs on importable, non-executable modules |
| B023 | 32 | closures capture loop variables |
| RUF012 | 16 | mutable class-level defaults |
| Remaining reported rules | 50 | async subprocesses, logging, control flow, and exception taxonomy |

The working tree is already dirty on `main` with existing quality-scoring and related
changes. Those changes are user-owned context and must remain intact.

## Goals

- Make the live Ruff 0.16 check pass with zero findings.
- Keep Ruff 0.16; do not solve the incident by pinning or disabling the newly exposed
  rules.
- Preserve public CLI/MCP APIs, storage schemas, cross-service payload shapes, and
  graceful-degradation contracts unless a focused regression test documents an
  intentional correction.
- Make exception and timestamp behavior more explicit and observable.
- Add focused regression tests for changes that can alter runtime behavior.
- Keep the work reviewable through bounded waves and per-wave validation.

## Non-goals

- Selecting `ALL` and remediating every optional Ruff rule (the target is the live
  default set reported by `ruff check session_buddy`).
- Rewriting historical SQLite/DuckDB timestamp rows.
- Broad architectural refactors unrelated to a reported rule.
- Resetting, stashing, committing, pushing, or otherwise rewriting the existing dirty
  tree without explicit user instruction.
- Introducing a global `noqa` or weakening the Ruff configuration.

## Design invariants

1. Every wave has an explicit file manifest and a rule manifest.
2. No two mutation agents edit the same file concurrently.
3. A wave may not increase the total live Ruff count.
4. Existing dirty hunks are inspected before a target file is edited.
5. A retained broad catch must have a documented boundary rationale, observable logging,
   and a local `# noqa: BLE001`; blanket per-file or project-wide suppression is not
   allowed.
6. New datetime values representing instants are UTC-aware.
7. User-facing error strings may retain exception text, but diagnostic log calls must
   rely on structured exception information rather than redundant interpolation.

## Transformation policies

### Timezone policy

Use `datetime.UTC` for instants and `time.monotonic()` for elapsed durations:

- `datetime.now(UTC)` for current instants.
- `datetime.fromtimestamp(value, UTC)` for filesystem timestamps.
- `parse_utc_timestamp(value)` at boundaries that read legacy ISO strings. A naive
  legacy value is interpreted as UTC for backward compatibility; an aware value is
  converted to UTC.
- SQLite remains text-backed in this work. Writers emit UTC ISO strings and readers
  normalize before arithmetic or window comparisons.
- Hook execution durations use `time.monotonic()` so wall-clock changes cannot create
  negative or naive/aware subtraction errors.

The parser/normalizer lives in a small utility module with unit tests. It is imported
at explicit boundaries rather than replacing every `datetime.fromisoformat` call
blindly.

### Exception and logging policy

Classify each `except Exception` by the operation it protects:

- optional imports: `ImportError`, `ModuleNotFoundError`, `AttributeError`;
- parsing and validation: `ValueError`, `TypeError`, `KeyError`, JSON decode errors;
- filesystem/database/network calls: the relevant `OSError`, database, or client
  exception hierarchy;
- MCP/provider graceful-degradation boundaries: retain a broad catch only when the
  function's documented contract is to return a fallback. Log the exception and add a
  local rationale for the rule suppression.

For logging:

- `logger.exception("operation failed")` captures the active traceback. Do not append
  `{exc}` to that message (`TRY401`).
- Replace `.error(..., exc_info=True)` with `.exception(...)` (`G201`), preserving
  structured `extra` fields.
- `S110` and `S112` sites must either narrow the caught tuple or log at debug/warning
  level before continuing.
- Generic raised exceptions become module-specific exceptions (`TRY002`).
- `TRY004`, `TRY203`, and redundant handlers are fixed without changing caller-visible
  error contracts unless a test proves the old type was accidental.

### Structural policy

- Bind closure values with default arguments or use `functools.partial`; prefer direct
  dispatch over an inline lambda table when that makes the data flow clearer (`B023`).
- Use `ClassVar` for immutable lookup tables and `field(default_factory=...)` for
  instance-owned mutable state (`RUF012`).
- Move the embedding cache to a module-level cached function so the cache does not
  retain each `SkillsEmbeddingService` instance (`B019`). Keep `clear_cache()` as the
  public invalidation operation.
- Review `RUF034` against existing callers before changing sort behavior; a lint fix
  that changes ordering is a behavior change and needs a regression test.
- Apply `SIM102`, `SIM117`, `PLC0206`, `PLW0602`, and related mechanical rules only
  after checking evaluation order and side effects.

### Process and entry-point policy

- Keep shebangs only on true executable scripts and set their executable mode.
- Remove accidental shebangs from importable modules; `python -m` and console-script
  entry points do not require a module shebang.
- Keep sync subprocess helpers synchronous and call them from async functions via
  `asyncio.to_thread`, preserving timeout, `check`, and return-code behavior.
- Make every `subprocess.run` call explicit about `check=`.

## Wave plan

### Wave 0 — baseline and protection

Capture Ruff JSON, rule/file counts, dirty status, file hashes, and a binary diff
snapshot outside the repository. Run the focused baseline tests. No source changes.

### Wave 1 — time utility and timestamp boundaries

Add and test the UTC parser/normalizer. Convert datetime findings in domain batches:

1. adapters and analytics;
2. core and lifecycle;
3. storage, backends, and tools;
4. remaining package modules.

After each batch, run targeted DTZ checks, timestamp round-trip tests, and the live
Ruff count. Do not rewrite existing database rows.

### Wave 2 — logging mechanics and small exception taxonomy fixes

Fix `TRY401`, `G201`, `S110`, `S112`, `TRY002`, `TRY004`, and `TRY203` in bounded
package batches. Preserve user-facing error text separately from diagnostic logs.
Add or update tests for structured log fields and loop continuation.

### Wave 3 — broad-catch classification

Process `BLE001` by directory: adapters/backends, core/services, MCP/tools,
storage/LLM, and remaining utilities. For each catch, choose a narrow tuple or a
justified observable boundary. Review the complete residual `BLE001` list after each
batch; no blanket ignore is permitted.

### Wave 4 — closure, defaults, and mechanical semantics

Fix B023 in `advanced_search.py` and the S3 cleanup loop; convert RUF012 tables;
refactor the embedding cache; address PLC0206, SIM102, SIM117, PLW0602, and RUF034
with focused tests for any changed output/order.

### Wave 5 — async subprocesses and entry-point modes

Fix the four ASYNC221 findings using sync helpers plus `asyncio.to_thread`, add
explicit subprocess `check` values, and classify/remove/chmod the 56 EXE001 sites.
Run CLI/module import smoke tests and subprocess safety tests.

### Wave 6 — residual sweep and full gate

Run live Ruff and explicit rule sweeps, resolve any newly exposed findings, run the
focused and integration regression matrix, then run the canonical Crackerjack fast
hook. Review the final diff against the initial dirty snapshot.

## Testing and validation

### Per-wave checks

```text
uv run ruff check --select <wave-rules> <wave-files>
uv run ruff check session_buddy
uv run ruff format --check <wave-files>
uv run python -m compileall <wave-files>
uv run pytest <focused-tests> --no-cov -q
```

The live total must be monotonically non-increasing. Any file outside the wave
manifest or any focused-test regression stops the wave.

### Behavior regression net

- UTC helper tests: aware output, naive legacy parsing, conversion of non-UTC offsets.
- TTL tests across a DST boundary for serverless storage.
- SQLite/DuckDB timestamp window and round-trip tests.
- Cross-service manifest timestamp tests for Akosha/IPFS/cloud paths.
- Hook duration tests using monotonic timing.
- Exception fallback tests proving the loop continues and the failure is logged.
- Structured logging tests preserving `extra` fields.
- Advanced-search operator tests for every filter operator.
- S3 cleanup tests proving each object key is bound to its own deletion call.
- Embedding-cache lifecycle tests proving service instances are not retained.
- Workflow-metrics ordering tests for the corrected sort branch.
- Async subprocess and CLI `--help` smoke tests.

### Final checks

- `uv run ruff check session_buddy` exits zero.
- Every explicit reported rule sweep exits zero (including EXE001, BLE001, DTZ,
  TRY, B023, RUF012, SIM, G201, ASYNC221, PLW1510, and related codes).
- `uv run ruff format --check session_buddy` exits zero.
- Focused unit/integration/security suites pass.
- `uv run crackerjack run --no-config-update` (or the repository's configured fast
  equivalent) passes.
- Coverage remains at or above the existing ratchet.
- `python scripts/audit_orphans.py` reports no newly orphaned production symbols.
- `python -m session_buddy --help` and the installed console script help succeed.

## Rollback signal and handling

Stop at the current wave if:

- Ruff findings increase;
- a focused test fails;
- a public signature, storage shape, or cross-service payload changes unexpectedly;
- a dirty hunk is overlapped without review; or
- an exception fallback becomes observable to callers.

For clean files, restore from the per-wave copy. For files that were already dirty,
do not auto-restore; create a three-way diff and ask the user before changing or
reverting any hunk.

## Integration Contract

- **Triggered from:** the session-buddy Ruff/Crackerjack fast hook.
- **Returns to / updates:** session-buddy source modules, focused regression tests,
  and the Ruff-compatible quality gate; no intentional public API or schema changes.
- **Demonstrable by:** zero live Ruff findings, passing focused tests, and the final
  Crackerjack fast hook.
- **Rollback signal:** any wave increases findings, changes a public contract, fails
  focused tests, or overlaps an unreviewed dirty hunk.
- **Observability added:** structured exception logs, explicit wave counts, and
  regression coverage for timezone, async, fallback, and cache behavior.

## Acceptance criteria

1. Live Ruff 0.16 reports zero findings for `session_buddy`.
2. No project-wide or directory-wide rule suppression is added.
3. Every retained broad catch has a local rationale and observable logging.
4. All new timestamp instants are UTC-aware and legacy timestamp reads are normalized
   before comparison.
5. Public CLI/MCP signatures and persisted schema shapes remain compatible.
6. Focused regression tests and the final fast hook pass.
7. Existing dirty changes remain present and unmodified except where the user-approved
   source remediation explicitly overlaps them.
8. The final report documents rule-count deltas, touched files, tests, and any
   intentionally retained local `noqa` comments.
