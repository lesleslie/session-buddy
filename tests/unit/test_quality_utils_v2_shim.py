from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def test_quality_utils_v2_is_alias_for_quality_scoring() -> None:
    utils_package = types.ModuleType("session_buddy.utils")
    utils_package.__path__ = []  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils"] = utils_package

    quality_score_parser_path = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "utils"
        / "quality_score_parser.py"
    )
    quality_score_parser_spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.quality_score_parser",
        quality_score_parser_path,
    )
    assert (
        quality_score_parser_spec is not None
        and quality_score_parser_spec.loader is not None
    )
    quality_score_parser = importlib.util.module_from_spec(quality_score_parser_spec)
    sys.modules["session_buddy.utils.quality_score_parser"] = quality_score_parser
    setattr(utils_package, "quality_score_parser", quality_score_parser)
    quality_score_parser_spec.loader.exec_module(quality_score_parser)

    quality_scoring_path = (
        Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "quality_scoring.py"
    )
    quality_scoring_spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.quality_scoring",
        quality_scoring_path,
    )
    assert quality_scoring_spec is not None and quality_scoring_spec.loader is not None
    quality_scoring = importlib.util.module_from_spec(quality_scoring_spec)
    sys.modules["session_buddy.utils.quality_scoring"] = quality_scoring
    setattr(utils_package, "quality_scoring", quality_scoring)
    quality_scoring_spec.loader.exec_module(quality_scoring)

    quality_utils_v2_path = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "utils"
        / "quality_utils_v2.py"
    )
    quality_utils_v2_spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.quality_utils_v2",
        quality_utils_v2_path,
    )
    assert quality_utils_v2_spec is not None and quality_utils_v2_spec.loader is not None
    quality_utils_v2 = importlib.util.module_from_spec(quality_utils_v2_spec)
    sys.modules["session_buddy.utils.quality_utils_v2"] = quality_utils_v2
    setattr(utils_package, "quality_utils_v2", quality_utils_v2)
    quality_utils_v2_spec.loader.exec_module(quality_utils_v2)

    assert sys.modules["session_buddy.utils.quality_utils_v2"] is quality_scoring
    assert quality_utils_v2.calculate_quality_score_v2 is quality_scoring.calculate_quality_score_v2
