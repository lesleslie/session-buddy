from __future__ import annotations

import importlib
import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


def test_compatibility_shims_importable() -> None:
    file_utils = importlib.import_module("session_buddy.utils.file_utils")
    logging_utils = importlib.import_module("session_buddy.utils.logging_utils")
    quality_utils_v2 = importlib.import_module(
        "session_buddy.utils.quality_utils_v2"
    )

    assert hasattr(file_utils, "_cleanup_temp_files")
    assert hasattr(logging_utils, "SessionLogger")
    assert hasattr(quality_utils_v2, "QualityScoreV2")
    assert (
        sys.modules["session_buddy.utils.quality_utils_v2"]
        is sys.modules["session_buddy.utils.quality_scoring"]
    )


def test_module_entrypoint_delegates_to_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from session_buddy import __main__

    called = {}

    def fake_cli_main() -> None:
        called["ok"] = True

    monkeypatch.setattr("session_buddy.cli.main", fake_cli_main)

    __main__.main()

    assert called == {"ok": True}


def test_quality_recommendations_cover_all_branches() -> None:
    from session_buddy.utils.quality.recommendations import (
        generate_quality_recommendations,
    )

    low = generate_quality_recommendations(
        score=12,
        project_context={},
        permissions_count=0,
        uv_available=False,
    )
    mid = generate_quality_recommendations(
        score=60,
        project_context={"has_tests": True},
        permissions_count=3,
        uv_available=True,
    )
    high = generate_quality_recommendations(
        score=90,
        project_context={"has_tests": True, "has_docs": True},
        permissions_count=6,
        uv_available=True,
    )

    assert low == [
        "Session needs attention - multiple areas for improvement",
        "Consider adding tests to improve project structure",
        "Documentation would enhance project maturity",
        "No trusted operations yet - permissions will be granted on first use",
        "Install UV package manager for better dependency management",
    ]
    assert mid == [
        "Good session health - minor optimizations available",
        "Documentation would enhance project maturity",
    ]
    assert high == [
        "Excellent session quality - maintain current practices",
        "Many trusted operations - consider reviewing for security",
    ]


def test_mode_base_configuration_and_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import session_buddy.modes.base as modes_base

    from session_buddy.modes.base import (
        ModeConfig,
        OperationMode,
        get_mode,
        register_mode,
    )

    config = ModeConfig(
        name="lite",
        database_path=":memory:",
        storage_backend="memory",
        additional_settings={"custom": "value"},
    )
    assert config.to_dict() == {
        "mode": "lite",
        "database_path": ":memory:",
        "storage_backend": "memory",
        "enable_embeddings": True,
        "enable_multi_project": True,
        "enable_token_optimization": True,
        "enable_auto_checkpoint": True,
        "enable_full_text_search": True,
        "enable_faceted_search": True,
        "enable_search_suggestions": True,
        "enable_auto_store": True,
        "enable_crackerjack": True,
        "enable_git_integration": True,
        "custom": "value",
    }

    class DummyMode(OperationMode):
        @property
        def name(self) -> str:
            return "dummy"

        def get_config(self) -> ModeConfig:
            return config

    assert DummyMode().validate_environment() == []
    assert DummyMode().get_startup_message() == "🚀 Starting Session-Buddy in dummy mode..."

    class DummyLiteMode(DummyMode):
        pass

    class DummyStandardMode(DummyMode):
        pass

    register_mode(DummyMode)
    monkeypatch.setattr("session_buddy.modes.base.LiteMode", DummyLiteMode)
    monkeypatch.setattr("session_buddy.modes.base.StandardMode", DummyStandardMode)
    monkeypatch.setenv("SESSION_BUDDY_MODE", "lite")

    assert isinstance(get_mode(), DummyLiteMode)
    assert isinstance(get_mode("standard"), DummyStandardMode)
    assert modes_base._MODE_REGISTRY["dummymode"] is DummyMode

    with pytest.raises(ValueError, match="Invalid mode"):
        get_mode("unsupported")


