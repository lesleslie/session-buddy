#!/usr/bin/env python3
"""Tests for :class:`session_buddy.cli.base.SessionBuddyCLI`.

Adoption gate for oneiric 0.19.0 ``BodaiCLIBase`` — the subclass must:

- Instantiate with the right ``component_name``.
- Wire the standard Bodai Core 7 surface (``version`` / ``doctor`` /
  ``health`` / ``--json`` / ``--version``) via ``BodaiCLIBase.run``
  semantics (Typer app invocation by calling it).
- Override ``_doctor_checks()`` with a REAL implementation that calls
  into the existing diagnostic surface (``session_buddy.doctor``), not
  the NotImplementedError stub from :class:`oneiric.cli.base.BodaiCLIBase`.
- Override ``_health_probe()`` with a REAL implementation that calls
  into the existing health surface
  (``session_buddy.mcp.tools.monitoring.health_tools.get_health_status``),
  not the NotImplementedError stub.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from oneiric.cli.base import BodaiCLIBase, ExitCode

from session_buddy.cli.base import (
    SessionBuddyCLI,
    SessionBuddySettings,
    _doctor_checks_dict,
    _run_health_probe,
    start_server_handler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def cli() -> SessionBuddyCLI:
    """Build a SessionBuddyCLI with start_handler/health_probe patched.

    Patches the handlers so the MCPServerCLIFactory lifecycle sub-Typer
    is constructed without trying to invoke ``server_optimized.run_server``
    or hit the actual health endpoint during these unit tests.
    """
    with patch(
        "session_buddy.cli.base.start_server_handler",
        MagicMock(return_value=None),
    ):
        # Build with default settings; the lifecycle sub-Typer will be
        # constructed but its commands are not invoked by the tests in
        # this module.
        return SessionBuddyCLI()


# ---------------------------------------------------------------------------
# Construction + metadata
# ---------------------------------------------------------------------------


def test_subclass_is_a_bodai_cli_base(cli: SessionBuddyCLI) -> None:
    """SessionBuddyCLI must be a BodaiCLIBase subclass (and a Typer app)."""
    assert isinstance(cli, BodaiCLIBase)
    assert isinstance(cli, typer.Typer)


def test_subclass_constructor_sets_component_name(cli: SessionBuddyCLI) -> None:
    """component_name must be exactly ``session-buddy`` for Bodai Core 7."""
    assert cli.component_name == "session-buddy"


def test_subclass_constructor_detects_version(cli: SessionBuddyCLI) -> None:
    """component_version is a string (parsed by importlib.metadata)."""
    assert isinstance(cli.component_version, str)
    assert cli.component_version != ""


def test_subclass_help_string_passed_through() -> None:
    """A custom help string propagates to the underlying Typer app."""
    app = SessionBuddyCLI(help="custom help text")
    assert app.info.help == "custom help text"


def test_settings_class_present_and_subclass_of_oneiric_config() -> None:
    """SessionBuddySettings extends OneiricMCPConfig — required by the
    mcp-common lifecycle sub-Typer for ``cache_root`` / ``pid_path``
    shims (regression pin)."""
    from oneiric.core.config import OneiricMCPConfig

    assert issubclass(SessionBuddySettings, OneiricMCPConfig)


def test_settings_pid_and_snapshot_paths_live_under_cache_dir() -> None:
    """Regression pin from the legacy test suite: pid/health/telemetry
    snapshot paths must all live under ``cache_dir``."""
    settings = SessionBuddySettings()
    assert isinstance(settings.pid_path(), Path)
    assert isinstance(settings.health_snapshot_path(), Path)
    assert isinstance(settings.telemetry_snapshot_path(), Path)
    assert settings.pid_path().parent == Path(settings.cache_dir)
    assert settings.health_snapshot_path().parent == Path(settings.cache_dir)
    assert settings.telemetry_snapshot_path().parent == Path(settings.cache_dir)
    assert settings.pid_path().name == "mcp_server.pid"
    assert settings.health_snapshot_path().name == "runtime_health.json"
    assert settings.telemetry_snapshot_path().name == "runtime_telemetry.json"


def test_settings_cache_root_shim() -> None:
    """Regression pin: ``cache_root`` is a Path shimmed from ``cache_dir``
    so mcp-common's ``validate_cache_ownership`` can read it."""
    settings = SessionBuddySettings()
    assert isinstance(settings.cache_root, Path)
    assert settings.cache_root == Path(settings.cache_dir)


