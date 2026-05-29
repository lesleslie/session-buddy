from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_project_context_helpers_and_async_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.core.lifecycle import project_context

    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".github").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "import fastapi\nfrom django.http import HttpResponse\nimport flask\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(project_context, "is_git_repository", lambda _: True)

    assert project_context.check_readme_exists(tmp_path) is True
    assert project_context.check_venv_exists(tmp_path) is True
    assert project_context.check_tests_exist(tmp_path) is True
    assert project_context.check_docs_exist(tmp_path) is True
    assert project_context.check_ci_cd_exists(tmp_path) is True

    indicators = project_context.get_basic_project_indicators(tmp_path)
    assert indicators["has_pyproject_toml"] is True
    assert indicators["has_readme"] is True
    assert indicators["has_git_repo"] is True
    assert indicators["has_venv"] is True
    assert indicators["has_tests"] is True
    assert indicators["has_docs"] is True
    assert indicators["has_ci_cd"] is True

    project_context.check_framework_imports(
        (tmp_path / "app.py").read_text(encoding="utf-8"),
        indicators,
    )
    assert indicators["uses_fastapi"] is True
    assert indicators["uses_django"] is True
    assert indicators["uses_flask"] is True

    async def _run() -> dict[str, bool]:
        return await project_context.analyze_project_context(tmp_path)

    analyzed = asyncio.run(_run())
    assert analyzed["has_python_files"] is True
    assert analyzed["uses_fastapi"] is True
    assert analyzed["uses_django"] is True
    assert analyzed["uses_flask"] is True


def test_session_info_parsing_and_handoff_discovery(
    tmp_path: Path,
) -> None:
    from session_buddy.core.lifecycle import session_info

    handoff_dir = tmp_path / ".crackerjack" / "session" / "handoff"
    handoff_dir.mkdir(parents=True)
    older = handoff_dir / "session_handoff_20240524.md"
    newer = handoff_dir / "session_handoff_20240525.md"
    older.write_text("older", encoding="utf-8")
    newer.write_text(
        "\n".join(
            [
                "# Session Handoff Report - demo",
                "",
                "**Session ended:** 2026-05-25T09:00:00",
                "**Final quality score:** 87",
                "**Working directory:** /tmp/project",
                "",
                "## Recommendations for Next Session",
                "",
                "1. Do the thing",
                "## Context",
            ]
        ),
        encoding="utf-8",
    )

    old_time = datetime(2024, 5, 23, tzinfo=timezone.utc).timestamp()
    new_time = datetime(2024, 5, 24, tzinfo=timezone.utc).timestamp()
    import os

    legacy_root = tmp_path / "legacy-root"
    legacy_root.mkdir()
    legacy_a = legacy_root / "session_handoff_20240523.md"
    legacy_b = legacy_root / "session_handoff_20240524.md"
    legacy_a.write_text("a", encoding="utf-8")
    legacy_b.write_text("b", encoding="utf-8")
    os.utime(legacy_a, (old_time, old_time))
    os.utime(legacy_b, (new_time, new_time))

    assert session_info.find_latest_handoff_file(tmp_path) == newer
    assert session_info.find_latest_handoff_file(tmp_path / "missing") is None

    discovered = session_info.discover_session_files(tmp_path)
    assert discovered == []

    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    legacy_files = [
        legacy_dir / "session_handoff_20240523.md",
        legacy_dir / "session_handoff_20240524.md",
    ]
    for path in legacy_files:
        path.write_text("legacy", encoding="utf-8")
    os.utime(legacy_files[0], (old_time, old_time))
    os.utime(legacy_files[1], (new_time, new_time))

    assert session_info.find_latest_handoff_file(legacy_dir) == legacy_files[1]

    session_file = tmp_path / "session_handoff.md"
    session_file.write_text(newer.read_text(encoding="utf-8"), encoding="utf-8")
    assert session_info.discover_session_files(tmp_path) == [session_file]

    assert session_info.extract_session_metadata(
        [
            "**Session ended:** 2026-05-25T09:00:00",
            "**Final quality score:** 87",
            "**Working directory:** /tmp/project",
        ]
    ) == {
        "ended_at": "2026-05-25T09:00:00",
        "quality_score": "87",
        "working_directory": "/tmp/project",
    }

    info = {}
    session_info.extract_session_recommendations(
        [
            "## Recommendations for Next Session",
            "",
            "1. Do the thing",
            "## End",
        ],
        info,
    )
    assert info["top_recommendation"] == "Do the thing"

    parsed = asyncio.run(session_info.parse_session_file(session_file))
    assert parsed.session_id == ""
    assert parsed.ended_at == "2026-05-25T09:00:00"
    assert parsed.quality_score == "87"
    assert parsed.working_directory == "/tmp/project"
    assert parsed.top_recommendation == "Do the thing"
    assert parsed.is_complete() is True

    assert asyncio.run(session_info.read_previous_session_info(session_file)) == {
        "ended_at": "2026-05-25T09:00:00",
        "quality_score": "87",
        "working_directory": "/tmp/project",
        "top_recommendation": "Do the thing",
    }

    incomplete_file = tmp_path / "incomplete.md"
    incomplete_file.write_text("not enough", encoding="utf-8")
    assert asyncio.run(session_info.read_previous_session_info(incomplete_file)) is None

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Path, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom")))
        assert asyncio.run(session_info.read_file_safely(session_file)) == ""


def test_handoff_build_and_save_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.core.lifecycle import handoff

    summary = {
        "project": "session-buddy",
        "session_end_time": "2026-05-25T09:00:00",
        "final_quality_score": 88,
        "working_directory": "/tmp/project",
        "recommendations": ["first", "second", "third", "fourth", "fifth", "sixth"],
    }
    quality_data = {
        "breakdown": {
            "code_quality": 32.5,
            "project_health": 21.0,
            "dev_velocity": 14.5,
            "security": 9.0,
        }
    }

    assert handoff.build_handoff_header(summary)[0] == (
        "# Session Handoff Report - session-buddy"
    )
    assert handoff.build_quality_section(quality_data) == [
        "## Quality Assessment",
        "",
        "- **Code quality:** 32.5/40",
        "- **Project health:** 21.0/30",
        "- **Dev velocity:** 14.5/20",
        "- **Security:** 9.0/10",
        "",
    ]
    assert handoff.build_recommendations_section(summary["recommendations"]) == [
        "## Recommendations for Next Session",
        "",
        "- first",
        "- second",
        "- third",
        "- fourth",
        "- fifth",
        "",
    ]
    assert handoff.build_recommendations_section([]) == []
    assert handoff.build_static_sections()[0] == "## Context for Next Session"

    generated = asyncio.run(
        handoff.generate_handoff_documentation(summary, quality_data),
    )
    assert "Session Handoff Report - session-buddy" in generated
    assert "## Quality Assessment" in generated
    assert "## Recommendations for Next Session" in generated

    class FixedDatetime:
        @classmethod
        def now(cls):
            return datetime(2026, 5, 25, 9, 15, 0)

    monkeypatch.setattr(handoff, "datetime", FixedDatetime)
    output = handoff.save_handoff_documentation(generated, tmp_path)
    assert output is not None
    assert output.name == "session_handoff_20260525_091500.md"
    assert output.read_text(encoding="utf-8") == generated

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            Path,
            "mkdir",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom")),
        )
        assert handoff.save_handoff_documentation("x", tmp_path) is None
