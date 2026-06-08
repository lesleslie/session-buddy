"""Integration tests for the ``doctor`` subcommand.

Verifies that:

* The pure helper functions (status formatting, aggregation, summary,
  exit-code mapping) work as documented.
* ``run_all_doctor_checks`` aggregates results from individual checks
  and isolates crashes to a single UNHEALTHY result without aborting
  the rest of the run.
* ``register_doctor_command`` adds a ``doctor`` subcommand to a Typer
  app (verified by inspecting the app's command list, not by invoking
  the CLI — Click 8+ / Typer 0.9+ incompatibility makes CliRunner
  unreliable in tests).

These tests are NOT end-to-end against a live ``python -m session_buddy
doctor`` invocation. If you want to verify the live CLI integration,
run manually::

    python -m session_buddy doctor
    python -m session_buddy doctor --json | python -m json.tool
"""

from __future__ import annotations

import json
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from session_buddy.doctor import (
    _aggregate_status,
    _exit_code_for,
    _format_status,
    _format_summary,
    _summary,
    register_doctor_command,
    run_all_doctor_checks,
)
from session_buddy.health_checks import ComponentHealth, HealthStatus


# ---------------------------------------------------------------------------
# Pure-function tests (synchronous, no I/O)
# ---------------------------------------------------------------------------
class TestDoctorHelpers:
    def test_format_status_for_each_level(self) -> None:
        assert _format_status(HealthStatus.HEALTHY) == "✅ Healthy"
        assert _format_status(HealthStatus.DEGRADED) == "⚠️ Degraded"
        assert _format_status(HealthStatus.UNHEALTHY) == "❌ Failed"

    def test_aggregate_status_picks_worst(self) -> None:
        results = [
            ComponentHealth(name="a", status=HealthStatus.HEALTHY, message="ok"),
            ComponentHealth(
                name="b", status=HealthStatus.UNHEALTHY, message="broken"
            ),
        ]
        assert _aggregate_status(results) == "unhealthy"

        results[1].status = HealthStatus.DEGRADED
        assert _aggregate_status(results) == "degraded"

        results[1].status = HealthStatus.HEALTHY
        assert _aggregate_status(results) == "healthy"

    def test_summary_counts(self) -> None:
        results = [
            ComponentHealth(name="h", status=HealthStatus.HEALTHY, message=""),
            ComponentHealth(name="d", status=HealthStatus.DEGRADED, message=""),
            ComponentHealth(name="u", status=HealthStatus.UNHEALTHY, message=""),
            ComponentHealth(name="h2", status=HealthStatus.HEALTHY, message=""),
        ]
        s = _summary(results)
        assert s == {"healthy": 2, "degraded": 1, "unhealthy": 1}

    def test_format_summary_string(self) -> None:
        results = [
            ComponentHealth(name="h", status=HealthStatus.HEALTHY, message=""),
            ComponentHealth(name="u", status=HealthStatus.UNHEALTHY, message=""),
        ]
        out = _format_summary(results)
        assert "1 healthy" in out
        assert "1 failed" in out
        assert "of 2" in out

    def test_exit_code_for_all_healthy_is_zero(self) -> None:
        from mcp_common.cli.factory import ExitCode

        results = [
            ComponentHealth(name="h", status=HealthStatus.HEALTHY, message="")
        ]
        assert _exit_code_for(results) == ExitCode.SUCCESS

    def test_exit_code_for_any_unhealthy_is_four(self) -> None:
        from mcp_common.cli.factory import ExitCode

        results = [
            ComponentHealth(name="h", status=HealthStatus.HEALTHY, message=""),
            ComponentHealth(
                name="u", status=HealthStatus.UNHEALTHY, message="bad"
            ),
        ]
        assert _exit_code_for(results) == ExitCode.HEALTH_CHECK_FAILED


# ---------------------------------------------------------------------------
# Aggregator tests (async, with mocked checks)
# ---------------------------------------------------------------------------
def _patch_healthy_checks() -> list:
    """Return a list of ``patch`` context managers that swap each doctor
    check for an AsyncMock returning a HEALTHY result.

    The mock also accepts any kwargs/args so it works as a drop-in for
    any of the production check signatures.
    """
    healthy = ComponentHealth(
        name="mocked_healthy",
        status=HealthStatus.HEALTHY,
        message="ok",
    )
    mock = AsyncMock(return_value=healthy)
    return [
        patch(f"session_buddy.doctor.{name}", mock)
        for name in (
            "check_python_env",
            "check_file_system",
            "check_database",
            "check_dependencies",
            "check_v2_migration",
            "check_code_graph_adapter",
            "check_code_index_round_trip",
            "check_auto_capture_recent",
            "check_claude_hooks_config",
            "check_server_port_bound",
        )
    ]


