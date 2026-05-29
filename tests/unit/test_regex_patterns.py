from __future__ import annotations

import re


def test_safe_patterns_have_expected_keys() -> None:
    from session_buddy.utils.regex_patterns import SAFE_PATTERNS

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
    from session_buddy.utils.regex_patterns import SAFE_PATTERNS

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
