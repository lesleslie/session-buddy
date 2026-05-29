from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _load_subprocess_executor_module():
    repo_root = Path(__file__).resolve().parents[2]

    if "session_buddy" not in sys.modules:
        package = types.ModuleType("session_buddy")
        package.__path__ = [str(repo_root / "session_buddy")]  # type: ignore[attr-defined]
        sys.modules["session_buddy"] = package

    utils_package_name = "session_buddy.utils"
    if utils_package_name not in sys.modules:
        utils_package = types.ModuleType(utils_package_name)
        utils_package.__path__ = [str(repo_root / "session_buddy" / "utils")]  # type: ignore[attr-defined]
        sys.modules[utils_package_name] = utils_package

    module_path = repo_root / "session_buddy" / "utils" / "subprocess_executor.py"
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.subprocess_executor",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


subprocess_executor = _load_subprocess_executor_module()
SafeSubprocess = subprocess_executor.SafeSubprocess
_get_safe_environment = subprocess_executor._get_safe_environment


def test_get_safe_environment_filters_sensitive_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_TOKEN", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    monkeypatch.setenv("PUBLIC_VALUE", "visible")

    safe_env = _get_safe_environment()

    assert "PUBLIC_VALUE" in safe_env
    assert safe_env["PUBLIC_VALUE"] == "visible"
    assert "SESSION_TOKEN" not in safe_env
    assert "DATABASE_URL" not in safe_env


def test_validate_command_allows_inline_python_source() -> None:
    command = ["python", "-c", "print('hello; still code')"]

    validated = SafeSubprocess.validate_command(command, {"python"})

    assert validated == command


def test_validate_command_rejects_shell_metacharacters() -> None:
    with pytest.raises(ValueError, match="Shell metacharacter"):
        SafeSubprocess.validate_command(["echo", "a|b"], {"echo"})

    with pytest.raises(ValueError, match="shell substitution"):
        SafeSubprocess.validate_command(["echo", "$(whoami)"], {"echo"})


def test_validate_command_rejects_empty_and_disallowed_commands() -> None:
    with pytest.raises(ValueError, match="Empty command"):
        SafeSubprocess.validate_command([], {"echo"})

    with pytest.raises(ValueError, match="Command not allowed: rm"):
        SafeSubprocess.validate_command(["rm", "-rf", "/"], {"echo"})


def test_run_safe_normalizes_python_and_enforces_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setenv("SESSION_SECRET", "redacted")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = SafeSubprocess.run_safe(["python", "-V"], allowed_commands={"python"})

    assert result.returncode == 0
    assert captured["command"][0] == sys.executable
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["check"] is False
    assert "SESSION_SECRET" not in captured["kwargs"]["env"]


def test_run_safe_serializes_ordered_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    acquired: list[int] = []
    released: list[int] = []
    monkeypatch.setattr(subprocess_executor, "_extract_ordered_echo_index", lambda _cmd: 7)
    monkeypatch.setattr(
        subprocess_executor,
        "_acquire_order_slot",
        lambda index: acquired.append(index),
    )
    monkeypatch.setattr(
        subprocess_executor,
        "_release_order_slot",
        lambda index: released.append(index),
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = SafeSubprocess.run_safe(["echo", "test_7"], allowed_commands={"echo"})

    assert result.returncode == 0
    assert acquired == [7]
    assert released == [7]
    assert captured["command"] == ["echo", "test_7"]


def test_popen_safe_uses_sanitized_environment_and_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_process = MagicMock()
    fake_process.wait.return_value = None

    def fake_popen(command: list[str], **kwargs: object) -> MagicMock:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return fake_process

    monkeypatch.setenv("API_TOKEN", "redacted")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    process = SafeSubprocess.popen_safe(["python3", "-c", "print('ok')"], allowed_commands={"python3"})

    assert process is fake_process
    assert captured["command"][0] == sys.executable
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["stdout"] is subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] is subprocess.DEVNULL
    assert "API_TOKEN" not in captured["kwargs"]["env"]


def test_ordered_echo_helpers_cover_slot_progression(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLock:
        def __init__(self) -> None:
            self.wait_calls = 0
            self.notified = False

        def __enter__(self) -> FakeLock:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def wait(self) -> None:
            self.wait_calls += 1
            subprocess_executor._NEXT_ORDERED_ECHO_INDEX = 4

        def notify_all(self) -> None:
            self.notified = True

    fake_lock = FakeLock()
    monkeypatch.setattr(subprocess_executor, "_ORDER_LOCK", fake_lock)
    monkeypatch.setattr(subprocess_executor, "_NEXT_ORDERED_ECHO_INDEX", 3)

    assert subprocess_executor._extract_ordered_echo_index(["echo", "test_4"]) == 4
    assert subprocess_executor._extract_ordered_echo_index(["echo", "nope"]) is None
    assert subprocess_executor._extract_ordered_echo_index(["git", "test_4"]) is None

    subprocess_executor._acquire_order_slot(4)
    assert fake_lock.wait_calls == 1

    subprocess_executor._release_order_slot(4)
    assert fake_lock.notified is True
    assert subprocess_executor._NEXT_ORDERED_ECHO_INDEX == 5


def test_release_order_slot_ignores_wrong_index(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLock:
        def __init__(self) -> None:
            self.notified = False

        def __enter__(self) -> FakeLock:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def notify_all(self) -> None:
            self.notified = True

    fake_lock = FakeLock()
    monkeypatch.setattr(subprocess_executor, "_ORDER_LOCK", fake_lock)
    monkeypatch.setattr(subprocess_executor, "_NEXT_ORDERED_ECHO_INDEX", 10)

    subprocess_executor._release_order_slot(9)

    assert fake_lock.notified is False
    assert subprocess_executor._NEXT_ORDERED_ECHO_INDEX == 10


def test_inline_python_argument_detection() -> None:
    assert subprocess_executor._is_inline_python_code_argument(
        ["python", "-c", "print('a;b')"],
        2,
    )
    assert not subprocess_executor._is_inline_python_code_argument(
        ["python", "-c", "print('a;b')"],
        1,
    )
    assert not subprocess_executor._is_inline_python_code_argument(
        ["echo", "a;b"],
        1,
    )


def test_normalize_command_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess_executor.sys, "executable", "/usr/bin/python3")

    assert subprocess_executor._normalize_command_executable([]) == []
    assert subprocess_executor._normalize_command_executable(["python", "-V"]) == [
        "/usr/bin/python3",
        "-V",
    ]
    assert subprocess_executor._normalize_command_executable(["python3", "-V"]) == [
        "/usr/bin/python3",
        "-V",
    ]
    assert subprocess_executor._normalize_command_executable(["git", "status"]) == [
        "git",
        "status",
    ]
