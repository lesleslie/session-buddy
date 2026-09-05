"""Smoke tests for session_buddy/scripts/test_runner.py CLI wrapper.

The runner is a thin shell around ``pytest.main`` and ``coverage`` subprocess
invocations; these tests pin argv parsing and the dispatch targets so future
refactors stay observable.
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from session_buddy.scripts.test_runner import main


def _set_argv(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> None:
    """Simulate ``python test_runner.py <args>`` by setting sys.argv."""
    monkeypatch.setattr(sys, "argv", ["test_runner.py", *args])


def test_no_flags_invokes_pytest_main_with_tests_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty argv defaults ``pytest_args`` to ``['tests/']`` and calls pytest.main."""
    _set_argv(monkeypatch, [])

    with mock.patch("pytest.main", return_value=0) as mock_pytest_main:
        result = main()

    mock_pytest_main.assert_called_once_with(["tests/"])
    assert result == 0


def test_passes_through_pytest_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """Custom positional and option args are forwarded to ``pytest.main``."""
    _set_argv(monkeypatch, ["tests/unit/foo.py", "-v", "--tb=short"])

    with mock.patch("pytest.main", return_value=0) as mock_pytest_main:
        main()

    mock_pytest_main.assert_called_once_with(
        ["tests/unit/foo.py", "-v", "--tb=short"]
    )


def test_strips_coverage_flag_and_invokes_coverage_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--coverage`` triggers ``coverage run -m pytest ...`` then ``coverage report``."""
    _set_argv(monkeypatch, ["--coverage"])

    fake_result = mock.Mock(returncode=0)
    with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
        result = main()

    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["coverage", "run", "-m", "pytest", "tests/"],
        check=False,
    )
    mock_run.assert_any_call(["coverage", "report"], check=False)
    assert result == 0


def test_short_coverage_flag_triggers_same_subprocess_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``-c`` is an alias for ``--coverage`` and takes the same path."""
    _set_argv(monkeypatch, ["-c", "tests/unit/"])

    fake_result = mock.Mock(returncode=0)
    with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
        main()

    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["coverage", "run", "-m", "pytest", "tests/unit/"],
        check=False,
    )
    mock_run.assert_any_call(["coverage", "report"], check=False)


def test_coverage_flag_strips_keep_pytest_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under ``--coverage`` only the wrapper's flags are stripped; pytest args pass through."""
    _set_argv(monkeypatch, ["--coverage", "tests/unit/foo.py", "-v", "--tb=short"])

    fake_result = mock.Mock(returncode=0)
    with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
        main()

    mock_run.assert_any_call(
        [
            "coverage", "run", "-m", "pytest",
            "tests/unit/foo.py", "-v", "--tb=short",
        ],
        check=False,
    )


def test_html_with_coverage_runs_coverage_html_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--coverage --html`` adds a third ``coverage html`` subprocess call."""
    _set_argv(monkeypatch, ["--coverage", "--html"])

    fake_result = mock.Mock(returncode=0)
    with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
        main()

    assert mock_run.call_count == 3
    mock_run.assert_any_call(
        ["coverage", "html", "--directory=htmlcov"],
        check=False,
    )


def test_html_alone_falls_through_to_pytest_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--html`` without ``--coverage`` strips the flag and runs pytest.main directly."""
    _set_argv(monkeypatch, ["--html"])

    with mock.patch("pytest.main", return_value=0) as mock_pytest_main, \
         mock.patch("subprocess.run") as mock_run:
        main()

    mock_pytest_main.assert_called_once_with(["tests/"])
    mock_run.assert_not_called()


def test_coverage_path_returns_subprocess_returncode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under ``--coverage`` ``main`` returns the first subprocess call's returncode."""
    _set_argv(monkeypatch, ["--coverage"])

    fake_result = mock.Mock(returncode=5)
    with mock.patch("subprocess.run", return_value=fake_result):
        assert main() == 5


def test_pytest_path_returns_pytest_main_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without ``--coverage`` ``main`` returns whatever ``pytest.main`` returns."""
    _set_argv(monkeypatch, [])

    with mock.patch("pytest.main", return_value=2):
        assert main() == 2
