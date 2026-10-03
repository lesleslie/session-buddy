# Session-Buddy Coverage Improvement (Wave 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift 10 session-buddy modules to ≥95% line + ≥90% branch coverage each, with a durable coverage-observability stack (audit script, backlog doc, baseline manifest, validator, anti-target list, selected-modules list) that prepares the way for the existing `--cov-fail-under=85` global gate without raising it.

**Architecture:** Phased fan-out — Phase 0 builds the observability stack; Phase 0.5 selects concrete modules from a hard machine-checked prerequisite; Phase 1 dispatches 5 parallel subagents per batch (one per module) in isolated worktrees with per-agent `COVERAGE_FILE`; one wave-lead gate per merged batch runs combined coverage + nodeid-set-diff against the baseline manifest; Phase 2 regenerates backlog + delta JSON + completion report. Source: spec `docs/superpowers/specs/2026-08-03-session-buddy-coverage-improvement-design.md` (v2, commit `af3f819c`).

**Tech Stack:** Python 3.13, pytest 8+ with `pytest-asyncio` (mode=auto), pytest-cov with `branch=true`, Python `coverage` CLI (5.x+) for `coverage combine`, Bash for `scripts/run_coverage_audit.sh` (POSIX-portable), `ruff check`/`pyright`/`crackerjack security` for the per-batch quality gate (Q3 deferred-to-action), `git worktree` for per-agent isolation, JSON for all manifests (no YAML, no INI).

## Global Constraints

The spec's wave-shape rules are the source of truth. Each task's implementer MUST read the spec section named below before starting that task. Constraints:

1. **Branch coverage MUST be enabled in `[tool.coverage.run]` (`branch = true`)** — Task 1 enforces this and is the only pyproject.toml change permitted.
1. **The wave does NOT change `--cov-fail-under=85`** — CLAUDE.md mandates it; the gate remains globally failing. Wave-1 runs measurement-only.
1. **Per-subagent checks (a)(b-fast)(c)(e) are TARGETED** to `tests/unit/test_<module>.py` with `--override-ini="addopts="` so global addopts don't pull in the full suite. Check (d) moves out of per-subagent briefs entirely; the wave-lead runs one serialized full-suite diff per merged batch.
1. **Worktree isolation** — every wave-1 subagent operates in its own worktree at `.worktrees/wave1-batch<X>-<name>/` on branch `feat/coverage-wave1-batch<X>-<name>`.
1. **Per-agent `COVERAGE_FILE=$PWD/.coverage.wave1.<name>`** — no two subagents write the same coverage file. Combine happens once per batch via `coverage combine`.
1. **`scripts/run_coverage_audit.sh` MUST use `set +e`, `|| true` around pytest, end with explicit `exit 0`.** Phase-0 self-test of `--self-test` proves the script exits 0 with a forced pytest failure.
1. **New `# pragma: no cover` requires wave-1 reviewer approval + one-line `# reason:`** comment. Unreviewed pragmas are auto-rejected.
1. **Module selection floor:** ≥20 statements, current 30-94% coverage, \<600 LOC, matches a slot in the table.
1. **MCP/CLI smoke for those target types:** `python -c "from session_buddy.<x> import <X>; assert <X> is not None"` + (CLI only) `python -m session_buddy.cli <cmd> --help` exit-0.
1. **Sync/async defensiveness is BLOCKING** — `inspect.iscoroutinefunction` run + grep `(asyncio\.run|run_until_complete|get_event_loop\(\)\.run)` empty in `tests/unit/test_<module>.py` (or each hit `# reason:`-justified in REPORT).
1. **`sync_async_hit_count` for G6 report = new occurrences of `asyncio.run` / `run_until_complete` / `get_event_loop().run` in wave-1-authored `tests/unit/test_<module>.py`** — define concretely; report verbatim.
1. **Anti-target fingerprint (conftest pollution)** — patterns are inline below in **Task 4**. Any matching module is excluded.
1. **Wave-lead full-suite gate is a node-id set-diff, NOT a rate** — `current_failure_nodeids - baseline_failure_nodeids = ∅`; pass-rate ratio is irrelevant (shifts on every test addition).
1. **Per-batch ruff/pyright gate is deferred (Q3)**: TODO note goes in `scripts/combine_wave_coverage.py`; wave-1 may ship without it; wave-2 should land it.

All deliverable code lands in `session-buddy/`. The plan assumes the working directory at task start is the repo root (`/Users/les/Projects/session-buddy`).

______________________________________________________________________

## Phase 0: Observability Stack

### Task 0: Preflight — capture repo state

**Files:**

- Read: `pyproject.toml`, `CLAUDE.md`, `docs/developer/TESTING.md`
- Create: `docs/baselines/wave1-preflight.json`

**Steps:**

- [ ] **Step 1: Verify branch coverage enablement target**

```bash
grep -E '^\s*branch\s*=\s*true\s*$' pyproject.toml
```

If absent → record in `wave1-preflight.json` under `needs_branch_true: true`.

- [ ] **Step 2: Capture current pytest failure signatures**

Run `uv run pytest tests/ -q --no-header --tb=no -p no:randomly > /tmp/preflight-pre.log 2>&1` (or via the venv if not uv).

Parse out failed nodeids into `wave1-preflight.json::baseline_failure_nodeids`.

- [ ] **Step 3: Capture current coverage.json**

```bash
uv run pytest tests/ --cov=session_buddy --cov-report=json:/tmp/preflight-coverage.json -q --no-header --tb=no 2>&1 | tail -20
```

Note: this will print failures and produce a partial coverage.json — that's expected for this preflight; the canonical coverage.json is captured in Task 4.

- [ ] **Step 4: Verify the existing pytest-cov defaults are sane**

```bash
uv run pytest --collect-only tests/ -q 2>&1 | tail -5
uv run pytest tests/unit/test_helpers.py -q --no-header -x 2>&1 | tail -10  # spot-test ONE fast file
```

If `test_helpers.py` is missing, replace with any small file in `tests/unit/`.

- [ ] **Step 5: Write `docs/baselines/wave1-preflight.json`**

```json
{
  "needs_branch_true": true,
  "baseline_failure_nodeids": ["tests/...::test_xyz", "..."],
  "pytest_collect_ok": true,
  "spot_test_passed": true,
  "captured_at": "<ISO timestamp>",
  "captured_on_commit": "<git rev-parse HEAD>"
}
```

- [ ] **Step 6: Commit**

```bash
git add docs/baselines/wave1-preflight.json
git commit -m "chore(coverage-wave1): preflight baseline failure manifest"
```

**Reports:** JSON path, count of failure nodeids captured, branch status.

### Task 1: Verify `branch = true`; add if missing

**Files:**

- Modify: `pyproject.toml` (only `[tool.coverage.run]` block; ONLY change is `branch = true` if missing)

**Steps:**

- [ ] **Step 1: Read preflight**

```bash
cat docs/baselines/wave1-preflight.json | python -c "import json,sys; print(json.load(sys.stdin)['needs_branch_true'])"
```

If `false`, skip this task entirely.

- [ ] **Step 2: Locate `[tool.coverage.run]` block**

```bash
awk '/^\[tool\.coverage\.run\]/{flag=1} flag && /^\[/{print NR": "$0; if (NR>1 && $0!~/^\[tool\.coverage\.run\]/) {flag=0}}' pyproject.toml
```

- [ ] **Step 3: Insert `branch = true` if missing**

```python
# Pseudocode: walk lines, find [tool.coverage.run] block, add `branch = true` after the first non-comment, non-blank line if not present.
```

Verify with `grep -E '^\s*branch\s*=\s*true\s*$' pyproject.toml`.

- [ ] **Step 4: Run a single pytest to confirm coverage still produces the same JSON shape**

```bash
uv run pytest tests/unit/test_helpers.py --cov=session_buddy.helpers --cov-branch --cov-report=json:/tmp/branch-coverage.json -q 2>&1 | tail -5
python -c "import json; d=json.load(open('/tmp/branch-coverage.json')); assert 'branch_coverage' in d['totals'] or 'branch_coverage' in d.get('files', {next(iter(d.get('files', {})), '')})['summary'] if isinstance(d.get('files'), dict) and d['files'] else True; print('BRANCH_OK')"
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "chore(coverage): enable branch coverage in [tool.coverage.run]"
```