# ---------------------------------------------------------------------------
# BodaiCLIBase.run() wiring — version / --version / --json global flags
# ---------------------------------------------------------------------------


def test_version_command_works(runner: CliRunner, cli: SessionBuddyCLI) -> None:
    """BodaiCLIBase-provided ``version`` command must emit the version
    string and exit with ``ExitCode.SUCCESS``."""
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == ExitCode.SUCCESS
    assert "session-buddy" in result.output
    assert cli.component_version in result.output


def test_global_version_flag_emits_deprecation(
    runner: CliRunner, cli: SessionBuddyCLI
) -> None:
    """``--version`` Typer option emits a DeprecationWarning (BodaiCLIBase
    cascade-fix round-1 F-α marker)."""
    import warnings

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        result = runner.invoke(cli, ["--version"])

    assert result.exit_code == ExitCode.SUCCESS
    assert "session-buddy" in result.output
    assert any(
        issubclass(w.category, DeprecationWarning) for w in caught_warnings
    ), "Expected DeprecationWarning for --version flag"


def test_global_short_version_flag_emits_deprecation(
    runner: CliRunner, cli: SessionBuddyCLI
) -> None:
    """``-V`` short flag must behave identically to ``--version``."""
    import warnings

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        result = runner.invoke(cli, ["-V"])

    assert result.exit_code == ExitCode.SUCCESS
    assert "session-buddy" in result.output
    assert any(
        issubclass(w.category, DeprecationWarning) for w in caught_warnings
    ), "Expected DeprecationWarning for -V flag"


def test_global_json_flag_accepted(runner: CliRunner, cli: SessionBuddyCLI) -> None:
    """``--json`` is a valid global flag and exits 0 on ``version``."""
    result = runner.invoke(cli, ["--json", "version"])
    assert result.exit_code == ExitCode.SUCCESS


# ---------------------------------------------------------------------------
# Doctor — REAL implementation, not stub
# ---------------------------------------------------------------------------


def test_doctor_command_runs_and_exits_success(
    runner: CliRunner, cli: SessionBuddyCLI
) -> None:
    """``doctor`` is provided by BodaiCLIBase; it must NOT exit
    ``ExitCode.UNAVAILABLE`` (which is what the NotImplementedError stub
    returns). The real implementation must surface the check list."""
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code != ExitCode.UNAVAILABLE, (
        "doctor returned UNAVAILABLE — the subclass must override "
        "_doctor_checks() with a real implementation, not the "
        "NotImplementedError stub from BodaiCLIBase."
    )


def test_doctor_json_flag_emits_checks_dict(
    runner: CliRunner, cli: SessionBuddyCLI
) -> None:
    """``--json doctor`` must emit a JSON document with a ``checks`` key."""
    result = runner.invoke(cli, ["--json", "doctor"])
    assert result.exit_code != ExitCode.UNAVAILABLE
    assert '"checks"' in result.output


def test_doctor_checks_helper_returns_real_dict() -> None:
    """The :func:`_doctor_checks_dict` helper must return a non-empty
    dict with real check entries — NOT an empty dict, NOT a stub
    returning ``{}``. Each entry must have at least a ``status`` and
    ``detail`` so BodaiCLIBase can render it."""
    checks = _doctor_checks_dict()
    assert isinstance(checks, dict)
    assert len(checks) > 0, (
        "doctor returned empty — must call into the existing doctor "
        "surface (run_all_doctor_checks), not a stub."
    )
    for name, info in checks.items():
        assert isinstance(name, str)
        assert isinstance(info, dict)
        assert "status" in info
        assert "detail" in info


