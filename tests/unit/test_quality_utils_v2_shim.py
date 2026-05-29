from __future__ import annotations

import importlib
import sys


def test_quality_utils_v2_is_alias_for_quality_scoring() -> None:
    sys.modules.pop("session_buddy.utils.quality_utils_v2", None)
    quality_utils_v2 = importlib.import_module("session_buddy.utils.quality_utils_v2")
    from session_buddy.utils import quality_scoring

    assert sys.modules["session_buddy.utils.quality_utils_v2"] is quality_scoring
    assert quality_utils_v2 is quality_scoring
