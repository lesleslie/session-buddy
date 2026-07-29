"""Compatibility shim for quality_utils_v2 renamed to quality_scoring."""

# Re-export everything from quality_scoring as quality_utils_v2
# Re-export the module itself
import sys

from session_buddy.utils.quality_scoring import (
    CodeQualityScore,
    DevVelocityScore,
    ProjectHealthScore,
    QualityScoreV2,
    SecurityScore,
    TrustScore,
    calculate_quality_score_v2,
)

__all__ = [
    "CodeQualityScore",
    "DevVelocityScore",
    "ProjectHealthScore",
    "QualityScoreV2",
    "SecurityScore",
    "TrustScore",
    "calculate_quality_score_v2",
]

sys.modules["session_buddy.utils.quality_utils_v2"] = sys.modules[
    "session_buddy.utils.quality_scoring"
]