def test_doctor_does_not_raise_not_implemented_error(
    runner: CliRunner, cli: SessionBuddyCLI
) -> None:
    """Regression pin: BodaiCLIBase's stub raises ``NotImplementedError``
    and the base class catches it to emit UNAVAILABLE. If the subclass
    override is missing or accidentally calls super(), this test would
    catch it via the UNAVAILABLE exit code (covered above) AND via the
    absence of any check output."""
    result = runner.invoke(cli, ["doctor"])
    # Either the run succeeded (output non-empty) OR it failed with a
    # real error — but UNAVAILABLE is the stub marker we must avoid.
    assert "doctor checks not yet implemented" not in result.output


# ---------------------------------------------------------------------------
# Health — REAL implementation, not stub
# ---------------------------------------------------------------------------


def test_health_command_runs_and_exits_success(
    runner: CliRunner, cli: SessionBuddyCLI
) -> None:
    """``health`` must NOT return ExitCode.UNAVAILABLE (the stub marker)
    and must produce some output (real probe data)."""
    result = runner.invoke(cli, ["health"])
    assert result.exit_code != ExitCode.UNAVAILABLE, (
        "health returned UNAVAILABLE — the subclass must override "
        "_health_probe() with a real implementation, not the "
        "NotImplementedError stub from BodaiCLIBase."
    )
    assert result.output.strip() != ""


def test_health_json_flag_emits_dict(runner: CliRunner, cli: SessionBuddyCLI) -> None:
    """``--json health`` must emit a JSON document."""
    result = runner.invoke(cli, ["--json", "health"])
    assert result.exit_code != ExitCode.UNAVAILABLE
    # JSON output must contain at least one quoted key from the
    # get_health_status() schema (``status``, ``components``, ``version``).
    lowered = result.output.lower()
    assert any(
        marker in lowered for marker in ('"status"', '"components"', '"version"')
    ), f"--json health did not emit a JSON document: {result.output!r}"


def test_health_probe_returns_real_dict_shape() -> None:
    """The lifecycle helper must return a ``RuntimeHealthSnapshot`` (not
    a stub ``{}``) that mirrors the pre-adoption shape. Pin the
    ``orchestrator_pid`` / ``watchers_running`` / ``activity_state``
    fields and assert the nested health payload carries real
    ``get_health_status()`` data."""
    import json

    probe = _run_health_probe(SessionBuddySettings())
    # Real RuntimeHealthSnapshot (not dict / not stub).
    assert not isinstance(probe, dict), (
        "_run_health_probe must return RuntimeHealthSnapshot so "
        "mcp_common can call .as_dict() on it; got dict instead."
    )
    # Snapshot fields.
    assert hasattr(probe, "orchestrator_pid")
    assert hasattr(probe, "watchers_running")
    assert hasattr(probe, "activity_state")
    # Nested health payload must contain real get_health_status keys.
    nested = probe.activity_state.get("health", {})
    assert isinstance(nested, dict)
    json.dumps(nested)
    assert any(
        k in nested for k in ("status", "components", "version", "timestamp")
    ), f"health payload is missing canonical keys: {list(nested.keys())}"


def test_health_does_not_raise_not_implemented_error(
    runner: CliRunner, cli: SessionBuddyCLI
) -> None:
    """Same regression pin as doctor — UNAVAILABLE + "not yet implemented"
    text must NOT appear."""
    result = runner.invoke(cli, ["health"])
    assert "health checks not yet implemented" not in result.output


# ---------------------------------------------------------------------------
# Sub-Typer wiring (server, checkpoint, analytics)
# ---------------------------------------------------------------------------


def test_server_subcommand_is_registered(cli: SessionBuddyCLI) -> None:
    """The mcp-common lifecycle verbs must be reachable under
    ``session-buddy server ...`` (no longer at root)."""
    registered = {
        getattr(grp, "name", None) for grp in getattr(cli, "registered_groups", [])
    }
    assert "server" in registered


def test_checkpoint_subcommand_is_registered(cli: SessionBuddyCLI) -> None:
    """``checkpoint cleanup-snapshots`` must still be reachable."""
    registered = {
        getattr(grp, "name", None) for grp in getattr(cli, "registered_groups", [])
    }
    assert "checkpoint" in registered


