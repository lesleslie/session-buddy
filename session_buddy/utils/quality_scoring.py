#!/usr/bin/env python3
# ruff: noqa: EXE001
"""Quality Scoring Algorithm V2 - Measures actual code quality.

This module implements a comprehensive quality scoring system that focuses on
real code quality metrics instead of superficial indicators.

Key improvements over V1:
- Integrates Crackerjack code quality metrics (coverage, lint, complexity)
- Smart project health indicators (doesn't penalize modern tooling)
- Separates permissions/trust from code quality
- Provides actionable, honest quality assessment
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import subprocess  # nosec B404
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli
from session_buddy.utils.time import utc_now

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from session_buddy.crackerjack_integration import (
        get_quality_metrics_history,
    )

# Crackerjack integration for quality metrics
try:
    from session_buddy.crackerjack_integration import (
        get_quality_metrics_history,
    )

    CRACKERJACK_AVAILABLE = True
except ImportError:
    CRACKERJACK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Async dispatch helper (asyncio.to_thread)
# ---------------------------------------------------------------------------
#
# The scoring helpers below historically used ``subprocess.run`` synchronously.
# In an async server (uvicorn), a sync ``subprocess.run`` blocks the event loop
# for the duration of the subprocess — concurrent scoring requests queue up
# behind whichever call holds the loop, eventually hitting client-side timeouts
# (mahavishnu followup 2026-07-16-multi-session-mcp-contention).
#
# Resolution: keep the per-scoring helpers sync (so direct unit-test calls and
# ``subprocess.run`` monkeypatches keep working unchanged) but dispatch them
# from the async orchestrators (``_calculate_project_health``,
# ``_calculate_dev_velocity``) via ``asyncio.to_thread``. The subprocess still
# runs synchronously — but in a worker thread — so the uvicorn loop keeps
# spinning while the git command executes. Concurrent checkpoint calls now
# parallelize across worker threads instead of serializing on the event loop.


@dataclass
class CodeQualityScore:
    """Code quality component (40 points max)."""

    test_coverage: float  # 0-15 points
    lint_score: float  # 0-10 points
    type_coverage: float  # 0-10 points
    complexity_score: float  # 0-5 points
    total: float  # Sum of above
    details: dict[str, Any]  # Detailed breakdown


@dataclass
class ProjectHealthScore:
    """Project health component (30 points max)."""

    tooling_score: float  # 0-15 points
    maturity_score: float  # 0-15 points
    total: float  # Sum of above
    details: dict[str, Any]  # Detailed breakdown


@dataclass
class DevVelocityScore:
    """Development velocity component (20 points max)."""

    git_activity: float  # 0-10 points
    dev_patterns: float  # 0-10 points
    total: float  # Sum of above
    details: dict[str, Any]  # Detailed breakdown


@dataclass
class SecurityScore:
    """Security component (10 points max)."""

    security_tools: float  # 0-5 points
    security_hygiene: float  # 0-5 points
    total: float  # Sum of above
    details: dict[str, Any]  # Detailed breakdown


@dataclass
class TrustScore:
    """Separate trust score (not part of quality)."""

    trusted_operations: float  # 0-40 points
    session_availability: float  # 0-30 points
    tool_ecosystem: float  # 0-30 points
    total: float  # 0-100 points
    details: dict[str, Any]  # Detailed breakdown


@dataclass
class QualityScoreV2:
    """Complete quality score V2 result."""

    total_score: float  # 0-100
    version: str  # "2.0"
    code_quality: CodeQualityScore
    project_health: ProjectHealthScore
    dev_velocity: DevVelocityScore
    security: SecurityScore
    trust_score: TrustScore
    recommendations: list[str]
    timestamp: str


# Crackerjack metrics cache (5 minute TTL)
_metrics_cache: dict[str, tuple[dict[str, Any], datetime]] = {}
_CACHE_TTL_MINUTES = 5


async def calculate_quality_score_v2(
    project_dir: Path,
    permissions_count: int = 0,
    session_available: bool = True,
    tool_count: int = 0,
) -> QualityScoreV2:
    """Calculate comprehensive quality score V2.

    Args:
        project_dir: Project directory to analyze
        permissions_count: Number of trusted operations (for trust score)
        session_available: Whether session management is available (for trust score)
        tool_count: Number of available MCP tools (for trust score)

    Returns:
        Complete quality score breakdown

    """
    # Calculate each component
    code_quality = await _calculate_code_quality(project_dir)
    project_health = await _calculate_project_health(project_dir)
    dev_velocity = await _calculate_dev_velocity(project_dir)
    security = await _calculate_security(project_dir)
    trust_score = _calculate_trust_score(
        permissions_count,
        session_available,
        tool_count,
    )

    # Calculate total
    total = (
        code_quality.total + project_health.total + dev_velocity.total + security.total
    )

    # Generate recommendations
    recommendations = _generate_recommendations_v2(
        code_quality,
        project_health,
        dev_velocity,
        security,
        total,
    )

    return QualityScoreV2(
        total_score=round(
            total,
        ),  # Convert to int for backward compatibility with tests
        version="2.0",
        code_quality=code_quality,
        project_health=project_health,
        dev_velocity=dev_velocity,
        security=security,
        trust_score=trust_score,
        recommendations=recommendations,
        timestamp=utc_now().isoformat(),
    )


async def _calculate_code_quality(project_dir: Path) -> CodeQualityScore:
    """Calculate code quality score (40 points max).

    Components:
    - test_coverage: 15 points (from Crackerjack)
    - lint_score: 10 points (from Crackerjack)
    - type_coverage: 10 points (from pyright/mypy)
    - complexity_score: 5 points (inverse of complexity)
    """
    metrics = await _get_crackerjack_metrics(project_dir)

    # Test coverage (0-15 points)
    coverage_pct = metrics.get("code_coverage", 0)
    test_coverage = (coverage_pct / 100) * 15

    # Lint score (0-10 points)
    # Crackerjack lint_score is already 0-100, normalized.
    # Missing data defaults to 0 with a ``lint_missing`` flag rather than
    # a perfect 100, so absent metrics cannot silently pass the gate.
    lint_raw = metrics.get("lint_score")
    if lint_raw is None:
        lint_score = 0.0
        lint_missing = True
    else:
        lint_score = (float(lint_raw) / 100) * 10
        lint_missing = False

    # Type coverage (0-10 points)
    # Try to extract from pyright/mypy via Crackerjack
    type_pct = await _get_type_coverage(project_dir, metrics)
    type_coverage = (type_pct / 100) * 10

    # Complexity score (0-5 points, inverse)
    # Missing data defaults to 0 with a ``complexity_missing`` flag rather
    # than a perfect 100, mirroring the lint handling above.
    complexity_raw = metrics.get("complexity_score")
    if complexity_raw is None:
        complexity_score = 0.0
        complexity_missing = True
    else:
        # complexity_score is 0-100 where 100 is best (low complexity)
        complexity_score = (float(complexity_raw) / 100) * 5
        complexity_missing = False

    total = test_coverage + lint_score + type_coverage + complexity_score

    return CodeQualityScore(
        test_coverage=round(test_coverage, 2),
        lint_score=round(lint_score, 2),
        type_coverage=round(type_coverage, 2),
        complexity_score=round(complexity_score, 2),
        total=round(total, 2),
        details={
            "coverage_pct": coverage_pct,
            "lint_raw": lint_raw,
            "type_pct": type_pct,
            "complexity_raw": complexity_raw,
            "lint_missing": lint_missing,
            "complexity_missing": complexity_missing,
            "metrics_source": "crackerjack" if metrics else "fallback",
        },
    )


async def _calculate_project_health(project_dir: Path) -> ProjectHealthScore:
    """Calculate project health score (30 points max).

    Components:
    - tooling_score: 15 points (modern tooling)
    - maturity_score: 15 points (project maturity)
    """
    # The sub-calculators (``_calculate_tooling_score``,
    # ``_calculate_maturity_score``) are sync and may run ``git log`` /
    # ``git branch`` synchronously via ``subprocess.run``. We dispatch them
    # via ``asyncio.to_thread`` so the uvicorn event loop keeps spinning
    # while the git subprocess runs (mahavishnu followup
    # 2026-07-16-multi-session-mcp-contention).
    tooling = await asyncio.to_thread(_calculate_tooling_score, project_dir)
    maturity = await asyncio.to_thread(_calculate_maturity_score, project_dir)

    return ProjectHealthScore(
        tooling_score=round(tooling["score"], 2),
        maturity_score=round(maturity["score"], 2),
        total=round(tooling["score"] + maturity["score"], 2),
        details={**tooling["details"], **maturity["details"]},
    )


def _score_package_management(project_dir: Path) -> tuple[float, dict[str, str]]:
    """Score package management setup (0-5 points)."""
    has_pyproject = (project_dir / "pyproject.toml").exists()
    has_lockfile = (project_dir / "uv.lock").exists() or (
        project_dir / "requirements.txt"
    ).exists()

    if has_pyproject and has_lockfile:
        return 5, {"package_mgmt": "modern (pyproject.toml + lockfile)"}
    if has_pyproject:
        return 3, {"package_mgmt": "partial (pyproject.toml, no lockfile)"}
    if has_lockfile:
        return 2, {"package_mgmt": "basic (lockfile only)"}
    return 0, {}


def _score_version_control(project_dir: Path) -> tuple[float, dict[str, str]]:
    """Score version control setup (0-5 points)."""
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return 0, {"version_control": "none"}

    with suppress(
        subprocess.SubprocessError,
        subprocess.TimeoutExpired,
        OSError,
        FileNotFoundError,
    ):
        # GIT_CEILING_DIRECTORIES prevents git from walking up the directory
        # tree and finding an unrelated parent repo (e.g. when a test's
        # tmp_path is itself inside a git checkout). Without it, an empty
        # project_dir/.git would silently return the parent repo's history
        # and inflate the score.
        ceiling = str(project_dir.parent.absolute())
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", "10"],
            check=False,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=2,
            env={**os.environ, "GIT_CEILING_DIRECTORIES": ceiling},
        )
        if result.returncode == 0 and len(result.stdout.strip().split("\n")) >= 5:
            return 5, {"version_control": "active git repository"}
        return 3, {"version_control": "git repo (limited history)"}

    return 2, {"version_control": "git repo (couldn't verify history)"}


def _score_dependency_management(project_dir: Path) -> tuple[float, dict[str, str]]:
    """Score dependency management (0-5 points)."""
    lockfile = project_dir / "uv.lock"
    if not lockfile.exists():
        lockfile = project_dir / "requirements.txt"

    if not lockfile.exists():
        return 0, {"dependency_mgmt": "none"}

    with suppress(OSError, PermissionError, FileNotFoundError, ValueError):
        lockfile_age_days = (
            utc_now() - datetime.fromtimestamp(lockfile.stat().st_mtime, tz=UTC)
        ).days

        if lockfile_age_days < 30:
            return 5, {"dependency_mgmt": "recently updated"}
        if lockfile_age_days < 90:
            return 3, {"dependency_mgmt": "moderately current"}
        return 1, {"dependency_mgmt": f"outdated ({lockfile_age_days} days)"}

    return 2, {"dependency_mgmt": "present (age unknown)"}


def _calculate_tooling_score(project_dir: Path) -> dict[str, Any]:
    """Calculate modern tooling score (0-15 points).

    Components:
    - package_management: 5 pts (pyproject.toml + lockfile)
    - version_control: 5 pts (.git + active history)
    - dependency_mgmt: 5 pts (lockfile + recent updates)
    """
    pkg_score, pkg_details = _score_package_management(project_dir)
    vc_score, vc_details = _score_version_control(project_dir)
    dep_score, dep_details = _score_dependency_management(project_dir)

    total_score = pkg_score + vc_score + dep_score
    details = pkg_details | vc_details | dep_details

    return {"score": total_score, "details": details}


def _calculate_maturity_score(project_dir: Path) -> dict[str, Any]:
    """Calculate project maturity score (0-15 points)."""
    score = 0
    details = {}

    testing_score, testing_details = _evaluate_testing_infra(project_dir)
    documentation_score, documentation_details = _evaluate_documentation(project_dir)
    ci_score, ci_details = _evaluate_ci_cd(project_dir)

    score += testing_score + documentation_score + ci_score
    details.update(testing_details)
    details.update(documentation_details)
    details.update(ci_details)

    return {"score": score, "details": details}


def _evaluate_testing_infra(project_dir: Path) -> tuple[int, dict[str, str]]:
    """Return score/details describing testing infrastructure maturity."""
    test_dirs = list(project_dir.glob("test*"))
    if not test_dirs:
        return 0, {"testing": "none"}

    test_dir = test_dirs[0]
    has_conftest = (test_dir / "conftest.py").exists()
    test_files = list(test_dir.rglob("test_*.py"))

    if has_conftest and len(test_files) >= 10:
        return 5, {"testing": f"comprehensive ({len(test_files)} test files)"}
    if len(test_files) >= 5:
        return 3, {"testing": f"moderate ({len(test_files)} test files)"}
    if test_files:
        return 1, {"testing": f"basic ({len(test_files)} test files)"}
    return 0, {"testing": "none"}


def _evaluate_documentation(project_dir: Path) -> tuple[int, dict[str, str]]:
    """Return documentation maturity score and details."""
    has_readme = (project_dir / "README.md").exists()
    docs_dir = project_dir / "docs"

    if has_readme and docs_dir.exists():
        doc_files = list(docs_dir.rglob("*.md"))
        if len(doc_files) >= 5:
            return 5, {"documentation": f"comprehensive ({len(doc_files)} docs)"}
        return 3, {"documentation": f"basic ({len(doc_files)} docs)"}
    if has_readme:
        return 2, {"documentation": "README only"}
    return 0, {"documentation": "none"}


def _evaluate_ci_cd(project_dir: Path) -> tuple[int, dict[str, str]]:
    """Return CI/CD maturity score and details."""
    github_workflows = project_dir / ".github" / "workflows"
    gitlab_ci = project_dir / ".gitlab-ci.yml"

    if github_workflows.exists():
        workflow_files = list(github_workflows.glob("*.yml")) + list(
            github_workflows.glob("*.yaml"),
        )
        if len(workflow_files) >= 2:
            return 5, {"ci_cd": f"github actions ({len(workflow_files)} workflows)"}
        if workflow_files:
            return 3, {"ci_cd": "github actions (1 workflow)"}
    elif gitlab_ci.exists():
        return 4, {"ci_cd": "gitlab ci"}
    return 0, {"ci_cd": "none"}


async def _calculate_dev_velocity(project_dir: Path) -> DevVelocityScore:
    """Calculate development velocity score (20 points max).

    Components:
    - git_activity: 10 points (commit frequency, quality)
    - dev_patterns: 10 points (issue tracking, branch strategy)

    The sub-calculators run ``git log`` / ``git branch`` synchronously
    via ``subprocess.run``; dispatch via ``asyncio.to_thread`` so the
    uvicorn event loop keeps spinning while the subprocess runs.
    """
    git_activity = await asyncio.to_thread(_analyze_git_activity, project_dir)
    dev_patterns = await asyncio.to_thread(_analyze_dev_patterns, project_dir)

    return DevVelocityScore(
        git_activity=round(git_activity["score"], 2),
        dev_patterns=round(dev_patterns["score"], 2),
        total=round(git_activity["score"] + dev_patterns["score"], 2),
        details={**git_activity["details"], **dev_patterns["details"]},
    )


def _analyze_git_activity(project_dir: Path) -> dict[str, Any]:
    """Analyze git activity (0-10 points)."""
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {"score": 0, "details": {"activity": "no git repository"}}

    try:
        commits = _collect_recent_commits(project_dir)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"score": 0, "details": {"error": f"git analysis failed: {exc}"}}

    frequency_score, frequency_details = _score_commit_frequency(commits)
    quality_score, quality_details = _score_commit_quality(commits)

    # Balance both metrics evenly (0-5 each)
    total_score = frequency_score + quality_score
    details = frequency_details | quality_details
    return {"score": total_score, "details": details}


def _collect_recent_commits(project_dir: Path) -> list[str]:
    """Return commit messages for the last 30 days."""
    since_date = (utc_now() - timedelta(days=30)).strftime("%Y-%m-%d")
    # Constrain git to the project_dir subtree so a test's empty
    # ``.git`` cannot silently walk up and return the parent
    # repo's history (which would inflate the dev_velocity score).
    ceiling = str(project_dir.parent.absolute())
    result = subprocess.run(
        ["git", "log", f"--since={since_date}", "--pretty=format:%s", "--no-merges"],
        check=False,
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=5,
        env={**os.environ, "GIT_CEILING_DIRECTORIES": ceiling},
    )

    if result.returncode != 0 or not result.stdout.strip():
        return []
    return result.stdout.strip().split("\n")


def _score_commit_frequency(commits: list[str]) -> tuple[int, dict[str, str]]:
    """Score commit frequency (0-5) with descriptive details."""
    commit_count = len(commits)
    if commit_count >= 20:
        return 5, {"frequency": f"active ({commit_count} commits/month)"}
    if commit_count >= 10:
        return 4, {"frequency": f"regular ({commit_count} commits/month)"}
    if commit_count >= 5:
        return 2, {"frequency": f"occasional ({commit_count} commits/month)"}
    if commit_count > 0:
        return 1, {"frequency": f"sparse ({commit_count} commits/month)"}
    return 0, {"frequency": "no recent commits"}


def _score_commit_quality(commits: list[str]) -> tuple[int, dict[str, str]]:
    """Score conventional commit adherence (0-5)."""
    if not commits:
        return 0, {"quality": "no data"}

    conventional = sum(
        1
        for msg in commits
        if re.match(r"^(feat|fix|docs|style|refactor|test|chore)(\(.*\))?:", msg)
    )
    commit_count = len(commits)

    if conventional >= commit_count * 0.8:
        return 5, {"quality": f"excellent ({conventional}/{commit_count} conventional)"}
    if conventional >= commit_count * 0.5:
        return 3, {"quality": f"good ({conventional}/{commit_count} conventional)"}
    if commit_count > 0:
        return 1, {"quality": f"basic ({conventional}/{commit_count} conventional)"}
    return 0, {"quality": "no data"}


def _analyze_dev_patterns(project_dir: Path) -> dict[str, Any]:
    """Analyze development patterns (0-10 points)."""
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {"score": 0, "details": {"patterns": "no git repository"}}

    issue_score, issue_details = _score_issue_tracking(project_dir)
    branch_score, branch_details = _score_branch_strategy(project_dir)

    details = issue_details | branch_details
    return {"score": issue_score + branch_score, "details": details}


def _score_issue_tracking(project_dir: Path) -> tuple[int, dict[str, str]]:
    """Analyze recent commits for issue references."""
    try:
        # Constrain git to the project_dir subtree so a test's empty
        # ``.git`` cannot silently walk up and use the parent repo's
        # commit history (which would inflate issue_tracking).
        ceiling = str(project_dir.parent.absolute())
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", "50", "--no-merges"],
            check=False,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "GIT_CEILING_DIRECTORIES": ceiling},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 0, {"issue_tracking": f"analysis failed: {exc}"}

    if result.returncode != 0 or not result.stdout.strip():
        return 0, {"issue_tracking": "no data"}

    commits = result.stdout.strip().split("\n")
    issue_refs = sum(1 for msg in commits if re.search(r"#\d+", msg))

    if issue_refs >= len(commits) * 0.5:
        return 5, {"issue_tracking": f"excellent ({issue_refs}/{len(commits)} refs)"}
    if issue_refs >= len(commits) * 0.25:
        return 3, {"issue_tracking": f"good ({issue_refs}/{len(commits)} refs)"}
    if issue_refs > 0:
        return 1, {"issue_tracking": f"basic ({issue_refs}/{len(commits)} refs)"}
    return 0, {"issue_tracking": "none"}


def _score_branch_strategy(project_dir: Path) -> tuple[int, dict[str, str]]:
    """Evaluate branch naming strategy for feature work."""
    try:
        # Constrain git to the project_dir subtree so a test's empty
        # ``.git`` cannot silently walk up and use the parent repo's
        # branches (which would inflate the branch_strategy score).
        ceiling = str(project_dir.parent.absolute())
        result = subprocess.run(
            ["git", "branch", "-a"],
            check=False,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "GIT_CEILING_DIRECTORIES": ceiling},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 0, {"branch_strategy": f"analysis failed: {exc}"}

    if result.returncode != 0 or not result.stdout.strip():
        return 0, {"branch_strategy": "no data"}

    branches = result.stdout.strip().split("\n")
    feature_branches = [b for b in branches if "feature/" in b or "feat/" in b]

    if len(feature_branches) >= 3:
        return 5, {
            "branch_strategy": f"feature branches ({len(feature_branches)} active)"
        }
    if feature_branches:
        return 3, {
            "branch_strategy": f"some feature branches ({len(feature_branches)})"
        }
    return 1, {"branch_strategy": "main-only development"}


async def _calculate_security(project_dir: Path) -> SecurityScore:
    """Calculate security score (10 points max).

    Components:
    - security_tools: 5 points (bandit, safety checks)
    - security_hygiene: 5 points (no secrets, secure patterns)
    """
    tools_score = await _run_security_checks(project_dir)
    hygiene_score = _check_security_hygiene(project_dir)

    return SecurityScore(
        security_tools=round(tools_score["score"], 2),
        security_hygiene=round(hygiene_score["score"], 2),
        total=round(tools_score["score"] + hygiene_score["score"], 2),
        details={**tools_score["details"], **hygiene_score["details"]},
    )


async def _run_security_checks(project_dir: Path) -> dict[str, Any]:
    """Run security tools via Crackerjack (0-5 points)."""
    metrics = await _get_crackerjack_metrics(project_dir)

    security_score_raw = metrics.get("security_score")
    if security_score_raw is None:
        # Missing data defaults to 0 with ``security_missing`` flag rather
        # than silently awarding a perfect score.
        score = 0
        security_missing = True
    else:
        # Security score from Crackerjack is 0-100, 100 is best
        score = (float(security_score_raw) / 100) * 5
        security_missing = False

    return {
        "score": score,
        "details": {
            "security_raw": security_score_raw,
            "security_missing": security_missing,
            "source": "crackerjack" if metrics else "fallback",
        },
    }


def _check_security_hygiene(project_dir: Path) -> dict[str, Any]:
    """Check security hygiene (0-5 points)."""
    score = 5  # Start with perfect, deduct for issues
    details = {}

    # Check for .env in .gitignore (critical)
    gitignore = project_dir / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".env" in content:
            details["env_ignored"] = "yes"
        else:
            score -= 2
            details["env_ignored"] = "no (-.5 pts)"
    else:
        score -= 1
        details["gitignore"] = "missing"

    # Check for hardcoded secrets (basic patterns)
    with suppress(
        OSError,
        PermissionError,
        FileNotFoundError,
        UnicodeDecodeError,
        ValueError,
    ):
        py_files = list(project_dir.rglob("*.py"))[:50]  # Limit to 50 files
        secret_patterns = [
            r"password\s*=\s*['\"][^'\"]+['\"]",
            r"api_key\s*=\s*['\"][^'\"]+['\"]",
            r"secret\s*=\s*['\"][^'\"]+['\"]",
        ]

        for py_file in py_files:
            content = py_file.read_text()
            for pattern in secret_patterns:
                if re.search(
                    pattern,
                    content,
                    re.IGNORECASE,
                ):  # REGEX OK: security pattern detection
                    score -= 2
                    details["hardcoded_secrets"] = f"found in {py_file.name}"
                    break

    return {"score": max(0, score), "details": details}


def _calculate_trust_score(
    permissions_count: int,
    session_available: bool,
    tool_count: int,
) -> TrustScore:
    """Calculate trust score (separate from quality, 0-100).

    This measures environment trust, not code quality.
    """
    # Trusted operations (0-40 points)
    trusted_ops = min(permissions_count * 10, 40)  # 4 operations = max

    # Session availability (0-30 points)
    session_score = 30 if session_available else 5

    # Tool ecosystem (0-30 points)
    # Scale by number of available tools
    tool_score = min(tool_count * 3, 30)  # 10 tools = max

    total = trusted_ops + session_score + tool_score

    return TrustScore(
        trusted_operations=trusted_ops,
        session_availability=session_score,
        tool_ecosystem=tool_score,
        total=total,
        details={
            "permissions_count": permissions_count,
            "session_available": session_available,
            "tool_count": tool_count,
        },
    )


def _get_cached_metrics(cache_key: str) -> dict[str, Any] | None:
    """Get cached metrics if still valid."""
    if cache_key not in _metrics_cache:
        return None

    cached_metrics, cached_time = _metrics_cache[cache_key]
    if utc_now() - cached_time < timedelta(minutes=_CACHE_TTL_MINUTES):
        return cached_metrics
    return None


def _parse_metrics_history(metrics_history: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse Crackerjack metrics history into structured format.

    Missing metric types surface as ``None`` so downstream consumers can
    distinguish "no data" from "perfect score". When multiple entries
    share the same metric_type, the *first* one wins (subsequent rows
    are ignored); this preserves the historical stability guarantee
    that ``code_coverage`` reported by the latest run cannot "rewind"
    earlier historical coverage.
    """
    metrics: dict[str, Any] = {
        "lint_score": None,
        "security_score": None,
        "complexity_score": None,
    }

    for metric in metrics_history[:10]:
        metric_type = metric.get("metric_type")
        if metric_type not in {
            "code_coverage",
            "lint_score",
            "security_score",
            "complexity_score",
        }:
            continue
        if metrics.get(metric_type) is None:
            metrics[metric_type] = metric.get("metric_value", 0)

    return metrics


