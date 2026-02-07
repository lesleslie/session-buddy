"""Compatibility shim for quality_utils_v2 renamed to quality_scoring."""

# Re-export everything from quality_scoring as quality_utils_v2
# Re-export the module itself
import sys

from session_buddy.utils.quality_scoring import *  # noqa: F401, F403

sys.modules["session_buddy.utils.quality_utils_v2"] = sys.modules[
    "session_buddy.utils.quality_scoring"
]  # noqa: F401