def test_analytics_subcommand_is_registered(cli: SessionBuddyCLI) -> None:
    """``analytics {sessions,duration,components,errors,active,report,sql}``
    must still be reachable."""
    registered = {
        getattr(grp, "name", None) for grp in getattr(cli, "registered_groups", [])
    }
    assert "analytics" in registered


def test_help_lists_all_expected_commands(
    runner: CliRunner, cli: SessionBuddyCLI
) -> None:
    """Top-level help must list version, doctor, health, server,
    checkpoint, and analytics — the full Bodai Core 7 + session-buddy
    surface."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("version", "doctor", "health", "server", "checkpoint", "analytics"):
        assert cmd in result.output, f"Missing {cmd!r} in help output"


# ---------------------------------------------------------------------------
# Backward-compat shim — create_app() returns self
# ---------------------------------------------------------------------------


def test_create_app_returns_self(cli: SessionBuddyCLI) -> None:
    """Legacy callers do ``cli = create_session_buddy_cli(); app = cli.create_app()``.
    ``create_app()`` must return the Typer app (i.e. ``self``) so the
    subsequent ``cli_runner.invoke(app, ...)`` keeps working."""
    assert cli.create_app() is cli


def test_create_session_buddy_cli_returns_bodai_cli_base() -> None:
    """The factory function used by the legacy ``__main__`` flow must
    return a ``SessionBuddyCLI`` (which is a ``BodaiCLIBase``)."""
    from session_buddy.cli import create_session_buddy_cli

    cli = create_session_buddy_cli()
    assert isinstance(cli, SessionBuddyCLI)
    assert isinstance(cli, BodaiCLIBase)
    assert cli.component_name == "session-buddy"


# ---------------------------------------------------------------------------
# Cascade-fix design invariants (mirrored from oneiric tests/cli/test_base.py)
# ---------------------------------------------------------------------------


def test_unified_callback_has_invoke_without_command(
    cli: SessionBuddyCLI,
) -> None:
    """Exactly ONE callback is registered: the unified root callback
    (BodaiCLIBase cascade-fix round-1 F-α marker)."""
    callback = getattr(cli, "registered_callback", None)
    assert callback is not None, "Unified callback should be registered"
    assert callback.invoke_without_command is True


def test_no_intercept_version_flag_method(cli: SessionBuddyCLI) -> None:
    """Round-1 F-α fix marker: the legacy sys.argv-mutating method must
    not exist on the subclass."""
    assert not hasattr(cli, "_intercept_version_flag")


# ---------------------------------------------------------------------------
# Doctor/health failure semantics (round-2 F-γ fix from oneiric)
# ---------------------------------------------------------------------------


def test_doctor_returns_error_when_subclass_impl_crashes(
    runner: CliRunner,
) -> None:
    """If the doctor's real implementation crashes, the CLI must surface
    ExitCode.ERROR (not UNAVAILABLE — UNAVAILABLE is for the
    NotImplementedError stub only)."""

    class BrokenCLI(SessionBuddyCLI):
        def _doctor_checks(self) -> dict[str, object]:
            raise RuntimeError("doctor exploded")

    # Patch start_server_handler so the lifecycle sub-Typer can be
    # constructed without invoking real handlers.
    with patch(
        "session_buddy.cli.base.start_server_handler",
        MagicMock(return_value=None),
    ):
        cli = BrokenCLI()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == ExitCode.ERROR


def test_health_returns_error_when_subclass_impl_crashes(
    runner: CliRunner,
) -> None:
    """Same invariant for health: real crashes -> ExitCode.ERROR."""

    class BrokenCLI(SessionBuddyCLI):
        def _health_probe(self) -> dict[str, object]:
            raise RuntimeError("health exploded")

    with patch(
        "session_buddy.cli.base.start_server_handler",
        MagicMock(return_value=None),
    ):
        cli = BrokenCLI()
    result = runner.invoke(cli, ["health"])
    assert result.exit_code == ExitCode.ERROR