def _read_coverage_json(project_dir: Path) -> float:
    """Read coverage percentage from coverage.json.

    Prefers ``percent_statements_covered`` (what users actually mean by
    "test coverage") over ``percent_covered`` (line coverage). Falls back
    to line coverage if the statements field is absent.
    """
    import json

    coverage_json = project_dir / "coverage.json"
    if not coverage_json.exists():
        return 0

    with suppress(
        OSError,
        PermissionError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
    ):
        coverage_data = json.loads(coverage_json.read_text())
        totals = coverage_data.get("totals", {})
        statements = totals.get("percent_statements_covered")
        if statements is not None:
            return float(statements)
        return float(totals.get("percent_covered", 0))

    return 0


def _read_coverage_dotfile(project_dir: Path) -> float:
    """Read coverage percentage from .coverage (coverage.py SQLite database).

    Most projects generate .coverage via --cov-report=html or no explicit report
    flag, and never produce coverage.json. This fallback reads the raw .coverage
    file using the coverage Python API so the scorer works for those projects.

    Prefers statement coverage via the coverage API; falls back to line
    coverage if the statement metric is not reported.
    """
    coverage_file = project_dir / ".coverage"
    if not coverage_file.exists():
        return 0

    with suppress(Exception):
        from coverage import Coverage
        from coverage.results import Numbers

        cov = Coverage(data_file=str(coverage_file))
        cov.load()

        # Try the precise statement coverage first. ``cov.report(precision=2)``
        # historically returned a percent_covered value; newer coverage.py
        # returns a Numbers object that exposes per-metric percents.
        buf = io.StringIO()
        total = cov.report(file=buf, skip_empty=True, precision=2)
        # coverage.py >=7 reports a Numbers instance with statement percent
        # instead of the legacy line percent. Detect and prefer it.
        if isinstance(total, Numbers) and total.n_statements:
            pct_attr = getattr(total, "pc_statements", None)
            if isinstance(pct_attr, (int, float)):
                return round(float(pct_attr), 2)
            return 0.0
        if isinstance(total, (int, float)):
            return round(float(total), 2)
        return 0.0

    return 0


