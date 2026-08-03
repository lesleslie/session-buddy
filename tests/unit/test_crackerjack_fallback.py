"""Tests for session_buddy.utils.crackerjack.fallback."""

from __future__ import annotations

import asyncio
import sys

import pytest

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
    """When enabled, helper runs the fallback and returns its placeholder result."""
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
    assert result is None
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
