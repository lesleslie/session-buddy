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
            path: {
                "summary": {
                    "percent_covered": float(values["pct"]),
                    "num_statements": int(values["n"]),
                    "missing_lines": int(
                        values["n"] * (100 - values["pct"]) / 100
                    ),
                }
            }
            for path, values in files.items()
        },
    }


def _full_slot_candidates() -> dict[str, dict[str, float | int]]:
    """Return enough valid candidates to fill the binding 5/2/2/1 slots."""
    return {
        "session_buddy/mcp/tools/a.py": {"pct": 50.0, "n": 101},
        "session_buddy/mcp/tools/b.py": {"pct": 55.0, "n": 102},
        "session_buddy/mcp/tools/c.py": {"pct": 60.0, "n": 103},
        "session_buddy/mcp/tools/d.py": {"pct": 65.0, "n": 104},
        "session_buddy/mcp/tools/e.py": {"pct": 70.0, "n": 105},
        "session_buddy/cli.py": {"pct": 40.0, "n": 50},
        "session_buddy/cli_with_modes.py": {"pct": 30.0, "n": 200},
        "session_buddy/core/coordinator.py": {"pct": 45.0, "n": 90},
        "session_buddy/app_monitor.py": {"pct": 35.0, "n": 70},
        "session_buddy/utils/formatter.py": {"pct": 70.0, "n": 60},
    }


@pytest.fixture
def repo_root() -> Path:
    # This test is three levels below the repository root, not two as in the brief.
    return Path(__file__).resolve().parents[3]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/wave1_select_modules.py", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_inputs(tmp_path: Path, cov: dict, anti_targets: list[str] | None = None) -> None:
    (tmp_path / "cov.json").write_text(json.dumps(cov))
    (tmp_path / "anti.json").write_text(
        json.dumps({"anti_targets": anti_targets or []})
    )


def _selector_args(tmp_path: Path) -> list[str]:
    return [
        "--coverage-json",
        str(tmp_path / "cov.json"),
        "--anti-targets-json",
        str(tmp_path / "anti.json"),
        "--output",
        str(tmp_path / "selected.json"),
    ]


def test_selector_picks_one_per_slot(tmp_path: Path, repo_root: Path) -> None:
    _write_inputs(tmp_path, _make_cov(_full_slot_candidates()))

    result = _run(_selector_args(tmp_path), cwd=repo_root)
    assert result.returncode == 0, result.stdout + result.stderr

    selected = json.loads((tmp_path / "selected.json").read_text())
    assert selected["slot_counts"] == {"mcp": 5, "cli": 2, "core": 2, "util": 1}
    assert len(selected["selected"]) == 10


def test_selector_skips_below_30_pct(tmp_path: Path, repo_root: Path) -> None:
    candidates = _full_slot_candidates()
    # This would win the LOC tie-breaker, but it is below the 30% floor.
    candidates["session_buddy/mcp/tools/low.py"] = {"pct": 10.0, "n": 20}
    _write_inputs(tmp_path, _make_cov(candidates))

    result = _run(_selector_args(tmp_path), cwd=repo_root)
    assert result.returncode == 0, result.stdout + result.stderr
    selected = json.loads((tmp_path / "selected.json").read_text())
    paths = [selection["path"] for selection in selected["selected"]]
    assert "session_buddy/mcp/tools/low.py" not in paths


def test_selector_excludes_anti_targets(tmp_path: Path, repo_root: Path) -> None:
    candidates = _full_slot_candidates()
    candidates["session_buddy/mcp/tools/polluted.py"] = {"pct": 50.0, "n": 20}
    _write_inputs(
        tmp_path,
        _make_cov(candidates),
        anti_targets=["session_buddy/mcp/tools/polluted.py"],
    )

    result = _run(_selector_args(tmp_path), cwd=repo_root)
    assert result.returncode == 0, result.stdout + result.stderr
    selected = json.loads((tmp_path / "selected.json").read_text())
    paths = [selection["path"] for selection in selected["selected"]]
    assert "session_buddy/mcp/tools/polluted.py" not in paths


def test_selector_skips_trivial_below_20_statements(
    tmp_path: Path, repo_root: Path
) -> None:
    candidates = _full_slot_candidates()
    candidates.update(
        {
            "session_buddy/__init__.py": {"pct": 50.0, "n": 5},
            "session_buddy/mcp/tools/trivial.py": {"pct": 50.0, "n": 15},
        }
    )
    _write_inputs(tmp_path, _make_cov(candidates))

    result = _run(_selector_args(tmp_path), cwd=repo_root)
    assert result.returncode == 0, result.stdout + result.stderr
    selected = json.loads((tmp_path / "selected.json").read_text())
    paths = [selection["path"] for selection in selected["selected"]]
    assert "session_buddy/__init__.py" not in paths
    assert "session_buddy/mcp/tools/trivial.py" not in paths


def test_selector_skips_modules_over_600_loc(
    tmp_path: Path, repo_root: Path
) -> None:
    candidates = _full_slot_candidates()
    candidates["session_buddy/mcp/tools/huge.py"] = {"pct": 50.0, "n": 700}
    _write_inputs(tmp_path, _make_cov(candidates))

    result = _run(_selector_args(tmp_path), cwd=repo_root)
    assert result.returncode == 0, result.stdout + result.stderr
    selected = json.loads((tmp_path / "selected.json").read_text())
    paths = [selection["path"] for selection in selected["selected"]]
    assert "session_buddy/mcp/tools/huge.py" not in paths


def test_selector_exits_nonzero_when_slot_underfilled(
    tmp_path: Path, repo_root: Path
) -> None:
    # Only one MCP candidate exists, so all available picks are written before exit.
    cov = _make_cov(
        {
            "session_buddy/mcp/tools/only.py": {"pct": 50.0, "n": 100},
            "session_buddy/cli.py": {"pct": 50.0, "n": 100},
        }
    )
    _write_inputs(tmp_path, cov)

    result = _run(_selector_args(tmp_path), cwd=repo_root)
    selected = json.loads((tmp_path / "selected.json").read_text())
    mcp_picks = [
        selection
        for selection in selected["selected"]
        if selection["layer"] == "mcp"
    ]
    assert len(mcp_picks) == 1
    assert result.returncode != 0