def _create_fallback_metrics() -> dict[str, Any]:
    """Last-resort fallback. Returns explicit unavailable markers, never perfect scores.

    Invoked only when every other tier (DB, reflection-DB, coverage-file, CLI) failed
    or was disabled. The ``unavailable: True`` flag is the explicit signal that no
    measurement occurred.
    """
    return {
        "code_coverage": None,
        "lint_score": None,
        "security_score": None,
        "complexity_score": None,
        "unavailable": True,
    }


async def _get_crackerjack_metrics(project_dir: Path | str) -> dict[str, Any]:
    """Get Crackerjack quality metrics with caching.

    Always returns a dict with all four scoring keys explicitly addressed.
    Missing measurements stay ``None``; the chain falls through CLI
    fallback + final synthesis instead of ever returning a partial dict.
    """
    # Ensure project_dir is a Path object
    if isinstance(project_dir, str):
        project_dir = Path(project_dir)
    cache_key = str(project_dir.resolve())

    # Check cache
    if cached := _get_cached_metrics(cache_key):
        return cached

    # Start with an empty dict populated key-by-key — never returns {}
    # early. Coverage files are a free signal even when Crackerjack is
    # unavailable so pick them up here. Use a truthy check so a literal
    # 0.0 reading (test fixtures + degenerate real projects) is still
    # treated as "no measurement," matching the pre-Task-9 behavior.
    metrics: dict[str, Any] = {}
    coverage_pct = _read_coverage_json(project_dir) or _read_coverage_dotfile(
        project_dir
    )
    if coverage_pct:
        metrics["code_coverage"] = coverage_pct

    # DB tier: pull the most recent historical values when Crackerjack
    # is available. Errors here are non-fatal because the CLI tier below
    # can still recover the missing keys.
    if CRACKERJACK_AVAILABLE:
        with suppress(ImportError, RuntimeError, ValueError, AttributeError, OSError):
            metrics_history = await get_quality_metrics_history(
                str(project_dir),
                None,
                days=1,
            )
            if metrics_history:
                metrics.update(_parse_metrics_history(metrics_history))

    SCORING_KEYS = frozenset(
        {"code_coverage", "lint_score", "security_score", "complexity_score"},
    )

    # CLI fallback tier. Always attempted when any scoring key is still
    # missing — including the partial-DB-history case the previous
    # implementation short-circuited past (final-review C1).
    if CRACKERJACK_AVAILABLE:
        missing = frozenset(k for k in SCORING_KEYS if metrics.get(k) is None)
        if missing:
            try:
                fallback = await try_crackerjack_cli(
                    project_dir=project_dir,
                    missing_metrics=missing,
                    timeout=30.0,
                    caller="consumer_chain",
                )
            except Exception:
                fallback = None
            if fallback:
                metrics.update(fallback)

    # Final synthesis tier. When ALL scoring keys are still missing we
    # persist the synthesized CrackerjackResult (so the MCP
    # ``crackerjack_metrics`` read path can render the unavailable
    # banner) and return the explicit ``_create_fallback_metrics``
    # sentinel. When only some keys are missing we keep any measured
    # values (coverage file, partial DB, partial CLI) and return a
    # partial dict without the ``unavailable: True`` flag — partial
    # truth beats masquerading-as-no-data.
    missing_keys = {k for k in SCORING_KEYS if metrics.get(k) is None}
    if missing_keys == SCORING_KEYS:
        # Every key missing — synthesize.
        synthesis = _create_fallback_metrics()
        if CRACKERJACK_AVAILABLE:
            try:
                from session_buddy.crackerjack_integration import (
                    CrackerjackIntegration,
                    get_crackerjack_integration as _get_global_integration,
                    synthesize_unavailable_result,
                )

                try:
                    db_path = _get_global_integration().db_path
                except Exception:
                    db_path = str(
                        Path.home()
                        / ".claude"
                        / "data"
                        / "crackerjack_integration.db",
                    )
                integration = CrackerjackIntegration(db_path=db_path)
                synthesized = synthesize_unavailable_result(str(project_dir))
                await integration._store_result(
                    f"cj_unavailable_{int(utc_now().timestamp() * 1000)}",
                    synthesized,
                )
            except Exception as exc:  # noqa: BLE001 - history-write best-effort
                # Previously swallowed silently (final-review I5). Log at
                # DEBUG so operators can debug the integration without
                # raising a hard warning on every CLI-disabled call.
                logger.debug(
                    "synthesis history write skipped",
                    extra={
                        "project_dir": str(project_dir),
                        "error": repr(exc),
                    },
                )
        return synthesis

    # Partial measurements — keep what we have, leave the rest as None.
    # Don't emit the synthesis flag for partial-truth output.
    for k in SCORING_KEYS:
        metrics.setdefault(k, None)
    return metrics


