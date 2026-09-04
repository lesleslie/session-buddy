"""Tests for session_buddy.utils.quality.recommendations.

Covers the quality-score-driven recommendation generator that produces
human-readable improvement hints from session metrics, project context,
permission counts, and tool availability.
"""

from __future__ import annotations

from typing import Any

import pytest

from session_buddy.utils.quality.recommendations import (
    generate_quality_recommendations,
)


def _ctx(
    *,
    has_tests: bool = True,
    has_docs: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    """Helper that builds a project_context dict with sensible defaults."""
    base: dict[str, Any] = {"has_tests": has_tests, "has_docs": has_docs}
    base.update(extra)
    return base


# -----------------------------------------------------------------------------
# Score tier branching: <50, 50..74, >=75
# -----------------------------------------------------------------------------


def test_score_below_50_emits_attention_message() -> None:
    recs = generate_quality_recommendations(
        score=0,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    assert recs[0] == "Session needs attention - multiple areas for improvement"


def test_score_just_below_50_emits_attention_message() -> None:
    recs = generate_quality_recommendations(
        score=49,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    assert recs[0] == "Session needs attention - multiple areas for improvement"


def test_score_at_50_emits_good_health_message() -> None:
    recs = generate_quality_recommendations(
        score=50,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    assert recs[0] == "Good session health - minor optimizations available"


def test_score_in_middle_range_emits_good_health_message() -> None:
    recs = generate_quality_recommendations(
        score=70,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    assert recs[0] == "Good session health - minor optimizations available"


def test_score_just_below_75_emits_good_health_message() -> None:
    recs = generate_quality_recommendations(
        score=74,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    assert recs[0] == "Good session health - minor optimizations available"


def test_score_at_75_emits_excellent_message() -> None:
    recs = generate_quality_recommendations(
        score=75,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    assert recs[0] == "Excellent session quality - maintain current practices"


def test_score_above_75_emits_excellent_message() -> None:
    recs = generate_quality_recommendations(
        score=100,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    assert recs[0] == "Excellent session quality - maintain current practices"


# -----------------------------------------------------------------------------
# Project context branching
# -----------------------------------------------------------------------------


def test_missing_has_tests_key_triggers_test_recommendation() -> None:
    ctx: dict[str, Any] = {}  # no has_tests, no has_docs
    recs = generate_quality_recommendations(
        score=90,
        project_context=ctx,
        permissions_count=3,
        uv_available=True,
    )
    msg = "Consider adding tests to improve project structure"
    assert msg in recs


def test_has_tests_false_triggers_test_recommendation() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(has_tests=False),
        permissions_count=3,
        uv_available=True,
    )
    msg = "Consider adding tests to improve project structure"
    assert msg in recs


def test_has_tests_true_omits_test_recommendation() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(has_tests=True),
        permissions_count=3,
        uv_available=True,
    )
    msg = "Consider adding tests to improve project structure"
    assert msg not in recs


def test_missing_has_docs_key_triggers_doc_recommendation() -> None:
    ctx: dict[str, Any] = {"has_tests": True}  # has_docs missing
    recs = generate_quality_recommendations(
        score=90,
        project_context=ctx,
        permissions_count=3,
        uv_available=True,
    )
    msg = "Documentation would enhance project maturity"
    assert msg in recs


def test_has_docs_false_triggers_doc_recommendation() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context={"has_tests": True, "has_docs": False},
        permissions_count=3,
        uv_available=True,
    )
    msg = "Documentation would enhance project maturity"
    assert msg in recs


def test_has_docs_true_omits_doc_recommendation() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(has_docs=True),
        permissions_count=3,
        uv_available=True,
    )
    msg = "Documentation would enhance project maturity"
    assert msg not in recs


# -----------------------------------------------------------------------------
# Permissions branching: ==0 vs 1..5 vs >5
# -----------------------------------------------------------------------------


def test_zero_permissions_trusts_message() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(),
        permissions_count=0,
        uv_available=True,
    )
    msg = "No trusted operations yet - permissions will be granted on first use"
    assert msg in recs


def test_one_permission_omits_perm_messages() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(),
        permissions_count=1,
        uv_available=True,
    )
    none_msg = "No trusted operations yet - permissions will be granted on first use"
    many_msg = "Many trusted operations - consider reviewing for security"
    assert none_msg not in recs
    assert many_msg not in recs


def test_five_permissions_omits_perm_messages() -> None:
    """Boundary: ==5 is still in the safe zone, only >5 triggers the warning."""
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(),
        permissions_count=5,
        uv_available=True,
    )
    none_msg = "No trusted operations yet - permissions will be granted on first use"
    many_msg = "Many trusted operations - consider reviewing for security"
    assert none_msg not in recs
    assert many_msg not in recs


def test_six_permissions_triggers_many_message() -> None:
    """Boundary: >5 (so 6) triggers the security-review message."""
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(),
        permissions_count=6,
        uv_available=True,
    )
    msg = "Many trusted operations - consider reviewing for security"
    assert msg in recs


