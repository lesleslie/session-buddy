from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "session_buddy"
    / "utils"
    / "quality_score_parser.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "session_buddy.utils.quality_score_parser",
    _MODULE_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

_analyze_quality_trend = _MODULE._analyze_quality_trend
_ensure_default_recommendations = _MODULE._ensure_default_recommendations
_extract_quality_scores = _MODULE._extract_quality_scores
_extract_score_from_content = _MODULE._extract_score_from_content
_extract_score_from_metadata = _MODULE._extract_score_from_metadata
_generate_quality_trend_recommendations = _MODULE._generate_quality_trend_recommendations
_get_intelligence_error_result = _MODULE._get_intelligence_error_result
_get_time_based_recommendations = _MODULE._get_time_based_recommendations
_parse_score_text = _MODULE._parse_score_text


def test_parse_score_text_variants() -> None:
    assert _parse_score_text("85/100") == 85.0
    assert _parse_score_text("0.85") == 85.0
    assert _parse_score_text("85") == 85.0
    assert _parse_score_text("1.1") == 1.1
    assert _parse_score_text("-0.5") is None
    assert _parse_score_text("101") is None
    assert _parse_score_text("85/not-a-number") is None
    assert _parse_score_text("not-a-score") is None


def test_extract_score_from_content() -> None:
    assert _extract_score_from_content("quality score: 92/100") == 92.0
    assert _extract_score_from_content("quality score: 0.75 passed") == 75.0
    assert _extract_score_from_content("quality score:") is None
    assert _extract_score_from_content("no score here") is None
    assert _extract_score_from_content(None) is None


def test_extract_score_from_metadata() -> None:
    assert _extract_score_from_metadata({"metadata": {"quality_score": 88}}) == 88.0
    assert _extract_score_from_metadata({"metadata": {"quality_score": 120}}) is None
    assert _extract_score_from_metadata({"metadata": {"other": 1}}) is None
    assert _extract_score_from_metadata({"metadata": None}) is None


def test_extract_quality_scores_prefers_content_then_metadata_and_skips_malformed() -> None:
    reflections = [
        {"content": "quality score: 90/100", "metadata": {"quality_score": 10}},
        {"content": "no score", "metadata": {"quality_score": 80}},
        {"content": "quality score: not-a-score", "metadata": {"quality_score": 70}},
        {"content": "no score", "metadata": {}},
        {"content": 123, "metadata": {"quality_score": 60}},
        object(),
    ]

    assert _extract_quality_scores(reflections) == [90.0, 80.0, 70.0]


def test_analyze_quality_trend_branches() -> None:
    trend, insights, improving = _analyze_quality_trend([90])
    assert trend == "insufficient_data"
    assert improving is False
    assert insights == ["Not enough data to analyze trend"]

    trend, insights, improving = _analyze_quality_trend([80, 81, 79])
    assert trend == "stable"
    assert improving is True
    assert insights == ["Initial quality baseline established"]

    trend, insights, improving = _analyze_quality_trend(
        [80, 81, 79, 80, 81, 80, 81, 79, 80, 81]
    )
    assert trend == "stable"
    assert improving is True
    assert any("stable" in item.lower() for item in insights)
    assert any("maintaining" in item.lower() for item in insights)

    trend, insights, improving = _analyze_quality_trend([50, 55, 60, 70, 80, 95, 96])
    assert trend == "improving"
    assert improving is True
    assert any("improving" in item.lower() for item in insights)
    assert any("excellent" in item.lower() for item in insights)

    trend, insights, improving = _analyze_quality_trend([95, 90, 85, 80, 75, 60, 50])
    assert trend == "declining"
    assert improving is False
    assert any("declining" in item.lower() for item in insights)
    assert any("focus" in item.lower() for item in insights)


def test_generate_quality_trend_recommendations_branches() -> None:
    assert _generate_quality_trend_recommendations([]) == [
        "📊 Start tracking quality metrics for trend analysis"
    ]

    critical = _generate_quality_trend_recommendations([40, 42, 39])
    assert critical[0].startswith("🚨 Critical")
    assert any("pair programming" in item.lower() for item in critical)

    caution = _generate_quality_trend_recommendations([60, 62, 64])
    assert caution[0].startswith("⚠️ Quality below target")

    good = _generate_quality_trend_recommendations([75, 80, 85])
    assert good[0].startswith("✅ Good quality")
    assert any("fine-tune" in item.lower() for item in good)

    excellent = _generate_quality_trend_recommendations([90, 92, 95])
    assert excellent[0].startswith("⭐ Excellent quality")
    assert any("positive trend" in item.lower() for item in excellent)

    declining = _generate_quality_trend_recommendations([80, 75, 70])
    assert any("declining trend" in item.lower() for item in declining)

    short_run = _generate_quality_trend_recommendations([80, 82])
    assert len(short_run) == 3
    assert not any("trend" in item.lower() for item in short_run)


def test_time_based_and_default_recommendations() -> None:
    assert any("morning" in item.lower() for item in _get_time_based_recommendations(8))
    assert any("afternoon" in item.lower() for item in _get_time_based_recommendations(13))
    assert any("evening" in item.lower() for item in _get_time_based_recommendations(18))
    assert any("late session" in item.lower() for item in _get_time_based_recommendations(2))

    assert _ensure_default_recommendations([]) == [
        "🎯 Focus on current development goals",
        "📝 Keep documentation updated",
        "🧪 Maintain test coverage",
        "🔍 Regular code quality checks",
    ]
    existing = ["keep going"]
    assert _ensure_default_recommendations(existing) is existing


def test_intelligence_error_result() -> None:
    result = _get_intelligence_error_result(RuntimeError("boom"))

    assert result["success"] is False
    assert "boom" in result["error"]
    assert result["fallback_mode"] is True
    assert isinstance(result["recommendations"], list)
