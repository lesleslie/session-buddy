from __future__ import annotations

import asyncio
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_QUALITY_SCORING_PATH = (
    Path(__file__).resolve().parents[2] / "session_buddy" / "core" / "quality_scoring.py"
)
_QUALITY_SCORING_SPEC = spec_from_file_location(
    "session_buddy.core.quality_scoring",
    _QUALITY_SCORING_PATH,
)
assert _QUALITY_SCORING_SPEC is not None and _QUALITY_SCORING_SPEC.loader is not None
_quality_scoring = module_from_spec(_QUALITY_SCORING_SPEC)
sys.modules[_QUALITY_SCORING_SPEC.name] = _quality_scoring
_QUALITY_SCORING_SPEC.loader.exec_module(_quality_scoring)

DefaultQualityScorer = _quality_scoring.DefaultQualityScorer
get_quality_scorer = _quality_scoring.get_quality_scorer
set_quality_scorer = _quality_scoring.set_quality_scorer

# Load the utils quality_scoring module so we can target
# ``_parse_metrics_history`` / ``_calculate_code_quality`` /
# ``_run_security_checks`` directly. The module is the implementation
# surface for N2 in the quality-scoring field audit spec.
_QUALITY_SCORING_UTILS_PATH = (
    Path(__file__).resolve().parents[2]
    / "session_buddy"
    / "utils"
    / "quality_scoring.py"
)
_QUALITY_SCORING_UTILS_SPEC = spec_from_file_location(
    "session_buddy.utils.quality_scoring",
    _QUALITY_SCORING_UTILS_PATH,
)
assert (
    _QUALITY_SCORING_UTILS_SPEC is not None
    and _QUALITY_SCORING_UTILS_SPEC.loader is not None
)
_quality_scoring_utils = module_from_spec(_QUALITY_SCORING_UTILS_SPEC)
sys.modules[_QUALITY_SCORING_UTILS_SPEC.name] = _quality_scoring_utils
_QUALITY_SCORING_UTILS_SPEC.loader.exec_module(_quality_scoring_utils)

_parse_metrics_history = _quality_scoring_utils._parse_metrics_history
_calculate_code_quality = _quality_scoring_utils._calculate_code_quality


def test_default_quality_scorer_uses_cwd_when_project_dir_missing(monkeypatch) -> None:
    scorer = DefaultQualityScorer()
    cwd = Path("/tmp/session-buddy-test")
    monkeypatch.setattr(_quality_scoring.Path, "cwd", lambda: cwd)

    result = asyncio.run(scorer.calculate_quality_score())

    assert result["total_score"] == 75
    assert result["overall"] == 75
    assert result["metrics"]["quality"]["score"] == 75


def test_default_quality_scorer_accepts_explicit_project_dir(tmp_path) -> None:
    scorer = DefaultQualityScorer()

    result = asyncio.run(scorer.calculate_quality_score(tmp_path))

    assert result["total_score"] == 75
    assert result["metrics"]["coverage"]["coverage_pct"] == 0
    assert result["recommendations"] == []


def test_default_quality_scorer_permissions_score() -> None:
    scorer = DefaultQualityScorer()

    assert scorer.get_permissions_score() == 10


def test_get_quality_scorer_singleton_and_setter(monkeypatch) -> None:
    monkeypatch.setattr(_quality_scoring, "_default_scorer", None, raising=False)

    first = get_quality_scorer()
    second = get_quality_scorer()

    assert first is second
    assert isinstance(first, DefaultQualityScorer)

    custom = DefaultQualityScorer()
    set_quality_scorer(custom)

    assert get_quality_scorer() is custom


def test_quality_scorer_abstract_base_methods_are_noops() -> None:
    class SuperCallingScorer(_quality_scoring.QualityScorer):
        async def calculate_quality_score(self, project_dir=None):
            return await super().calculate_quality_score(project_dir)

        def get_permissions_score(self) -> int:
            return super().get_permissions_score()

    scorer = SuperCallingScorer()

    assert asyncio.run(scorer.calculate_quality_score()) is None
    assert scorer.get_permissions_score() is None


def test_parse_metrics_history_defaults_to_none_for_missing_metrics() -> None:
    """Missing metric history entries must surface as None, not 100."""
    history = [
        {
            "metric_type": "code_coverage",
            "metric_value": 80.0,
            "timestamp": "2026-07-27T00:00:00Z",
        },
    ]
    metrics = _parse_metrics_history(history)
    assert metrics["code_coverage"] == 80.0
    assert metrics["lint_score"] is None
    assert metrics["security_score"] is None
    assert metrics["complexity_score"] is None


def test_calculate_code_quality_missing_lint_scores_zero(monkeypatch, tmp_path) -> None:
    """When lint_score is None, code quality awards zero lint points and flags missing."""
    metrics = {
        "code_coverage": 0,
        "lint_score": None,
        "complexity_score": None,
    }

    async def fake_get_crackerjack_metrics(_p):
        return metrics

    monkeypatch.setattr(
        _quality_scoring_utils,
        "_get_crackerjack_metrics",
        fake_get_crackerjack_metrics,
    )
    score = asyncio.run(_calculate_code_quality(tmp_path))
    assert score.lint_score == 0.0
    assert score.details["lint_missing"] is True


# ---------------------------------------------------------------------------
# Coverage tests for session_buddy.utils.quality_scoring
# ---------------------------------------------------------------------------
#
# The historical module ``session_buddy.utils.quality_utils`` was renamed to
# ``quality_utils_v2`` and the implementation was moved into
# ``session_buddy.utils.quality_scoring``. This block targets the full
# scoring surface: dataclasses, helpers, the four-component aggregator,
# coverage/CLI/DB fallback tiers, and the recommendation generator.

