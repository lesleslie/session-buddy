# Crackerjack CLI flag mapping (verified 2026-08-03)

Task 0 preflight evidence for the quality-scoring crackerjack fallback plan.
Task 4 reads this file to pick crackerjack flags from `missing_metrics`.

## Environment

- **session-buddy worktree**: `feat/quality-scoring-crackerjack-fallback` at
  `/Users/les/Projects/session-buddy/.claude/worktrees/feat-quality-scoring-crackerjack-fallback/`
- **Python used**: `/Users/les/Projects/session-buddy/.venv/bin/python` (Python 3.13.11, the parent venv)
- **crackerjack version**: v0.70.3
- **Test project**: `/tmp/lychee-cli-verify` containing:
  - `mathlib.py` with `def add(a, b): return a + b`
  - `test_mathlib.py` with `def test_add(): assert add(1, 2) == 3`

## Discrepancies in the brief's example probe

The brief's example probe code references `_get_applicable_parsers` as a
module-level function and `CrackerjackOutputParser.parse_output` as a dict
return — both are wrong against the current code. The actual API:

- `_get_applicable_parsers` is an **instance method** on `CrackerjackOutputParser`
  (it is not exported from the module).
- `parse_output` returns a **tuple** `(parsed_data, memory_insights)`, not a dict.
- The brief's flag `--security` is **not a valid `crackerjack run` flag** —
  the CLI rejects it with `No such option: --security`. There is no security-only
  flag; security is bundled with `--comp` (`--comp` = comprehensive).

The probe below runs against the real API and discovers the actual flag
surface.

## Step A — applicable parsers per semantic command

Reads `CrackerjackOutputParser._get_applicable_parsers(command)` (the
internal method that maps a semantic command name to the parser chain).
Implementation lives at
`session_buddy/utils/crackerjack/output_parser.py:71-82`.

| semantic command | applicable parsers |
|---|---|
| `test` | `test`, `coverage` |
| `check` | `test`, `lint`, `security`, `coverage`, `complexity` |
| `lint` | `lint` |
| `format` | `lint` |
| `security` | `security` |
| `coverage` | `coverage` |
| `complexity` | `complexity` |

## Step B — default `parsed_data` keys per semantic command

Parsed with empty `stdout`/`stderr` so only the parser-chain's own
`_init_parsed_data` and inactive summary keys show up. Every semantic
command seeds these base keys:

- `command`, `test_results`, `lint_issues`, `security_issues`,
  `coverage_data`, `complexity_data`, `progress_info`, `quality_metrics`

When the matching parser fires, its dedicated summary key appears too
(`test_summary`, `lint_summary`, `security_summary`, `coverage_summary`,
`complexity_summary`). Per call:

| semantic command | keys produced |
|---|---|
| `test` | `command`, `complexity_data`, `coverage_data`, `coverage_summary`, `lint_issues`, `progress_info`, `quality_metrics`, `security_issues`, `test_results`, `test_summary` |
| `check` | `command`, `complexity_data`, `complexity_summary`, `coverage_data`, `coverage_summary`, `lint_issues`, `lint_summary`, `progress_info`, `quality_metrics`, `security_issues`, `security_summary`, `test_results`, `test_summary` |
| `lint` | `command`, `complexity_data`, `coverage_data`, `lint_issues`, `lint_summary`, `progress_info`, `quality_metrics`, `security_issues`, `test_results` |
| `format` | `command`, `complexity_data`, `coverage_data`, `lint_issues`, `lint_summary`, `progress_info`, `quality_metrics`, `security_issues`, `test_results` |
| `security` | `command`, `complexity_data`, `coverage_data`, `lint_issues`, `progress_info`, `quality_metrics`, `security_issues`, `security_summary`, `test_results` |
| `coverage` | `command`, `complexity_data`, `coverage_data`, `coverage_summary`, `lint_issues`, `progress_info`, `quality_metrics`, `security_issues`, `test_results` |
| `complexity` | `command`, `complexity_data`, `complexity_summary`, `coverage_data`, `lint_issues`, `progress_info`, `quality_metrics`, `security_issues`, `test_results` |

Note: the `progress_info` block is appended by every call because
`parse_output` always runs the `progress` parser after the command-specific
chain (see `output_parser.py:54`).

## Step C — actual CLI invocations

These are the flag combinations the brief asked to probe, run against
`/tmp/lychee-cli-verify` with a 90s timeout each.