async def _get_type_coverage(
    project_dir: Path,
    crackerjack_metrics: dict[str, Any],
) -> float:
    """Get type coverage percentage.

    Try to extract from Crackerjack, fallback to manual check.
    """
    # First, try to get from Crackerjack metrics
    if "type_coverage" in crackerjack_metrics:
        return float(crackerjack_metrics["type_coverage"])

    # Fallback: Check for pyright/mypy configuration
    has_pyright = (project_dir / "pyrightconfig.json").exists()
    has_mypy = (project_dir / "mypy.ini").exists() or (
        project_dir / "pyproject.toml"
    ).exists()

    if has_pyright or has_mypy:
        # Estimate based on project structure
        # This is a rough estimate until we have actual coverage data
        return 70.0  # Assume decent coverage if type checker configured

    return 30.0  # Low default if no type checking


def _generate_recommendations_v2(
    code_quality: CodeQualityScore,
    project_health: ProjectHealthScore,
    dev_velocity: DevVelocityScore,
    security: SecurityScore,
    total_score: float,
) -> list[str]:
    """Generate actionable recommendations based on V2 scores."""
    recommendations = []

    # Overall score assessment
    if total_score >= 90:
        recommendations.append("⭐ Excellent code quality - maintain current standards")
    elif total_score >= 75:
        recommendations.append("✅ Good quality - minor improvements available")
    elif total_score >= 60:
        recommendations.append("⚠️ Moderate quality - focus on improvements below")
    else:
        recommendations.append("🚨 Quality needs attention - prioritize critical fixes")

    # Code quality recommendations
    if code_quality.test_coverage < 10:  # <67% coverage
        recommendations.append(
            f"🧪 Critical: Increase test coverage ({code_quality.details['coverage_pct']:.1f}% → target 80%+)",
        )
    elif code_quality.test_coverage < 13:  # <87% coverage
        recommendations.append(
            f"🧪 Add more tests ({code_quality.details['coverage_pct']:.1f}% coverage)",
        )

    if code_quality.lint_score < 8:  # <80% lint score
        recommendations.append("🔧 Address lint issues to improve code quality")

    if code_quality.type_coverage < 7:  # <70% type coverage
        recommendations.append("📝 Add type hints for better code safety")

    if code_quality.complexity_score < 3:  # High complexity
        recommendations.append("🔄 Refactor complex functions (reduce complexity)")

    # Project health recommendations
    if project_health.tooling_score < 10:
        recommendations.append(
            "🔨 Improve tooling setup (add lockfile, update dependencies)",
        )

    if project_health.maturity_score < 10:
        recommendations.append("📚 Enhance project maturity (add docs, tests, CI/CD)")

    # Dev velocity recommendations
    if dev_velocity.git_activity < 5:
        recommendations.append("💬 Improve commit quality (use conventional commits)")

    if dev_velocity.dev_patterns < 5:
        recommendations.append("🌿 Consider feature branch workflow and issue tracking")

    # Security recommendations
    if security.total < 8:
        recommendations.append("🔒 Address security issues (run bandit, check secrets)")

    return recommendations


# Backward compatibility: Export V1 calculator as well
from session_buddy.utils.quality_score_parser import (
    _extract_quality_scores,
    _generate_quality_trend_recommendations,
)

__all__ = [
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