_calculate_project_health = _quality_scoring_utils._calculate_project_health
_calculate_dev_velocity = _quality_scoring_utils._calculate_dev_velocity
_calculate_security = _quality_scoring_utils._calculate_security
_calculate_trust_score = _quality_scoring_utils._calculate_trust_score
_calculate_code_quality = _quality_scoring_utils._calculate_code_quality
_score_package_management = _quality_scoring_utils._score_package_management
_score_version_control = _quality_scoring_utils._score_version_control
_score_dependency_management = _quality_scoring_utils._score_dependency_management
_calculate_tooling_score = _quality_scoring_utils._calculate_tooling_score
_calculate_maturity_score = _quality_scoring_utils._calculate_maturity_score
_evaluate_testing_infra = _quality_scoring_utils._evaluate_testing_infra
_evaluate_documentation = _quality_scoring_utils._evaluate_documentation
_evaluate_ci_cd = _quality_scoring_utils._evaluate_ci_cd
_analyze_git_activity = _quality_scoring_utils._analyze_git_activity
_collect_recent_commits = _quality_scoring_utils._collect_recent_commits
_score_commit_frequency = _quality_scoring_utils._score_commit_frequency
_score_commit_quality = _quality_scoring_utils._score_commit_quality
_analyze_dev_patterns = _quality_scoring_utils._analyze_dev_patterns
_score_issue_tracking = _quality_scoring_utils._score_issue_tracking
_score_branch_strategy = _quality_scoring_utils._score_branch_strategy
_run_security_checks = _quality_scoring_utils._run_security_checks
_check_security_hygiene = _quality_scoring_utils._check_security_hygiene
_get_cached_metrics = _quality_scoring_utils._get_cached_metrics
_read_coverage_json = _quality_scoring_utils._read_coverage_json
_read_coverage_dotfile = _quality_scoring_utils._read_coverage_dotfile
_create_fallback_metrics = _quality_scoring_utils._create_fallback_metrics
_get_crackerjack_metrics = _quality_scoring_utils._get_crackerjack_metrics
_get_type_coverage = _quality_scoring_utils._get_type_coverage
_generate_recommendations_v2 = _quality_scoring_utils._generate_recommendations_v2
CodeQualityScore = _quality_scoring_utils.CodeQualityScore
ProjectHealthScore = _quality_scoring_utils.ProjectHealthScore
DevVelocityScore = _quality_scoring_utils.DevVelocityScore
SecurityScore = _quality_scoring_utils.SecurityScore
TrustScore = _quality_scoring_utils.TrustScore
QualityScoreV2 = _quality_scoring_utils.QualityScoreV2
calculate_quality_score_v2 = _quality_scoring_utils.calculate_quality_score_v2


# ---------------------------------------------------------------------------
# Dataclass construction (trivial but pins the field shape)
# ---------------------------------------------------------------------------


def test_dataclasses_instantiate_with_all_fields() -> None:
    code = CodeQualityScore(
        test_coverage=1.0,
        lint_score=2.0,
        type_coverage=3.0,
        complexity_score=4.0,
        total=10.0,
        details={"k": "v"},
    )
    assert code.test_coverage == 1.0
    assert code.details == {"k": "v"}

    health = ProjectHealthScore(
        tooling_score=5.0,
        maturity_score=6.0,
        total=11.0,
        details={},
    )
    assert health.total == 11.0

    velocity = DevVelocityScore(
        git_activity=2.0,
        dev_patterns=3.0,
        total=5.0,
        details={"a": 1},
    )
    assert velocity.git_activity == 2.0

    security = SecurityScore(
        security_tools=1.0,
        security_hygiene=2.0,
        total=3.0,
        details={},
    )
    assert security.total == 3.0

    trust = TrustScore(
        trusted_operations=10.0,
        session_availability=20.0,
        tool_ecosystem=30.0,
        total=60.0,
        details={"x": True},
    )
    assert trust.total == 60.0

    score = QualityScoreV2(
        total_score=70,
        version="2.0",
        code_quality=code,
        project_health=health,
        dev_velocity=velocity,
        security=security,
        trust_score=trust,
        recommendations=["r1"],
        timestamp="2026-09-04T00:00:00",
    )
    assert score.version == "2.0"
    assert score.recommendations == ["r1"]
    assert score.code_quality is code


# ---------------------------------------------------------------------------
# _score_package_management — 4 branches (modern/partial/basic/none)
# ---------------------------------------------------------------------------


def test_score_package_management_modern(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "uv.lock").write_text("# lock\n")
    score, details = _score_package_management(tmp_path)
    assert score == 5
    assert details["package_mgmt"].startswith("modern")


