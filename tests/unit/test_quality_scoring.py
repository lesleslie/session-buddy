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
