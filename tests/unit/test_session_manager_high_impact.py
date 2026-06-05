from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from session_buddy.core.session_manager import (
    SessionLifecycleManager,
    get_session_logger,
)


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> SessionLifecycleManager:
    SessionLifecycleManager._instance = None
    SessionLifecycleManager._session_id = None
    SessionLifecycleManager._initialized = False
    monkeypatch.setattr(SessionLifecycleManager, "_initialize_templates", lambda self: None)
    instance = SessionLifecycleManager(
        logger=Mock(),
        quality_scorer=Mock(get_permissions_score=Mock(return_value=10)),
    )
    yield instance
    SessionLifecycleManager._instance = None
    SessionLifecycleManager._session_id = None
    SessionLifecycleManager._initialized = False


def _install_reflection_utils(
    monkeypatch: pytest.MonkeyPatch,
    *,
    should_store: bool = True,
    reason: str = "recommended",
) -> None:
    fake_reflection_utils = types.ModuleType("session_buddy.utils.reflection_utils")
    fake_reflection_utils.should_auto_store_checkpoint = lambda **kwargs: SimpleNamespace(  # type: ignore[attr-defined]
        should_store=should_store,
        reason=SimpleNamespace(value=reason),
    )
    fake_reflection_utils.format_auto_store_summary = lambda decision: "auto-store summary"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.utils.reflection_utils", fake_reflection_utils)


def test_constructor_falls_back_to_default_quality_scorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SessionLifecycleManager, "_initialize_templates", lambda self: None)
    monkeypatch.setattr(
        "session_buddy.di.get_sync_typed",
        Mock(side_effect=RuntimeError("boom")),
    )

    manager = SessionLifecycleManager()

    from session_buddy.core.quality_scoring import DefaultQualityScorer

    assert isinstance(manager.quality_scorer, DefaultQualityScorer)


def test_initialize_templates_handles_jinja_import_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_jinja2 = types.ModuleType("jinja2")

    def raising_environment(*args, **kwargs):
        raise RuntimeError("jinja unavailable")

    fake_jinja2.Environment = raising_environment  # type: ignore[attr-defined]
    fake_jinja2.FileSystemLoader = lambda *args, **kwargs: object()  # type: ignore[attr-defined]
    fake_jinja2.select_autoescape = lambda *args, **kwargs: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jinja2", fake_jinja2)

    manager = SessionLifecycleManager(
        logger=Mock(),
        quality_scorer=Mock(get_permissions_score=Mock(return_value=10)),
    )

    assert manager.templates is None
    manager.logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_calculate_quality_score_delegates_project_dir_as_string(
    manager: SessionLifecycleManager,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"total_score": 91, "breakdown": {}, "recommendations": []}
    fake_server = types.ModuleType("session_buddy.server")
    fake_server.calculate_quality_score = AsyncMock(return_value=expected)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.server", fake_server)

    result = await manager.calculate_quality_score(project_dir=tmp_path)

    assert result == expected
    fake_server.calculate_quality_score.assert_awaited_once_with(project_dir=str(tmp_path))  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_calculate_quality_score_uses_none_when_project_dir_missing(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"total_score": 77, "breakdown": {}, "recommendations": []}
    fake_server = types.ModuleType("session_buddy.server")
    fake_server.calculate_quality_score = AsyncMock(return_value=expected)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.server", fake_server)

    result = await manager.calculate_quality_score()

    assert result == expected
    fake_server.calculate_quality_score.assert_awaited_once_with(project_dir=None)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_perform_quality_assessment_returns_default_for_invalid_data(
    manager: SessionLifecycleManager,
    tmp_path,
) -> None:
    manager.calculate_quality_score = AsyncMock(return_value=None)

    score, data = await manager.perform_quality_assessment(project_dir=tmp_path)

    assert score == 75
    assert data["total_score"] == 75
    assert data["version"] == "unknown"
    assert data["recommendations"] == ["Quality assessment failed - using default score"]
    manager.logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_perform_quality_assessment_infers_total_score_from_overall(
    manager: SessionLifecycleManager,
) -> None:
    manager.calculate_quality_score = AsyncMock(
        return_value={"overall": 88, "breakdown": {}, "recommendations": []}
    )

    score, data = await manager.perform_quality_assessment()

    assert score == 88
    assert data["total_score"] == 88
    manager.logger.error.assert_called_once()


def test_generate_quality_recommendations_thresholds_and_limit(
    manager: SessionLifecycleManager,
) -> None:
    low = manager._generate_quality_recommendations(45, {}, False)
    mid = manager._generate_quality_recommendations(
        65,
        {"has_pyproject_toml": True, "has_git_repo": True, "has_tests": True},
        True,
    )
    high = manager._generate_quality_recommendations(
        85,
        {"has_pyproject_toml": True, "has_git_repo": True, "has_tests": True},
        True,
    )

    assert low == [
        "Session needs attention - multiple areas for improvement",
        "Consider adding pyproject.toml for modern Python project structure",
        "Initialize git repository for version control",
        "Install UV package manager for improved dependency management",
        "Add test suite to improve code quality",
    ]
    assert mid == ["Good session quality with room for optimization"]
    assert high == ["Excellent session setup! Keep up the good work"]