def test_backend_base_session_state_and_storage() -> None:
    from session_buddy.backends.base import SessionState, SessionStorage

    state = SessionState(
        session_id="s1",
        user_id="u1",
        project_id="p1",
        created_at="2026-01-01T10:00:00",
        last_activity="2026-01-01T10:05:00",
    )

    assert state.to_dict()["session_id"] == "s1"
    assert SessionState.from_dict(state.to_dict()) == state
    assert state.get_compressed_size() > 0

    with pytest.raises(ValueError, match="Invalid ISO timestamp format"):
        SessionState(
            session_id="s1",
            user_id="u1",
            project_id="p1",
            created_at="not-an-iso-time",
            last_activity="2026-01-01T10:05:00",
        )

    class DummyStorage(SessionStorage):
        async def store_session(self, session_state, ttl_seconds=None) -> bool:
            return True

        async def retrieve_session(self, session_id: str):
            return None

        async def delete_session(self, session_id: str) -> bool:
            return True

        async def list_sessions(self, user_id=None, project_id=None) -> list[str]:
            return []

        async def cleanup_expired_sessions(self) -> int:
            return 0

        async def is_available(self) -> bool:
            return True

    storage = DummyStorage({"backend": "dummy"})
    assert storage.config == {"backend": "dummy"}
    assert storage.logger.name == "serverless.dummystorage"


def test_llm_models_dataclasses() -> None:
    from session_buddy.llm.models import (
        LLMMessage,
        LLMResponse,
        StreamChunk,
        StreamGenerationOptions,
    )
    from session_buddy.types import JsonDict, JsonValue

    options = StreamGenerationOptions(provider="openai", model="gpt-4o")
    assert options.provider == "openai"
    assert options.use_fallback is True
    with pytest.raises(FrozenInstanceError):
        options.provider = "anthropic"  # type: ignore[misc]

    chunk = StreamChunk.content_chunk("hello", provider="openai")
    error = StreamChunk.error_chunk("boom")
    assert chunk.content == "hello"
    assert chunk.provider == "openai"
    assert error.is_error is True
    assert error.metadata == {"error": "boom"}

    message = LLMMessage(role="user", content="hi")
    preset_message = LLMMessage(
        role="assistant",
        content="hello",
        timestamp="2026-01-01T10:00:00",
        metadata={"source": "test"},
    )
    response = LLMResponse(
        content="ok",
        model="gpt",
        provider="openai",
        usage={"prompt_tokens": 1},
        finish_reason="stop",
        timestamp="2026-01-01T10:00:00",
        metadata={"latency_ms": 10},
    )
    response_default = LLMResponse(
        content="ok",
        model="gpt",
        provider="openai",
        usage={"prompt_tokens": 1},
        finish_reason="stop",
        timestamp="2026-01-01T10:00:00",
    )

    assert message.timestamp is not None
    assert message.metadata == {}
    assert preset_message.timestamp == "2026-01-01T10:00:00"
    assert preset_message.metadata == {"source": "test"}
    assert response.metadata == {"latency_ms": 10}
    assert response_default.metadata == {}
    assert JsonValue is not None
    json_dict: JsonDict = {"message": "ok"}
    assert json_dict["message"] == "ok"