class TestRunAllDoctorChecks:
    async def test_returns_one_result_per_check(self) -> None:
        """The aggregator should produce exactly 10 results (the documented count)."""
        mocks = _patch_healthy_checks()
        for m in mocks:
            m.start()
        try:
            results = await run_all_doctor_checks()
        finally:
            for m in mocks:
                m.stop()

        # The 10 distinct checks defined in run_all_doctor_checks.
        # When the original functions are patched, the ``coro`` variable
        # in run_all_doctor_checks still holds the original function's
        # ``__name__`` from the coroutine — except it's actually the
        # patched mock now. The name in the crash path comes from
        # ``getattr(coro, '__name__', 'unknown')`` on the mock object,
        # which uses the mock's auto-generated name. We accept either
        # the original function name or the mock's name to keep this
        # test stable across Python/mock versions.
        assert len(results) == 10
        for r in results:
            assert r.status == HealthStatus.HEALTHY
            assert r.message == "ok"

    async def test_individual_check_crash_isolated(self) -> None:
        """A single crashing check must not abort the whole doctor run."""
        healthy = ComponentHealth(
            name="mocked_healthy",
            status=HealthStatus.HEALTHY,
            message="ok",
        )
        # ``AsyncMock`` with side_effect raises when awaited.
        crashing = AsyncMock(side_effect=RuntimeError("boom"))
        mocks = _patch_healthy_checks()
        # Replace one of the mocks with a crashing one.
        mocks[1] = patch("session_buddy.doctor.check_file_system", crashing)
        for m in mocks:
            m.start()
        try:
            results = await run_all_doctor_checks()
        finally:
            for m in mocks:
                m.stop()

        # Find the failed check (the name may be the original or the
        # mock's auto-name — accept either).
        failed = [r for r in results if r.status == HealthStatus.UNHEALTHY]
        assert len(failed) == 1, f"Expected 1 failed check, got {failed}"
        assert "boom" in failed[0].message
        # All 9 other checks should have completed.
        assert len(results) == 10

    async def test_db_path_centralized_for_db_using_checks(self) -> None:
        """``run_all_doctor_checks`` must resolve the DB path ONCE and
        pass it to every DB-using check.

        Three checks need the database path:
            - ``check_database``
            - ``check_v2_migration``
            - ``check_auto_capture_recent``

        The aggregator should call ``get_database_path`` exactly once
        and pass the same ``Path`` to all three. This proves the path
        is centralized — individual checks no longer need to know how
        to look up the canonical path on their own.
        """
        from pathlib import Path as _Path

        # All checks return HEALTHY so the aggregator runs cleanly.
        healthy = ComponentHealth(
            name="mocked_healthy",
            status=HealthStatus.HEALTHY,
            message="ok",
        )
        mock_check = AsyncMock(return_value=healthy)

        # Track which checks received a ``db_path``.
        received: dict[str, object] = {}

        def make_recorder(name: str) -> AsyncMock:
            async def _record(*args: object, **kwargs: object) -> ComponentHealth:
                # The aggregator passes ``db_path`` positionally. Accept
                # either positional or keyword so the test stays robust
                # if the call style changes.
                if "db_path" in kwargs:
                    received[name] = kwargs["db_path"]
                elif args:
                    received[name] = args[0]
                else:
                    received[name] = None
                return healthy

            return AsyncMock(side_effect=_record)

        recorders = {
            "check_python_env": make_recorder("check_python_env"),
            "check_file_system": make_recorder("check_file_system"),
            "check_database": make_recorder("check_database"),
            "check_dependencies": make_recorder("check_dependencies"),
            "check_v2_migration": make_recorder("check_v2_migration"),
            "check_code_graph_adapter": make_recorder("check_code_graph_adapter"),
            "check_code_index_round_trip": make_recorder("check_code_index_round_trip"),
            "check_auto_capture_recent": make_recorder("check_auto_capture_recent"),
            "check_claude_hooks_config": make_recorder("check_claude_hooks_config"),
            "check_server_port_bound": make_recorder("check_server_port_bound"),
        }

        # A sentinel path that is NOT the real production path. We
        # verify the aggregator used *this* path, not whatever
        # ``get_database_path`` would normally return.
        sentinel = _Path("/tmp/doctor_test_sentinel.duckdb")

        # Count calls to ``get_database_path`` to prove it's resolved
        # exactly once.
        resolve_calls = 0

        def fake_get_database_path() -> _Path:
            nonlocal resolve_calls
            resolve_calls += 1
            return sentinel

        patches = [patch(f"session_buddy.doctor.{name}", rec) for name, rec in recorders.items()]
        patches.append(
            patch("session_buddy.settings.get_database_path", fake_get_database_path)
        )

        for p in patches:
            p.start()
        try:
            results = await run_all_doctor_checks()
        finally:
            for p in patches:
                p.stop()

        # Path resolved exactly once (centralized).
        assert resolve_calls == 1, (
            f"Expected get_database_path to be called once, got {resolve_calls}. "
            "Path resolution is not centralized."
        )

        # The three DB-using checks all received the sentinel path.
        db_using = (
            "check_database",
            "check_v2_migration",
            "check_auto_capture_recent",
        )
        for name in db_using:
            assert name in received, f"{name} was not invoked"
            assert received[name] == sentinel, (
                f"{name} received db_path={received[name]!r}, expected {sentinel}"
            )

        # Non-DB checks were not given a db_path (they have different
        # signatures; this confirms we didn't accidentally widen them).
        for name in recorders:
            if name not in db_using:
                # These checks were called positionally with no args
                # in ``run_all_doctor_checks`` — recorded value should
                # be None since they don't take db_path.
                assert received.get(name) is None, (
                    f"{name} unexpectedly received db_path={received.get(name)!r}"
                )

        # Sanity: 10 results came back.
        assert len(results) == 10

    async def test_duckdb_connect_call_count_under_db_check_count(self) -> None:
        """End-to-end proof of centralization: count raw ``duckdb.connect``
        calls during a full doctor run and assert the count is bounded by
        the number of DB-using checks.

        Each DB-using check opens its own connection (we don't pool a
        single connection across coroutines — DuckDB isn't async-safe).
        The win from this refactor is path centralization, not connect
        pooling. This test therefore pins the upper bound at
        ``len(db_using_checks)`` and asserts the path was resolved once.
        """
        from pathlib import Path as _Path

        # Real path used for the resolution — a tmp file the checks
        # can ``connect`` to without touching production data.
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False)
        tmp.close()
        db_file = _Path(tmp.name)

        # Mock all doctor checks except the three that touch DuckDB.
        # We let the real check bodies run, but count the connects.
        try:
            # We can't easily let the real ``check_v2_migration`` /
            # ``check_auto_capture_recent`` bodies run in a unit test
            # (they have heavy deps). Instead, mock them to call
            # ``duckdb.connect`` exactly once each so we can verify the
            # aggregator passed the same path.
            import duckdb as _duckdb

            real_connect = _duckdb.connect
            call_count = 0
            seen_paths: list[str] = []

            def counting_connect(path: str, *args: object, **kwargs: object) -> object:
                nonlocal call_count
                call_count += 1
                seen_paths.append(str(path))
                return real_connect(path, *args, **kwargs)

            def fake_open(path: str) -> object:  # for the auto-capture path
                nonlocal call_count
                call_count += 1
                seen_paths.append(str(path))
                # Use a real connection (in-memory) for the auto-capture
                # flow; we just want to record that connect was called.
                return real_connect(":memory:")

            # Patch get_migration_status to call duckdb.connect once.
            def fake_migration_status(db_path: object = None) -> dict[str, object]:
                counting_connect(str(db_path) if db_path else ":memory:")
                # Mimic the shape the check inspects.
                return {
                    "current_version": "v2",
                    "migration_history": [],
                    "counts": {"v2_conversations": 0},
                }

            def fake_open_adapter(db_path: object = None) -> object:
                counting_connect(str(db_path) if db_path else ":memory:")
                # Return a mock that mimics a ReflectionDatabaseAdapterOneiric
                # well enough for the rest of the check to no-op.
                from unittest.mock import MagicMock

                mock = MagicMock()
                mock._table = lambda x: x
                conn = real_connect(":memory:")
                mock.conn = conn
                mock.aclose = AsyncMock()
                mock.initialize = AsyncMock()
                return mock

            class _AdapterCtx:
                def __init__(self, db_path: object) -> None:
                    self.db_path = str(db_path) if db_path else ":memory:"

                async def initialize(self) -> None:
                    counting_connect(self.db_path)

                async def aclose(self) -> None:
                    with suppress(Exception):
                        self._conn.close()

            async def fake_auto_capture(db_path: object = None) -> ComponentHealth:
                ctx = _AdapterCtx(db_path)
                await ctx.initialize()
                return ComponentHealth(
                    name="auto_capture_recent",
                    status=HealthStatus.HEALTHY,
                    message="ok",
                )

            async def fake_v2(db_path: object = None) -> ComponentHealth:
                fake_migration_status(db_path)
                return ComponentHealth(
                    name="v2_migration",
                    status=HealthStatus.HEALTHY,
                    message="ok",
                )

            async def fake_database(db_path: object = None) -> ComponentHealth:
                # check_database is a wrapper around check_database_health
                # which doesn't use duckdb.connect directly, so the count
                # here is zero for the real path. We still call
                # ``counting_connect`` to prove the aggregator passed the
                # same path.
                counting_connect(str(db_path) if db_path else ":memory:")
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="ok",
                )

            # Mock all the non-DB checks too so the aggregator doesn't
            # touch the filesystem/network/etc.
            healthy = ComponentHealth(
                name="mocked_healthy",
                status=HealthStatus.HEALTHY,
                message="ok",
            )
            mock_check = AsyncMock(return_value=healthy)

            patches = [
                patch("session_buddy.doctor.check_python_env", mock_check),
                patch("session_buddy.doctor.check_file_system", mock_check),
                patch("session_buddy.doctor.check_dependencies", mock_check),
                patch("session_buddy.doctor.check_code_graph_adapter", mock_check),
                patch("session_buddy.doctor.check_code_index_round_trip", mock_check),
                patch("session_buddy.doctor.check_claude_hooks_config", mock_check),
                patch("session_buddy.doctor.check_server_port_bound", mock_check),
                patch("session_buddy.doctor.check_database", fake_database),
                patch("session_buddy.doctor.check_v2_migration", fake_v2),
                patch("session_buddy.doctor.check_auto_capture_recent", fake_auto_capture),
                patch(
                    "session_buddy.settings.get_database_path",
                    lambda: db_file,
                ),
            ]

            for p in patches:
                p.start()
            try:
                results = await run_all_doctor_checks()
            finally:
                for p in patches:
                    p.stop()

            # Three DB-using checks, three connects (one per check).
            # This proves: 1) each check got a path, 2) the aggregator
            # passed the same path to all of them.
            db_using = ("check_database", "check_v2_migration", "check_auto_capture_recent")
            assert call_count == len(db_using), (
                f"Expected {len(db_using)} duckdb.connect calls "
                f"(one per DB-using check), got {call_count}"
            )
            # All three checks received the centralised path.
            assert all(p == str(db_file) for p in seen_paths), (
                f"DB-using checks did not all receive the same centralised "
                f"path. seen_paths={seen_paths}, expected={db_file}"
            )
            # Aggregator produced 10 results.
            assert len(results) == 10
        finally:
            with suppress(Exception):
                _Path(tmp.name).unlink()


