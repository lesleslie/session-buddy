from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest


def _load_quality_scoring_module():
    package_name = "session_buddy.utils"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = []  # type: ignore[attr-defined]
        sys.modules[package_name] = package

    parser_module = types.ModuleType("session_buddy.utils.quality_score_parser")
    parser_module._extract_quality_scores = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    parser_module._generate_quality_trend_recommendations = (  # type: ignore[attr-defined]
        lambda *args, **kwargs: []
    )
    sys.modules["session_buddy.utils.quality_score_parser"] = parser_module

    crackerjack_module = types.ModuleType("session_buddy.crackerjack_integration")

    async def get_quality_metrics_history(*args, **kwargs):
        return []

    crackerjack_module.get_quality_metrics_history = get_quality_metrics_history  # type: ignore[attr-defined]
    sys.modules["session_buddy.crackerjack_integration"] = crackerjack_module

    module_path = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "utils"
        / "quality_scoring.py"
    )
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.quality_scoring",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qs = _load_quality_scoring_module()


def test_cached_metrics_respects_ttl() -> None:
    cache_key = "cache-key"
    qs._metrics_cache.clear()
    qs._metrics_cache[cache_key] = ({"code_coverage": 55}, qs.datetime.now())

    assert qs._get_cached_metrics(cache_key) == {"code_coverage": 55}

    stale_time = qs.datetime.now() - qs.timedelta(minutes=10)
    qs._metrics_cache[cache_key] = ({"code_coverage": 10}, stale_time)
    assert qs._get_cached_metrics(cache_key) is None


def test_parse_metrics_history_uses_defaults_and_first_values() -> None:
    metrics = qs._parse_metrics_history(
        [
            {"metric_type": "code_coverage", "metric_value": 88},
            {"metric_type": "lint_score", "metric_value": 91},
            {"metric_type": "security_score", "metric_value": 77},
            {"metric_type": "complexity_score", "metric_value": 66},
            {"metric_type": "code_coverage", "metric_value": 11},
        ]
        * 3
    )

    assert metrics["code_coverage"] == 88
    assert metrics["lint_score"] == 91
    assert metrics["security_score"] == 77
    assert metrics["complexity_score"] == 66