def test_format_quality_results_includes_trust_object_and_checkpoint_details(
    manager: SessionLifecycleManager,
) -> None:
    trust = SimpleNamespace(
        total=92,
        details={
            "permissions_count": 3,
            "session_available": True,
            "tool_count": 7,
        },
    )
    quality_data = {
        "breakdown": {
            "code_quality": 31.5,
            "project_health": 26.0,
            "dev_velocity": 18.0,
            "security": 9.0,
        },
        "trust_score": trust,
        "recommendations": [
            "first",
            "second",
            "third",
            "fourth",
        ],
    }
    checkpoint_result = {
        "strengths": ["fast", "reliable", "thorough"],
        "session_stats": {
            "duration_minutes": 12,
            "total_checkpoints": 3,
            "success_rate": 66.7,
        },
    }

    output = manager.format_quality_results(85, quality_data, checkpoint_result)

    assert any("EXCELLENT (Score: 85/100)" in line for line in output)
    assert any("Trust score: 92/100" in line for line in output)
    assert any("Trusted operations: 3/40" in line for line in output)
    assert any("Session features: True (available)" in line for line in output)
    assert any("Tool ecosystem: 7 tools" in line for line in output)
    assert any("first" in line for line in output)
    assert any("third" in line for line in output)
    assert not any("fourth" in line for line in output)
    assert any("Session strengths:" in line for line in output)
    assert any("Duration: 12 minutes" in line for line in output)


def test_format_trust_score_ignores_non_dict_details(manager: SessionLifecycleManager) -> None:
    class BadTrust:
        total = 7
        details = ["invalid"]

    assert manager._format_trust_score(BadTrust()) == [
        "\n🔐 Trust score: 7/100 (separate metric)",
    ]
    assert manager._format_trust_score({"total": 5}) == [
        "\n🔐 Trust score: 5/100 (separate metric)",
    ]


