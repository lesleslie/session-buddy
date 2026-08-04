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
# F3 workaround: tests/unit/test_quality_scoring_metrics_registry.py has a
# pre-existing collection ERROR that interrupts pytest collection. Ignoring
# that file lets pytest complete and coverage.json to be produced.
uv run pytest tests/ \
    --ignore=tests/unit/test_quality_scoring_metrics_registry.py \
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