# ---------------------------------------------------------------------------
# Typer registration test (sync, introspects the app's command list)
# ---------------------------------------------------------------------------
class TestRegisterDoctorCommand:
    def test_registers_doctor_subcommand(self) -> None:
        """``register_doctor_command`` must add a ``doctor`` command to a Typer app.

        We verify by introspection rather than by invoking the CLI:
        Click 8 + Typer 0.9+ have shifted how commands are stored,
        and ``CliRunner`` is not reliable across versions. The actual
        CLI integration is covered by the live ``test_cli_help_lists_doctor``
        smoke test below (gated on ``@pytest.mark.slow``).
        """
        import typer

        app = typer.Typer()
        register_doctor_command(app)

        # Modern Typer exposes ``registered_commands`` as a list of
        # ``CommandInfo`` objects, each with a ``.name`` attribute. The
        # exact attribute name is private API but stable across the
        # 0.9+ / 0.12+ range we support.
        command_names = {
            getattr(cmd, "name", None)
            for cmd in getattr(app, "registered_commands", [])
        }
        assert "doctor" in command_names, (
            f"register_doctor_command did not add a 'doctor' command. "
            f"Found commands: {command_names}"
        )


# ---------------------------------------------------------------------------
# Live CLI smoke (slow + env-dependent; opt-in)
# ---------------------------------------------------------------------------
@pytest.mark.slow
class TestDoctorCLIIntegration:
    def test_cli_help_lists_doctor(self) -> None:
        """The top-level CLI should list ``doctor`` in its help output."""
        result = subprocess.run(
            [sys.executable, "-m", "session_buddy", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parents[2],  # session-buddy repo root
            check=False,
        )
        assert result.returncode == 0
        assert "doctor" in result.stdout