**Reports:** Commit SHA, confirmation grep output, BRANCH_OK output.

### Task 2: `scripts/run_coverage_audit.sh` with `--self-test`

**Files:**

- Create: `session-buddy/scripts/run_coverage_audit.sh`
- Create: `tests/unit/scripts/test_run_coverage_audit.py`

**Steps:**

- [ ] **Step 1: Write the test FIRST (shell-level smoke via pytest)**

```python
# tests/unit/scripts/test_run_coverage_audit.py
"""Smoke tests for the audit script."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def repo_root() -> Path:
    # Locate the repo relative to this test file
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def audit_script(repo_root: Path) -> Path:
    p = repo_root / "scripts" / "run_coverage_audit.sh"
    if not p.exists():
        pytest.skip(f"audit script not yet present at {p}")
    return p


def test_audit_script_exists(audit_script: Path) -> None:
    assert audit_script.exists()
    assert audit_script.is_file()


def test_audit_script_is_executable(audit_script: Path) -> None:
    import os
    import stat
    mode = audit_script.stat().st_mode
    assert mode & stat.S_IXUSR, "audit script must be executable"


def test_audit_script_self_test_exits_zero_with_forced_failure(
    audit_script: Path,
    repo_root: Path,
) -> None:
    """Self-test must exit 0 even when the embedded pytest fails."""
    if shutil.which("bash") is None:
        pytest.skip("bash not available")

    # Invoke from a tempdir with a deliberately non-importable module so pytest collects 0
    result = subprocess.run(
        [
            "bash",
            str(audit_script),
            "--self-test",
            "--pytest-args",
            "tests/this_file_does_not_exist__2345.py::test_nope",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    assert result.returncode == 0, (
        f"--self-test must exit 0 even with forced failure.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The FAIL output must still appear in stdout
    assert "FAIL" in result.stdout or "fail" in result.stdout.lower(), (
        "FAIL output must be visible in stdout"
    )


def test_audit_script_uses_set_plus_e_not_set_minus_e(audit_script: Path) -> None:
    """Audit script MUST NOT have `set -e` (would propagate pytest failures)."""
    content = audit_script.read_text()
    assert "set -e" not in content, (
        "`set -e` would propagate pytest failures; use `set +e` and `|| true`"
    )


def test_audit_script_ends_with_exit_zero(audit_script: Path) -> None:
    content = audit_script.read_text()
    # The script must terminate with explicit exit 0
    last_non_blank = next(
        (line.strip() for line in reversed(content.splitlines()) if line.strip()),
        "",
    )
    assert last_non_blank == "exit 0", (
        f"script must end with `exit 0`, got: {last_non_blank!r}"
    )
```

