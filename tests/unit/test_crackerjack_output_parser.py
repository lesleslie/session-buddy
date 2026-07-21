"""Regression tests for Crackerjack output parser coverage handling.

These tests pin the parser to correctly handle decimal coverage percentages
emitted by mahavishnu's pytest invocation (e.g. ``TOTAL 52464 37163 29.16%``).
"""

from __future__ import annotations

from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser


_MAHAVISHNU_COVERAGE_OUTPUT = """\
Name                          Stmts   Miss  Cover
---------------------------------------------------------
session_buddy/core/foo.py         10      2    80%
session_buddy/core/bar.py         20      5    75%
---------------------------------------------------------
TOTAL                          52464  37163  29.16%
"""


def test_coverage_total_decimal_extracted_as_float() -> None:
    """The TOTAL row's percent must be parsed as float, not int."""
    parser = CrackerjackOutputParser()
    parsed_data, _insights = parser.parse_output(
        command="coverage",
        stdout=_MAHAVISHNU_COVERAGE_OUTPUT,
        stderr="",
    )

    assert parsed_data["coverage_summary"]["total_coverage"] == 29.16


def test_coverage_total_integer_still_works() -> None:
    """Integer percentages (e.g. 95%) must continue to parse correctly."""
    output = """\
TOTAL 1000 50 95%
"""
    parser = CrackerjackOutputParser()
    parsed_data, _insights = parser.parse_output(
        command="coverage",
        stdout=output,
        stderr="",
    )

    assert parsed_data["coverage_summary"]["total_coverage"] == 95.0


def test_pytest_coverage_decimal_extracted_as_float() -> None:
    """The pytest_coverage variant must also surface a float percent."""
    output = """\
TOTAL 52464 37163 29.16%
"""
    parser = CrackerjackOutputParser()
    parsed_data, _insights = parser.parse_output(
        command="test",
        stdout=output,
        stderr="",
    )

    assert parsed_data["coverage_summary"]["total_coverage"] == 29.16