def test_score_package_management_partial_no_lockfile(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    score, details = _score_package_management(tmp_path)
    assert score == 3
    assert details["package_mgmt"].startswith("partial")


def test_score_package_management_basic_requirements_only(tmp_path) -> None:
    (tmp_path / "requirements.txt").write_text("requests\n")
    score, details = _score_package_management(tmp_path)
    assert score == 2
    assert details["package_mgmt"].startswith("basic")


def test_score_package_management_empty(tmp_path) -> None:
    score, details = _score_package_management(tmp_path)
    assert score == 0
    assert details == {}


# ---------------------------------------------------------------------------
# _score_version_control — 4 branches
# ---------------------------------------------------------------------------


def test_score_version_control_no_git_dir(tmp_path) -> None:
    score, details = _score_version_control(tmp_path)
    assert score == 0
    assert details["version_control"] == "none"


def test_score_version_control_git_no_history(tmp_path) -> None:
    # ``git`` binary may not be on the test PATH; the function catches
    # that and falls through to the "couldn't verify" branch.
    (tmp_path / ".git").mkdir()
    score, details = _score_version_control(tmp_path)
    assert score in (2, 3)
    assert "git repo" in details["version_control"]


def test_score_version_control_active_repo(tmp_path) -> None:
    """A repo with >=5 commits scores the maximum 5 points."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=tmp_path,
        check=True,
    )
    for i in range(6):
        (tmp_path / f"file_{i}.txt").write_text(f"{i}\n")
        subprocess.run(["git", "add", f"file_{i}.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", f"c{i}"],
            cwd=tmp_path,
            check=True,
        )
    score, details = _score_version_control(tmp_path)
    assert score == 5
    assert details["version_control"] == "active git repository"


# ---------------------------------------------------------------------------
# _score_dependency_management — 4 branches + unknown-age fallback
# ---------------------------------------------------------------------------


def test_score_dependency_management_no_lockfile(tmp_path) -> None:
    score, details = _score_dependency_management(tmp_path)
    assert score == 0
    assert details["dependency_mgmt"] == "none"


def test_score_dependency_management_recent(tmp_path) -> None:
    """uv.lock <30 days old scores 5."""
    (tmp_path / "uv.lock").write_text("# lock\n")
    score, details = _score_dependency_management(tmp_path)
    assert score == 5
    assert details["dependency_mgmt"] == "recently updated"


def test_score_dependency_management_present_unknown_age(tmp_path, monkeypatch) -> None:
    """When stat() raises the function falls through to the 'age unknown' branch."""
    import session_buddy.utils.quality_scoring as qs

    monkeypatch.setattr(qs.Path, "stat", lambda self: (_ for _ in ()).throw(OSError))


def test_score_dependency_management_outdated_lockfile(tmp_path, monkeypatch) -> None:
    """Lockfile >90 days old scores 1 with descriptive detail."""
    import time as _time

    from datetime import UTC, datetime, timedelta

    import session_buddy.utils.quality_scoring as qs

    (tmp_path / "uv.lock").write_text("# lock\n")

    # Force the path to report a stale mtime by patching stat() to return
    # a 100-day-old timestamp.
    stale = (datetime.now(tz=UTC) - timedelta(days=100)).timestamp()

    real_stat = qs.Path.stat

    def fake_stat(self, *args, **kwargs):
        if self.name == "uv.lock":
            result = real_stat(self, *args, **kwargs)
            # Replace st_mtime with the stale timestamp.
            class _StatProxy:
                def __getattr__(self, attr):
                    if attr == "st_mtime":
                        return stale
                    return getattr(result, attr)

            return _StatProxy()
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(qs.Path, "stat", fake_stat)
    score, details = _score_dependency_management(tmp_path)
    assert score == 1
    assert details["dependency_mgmt"].startswith("outdated")


# ---------------------------------------------------------------------------
# _calculate_tooling_score — composite
# ---------------------------------------------------------------------------


def test_calculate_tooling_score_full(tmp_path) -> None:
    import subprocess

    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "uv.lock").write_text("# lock\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    for i in range(6):
        (tmp_path / f"file_{i}.txt").write_text(f"{i}\n")
        subprocess.run(["git", "add", f"file_{i}.txt"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"c{i}"], cwd=tmp_path, check=True)

    result = _calculate_tooling_score(tmp_path)
    assert result["score"] >= 10
    assert "package_mgmt" in result["details"]


def test_calculate_tooling_score_minimal(tmp_path) -> None:
    result = _calculate_tooling_score(tmp_path)
    assert result["score"] == 0
    # Each sub-scorer reports a 'none' label even when scoring zero.
    assert result["details"]["version_control"] == "none"
    assert result["details"]["dependency_mgmt"] == "none"


# ---------------------------------------------------------------------------
# _evaluate_testing_infra — 4 branches
# ---------------------------------------------------------------------------


def test_evaluate_testing_infra_none(tmp_path) -> None:
    score, details = _evaluate_testing_infra(tmp_path)
    assert score == 0
    assert details["testing"] == "none"


def test_evaluate_testing_infra_comprehensive(tmp_path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text("# conftest\n")
    for i in range(11):
        (tests / f"test_{i}.py").write_text("def test_x(): pass\n")
    score, details = _evaluate_testing_infra(tmp_path)
    assert score == 5
    assert details["testing"].startswith("comprehensive")


def test_evaluate_testing_infra_moderate(tmp_path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    for i in range(7):
        (tests / f"test_{i}.py").write_text("def test_x(): pass\n")
    score, details = _evaluate_testing_infra(tmp_path)
    assert score == 3
    assert details["testing"].startswith("moderate")


def test_evaluate_testing_infra_basic(tmp_path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_one.py").write_text("def test_x(): pass\n")
    score, details = _evaluate_testing_infra(tmp_path)
    assert score == 1
    assert details["testing"].startswith("basic")


# ---------------------------------------------------------------------------
# _evaluate_documentation — 4 branches
# ---------------------------------------------------------------------------


def test_evaluate_documentation_none(tmp_path) -> None:
    score, details = _evaluate_documentation(tmp_path)
    assert score == 0
    assert details["documentation"] == "none"


def test_evaluate_documentation_readme_only(tmp_path) -> None:
    (tmp_path / "README.md").write_text("# Project\n")
    score, details = _evaluate_documentation(tmp_path)
    assert score == 2
    assert details["documentation"] == "README only"


def test_evaluate_documentation_basic_docs_dir(tmp_path) -> None:
    (tmp_path / "README.md").write_text("# Project\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(3):
        (docs / f"d_{i}.md").write_text(f"# D{i}\n")
    score, details = _evaluate_documentation(tmp_path)
    assert score == 3
    assert details["documentation"].startswith("basic")


def test_evaluate_documentation_comprehensive(tmp_path) -> None:
    (tmp_path / "README.md").write_text("# Project\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(6):
        (docs / f"d_{i}.md").write_text(f"# D{i}\n")
    score, details = _evaluate_documentation(tmp_path)
    assert score == 5
    assert details["documentation"].startswith("comprehensive")


# ---------------------------------------------------------------------------
# _evaluate_ci_cd — 4 branches
# ---------------------------------------------------------------------------


def test_evaluate_ci_cd_none(tmp_path) -> None:
    score, details = _evaluate_ci_cd(tmp_path)
    assert score == 0
    assert details["ci_cd"] == "none"


def test_evaluate_ci_cd_github_one_workflow(tmp_path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")
    score, details = _evaluate_ci_cd(tmp_path)
    assert score == 3
    assert details["ci_cd"].startswith("github")


def test_evaluate_ci_cd_github_two_workflows(tmp_path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")
    (workflows / "release.yml").write_text("name: Release\n")
    score, details = _evaluate_ci_cd(tmp_path)
    assert score == 5
    assert "2" in details["ci_cd"]


def test_evaluate_ci_cd_gitlab(tmp_path) -> None:
    (tmp_path / ".gitlab-ci.yml").write_text("stages: [test]\n")
    score, details = _evaluate_ci_cd(tmp_path)
    assert score == 4
    assert details["ci_cd"] == "gitlab ci"


# ---------------------------------------------------------------------------
# _calculate_maturity_score — composite
# ---------------------------------------------------------------------------


def test_calculate_maturity_score_minimal(tmp_path) -> None:
    result = _calculate_maturity_score(tmp_path)
    assert result["score"] == 0
    # Each sub-scorer reports a 'none' label even when scoring zero.
    assert result["details"]["testing"] == "none"
    assert result["details"]["documentation"] == "none"
    assert result["details"]["ci_cd"] == "none"


def test_calculate_maturity_score_comprehensive(tmp_path) -> None:
    (tmp_path / "README.md").write_text("# P\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(6):
        (docs / f"d_{i}.md").write_text(f"# D{i}\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text("# conftest\n")
    # Files must match the rglob("test_*.py") pattern in _evaluate_testing_infra.
    for i in range(11):
        (tests / f"test_t_{i}.py").write_text("def test_x(): pass\n")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")
    (workflows / "release.yml").write_text("name: Release\n")

    result = _calculate_maturity_score(tmp_path)
    assert result["score"] == 15


# ---------------------------------------------------------------------------
# _calculate_project_health / _calculate_dev_velocity / _calculate_security
# ---------------------------------------------------------------------------


def test_calculate_project_health_returns_project_health_score(tmp_path) -> None:
    """ProjectHealthScore is returned with details merged from tooling + maturity."""
    score = asyncio.run(_calculate_project_health(tmp_path))
    assert isinstance(score, ProjectHealthScore)
    assert score.details is not None
    assert score.total == round(score.tooling_score + score.maturity_score, 2)


def test_calculate_dev_velocity_no_git(tmp_path) -> None:
    score = asyncio.run(_calculate_dev_velocity(tmp_path))
    assert isinstance(score, DevVelocityScore)
    assert score.git_activity == 0
    assert score.dev_patterns == 0
    assert "no git repository" in score.details["activity"]
    assert "no git repository" in score.details["patterns"]


def test_calculate_security_default(tmp_path, monkeypatch) -> None:
    """Security score defaults to 0/0 when no security data exists."""
    # Empty tmp_path with a clean .gitignore so hygiene check passes.
    (tmp_path / ".gitignore").write_text(".env\n")

    async def fake_metrics(_p):
        return {}

    monkeypatch.setattr(
        _quality_scoring_utils,
        "_get_crackerjack_metrics",
        fake_metrics,
    )

    score = asyncio.run(_calculate_security(tmp_path))
    assert isinstance(score, SecurityScore)
    assert score.security_tools == 0.0
    assert score.security_hygiene == 5.0
    assert score.details["security_missing"] is True
    assert score.details["env_ignored"] == "yes"


# ---------------------------------------------------------------------------
# _analyze_git_activity / _collect_recent_commits / commit scoring
# ---------------------------------------------------------------------------


def test_collect_recent_commits_returns_list(tmp_path) -> None:
    commits = _collect_recent_commits(tmp_path)
    assert isinstance(commits, list)


def test_score_commit_frequency_thresholds() -> None:
    assert _score_commit_frequency(["x"] * 25)[0] == 5
    assert _score_commit_frequency(["x"] * 15)[0] == 4
    assert _score_commit_frequency(["x"] * 7)[0] == 2
    assert _score_commit_frequency(["x"])[0] == 1
    assert _score_commit_frequency([])[0] == 0


def test_score_commit_quality_excellent() -> None:
    commits = ["feat: a", "fix: b", "chore: c", "docs: d"]
    score, details = _score_commit_quality(commits)
    assert score == 5
    assert "excellent" in details["quality"]


def test_score_commit_quality_good() -> None:
    commits = ["feat: a", "fix: b", "no prefix here", "no prefix here"]
    score, details = _score_commit_quality(commits)
    assert score == 3
    assert "good" in details["quality"]


def test_score_commit_quality_basic() -> None:
    commits = ["feat: a", "no prefix", "no prefix", "no prefix"]
    score, details = _score_commit_quality(commits)
    assert score == 1
    assert "basic" in details["quality"]


def test_score_commit_quality_empty() -> None:
    score, details = _score_commit_quality([])
    assert score == 0
    assert details["quality"] == "no data"


def test_analyze_git_activity_no_git(tmp_path) -> None:
    result = _analyze_git_activity(tmp_path)
    assert result["score"] == 0
    assert result["details"]["activity"] == "no git repository"


def test_analyze_git_activity_subprocess_failure(tmp_path, monkeypatch) -> None:
    """When ``_collect_recent_commits`` raises, the analyzer records error and scores 0."""
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(
        _quality_scoring_utils,
        "_collect_recent_commits",
        lambda _p: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = _analyze_git_activity(tmp_path)
    assert result["score"] == 0
    assert "error" in result["details"]
    assert "boom" in result["details"]["error"]


# ---------------------------------------------------------------------------
# _analyze_dev_patterns / _score_issue_tracking / _score_branch_strategy
# ---------------------------------------------------------------------------


def test_analyze_dev_patterns_no_git(tmp_path) -> None:
    result = _analyze_dev_patterns(tmp_path)
    assert result["score"] == 0
    assert result["details"]["patterns"] == "no git repository"


def test_score_issue_tracking_no_git_returns_zero(tmp_path) -> None:
    """With no .git dir, ``_score_issue_tracking`` returns 0 + 'no data'."""
    score, details = _score_issue_tracking(tmp_path)
    assert score == 0
    # git binary may not be present; either way we expect a 0 score.
    assert details["issue_tracking"] in ("no data",)


def test_score_issue_tracking_subprocess_error(tmp_path, monkeypatch) -> None:
    """When ``subprocess.run`` raises, the function records the exception."""
    (tmp_path / ".git").mkdir()

    def fake_run(*args, **kwargs):
        raise OSError("subprocess down")

    monkeypatch.setattr(
        _quality_scoring_utils.subprocess, "run", fake_run
    )
    score, details = _score_issue_tracking(tmp_path)
    assert score == 0
    assert "subprocess down" in details["issue_tracking"]


def test_score_branch_strategy_main_only(tmp_path) -> None:
    """An empty branch list scores 1 ('main-only')."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("a")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    score, details = _score_branch_strategy(tmp_path)
    # main-only branch, no feature/* branches -> score 1
    assert score == 1
    assert details["branch_strategy"] == "main-only development"


def test_score_branch_strategy_with_feature_branches(tmp_path) -> None:
    """A repo with >=3 feature branches scores 5."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("a")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    for name in ("feature/a", "feature/b", "feature/c"):
        subprocess.run(["git", "branch", name], cwd=tmp_path, check=True)
    score, details = _score_branch_strategy(tmp_path)
    assert score == 5
    assert "feature branches" in details["branch_strategy"]


def test_score_branch_strategy_subprocess_error(tmp_path, monkeypatch) -> None:
    """When ``subprocess.run`` raises, return 0 + error detail."""
    (tmp_path / ".git").mkdir()

    def fake_run(*args, **kwargs):
        raise OSError("branch cmd down")

    monkeypatch.setattr(
        _quality_scoring_utils.subprocess, "run", fake_run
    )
    score, details = _score_branch_strategy(tmp_path)
    assert score == 0
    assert "branch cmd down" in details["branch_strategy"]


# ---------------------------------------------------------------------------
# _run_security_checks / _check_security_hygiene
# ---------------------------------------------------------------------------


def test_run_security_checks_missing(monkeypatch, tmp_path) -> None:
    """Missing security_score yields 0 + security_missing flag."""

    async def fake_metrics(_p):
        return {}

    monkeypatch.setattr(
        _quality_scoring_utils,
        "_get_crackerjack_metrics",
        fake_metrics,
    )

    result = asyncio.run(_run_security_checks(tmp_path))
    assert result["score"] == 0
    assert result["details"]["security_missing"] is True


def test_run_security_checks_present(monkeypatch, tmp_path) -> None:
    """When security_score is present, score = (raw/100)*5."""

    async def fake_metrics(_p):
        return {"security_score": 80}

    monkeypatch.setattr(
        _quality_scoring_utils,
        "_get_crackerjack_metrics",
        fake_metrics,
    )

    result = asyncio.run(_run_security_checks(tmp_path))
    assert result["score"] == 4.0  # (80/100)*5
    assert result["details"]["security_missing"] is False


def test_check_security_hygiene_full_deductions(tmp_path) -> None:
    """Missing .gitignore (-1) + one hardcoded password (-2) -> score 2."""
    # py_file with a password pattern triggers the -2 deduction.
    (tmp_path / "leaky.py").write_text('password = "secret123"\n')
    # No .gitignore -> -1
    # One hardcoded secret match -> -2
    # 5 - 1 - 2 = 2
    result = _check_security_hygiene(tmp_path)
    assert result["score"] == 2
    assert result["details"]["gitignore"] == "missing"
    assert "leaky.py" in result["details"]["hardcoded_secrets"]


def test_check_security_hygiene_env_not_ignored(tmp_path) -> None:
    """``.gitignore`` exists but lacks ``.env`` -> -2 deduction."""
    (tmp_path / ".gitignore").write_text("__pycache__/\n")
    result = _check_security_hygiene(tmp_path)
    assert result["score"] == 3
    assert result["details"]["env_ignored"] == "no (-.5 pts)"


def test_check_security_hygiene_clean(tmp_path) -> None:
    """.gitignore with .env AND no secrets -> score stays 5."""
    (tmp_path / ".gitignore").write_text(".env\n")
    result = _check_security_hygiene(tmp_path)
    assert result["score"] == 5
    assert result["details"]["env_ignored"] == "yes"


# ---------------------------------------------------------------------------
# _calculate_trust_score — 3 dimensions
# ---------------------------------------------------------------------------


def test_calculate_trust_score_perfect() -> None:
    score = _calculate_trust_score(4, True, 10)
    assert score.trusted_operations == 40
    assert score.session_availability == 30
    assert score.tool_ecosystem == 30
    assert score.total == 100


def test_calculate_trust_score_no_session() -> None:
    score = _calculate_trust_score(0, False, 0)
    assert score.trusted_operations == 0
    assert score.session_availability == 5
    assert score.tool_ecosystem == 0
    assert score.total == 5


def test_calculate_trust_score_caps_at_max() -> None:
    """Beyond 4 permissions and 10 tools, the score caps at 40/30."""
    score = _calculate_trust_score(10, True, 20)
    assert score.trusted_operations == 40  # min(10*10, 40)
    assert score.tool_ecosystem == 30  # min(20*3, 30)


# ---------------------------------------------------------------------------
# _get_cached_metrics — cache TTL behavior
# ---------------------------------------------------------------------------


def test_get_cached_metrics_returns_none_when_missing(monkeypatch) -> None:
    # Use a key that's definitely absent.
    assert _get_cached_metrics("/nonexistent/cache/key") is None


def test_get_cached_metrics_hits_within_ttl(monkeypatch) -> None:
    """Fresh entries (<5 min) return the cached dict."""
    from datetime import datetime, timezone

    monkeypatch.setattr(
        _quality_scoring_utils, "_metrics_cache",
        {"/fresh": ({"k": 1}, datetime.now(tz=timezone.utc))},
        raising=False,
    )
    assert _get_cached_metrics("/fresh") == {"k": 1}


def test_get_cached_metrics_misses_when_expired(monkeypatch) -> None:
    """Entries older than TTL return None (miss)."""
    from datetime import datetime, timedelta, timezone

    stale = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    monkeypatch.setattr(
        _quality_scoring_utils, "_metrics_cache",
        {"/stale": ({"k": 1}, stale)},
        raising=False,
    )
    assert _get_cached_metrics("/stale") is None


def test_get_cached_metrics_handles_naive_datetime(monkeypatch) -> None:
    """Naive cached datetimes are normalized to local tz, not rejected."""
    from datetime import datetime

    monkeypatch.setattr(
        _quality_scoring_utils, "_metrics_cache",
        {"/naive": ({"k": 1}, datetime.now())},
        raising=False,
    )
    assert _get_cached_metrics("/naive") == {"k": 1}


# ---------------------------------------------------------------------------
# _parse_metrics_history — already tested; add a couple more branches
# ---------------------------------------------------------------------------


def test_parse_metrics_history_ignores_unknown_metric_type() -> None:
    history = [
        {"metric_type": "unknown_metric", "metric_value": 99.0},
        {"metric_type": "lint_score", "metric_value": 50.0},
    ]
    metrics = _parse_metrics_history(history)
    assert metrics["lint_score"] == 50.0
    assert "unknown_metric" not in metrics


def test_parse_metrics_history_first_wins() -> None:
    """Duplicate metric_types: first occurrence wins."""
    history = [
        {"metric_type": "code_coverage", "metric_value": 80.0},
        {"metric_type": "code_coverage", "metric_value": 95.0},  # ignored
    ]
    metrics = _parse_metrics_history(history)
    assert metrics["code_coverage"] == 80.0


def test_parse_metrics_history_truncates_at_ten() -> None:
    """Beyond 10 entries, the parser stops scanning."""
    history = [{"metric_type": "lint_score", "metric_value": float(i)} for i in range(15)]
    metrics = _parse_metrics_history(history)
    # First 10 entries set lint_score to 0; entries 10+ are ignored.
    assert metrics["lint_score"] == 0.0


# ---------------------------------------------------------------------------
# _read_coverage_json — present, missing, malformed, statement vs line
# ---------------------------------------------------------------------------


def test_read_coverage_json_missing(tmp_path) -> None:
    assert _read_coverage_json(tmp_path) == 0


def test_read_coverage_json_malformed(tmp_path) -> None:
    (tmp_path / "coverage.json").write_text("{not valid json")
    assert _read_coverage_json(tmp_path) == 0


def test_read_coverage_json_prefers_statements(tmp_path) -> None:
    (tmp_path / "coverage.json").write_text(
        '{"totals": {"percent_statements_covered": 87.5, "percent_covered": 70.0}}'
    )
    assert _read_coverage_json(tmp_path) == 87.5


def test_read_coverage_json_falls_back_to_line(tmp_path) -> None:
    """When ``percent_statements_covered`` is absent, fall back to ``percent_covered``."""
    (tmp_path / "coverage.json").write_text('{"totals": {"percent_covered": 60.0}}')
    assert _read_coverage_json(tmp_path) == 60.0


# ---------------------------------------------------------------------------
# _read_coverage_dotfile — missing, present
# ---------------------------------------------------------------------------


def test_read_coverage_dotfile_missing(tmp_path) -> None:
    assert _read_coverage_dotfile(tmp_path) == 0


def test_read_coverage_dotfile_returns_zero_on_corrupt(tmp_path) -> None:
    (tmp_path / ".coverage").write_bytes(b"not a real coverage db")
    assert _read_coverage_dotfile(tmp_path) == 0


def test_read_coverage_dotfile_legacy_int(monkeypatch, tmp_path) -> None:
    """Older coverage.py returns a plain int (line-coverage percent)."""
    from unittest.mock import MagicMock, patch

    (tmp_path / ".coverage").write_bytes(b"")

    mock_cov = MagicMock()
    mock_cov.report.return_value = 72.5  # legacy int return

    with patch("coverage.Coverage", return_value=mock_cov):
        result = _read_coverage_dotfile(tmp_path)

    assert result == 72.5


def test_read_coverage_dotfile_numbers_pc_statements(monkeypatch, tmp_path) -> None:
    """Newer coverage.py returns a Numbers instance with pc_statements.

    The function imports ``coverage.results.Numbers`` inside its body; we
    patch the symbol at the source location so the ``isinstance`` branch
    fires for our duck-typed stand-in.
    """
    from unittest.mock import MagicMock, patch

    class DuckNumbers:
        n_statements = 10
        pc_statements = 91.0

    monkeypatch.setattr("coverage.results.Numbers", DuckNumbers)

    (tmp_path / ".coverage").write_bytes(b"")
    mock_cov = MagicMock()
    mock_cov.report.return_value = DuckNumbers()

    with patch("coverage.Coverage", return_value=mock_cov):
        result = _read_coverage_dotfile(tmp_path)

    assert result == 91.0


# ---------------------------------------------------------------------------
# _create_fallback_metrics — explicit unavailable sentinel
# ---------------------------------------------------------------------------


def test_create_fallback_metrics_marks_unavailable() -> None:
    metrics = _create_fallback_metrics()
    assert metrics["unavailable"] is True
    for k in ("code_coverage", "lint_score", "security_score", "complexity_score"):
        assert metrics[k] is None


# ---------------------------------------------------------------------------
# _get_crackerjack_metrics — cache behavior + str conversion
# ---------------------------------------------------------------------------


def test_get_crackerjack_metrics_accepts_string_path(tmp_path, monkeypatch) -> None:
    """String paths are coerced to Path objects."""
    monkeypatch.setattr(
        _quality_scoring_utils, "_metrics_cache", {}, raising=False
    )

    async def fake_collect(_p):
        return {}

    monkeypatch.setattr(
        _quality_scoring_utils,
        "_collect_crackerjack_metrics",
        fake_collect,
    )
    monkeypatch.setattr(_quality_scoring_utils, "CRACKERJACK_AVAILABLE", False)
    result = asyncio.run(_get_crackerjack_metrics(str(tmp_path)))
    assert result == {}


def test_get_crackerjack_metrics_cache_hit(monkeypatch) -> None:
    """When the cache has fresh data, the orchestrator returns it directly."""
    from datetime import datetime, timezone

    sentinel = {"code_coverage": 50.0, "lint_score": 60.0, "security_score": 70.0, "complexity_score": 80.0}
    monkeypatch.setattr(
        _quality_scoring_utils,
        "_metrics_cache",
        {"/cached": (sentinel, datetime.now(tz=timezone.utc))},
        raising=False,
    )
    result = asyncio.run(_get_crackerjack_metrics("/cached"))
    assert result is sentinel


def test_get_crackerjack_metrics_unavailable_when_cli_disabled(monkeypatch, tmp_path) -> None:
    """CLI tier disabled + coverage-only metrics -> synthesized unavailable."""
    monkeypatch.setattr(_quality_scoring_utils, "_metrics_cache", {}, raising=False)
    monkeypatch.setattr(_quality_scoring_utils, "CRACKERJACK_AVAILABLE", False)

    async def fake_collect(_p):
        # Coverage-only signal — no non-coverage source populated.
        return {"code_coverage": 80.0}

    monkeypatch.setattr(
        _quality_scoring_utils,
        "_collect_crackerjack_metrics",
        fake_collect,
    )
    result = asyncio.run(_get_crackerjack_metrics(tmp_path))
    assert result["unavailable"] is True


# ---------------------------------------------------------------------------
# _get_type_coverage — three branches
# ---------------------------------------------------------------------------


def test_get_type_coverage_from_crackerjack(tmp_path) -> None:
    result = asyncio.run(_get_type_coverage(tmp_path, {"type_coverage": 92.0}))
    assert result == 92.0


def test_get_type_coverage_from_pyright(tmp_path) -> None:
    (tmp_path / "pyrightconfig.json").write_text("{}")
    result = asyncio.run(_get_type_coverage(tmp_path, {}))
    assert result == 70.0


def test_get_type_coverage_from_mypy_config(tmp_path) -> None:
    (tmp_path / "mypy.ini").write_text("[mypy]\n")
    result = asyncio.run(_get_type_coverage(tmp_path, {}))
    assert result == 70.0


def test_get_type_coverage_no_checker(tmp_path) -> None:
    result = asyncio.run(_get_type_coverage(tmp_path, {}))
    assert result == 30.0


# ---------------------------------------------------------------------------
# _generate_recommendations_v2 — each threshold
# ---------------------------------------------------------------------------


def _scores(
    test=15.0,
    lint=10.0,
    type_cov=10.0,
    complexity=5.0,
    tooling=15.0,
    maturity=15.0,
    git_act=10.0,
    dev_patterns=10.0,
    sec_tools=5.0,
    sec_hygiene=5.0,
    total=100.0,
):
    return (
        CodeQualityScore(
            test_coverage=test,
            lint_score=lint,
            type_coverage=type_cov,
            complexity_score=complexity,
            total=test + lint + type_cov + complexity,
            details={"coverage_pct": 50.0},
        ),
        ProjectHealthScore(
            tooling_score=tooling,
            maturity_score=maturity,
            total=tooling + maturity,
            details={},
        ),
        DevVelocityScore(
            git_activity=git_act,
            dev_patterns=dev_patterns,
            total=git_act + dev_patterns,
            details={},
        ),
        SecurityScore(
            security_tools=sec_tools,
            security_hygiene=sec_hygiene,
            total=sec_tools + sec_hygiene,
            details={},
        ),
        total,
    )


def test_recommendations_excellent_band() -> None:
    cq, ph, dv, sec, total = _scores(total=95.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("Excellent" in r for r in recs)


def test_recommendations_good_band() -> None:
    cq, ph, dv, sec, total = _scores(total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("Good quality" in r for r in recs)


def test_recommendations_moderate_band() -> None:
    cq, ph, dv, sec, total = _scores(total=65.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("Moderate" in r for r in recs)


def test_recommendations_critical_band() -> None:
    cq, ph, dv, sec, total = _scores(total=50.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("prioritize" in r.lower() for r in recs)


def test_recommendations_coverage_critical() -> None:
    cq, ph, dv, sec, total = _scores(test=5.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("Critical: Increase test coverage" in r for r in recs)


def test_recommendations_coverage_add_more() -> None:
    cq, ph, dv, sec, total = _scores(test=11.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("Add more tests" in r for r in recs)


def test_recommendations_lint_below_8() -> None:
    cq, ph, dv, sec, total = _scores(lint=5.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("lint" in r.lower() for r in recs)


def test_recommendations_type_below_7() -> None:
    cq, ph, dv, sec, total = _scores(type_cov=4.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("type hints" in r.lower() for r in recs)


def test_recommendations_complexity_below_3() -> None:
    cq, ph, dv, sec, total = _scores(complexity=1.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("Refactor complex" in r for r in recs)


def test_recommendations_tooling_below_10() -> None:
    cq, ph, dv, sec, total = _scores(tooling=5.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("tooling" in r.lower() for r in recs)


def test_recommendations_maturity_below_10() -> None:
    cq, ph, dv, sec, total = _scores(maturity=5.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("maturity" in r.lower() for r in recs)


def test_recommendations_git_activity_below_5() -> None:
    cq, ph, dv, sec, total = _scores(git_act=2.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("commit quality" in r.lower() for r in recs)


def test_recommendations_dev_patterns_below_5() -> None:
    cq, ph, dv, sec, total = _scores(dev_patterns=2.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("feature branch" in r.lower() for r in recs)


def test_recommendations_security_below_8() -> None:
    cq, ph, dv, sec, total = _scores(sec_tools=2.0, sec_hygiene=2.0, total=80.0)
    recs = _generate_recommendations_v2(cq, ph, dv, sec, total)
    assert any("security" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# calculate_quality_score_v2 — aggregator
# ---------------------------------------------------------------------------


def test_calculate_quality_score_v2_runs_and_returns_dataclass(
    monkeypatch, tmp_path
) -> None:
    """End-to-end orchestrator returns a fully-populated QualityScoreV2."""

    async def fake_metrics(_p):
        return {
            "code_coverage": 80.0,
            "lint_score": 70.0,
            "security_score": 60.0,
            "complexity_score": 90.0,
        }

    monkeypatch.setattr(
        _quality_scoring_utils,
        "_get_crackerjack_metrics",
        fake_metrics,
    )

    result = asyncio.run(
        calculate_quality_score_v2(
            tmp_path,
            permissions_count=2,
            session_available=True,
            tool_count=5,
        )
    )

    assert isinstance(result, QualityScoreV2)
    assert result.version == "2.0"
    assert 0 <= result.total_score <= 100
    assert result.timestamp.endswith("+00:00") or "T" in result.timestamp
    assert isinstance(result.code_quality, CodeQualityScore)
    assert isinstance(result.project_health, ProjectHealthScore)
    assert isinstance(result.dev_velocity, DevVelocityScore)
    assert isinstance(result.security, SecurityScore)
    assert isinstance(result.trust_score, TrustScore)
    assert isinstance(result.recommendations, list)


# ---------------------------------------------------------------------------
# Module-level: __all__ + backward-compat re-exports
# ---------------------------------------------------------------------------


def test_module_all_matches_expected_surface() -> None:
    assert _quality_scoring_utils.__all__ == [
        "CodeQualityScore",
        "DevVelocityScore",
        "ProjectHealthScore",
        "QualityScoreV2",
        "SecurityScore",
        "TrustScore",
        "_extract_quality_scores",
        "_generate_quality_trend_recommendations",
        "calculate_quality_score_v2",
    ]


def test_extract_quality_scores_re_export_is_callable() -> None:
    """The re-exported ``_extract_quality_scores`` is a callable from the parser."""
    fn = _quality_scoring_utils._extract_quality_scores
    assert callable(fn)
    # Smoke call: empty input -> empty list.
    assert fn([]) == []


def test_generate_quality_trend_recommendations_re_export_is_callable() -> None:
    """The re-exported ``_generate_quality_trend_recommendations`` is callable."""
    fn = _quality_scoring_utils._generate_quality_trend_recommendations
    assert callable(fn)
    # Empty scores -> starter message.
    recs = fn([])
    assert isinstance(recs, list)
    assert len(recs) >= 1
