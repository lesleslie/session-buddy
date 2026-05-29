from __future__ import annotations


def test_generate_quality_recommendations_low_score_minimal_context() -> None:
    from session_buddy.utils.quality.recommendations import (
        generate_quality_recommendations,
    )

    result = generate_quality_recommendations(
        score=10,
        project_context={},
        permissions_count=0,
        uv_available=False,
    )

    assert result == [
        "Session needs attention - multiple areas for improvement",
        "Consider adding tests to improve project structure",
        "Documentation would enhance project maturity",
        "No trusted operations yet - permissions will be granted on first use",
        "Install UV package manager for better dependency management",
    ]


def test_generate_quality_recommendations_mid_and_high_score_paths() -> None:
    from session_buddy.utils.quality.recommendations import (
        generate_quality_recommendations,
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

    assert mid == [
        "Good session health - minor optimizations available",
        "Documentation would enhance project maturity",
    ]
    assert high == [
        "Excellent session quality - maintain current practices",
        "Many trusted operations - consider reviewing for security",
    ]

