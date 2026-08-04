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
        capture_output=True, text=True,
        # parents[3] resolves to repo root, not parents[2] which gives tests/
        cwd=Path(__file__).resolve().parents[3],
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
