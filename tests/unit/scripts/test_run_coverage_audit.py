"""Smoke tests for the audit script."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def repo_root() -> Path:
    # Locate the repo relative to this test file
    # NOTE: brief's snippet says parents[2], but that resolves to tests/ (not the
    # repo root) given the file lives at tests/unit/scripts/. Fixed to parents[3]
    # so the fixture actually locates the repo root and the test passes.
    return Path(__file__).resolve().parents[3]


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
