from __future__ import annotations

import importlib
import sys


def test_file_utils_re_exports_filesystem_helpers() -> None:
    module = importlib.import_module("session_buddy.utils.file_utils")

    assert hasattr(module, "_cleanup_temp_files")
    assert hasattr(module, "_cleanup_session_logs")
    assert hasattr(module, "_cleanup_uv_cache")


def test_logging_utils_re_exports_logging_api() -> None:
    module = importlib.import_module("session_buddy.utils.logging_utils")

    assert hasattr(module, "SessionLogger")
    assert hasattr(module, "get_session_logger")


def test_quality_utils_v2_aliases_quality_scoring_module() -> None:
    module = importlib.import_module("session_buddy.utils.quality_utils_v2")
    scoring = importlib.import_module("session_buddy.utils.quality_scoring")

    assert module is scoring
    assert sys.modules["session_buddy.utils.quality_utils_v2"] is scoring