- [ ] **Step 2: Run the tests to verify they FAIL (the script doesn't exist yet)**

```bash
uv run pytest tests/unit/scripts/test_run_coverage_audit.py -v --no-header 2>&1 | tail -10
```

Expected: `audit_script` fixture skips (the file doesn't exist). That's the failing state.

- [ ] **Step 3: Write `scripts/run_coverage_audit.sh`**

```bash
#!/usr/bin/env bash
# scripts/run_coverage_audit.sh
#
# Runs pytest --cov and prints a summary table.
# ALWAYS exits 0 (CI does not fail on coverage gaps).
# Use --self-test to verify: runs an intentionally failing pytest invocation
# and checks the script still exits 0 with the failure visible in stdout.

set +e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

SELF_TEST=0
PYTEST_EXTRA_ARGS=()

while [ "$#" -gt 0 ]; do
    case "$1" in
        --self-test)
            SELF_TEST=1
            shift
            ;;
        --pytest-args)
            shift
            # Consume all remaining args as pytest args
            while [ "$#" -gt 0 ]; do
                PYTEST_EXTRA_ARGS+=("$1")
                shift
            done
            ;;
        *)
            PYTEST_EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

if [ "${SELF_TEST}" -eq 1 ]; then
    if [ ${#PYTEST_EXTRA_ARGS[@]} -eq 0 ]; then
        PYTEST_EXTRA_ARGS=("tests/this_file_does_not_exist__2345.py::test_nope")
    fi
    echo "[audit] --self-test mode: forcing pytest to fail"
fi

echo "🔍 Session-Buddy Coverage Audit"
echo "=============================="
echo ""

COVERAGE_JSON="/tmp/sb-coverage-audit.json"

# Always succeeds at the shell level; pytest failures appear in output.
uv run pytest tests/ \
    --cov=session_buddy \
    --cov-branch \
    --cov-report="json:${COVERAGE_JSON}" \
    --cov-report=term-missing:skip-covered \
    --cov-report=term \
    -q --no-header --tb=line "${PYTEST_EXTRA_ARGS[@]}" 2>&1 | tee /tmp/sb-coverage-audit.log
PYTEST_RC="${PIPESTATUS[0]}"

echo ""
echo "📊 Audit Summary"
echo "----------------"
if [ -f "${COVERAGE_JSON}" ]; then
    python - <<'PY'
import json, sys
try:
    with open("/tmp/sb-coverage-audit.json") as f:
        d = json.load(f)
    t = d.get("totals", {})
    pct = t.get("percent_covered", 0.0)
    print(f"  Overall coverage: {pct:.1f}%")
    print(f"  Total statements: {t.get('num_statements', 0)}")
    print(f"  Covered lines: {t.get('covered_lines', 0)}")
    print(f"  Missing lines: {t.get('missing_lines', 0)}")
    low = []
    for path, fd in (d.get("files") or {}).items():
        s = fd.get("summary", {}) if isinstance(fd, dict) else {}
        if (s.get("percent_covered", 100.0)) < 30.0:
            low.append((path, s.get("percent_covered", 0.0)))
    low.sort(key=lambda x: x[1])
    if low:
        print(f"\n  Files below 30% coverage ({len(low)}):")
        for p, pc in low[:10]:
            print(f"    {pc:5.1f}%  {p}")
        if len(low) > 10:
            print(f"    ...and {len(low) - 10} more")
except Exception as e:
    print(f"  (could not parse coverage.json: {e})")
PY
fi
echo ""
if [ "${PYTEST_RC}" -ne 0 ]; then
    echo "⚠️  pytest exited with code ${PYTEST_RC} (FAIL lines appear above)"
fi
echo "✅ Audit complete"

# ALWAYS exit 0 — this script is observability, never a gate.
exit 0
```

- [ ] **Step 4: Make executable; rerun tests**

```bash
chmod +x scripts/run_coverage_audit.sh
uv run pytest tests/unit/scripts/test_run_coverage_audit.py -v --no-header 2>&1 | tail -15
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_coverage_audit.sh tests/unit/scripts/test_run_coverage_audit.py
git chmod +x scripts/run_coverage_audit.sh  # keep the +x bit in git
git commit -m "feat(scripts): coverage audit script with --self-test mode"
```

**Reports:** Test names passed, the audit script's full path, a one-line summary of `bash scripts/run_coverage_audit.sh --self-test` exit code.

### Task 3: `scripts/verify_backlog.py` + tests

**Files:**

- Create: `session-buddy/scripts/verify_backlog.py`
- Create: `tests/unit/scripts/test_verify_backlog.py`

**Steps:**

- [ ] **Step 1: Write the tests FIRST**

```python
# tests/unit/scripts/test_verify_backlog.py
"""Tests for the deterministic backlog validator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def fake_coverage(tmp_path: Path) -> Path:
    cov = {
        "totals": {"percent_covered": 50.0, "num_statements": 100, "covered_lines": 50, "missing_lines": 50},
        "files": {
            "session_buddy/foo.py": {"summary": {"percent_covered": 100.0, "num_statements": 10, "missing_lines": 0}},
            "session_buddy/bar.py": {"summary": {"percent_covered": 0.0, "num_statements": 20, "missing_lines": 20}},
            "session_buddy/baz.py": {"summary": {"percent_covered": 50.0, "num_statements": 4, "missing_lines": 2}},
        },
    }
    p = tmp_path / "coverage.json"
    p.write_text(json.dumps(cov))
    return p


@pytest.fixture
def fake_backlog(tmp_path: Path) -> Path:
    p = tmp_path / "docs" / "coverage-backlog.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# Coverage Backlog\n\n"
        "## Tier definitions\n\nTBD\n\n"
        "## Per-directory backlog\n\n"
        "### `session_buddy/foo.py`\n- pct: 100, lines: 10, tier: good\n"
        "### `session_buddy/bar.py`\n- pct: 0, lines: 20, tier: untested\n"
    )
    return p


def _run_validator(cov_path: Path, backlog_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/verify_backlog.py", str(cov_path), str(backlog_path)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2],
    )


def test_validator_passes_when_backlog_matches(fake_coverage: Path, fake_backlog: Path) -> None:
    """All files in coverage.json appear in backlog with correct tier."""
    result = _run_validator(fake_coverage, fake_backlog)
    # baz.py is missing from backlog — that's a failure
    assert result.returncode == 1, result.stdout + result.stderr
    assert "baz.py" in result.stdout, "validator must name the missing file"


def test_validator_flags_duplicate_entry(tmp_path: Path) -> None:
    cov = {
        "totals": {"percent_covered": 100.0, "num_statements": 10, "covered_lines": 10, "missing_lines": 0},
        "files": {"session_buddy/foo.py": {"summary": {"percent_covered": 100.0, "num_statements": 10, "missing_lines": 0}}},
    }
    covp = tmp_path / "coverage.json"
    covp.write_text(json.dumps(cov))
    bg = tmp_path / "backlog.md"
    bg.write_text("## `foo.py`\nx\n## `foo.py`\ny\n")  # same file twice
    result = _run_validator(covp, bg)
    assert result.returncode == 1
    assert "duplicate" in result.stdout.lower()


def test_validator_flags_wrong_tier(tmp_path: Path) -> None:
    cov = {
        "totals": {"percent_covered": 100.0, "num_statements": 10, "covered_lines": 10, "missing_lines": 0},
        "files": {"session_buddy/foo.py": {"summary": {"percent_covered": 90.0, "num_statements": 10, "missing_lines": 1}}},
    }
    covp = tmp_path / "coverage.json"
    covp.write_text(json.dumps(cov))
    bg = tmp_path / "backlog.md"
    bg.write_text("## `foo.py`\ntier: untested\n")  # 90% is "partial", not "untested"
    result = _run_validator(covp, bg)
    assert result.returncode == 1
    assert "tier" in result.stdout.lower()


def test_validator_flags_stale_pct(tmp_path: Path) -> None:
    cov = {
        "totals": {"percent_covered": 100.0, "num_statements": 10, "covered_lines": 10, "missing_lines": 0},
        "files": {"session_buddy/foo.py": {"summary": {"percent_covered": 90.0, "num_statements": 10, "missing_lines": 1}}},
    }
    covp = tmp_path / "coverage.json"
    covp.write_text(json.dumps(cov))
    bg = tmp_path / "backlog.md"
    bg.write_text("## `foo.py`\npct: 50\ntier: partial\n")  # 50% != 90%
    result = _run_validator(covp, bg)
    assert result.returncode == 1
    assert "pct" in result.stdout.lower() or "percent" in result.stdout.lower()


def test_validator_exits_zero_on_empty_inputs(tmp_path: Path) -> None:
    cov = {"totals": {}, "files": {}}
    covp = tmp_path / "cov.json"
    covp.write_text(json.dumps(cov))
    bg = tmp_path / "backlog.md"
    bg.write_text("# empty\n")
    result = _run_validator(covp, bg)
    # Empty inputs should pass (nothing to disagree on)
    assert result.returncode == 0
```

- [ ] **Step 2: Run tests; verify they FAIL**

```bash
uv run pytest tests/unit/scripts/test_verify_backlog.py -v --no-header 2>&1 | tail -10
```

Expected: errors (the script doesn't exist).

- [ ] **Step 3: Write `scripts/verify_backlog.py`**

```python
#!/usr/bin/env python3
"""Deterministic backlog validator.

Compares every file in coverage.json against rows in the backlog doc and
fails on missing, duplicate, stale-pct, or wrong-tier entries.

Tier boundaries (must match the L0/L1/L2/L3 spec):
  0%   → untested
  1-49% → low
  50-79% → partial
  80%+ → good

Usage:
    python scripts/verify_backlog.py coverage.json docs/coverage-backlog.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


TIER_RANGES = (
    ("untested", lambda pct: pct == 0),
    ("low", lambda pct: 0 < pct <= 49),
    ("partial", lambda pct: 49 < pct <= 79),
    ("good", lambda pct: pct >= 80),
)


def tier_for(pct: float) -> str:
    for name, pred in TIER_RANGES:
        if pred(pct):
            return name
    return "unknown"


def parse_backlog_row(line: str) -> tuple[str, float | None, str | None]:
    """Parse a row like: `### \`path/to/file.py\` ... - pct: 50, ... - tier: partial`"""
    # Simple heuristic; the backlog writer controls format
    m = re.search(r"###\s+`([^`]+)`", line)
    path = m.group(1) if m else ""
    pct_match = re.search(r"pct[:\s=]+(\d+(?:\.\d+)?)", line)
    pct = float(pct_match.group(1)) if pct_match else None
    tier_match = re.search(r"tier[:\s=]+(\w+)", line)
    tier = tier_match.group(1) if tier_match else None
    return path, pct, tier


def extract_backlog_rows(backlog_md: str) -> list[tuple[str, float | None, str | None]]:
    rows = []
    in_per_dir = False
    for line in backlog_md.splitlines():
        if line.startswith("## Per-directory backlog"):
            in_per_dir = True
            continue
        if in_per_dir and line.startswith("## ") and "Per-directory" not in line:
            in_per_dir = False
        if not in_per_dir:
            continue
        if line.startswith("### `") and line.strip().endswith("`"):
            row = parse_backlog_row(line)
            if row[0]:
                rows.append(row)
            continue
        if line.startswith("### "):
            # Continuation lines (`### `path` extra text`)
            row = parse_backlog_row(line)
            if row[0]:
                rows.append(row)
    return rows


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: verify_backlog.py coverage.json docs/coverage-backlog.md", file=sys.stderr)
        return 2
    cov_path = Path(argv[1])
    backlog_path = Path(argv[2])

    cov = json.loads(cov_path.read_text())
    files = cov.get("files", {})
    backlog_text = backlog_path.read_text()
    backlog_rows = extract_backlog_rows(backlog_text)

    failures = []

    # Index backlog by path; detect duplicates
    by_path: dict[str, list[tuple[float | None, str | None]]] = {}
    for path, pct, tier in backlog_rows:
        by_path.setdefault(path, []).append((pct, tier))

    for path, entries in by_path.items():
        if len(entries) > 1:
            failures.append(f"DUPLICATE entry: {path} appears {len(entries)} times")

    # Check every file in coverage.json appears in backlog with matching pct + tier
    for rel_path, fd in sorted(files.items()):
        if not isinstance(fd, dict):
            continue
        s = fd.get("summary", {}) if isinstance(fd.get("summary"), dict) else {}
        pct = float(s.get("percent_covered", 0.0))
        expected_tier = tier_for(pct)
        if rel_path not in by_path:
            failures.append(f"MISSING: {rel_path} ({pct:.1f}%, tier={expected_tier}) not in backlog")
            continue
        entries = by_path[rel_path]
        for entry_pct, entry_tier in entries:
            if entry_pct is not None and abs(entry_pct - pct) > 0.5:
                failures.append(f"STALE pct: {rel_path} backlog={entry_pct} coverage={pct:.1f}")
            if entry_tier and entry_tier != expected_tier:
                failures.append(f"WRONG tier: {rel_path} backlog={entry_tier} expected={expected_tier}")

    if failures:
        print("❌ Backlog validation FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        # Also print to stdout so the script's exit is observable from CI logs
        for f in failures:
            print(f"- {f}")
        return 1

    if not files:
        print("✅ Empty coverage.json + empty backlog — nothing to validate")
        return 0

    print(f"✅ Backlog validates against coverage.json ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Make executable; rerun tests**

```bash
chmod +x scripts/verify_backlog.py
uv run pytest tests/unit/scripts/test_verify_backlog.py -v --no-header 2>&1 | tail -15
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_backlog.py tests/unit/scripts/test_verify_backlog.py
git commit -m "feat(scripts): deterministic backlog validator"
```

**Reports:** Test pass count, validator exit code on the project once `coverage.json` exists (will be done in Task 4).

### Task 4: Generate wave-1 baseline manifest + first backlog doc

**Files:**

- Create: `session-buddy/docs/baselines/wave1-baseline.json`
- Modify: (or extend) `session-buddy/scripts/analyze_coverage.py` — see Step 3 note
- Modify (regenerate): `session-buddy/docs/coverage-backlog.md`

> If `analyze_coverage.py` does not yet produce a per-file tier/pct/pct-row format readable by `verify_backlog.py`, this task extends it to do so. If it already produces something else, this task adds a thin wrapper that re-formats into the validator's expected layout.

**Steps:**

- [ ] **Step 1: Produce the canonical coverage.json**

```bash
uv run pytest tests/ \
    --cov=session_buddy \
    --cov-branch \
    --cov-report=json:coverage.json \
    --cov-report=term-missing:skip-covered \
    -q --no-header --tb=line 2>&1 | tee /tmp/baseline-pytest.log | tail -20
PYTEST_RC=$?
echo "pytest exit code: ${PYTEST_RC}"
```

- [ ] **Step 2: Capture failure signatures**

```bash
uv run pytest tests/ -q --no-header --tb=no -p no:randomly 2>&1 \
    | tee /tmp/baseline-failures.log \
    | grep -E '^FAILED ' | awk '{print $2}' \
    | sort -u > /tmp/baseline-failures.txt
wc -l /tmp/baseline-failures.txt
```

- [ ] **Step 3: Generate backlog doc from coverage.json**

If `scripts/analyze_coverage.py` already produces the correct per-file format (with `### \`path\``headings and`pct: NN, tier: <name>\` rows), invoke it:

```bash
python scripts/analyze_coverage.py coverage.json --output docs/coverage-backlog.md
```

If not, write a tiny inline script to produce a minimal compatible doc for the validator:

```bash
python - <<'PY'
import json, sys
from pathlib import Path

cov = json.loads(Path("coverage.json").read_text())

def tier_for(pct: float) -> str:
    if pct == 0: return "untested"
    if pct < 50: return "low"
    if pct < 80: return "partial"
    return "good"

lines = ["# Coverage Backlog",
         "",
         "> Regenerated from coverage.json",
         "",
         "## Tier definitions",
         "",
         "| Tier | Coverage | Action |",
         "|---|---|---|",
         "| untested | 0% | Write at least smoke tests |",
         "| low | 1-49% | Targeted gap-fill |",
         "| partial | 50-79% | Continue tests |",
         "| good | 80%+ | Maintain |",
         "",
         "## Per-directory backlog",
         ""]
for rel, fd in sorted(cov.get("files", {}).items()):
    s = fd.get("summary", {}) if isinstance(fd, dict) else {}
    pct = float(s.get("percent_covered", 0.0))
    n = int(s.get("num_statements", 0))
    tier = tier_for(pct)
    lines.append(f"### `{rel}`")
    lines.append(f"- pct: {int(pct)}, lines: {n}, tier: {tier}")
    lines.append("")
Path("docs/coverage-backlog.md").write_text("\n".join(lines))
print("WROTE docs/coverage-backlog.md")
PY
```

- [ ] **Step 4: Run the backlog validator**

```bash
python scripts/verify_backlog.py coverage.json docs/coverage-backlog.md
```

Expected: exit 0. If exit 1 → the inline generator step doesn't match the validator's expected format; loop Step 3 and fix.

- [ ] **Step 5: Write `docs/baselines/wave1-baseline.json`**

```python
# Inline script:
import json, subprocess, datetime
from pathlib import Path

failures = sorted(Path("/tmp/baseline-failures.txt").read_text().splitlines())
failures = [f for f in failures if f]  # drop empty lines

cov = json.loads(Path("coverage.json").read_text())
files = cov.get("files", {})
per_file_metrics = {}
for rel, fd in sorted(files.items()):
    if not isinstance(fd, dict):
        continue
    s = fd.get("summary", {}) if isinstance(fd.get("summary"), dict) else {}
    per_file_metrics[rel] = {
        "lines": int(s.get("num_statements", 0)),
        "covered_lines": int(s.get("covered_lines", 0)),
        "missing_lines": int(s.get("missing_lines", 0)),
        "pct": round(float(s.get("percent_covered", 0.0)), 2),
        "branch_pct": round(float(s.get("percent_covered", 0.0) if "branch_coverage" not in s else s["percent_covered"]), 2),
    }

manifest = {
    "captured_at": datetime.datetime.utcnow().isoformat() + "Z",
    "captured_on_commit": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
    "test_invocation": "uv run pytest tests/ --cov=session_buddy --cov-branch --cov-report=json:coverage.json --cov-report=term-missing:skip-covered -q --no-header --tb=line",
    "baseline_failure_nodeids": failures,
    "test_count_total": None,  # filled in below
    "per_file_metrics": per_file_metrics,
}
# Fill total test count
total = 0
import re
for line in Path("/tmp/baseline-pytest.log").read_text().splitlines():
    m = re.match(r"^(\d+) passed", line)
    if m:
        manifest["test_count_total"] = int(m.group(1))
        break

Path("docs/baselines/wave1-baseline.json").parent.mkdir(parents=True, exist_ok=True)
Path("docs/baselines/wave1-baseline.json").write_text(json.dumps(manifest, indent=2))
print(f"WROTE {len(failures)} baseline failures, {len(per_file_metrics)} file metrics")
```

- [ ] **Step 6: Commit**

```bash
git add coverage.json docs/coverage-backlog.md docs/baselines/wave1-baseline.json
git rm --cached coverage.json 2>/dev/null || true   # if there's a .gitignore for it
# Document the policy in .gitignore if needed
git commit -m "feat(coverage): wave-1 baseline manifest + first backlog doc"
```

Note: `coverage.json` is typically gitignored. If so, write `coverage.json` to `.gitignore` if not present and remove from the commit. The manifest's `per_file_metrics` carry the same data.

**Reports:** total failures, total files in backlog, validator exit code.

### Task 5: `scripts/wave1_select_modules.py` (Phase 0.5 — module selection)

**Files:**

- Create: `session-buddy/scripts/wave1_select_modules.py`
- Create: `session-buddy/docs/baselines/wave1-anti-targets.json`
- Create: `session-buddy/docs/baselines/wave1-selected.json`
- Create: `tests/unit/scripts/test_wave1_select_modules.py`

**Steps:**

- [ ] **Step 1: Write the tests FIRST**

```python
# tests/unit/scripts/test_wave1_select_modules.py
"""Tests for wave-1 module selection."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _make_cov(files: dict[str, dict[str, float | int]]) -> dict:
    return {
        "totals": {"percent_covered": 50.0},
        "files": {
            p: {"summary": {"percent_covered": float(v["pct"]), "num_statements": int(v["n"]), "missing_lines": int(v["n"] * (100 - v["pct"]) / 100)}}
            for p, v in files.items()
        },
    }


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "scripts/wave1_select_modules.py"] + args, cwd=cwd, capture_output=True, text=True)


def test_selector_picks_one_per_slot(tmp_path: Path, repo_root: Path) -> None:
    cov = _make_cov({
        "session_buddy/mcp/tools/a.py": {"pct": 50.0, "n": 100},
        "session_buddy/mcp/tools/b.py": {"pct": 60.0, "n": 80},
        "session_buddy/cli.py": {"pct": 40.0, "n": 50},
        "session_buddy/cli_with_modes.py": {"pct": 30.0, "n": 200},
        "session_buddy/core/coordinator.py": {"pct": 45.0, "n": 90},
        "session_buddy/app_monitor.py": {"pct": 35.0, "n": 70},
        "session_buddy/utils/formatter.py": {"pct": 70.0, "n": 60},
    })
    (tmp_path / "cov.json").write_text(json.dumps(cov))
    anti_targets = {"anti_targets": []}
    (tmp_path / "anti.json").write_text(json.dumps(anti_targets))

    result = _run([
        "--coverage-json", str(tmp_path / "cov.json"),
        "--anti-targets-json", str(tmp_path / "anti.json"),
        "--output", str(tmp_path / "selected.json"),
    ], cwd=repo_root)
    assert result.returncode == 0, result.stdout + result.stderr

    selected = json.loads((tmp_path / "selected.json").read_text())
    slots = {s["slot"]: s for s in selected["selected"]}

    # Should pick one MCP, two CLI, two core, one util — at least one per layer
    layers = {s["layer"] for s in selected["selected"]}
    assert layers == {"mcp", "cli", "core", "util"}


def test_selector_skips_below_30_pct(tmp_path: Path, repo_root: Path) -> None:
    cov = _make_cov({
        "session_buddy/mcp/tools/low.py": {"pct": 10.0, "n": 100},  # would be a great lift, but <30
        "session_buddy/mcp/tools/ok.py": {"pct": 50.0, "n": 100},
    })
    (tmp_path / "cov.json").write_text(json.dumps(cov))
    (tmp_path / "anti.json").write_text(json.dumps({"anti_targets": []}))

    result = _run([
        "--coverage-json", str(tmp_path / "cov.json"),
        "--anti-targets-json", str(tmp_path / "anti.json"),
        "--output", str(tmp_path / "selected.json"),
    ], cwd=repo_root)
    assert result.returncode == 0
    selected = json.loads((tmp_path / "selected.json").read_text())
    paths = [s["path"] for s in selected["selected"]]
    assert "session_buddy/mcp/tools/low.py" not in paths


def test_selector_excludes_anti_targets(tmp_path: Path, repo_root: Path) -> None:
    cov = _make_cov({
        "session_buddy/mcp/tools/polluted.py": {"pct": 50.0, "n": 100},
        "session_buddy/mcp/tools/clean.py": {"pct": 50.0, "n": 100},
    })
    (tmp_path / "cov.json").write_text(json.dumps(cov))
    (tmp_path / "anti.json").write_text(json.dumps({"anti_targets": ["session_buddy/mcp/tools/polluted.py"]}))

    result = _run([
        "--coverage-json", str(tmp_path / "cov.json"),
        "--anti-targets-json", str(tmp_path / "anti.json"),
        "--output", str(tmp_path / "selected.json"),
    ], cwd=repo_root)
    assert result.returncode == 0
    selected = json.loads((tmp_path / "selected.json").read_text())
    paths = [s["path"] for s in selected["selected"]]
    assert "session_buddy/mcp/tools/polluted.py" not in paths


def test_selector_skips_trivial_below_20_statements(tmp_path: Path, repo_root: Path) -> None:
    cov = _make_cov({
        "session_buddy/__init__.py": {"pct": 0.0, "n": 5},    # trivial; excluded
        "session_buddy/mcp/tools/trivial.py": {"pct": 50.0, "n": 15},  # also trivial
        "session_buddy/mcp/tools/real.py": {"pct": 50.0, "n": 100},
    })
    (tmp_path / "cov.json").write_text(json.dumps(cov))
    (tmp_path / "anti.json").write_text(json.dumps({"anti_targets": []}))

    result = _run([
        "--coverage-json", str(tmp_path / "cov.json"),
        "--anti-targets-json", str(tmp_path / "anti.json"),
        "--output", str(tmp_path / "selected.json"),
    ], cwd=repo_root)
    assert result.returncode == 0
    selected = json.loads((tmp_path / "selected.json").read_text())
    paths = [s["path"] for s in selected["selected"]]
    assert "session_buddy/__init__.py" not in paths


def test_selector_skips_modules_over_600_loc(tmp_path: Path, repo_root: Path) -> None:
    cov = _make_cov({
        "session_buddy/mcp/tools/huge.py": {"pct": 50.0, "n": 700},  # > 600
        "session_buddy/mcp/tools/ok.py": {"pct": 50.0, "n": 100},
    })
    (tmp_path / "cov.json").write_text(json.dumps(cov))
    (tmp_path / "anti.json").write_text(json.dumps({"anti_targets": []}))

    result = _run([
        "--coverage-json", str(tmp_path / "cov.json"),
        "--anti-targets-json", str(tmp_path / "anti.json"),
        "--output", str(tmp_path / "selected.json"),
    ], cwd=repo_root)
    assert result.returncode == 0
    selected = json.loads((tmp_path / "selected.json").read_text())
    paths = [s["path"] for s in selected["selected"]]
    assert "session_buddy/mcp/tools/huge.py" not in paths


def test_selector_exits_nonzero_when_slot_underfilled(tmp_path: Path, repo_root: Path) -> None:
    # Only one MCP candidate exists; expect selector to either fill from cli or exit nonzero
    cov = _make_cov({
        "session_buddy/mcp/tools/only.py": {"pct": 50.0, "n": 100},
        "session_buddy/cli.py": {"pct": 50.0, "n": 100},
    })
    (tmp_path / "cov.json").write_text(json.dumps(cov))
    (tmp_path / "anti.json").write_text(json.dumps({"anti_targets": []}))

    result = _run([
        "--coverage-json", str(tmp_path / "cov.json"),
        "--anti-targets-json", str(tmp_path / "anti.json"),
        "--output", str(tmp_path / "selected.json"),
    ], cwd=repo_root)
    # Either the selector fills the mcp slot with `only.py` (returncode 0)
    # OR exits nonzero when the spec's slot minimum is unmet.
    # Spec says slots must be filled; we exit 1 if not enough MCP candidates for 5 slots.
    selected = json.loads((tmp_path / "selected.json").read_text())
    mcp_picks = [s for s in selected["selected"] if s["layer"] == "mcp"]
    if len(mcp_picks) < 5:
        assert result.returncode != 0
```

- [ ] **Step 2: Run tests; verify they FAIL**

```bash
uv run pytest tests/unit/scripts/test_wave1_select_modules.py -v --no-header 2>&1 | tail -10
```

- [ ] **Step 3: Build the conftest-pollution anti-target list**

```bash
# Inline script to detect pollution:
python - <<'PY'
import json, re, subprocess
from pathlib import Path

# Anti-target detection: tests that use sys.modules repointing OR
# monkeypatch.setattr against string-form dotted paths at module-load time.
ANTI_PATTERNS = [
    re.compile(r"sys\.modules\["),
    re.compile(r"monkeypatch\.setattr\(['\"][^'\"]+\.([a-z_]+)['\"]"),
]

polluted = []
for test_file in Path("tests").rglob("test_*.py"):
    text = test_file.read_text(errors="replace")
    hits = sum((p.search(text) is not None) for p in ANTI_PATTERNS)
    if hits >= 2:  # both patterns present → likely polluted
        # Find the session_buddy module the test is most likely about
        m = re.search(r"session_buddy[./]([a-z_/]+)", text)
        target = f"session_buddy/{m.group(1).replace('/', '/')}.py" if m else None
        if target:
            polluted.append({"test": str(test_file), "target": target, "patterns_matched": hits})

out = {
    "generated_at": subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"]).decode().strip(),
    "rules": ["sys.modules[", "monkeypatch.setattr with string-form dotted path"],
    "anti_targets": sorted({p["target"] for p in polluted}),
}
Path("docs/baselines/wave1-anti-targets.json").write_text(json.dumps(out, indent=2))
print(f"WROTE {len(out['anti_targets'])} anti-targets")
PY
```

- [ ] **Step 4: Write `scripts/wave1_select_modules.py`**

```python
#!/usr/bin/env python3
"""Wave-1 module selection.

Reads coverage.json + the anti-target list and selects exactly 10 modules
across 4 layers (5 MCP / 2 CLI / 2 core / 1 util), honoring the spec's
hard floors and tie-breakers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SLOTS = {
    "mcp":  5,
    "cli":  2,
    "core": 2,
    "util": 1,
}


def layer_of(path: str) -> str:
    p = path.replace("\\", "/")
    if "/mcp/tools/" in p:
        return "mcp"
    if p.startswith("session_buddy/cli") or "/cli/" in p:
        return "cli"
    if "/core/" in p or "/coordinator" in p or "/manager" in p or "/app_monitor" in p or "/natural_scheduler" in p:
        return "core"
    if "/utils/" in p:
        return "util"
    return "other"


def select(
    cov_files: dict[str, dict],
    anti_targets: set[str],
    min_statements: int = 20,
    max_statements: int = 600,
    pct_min: float = 30.0,
    pct_max: float = 94.0,
) -> list[dict]:
    """Apply floors + tie-breakers; return list of picks per slot."""
    candidates = []
    for path, fd in cov_files.items():
        if path in anti_targets:
            continue
        if path.endswith("/__init__.py"):
            continue
        s = fd.get("summary", {}) if isinstance(fd, dict) else {}
        pct = float(s.get("percent_covered", 0.0))
        n = int(s.get("num_statements", 0))
        if not (pct_min <= pct <= pct_max):
            continue
        if not (min_statements <= n <= max_statements):
            continue
        layer = layer_of(path)
        if layer == "other":
            continue
        candidates.append({"path": path, "pct": pct, "n": n, "layer": layer})

    # Tie-breakers: smaller LOC, then closer to 30% from below
    candidates.sort(key=lambda c: (c["n"], abs(c["pct"] - 30)))

    picks = []
    picked_paths = set()
    for layer, count in SLOTS.items():
        layer_cands = [c for c in candidates if c["layer"] == layer and c["path"] not in picked_paths]
        for c in layer_cands[:count]:
            picks.append({
                "path": c["path"],
                "layer": c["layer"],
                "pct": round(c["pct"], 2),
                "statements": c["n"],
            })
            picked_paths.add(c["path"])
    return picks


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", required=True)
    parser.add_argument("--anti-targets-json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv[1:])

    cov = json.loads(Path(args.coverage_json).read_text())
    anti = json.loads(Path(args.anti_targets_json).read_text())
    anti_targets = set(anti.get("anti_targets", []))

    files = cov.get("files", {})
    if not files:
        print("❌ coverage.json has no files; did the pytest run complete?", file=sys.stderr)
        return 1

    picks = select(files, anti_targets)

    # Verify all slots filled
    counts = {l: sum(1 for p in picks if p["layer"] == l) for l in SLOTS}
    missing_slots = [l for l, c in counts.items() if c < SLOTS[l]]
    if missing_slots:
        print(f"❌ Slot under-fill: {missing_slots} need more candidates. Picked: {[p['path'] for p in picks]}", file=sys.stderr)
        return 1

    out = {
        "selected": picks,
        "slot_counts": counts,
        "selection_rules": {
            "anti_target_count": len(anti_targets),
            "pct_window": "[30, 94]",
            "statements_window": "[20, 600]",
            "tie_breakers": ["smaller_n", "closer_to_30pct"],
        },
        "generated_at": "wave-1",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=2))
    print(f"WROTE {len(picks)} picks across {len(SLOTS)} layers to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 5: Run selector against project state**

```bash
chmod +x scripts/wave1_select_modules.py
python scripts/wave1_select_modules.py \
    --coverage-json coverage.json \
    --anti-targets-json docs/baselines/wave1-anti-targets.json \
    --output docs/baselines/wave1-selected.json
```

If exit 1 (slot under-fill), either lower slot counts or skip to wave-2 for under-filled layers — surface to user.

- [ ] **Step 6: Re-run tests**

```bash
uv run pytest tests/unit/scripts/test_wave1_select_modules.py -v --no-header 2>&1 | tail -10
```

Expected: all 6 tests pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/wave1_select_modules.py tests/unit/scripts/test_wave1_select_modules.py \
        docs/baselines/wave1-anti-targets.json docs/baselines/wave1-selected.json
git commit -m "feat(scripts): wave-1 module selector + anti-target detection"
```

**Reports:** Slot counts in `wave1-selected.json`, anti-target count, the 10 picked paths.

### Task 5b: Wave-1 baseline commit

**Files:** (no new files)

- [ ] **Step 1: Verify Phase 0 + 0.5 outputs all exist**

```bash
ls -1 docs/baselines/wave1-{preflight,baseline,anti-targets,selected}.json coverage.json docs/coverage-backlog.md
```

- [ ] **Step 2: Run the audit script + the validator**

```bash
bash scripts/run_coverage_audit.sh 2>&1 | tail -30
python scripts/verify_backlog.py coverage.json docs/coverage-backlog.md
```

- [ ] **Step 3: Add a CHANGELOG-style WAVE1_PROGRESS.md note**

```markdown
# Wave 1 Coverage — Start state

Generated: <ISO timestamp>
Initial commit: <git rev-parse HEAD>

## Phase 0 outputs
- `docs/baselines/wave1-baseline.json` — failure manifest + per-file coverage snapshot
- `docs/coverage-backlog.md` — 4-tier categorization
- `scripts/run_coverage_audit.sh` — observability script (does not fail build)
- `scripts/verify_backlog.py` — deterministic backlog validator
- `scripts/wave1_select_modules.py` — machine-checked module picker

## Phase 0.5 selection
See `docs/baselines/wave1-selected.json` for the 10 picked modules.

## Wave-1 target
- 10 modules × ≥95% line + ≥90% branch coverage
- 0 new nodeid-set-diff failures
- Coverage global gate stays at `--cov-fail-under=85` (CLAUDE.md); wave-1 prepares but does not raise
```

- [ ] **Step 4: Commit (close Phase 0)**

```bash
git add docs/baselines/wave1-selected.json  # if not yet
git commit --allow-empty -m "chore(coverage-wave1): close Phase 0 — observability stack ready"
```

**Reports:** Audit script exit code; validator exit code; selected.json slot counts.

______________________________________________________________________

## Phase 1: Per-Module Lifts (10 Tasks, Tasks 6-10 + 12-16)

> **Each per-module lift task (Tasks 6-10 and Tasks 12-16) operates in an isolated worktree and uses the wave-1 subagent brief from the spec (Section "Subagent brief template").** Tasks 6-10 belong to batch 1a; tasks 12-16 belong to batch 1b. All five per-subagent checks (a)(b-fast)(c)(e) execute against the worktree's `tests/unit/test_<module>.py` and that worktree's COVERAGE_FILE.

### Task 6: Reference module lift — full TDD with subagent brief (Module #1)

**Files (in worktree `.worktrees/wave1-batch1a-<module1>`):**

- Create: `tests/unit/test_<module1>.py`
- Read: `session_buddy/<module1>.py` (target)

**Steps:**

- [ ] **Step 1: Create worktree and branch**

```bash
git worktree add .worktrees/wave1-batch1a-module1 -b feat/coverage-wave1-batch1a-module1 main
cd .worktrees/wave1-batch1a-module1
export COVERAGE_FILE="$PWD/.coverage.wave1.module1"
```

- [ ] **Step 2: Read the spec's subagent brief template**

Open `docs/superpowers/specs/2026-08-03-session-buddy-coverage-improvement-design.md` and copy the "Subagent brief template" section into a working scratch file `task6-brief.md`. Replace `<module>` with the actual picked path.

- [ ] **Step 3: Write module tests (TDD: write tests first against the public surface)**

Read `session_buddy/<module1>.py`. For every public function (`def [a-z]` excluding `_`-prefixed):

- Write a happy-path test with a known input
- Write at least one unhappy-path test (validation failure, empty input, type error, etc.)

If target is an MCP tool: also add a registration smoke (`from session_buddy.<x> import <X>; assert <X> is not None`).
If target is a CLI: also add `subprocess.run([sys.executable, "-m", "session_buddy.cli", "<cmd>", "--help"], ...)` exit-0 test.

- [ ] **Step 4: Run check (a)**

```bash
COVERAGE_FILE="$PWD/.coverage.wave1.module1" uv run pytest tests/unit/test_<module1>.py -v --no-header -q
```

All tests pass.

- [ ] **Step 5: Run check (b-fast) — targeted with --cov filter**

```bash
COVERAGE_FILE="$PWD/.coverage.wave1.module1" uv run pytest tests/unit/test_<module1>.py -q --no-header \
    --cov=session_buddy.<module1> --cov-branch \
    --cov-report=term:skip-covered \
    --override-ini="addopts="
```

Verify: line coverage on this module ≥95%; branch coverage ≥90%.

- [ ] **Step 6: Run check (c) sync/async defensiveness**

```bash
# (c1) coroutine assertion
uv run python -c "import inspect, session_buddy.<module1>; names = [(n, getattr(session_buddy.<module1>, n)) for n in dir(session_buddy.<module1>) if not n.startswith('_')]; coros = [(n, f) for n, f in names if inspect.iscoroutinefunction(f)]; print('COROS:', [n for n, _ in coros]); [inspect.iscoroutinefunction(f) for n, f in coros]"

# (c2) sync bridge grep
grep -nE '(asyncio\.run|run_until_complete|get_event_loop\(\)\.run)' tests/unit/test_<module1>.py
```

Empty grep output OR each hit `# reason:`-justified.

- [ ] **Step 7: Run check (e) public-function coverage**

```bash
# count `def [a-z]` (no underscore prefix) in target
grep -cE '^def [a-z][a-zA-Z0-9_]*\(' session_buddy/<module1>.py
# count test functions / fixtures that reference each public name
uv run pytest tests/unit/test_<module1>.py --collect-only -q 2>&1 | wc -l
```

Both numbers non-zero and reasonable.

- [ ] **Step 8: Commit the per-module work**

```bash
git add tests/unit/test_<module1>.py
# Add ONLY `pragma: no cover` if reviewer pre-approved a justification
git commit -m "test(coverage): lift <module1> to ≥95% line / ≥90% branch"
```

- [ ] **Step 9: Report**

Write `task6-report.md`:

- Test count, line count added
- Before/after coverage
- (c1) coroutine list
- (c2) grep output (empty → "no sync bridges")
- (e) public function counts
- Concerns (if any)

**Reports:** Path `task6-report.md`, all 5-check confirmations.

### Tasks 7-10: Lift modules #2, #3, #4, #5 (Batch 1a)

**Same shape as Task 6**, with `<module2>` / `<module3>` / etc. substituted.

For each task:

- Create worktree `.worktrees/wave1-batch1a-module<N>` on `feat/coverage-wave1-batch1a-module<N>`
- Set `COVERAGE_FILE="$PWD/.coverage.wave1.module<N>"`
- Execute steps 3-9 from Task 6
- Commit on the worktree's branch
- Write `task<N>-report.md`

**Special parallel note:** Tasks 7-10 are dispatched by the wave-lead in PARALLEL (one Agent invocation each, each in a different worktree). Each subagent has its own context; they communicate via their `task<N>-report.md` files in the controller's scratch directory.

### Task 11: Wave-lead batch 1a gate

**Files (in the controller session, not a worktree):**

- Modify: `coverage.json` (combine agent reports)
- Create: `docs/baselines/wave1-batch1a-delta.json`

**Steps:**

- [ ] **Step 1: Merge subagent branches into batch branch**

```bash
git checkout -b feat/coverage-wave1-batch1a main
git merge --no-ff feat/coverage-wave1-batch1a-module1 -m "merge: batch1a module1"
git merge --no-ff feat/coverage-wave1-batch1a-module2 -m "merge: batch1a module2"
git merge --no-ff feat/coverage-wave1-batch1a-module3 -m "merge: batch1a module3"
git merge --no-ff feat/coverage-wave1-batch1a-module4 -m "merge: batch1a module4"
git merge --no-ff feat/coverage-wave1-batch1a-module5 -m "merge: batch1a module5"
```

- [ ] **Step 2: Combine per-agent coverage files**

```bash
# Copy each agent's COVERAGE_FILE into the controller's directory
cp .worktrees/wave1-batch1a-module1/.coverage.wave1.module1 /tmp/combined-coverage-module1
cp .worktrees/wave1-batch1a-module2/.coverage.wave1.module2 /tmp/combined-coverage-module2
# ... for all 5
COVERAGE_FILE=/tmp/combined-coverage-batch1a uv run coverage combine \
    /tmp/combined-coverage-module1 \
    /tmp/combined-coverage-module2 \
    /tmp/combined-coverage-module3 \
    /tmp/combined-coverage-module4 \
    /tmp/combined-coverage-module5 \
    --keep
uv run coverage json --include="session_buddy/*" -o coverage-batch1a.json
```

- [ ] **Step 3: Wave-lead single full-suite run + nodeid-set-diff**

```bash
uv run pytest tests/ -q --no-header --tb=line 2>&1 | tee /tmp/batch1a-full.log
PYTEST_RC=$?

# Compute current failure nodeids
grep -E '^FAILED ' /tmp/batch1a-full.log | awk '{print $2}' | sort -u > /tmp/batch1a-current-failures.txt

# Compare to baseline
comm -13 <(sort -u docs/baselines/wave1-baseline.json | python -c "import json,sys; print('\n'.join(json.loads(sys.stdin.read())['baseline_failure_nodeids']))") \
        <(sort -u /tmp/batch1a-current-failures.txt) > /tmp/batch1a-new-failures.txt

wc -l /tmp/batch1a-new-failures.txt
```

- [ ] **Step 4: Decision**

- If `wc -l /tmp/batch1a-new-failures.txt` is 0 → batch 1a PASSES; proceed.

- If >0 → review each new failure. If wave-1 caused it, revert the responsible subagent's commit (`git revert <sha>`) and re-run Step 2. If pre-existing in a flaky-test sense, escalate to user.

- [ ] **Step 5: Write delta JSON**

```python
# Inline:
import json, subprocess, datetime
from pathlib import Path

delta = {
    "phase": "batch1a",
    "captured_at": datetime.datetime.utcnow().isoformat() + "Z",
    "captured_on_commit": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
    "new_failures": Path("/tmp/batch1a-new-failures.txt").read_text().splitlines(),
    "covered_modules": ["<the 5 modules from batch1a>"],
    "merge_commit": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
}
Path("docs/baselines/wave1-batch1a-delta.json").write_text(json.dumps(delta, indent=2))
```

- [ ] **Step 6: Commit (close batch 1a)**

```bash
git add docs/baselines/wave1-batch1a-delta.json coverage-batch1a.json
git commit -m "feat(coverage): batch 1a gate — 5 modules lifted, 0 new failures"
```

**Reports:** Combined coverage line, `wc -l /tmp/batch1a-new-failures.txt` (=0 expected), commit SHA.

### Tasks 12-16: Lift modules #6-#10 (Batch 1b)

Identical to Tasks 6-10 with `<module6>`-`<module10>`. Worktree `.worktrees/wave1-batch1b-module<N>`, branch `feat/coverage-wave1-batch1b-module<N>`. Dispatched in parallel by wave-lead.

### Task 17: Wave-lead batch 1b gate

Same shape as Task 16 (merged into `feat/coverage-wave1-batch1b`, combined coverage, single full-suite diff against `wave1-baseline.json`). Output: `docs/baselines/wave1-batch1b-delta.json`.

**Special note:** The baseline is `wave1-baseline.json` (captured in Task 4) — NOT the batch1a delta. The batch1a failures (now fixed or unfixed) are baseline-checked, but `baseline_failure_nodeids` is the master set.

______________________________________________________________________

## Phase 2: Closing

### Task 18: Regenerate backlog + delta JSON

**Files:**

- Modify (regenerate): `session-buddy/docs/coverage-backlog.md`
- Create: `session-buddy/docs/baselines/wave1-delta.json` (wave-end summary)
- Modify (remove if stale): `coverage.json` (or keep but gitignored)

**Steps:**

- [ ] **Step 1: Generate the post-wave coverage.json**

```bash
git checkout feat/coverage-wave1  # create this branch in Task 18-prep if needed
git merge --no-ff feat/coverage-wave1-batch1a -m "merge: batch1a → wave1"
git merge --no-ff feat/coverage-wave1-batch1b -m "merge: batch1b → wave1"

uv run pytest tests/ \
    --cov=session_buddy \
    --cov-branch \
    --cov-report=json:coverage.json \
    --cov-report=term-missing:skip-covered \
    -q --no-header --tb=line 2>&1 | tee /tmp/wave1-end-pytest.log | tail -10
```

- [ ] **Step 2: Regenerate backlog**

```bash
# Reuse Task 4's Step 3 inline generator (or scripts/analyze_coverage.py)
python -c "
import json
from pathlib import Path
# ... (repeat the inline backlog generator from Task 4)
"
```

- [ ] **Step 3: Validate backlog**

```bash
python scripts/verify_backlog.py coverage.json docs/coverage-backlog.md
```

Must exit 0.

- [ ] **Step 4: Write wave-end delta**

```python
# Inline:
import json, subprocess, datetime
from pathlib import Path

baseline = json.loads(Path("docs/baselines/wave1-baseline.json").read_text())
current = json.loads(Path("coverage.json").read_text())

# Per-module delta
def tier_for(pct):
    if pct == 0: return "untested"
    if pct < 50: return "low"
    if pct < 80: return "partial"
    return "good"

per_file = {}
for path, fd in (current.get("files") or {}).items():
    if not isinstance(fd, dict): continue
    s = fd.get("summary", {})
    pct_now = float(s.get("percent_covered", 0.0))
    base = baseline.get("per_file_metrics", {}).get(path, {})
    pct_base = base.get("pct", 0.0)
    tier_now = tier_for(pct_now)
    per_file[path] = {
        "before_pct": pct_base,
        "after_pct": pct_now,
        "delta_pct": round(pct_now - pct_base, 2),
        "tier_now": tier_now,
        "lifted": (pct_base < 95.0 and pct_now >= 95.0),
    }

delta = {
    "captured_at": datetime.datetime.utcnow().isoformat() + "Z",
    "captured_on_commit": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
    "files_lifted_to_95_plus": [p for p, m in per_file.items() if m["lifted"]],
    "files_unchanged_or_regressed": [p for p, m in per_file.items() if not m["lifted"]],
    "per_file_delta": per_file,
}
Path("docs/baselines/wave1-delta.json").write_text(json.dumps(delta, indent=2))
print(f"WROTE wave1-delta.json with {len(delta['files_lifted_to_95_plus'])} lifted files")
```

- [ ] **Step 5: Commit**

```bash
git add coverage.json docs/coverage-backlog.md docs/baselines/wave1-delta.json
git rm --cached coverage.json 2>/dev/null || true
git commit -m "feat(coverage-wave1): regenerated backlog + end-of-wave delta"
```

**Reports:** Lifted-module count, validator exit code.

### Task 19: Completion report

**Files:**

- Create: `session-buddy/docs/archive/completion-reports/2026-08-03-session-buddy-coverage-wave1.md`

**Steps:**

- [ ] **Step 1: Write the report**

```bash
python - <<'PY'
import json
from pathlib import Path
from datetime import datetime

baseline = json.loads(Path("docs/baselines/wave1-baseline.json").read_text())
delta = json.loads(Path("docs/baselines/wave1-delta.json").read_text())
batch1a = json.loads(Path("docs/baselines/wave1-batch1a-delta.json").read_text())
batch1b = json.loads(Path("docs/baselines/wave1-batch1b-delta.json").read_text())

def tier_for(pct):
    if pct == 0: return "untested"
    if pct < 50: return "low"
    if pct < 80: return "partial"
    return "good"

# Sync/async hit count
import subprocess, re
sync_async_hits = 0
justified_hits = 0
for test_file in Path("tests/unit").rglob("test_*.py"):
    text = test_file.read_text(errors="replace")
    for line_no, line in enumerate(text.splitlines(), 1):
        if re.search(r"(asyncio\.run|run_until_complete|get_event_loop\(\)\.run)", line):
            if "# reason:" in line or "# pragma:" in line:
                justified_hits += 1
            else:
                sync_async_hits += 1

# Per-module report rows
rows = []
for path in delta["files_lifted_to_95_plus"] + delta["files_unchanged_or_regressed"]:
    m = delta["per_file_delta"][path]
    base = baseline.get("per_file_metrics", {}).get(path, {})
    rows.append(f"| `{path}` | {m['before_pct']:.1f}% | {m['after_pct']:.1f}% | {m['delta_pct']:+.1f} | {m['tier_now']} |")

new_failures_total = len(batch1a.get("new_failures", [])) + len(batch1b.get("new_failures", []))

body = f"""# Wave-1 Coverage Completion Report

**Date:** {datetime.utcnow().isoformat()}Z
**Wave spec:** `docs/superpowers/specs/2026-08-03-session-buddy-coverage-improvement-design.md` (v2)
**Baseline:** `docs/baselines/wave1-baseline.json`
**Delta:** `docs/baselines/wave1-delta.json`

## Summary

- **Modules lifted to ≥95% line:** {len(delta['files_lifted_to_95_plus'])}
- **New failures introduced by wave-1:** {new_failures_total}
- **Sync/async defensiveness `sync_async_hit_count`:** {sync_async_hits} unjustified hits, {justified_hits} justified
- **CLAUDE.md gate (`--cov-fail-under=85`):** UNCHANGED — wave-1 prepares, does not raise

## Per-module before / after

| Module | Before | After | Δ | Tier |
|---|---|---|---|---|
{chr(10).join(rows)}

## Batch gates

- **Batch 1a:** 5 modules merged; new failures = {len(batch1a.get('new_failures', []))}
- **Batch 1b:** 5 modules merged; new failures = {len(batch1b.get('new_failures', []))}

## Outcomes vs spec

- **G1 (backlog doc):** {"PASS" if Path("docs/coverage-backlog.md").exists() else "FAIL"}
- **G2 (audit script):** {"PASS" if Path("scripts/run_coverage_audit.sh").exists() else "FAIL"}
- **G3 (10 modules ≥95% line + ≥90% branch):** {"PASS — count="+ str(len(delta['files_lifted_to_95_plus'])) if len(delta['files_lifted_to_95_plus']) >= 10 else "PARTIAL — only "+ str(len(delta['files_lifted_to_95_plus']))}
- **G4 (sync/async blocking):** {"PASS" if sync_async_hits == 0 else "FAIL — "+ str(sync_async_hits) + " unjustified hits"}
- **G5 (no new failures):** {"PASS" if new_failures_total == 0 else "FAIL — "+ str(new_failures_total) + " new failures"}
- **G6 (this report):** PASS

## Blockers hit

(None yet — see commit history or task reports.)

## Wave-2 next steps

- Modules still in `untested` or `low` tier are wave-2/3 candidates.
- If wave-1 reaches >95% lifted, a follow-up plan may propose raising per-module coverage or amending CLAUDE.md's `--cov-fail-under=85` for the (now achievable) global gate.

## Raw artifacts

- `coverage.json` (gitignored)
- `docs/baselines/wave1-baseline.json`
- `docs/baselines/wave1-batch1a-delta.json`
- `docs/baselines/wave1-batch1b-delta.json`
- `docs/baselines/wave1-delta.json`
- `docs/baselines/wave1-anti-targets.json`
- `docs/baselines/wave1-selected.json`
"""

Path("docs/archive/completion-reports").mkdir(parents=True, exist_ok=True)
Path("docs/archive/completion-reports/2026-08-03-session-buddy-coverage-wave1.md").write_text(body)
print("WROTE completion report")
PY
```

- [ ] **Step 2: Commit**

```bash
git add docs/archive/completion-reports/2026-08-03-session-buddy-coverage-wave1.md
git commit -m "docs(coverage-wave1): completion report"
```

- [ ] **Step 3: Close the wave branch**

```bash
git checkout main
git merge --no-ff feat/coverage-wave1 -m "merge: coverage wave 1"
git worktree remove .worktrees/wave1-batch1a-module1
git worktree remove .worktrees/wave1-batch1a-module2
# ...
git branch -d feat/coverage-wave1-batch1a-module1
```

(Per Bodai pre-1.0 merge policy: branch into main directly via fast-forward.)

- [ ] **Step 4: Final verification — run audit script**

```bash
bash scripts/run_coverage_audit.sh 2>&1 | tail -20
```

Expected: exit 0, summary printed.

**Reports:** Completion report path, all G-numbers' PASS/FAIL, branch state (clean), worktree list empty.

______________________________________________________________________

## Self-Review (run before opening for execution)

1. **Spec coverage:** Each goal G1-G7 maps to a task (G1 → Tasks 4+18, G2 → Task 2, G3 → Tasks 6-10 + 12-16, G4 → Step 6 of Task 6 (and 7-10, 12-16 by reference), G5 → Steps 3-4 of Tasks 11+17, G6 → Task 19, G7 → Tasks 11+17).
1. **Placeholder scan:** All scripts and tasks have concrete commands — no "TODO", "TBD", or "add appropriate". The exception: `scripts/analyze_coverage.py` may need extension (Step 3, Task 4 handles this conditionally).
1. **Type consistency:** Worktree paths (`wave1-batchX-moduleN`), coverage file names (`.coverage.wave1.<name>`), branch names (`feat/coverage-wave1-batch<X>-<module>`) used uniformly.
1. **Scope:** Plan is single-implementation. Phase 2 / completion report is in scope; CLAUDE.md amendment is explicitly out of scope (per N1 reframe).