def test_setup_working_directory_rejects_invalid_and_escaped_paths(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    nested_base = tmp_path / "base"
    nested_base.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    fake_tmp = tmp_path / "fake_tmp"
    fake_tmp.mkdir()
    regular_file = tmp_path / "regular.txt"
    regular_file.write_text("not a directory")

    monkeypatch.setattr(manager, "_get_current_working_directory", lambda: nested_base)
    monkeypatch.setattr(
        "session_buddy.core.session_manager.tempfile.gettempdir",
        lambda: str(fake_tmp),
    )
    monkeypatch.setattr(
        "session_buddy.core.session_manager.Path.home",
        lambda: tmp_path / "isolated_home",
    )

    with pytest.raises(ValueError, match="Traversal not allowed"):
        manager._setup_working_directory("../traversal")

    with pytest.raises(ValueError, match="Path does not exist"):
        manager._setup_working_directory(str(tmp_path / "missing"))

    with pytest.raises(ValueError, match="Path is not a directory"):
        manager._setup_working_directory(str(regular_file))

    with pytest.raises(ValueError, match="Path escapes base directory"):
        manager._setup_working_directory(str(outside_dir))


def test_get_current_working_directory_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def raising_cwd() -> Path:
        raise FileNotFoundError

    monkeypatch.setattr("session_buddy.core.session_manager.Path.cwd", raising_cwd)
    monkeypatch.setattr("session_buddy.core.session_manager.Path.home", lambda: tmp_path)

    manager = SessionLifecycleManager(
        logger=Mock(),
        quality_scorer=Mock(get_permissions_score=Mock(return_value=10)),
    )

    assert manager._get_current_working_directory() == tmp_path


def test_get_session_logger_returns_module_logger() -> None:
    assert get_session_logger().name == "session_buddy.core.session_manager"


def test_setup_claude_directories_uses_home_then_falls_back(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    home_claude = home_dir / ".claude"

    monkeypatch.setattr("session_buddy.core.session_manager.Path.home", lambda: home_dir)
    monkeypatch.setattr(manager, "_get_current_working_directory", lambda: project_dir)

    original_mkdir = Path.mkdir
    mkdir_calls: list[str] = []

    def fake_mkdir(self: Path, *args, **kwargs):
        mkdir_calls.append(str(self))
        if self == home_claude:
            raise OSError("home blocked")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    result = manager._setup_claude_directories(project_dir)

    assert result == project_dir / ".claude"
    assert any(str(home_claude) == call for call in mkdir_calls)
    assert (project_dir / ".claude" / "data").exists()
    assert (project_dir / ".claude" / "logs").exists()


def test_setup_claude_directories_raises_when_all_candidates_fail(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    monkeypatch.setattr("session_buddy.core.session_manager.Path.home", lambda: home_dir)
    monkeypatch.setattr(manager, "_get_current_working_directory", lambda: project_dir)

    def always_fail(self: Path, *args, **kwargs):
        raise OSError("blocked")

    monkeypatch.setattr(Path, "mkdir", always_fail)

    with pytest.raises(OSError, match="blocked"):
        manager._setup_claude_directories(project_dir)


@pytest.mark.asyncio
async def test_initialize_session_success_uses_helper_results(
    manager: SessionLifecycleManager,
    tmp_path: Path,
) -> None:
    def fake_setup(working_directory: str | None) -> Path:
        manager.current_project = "demo"
        return tmp_path

    manager._setup_working_directory = Mock(side_effect=fake_setup)
    manager._setup_claude_directories = Mock(return_value=tmp_path / ".claude")
    manager.analyze_project_context = AsyncMock(return_value={"has_git_repo": True})
    manager.perform_quality_assessment = AsyncMock(
        return_value=(88, {"breakdown": {}, "recommendations": ["keep"]})
    )
    manager._get_previous_session_info = AsyncMock(return_value={"session_id": "prev"})

    result = await manager.initialize_session("demo")

    assert result["success"] is True
    assert result["project"] == "demo"
    assert result["working_directory"] == str(tmp_path)
    assert result["claude_directory"] == str(tmp_path / ".claude")
    assert result["previous_session"] == {"session_id": "prev"}


@pytest.mark.asyncio
async def test_initialize_session_returns_error_when_setup_fails(
    manager: SessionLifecycleManager,
) -> None:
    manager._setup_working_directory = Mock(side_effect=ValueError("bad setup"))

    result = await manager.initialize_session("demo")

    assert result == {"success": False, "error": "bad setup"}
    manager.logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_status_success(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager.analyze_project_context = AsyncMock(return_value={"has_git_repo": True})
    manager.perform_quality_assessment = AsyncMock(
        return_value=(84, {"breakdown": {"code_quality": 1}, "recommendations": ["ok"]})
    )
    monkeypatch.setattr(
        "session_buddy.core.session_manager.shutil.which",
        lambda name: "/usr/bin/uv" if name == "uv" else None,
    )
    monkeypatch.setattr("session_buddy.core.session_manager.is_git_repository", lambda path: True)
    monkeypatch.setattr("session_buddy.core.session_manager.Path.home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir()

    result = await manager.get_session_status(str(tmp_path))

    assert result["success"] is True
    assert result["project"] == tmp_path.name
    assert result["quality_score"] == 84
    assert result["system_health"] == {
        "uv_available": True,
        "git_repository": True,
        "claude_directory": True,
    }


@pytest.mark.asyncio
async def test_checkpoint_session_success(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_hooks_manager = Mock()
    fake_hooks_manager.execute_hooks = AsyncMock(return_value=["hook-result"])
    monkeypatch.setattr("session_buddy.di.get_sync_typed", Mock(return_value=fake_hooks_manager))

    fake_reflection_utils = types.ModuleType("session_buddy.utils.reflection_utils")
    fake_reflection_utils.should_auto_store_checkpoint = lambda **kwargs: SimpleNamespace(  # type: ignore[attr-defined]
        should_store=True,
        reason=SimpleNamespace(value="recommended"),
    )
    fake_reflection_utils.format_auto_store_summary = lambda decision: "auto-store summary"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.utils.reflection_utils", fake_reflection_utils)

    manager.perform_quality_assessment = AsyncMock(
        return_value=(82, {"breakdown": {"code_quality": 1}, "recommendations": ["ok"]})
    )
    manager._extract_and_store_insights = AsyncMock(return_value=2)
    manager._store_conversation_checkpoint_if_enabled = AsyncMock(
        return_value={"success": True, "conversation_id": "conv-1"}
    )
    manager.perform_git_checkpoint = AsyncMock(return_value=["git-output"])
    manager.format_quality_results = Mock(return_value=["formatted"])

    result = await manager.checkpoint_session(str(tmp_path), is_manual=True)

    assert result["success"] is True
    assert result["quality_score"] == 82
    assert result["git_output"] == ["git-output"]
    assert result["auto_store_summary"] == "auto-store summary"
    assert result["insights_extracted"] == 2
    assert result["conversation_stored"] == {"success": True, "conversation_id": "conv-1"}
    assert result["quality_output"] == ["formatted"]
    assert fake_hooks_manager.execute_hooks.await_count == 2


@pytest.mark.asyncio
async def test_checkpoint_session_continues_when_hooks_di_lookup_fails(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "session_buddy.di.get_sync_typed", Mock(side_effect=RuntimeError("di boom"))
    )
    _install_reflection_utils(monkeypatch)

    manager.perform_quality_assessment = AsyncMock(
        return_value=(76, {"breakdown": {}, "recommendations": []})
    )
    manager._extract_and_store_insights = AsyncMock(return_value=0)
    manager._store_conversation_checkpoint_if_enabled = AsyncMock(
        return_value={"success": True}
    )
    manager.perform_git_checkpoint = AsyncMock(return_value=[])
    manager.format_quality_results = Mock(return_value=[])

    result = await manager.checkpoint_session(str(tmp_path))

    assert result["success"] is True
    assert any(
        call.args == ("Failed to get hooks manager from DI: %s", "di boom")
        for call in manager.logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_checkpoint_session_handles_hook_and_di_failures(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_hooks_manager = Mock()
    fake_hooks_manager.execute_hooks = AsyncMock(
        side_effect=[RuntimeError("pre boom"), []]
    )
    monkeypatch.setattr(
        "session_buddy.di.get_sync_typed", Mock(return_value=fake_hooks_manager)
    )
    _install_reflection_utils(monkeypatch)

    manager.perform_quality_assessment = AsyncMock(
        return_value=(76, {"breakdown": {}, "recommendations": []})
    )
    manager._extract_and_store_insights = AsyncMock(return_value=0)
    manager._store_conversation_checkpoint_if_enabled = AsyncMock(
        return_value={"success": True}
    )
    manager.perform_git_checkpoint = AsyncMock(return_value=[])
    manager.format_quality_results = Mock(return_value=[])

    result = await manager.checkpoint_session(str(tmp_path))

    assert result["success"] is True
    assert any(
        call.args == ("PRE_CHECKPOINT hooks failed: %s", "pre boom")
        for call in manager.logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_checkpoint_session_handles_post_hook_failure(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_hooks_manager = Mock()
    fake_hooks_manager.execute_hooks = AsyncMock(side_effect=[[], RuntimeError("post boom")])
    monkeypatch.setattr(
        "session_buddy.di.get_sync_typed", Mock(return_value=fake_hooks_manager)
    )
    _install_reflection_utils(monkeypatch)

    manager.perform_quality_assessment = AsyncMock(
        return_value=(79, {"breakdown": {}, "recommendations": []})
    )
    manager._extract_and_store_insights = AsyncMock(return_value=0)
    manager._store_conversation_checkpoint_if_enabled = AsyncMock(
        return_value={"success": True}
    )
    manager.perform_git_checkpoint = AsyncMock(return_value=[])
    manager.format_quality_results = Mock(return_value=[])

    result = await manager.checkpoint_session(str(tmp_path))

    assert result["success"] is True
    assert any(
        call.args == ("POST_CHECKPOINT hooks failed: %s", "post boom")
        for call in manager.logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_checkpoint_session_returns_failure_on_outer_exception(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "session_buddy.core.session_manager.generate_ulid",
        Mock(side_effect=RuntimeError("ulid boom")),
    )
    _install_reflection_utils(monkeypatch)

    result = await manager.checkpoint_session(str(tmp_path))

    assert result == {"success": False, "error": "RuntimeError: ulid boom"}
    manager.logger.exception.assert_called_once()


def test_format_quality_results_handles_low_and_medium_scores_and_bad_breakdown(
    manager: SessionLifecycleManager,
) -> None:
    low_output = manager.format_quality_results(
        45,
        {"breakdown": None, "recommendations": []},
    )
    medium_output = manager.format_quality_results(
        65,
        {
            "breakdown": {
                "code_quality": 11.0,
                "project_health": 12.0,
                "dev_velocity": 13.0,
                "security": 14.0,
            },
            "recommendations": ["one", "two", "three", "four"],
        },
    )

    assert any("NEEDS ATTENTION" in line for line in low_output)
    assert any("Quality breakdown: unavailable" in line for line in low_output)
    assert any("GOOD (Score: 65/100)" in line for line in medium_output)
    assert any("Code quality: 11.0/40" in line for line in medium_output)
    assert any("one" in line for line in medium_output)
    assert any("three" in line for line in medium_output)
    assert not any("four" in line for line in medium_output)


@pytest.mark.asyncio
async def test_generate_handoff_documentation_and_save_round_trip(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    populated = await manager._generate_handoff_documentation(
        {
            "project": "demo",
            "session_end_time": "2024-01-01T00:00:00",
            "final_quality_score": 88,
            "working_directory": "/work",
            "recommendations": ["keep going"],
        },
        {"breakdown": {"code_quality": 12, "project_health": 8}},
    )
    defaulted = await manager._generate_handoff_documentation({}, {})

    assert "# Session Handoff Report - demo" in populated
    assert "## Recommendations" in populated
    assert "## Quality Breakdown" in populated
    assert "Session ended" in defaulted
    assert "unknown" in defaulted

    saved = manager._save_handoff_documentation(populated, tmp_path)
    assert saved is not None
    assert saved.read_text() == populated

    def always_block(self: Path, *args, **kwargs):
        raise OSError("blocked")

    monkeypatch.setattr(Path, "write_text", always_block)
    assert manager._save_handoff_documentation(populated, tmp_path) is None


@pytest.mark.asyncio
async def test_read_previous_session_info_handles_json_markdown_and_oserror(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "session.session.json"
    markdown_path = tmp_path / "session_handoff.md"
    broken_path = tmp_path / "broken.session.json"

    json_path.write_text('{"session_id": "json-1", "project": "demo"}')
    markdown_path.write_text("markdown content")

    fake_session_info = SimpleNamespace(
        is_complete=lambda: True,
        ended_at="2024-01-01T00:00:00",
        quality_score=91,
        working_directory="/work",
        top_recommendation="keep going",
        session_id="md-1",
    )
    fake_session_module = types.ModuleType("session_buddy.core.lifecycle.session_info")
    fake_session_module.parse_session_file = AsyncMock(return_value=fake_session_info)
    monkeypatch.setitem(sys.modules, "session_buddy.core.lifecycle.session_info", fake_session_module)

    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs):
        if self == json_path:
            return '{"session_id": "json-1", "project": "demo"}'
        if self == markdown_path:
            return "markdown content"
        if self == broken_path:
            raise OSError("blocked")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert await manager._read_previous_session_info(json_path) == {
        "session_id": "json-1",
        "project": "demo",
    }

    list_path = tmp_path / "list.session.json"
    list_path.write_text("[1, 2, 3]")
    assert await manager._read_previous_session_info(list_path) is None

    markdown_result = await manager._read_previous_session_info(markdown_path)
    assert markdown_result == {
        "ended_at": "2024-01-01T00:00:00",
        "quality_score": 91,
        "working_directory": "/work",
        "top_recommendation": "keep going",
        "session_id": "md-1",
    }

    assert await manager._read_previous_session_info(broken_path) is None


def test_find_latest_handoff_file_prefers_most_recent_candidates(tmp_path: Path) -> None:
    current_dir = tmp_path / "project"
    current_dir.mkdir()

    legacy = current_dir / "session_handoff_old.md"
    legacy.write_text("legacy")
    nested_dir = current_dir / ".crackerjack" / "session" / "handoff"
    nested_dir.mkdir(parents=True)
    nested = nested_dir / "session_handoff_new.md"
    nested.write_text("nested")
    os.utime(legacy, (100, 100))
    os.utime(nested, (200, 200))

    manager = SessionLifecycleManager(
        logger=Mock(),
        quality_scorer=Mock(get_permissions_score=Mock(return_value=10)),
    )

    assert manager._find_latest_handoff_file(current_dir) == nested

    os.utime(legacy, (300, 300))
    assert manager._find_latest_handoff_file(current_dir) == legacy

    json_dir = tmp_path / "json"
    json_dir.mkdir()
    handoff_json = json_dir / "recent.handoff.json"
    session_json = json_dir / "older.session.json"
    handoff_json.write_text("{}")
    session_json.write_text("{}")
    os.utime(handoff_json, (400, 400))
    os.utime(session_json, (100, 100))

    assert manager._find_latest_handoff_file(json_dir) == handoff_json


@pytest.mark.asyncio
async def test_get_previous_session_info_uses_session_files_then_handoff(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_path = tmp_path / "session.session.json"
    handoff_path = tmp_path / "session_handoff.md"

    manager._discover_session_files = Mock(return_value=[session_path])
    manager._read_previous_session_info = AsyncMock(return_value={"session_id": "direct"})
    manager._find_latest_handoff_file = Mock(return_value=handoff_path)

    assert await manager._get_previous_session_info(tmp_path) == {"session_id": "direct"}
    manager._find_latest_handoff_file.assert_not_called()

    manager._discover_session_files = Mock(return_value=[])
    manager._read_previous_session_info = AsyncMock(return_value={"session_id": "from-handoff"})

    assert await manager._get_previous_session_info(tmp_path) == {"session_id": "from-handoff"}
    manager._find_latest_handoff_file.assert_called_once_with(tmp_path)

    manager._read_previous_session_info = AsyncMock(return_value=None)
    manager._find_latest_handoff_file = Mock(return_value=None)
    assert await manager._get_previous_session_info(tmp_path) is None


@pytest.mark.asyncio
async def test_analyze_project_context_covers_positive_and_error_branches(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_dir = tmp_path / "project"
    current_dir.mkdir()
    (current_dir / "README.md").write_text("# docs")
    (current_dir / "pyproject.toml").write_text("django = '*'\n")
    (current_dir / "setup.py").write_text("setup()")
    (current_dir / "requirements.txt").write_text("fastapi\n")
    (current_dir / "src").mkdir()
    (current_dir / ".github").mkdir()
    (current_dir / ".venv").mkdir()
    (current_dir / "docs").mkdir()
    (current_dir / "docs" / "index.md").write_text("docs")
    (current_dir / "test_sample.py").write_text("import flask")
    (current_dir / "app.py").write_text("import fastapi\nimport django\nimport flask")

    monkeypatch.setattr(
        "session_buddy.core.session_manager.is_git_repository",
        lambda path: True,
    )

    original_glob = Path.glob

    def fake_glob(self: Path, pattern: str):
        if self == current_dir and pattern == "README*":
            raise OSError("blocked")
        return original_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", fake_glob)

    result = await manager.analyze_project_context(current_dir)

    assert result == {
        "has_git_repo": True,
        "has_readme": False,
        "has_pyproject_toml": True,
        "has_setup_py": True,
        "has_requirements_txt": True,
        "has_src_structure": True,
        "has_tests": True,
        "has_docs": True,
        "has_ci_cd": True,
        "has_venv": True,
        "has_python_files": True,
        "uses_fastapi": True,
        "uses_django": True,
        "uses_flask": True,
    }


def test_validate_working_directory_and_score_history(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    assert manager._validate_working_directory(str(project_dir)) == project_dir.resolve()

    home_dir = tmp_path / "home"
    monkeypatch.setattr("session_buddy.core.session_manager.Path.home", lambda: home_dir)
    assert manager._validate_working_directory(str(home_dir)) == home_dir

    missing_home = tmp_path / "missing-home"
    monkeypatch.setattr("session_buddy.core.session_manager.Path.home", lambda: missing_home)
    assert manager._validate_working_directory(str(missing_home)) == missing_home

    regular_file = tmp_path / "file.txt"
    regular_file.write_text("content")

    with pytest.raises(ValueError, match="Traversal not allowed"):
        manager._validate_working_directory("../escape")

    with pytest.raises(ValueError, match="Path does not exist"):
        manager._validate_working_directory(str(tmp_path / "missing"))

    with pytest.raises(ValueError, match="Path is not a directory"):
        manager._validate_working_directory(str(regular_file))

    working_dir = tmp_path / "working"
    working_dir.mkdir()
    monkeypatch.setattr(
        manager,
        "_get_current_working_directory",
        Mock(side_effect=FileNotFoundError),
    )
    monkeypatch.setattr("session_buddy.core.session_manager.os.chdir", Mock())
    assert manager._setup_working_directory(str(working_dir)) == working_dir.resolve()
    assert manager.current_project == working_dir.name
    assert manager._setup_working_directory(None) == missing_home

    assert manager.get_previous_quality_score("demo") is None
    for score in range(12):
        manager.record_quality_score("demo", score)

    assert manager.get_previous_quality_score("demo") == 11
    assert manager._quality_history["demo"] == list(range(2, 12))


def test_quality_helper_methods_and_format_result(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_context = {"a": True, "b": False, "c": True, "d": True}
    assert manager._calculate_project_score(project_context) == 30.0
    assert manager._calculate_permissions_score() == 10
    assert manager._calculate_session_score() == 20

    monkeypatch.setattr(
        "session_buddy.core.session_manager.shutil.which",
        lambda name: None,
    )
    assert manager._calculate_tool_score() == 10

    monkeypatch.setattr(
        "session_buddy.core.session_manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )
    assert manager._calculate_tool_score() == 20

    formatted = manager._format_quality_score_result(
        81,
        30.0,
        10,
        20,
        20,
        {
            "has_git_repo": True,
            "has_pyproject_toml": True,
            "has_tests": True,
        },
        True,
    )
    assert formatted["total_score"] == 81
    assert formatted["breakdown"]["project_health"] == 30.0
    assert formatted["recommendations"] == ["Excellent session setup! Keep up the good work"]


@pytest.mark.asyncio
async def test_extract_and_store_insights_covers_disabled_success_and_failure(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    disabled_settings = SimpleNamespace(
        enable_insight_extraction=False,
        insight_extraction_confidence_threshold=0.4,
        insight_extraction_max_per_checkpoint=5,
        database_path=tmp_path / "db.duckdb",
    )
    enabled_settings = SimpleNamespace(
        enable_insight_extraction=True,
        insight_extraction_confidence_threshold=0.4,
        insight_extraction_max_per_checkpoint=1,
        database_path=tmp_path / "db.duckdb",
    )

    fake_settings_module = types.ModuleType("session_buddy.settings")
    fake_settings_module.SessionMgmtSettings = lambda: disabled_settings  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.settings", fake_settings_module)

    manager.current_project = "demo"
    assert await manager._extract_and_store_insights("checkpoint") == 0

    fake_settings_module.SessionMgmtSettings = lambda: enabled_settings  # type: ignore[attr-defined]

    fake_insight = SimpleNamespace(
        content="insight",
        insight_type="note",
        topics=["topic"],
        source_conversation_id="conv-1",
        source_reflection_id="ref-1",
        confidence=0.9,
        quality_score=88,
    )
    fake_extractor_module = types.ModuleType("session_buddy.insights.extractor")
    fake_extractor_module.extract_insights_from_context = lambda **kwargs: [fake_insight, fake_insight]  # type: ignore[attr-defined]
    fake_extractor_module.filter_duplicate_insights = lambda insights, seen_hashes: ([insights[0]], {"seen"})  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules, "session_buddy.insights.extractor", fake_extractor_module
    )

    stored_calls: list[dict[str, object]] = []

    class FakeReflectionDatabase:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self) -> FakeReflectionDatabase:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def store_insight(self, **kwargs) -> None:
            stored_calls.append(kwargs)

    fake_reflection_module = types.ModuleType(
        "session_buddy.adapters.reflection_adapter_oneiric"
    )
    fake_reflection_module.ReflectionDatabase = FakeReflectionDatabase  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        fake_reflection_module,
    )

    fake_adapter_settings = types.ModuleType("session_buddy.adapters.settings")
    fake_adapter_settings.ReflectionAdapterSettings = lambda **kwargs: SimpleNamespace(**kwargs)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.adapters.settings", fake_adapter_settings)

    assert await manager._extract_and_store_insights("checkpoint") == 1
    assert stored_calls and stored_calls[0]["content"] == "insight"
    assert manager._captured_insight_hashes == {"seen"}

    manager.current_project = None
    stored_calls.clear()
    fake_extractor_module.extract_insights_from_context = lambda **kwargs: [fake_insight]  # type: ignore[attr-defined]
    fake_extractor_module.filter_duplicate_insights = lambda insights, seen_hashes: ([insights[0]], {"seen-2"})  # type: ignore[attr-defined]

    assert await manager._extract_and_store_insights("session_end") == 1
    assert stored_calls and stored_calls[0]["projects"] is None

    fake_extractor_module.extract_insights_from_context = lambda **kwargs: []  # type: ignore[attr-defined]
    fake_extractor_module.filter_duplicate_insights = lambda insights, seen_hashes: ([], seen_hashes)  # type: ignore[attr-defined]

    assert await manager._extract_and_store_insights("checkpoint") == 0

    fake_extractor_module.extract_insights_from_context = Mock(side_effect=RuntimeError("boom"))  # type: ignore[attr-defined]
    assert await manager._extract_and_store_insights("checkpoint") == 0
    assert any(
        call.args == (
            "Insight extraction failed at %s (continuing), error=%s",
            "checkpoint",
            "boom",
        )
        for call in manager.logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_analyze_project_context_handles_read_and_glob_failures(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_dir = tmp_path / "project"
    current_dir.mkdir()
    (current_dir / "requirements.txt").write_text("fastapi")
    (current_dir / "pyproject.toml").write_text("django")
    (current_dir / "app.py").write_text("print('x')")

    monkeypatch.setattr(
        "session_buddy.core.session_manager.is_git_repository",
        lambda path: False,
    )

    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs):
        if self.name in {"requirements.txt", "pyproject.toml"}:
            raise OSError("blocked")
        return original_read_text(self, *args, **kwargs)

    def fake_glob(self: Path, pattern: str):
        if pattern == "**/*.py":
            raise OSError("glob blocked")
        return []

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    monkeypatch.setattr(Path, "glob", fake_glob)

    result = await manager.analyze_project_context(current_dir)

    assert result["has_git_repo"] is False
    assert result["has_python_files"] is False
    assert result["uses_fastapi"] is False
    assert result["uses_django"] is False
    assert result["uses_flask"] is False


def test_discover_session_files_and_handoff_fallbacks(
    manager: SessionLifecycleManager,
    tmp_path: Path,
) -> None:
    current_dir = tmp_path / "project"
    current_dir.mkdir()
    direct_session = current_dir / "alpha.session.json"
    nested_session = current_dir / "nested" / "beta.session.json"
    nested_session.parent.mkdir()
    direct_session.write_text("{}")
    nested_session.write_text("{}")
    assert set(manager._discover_session_files(current_dir)) == {
        direct_session,
        nested_session,
    }
    assert manager._find_latest_handoff_file(current_dir) == nested_session

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert manager._find_latest_handoff_file(empty_dir) is None

    legacy_only = tmp_path / "legacy"
    legacy_only.mkdir()
    legacy = legacy_only / "session_handoff_old.md"
    legacy.write_text("legacy")
    assert manager._find_latest_handoff_file(legacy_only) == legacy


@pytest.mark.asyncio
async def test_end_session_success(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_hooks_manager = Mock()
    fake_hooks_manager.execute_hooks = AsyncMock(return_value=["hook"])
    monkeypatch.setattr("session_buddy.di.get_sync_typed", Mock(return_value=fake_hooks_manager))

    manager.perform_quality_assessment = AsyncMock(
        return_value=(81, {"breakdown": {}, "recommendations": ["done"]})
    )
    manager._extract_and_store_insights = AsyncMock(return_value=1)
    manager._store_conversation_checkpoint_if_enabled = AsyncMock(
        return_value={"success": True, "conversation_id": "conv-2"}
    )
    manager._generate_handoff_documentation = AsyncMock(return_value="handoff")
    manager._save_handoff_documentation = Mock(return_value=tmp_path / "handoff.md")

    result = await manager.end_session(str(tmp_path))

    assert result["success"] is True
    assert result["summary"]["project"] == tmp_path.name
    assert result["summary"]["final_quality_score"] == 81
    assert result["summary"]["handoff_documentation"] == str(tmp_path / "handoff.md")
    assert result["summary"]["insights_extracted"] == 1
    assert result["summary"]["conversation_stored"] == {"success": True, "conversation_id": "conv-2"}
    assert fake_hooks_manager.execute_hooks.await_count == 2


@pytest.mark.asyncio
async def test_end_session_continues_when_hooks_di_lookup_fails(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "session_buddy.di.get_sync_typed", Mock(side_effect=RuntimeError("di boom"))
    )
    manager.perform_quality_assessment = AsyncMock(
        return_value=(81, {"breakdown": {}, "recommendations": ["done"]})
    )
    manager._extract_and_store_insights = AsyncMock(return_value=1)
    manager._store_conversation_checkpoint_if_enabled = AsyncMock(
        return_value={"success": True, "conversation_id": "conv-2"}
    )
    manager._generate_handoff_documentation = AsyncMock(return_value="handoff")
    manager._save_handoff_documentation = Mock(return_value=tmp_path / "handoff.md")

    result = await manager.end_session(str(tmp_path))

    assert result["success"] is True
    assert any(
        call.args == ("PRE_SESSION_END hooks failed: %s", "di boom")
        for call in manager.logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_end_session_handles_hook_failures_and_outer_exception(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_hooks_manager = Mock()
    fake_hooks_manager.execute_hooks = AsyncMock(side_effect=[RuntimeError("pre boom"), []])
    monkeypatch.setattr(
        "session_buddy.di.get_sync_typed", Mock(return_value=fake_hooks_manager)
    )
    manager.perform_quality_assessment = AsyncMock(
        return_value=(81, {"breakdown": {}, "recommendations": ["done"]})
    )
    manager._extract_and_store_insights = AsyncMock(return_value=1)
    manager._store_conversation_checkpoint_if_enabled = AsyncMock(
        return_value={"success": True, "conversation_id": "conv-2"}
    )
    manager._generate_handoff_documentation = AsyncMock(return_value="handoff")
    manager._save_handoff_documentation = Mock(return_value=tmp_path / "handoff.md")

    result = await manager.end_session(str(tmp_path))

    assert result["success"] is True
    assert any(
        call.args == ("PRE_SESSION_END hooks failed: %s", "pre boom")
        for call in manager.logger.warning.call_args_list
    )

    manager.logger.warning.reset_mock()
    fake_hooks_manager.execute_hooks = AsyncMock(side_effect=[[], RuntimeError("post boom")])

    result = await manager.end_session(str(tmp_path))

    assert result["success"] is True
    assert any(
        call.args == ("SESSION_END hooks failed: %s", "post boom")
        for call in manager.logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_end_session_returns_failure_on_outer_exception(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_hooks_manager = Mock()
    fake_hooks_manager.execute_hooks = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "session_buddy.di.get_sync_typed", Mock(return_value=fake_hooks_manager)
    )
    manager.perform_quality_assessment = AsyncMock(
        return_value=(81, {"breakdown": {}, "recommendations": ["done"]})
    )
    manager._extract_and_store_insights = AsyncMock(return_value=1)
    manager._store_conversation_checkpoint_if_enabled = AsyncMock(
        return_value={"success": True, "conversation_id": "conv-2"}
    )
    manager._generate_handoff_documentation = AsyncMock(
        side_effect=RuntimeError("handoff boom")
    )

    result = await manager.end_session(str(tmp_path))

    assert result == {"success": False, "error": "handoff boom"}
    manager.logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_perform_git_checkpoint_success_and_failure_paths(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "session_buddy.core.session_manager.create_checkpoint_commit",
        lambda current_dir, project, quality_score: (
            True,
            "commit-123",
            ["git line 1", "git line 2"],
        ),
    )
    manager._schedule_git_maintenance = AsyncMock(return_value=None)
    manager.current_project = "demo"

    success_output = await manager.perform_git_checkpoint(tmp_path, 88)

    assert any("Git Checkpoint Commit" in line for line in success_output)
    assert "git line 1" in success_output
    assert manager._schedule_git_maintenance.await_count == 1

    monkeypatch.setattr(
        "session_buddy.core.session_manager.create_checkpoint_commit",
        Mock(side_effect=RuntimeError("git boom")),
    )

    failure_output = await manager.perform_git_checkpoint(tmp_path, 88)

    assert any("Git operations error" in line for line in failure_output)
    manager.logger.exception.assert_called()


@pytest.mark.asyncio
async def test_schedule_git_maintenance_covers_settings_and_gc_paths(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = SimpleNamespace(
        git_auto_gc=False,
        git_gc_only_when_clean=True,
        git_gc_prune_delay=10,
        git_gc_auto_threshold=25,
    )
    fake_settings_module = types.ModuleType("session_buddy.settings")
    fake_settings_module.get_settings = lambda: settings  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.settings", fake_settings_module)

    git_gc = Mock(return_value=(True, "scheduled"))
    monkeypatch.setattr(
        "session_buddy.core.session_manager.schedule_automatic_git_gc", git_gc
    )
    monkeypatch.setattr(
        "session_buddy.core.session_manager.is_git_operation_in_progress",
        lambda directory: True,
    )

    output: list[str] = []
    await manager._schedule_git_maintenance(tmp_path, output)

    assert output == []
    git_gc.assert_not_called()

    settings.git_auto_gc = True
    manager.current_project = "demo"

    output = []
    await manager._schedule_git_maintenance(tmp_path, output)

    assert output == ["\n🔄 Git operation in progress - skipping gc"]
    git_gc.assert_not_called()

    monkeypatch.setattr(
        "session_buddy.core.session_manager.is_git_operation_in_progress",
        lambda directory: False,
    )

    output = []
    await manager._schedule_git_maintenance(tmp_path, output)

    assert output == ["\n🧹 scheduled"]
    git_gc.assert_called_once_with(
        tmp_path,
        prune_delay=10,
        auto_threshold=25,
    )
    assert any(
        call.args[0] == "Scheduled git gc, project=%s, prune_delay=%s, threshold=%d"
        for call in manager.logger.info.call_args_list
    )

    manager.logger.warning.reset_mock()
    git_gc.reset_mock(return_value=True, side_effect=False)
    git_gc.side_effect = RuntimeError("gc boom")
    output = []
    await manager._schedule_git_maintenance(tmp_path, output)
    assert any(
        call.args[0] == "Git maintenance scheduling failed (continuing), project=%s, error=%s"
        for call in manager.logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_store_conversation_checkpoint_if_enabled_covers_modes(
    manager: SessionLifecycleManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        auto_store_conversations_on_checkpoint=False,
        auto_store_conversations_on_session_end=True,
    )
    fake_settings_module = types.ModuleType("session_buddy.settings")
    fake_settings_module.get_settings = lambda: settings  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.settings", fake_settings_module)

    store = AsyncMock(return_value={"success": True, "conversation_id": "conv-9"})
    fake_storage_module = types.ModuleType("session_buddy.core.conversation_storage")
    fake_storage_module.store_conversation_checkpoint = store  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules, "session_buddy.core.conversation_storage", fake_storage_module
    )

    disabled = await manager._store_conversation_checkpoint_if_enabled(
        checkpoint_type="checkpoint",
        quality_score=80,
        is_manual=False,
    )
    assert disabled == {"success": False, "reason": "disabled_in_settings"}
    store.assert_not_called()

    checkpoint_enabled = await manager._store_conversation_checkpoint_if_enabled(
        checkpoint_type="session_end",
        quality_score=80,
        is_manual=False,
    )
    assert checkpoint_enabled == {"success": True, "conversation_id": "conv-9"}
    store.assert_awaited_once()

    store.reset_mock()
    settings.auto_store_conversations_on_session_end = False
    manual_enabled = await manager._store_conversation_checkpoint_if_enabled(
        checkpoint_type="manual",
        quality_score=80,
        is_manual=True,
    )
    assert manual_enabled == {"success": True, "conversation_id": "conv-9"}
    store.assert_awaited_once()

    store.reset_mock(side_effect=True)
    store.side_effect = RuntimeError("store boom")
    result = await manager._store_conversation_checkpoint_if_enabled(
        checkpoint_type="manual",
        quality_score=80,
        is_manual=True,
    )
    assert result == {"success": False, "error": "store boom"}
    assert any(
        call.args == ("Conversation storage failed (continuing), project=%s, error=%s", manager.current_project, "store boom")
        for call in manager.logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_get_session_status_returns_failure_on_exception(
    manager: SessionLifecycleManager,
    tmp_path,
) -> None:
    manager.analyze_project_context = AsyncMock(return_value={"has_git_repo": False})
    manager.perform_quality_assessment = AsyncMock(side_effect=RuntimeError("boom"))

    result = await manager.get_session_status(str(tmp_path))

    assert result["success"] is False
    assert "boom" in result["error"]
    manager.logger.exception.assert_called_once()