def test_path_validation_security_branches(tmp_path: Path) -> None:
    from session_buddy.utils.path_validation import (
        PathValidator,
        validate_working_directory,
    )

    validator = PathValidator()
    validator.allowed_directories.add(tmp_path)

    assert PathValidator.ALLOWED_SCHEMES == {"file", ""}
    assert PathValidator.MAX_PATH_LENGTH == 4096
    assert validator.validate_user_path(tmp_path) == tmp_path.resolve()
    assert validate_working_directory(None) == Path.cwd()

    with pytest.raises(ValueError, match="Null bytes not allowed"):
        validator.validate_user_path("bad\x00path")

    with pytest.raises(ValueError, match="Null bytes not allowed"):
        validator.validate_user_path(Path("valid") / Path("\x00"))

    with pytest.raises(ValueError, match="Path too long"):
        validator.validate_user_path("a" * (PathValidator.MAX_PATH_LENGTH + 1))

    with pytest.raises(ValueError, match="outside allowed directories|escapes base directory"):
        # Path("..") resolves to a parent directory, which the validator
        # rejects as a traversal attempt ("escapes base directory") before
        # it falls through to the "outside allowed directories" check.
        # Either rejection is acceptable behavior for this security branch.
        validator.validate_user_path(Path("..") / "outside", base_dir=tmp_path)

    with pytest.raises(ValueError, match="escapes base directory"):
        with pytest.MonkeyPatch.context() as mp:
            other_dir = Path(tmp_path.parent / "other-path-validation-dir")
            other_dir.mkdir(exist_ok=True)
            mp.setattr(Path, "exists", lambda self: True)
            mp.setattr(Path, "is_dir", lambda self: True)
            validator.validate_user_path(other_dir, base_dir=tmp_path)

    assert validator.validate_user_path(tmp_path, allow_traversal=True)

    with pytest.raises(ValueError, match="Path does not exist"):
        validator.validate_user_path(tmp_path / "missing")

    file_path = tmp_path / "file.txt"
    file_path.write_text("content")
    with pytest.raises(ValueError, match="Path is not a directory"):
        validator.validate_user_path(file_path)

    with pytest.raises(ValueError, match="not permitted"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(Path, "exists", lambda self: True)
            mp.setattr(Path, "is_dir", lambda self: False)
            PathValidator().validate_user_path("/dev/null")

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    assert PathValidator.validate_git_path(git_dir) == git_dir.resolve()

    with pytest.raises(ValueError, match="Direct .git access blocked"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                PathValidator,
                "validate_user_path",
                staticmethod(lambda path, allow_traversal=False, base_dir=None: Path("/path/.git/config")),
            )
            PathValidator.validate_git_path("/path/.git/config")

    assert validate_working_directory(str(tmp_path)) == tmp_path.resolve()


def test_mcp_schema_registry_branches(tmp_path: Path) -> None:
    from session_buddy.mcp import schemas
    from session_buddy.mcp.event_models import SessionStartEvent

    all_schemas = schemas.get_all_schemas()
    assert "SessionStartEvent" in all_schemas
    assert "SessionEndEvent" in all_schemas
    assert schemas.get_schema_version() == "1.0"
    assert schemas.list_event_models()[0] == "SessionStartEvent"
    assert schemas.check_schema_compatibility("1.0") is True
    assert schemas.check_schema_compatibility("2.0") is False
    assert "1.0" in schemas.get_schema_changelog()

    schema = schemas.get_schema("SessionStartEvent")
    assert schema["title"] == "SessionStartEvent"
    assert schema["event_version"] == "1.0"

    event = schemas.validate_event_json(
        "SessionStartEvent",
        {
            "event_version": "1.0",
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "component_name": "mahavishnu",
            "shell_type": "MahavishnuShell",
            "timestamp": "2026-02-06T12:34:56.789Z",
            "pid": 12345,
            "user": {"username": "john", "home": "/home/john"},
            "hostname": "server01",
            "environment": {
                "python_version": "3.13.0",
                "platform": "Linux-6.5.0-x86_64",
                "cwd": "/home/john/projects",
            },
        },
    )
    assert isinstance(event, SessionStartEvent)

    event_from_string = schemas.validate_event_json(
        "SessionStartEvent",
        json.dumps(
            {
                "event_version": "1.0",
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "component_name": "mahavishnu",
                "shell_type": "MahavishnuShell",
                "timestamp": "2026-02-06T12:34:56.789Z",
                "pid": 12345,
                "user": {"username": "john", "home": "/home/john"},
                "hostname": "server01",
                "environment": {
                    "python_version": "3.13.0",
                    "platform": "Linux-6.5.0-x86_64",
                    "cwd": "/home/john/projects",
                },
            }
        ),
    )
    assert isinstance(event_from_string, SessionStartEvent)

    with pytest.raises(ValueError, match="Unknown model"):
        schemas.get_schema("UnknownModel")

    with pytest.raises(ValueError, match="Unknown model"):
        schemas.validate_event_json("UnknownModel", {})

    with pytest.raises(ValueError, match="Unsupported format"):
        schemas.export_schemas_to_file(tmp_path / "schemas.txt", format="txt")

    output = tmp_path / "schemas.json"
    schemas.export_schemas_to_file(output, format="json")
    assert output.exists()

    with output.open("r", encoding="utf-8") as f:
        exported = json.load(f)
    assert exported["SessionStartEvent"]["event_version"] == "1.0"

    yaml_output = tmp_path / "schemas.yaml"
    schemas.export_schemas_to_file(yaml_output, format="yaml")
    assert yaml_output.exists()

    with pytest.raises(ValueError, match="Unsupported event version"):
        schemas.validate_event_version("2.0")

    schemas.validate_event_version("1.0")


def test_value_objects_default_and_custom_state() -> None:
    from datetime import datetime

    from session_buddy.session_types import (
        RecurrenceInterval,
        SQLCondition,
        TimeRange,
    )
    from session_buddy.utils.scheduler.models import (
        NaturalReminder,
        ReminderStatus,
        ReminderType,
        SchedulingContext,
    )
    from session_buddy.utils.search.models import (
        SearchFacet,
        SearchFilter,
        SearchResult,
    )

    start = datetime(2026, 1, 1, 10, 0, 0)
    end = datetime(2026, 1, 1, 11, 0, 0)
    time_range = TimeRange(start=start, end=end)
    condition = SQLCondition(
        condition="created_at >= ?",
        params=[start],
    )
    recurrence = RecurrenceInterval(frequency="daily", interval=3)

    search_filter = SearchFilter(field="project", operator="eq", value="session-buddy")
    facet = SearchFacet(name="project", values=[("session-buddy", 2)])
    result = SearchResult(
        content_id="1",
        content_type="note",
        title="Session",
        content="hello",
        score=0.75,
    )

    reminder = NaturalReminder(
        reminder_id="rem-1",
        reminder_type=ReminderType.TASK,
        expression="tomorrow",
        scheduled_time=start,
        action="review",
    )
    context = SchedulingContext(session_start=start, current_task="review")

    assert time_range.start == start
    assert time_range.end == end
    assert condition.condition == "created_at >= ?"
    assert condition.params == [start]
    assert recurrence.frequency == "daily"
    assert recurrence.interval == 3
    assert search_filter.negate is False
    assert facet.facet_type == "terms"
    assert result.metadata == {}
    assert result.highlights == []
    assert result.facets == {}
    assert reminder.status is ReminderStatus.PENDING
    assert reminder.executed_at is None
    assert reminder.failure_reason is None
    assert context.session_start == start
    assert context.current_task == "review"


def test_project_analysis_helpers_and_async_entrypoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.core.lifecycle import project_context as lifecycle_context
    from session_buddy.utils import project_analysis

    (tmp_path / "README.md").write_text("readme")
    (tmp_path / ".venv").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".github").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
    (tmp_path / "requirements.txt").write_text("pytest\n")
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / ".mcp.json").write_text("{}")
    (tmp_path / "app.py").write_text(
        "import fastapi\nfrom django.http import HttpResponse\nimport flask\n",
    )

    monkeypatch.setattr(lifecycle_context, "is_git_repository", lambda _: True)

    assert lifecycle_context.check_readme_exists(tmp_path) is True
    assert lifecycle_context.check_venv_exists(tmp_path) is True
    assert lifecycle_context.check_tests_exist(tmp_path) is True
    assert lifecycle_context.check_docs_exist(tmp_path) is True
    assert lifecycle_context.check_ci_cd_exists(tmp_path) is True

    indicators = lifecycle_context.get_basic_project_indicators(tmp_path)
    assert indicators["has_pyproject_toml"] is True
    assert indicators["has_setup_py"] is False
    assert indicators["has_requirements_txt"] is True
    assert indicators["has_readme"] is True
    assert indicators["has_git_repo"] is True
    assert indicators["has_venv"] is True
    assert indicators["has_tests"] is True
    assert indicators["has_docs"] is True
    assert indicators["has_ci_cd"] is True

    framework_indicators: dict[str, bool] = {}
    lifecycle_context.check_framework_imports(
        "import fastapi\nfrom django.http import HttpResponse\nimport flask\n",
        framework_indicators,
    )
    assert framework_indicators == {
        "uses_fastapi": True,
        "uses_django": True,
        "uses_flask": True,
    }

    detect_indicators: dict[str, bool] = {}
    lifecycle_context.detect_python_frameworks([tmp_path / "app.py"], detect_indicators)
    assert detect_indicators == {
        "uses_fastapi": True,
        "uses_django": True,
        "uses_flask": True,
    }

    lifecycle_context.add_python_context_indicators(tmp_path, indicators)
    assert indicators["has_python_files"] is True
    assert indicators["uses_fastapi"] is True
    assert indicators["uses_django"] is True
    assert indicators["uses_flask"] is True

    assert project_analysis is not None


