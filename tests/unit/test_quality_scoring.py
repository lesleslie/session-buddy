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
