# Wave 1 Coverage — Start state

Generated: 2026-08-04T04:15:03Z
Initial commit: f03a8e1888c78435161b0c98a3e27ccbbfd42000

## Phase 0 outputs
- `docs/baselines/wave1-baseline.json` — failure manifest + per-file coverage snapshot
- `docs/baselines/wave1-preflight.json` — preflight probe results
- `docs/baselines/wave1-anti-targets.json` — files excluded from selection (not worth lifting)
- `docs/coverage-backlog.md` — 4-tier categorization
- `scripts/run_coverage_audit.sh` — observability script (does not fail build)
- `scripts/verify_backlog.py` — deterministic backlog validator
- `scripts/wave1_select_modules.py` — machine-checked module picker

## Phase 0.5 selection
See `docs/baselines/wave1-selected.json` for the 10 picked modules.

- selected modules: 10
- slot_counts: {mcp: 5, cli: 2, core: 2, util: 1}

## Wave-1 target
- 10 modules × ≥95% line + ≥90% branch coverage
- 0 new nodeid-set-diff failures
- Coverage global gate stays at `--cov-fail-under=85` (CLAUDE.md); wave-1 prepares but does not raise