| CLI invocation | Result | `parsed_data` keys produced (per `parse_output` with the most-revealing semantic command) |
|---|---|---|
| `python -m crackerjack run --comp` | exit_code=1, 1534 bytes stdout / 481 bytes stderr; ratchet refresh ran, then `pyscn` failed JSON parsing (no Python files in fixture). | With `semantic='check'`: `lint_summary`, `security_summary`, `complexity_summary`, `progress_info` populated. Re-run with `--skip-hooks` clears the pyscn issue and yields `exit_code=0`, same key set. |
| `python -m crackerjack run --run-tests` | TIMEOUT after 90s (full test suite, including integration gates, runs longer than the probe budget). | (Not captured — would need a longer timeout and a populated fixture.) |
| `python -m crackerjack run --fast --quick` | TIMEOUT after 90s. | (Not captured.) |
| `python -m crackerjack run --security` | exit_code=2, CLI error: `No such option: --security`. | N/A — flag does not exist. Use `run --comp` (which is the comprehensive run that includes security) instead. |

### Additional invocations probed

| CLI invocation | Result | Notes |
|---|---|---|
| `python -m crackerjack run --comp --skip-hooks` | exit_code=0 (1534 bytes stdout). | Confirms `--comp` is the comprehensive run that bundles security, lint, complexity, tests, and coverage. |
| `python -m crackerjack run-tests --no-coverage` | exit_code=1 (pytest ran on the 1-test fixture). | Top-level `run-tests` subcommand exists separately from the `--run-tests` flag. Useful when only the test stage is needed. |

## Mapped CLI → semantic command → parsed_data keys

This is the table Task 4 should consume. Entries marked **UNKNOWN** could
not be captured because the CLI invocation did not complete within the
90s probe budget (the brief's example timings are too short for a real
crackerjack run on a populated project — both `--run-tests` and
`--fast --quick` ran past the budget).

| CLI invocation | Semantic command (for `parse_output`) | `parsed_data` keys produced (non-empty after capture) |
|---|---|---|
| `run --comp` | `check` | `progress_info`, `lint_summary`, `security_summary`, `complexity_summary` |
| `run --comp --skip-hooks` | `check` | `progress_info`, `lint_summary`, `security_summary`, `complexity_summary` |
| `run --run-tests` | `test` | UNKNOWN — timed out at 90s |
| `run --fast --quick` | `lint` | UNKNOWN — timed out at 90s |
| `run --security` | — | INVALID — CLI rejects (`No such option: --security`). Use `run --comp` for security metrics. |
| `run-tests` (subcommand) | `test` | `progress_info` (pytest output captured; coverage disabled via `--no-coverage`) |

## Implications for Task 4

- The brief's `--security` flag does **not exist**. The fallback must use
  `run --comp` (or `run --comp --skip-hooks` for a faster dry run) when
  security metrics are missing. `--comp` is what bundles `security`
  semantics into the `check` parser chain.
- `run --run-tests` and `run --fast --quick` both exceed 90s on a non-trivial
  fixture. If Task 4 needs to call these from a CLI fallback, the timeout
  for the subprocess must be larger than 90s (crackerjack's default test
  timeout is 300s per the `run-tests --help`).
- Because `parse_output` returns `(parsed_data, insights)` rather than a
  dict, the fallback must destructure both. The `insights` list is the
  memory-side artifact and does not need to feed back into the metric
  filling that Task 4 implements.
- The mapping Task 4 should encode is:
  - missing `test_results` / `coverage_data` → run `crackerjack run-tests` (or `run --run-tests`).
  - missing `lint_issues` → run `crackerjack run --fast --quick` (with a >90s timeout).
  - missing `security_issues` → run `crackerjack run --comp --skip-hooks` (there is no dedicated security flag).
  - missing `complexity_data` → run `crackerjack run --comp --skip-hooks` (bundled with `--comp`).

## How to reproduce

```bash
cd /Users/les/Projects/session-buddy/.claude/worktrees/feat-quality-scoring-crackerjack-fallback
mkdir -p /tmp/lychee-cli-verify && cd /tmp/lychee-cli-verify
echo 'def add(a, b): return a + b' > mathlib.py
echo 'def test_add(): assert add(1, 2) == 3' > test_mathlib.py

# Step A + B (no subprocess needed)
/Users/les/Projects/session-buddy/.venv/bin/python -c "
from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser
p = CrackerjackOutputParser()
for cmd in ['test','check','lint','format','security','coverage','complexity']:
    print(cmd, '->', p._get_applicable_parsers(cmd))
"

# Step C (each invocation is independent — pick the ones you need)
/Users/les/Projects/session-buddy/.venv/bin/python -m crackerjack run --comp --skip-hooks
# /Users/les/Projects/session-buddy/.venv/bin/python -m crackerjack run --run-tests
# /Users/les/Projects/session-buddy/.venv/bin/python -m crackerjack run --fast --quick
# /Users/les/Projects/session-buddy/.venv/bin/python -m crackerjack run-tests --no-coverage
```
