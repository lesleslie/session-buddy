from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_QUALITY_RECOMMENDATIONS_PATH = (
    Path(__file__).resolve().parents[2]
    / "session_buddy"
    / "utils"
    / "quality"
    / "recommendations.py"
)
_QUALITY_RECOMMENDATIONS_SPEC = importlib.util.spec_from_file_location(
    "session_buddy.utils.quality.recommendations",
    _QUALITY_RECOMMENDATIONS_PATH,
)
assert (
    _QUALITY_RECOMMENDATIONS_SPEC is not None
    and _QUALITY_RECOMMENDATIONS_SPEC.loader is not None
)
_QUALITY_RECOMMENDATIONS_MODULE = importlib.util.module_from_spec(
    _QUALITY_RECOMMENDATIONS_SPEC
)
sys.modules[_QUALITY_RECOMMENDATIONS_SPEC.name] = _QUALITY_RECOMMENDATIONS_MODULE
_QUALITY_RECOMMENDATIONS_SPEC.loader.exec_module(_QUALITY_RECOMMENDATIONS_MODULE)
generate_quality_recommendations = (
    _QUALITY_RECOMMENDATIONS_MODULE.generate_quality_recommendations
)


def test_generate_quality_recommendations_covers_all_branches() -> None:
    low = generate_quality_recommendations(
        score=10,
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
    docs_only = generate_quality_recommendations(
        score=90,
        project_context={"has_docs": False},
        permissions_count=1,
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
    assert docs_only == [
        "Excellent session quality - maintain current practices",
        "Consider adding tests to improve project structure",
        "Documentation would enhance project maturity",
    ]