@pytest.mark.asyncio
async def test_core_project_analysis_async_entrypoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.core.lifecycle.project_context import analyze_project_context

    monkeypatch.setattr(
        "session_buddy.core.lifecycle.project_context.is_git_repository",
        lambda _: True,
    )

    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
    (tmp_path / "README.md").write_text("readme")
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "app.py").write_text(
        "import fastapi\nfrom django.http import HttpResponse\nimport flask\n",
    )

    result = await analyze_project_context(tmp_path)

    assert result["has_pyproject_toml"] is True
    assert result["has_readme"] is True
    assert result["has_git_repo"] is True
    assert result["has_tests"] is True
    assert result["has_docs"] is True
    assert result["has_python_files"] is True
    assert result["uses_fastapi"] is True
    assert result["uses_django"] is True
    assert result["uses_flask"] is True


def test_detect_python_frameworks_skips_unreadable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.core.lifecycle.project_context import (
        detect_python_frameworks,
    )

    good_file = tmp_path / "good.py"
    good_file.write_text("import fastapi\n")
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("import django\n")

    original_open = Path.open

    def flaky_open(self: Path, *args: object, **kwargs: object):
        if self == bad_file:
            raise PermissionError("denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)

    indicators: dict[str, bool] = {}
    detect_python_frameworks([bad_file, good_file], indicators)

    assert indicators == {"uses_fastapi": True}


@pytest.mark.asyncio
async def test_project_analysis_async_wrapper(
    tmp_path: Path,
) -> None:
    from session_buddy.utils.project_analysis import analyze_project_context

    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
    (tmp_path / "README.md").write_text("readme")
    (tmp_path / "requirements.txt").write_text("pytest\n")
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / ".mcp.json").write_text("{}")
    (tmp_path / "test_example.py").write_text("assert True\n")

    result = await analyze_project_context(tmp_path)

    assert result == {
        "python_project": True,
        "git_repo": False,
        "has_tests": True,
        "has_docs": True,
        "has_requirements": True,
        "has_uv_lock": True,
        "has_mcp_config": True,
    }

    missing = await analyze_project_context(tmp_path / "missing")
    assert missing == {
        "python_project": False,
        "git_repo": False,
        "has_tests": False,
        "has_docs": False,
        "has_requirements": False,
        "has_uv_lock": False,
        "has_mcp_config": False,
    }


@pytest.mark.asyncio
async def test_project_analysis_falls_back_on_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.utils.project_analysis import analyze_project_context

    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")

    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == tmp_path:
            raise OSError("boom")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = await analyze_project_context(tmp_path)

    assert result == {
        "python_project": False,
        "git_repo": False,
        "has_tests": False,
        "has_docs": False,
        "has_requirements": False,
        "has_uv_lock": False,
        "has_mcp_config": False,
    }