def test_tooling_and_maturity_helpers_cover_core_branches(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    assert qs._score_package_management(project) == (0, {})
    (project / "pyproject.toml").write_text("[project]\n")
    assert qs._score_package_management(project) == (
        3,
        {"package_mgmt": "partial (pyproject.toml, no lockfile)"},
    )
    (project / "uv.lock").write_text("# lock\n")
    assert qs._score_package_management(project) == (
        5,
        {"package_mgmt": "modern (pyproject.toml + lockfile)"},
    )

    dependency_only = tmp_path / "dependency_only"
    dependency_only.mkdir()
    lockfile = dependency_only / "requirements.txt"
    lockfile.write_text("a==1\n")
    now = qs.datetime.now().timestamp()
    os.utime(lockfile, (now, now))
    assert qs._score_dependency_management(dependency_only) == (
        5,
        {"dependency_mgmt": "recently updated"},
    )
    old = now - (60 * 60 * 24 * 60)
    os.utime(lockfile, (old, old))
    assert qs._score_dependency_management(dependency_only) == (
        3,
        {"dependency_mgmt": "moderately current"},
    )
    older = now - (60 * 60 * 24 * 120)
    os.utime(lockfile, (older, older))
    assert qs._score_dependency_management(dependency_only) == (
        1,
        {"dependency_mgmt": "outdated (120 days)"},
    )

    unknown_age = tmp_path / "unknown_age"
    unknown_age.mkdir()
    unknown_lock = unknown_age / "requirements.txt"
    unknown_lock.write_text("a==1\n")

    original_exists = Path.exists
    original_stat = Path.stat

    def fake_exists(self: Path, *args, **kwargs):
        if self == unknown_lock:
            return True
        return original_exists(self, *args, **kwargs)

    def fake_stat(self: Path, *args, **kwargs):
        if self == unknown_lock:
            raise OSError("blocked")
        return original_stat(self, *args, **kwargs)

    # Age-unknown fallback is exercised by a stat failure.
    from unittest.mock import patch

    with patch.object(Path, "exists", fake_exists), patch.object(Path, "stat", fake_stat):
        assert qs._score_dependency_management(unknown_age) == (
            2,
            {"dependency_mgmt": "present (age unknown)"},
        )

    test_dir = project / "tests"
    test_dir.mkdir()
    assert qs._evaluate_testing_infra(project) == (0, {"testing": "none"})
    (test_dir / "conftest.py").write_text("# conftest\n")
    for i in range(10):
        (test_dir / f"test_{i}.py").write_text("def test_x(): pass\n")
    assert qs._evaluate_testing_infra(project) == (
        5,
        {"testing": "comprehensive (10 test files)"},
    )

    docs_dir = project / "docs"
    docs_dir.mkdir()
    (project / "README.md").write_text("# readme\n")
    assert qs._evaluate_documentation(project) == (3, {"documentation": "basic (0 docs)"})
    for i in range(4):
        (docs_dir / f"doc_{i}.md").write_text("# doc\n")
    assert qs._evaluate_documentation(project) == (
        3,
        {"documentation": "basic (4 docs)"},
    )
    (docs_dir / "doc_4.md").write_text("# doc\n")
    assert qs._evaluate_documentation(project) == (
        5,
        {"documentation": "comprehensive (5 docs)"},
    )

    readme_only = tmp_path / "readme_only"
    readme_only.mkdir()
    (readme_only / "README.md").write_text("# readme\n")
    assert qs._evaluate_documentation(readme_only) == (
        2,
        {"documentation": "README only"},
    )

    assert qs._evaluate_ci_cd(project) == (0, {"ci_cd": "none"})
    workflows = project / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")
    assert qs._evaluate_ci_cd(project) == (3, {"ci_cd": "github actions (1 workflow)"})
    (workflows / "release.yaml").write_text("name: Release\n")
    assert qs._evaluate_ci_cd(project) == (5, {"ci_cd": "github actions (2 workflows)"})

    gitlab = tmp_path / "gitlab"
    gitlab.mkdir()
    (gitlab / "README.md").write_text("# readme\n")
    (gitlab / ".gitlab-ci.yml").write_text("stages: []\n")
    assert qs._evaluate_ci_cd(gitlab) == (4, {"ci_cd": "gitlab ci"})


def test_git_and_commit_helpers_cover_branching(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".git").mkdir()

    class Result:
        def __init__(self, returncode: int = 0, stdout: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout

    def fake_run(cmd, check=False, cwd=None, capture_output=False, text=False, timeout=None):
        if cmd[:3] == ["git", "log", "--oneline"]:
            return Result(stdout="a\nb\nc\nd\ne")
        if cmd[:2] == ["git", "log"] and "--since=" in cmd[2]:
            return Result(stdout="feat: one #1\nfix: two\nchore: three #3")
        if cmd[:2] == ["git", "branch"]:
            return Result(stdout="  main\n  feature/x\n  feature/y\n  feat/z")
        return Result(stdout="")

    monkeypatch.setattr(qs.subprocess, "run", fake_run)

    assert qs._collect_recent_commits(project) == [
        "feat: one #1",
        "fix: two",
        "chore: three #3",
    ]
    assert qs._score_commit_frequency([]) == (0, {"frequency": "no recent commits"})
    assert qs._score_commit_frequency(["a"] * 10) == (4, {"frequency": "regular (10 commits/month)"})
    assert qs._score_commit_quality([]) == (0, {"quality": "no data"})
    assert qs._score_commit_quality(["feat: a", "fix: b", "docs: c"]) == (
        5,
        {"quality": "excellent (3/3 conventional)"},
    )
    assert qs._score_commit_quality(["feat: a", "bad", "worse", "nope"]) == (
        1,
        {"quality": "basic (1/4 conventional)"},
    )

    activity = qs._analyze_git_activity(project)
    assert activity["score"] == 6
    assert "frequency" in activity["details"]
    patterns = qs._analyze_dev_patterns(project)
    assert patterns["score"] == 5
    assert "issue_tracking" in patterns["details"]
    assert "branch_strategy" in patterns["details"]


@pytest.mark.asyncio
async def test_security_helpers_and_trust_recommendations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project = tmp_path / "secure"
    project.mkdir()
    (project / ".gitignore").write_text("*.pyc\n")
    (project / "secrets.py").write_text("password = 'abc123'\n")
    (project / "pyrightconfig.json").write_text("{}")

    monkeypatch.setattr(
        qs,
        "_get_crackerjack_metrics",
        AsyncMock(return_value={"security_score": 80}),
    )

    hygiene = qs._check_security_hygiene(project)
    assert hygiene["score"] <= 3
    assert hygiene["details"].get("env_ignored") == "no (-.5 pts)"
    assert "hardcoded_secrets" in hygiene["details"]

    security = await qs._run_security_checks(project)
    assert round(security["score"], 2) == 4.0
    assert security["details"]["source"] == "crackerjack"

    assert await qs._get_type_coverage(project, {"type_coverage": 88.0}) == 88.0
    assert await qs._get_type_coverage(project, {}) == 70.0
    assert await qs._get_type_coverage(tmp_path / "plain", {}) == 30.0

    trust = qs._calculate_trust_score(permissions_count=5, session_available=False, tool_count=11)
    assert trust.total == 40 + 5 + 30
    assert trust.details["permissions_count"] == 5

    code_quality = qs.CodeQualityScore(
        test_coverage=5.0,
        lint_score=4.0,
        type_coverage=3.0,
        complexity_score=2.0,
        total=14.0,
        details={"coverage_pct": 33.3},
    )
    project_health = qs.ProjectHealthScore(tooling_score=5.0, maturity_score=5.0, total=10.0, details={})
    dev_velocity = qs.DevVelocityScore(git_activity=3.0, dev_patterns=2.0, total=5.0, details={})
    security_score = qs.SecurityScore(security_tools=3.0, security_hygiene=2.0, total=5.0, details={})
    recs = qs._generate_recommendations_v2(code_quality, project_health, dev_velocity, security_score, 34.0)
    assert len(recs) >= 5
    assert any("Critical" in rec or "attention" in rec for rec in recs)


@pytest.mark.asyncio
async def test_calculate_quality_score_v2_and_metrics_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qs._metrics_cache.clear()

    async def fake_metrics_history(*args, **kwargs):
        return [
            {"metric_type": "code_coverage", "metric_value": 64},
            {"metric_type": "lint_score", "metric_value": 80},
            {"metric_type": "security_score", "metric_value": 70},
            {"metric_type": "complexity_score", "metric_value": 90},
        ]

    monkeypatch.setattr(qs, "CRACKERJACK_AVAILABLE", True)
    monkeypatch.setattr(qs, "get_quality_metrics_history", fake_metrics_history)
    monkeypatch.setattr(qs, "_get_type_coverage", AsyncMock(return_value=70.0))

    result = await qs.calculate_quality_score_v2(
        tmp_path,
        permissions_count=2,
        session_available=True,
        tool_count=3,
    )

    assert result.version == "2.0"
    assert result.total_score > 0
    assert result.trust_score.total == 59

    qs._metrics_cache.clear()
    monkeypatch.setattr(qs, "CRACKERJACK_AVAILABLE", False)
    monkeypatch.setattr(qs, "_read_coverage_json", Mock(return_value=55.0))
    monkeypatch.setattr(qs, "_read_coverage_dotfile", Mock(return_value=0))
    metrics = await qs._get_crackerjack_metrics(tmp_path)
    assert metrics["code_coverage"] == 55.0
    assert await qs._get_crackerjack_metrics(tmp_path) == metrics