def test_large_permissions_count_triggers_many_message() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(),
        permissions_count=42,
        uv_available=True,
    )
    msg = "Many trusted operations - consider reviewing for security"
    assert msg in recs


# -----------------------------------------------------------------------------
# uv_available branching
# -----------------------------------------------------------------------------


def test_uv_unavailable_triggers_install_message() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=False,
    )
    msg = "Install UV package manager for better dependency management"
    assert msg in recs


def test_uv_available_omits_install_message() -> None:
    recs = generate_quality_recommendations(
        score=90,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    msg = "Install UV package manager for better dependency management"
    assert msg not in recs


# -----------------------------------------------------------------------------
# Integration: all conditions fire together
# -----------------------------------------------------------------------------


def test_all_conditions_fire_produces_five_recommendations() -> None:
    recs = generate_quality_recommendations(
        score=10,
        project_context={},  # no has_tests, no has_docs
        permissions_count=0,
        uv_available=False,
    )
    assert len(recs) == 5
    assert recs[0] == "Session needs attention - multiple areas for improvement"
    assert "Consider adding tests to improve project structure" in recs
    assert "Documentation would enhance project maturity" in recs
    assert (
        "No trusted operations yet - permissions will be granted on first use" in recs
    )
    assert "Install UV package manager for better dependency management" in recs


def test_perfect_inputs_produce_single_recommendation() -> None:
    """Score >=75 + tests + docs + perm in [1,5] + uv available -> one rec only."""
    recs = generate_quality_recommendations(
        score=95,
        project_context=_ctx(has_tests=True, has_docs=True),
        permissions_count=3,
        uv_available=True,
    )
    assert recs == ["Excellent session quality - maintain current practices"]
    assert len(recs) == 1


def test_score_attention_with_perfect_project_produces_one_rec() -> None:
    """Score <50 alone emits only the score-tier message — no project/perm/uv recs."""
    recs = generate_quality_recommendations(
        score=10,
        project_context=_ctx(has_tests=True, has_docs=True),
        permissions_count=3,
        uv_available=True,
    )
    assert len(recs) == 1
    assert recs[0] == "Session needs attention - multiple areas for improvement"


def test_unknown_project_context_keys_are_ignored() -> None:
    """Extra keys in project_context must not break or affect recommendations."""
    recs = generate_quality_recommendations(
        score=95,
        project_context={
            "has_tests": True,
            "has_docs": True,
            "weird_key": "ignored",
            "another_key": [1, 2, 3],
        },
        permissions_count=3,
        uv_available=True,
    )
    assert recs == ["Excellent session quality - maintain current practices"]


@pytest.mark.parametrize(
    ("score", "expected_first"),
    [
        (0, "Session needs attention - multiple areas for improvement"),
        (49, "Session needs attention - multiple areas for improvement"),
        (50, "Good session health - minor optimizations available"),
        (74, "Good session health - minor optimizations available"),
        (75, "Excellent session quality - maintain current practices"),
        (200, "Excellent session quality - maintain current practices"),
    ],
)
def test_score_branching_parametric(
    score: int,
    expected_first: str,
) -> None:
    recs = generate_quality_recommendations(
        score=score,
        project_context=_ctx(),
        permissions_count=3,
        uv_available=True,
    )
    assert recs[0] == expected_first
