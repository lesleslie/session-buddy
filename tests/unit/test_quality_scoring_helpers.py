from __future__ import annotations

import json
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
        package.__path__ = [
            str(Path(__file__).resolve().parents[2] / "session_buddy" / "utils"),
        ]  # type: ignore[attr-defined]
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


def test_coverage_readers_and_fallback_metrics(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(json.dumps({"totals": {"percent_covered": 88.5}}))
    assert qs._read_coverage_json(tmp_path) == 88.5

    coverage_json.write_text("not-json")
    assert qs._read_coverage_json(tmp_path) == 0

    coverage_file = tmp_path / ".coverage"
    coverage_file.write_text("sqlite placeholder")

    class FakeCoverage:
        def __init__(self, data_file: str) -> None:
            self.data_file = data_file

        def load(self) -> None:
            return None

        def report(self, file, skip_empty: bool = True) -> float:
            file.write("coverage report")
            return 73.25

    import coverage as coverage_module

    original_coverage = coverage_module.Coverage
    coverage_module.Coverage = FakeCoverage  # type: ignore[assignment]
    try:
        assert qs._read_coverage_dotfile(tmp_path) == 73.25
    finally:
        coverage_module.Coverage = original_coverage  # type: ignore[assignment]

    assert qs._create_fallback_metrics(42.0) == {
        "code_coverage": 42.0,
        "lint_score": 100,
        "security_score": 100,
        "complexity_score": 100,
    }


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

    lock_only = tmp_path / "lock_only"
    lock_only.mkdir()
    (lock_only / "requirements.txt").write_text("a==1\n")
    assert qs._score_package_management(lock_only) == (
        2,
        {"package_mgmt": "basic (lockfile only)"},
    )

    uv_only = tmp_path / "uv_only"
    uv_only.mkdir()
    (uv_only / "uv.lock").write_text("# lock\n")
    assert qs._score_dependency_management(uv_only) == (
        5,
        {"dependency_mgmt": "recently updated"},
    )

    git_only = tmp_path / "git_only"
    git_only.mkdir()
    (git_only / ".git").mkdir()
    assert qs._score_version_control(git_only) == (
        3,
        {"version_control": "git repo (limited history)"},
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

    none_dependency = tmp_path / "none_dependency"
    none_dependency.mkdir()
    assert qs._score_dependency_management(none_dependency) == (0, {"dependency_mgmt": "none"})

    test_dir = project / "tests"
    test_dir.mkdir()
    assert qs._evaluate_testing_infra(project) == (0, {"testing": "none"})
    (test_dir / "conftest.py").write_text("# conftest\n")
    for i in range(4):
        (test_dir / f"test_basic_{i}.py").write_text("def test_x(): pass\n")
    assert qs._evaluate_testing_infra(project) == (
        1,
        {"testing": "basic (4 test files)"},
    )
    (test_dir / "test_4.py").write_text("def test_x(): pass\n")
    assert qs._evaluate_testing_infra(project) == (
        3,
        {"testing": "moderate (5 test files)"},
    )
    (test_dir / "conftest.py").write_text("# conftest\n")
    for i in range(10):
        (test_dir / f"test_{i}.py").write_text("def test_x(): pass\n")
    assert qs._evaluate_testing_infra(project) == (
        5,
        {"testing": "comprehensive (14 test files)"},
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

    feature_only = tmp_path / "feature_only"
    feature_only.mkdir()
    workflows = feature_only / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")
    assert qs._evaluate_ci_cd(feature_only) == (3, {"ci_cd": "github actions (1 workflow)"})

    empty_workflows = tmp_path / "empty_workflows"
    empty_workflows.mkdir()
    (empty_workflows / ".github" / "workflows").mkdir(parents=True)
    assert qs._evaluate_ci_cd(empty_workflows) == (0, {"ci_cd": "none"})


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

    plain_project = tmp_path / "plain"
    plain_project.mkdir()
    assert qs._analyze_git_activity(plain_project) == {
        "score": 0,
        "details": {"activity": "no git repository"},
    }

    def failing_collect(_project_dir: Path):
        raise RuntimeError("collect failed")

    monkeypatch.setattr(qs, "_collect_recent_commits", failing_collect)
    assert qs._analyze_git_activity(project) == {
        "score": 0,
        "details": {"error": "git analysis failed: collect failed"},
    }

    def no_data_run(cmd, **kwargs):
        if cmd[:2] == ["git", "log"] and "--oneline" in cmd:
            return Result(stdout="")
        if cmd[:2] == ["git", "branch"]:
            return Result(stdout="")
        return Result(stdout="")

    monkeypatch.setattr(qs.subprocess, "run", no_data_run)
    assert qs._score_issue_tracking(project) == (0, {"issue_tracking": "no data"})
    assert qs._score_branch_strategy(project) == (0, {"branch_strategy": "no data"})

    gitless = tmp_path / "gitless"
    gitless.mkdir()
    assert qs._analyze_dev_patterns(gitless) == {
        "score": 0,
        "details": {"patterns": "no git repository"},
    }


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

    clean_project = tmp_path / "clean"
    clean_project.mkdir()
    (clean_project / ".gitignore").write_text(".env\n")
    assert qs._check_security_hygiene(clean_project)["details"].get("env_ignored") == "yes"

    no_gitignore = tmp_path / "no_gitignore"
    no_gitignore.mkdir()
    assert qs._check_security_hygiene(no_gitignore)["details"].get("gitignore") == "missing"

    no_secret_project = tmp_path / "no_secret_project"
    no_secret_project.mkdir()
    (no_secret_project / ".gitignore").write_text(".env\n")
    (no_secret_project / "module.py").write_text("value = 1\nprint(value)\n")
    no_secret_hygiene = qs._check_security_hygiene(no_secret_project)
    assert "hardcoded_secrets" not in no_secret_hygiene["details"]

    security = await qs._run_security_checks(project)
    assert round(security["score"], 2) == 4.0
    assert security["details"]["source"] == "crackerjack"

    assert await qs._get_type_coverage(project, {"type_coverage": 88.0}) == 88.0
    assert await qs._get_type_coverage(project, {}) == 70.0
    assert await qs._get_type_coverage(tmp_path / "plain", {}) == 30.0

    trust = qs._calculate_trust_score(permissions_count=5, session_available=False, tool_count=11)
    assert trust.total == 40 + 5 + 30
    assert trust.details["permissions_count"] == 5

    assert qs._check_security_hygiene(tmp_path / "missing")["details"].get("gitignore") == "missing"

    monkeypatch.setattr(qs, "_get_crackerjack_metrics", AsyncMock(return_value={}))
    fallback_security = await qs._run_security_checks(tmp_path / "fallback")
    assert fallback_security["details"]["source"] == "fallback"
    assert fallback_security["details"]["security_raw"] == 100

    typed = tmp_path / "typed"
    typed.mkdir()
    (typed / "pyrightconfig.json").write_text("{}")
    assert await qs._get_type_coverage(typed, {}) == 70.0

    plain = tmp_path / "plain_no_types"
    plain.mkdir()
    assert await qs._get_type_coverage(plain, {}) == 30.0

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

    excellent = qs._generate_recommendations_v2(
        qs.CodeQualityScore(
            test_coverage=13.0,
            lint_score=9.0,
            type_coverage=8.0,
            complexity_score=4.0,
            total=34.0,
            details={"coverage_pct": 90.0},
        ),
        qs.ProjectHealthScore(tooling_score=11.0, maturity_score=11.0, total=22.0, details={}),
        qs.DevVelocityScore(git_activity=6.0, dev_patterns=6.0, total=12.0, details={}),
        qs.SecurityScore(security_tools=5.0, security_hygiene=5.0, total=10.0, details={}),
        92.0,
    )
    assert excellent[0].startswith("⭐ Excellent")

    good = qs._generate_recommendations_v2(
        qs.CodeQualityScore(
            test_coverage=13.0,
            lint_score=9.0,
            type_coverage=8.0,
            complexity_score=4.0,
            total=34.0,
            details={"coverage_pct": 90.0},
        ),
        qs.ProjectHealthScore(tooling_score=11.0, maturity_score=11.0, total=22.0, details={}),
        qs.DevVelocityScore(git_activity=6.0, dev_patterns=6.0, total=12.0, details={}),
        qs.SecurityScore(security_tools=5.0, security_hygiene=5.0, total=10.0, details={}),
        80.0,
    )
    assert good[0].startswith("✅ Good quality")

    moderate = qs._generate_recommendations_v2(
        qs.CodeQualityScore(
            test_coverage=13.0,
            lint_score=9.0,
            type_coverage=8.0,
            complexity_score=4.0,
            total=34.0,
            details={"coverage_pct": 90.0},
        ),
        qs.ProjectHealthScore(tooling_score=11.0, maturity_score=11.0, total=22.0, details={}),
        qs.DevVelocityScore(git_activity=6.0, dev_patterns=6.0, total=12.0, details={}),
        qs.SecurityScore(security_tools=5.0, security_hygiene=5.0, total=10.0, details={}),
        60.0,
    )
    assert moderate[0].startswith("⚠️ Moderate quality")


@pytest.mark.asyncio
async def test_coverage_readers_and_metric_fallback_edges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert qs._read_coverage_json(tmp_path) == 0
    assert qs._read_coverage_dotfile(tmp_path) == 0

    coverage_file = tmp_path / ".coverage"
    coverage_file.write_text("sqlite placeholder")

    class BrokenCoverage:
        def __init__(self, data_file: str) -> None:
            self.data_file = data_file

        def load(self) -> None:
            return None

        def report(self, file, skip_empty: bool = True) -> float:
            raise RuntimeError("broken coverage")

    import coverage as coverage_module

    original_coverage = coverage_module.Coverage
    coverage_module.Coverage = BrokenCoverage  # type: ignore[assignment]
    try:
        assert qs._read_coverage_dotfile(tmp_path) == 0
    finally:
        coverage_module.Coverage = original_coverage  # type: ignore[assignment]

    qs._metrics_cache.clear()
    monkeypatch.setattr(qs, "CRACKERJACK_AVAILABLE", True)

    async def partial_history(*args, **kwargs):
        return [{"metric_type": "lint_score", "metric_value": 81}]

    monkeypatch.setattr(qs, "get_quality_metrics_history", partial_history)
    monkeypatch.setattr(qs, "_read_coverage_json", Mock(return_value=0))
    monkeypatch.setattr(qs, "_read_coverage_dotfile", Mock(return_value=0))

    metrics = await qs._get_crackerjack_metrics(str(tmp_path))
    assert metrics["lint_score"] == 81
    assert "code_coverage" not in metrics
    assert metrics["security_score"] == 100


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


def test_git_commit_and_version_control_fallback_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project = tmp_path / "git"
    project.mkdir()
    (project / ".git").mkdir()

    class Result:
        def __init__(self, returncode: int = 0, stdout: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout

    def run_for_commits(cmd, check=False, cwd=None, capture_output=False, text=False, timeout=None):
        if cmd[:3] == ["git", "log", "--oneline"]:
            return Result(stdout="feat: a\nfix: b\nchore: c\ndocs: d\ntest: e\nfeat: f\nfix: g\n")
        if cmd[:2] == ["git", "log"] and "--since=" in cmd[2]:
            return Result(returncode=1, stdout="")
        if cmd[:2] == ["git", "branch"]:
            return Result(stdout="  main\n  feature/a\n  feature/b\n")
        return Result(stdout="")

    monkeypatch.setattr(qs.subprocess, "run", run_for_commits)

    assert qs._score_commit_frequency(["a"] * 20) == (5, {"frequency": "active (20 commits/month)"})
    assert qs._score_commit_frequency(["a"] * 5) == (2, {"frequency": "occasional (5 commits/month)"})
    assert qs._score_commit_frequency(["a"]) == (1, {"frequency": "sparse (1 commits/month)"})

    assert qs._score_commit_quality(["feat: a", "fix: b", "bad", "bad"]) == (
        3,
        {"quality": "good (2/4 conventional)"},
    )

    assert qs._collect_recent_commits(project) == []
    assert qs._analyze_git_activity(project) == {
        "score": 0,
        "details": {"frequency": "no recent commits", "quality": "no data"},
    }

    def run_issue_tracking_basic(cmd, check=False, cwd=None, capture_output=False, text=False, timeout=None):
        if cmd[:2] == ["git", "log"]:
            return Result(stdout="feat: a #1\nfix: b\nchore: c\nrefactor: d\nstyle: e\n")
        if cmd[:2] == ["git", "branch"]:
            return Result(stdout="  main\n  feature/a\n  feature/b\n")
        return Result(stdout="")

    monkeypatch.setattr(qs.subprocess, "run", run_issue_tracking_basic)
    assert qs._score_issue_tracking(project) == (1, {"issue_tracking": "basic (1/5 refs)"})
    assert qs._score_branch_strategy(project) == (3, {"branch_strategy": "some feature branches (2)"})

    def run_issue_tracking_good(cmd, check=False, cwd=None, capture_output=False, text=False, timeout=None):
        if cmd[:2] == ["git", "log"]:
            return Result(stdout="feat: a #1\nfix: b #2\nchore: c #3\nrefactor: d\nstyle: e\n")
        if cmd[:2] == ["git", "branch"]:
            return Result(stdout="  main\n")
        return Result(stdout="")

    monkeypatch.setattr(qs.subprocess, "run", run_issue_tracking_good)
    assert qs._score_issue_tracking(project) == (5, {"issue_tracking": "excellent (3/5 refs)"})

    def run_issue_tracking_good_ratio(cmd, check=False, cwd=None, capture_output=False, text=False, timeout=None):
        if cmd[:2] == ["git", "log"]:
            return Result(stdout="feat: a #1\nfix: b #2\nchore: c\nrefactor: d\nstyle: e\n")
        if cmd[:2] == ["git", "branch"]:
            return Result(stdout="  main\n")
        return Result(stdout="")

    monkeypatch.setattr(qs.subprocess, "run", run_issue_tracking_good_ratio)
    assert qs._score_issue_tracking(project) == (3, {"issue_tracking": "good (2/5 refs)"})
    assert qs._score_branch_strategy(project) == (1, {"branch_strategy": "main-only development"})

    def run_active_history(cmd, check=False, cwd=None, capture_output=False, text=False, timeout=None):
        if cmd[:3] == ["git", "log", "--oneline"]:
            return Result(stdout="feat: a\nfix: b\nchore: c\ndocs: d\ntest: e")
        if cmd[:2] == ["git", "branch"]:
            return Result(stdout="  main\n")
        return Result(stdout="")

    monkeypatch.setattr(qs.subprocess, "run", run_active_history)
    assert qs._score_version_control(project) == (5, {"version_control": "active git repository"})

    def run_raise(*args, **kwargs):
        raise OSError("blocked")

    monkeypatch.setattr(qs.subprocess, "run", run_raise)
    assert qs._score_version_control(project) == (
        2,
        {"version_control": "git repo (couldn't verify history)"},
    )
    assert qs._score_issue_tracking(project) == (0, {"issue_tracking": "analysis failed: blocked"})
    assert qs._score_branch_strategy(project) == (0, {"branch_strategy": "analysis failed: blocked"})


@pytest.mark.asyncio
async def test_get_crackerjack_metrics_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qs._metrics_cache.clear()
    monkeypatch.setattr(qs, "CRACKERJACK_AVAILABLE", False)
    monkeypatch.setattr(qs, "_read_coverage_json", Mock(return_value=0))
    monkeypatch.setattr(qs, "_read_coverage_dotfile", Mock(return_value=61.0))

    metrics = await qs._get_crackerjack_metrics(tmp_path)

    assert metrics == {
        "code_coverage": 61.0,
        "lint_score": 100,
        "security_score": 100,
        "complexity_score": 100,
    }
    assert await qs._get_crackerjack_metrics(tmp_path) == metrics


@pytest.mark.asyncio
async def test_get_crackerjack_metrics_no_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    qs._metrics_cache.clear()
    monkeypatch.setattr(qs, "CRACKERJACK_AVAILABLE", False)
    monkeypatch.setattr(qs, "_read_coverage_json", Mock(return_value=0))
    monkeypatch.setattr(qs, "_read_coverage_dotfile", Mock(return_value=0))

    assert await qs._get_crackerjack_metrics(tmp_path) == {}


@pytest.mark.asyncio
async def test_crackerjack_metrics_fallback_and_recommendation_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qs._metrics_cache.clear()
    monkeypatch.setattr(qs, "CRACKERJACK_AVAILABLE", True)

    async def empty_history(*args, **kwargs):
        return []

    monkeypatch.setattr(qs, "get_quality_metrics_history", empty_history)
    monkeypatch.setattr(qs, "_read_coverage_json", Mock(return_value=0))
    monkeypatch.setattr(qs, "_read_coverage_dotfile", Mock(return_value=67.0))

    metrics = await qs._get_crackerjack_metrics(tmp_path)
    assert metrics == {
        "code_coverage": 67.0,
        "lint_score": 100,
        "security_score": 100,
        "complexity_score": 100,
    }

    qs._metrics_cache.clear()

    async def coverage_missing_history(*args, **kwargs):
        return [{"metric_type": "lint_score", "metric_value": 81}]

    monkeypatch.setattr(qs, "get_quality_metrics_history", coverage_missing_history)
    monkeypatch.setattr(qs, "_read_coverage_json", Mock(return_value=71.0))
    monkeypatch.setattr(qs, "_read_coverage_dotfile", Mock(return_value=0))

    metrics = await qs._get_crackerjack_metrics(tmp_path)
    assert metrics["code_coverage"] == 71.0
    assert metrics["lint_score"] == 81

    code_quality = qs.CodeQualityScore(
        test_coverage=11.0,
        lint_score=9.0,
        type_coverage=8.0,
        complexity_score=4.0,
        total=32.0,
        details={"coverage_pct": 71.0},
    )
    project_health = qs.ProjectHealthScore(tooling_score=11.0, maturity_score=11.0, total=22.0, details={})
    dev_velocity = qs.DevVelocityScore(git_activity=6.0, dev_patterns=6.0, total=12.0, details={})
    security_score = qs.SecurityScore(security_tools=5.0, security_hygiene=5.0, total=10.0, details={})
    recs = qs._generate_recommendations_v2(code_quality, project_health, dev_velocity, security_score, 80.0)
    assert recs[0].startswith("✅ Good quality")
    assert any("Add more tests" in rec for rec in recs)

    qs._metrics_cache.clear()
    monkeypatch.setattr(qs, "get_quality_metrics_history", empty_history)
    monkeypatch.setattr(qs, "_read_coverage_json", Mock(return_value=0))
    monkeypatch.setattr(qs, "_read_coverage_dotfile", Mock(return_value=0))
    assert await qs._get_crackerjack_metrics(tmp_path) == {}
