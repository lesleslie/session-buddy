"""Tests for ``session_buddy.mcp.tools.session.session_tools``.

Targets ``session_tools.py`` (1291 LOC, 11.2% baseline coverage).
Covers:
- ``SessionOutputBuilder`` formatting helpers
- ``should_suggest_compact`` re-export
- Working-directory auto-detection helpers
- Session shortcut creation
- Environment setup (UV probe, subprocess error paths)
- ``_start_impl`` / ``_checkpoint_impl`` / ``_end_impl`` / ``_status_impl``
- ``_pre_compact_sync_impl``
- ``_single_flight_checkpoint`` coalescing
- ``register_session_tools`` decorator registration
- ``_queue_akosha_sync_background`` / ``_akosha_sync_background_task``
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from session_buddy.mcp.tools.session import session_tools as mod
from session_buddy.mcp.tools.session.session_tools import (
    SessionOutputBuilder,
    SessionSetupResults,
    _add_environment_info_to_output,
    _add_health_section_to_output,
    _add_project_context_to_output,
    _add_project_section_to_output,
    _add_quality_section_to_output,
    _add_session_info_to_output,
    _check_environment_variables,
    _check_parent_process_cwd,
    _check_working_dir_file,
    _collect_git_repos,
    _create_session_shortcuts,
    _find_recent_git_repository,
    _format_recommendations,
    _format_session_summary,
    _format_successful_end,
    _get_client_working_directory,
    _get_most_recent_client_repo,
    _get_session_manager,
    _is_git_repository,
    _perform_environment_setup,
    _queue_akosha_sync_background,
    _safe_get_mtime,
    _setup_uv_dependencies,
    _single_flight_checkpoint,
    register_session_tools,
    should_suggest_compact,
)


# ---------------------------------------------------------------------------
# _FakeMCP and helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Capture-only stand-in for the FastMCP server."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.prompts: dict[str, Any] = {}
        self.resources: dict[str, Any] = {}

    def tool(self, *_args: Any, **_kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            return fn

        return decorator

    def add_tool(self, fn: Any, name: str | None = None, **_kwargs: Any) -> None:
        self.tools[name or fn.__name__] = fn


# ---------------------------------------------------------------------------
# SessionOutputBuilder
# ---------------------------------------------------------------------------


class TestSessionOutputBuilder:
    def test_starts_empty(self) -> None:
        b = SessionOutputBuilder()
        assert b.build() == ""

    def test_add_header_uses_default_separator(self) -> None:
        b = SessionOutputBuilder()
        b.add_header("Title")
        out = b.build().split("\n")
        assert out[0] == "Title"
        assert out[1] == "=" * len("Title")

    def test_add_header_custom_separator(self) -> None:
        b = SessionOutputBuilder()
        b.add_header("Hi", separator_char="-")
        out = b.build().split("\n")
        assert out[0] == "Hi"
        assert out[1] == "--"

    def test_add_section_with_title(self) -> None:
        b = SessionOutputBuilder()
        b.add_section("Things", ["a", "b"])
        out = b.build()
        assert "\nThings:" in out
        assert "a" in out and "b" in out

    def test_add_section_without_title(self) -> None:
        b = SessionOutputBuilder()
        b.add_section("", ["alpha"])
        assert b.build() == "alpha"

    def test_add_status_item_pass(self) -> None:
        b = SessionOutputBuilder()
        b.add_status_item("Git", True)
        assert "✅" in b.build()

    def test_add_status_item_fail(self) -> None:
        b = SessionOutputBuilder()
        b.add_status_item("Git", False)
        assert "❌" in b.build()

    def test_add_status_item_with_value(self) -> None:
        b = SessionOutputBuilder()
        b.add_status_item("Git", True, value="ok")
        assert "ok" in b.build()

    def test_add_simple_item(self) -> None:
        b = SessionOutputBuilder()
        b.add_simple_item("hi")
        assert b.build() == "hi"

    def test_build_joins_with_newlines(self) -> None:
        b = SessionOutputBuilder()
        b.add_simple_item("a")
        b.add_simple_item("b")
        assert b.build() == "a\nb"


# ---------------------------------------------------------------------------
# should_suggest_compact re-export
# ---------------------------------------------------------------------------


class TestShouldSuggestCompact:
    def test_returns_tuple(self) -> None:
        result = should_suggest_compact()
        assert isinstance(result, tuple)
        assert len(result) == 2
        flag, reason = result
        assert isinstance(flag, bool)
        assert isinstance(reason, str)


# ---------------------------------------------------------------------------
# Working-directory detection helpers
# ---------------------------------------------------------------------------


class TestCheckEnvironmentVariables:
    def test_no_env_vars_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k in ("CLAUDE_WORKING_DIR", "CLIENT_PWD", "CLAUDE_PROJECT_DIR"):
            monkeypatch.delenv(k, raising=False)
        assert _check_environment_variables() is None

    def test_returns_existing_env_var(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CLAUDE_WORKING_DIR", str(tmp_path))
        assert _check_environment_variables() == str(tmp_path)

    def test_first_match_wins(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CLAUDE_WORKING_DIR", str(tmp_path))
        monkeypatch.setenv("CLIENT_PWD", "/nonexistent-please-ignore")
        # First declared env var wins.
        assert _check_environment_variables() == str(tmp_path)

    def test_nonexistent_path_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_WORKING_DIR", "/__definitely_nonexistent_path__")
        assert _check_environment_variables() is None


class TestCheckWorkingDirFile:
    def test_no_file_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import tempfile

        # Point tempfile.gettempdir() at an empty dir so the test file is absent.
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(empty_dir))
        assert _check_working_dir_file() is None

    def test_returns_file_content_when_valid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tempfile

        target_dir = tmp_path / "real_repo"
        target_dir.mkdir()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        (tmp_path / "claude-git-working-dir").write_text(str(target_dir))
        assert _check_working_dir_file() == str(target_dir)

    def test_filters_session_mgmt_mcp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tempfile

        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        (tmp_path / "claude-git-working-dir").write_text("/tmp/session-mgmt-mcp")
        assert _check_working_dir_file() is None


class TestCheckParentProcessCwd:
    def test_returns_none_when_psutil_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Block psutil import to exercise the except branch.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert _check_parent_process_cwd() is None


class TestIsGitRepository:
    def test_true_for_git_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        assert _is_git_repository(tmp_path) is True

    def test_false_for_regular_dir(self, tmp_path: Path) -> None:
        assert _is_git_repository(tmp_path) is False

    def test_false_for_missing_path(self, tmp_path: Path) -> None:
        assert _is_git_repository(tmp_path / "missing") is False


class TestSafeGetMtime:
    def test_returns_mtime_for_existing(self, tmp_path: Path) -> None:
        result = _safe_get_mtime(tmp_path)
        assert isinstance(result, float)
        assert result > 0


class TestCollectGitRepos:
    def test_returns_git_repos_with_mtimes(self, tmp_path: Path) -> None:
        repo1 = tmp_path / "repo1"
        repo1.mkdir()
        (repo1 / ".git").mkdir()
        plain = tmp_path / "plain"
        plain.mkdir()

        result = _collect_git_repos(tmp_path)
        names = [path for _, path in result]
        assert str(repo1) in names
        assert all(isinstance(m, float) for m, _ in result)
        # Plain directory is excluded.
        assert not any(path == str(plain) for _, path in result)

    def test_skips_permission_errors(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Force _safe_get_mtime to return None for one path.
        original = mod._safe_get_mtime
        called: list[Path] = []

        def fake_mtime(p: Path) -> float | None:
            called.append(p)
            return None  # always None → all repos filtered out

        monkeypatch.setattr(mod, "_safe_get_mtime", fake_mtime)
        repo = tmp_path / "r"
        repo.mkdir()
        (repo / ".git").mkdir()
        assert _collect_git_repos(tmp_path) == []
        assert called  # function was invoked


class TestGetMostRecentClientRepo:
    def test_filters_session_mgmt_mcp(self) -> None:
        repos = [(1.0, "/Users/x/session-mgmt-mcp")]
        assert _get_most_recent_client_repo(repos) is None

    def test_returns_first_match(self) -> None:
        repos = [(2.0, "/proj/a"), (1.0, "/proj/b")]
        assert _get_most_recent_client_repo(repos) == "/proj/a"


class TestFindRecentGitRepository:
    def test_returns_none_for_missing_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # All candidate project dirs missing.
        def fake_collect(p: Path) -> list[tuple[float, str]]:
            return []

        monkeypatch.setattr(mod, "_collect_git_repos", fake_collect)
        # Both /Users/les/Projects and ~/Projects exist on the test host,
        # but the fake_collect returns empty.
        assert _find_recent_git_repository() is None


# ---------------------------------------------------------------------------
# _create_session_shortcuts
# ---------------------------------------------------------------------------


class TestCreateSessionShortcuts:
    def test_creates_files_and_reports_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = _create_session_shortcuts()
        assert result["created"] is True
        assert result["existed"] is False
        assert "start" in result["shortcuts"]
        assert "checkpoint" in result["shortcuts"]
        assert "end" in result["shortcuts"]
        # Files should exist on disk.
        assert (tmp_path / ".claude" / "commands" / "start.md").exists()

    def test_reports_existed_when_already_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Pre-create one shortcut to test the "existed" branch.
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "start.md").write_text("pre-existing")
        result = _create_session_shortcuts()
        # When start.md exists and checkpoint/end are freshly created,
        # the ``shortcuts`` list carries the CREATED entries
        # (created_shortcuts takes precedence over existing_shortcuts).
        # The pre-existing file should NOT have been overwritten.
        assert (commands_dir / "start.md").read_text() == "pre-existing"
        assert "checkpoint" in result["shortcuts"]
        assert "end" in result["shortcuts"]
        # "start" was not created this run, so it's not in the shortcuts
        # list (the list reflects created-or-fallback, and we created others).
        assert result["created"] is True

    def test_all_existed_returns_existed_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        for f in ("start.md", "checkpoint.md", "end.md"):
            (commands_dir / f).write_text("preexisting")
        result = _create_session_shortcuts()
        assert result["existed"] is True
        assert result["created"] is False
        assert set(result["shortcuts"]) == {"start", "checkpoint", "end"}


# ---------------------------------------------------------------------------
# _setup_uv_dependencies
# ---------------------------------------------------------------------------


class TestSetupUvDependencies:
    def test_missing_uv_in_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import shutil

        monkeypatch.setattr(shutil, "which", lambda _: None)
        out = _setup_uv_dependencies(tmp_path)
        assert any("UV not found" in line for line in out)

    def test_no_pyproject(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import shutil

        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/uv")
        out = _setup_uv_dependencies(tmp_path)
        assert any("No pyproject.toml" in line for line in out)

    def test_successful_uv_sync(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import shutil
        import subprocess as real_subprocess

        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")

        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/uv")

        def fake_run(*args: Any, **kwargs: Any) -> Any:
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            return r

        monkeypatch.setattr(real_subprocess, "run", fake_run)
        out = _setup_uv_dependencies(tmp_path)
        assert any("UV dependencies synchronized" in line for line in out)

    def test_uv_sync_failed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import shutil
        import subprocess as real_subprocess

        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/uv")

        def fake_run(*args: Any, **kwargs: Any) -> Any:
            r = MagicMock()
            r.returncode = 1
            r.stderr = "boom"
            return r

        monkeypatch.setattr(real_subprocess, "run", fake_run)
        out = _setup_uv_dependencies(tmp_path)
        assert any("UV sync had issues" in line for line in out)

    def test_uv_sync_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import shutil
        import subprocess as real_subprocess

        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/uv")

        def fake_run(*args: Any, **kwargs: Any) -> Any:
            raise real_subprocess.TimeoutExpired(cmd="uv", timeout=60)

        monkeypatch.setattr(real_subprocess, "run", fake_run)
        out = _setup_uv_dependencies(tmp_path)
        assert any("UV sync timed out" in line for line in out)

    def test_uv_sync_oserror(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import shutil
        import subprocess as real_subprocess

        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/uv")

        def fake_run(*args: Any, **kwargs: Any) -> Any:
            raise OSError("disk gone")

        monkeypatch.setattr(real_subprocess, "run", fake_run)
        out = _setup_uv_dependencies(tmp_path)
        assert any("UV sync error" in line for line in out)


# ---------------------------------------------------------------------------
# Output section helpers
# ---------------------------------------------------------------------------


class TestAddSessionInfoToOutput:
    def test_appends_required_lines(self) -> None:
        builder = SessionOutputBuilder()
        result = {
            "project": "demo",
            "working_directory": "/tmp/demo",
            "claude_directory": "/home/u/.claude",
            "quality_score": 92,
            "project_context": {"a": True, "b": False, "c": True},
        }
        _add_session_info_to_output(builder, result)
        text = builder.build()
        assert "demo" in text
        assert "/tmp/demo" in text
        assert "92/100" in text
        assert "2/3" in text  # 2 of 3 context indicators true


class TestAddProjectSectionToOutput:
    def test_appends_required_lines(self) -> None:
        builder = SessionOutputBuilder()
        _add_project_section_to_output(
            builder,
            {
                "project": "p",
                "working_directory": "/wd",
                "quality_score": 50,
            },
        )
        text = builder.build()
        assert "p" in text
        assert "/wd" in text
        assert "50/100" in text


class TestAddQualitySectionToOutput:
    def test_appends_quality_lines(self) -> None:
        builder = SessionOutputBuilder()
        breakdown = {
            "code_quality": 30.0,
            "project_health": 20.0,
            "dev_velocity": 15.0,
            "security": 8.0,
        }
        _add_quality_section_to_output(builder, breakdown)
        # The function writes the section twice (once in try, once after).
        text = builder.build()
        assert "30.0/40" in text
        assert "20.0/30" in text
        assert "15.0/20" in text
        assert "8.0/10" in text

    def test_keyerror_branch_renders_error_section(self) -> None:
        """After fix: missing breakdown keys produce an error section, not UnboundLocalError.

        ``_add_quality_section_to_output`` now assigns ``quality_items``
        in the ``except`` block so the unconditional ``add_section`` call
        after the ``try`` is no longer an ``UnboundLocalError`` waiting
        to happen. Instead, callers see a structured error message.
        """
        builder = SessionOutputBuilder()
        # Should NOT raise; should render an error section instead.
        _add_quality_section_to_output(
            builder,
            {"code_quality": 10.0},  # type: ignore[typeddict-item]
        )
        rendered = builder.build()
        assert "Error formatting quality metrics" in rendered
        assert "Quality breakdown" in rendered


class TestAddHealthSectionToOutput:
    def test_appends_health_items(self) -> None:
        builder = SessionOutputBuilder()
        _add_health_section_to_output(
            builder,
            {
                "uv_available": True,
                "git_repository": False,
                "claude_directory": True,
            },
        )
        text = builder.build()
        assert "UV package manager" in text
        assert "✅" in text
        assert "❌" in text


class TestAddProjectContextToOutput:
    def test_appends_context_items(self) -> None:
        builder = SessionOutputBuilder()
        _add_project_context_to_output(
            builder,
            {
                "has_pyproject_toml": True,
                "has_git_repo": False,
                "has_tests": True,
                "has_docs": True,
                "extra": False,
            },
        )
        text = builder.build()
        # The function sums truthy values in the full dict (5 keys total,
        # 3 are True), so the header reads "3/5 indicators".
        assert "3/5" in text
        assert "pyproject.toml" in text


class TestAddEnvironmentInfoToOutput:
    def test_shortcuts_created_branch(self) -> None:
        builder = SessionOutputBuilder()
        setup = SessionSetupResults(
            uv_setup=[],
            shortcuts_result={"created": True, "shortcuts": ["start"]},
            recommendations=[],
        )
        _add_environment_info_to_output(builder, setup)
        assert "Created session management shortcuts" in builder.build()

    def test_shortcuts_existed_branch(self) -> None:
        builder = SessionOutputBuilder()
        setup = SessionSetupResults(
            uv_setup=[],
            shortcuts_result={"created": False, "existed": True, "shortcuts": ["start"]},
            recommendations=[],
        )
        _add_environment_info_to_output(builder, setup)
        assert "shortcuts already exist" in builder.build()

    def test_recommendations_truncated_to_three(self) -> None:
        builder = SessionOutputBuilder()
        setup = SessionSetupResults(
            uv_setup=[],
            shortcuts_result={},
            recommendations=["r1", "r2", "r3", "r4", "r5"],
        )
        _add_environment_info_to_output(builder, setup)
        text = builder.build()
        assert "r1" in text and "r3" in text
        assert "r4" not in text


# ---------------------------------------------------------------------------
# End formatting helpers
# ---------------------------------------------------------------------------


class TestFormatRecommendations:
    def test_empty_returns_empty_string(self) -> None:
        assert _format_recommendations([]) == ""

    def test_caps_at_five_items(self) -> None:
        result = _format_recommendations([f"rec-{i}" for i in range(10)])
        assert "rec-0" in result
        assert "rec-4" in result
        assert "rec-5" not in result


class TestFormatSessionSummary:
    def test_with_handoff_doc(self) -> None:
        result = _format_session_summary(
            {"working_directory": "/x", "handoff_documentation": "/handoff.md"}
        )
        assert "/x" in result
        assert "/handoff.md" in result

    def test_without_handoff_doc(self) -> None:
        result = _format_session_summary({"working_directory": "/x"})
        assert "/x" in result
        assert "Handoff documentation" not in result


class TestFormatSuccessfulEnd:
    def test_includes_recommendations_and_summary(self) -> None:
        result = _format_successful_end(
            {
                "project": "p",
                "final_quality_score": 88,
                "session_end_time": "2026-01-01",
                "working_directory": "/wd",
                "recommendations": ["reca"],
            }
        )
        assert "p" in result
        assert "88/100" in result
        assert "reca" in result
        assert "Session ended successfully" in result


# ---------------------------------------------------------------------------
# _perform_environment_setup
# ---------------------------------------------------------------------------


class TestPerformEnvironmentSetup:
    @pytest.mark.asyncio
    async def test_returns_session_setup_results(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Replace shortcut creator to avoid touching real ~/.claude/.
        monkeypatch.setattr(
            mod,
            "_create_session_shortcuts",
            lambda: {"created": True, "shortcuts": ["start"]},
        )
        result = {
            "working_directory": str(tmp_path),
            "quality_data": {"recommendations": ["a", "b"]},
        }
        out = await _perform_environment_setup(result)
        assert isinstance(out, SessionSetupResults)
        assert out.recommendations == ["a", "b"]
        assert out.shortcuts_result["created"] is True
        # UV setup should at least include the header lines.
        joined = "\n".join(out.uv_setup)
        assert "UV Package Management Setup" in joined


# ---------------------------------------------------------------------------
# _get_session_manager
# ---------------------------------------------------------------------------


class TestGetSessionManager:
    def test_returns_lifecycle_manager_instance(self) -> None:
        mgr = _get_session_manager()
        from session_buddy.core import SessionLifecycleManager

        assert isinstance(mgr, SessionLifecycleManager)


# ---------------------------------------------------------------------------
# Akosha background sync helpers
# ---------------------------------------------------------------------------


class TestQueueAkoshaSyncBackground:
    def test_no_loop_skips_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Without a running loop, asyncio.create_task would raise. The function
        # guards with a broad try/except. We want it to swallow the error and
        # NOT crash.
        from session_buddy import settings as settings_module
        from session_buddy.storage.akosha_config import AkoshaSyncConfig

        # Build a fake AkoshaSyncConfig that says "yes, upload".
        fake_cfg = MagicMock(spec=AkoshaSyncConfig)
        fake_cfg.upload_on_session_end = True
        monkeypatch.setattr(AkoshaSyncConfig, "from_settings", lambda s: fake_cfg)
        # Patch asyncio.create_task to raise to exercise the except branch.
        import asyncio as real_asyncio

        monkeypatch.setattr(real_asyncio, "create_task", MagicMock(side_effect=RuntimeError("no loop")))

        # Should not raise.
        try:
            _queue_akosha_sync_background()
        except Exception as e:
            pytest.fail(f"queue helper should swallow exceptions: {e}")

    def test_disabled_returns_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from session_buddy.storage.akosha_config import AkoshaSyncConfig

        fake_cfg = MagicMock(spec=AkoshaSyncConfig)
        fake_cfg.upload_on_session_end = False
        monkeypatch.setattr(AkoshaSyncConfig, "from_settings", lambda s: fake_cfg)

        import asyncio as real_asyncio

        called = MagicMock()
        monkeypatch.setattr(real_asyncio, "create_task", called)

        _queue_akosha_sync_background()
        # Should have skipped enqueueing.
        called.assert_not_called()


# ---------------------------------------------------------------------------
# _start_impl
# ---------------------------------------------------------------------------


class TestStartImpl:
    @pytest.mark.asyncio
    async def test_start_success_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        async def fake_initialize(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            return {
                "success": True,
                "project": "demo",
                "working_directory": str(tmp_path),
                "claude_directory": str(tmp_path),
                "quality_score": 90,
                "project_context": {"a": True},
                "conversation_id": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            }

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.initialize_session",
            fake_initialize,
        )
        # Avoid touching ~/.claude/ shortcuts.
        monkeypatch.setattr(
            mod,
            "_create_session_shortcuts",
            lambda: {"created": True, "shortcuts": ["start"]},
        )

        prose, cid = await mod._start_impl(working_directory=str(tmp_path))
        assert isinstance(prose, str) and prose
        assert cid == "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        assert "demo" in prose

    @pytest.mark.asyncio
    async def test_start_failure_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        async def fake_initialize(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            return {
                "success": False,
                "error": "nope",
                "project": "demo",
                "working_directory": str(tmp_path),
                "claude_directory": str(tmp_path),
                "quality_score": 0,
                "project_context": {},
            }

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.initialize_session",
            fake_initialize,
        )

        prose, cid = await mod._start_impl(working_directory=str(tmp_path))
        assert "nope" in prose
        # No conversation_id is recorded on failure → cid is None (G6 sentinel).
        assert cid is None

    @pytest.mark.asyncio
    async def test_start_exception_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        async def boom(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.initialize_session",
            boom,
        )

        prose, cid = await mod._start_impl(working_directory=str(tmp_path))
        assert "kaboom" in prose
        assert cid is None


# ---------------------------------------------------------------------------
# _checkpoint_impl
# ---------------------------------------------------------------------------


class TestCheckpointImpl:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_checkpoint(self: Any, working_directory: str | None, is_manual: bool = True) -> dict[str, Any]:
            return {
                "success": True,
                "quality_output": ["📊 quality: 88"],
                "git_output": ["📁 git: clean"],
                "quality_data": {"total_score": 88, "breakdown": {}, "recommendations": []},
                "timestamp": "now",
                "auto_store_decision": None,
            }

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.checkpoint_session",
            fake_checkpoint,
        )
        out = await mod._checkpoint_impl(working_directory="/wd")
        assert "📊 quality: 88" in out
        assert "Checkpoint completed" in out

    @pytest.mark.asyncio
    async def test_success_with_minimal_quality_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_checkpoint(self: Any, working_directory: str | None, is_manual: bool = True) -> dict[str, Any]:
            return {
                "success": True,
                "quality_output": [],
                "git_output": [],
                "quality_score": 70,
                "timestamp": "now",
            }

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.checkpoint_session",
            fake_checkpoint,
        )
        out = await mod._checkpoint_impl(working_directory="/wd")
        # Minimal fixture path: quality_data synthesized as {} → success path emits output.
        assert "Checkpoint completed" in out

    @pytest.mark.asyncio
    async def test_quality_data_missing_total_score(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_checkpoint(self: Any, working_directory: str | None, is_manual: bool = True) -> dict[str, Any]:
            return {
                "success": True,
                "quality_output": [],
                "git_output": [],
                "quality_data": {"breakdown": {}, "recommendations": []},  # no total_score
                "timestamp": "now",
            }

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.checkpoint_session",
            fake_checkpoint,
        )
        out = await mod._checkpoint_impl(working_directory="/wd")
        assert "Checkpoint failed" in out
        assert "total_score" in out

    @pytest.mark.asyncio
    async def test_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_checkpoint(self: Any, working_directory: str | None, is_manual: bool = True) -> dict[str, Any]:
            return {"success": False, "error": "fail-reason"}

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.checkpoint_session",
            fake_checkpoint,
        )
        out = await mod._checkpoint_impl(working_directory="/wd")
        assert "fail-reason" in out

    @pytest.mark.asyncio
    async def test_exception_returns_user_visible_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(self: Any, working_directory: str | None, is_manual: bool = True) -> dict[str, Any]:
            raise RuntimeError("broken")

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.checkpoint_session",
            boom,
        )
        out = await mod._checkpoint_impl(working_directory="/wd")
        assert "broken" in out


# ---------------------------------------------------------------------------
# _single_flight_checkpoint
# ---------------------------------------------------------------------------


class TestSingleFlightCheckpoint:
    @pytest.mark.asyncio
    async def test_concurrent_calls_coalesce(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = 0
        started = asyncio.Event()
        release = asyncio.Event()

        async def fake_impl(working_directory: str | None = None) -> str:
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return "ok"

        monkeypatch.setattr(mod, "_checkpoint_impl", fake_impl)

        # Disable working-directory auto-detect for this test.
        monkeypatch.setattr(mod, "_get_client_working_directory", lambda: None)

        leader = asyncio.create_task(_single_flight_checkpoint("/wd"))
        await started.wait()
        follower = asyncio.create_task(_single_flight_checkpoint("/wd"))

        # Let leader finish.
        release.set()
        a, b = await asyncio.gather(leader, follower)
        assert a == b == "ok"
        # Only one underlying execution.
        assert calls == 1

    @pytest.mark.asyncio
    async def test_distinct_working_dirs_run_independently(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        async def fake_impl(working_directory: str | None = None) -> str:
            calls.append(working_directory or "")
            await asyncio.sleep(0.01)
            return f"ok:{working_directory}"

        monkeypatch.setattr(mod, "_checkpoint_impl", fake_impl)

        a, b = await asyncio.gather(
            _single_flight_checkpoint("/wd-a"),
            _single_flight_checkpoint("/wd-b"),
        )
        assert {a, b} == {"ok:/wd-a", "ok:/wd-b"}
        assert calls == ["/wd-a", "/wd-b"]

    @pytest.mark.asyncio
    async def test_exception_propagates_to_all_callers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def boom(working_directory: str | None = None) -> str:
            started.set()
            await release.wait()
            raise ValueError("nope")

        monkeypatch.setattr(mod, "_checkpoint_impl", boom)

        leader = asyncio.create_task(_single_flight_checkpoint("/wd"))
        await started.wait()
        follower = asyncio.create_task(_single_flight_checkpoint("/wd"))

        release.set()
        results = await asyncio.gather(leader, follower, return_exceptions=True)
        assert all(isinstance(r, ValueError) for r in results)
        # Both observed the same message.
        assert all(str(r) == "nope" for r in results)


# ---------------------------------------------------------------------------
# _end_impl
# ---------------------------------------------------------------------------


class TestEndImpl:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_end(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            return {
                "success": True,
                "summary": {
                    "project": "p",
                    "final_quality_score": 92,
                    "session_end_time": "now",
                    "working_directory": "/wd",
                    "recommendations": ["rec"],
                },
            }

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.end_session",
            fake_end,
        )
        # Don't queue a real background task.
        monkeypatch.setattr(mod, "_queue_akosha_sync_background", lambda: None)

        out = await mod._end_impl(working_directory="/wd")
        assert "Session ended successfully" in out
        assert "92/100" in out
        assert "rec" in out

    @pytest.mark.asyncio
    async def test_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_end(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            return {"success": False, "error": "oops"}

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.end_session",
            fake_end,
        )
        out = await mod._end_impl(working_directory="/wd")
        assert "oops" in out

    @pytest.mark.asyncio
    async def test_exception_returns_user_visible_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            raise RuntimeError("endboom")

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.end_session",
            boom,
        )
        out = await mod._end_impl(working_directory="/wd")
        assert "endboom" in out


# ---------------------------------------------------------------------------
# _status_impl
# ---------------------------------------------------------------------------


class TestStatusImpl:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_status(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            return {
                "success": True,
                "project": "p",
                "working_directory": "/wd",
                "quality_score": 80,
                "quality_breakdown": {
                    "code_quality": 30.0,
                    "project_health": 20.0,
                    "dev_velocity": 15.0,
                    "security": 8.0,
                },
                "system_health": {
                    "uv_available": True,
                    "git_repository": True,
                    "claude_directory": True,
                },
                "project_context": {
                    "has_pyproject_toml": True,
                    "has_git_repo": True,
                    "has_tests": True,
                    "has_docs": True,
                },
                "recommendations": ["r1", "r2"],
                "timestamp": "now",
            }

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.get_session_status",
            fake_status,
        )
        out = await mod._status_impl(working_directory="/wd")
        assert "80/100" in out
        assert "p" in out
        assert "Recommendations" in out

    @pytest.mark.asyncio
    async def test_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_status(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            return {"success": False, "error": "broken"}

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.get_session_status",
            fake_status,
        )
        out = await mod._status_impl(working_directory="/wd")
        assert "broken" in out

    @pytest.mark.asyncio
    async def test_exception_returns_user_visible_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(self: Any, working_directory: str | None = None) -> dict[str, Any]:
            raise RuntimeError("statusboom")

        monkeypatch.setattr(
            "session_buddy.core.SessionLifecycleManager.get_session_status",
            boom,
        )
        out = await mod._status_impl(working_directory="/wd")
        assert "statusboom" in out


# ---------------------------------------------------------------------------
# _handle_auto_compaction / _handle_auto_store_reflection
# ---------------------------------------------------------------------------


class TestHandleAutoCompaction:
    @pytest.mark.asyncio
    async def test_should_compact_true_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy import server_optimized

        monkeypatch.setattr(
            server_optimized,
            "should_suggest_compact",
            lambda: (True, "reason"),
        )

        async def fake_execute() -> None:
            return None

        monkeypatch.setattr(server_optimized, "_execute_auto_compact", fake_execute)

        out: list[str] = []
        await mod._handle_auto_compaction(out)
        text = "\n".join(out)
        assert "Automatic Compaction Analysis" in text
        assert "Context automatically optimized" in text

    @pytest.mark.asyncio
    async def test_should_compact_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from session_buddy import server_optimized

        monkeypatch.setattr(
            server_optimized,
            "should_suggest_compact",
            lambda: (False, "stable"),
        )
        out: list[str] = []
        await mod._handle_auto_compaction(out)
        text = "\n".join(out)
        assert "well-optimized" in text

    @pytest.mark.asyncio
    async def test_execute_compact_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from session_buddy import server_optimized

        monkeypatch.setattr(
            server_optimized,
            "should_suggest_compact",
            lambda: (True, "reason"),
        )

        async def boom() -> None:
            raise RuntimeError("auto-compact failed")

        monkeypatch.setattr(server_optimized, "_execute_auto_compact", boom)

        out: list[str] = []
        await mod._handle_auto_compaction(out)
        text = "\n".join(out)
        assert "Auto-compact skipped" in text
        assert "manual" in text


class TestHandleAutoStoreReflection:
    @pytest.mark.asyncio
    async def test_no_decision_returns_silently(self) -> None:
        out: list[str] = []
        await mod._handle_auto_store_reflection({}, out)
        assert out == []

    @pytest.mark.asyncio
    async def test_should_store_false_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        decision = MagicMock()
        decision.should_store = False
        decision.reason = MagicMock(value="noop")
        result = {
            "auto_store_decision": decision,
            "auto_store_summary": "skipped because X",
        }
        out: list[str] = []
        await mod._handle_auto_store_reflection(result, out)
        assert "skipped because X" in "\n".join(out)

    @pytest.mark.asyncio
    async def test_should_store_true_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import datetime, timezone

        decision = MagicMock()
        decision.should_store = True
        decision.reason = MagicMock(value="quality_improvement")
        decision.metadata = {"delta": 5}

        class FakeDB:
            async def initialize(self) -> None:
                pass

            async def store_reflection(self, content: str, tags: list[str]) -> str:
                return "ref-id"

        class FakeReflectionTools:
            @staticmethod
            async def get_reflection_database():
                return FakeDB()

        async def fake_get_db():
            return FakeDB()

        # Patch the lazy import inside _handle_auto_store_reflection.
        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            fake_get_db,
        )
        # _get_session_manager is called to derive current_project.
        monkeypatch.setattr(
            mod,
            "_get_session_manager",
            lambda: MagicMock(current_project="demo"),
        )

        result = {
            "auto_store_decision": decision,
            "auto_store_summary": "stored",
            "quality_score": 80,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        out: list[str] = []
        await mod._handle_auto_store_reflection(result, out)
        assert "stored" in "\n".join(out)

    @pytest.mark.asyncio
    async def test_should_store_true_branch_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        decision = MagicMock()
        decision.should_store = True
        decision.reason = MagicMock(value="quality_improvement")
        decision.metadata = {"delta": 5}

        async def boom_db():
            raise RuntimeError("db down")

        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            boom_db,
        )

        result = {
            "auto_store_decision": decision,
            "auto_store_summary": "stored",
            "quality_score": 80,
            "timestamp": "now",
        }
        out: list[str] = []
        await mod._handle_auto_store_reflection(result, out)
        assert "Reflection storage failed" in "\n".join(out)


# ---------------------------------------------------------------------------
# _pre_compact_sync_impl
# ---------------------------------------------------------------------------


class TestPreCompactSyncImpl:
    @pytest.mark.asyncio
    async def test_no_quality_score_no_reflection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Make get_settings().reflection adapter gracefully no-op.
        class FakeDB:
            async def initialize(self) -> None:
                pass

            async def store_reflection(self, content: str, tags: list[str]) -> str:
                return "ref-1"

        async def fake_db():
            return FakeDB()

        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            fake_db,
        )
        monkeypatch.setattr(
            mod,
            "_get_client_working_directory",
            lambda: None,
        )
        # _get_session_manager returns a stub with no _last_quality_score attr.
        monkeypatch.setattr(
            mod,
            "_get_session_manager",
            lambda: MagicMock(current_project=None, spec=["current_project"]),
        )

        result = await mod._pre_compact_sync_impl()
        assert result["success"] is True
        assert "reflection_id" in result
        assert result["reflection_stored"] is True

    @pytest.mark.asyncio
    async def test_reflection_storage_failure_recorded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeDB:
            async def initialize(self) -> None:
                pass

            async def store_reflection(self, content: str, tags: list[str]) -> str:
                raise RuntimeError("store failed")

        async def fake_db():
            return FakeDB()

        monkeypatch.setattr(
            "session_buddy.reflection_tools.get_reflection_database",
            fake_db,
        )
        monkeypatch.setattr(
            mod,
            "_get_client_working_directory",
            lambda: None,
        )
        monkeypatch.setattr(
            mod,
            "_get_session_manager",
            lambda: MagicMock(current_project=None, spec=["current_project"]),
        )

        result = await mod._pre_compact_sync_impl()
        assert result["success"] is True
        assert result["reflection_stored"] is False
        assert "store failed" in result["reflection_error"]

    @pytest.mark.asyncio
    async def test_session_manager_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom() -> None:
            raise RuntimeError("manager down")

        monkeypatch.setattr(mod, "_get_session_manager", boom)

        result = await mod._pre_compact_sync_impl()
        assert result["success"] is False
        assert "manager down" in result["error"]


# ---------------------------------------------------------------------------
# register_session_tools
# ---------------------------------------------------------------------------


class TestRegisterSessionTools:
    def test_registers_every_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeMCP()
        register_session_tools(fake)
        # Tool names should be registered as decorated functions.
        # We patch FastMCP.tool to capture names.
        registered: list[str] = []

        class _CapturingMCP:
            def tool(self, *_args: Any, **_kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    registered.append(fn.__name__)
                    return fn

                return decorator

        register_session_tools(_CapturingMCP())  # type: ignore[arg-type]
        expected = {
            "start",
            "checkpoint",
            "end",
            "status",
            "health_check",
            "server_info",
            "ping",
            "pre_compact_sync",
        }
        assert expected.issubset(set(registered))


# ---------------------------------------------------------------------------
# ping / health_check / server_info
# ---------------------------------------------------------------------------


class TestPingHealthServerInfo:
    @pytest.mark.asyncio
    async def test_ping_returns_canonical_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Capture every decorated tool function so we can invoke them directly.
        captured: dict[str, Any] = {}

        class _Capturing:
            def tool(self, *_args: Any, **_kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    captured[fn.__name__] = fn
                    return fn

                return decorator

        register_session_tools(_Capturing())  # type: ignore[arg-type]

        ping_fn = captured["ping"]
        result = await ping_fn()
        assert result["status"] == "ok"
        assert result["service"] == "session-buddy"
        assert "version" in result
        assert "uptime_seconds" in result
        assert isinstance(result["uptime_seconds"], (int, float))

    @pytest.mark.asyncio
    async def test_health_check_returns_block(self) -> None:
        captured: dict[str, Any] = {}

        class _Fake:
            def tool(self, *_args: Any, **_kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    captured[fn.__name__] = fn
                    return fn

                return decorator

        register_session_tools(_Fake())  # type: ignore[arg-type]
        result = await captured["health_check"]()
        assert "MCP Server Health Check" in result
        assert "operational" in result.lower()

    @pytest.mark.asyncio
    async def test_server_info_returns_block(self) -> None:
        captured: dict[str, Any] = {}

        class _Fake:
            def tool(self, *_args: Any, **_kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    captured[fn.__name__] = fn
                    return fn

                return decorator

        register_session_tools(_Fake())  # type: ignore[arg-type]
        result = await captured["server_info"]()
        assert "Session-mgmt MCP Server Information" in result
        assert "running and accessible" in result

    @pytest.mark.asyncio
    async def test_pre_compact_sync_success(self) -> None:
        captured: dict[str, Any] = {}

        class _Fake:
            def tool(self, *_args: Any, **_kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    captured[fn.__name__] = fn
                    return fn

                return decorator

        register_session_tools(_Fake())  # type: ignore[arg-type]

        # Stub the impl to return a success envelope.
        async def fake_impl() -> dict[str, Any]:
            return {
                "success": True,
                "project": "demo",
                "timestamp": "now",
                "quality_score": 88,
                "reflection_stored": True,
                "reflection_id": "ref-1",
                "tags": ["t1", "t2"],
            }

        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.setattr(mod, "_pre_compact_sync_impl", fake_impl)
            result = await captured["pre_compact_sync"]()
        finally:
            monkeypatch.undo()

        assert "Pre-Compact Sync Complete" in result
        assert "demo" in result
        assert "ref-1" in result

    @pytest.mark.asyncio
    async def test_pre_compact_sync_failure(self) -> None:
        captured: dict[str, Any] = {}

        class _Fake:
            def tool(self, *_args: Any, **_kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    captured[fn.__name__] = fn
                    return fn

                return decorator

        register_session_tools(_Fake())  # type: ignore[arg-type]

        async def fake_impl() -> dict[str, Any]:
            return {"success": False, "error": "synced-fail"}

        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.setattr(mod, "_pre_compact_sync_impl", fake_impl)
            result = await captured["pre_compact_sync"]()
        finally:
            monkeypatch.undo()

        assert "synced-fail" in result

    @pytest.mark.asyncio
    async def test_pre_compact_sync_no_reflection_stored(self) -> None:
        captured: dict[str, Any] = {}

        class _Fake:
            def tool(self, *_args: Any, **_kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    captured[fn.__name__] = fn
                    return fn

                return decorator

        register_session_tools(_Fake())  # type: ignore[arg-type]

        async def fake_impl() -> dict[str, Any]:
            return {
                "success": True,
                "project": "demo",
                "timestamp": "now",
                "quality_score": None,
                "reflection_stored": False,
            }

        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.setattr(mod, "_pre_compact_sync_impl", fake_impl)
            result = await captured["pre_compact_sync"]()
        finally:
            monkeypatch.undo()

        assert "Reflection storage skipped" in result
