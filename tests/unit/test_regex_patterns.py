from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
import re

_UTILS_PACKAGE = types.ModuleType("session_buddy.utils")
_UTILS_PACKAGE.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("session_buddy.utils", _UTILS_PACKAGE)


class _ValidatedPattern:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


_CRACKERJACK_PACKAGE = types.ModuleType("crackerjack")
_CRACKERJACK_PACKAGE.__path__ = []  # type: ignore[attr-defined]
_CRACKERJACK_SERVICES = types.ModuleType("crackerjack.services")
_CRACKERJACK_SERVICES.__path__ = []  # type: ignore[attr-defined]
_CRACKERJACK_REGEX = types.ModuleType("crackerjack.services.regex_patterns")
_CRACKERJACK_REGEX.ValidatedPattern = _ValidatedPattern
sys.modules.setdefault("crackerjack", _CRACKERJACK_PACKAGE)
sys.modules.setdefault("crackerjack.services", _CRACKERJACK_SERVICES)
sys.modules.setdefault("crackerjack.services.regex_patterns", _CRACKERJACK_REGEX)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "regex_patterns.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.regex_patterns", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.regex_patterns", _MODULE)
_SPEC.loader.exec_module(_MODULE)

SAFE_PATTERNS = _MODULE.SAFE_PATTERNS


def test_safe_patterns_have_expected_keys() -> None:
    expected = {
        "python_code_block",
        "generic_code_block",
        "python_traceback",
        "python_exception",
        "javascript_error",
        "compile_error",
        "warning_pattern",
        "assertion_error",
        "import_error",
        "module_not_found",
        "file_not_found",
        "permission_denied",
        "network_error",
    }

    assert expected.issubset(SAFE_PATTERNS)


def test_safe_patterns_apply_to_sample_strings() -> None:
    python_code = SAFE_PATTERNS["python_code_block"]
    python_traceback = SAFE_PATTERNS["python_traceback"]
    python_exception = SAFE_PATTERNS["python_exception"]

    assert re.sub(
        python_code.pattern,
        python_code.replacement,
        "```python\nprint('hello')\n```",
        flags=python_code.flags,
    ) == "print('hello')"

    assert re.sub(
        python_traceback.pattern,
        python_traceback.replacement,
        "Traceback (most recent call last):\n  File test.py\nError: msg",
        flags=python_traceback.flags,
    ) == "<TRACEBACK_MASKED>"

    assert re.sub(
        python_exception.pattern,
        python_exception.replacement,
        "ValueError: invalid input",
    ) == "ValueError: <ERROR_MESSAGE_MASKED>"


def test_coverage_line_pattern_supports_decimals() -> None:
    """Regression: coverage_line must accept decimal percentages (e.g. 29.16%).

    Mahavishnu's pytest coverage output emits 'TOTAL 52464 37163 29.16%' which
    the legacy int-only regex `(\\d+)%` could not match.
    """
    pattern = SAFE_PATTERNS["coverage_line"]
    match = pattern.search("TOTAL 52464 37163 29.16%")
    assert match is not None
    assert match.group(1) == "29.16"
    assert float(match.group(1)) == 29.16

    # Integer percentages must still match.
    int_match = pattern.search("TOTAL 1000 50 95%")
    assert int_match is not None
    assert int_match.group(1) == "95"

    # coverage_summary must also support decimals (same source pattern).
    summary = SAFE_PATTERNS["coverage_summary"]
    summary_match = summary.search("TOTAL 52464 37163 29.16%")
    assert summary_match is not None
    assert summary_match.group(1) == "29.16"


def test_coverage_total_pattern_captures_stmts_missing_percent() -> None:
    """coverage_total must capture stmts, miss, and percent (as floats)."""
    pattern = SAFE_PATTERNS["coverage_total"]
    match = pattern.search("TOTAL 52464 37163 29.16%")
    assert match is not None
    stmts, missing, percent = match.groups()
    assert int(stmts) == 52464
    assert int(missing) == 37163
    assert float(percent) == 29.16
