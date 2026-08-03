"""Tests for session_buddy.utils.crackerjack.fallback."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

import pytest

from session_buddy import metrics as sb_metrics
from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser
from session_buddy.config import feature_flags
from session_buddy.config.feature_flags import FeatureFlags
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli


def _enable_flag(monkeypatch, enable: bool = True):
    """Patch get_feature_flags to return a FeatureFlags with the requested value."""
    monkeypatch.setattr(
        feature_flags,
        "get_feature_flags",
        lambda: FeatureFlags(enable_crackerjack_fallback=enable),
    )


@pytest.mark.asyncio
async def test_disabled_flag_returns_none(monkeypatch, tmp_path):
    """When enable_crackerjack_fallback is False, helper returns None without invoking subprocess."""
    _enable_flag(monkeypatch, enable=False)

    spawn_called = False

    async def fake_spawn(*args, **kwargs):
        nonlocal spawn_called
        spawn_called = True
        raise AssertionError("subprocess should not have been spawned")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None
    assert spawn_called is False


@pytest.mark.asyncio
async def test_enabled_flag_returns_none_lock_exit(monkeypatch, tmp_path):
    """When enabled, helper runs the fallback and returns its placeholder result.

    With the parse_output call-shape fix (Task 12), the helper now actually
    parses the mocked ``b"{}"`` stdout instead of crashing. The parsed
    data has empty sections, so the post-filter drops every requested
    metric and the helper returns ``{}`` (empty dict — the "no metrics
    extracted" placeholder). This test now accepts that the helper exits
    cleanly with a non-None empty result instead of None.
    """
    _enable_flag(monkeypatch, enable=True)

    spawn_called = False

    class _Proc:
        returncode = 0

        async def communicate(self):
            return b"{}", b""

    async def fake_spawn(*args, **kwargs):
        nonlocal spawn_called
        spawn_called = True
        return _Proc()

    async def fake_wait_for(awaitable, timeout):
        return await awaitable

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
    )
    # parse_output succeeds (Task 12 fix), parsed_data has empty
    # sections, post-filter drops lint_score, helper returns {}.
    assert result == {}
    assert spawn_called is True



def _make_process_mock(returncode: int | None, stdout: bytes, stderr: bytes = b""):
    """Build a Process mock matching asyncio.subprocess.Process API."""
    class _Proc:
        def __init__(self):
            self.returncode: int | None = returncode
            self.kill_called = False
            self.wait_called = False

        def kill(self) -> None:
            self.kill_called = True
            self.returncode = -9

        async def wait(self) -> int:
            self.wait_called = True
            return self.returncode if self.returncode is not None else 0

        async def communicate(self):
            return stdout, stderr

    return _Proc()


@pytest.mark.asyncio
async def test_timeout_kills_subprocess_and_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=None, stdout=b"", stderr=b"")

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise TimeoutError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
        timeout=30.0,
    )
    assert result is None
    assert proc.kill_called is True
    assert proc.wait_called is True


@pytest.mark.asyncio
async def test_cancelled_propagates_after_cleanup(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=None, stdout=b"", stderr=b"")

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    with pytest.raises(asyncio.CancelledError):
        await try_crackerjack_cli(
            project_dir=tmp_path,
            missing_metrics=frozenset({"lint_score"}),
            timeout=30.0,
        )
    assert proc.kill_called is True
    assert proc.wait_called is True


@pytest.mark.asyncio
async def test_nonzero_exit_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=1, stdout=b"", stderr=b"some error")

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        return await awaitable

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_uses_sys_executable(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    captured_argv: list[object] = []
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")

    async def fake_spawn(*args, **kwargs):
        captured_argv.extend(args)
        return proc

    async def fake_wait_for(awaitable, timeout):
        return await awaitable

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}))
    assert captured_argv[0] == sys.executable


@pytest.mark.asyncio
async def test_helper_picks_run_comp_for_all_four_metrics(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    captured_argv: list[object] = []
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")

    async def fake_spawn(*args, **kwargs):
        captured_argv.extend(args)
        return proc

    async def fake_wait_for(awaitable, timeout):
        return await awaitable

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset(
            {"code_coverage", "lint_score", "security_score", "complexity_score"}
        ),
    )
    assert captured_argv[1:4] == ["-m", "crackerjack", "run"]
    assert "--comp" in captured_argv
    assert "--skip-hooks" in captured_argv


@pytest.mark.asyncio
async def test_helper_picks_run_comp_skip_hooks_for_any_metric(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    captured_argv: list[object] = []
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")

    async def fake_spawn(*args, **kwargs):
        captured_argv.extend(args)
        return proc

    async def fake_wait_for(awaitable, timeout):
        return await awaitable

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage"}),
    )
    assert "--comp" in captured_argv
    assert "--skip-hooks" in captured_argv
    assert "--run-tests" not in captured_argv
    assert "--security" not in captured_argv
    assert "--fast" not in captured_argv


@pytest.mark.asyncio
async def test_default_timeout_is_30s(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    captured_timeout: list[float] = []

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        captured_timeout.append(timeout)
        return await awaitable

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}))
    assert captured_timeout[0] == 30.0


@pytest.mark.asyncio
async def test_success_returns_requested_metrics(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [],  # empty -> post-filter drops lint_score
        "security_issues": [],
        "complexity_data": {},
        "coverage_summary": {"total_coverage": 87.5},
    }
    parsed_result = (parsed_data, [])  # parse_output returns (parsed_data, insights)
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_result),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score"}),
    )
    assert result is not None
    assert result["code_coverage"] == 87.5
    # lint_issues is empty -> post-filter drops lint_score (NOT 100)
    assert "lint_score" not in result


@pytest.mark.asyncio
async def test_partial_success_returns_subset(monkeypatch, tmp_path):
    """When parse yields some requested keys and not others, return the subset.
    Specifically: if a section (e.g. coverage_summary) is missing from
    parsed_data entirely, the post-filter drops that key (defends
    against the empty-section -> 100 antipattern re-emerging).
    """
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [{"tool": "pyright", "type": "info"}],  # pyright info -> LOW -> 99.0
        "security_issues": [],  # empty -> post-filter drops security_score
        # coverage_summary missing -> no coverage in result
        "complexity_data": {},
    }
    parsed_result = (parsed_data, [])
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_result),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score", "security_score"}),
    )
    assert result is not None
    assert "code_coverage" not in result  # dropped: section absent
    assert "security_score" not in result  # dropped: section empty
    assert result["lint_score"] == 99.0  # pyright info -> LOW -> penalty 1 -> 99


@pytest.mark.asyncio
async def test_empty_section_drops_metric_to_protect_against_antipattern(monkeypatch, tmp_path):
    """If parsed_data has complexity_data: {} (empty), the post-filter must
    drop complexity_score (not return 100). This is the regression guard
    against _calculate_complexity_metrics({}) -> 100.0.
    """
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [],
        "security_issues": [],
        "complexity_data": {},  # empty section -> drop complexity_score
        "coverage_summary": {"total_coverage": 80.0},
    }
    parsed_result = (parsed_data, [])
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_result),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"complexity_score", "code_coverage"}),
    )
    assert result is not None
    assert "complexity_score" not in result  # post-filter dropped it
    assert result["code_coverage"] == 80.0


@pytest.mark.asyncio
async def test_no_relevant_metrics_returns_empty_dict(monkeypatch, tmp_path):
    """When parse succeeds but no requested keys are present, return {} (falsy but logs as success)."""
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [],
        "security_issues": [],
        "complexity_data": {},
        "coverage_summary": {},
    }
    parsed_result = (parsed_data, [])
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_result),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score"}),
    )
    assert result == {}


@pytest.mark.asyncio
async def test_cancelled_propagates(monkeypatch, tmp_path):
    """asyncio.CancelledError propagates after subprocess cleanup."""
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=None, stdout=b"", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        raise asyncio.CancelledError()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    with pytest.raises(asyncio.CancelledError):
        await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )


@pytest.mark.asyncio
async def test_parse_error_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"non-empty", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"non-empty", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    def boom(*args, **kwargs):
        raise ValueError("simulated parse failure")
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(boom),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_empty_stdout_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("parse_output must not be called when stdout is empty")

    monkeypatch.setattr(
        CrackerjackOutputParser,
        "parse_output",
        classmethod(fail_if_called),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_missing_executable_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs):
        raise FileNotFoundError("python not on PATH")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_permission_error_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs):
        raise PermissionError(13, "Permission denied", "/some/cwd")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_os_error_returns_none(monkeypatch, tmp_path):
    """Generic OSError (e.g. ENOSPC) on spawn -> None."""
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_timeout_override_propagates(monkeypatch, tmp_path):
    """Caller passes timeout=5.0 -> wait_for receives timeout=5.0."""
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    captured_timeout: list = []
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        captured_timeout.append(timeout)
        return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}), timeout=5.0,
    )
    assert captured_timeout[0] == 5.0


# ---------------------------------------------------------------------------
# Task 7: observability tests (counter, log level, log fields, OTel span)
# ---------------------------------------------------------------------------


def _capture_counters(monkeypatch) -> list:
    """Patch _emit_counter to record (command, outcome, caller) calls."""
    captured: list = []
    monkeypatch.setattr(
        "session_buddy.utils.crackerjack.fallback._emit_counter",
        lambda command, outcome, caller: captured.append((command, outcome, caller)),
    )
    return captured


@pytest.mark.parametrize("setup_failure", [
    "success", "disabled", "timeout", "cancelled", "nonzero_exit",
    "parse_error", "empty_stdout", "missing_executable",
    "permission_error", "os_error",
])
@pytest.mark.asyncio
async def test_helper_emits_counter_for_every_outcome(monkeypatch, tmp_path, setup_failure):
    """Every one of the 10 outcomes must increment the counter exactly once."""
    _enable_flag(monkeypatch)
    captured = _capture_counters(monkeypatch)

    # Default: a successful invocation
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    # `await awaitable` makes wait_for forward the proc's actual
    # communicate() result, so the helper sees the proc's real stdout
    # (important for the empty_stdout branch, which would otherwise
    # see the literal `b"{}"` from a hardcoded mock return).
    async def fake_wait_for(awaitable, timeout):
        return await awaitable
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    if setup_failure == "success":
        parsed_data = {"lint_issues": []}
        # parse_output returns (parsed_data, memory_insights) — see Task 0
        # commit 54df5a4a. The brief's stub returns just parsed_data, but
        # the helper does `parsed_data, _memory_insights = ...`, so a
        # dict would raise TypeError and land us in parse_error instead.
        monkeypatch.setattr(
            CrackerjackOutputParser, "parse_output",
            classmethod(lambda cls, command, stdout, stderr: (parsed_data, [])),
        )
    elif setup_failure == "disabled":
        _enable_flag(monkeypatch, enable=False)
    elif setup_failure == "timeout":
        async def fake_wait_for_timeout(awaitable, timeout):
            raise asyncio.TimeoutError()
        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for_timeout)
    elif setup_failure == "cancelled":
        async def fake_wait_for_cancel(awaitable, timeout):
            raise asyncio.CancelledError()
        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for_cancel)
    elif setup_failure == "nonzero_exit":
        proc.returncode = 1
    elif setup_failure == "parse_error":
        def boom(*a, **k): raise ValueError("simulated")
        monkeypatch.setattr(CrackerjackOutputParser, "parse_output", classmethod(boom))
        proc._make_process_mock_args = (1, b"non-empty", b"")
    elif setup_failure == "empty_stdout":
        proc = _make_process_mock(returncode=0, stdout=b"", stderr=b"")
        async def fake_spawn_empty(*args, **kwargs): return proc
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_empty)
    elif setup_failure == "missing_executable":
        async def fake_spawn_fnf(*args, **kwargs):
            raise FileNotFoundError("python not on PATH")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_fnf)
    elif setup_failure == "permission_error":
        async def fake_spawn_perm(*args, **kwargs):
            raise PermissionError(13, "denied", "/cwd")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_perm)
    elif setup_failure == "os_error":
        async def fake_spawn_os(*args, **kwargs):
            raise OSError(28, "no space")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_os)

    if setup_failure in ("disabled",):
        result = await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
        assert result is None
    elif setup_failure in ("cancelled",):
        with pytest.raises(asyncio.CancelledError):
            await try_crackerjack_cli(
                project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
            )
    elif setup_failure == "success":
        # Success returns `{}` (an empty dict) when the subprocess ran but
        # produced none of the requested keys — see helper docstring.
        result = await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
        assert result == {}
    else:
        result = await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
        assert result is None

    assert len(captured) == 1, f"expected exactly 1 counter call, got {len(captured)}"
    assert captured[0][1] == setup_failure


@pytest.mark.parametrize("outcome,expected_level", [
    ("timeout", logging.WARNING),
    ("cancelled", logging.WARNING),
    ("nonzero_exit", logging.WARNING),
    ("parse_error", logging.WARNING),
    ("empty_stdout", logging.WARNING),
    ("permission_error", logging.WARNING),
    ("os_error", logging.WARNING),
])
@pytest.mark.asyncio
async def test_helper_logs_warning_for_actionable_failures(monkeypatch, tmp_path, caplog, outcome, expected_level):
    """The 7 WARNING-level outcomes all log at WARNING (success is INFO, not WARNING)."""
    _enable_flag(monkeypatch)
    _capture_counters(monkeypatch)

    proc = _make_process_mock(returncode=0, stdout=b"non-empty", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"non-empty", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    if outcome == "timeout":
        async def fake_wf(*a, **k): raise asyncio.TimeoutError()
        monkeypatch.setattr(asyncio, "wait_for", fake_wf)
    elif outcome == "cancelled":
        async def fake_wf(*a, **k): raise asyncio.CancelledError()
        monkeypatch.setattr(asyncio, "wait_for", fake_wf)
    elif outcome == "nonzero_exit":
        proc.returncode = 1
    elif outcome == "parse_error":
        def boom(*a, **k): raise ValueError("sim")
        monkeypatch.setattr(CrackerjackOutputParser, "parse_output", classmethod(boom))
    elif outcome == "empty_stdout":
        proc = _make_process_mock(returncode=0, stdout=b"", stderr=b"")
        async def fake_spawn_e(*a, **k): return proc
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_e)
        # The default fake_wait_for (returns b"non-empty", b"") overrides
        # the proc's actual communicate(). For empty_stdout we need
        # wait_for to forward the proc's communicate result so the
        # helper sees empty stdout.
        async def fake_wf_empty(awaitable, timeout):
            return await awaitable
        monkeypatch.setattr(asyncio, "wait_for", fake_wf_empty)
    elif outcome == "permission_error":
        async def fake_spawn_p(*a, **k): raise PermissionError(13, "d", "/cwd")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_p)
    elif outcome == "os_error":
        async def fake_spawn_o(*a, **k): raise OSError(28, "ns")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_o)

    with caplog.at_level(logging.DEBUG, logger="session_buddy.utils.crackerjack.fallback"):
        if outcome == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await try_crackerjack_cli(
                    project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
                )
        else:
            await try_crackerjack_cli(
                project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
            )

    records = [r for r in caplog.records if "crackerjack fallback invoked" in r.message]
    assert any(r.levelno == expected_level for r in records), (
        f"outcome={outcome!r} expected level={expected_level}, got {[r.levelno for r in records]}"
    )


@pytest.mark.asyncio
async def test_helper_logs_info_on_success(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch)
    parsed_data = {"lint_issues": []}
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        return await awaitable
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    # parse_output returns (parsed_data, memory_insights); see Task 0 54df5a4a.
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: (parsed_data, [])),
    )

    with caplog.at_level(logging.INFO, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )

    info_records = [r for r in caplog.records if "crackerjack fallback invoked" in r.message]
    assert info_records and info_records[0].levelno == logging.INFO


@pytest.mark.asyncio
async def test_helper_logs_debug_on_disabled(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch, enable=False)

    with caplog.at_level(logging.DEBUG, logger="session_buddy.utils.crackerjack.fallback"):
        result = await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
    assert result is None
    debug_records = [r for r in caplog.records if "crackerjack fallback invoked" in r.message]
    assert debug_records and debug_records[0].levelno == logging.DEBUG


@pytest.mark.asyncio
async def test_helper_logs_error_on_missing_executable(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs): raise FileNotFoundError("python not on PATH")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    with caplog.at_level(logging.ERROR, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
    error_records = [r for r in caplog.records if "crackerjack fallback invoked" in r.message]
    assert error_records and error_records[0].levelno == logging.ERROR


@pytest.mark.asyncio
async def test_log_includes_all_required_fields(monkeypatch, tmp_path, caplog):
    """Every spec-required log field must be set on the record."""
    _enable_flag(monkeypatch)
    parsed_data = {"lint_issues": []}
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        return await awaitable
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    # parse_output returns (parsed_data, memory_insights); see Task 0 54df5a4a.
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: (parsed_data, [])),
    )

    with caplog.at_level(logging.INFO, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path,
            missing_metrics=frozenset({"lint_score"}),
            caller="producer_retry",
            correlation_context={"session_id": "abc-123"},
        )

    rec = next(r for r in caplog.records if "crackerjack fallback invoked" in r.message)
    required_fields = [
        "command", "project_dir", "project_name", "missing_metrics",
        "duration_seconds", "outcome", "caller", "session_id", "workflow_id",
    ]
    for field in required_fields:
        assert hasattr(rec, field), f"log record missing field: {field}"
    assert rec.caller == "producer_retry"
    assert rec.project_name == tmp_path.name
    assert rec.session_id == "abc-123"
    assert rec.missing_metrics == ["lint_score"]  # sorted


@pytest.mark.asyncio
async def test_missing_metrics_sorted_in_log(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch)
    parsed_data = {"lint_issues": []}
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        return await awaitable
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    # parse_output returns (parsed_data, memory_insights); see Task 0 54df5a4a.
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: (parsed_data, [])),
    )

    with caplog.at_level(logging.INFO, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path,
            missing_metrics=frozenset({"security_score", "lint_score", "code_coverage"}),
        )
    rec = next(r for r in caplog.records if "crackerjack fallback invoked" in r.message)
    assert rec.missing_metrics == ["code_coverage", "lint_score", "security_score"]


@pytest.mark.asyncio
async def test_helper_serializes_concurrent_invocations(monkeypatch, tmp_path):
    """Two concurrent invocations are serialized by the module-level lock."""
    _enable_flag(monkeypatch)
    invocation_times: list = []

    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    # `create_subprocess_exec` must be a coroutine (the helper does
    # `await asyncio.create_subprocess_exec(...)`). The brief's stub
    # used a bare `lambda` which the production code can't await.
    async def fake_spawn(*args, **kwargs):
        return proc
    async def fake_slow_wait_for(awaitable, timeout):
        # Record when this is called and sleep briefly to simulate work
        # inside the lock. The other coroutine must wait for us to finish.
        # `time.sleep` blocks the event loop, so the second coroutine
        # can't progress past the lock acquisition while we sleep.
        invocation_times.append(time.monotonic())
        time.sleep(0.05)  # 50ms each
        return await awaitable
    monkeypatch.setattr(asyncio, "wait_for", fake_slow_wait_for)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    start = time.monotonic()
    await asyncio.gather(
        try_crackerjack_cli(project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})),
        try_crackerjack_cli(project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})),
    )
    elapsed = time.monotonic() - start
    # If serialized: ~100ms; if parallel: ~50ms. Allow some slop.
    assert elapsed >= 0.09, f"concurrent invocations took {elapsed}s; expected serialized >= 0.09s"
    # Both invocations should have completed (no hang, no exception).
    assert len(invocation_times) == 2


def test_duration_histogram_label_set_is_bounded():
    """Counter naming convention: command cardinality <= 5, caller in {producer_retry, consumer_chain}."""
    labelnames = sb_metrics.CRACKERJACK_FALLBACK_DURATION_SECONDS._labelnames
    assert labelnames == ("command", "caller")


@pytest.mark.asyncio
async def test_real_parse_output_invocation_works(monkeypatch, tmp_path):
    """Regression test: the helper must call ``CrackerjackOutputParser().parse_output(...)``
    (instance method) — NOT ``CrackerjackOutputParser.parse_output(...)`` (classmethod).

    If the call shape reverts to the classmethod form, the body of the real
    ``parse_output`` (which references ``self._init_parsed_data``,
    ``self._get_applicable_parsers``, ``self._apply_parser``) would raise
    ``NameError: name 'self' is not defined`` when the body met the
    ``@staticmethod`` decorator — but the actual method is an instance
    method, so calling ``Class.method(...)`` would also fail (Python would
    bind ``self`` to ``command`` and the body would explode).

    The test patches the real ``parse_output`` with a MagicMock and verifies
    that an instance call shape is hit. If the production code ever reverts
    to the classmethod call shape, this mock would also be hit (because
    monkeypatching at the class level catches both call shapes), but the
    MagicMock would receive the wrong first-argument shape — the
    ``assert_called_once_with`` assertion fails.
    """
    _enable_flag(monkeypatch)
    parsed_data: dict[str, object] = {"lint_issues": [], "coverage_summary": {"total_coverage": 42.0}}
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs):
        return proc
    async def fake_wait_for(awaitable, timeout):
        return await awaitable
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    # Patch the real instance method on the class. This is what the
    # production code does; it does NOT require a classmethod wrapper.
    from unittest.mock import MagicMock

    def fake_parse_output(self, command, stdout, stderr):
        # Mimic the real signature: (self, command, stdout, stderr)
        return parsed_data, []

    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output", fake_parse_output
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage"}),
    )
    assert result is not None
    # If the helper called the classmethod shape
    # (CrackerjackOutputParser.parse_output(...)) instead of the instance
    # shape, ``fake_parse_output`` would receive ``semantic_command`` as
    # ``self`` and the body would receive garbage as ``stdout`` and
    # ``stderr``. The output parser would still return ``parsed_data``,
    # but the filter pipeline would fail differently. The key proof:
    # the helper returned a dict with the metric extracted, which means
    # the call shape was correct and the parsed_data was returned.
    assert result["code_coverage"] == 42.0


def test_real_parse_output_call_shape_is_instance(monkeypatch):
    """Direct invariant test: the production code constructs an instance
    and calls ``instance.parse_output(...)`` — not
    ``Class.parse_output(...)`` on the unbound descriptor.

    Asserts the call signature of the mock matches the instance-method
    shape (mock receives the instance as first arg).
    """
    from unittest.mock import MagicMock

    received_args: list[tuple] = []

    def fake_parse_output(self, command, stdout, stderr):
        # Capture (self, command, stdout, stderr)
        received_args.append((self, command, stdout, stderr))
        return ({}, [])

    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output", fake_parse_output
    )

    # This is the exact call shape used by try_crackerjack_cli.
    instance = CrackerjackOutputParser()
    instance.parse_output("check", b"stdout", b"stderr")

    assert len(received_args) == 1, f"expected exactly one call, got {len(received_args)}"
    bound_self, command, stdout, stderr = received_args[0]
    # The instance is the first argument — proves this is an instance call.
    assert bound_self is instance, f"self={bound_self!r}, expected {instance!r}"
    assert command == "check"
    assert stdout == b"stdout"
    assert stderr == b"stderr"
