from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_QUALITY_RECOMMENDATIONS_PATH = (
    Path(__file__).resolve().parents[2]
    / "session_buddy"
    / "utils"
    / "quality"
    / "recommendations.py"
)
_QUALITY_RECOMMENDATIONS_SPEC = spec_from_file_location(
    "session_buddy.utils.quality.recommendations",
    _QUALITY_RECOMMENDATIONS_PATH,
)
assert (
    _QUALITY_RECOMMENDATIONS_SPEC is not None
    and _QUALITY_RECOMMENDATIONS_SPEC.loader is not None
)
_quality_recommendations = module_from_spec(_QUALITY_RECOMMENDATIONS_SPEC)
sys.modules[_QUALITY_RECOMMENDATIONS_SPEC.name] = _quality_recommendations
_QUALITY_RECOMMENDATIONS_SPEC.loader.exec_module(_quality_recommendations)

generate_quality_recommendations = _quality_recommendations.generate_quality_recommendations


def test_generate_quality_recommendations_low_score_and_missing_project_data() -> None:
    recommendations = generate_quality_recommendations(
        score=25,
        project_context={},
        permissions_count=0,
        uv_available=False,
    )

    assert recommendations == [
        "Session needs attention - multiple areas for improvement",
        "Consider adding tests to improve project structure",
        "Documentation would enhance project maturity",
        "No trusted operations yet - permissions will be granted on first use",
        "Install UV package manager for better dependency management",
    ]


def test_generate_quality_recommendations_mid_score_and_security_review() -> None:
    recommendations = generate_quality_recommendations(
        score=60,
        project_context={"has_tests": True, "has_docs": True},
        permissions_count=6,
        uv_available=True,
    )

    assert recommendations == [
        "Good session health - minor optimizations available",
        "Many trusted operations - consider reviewing for security",
    ]


def test_generate_quality_recommendations_high_score_with_partial_project_context() -> None:
    recommendations = generate_quality_recommendations(
        score=90,
        project_context={"has_tests": True},
        permissions_count=1,
        uv_available=True,
    )

    assert recommendations == [
        "Excellent session quality - maintain current practices",
        "Documentation would enhance project maturity",
    ]
