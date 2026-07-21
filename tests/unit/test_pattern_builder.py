from __future__ import annotations


def test_pattern_mappings_builder_chain() -> None:
    from session_buddy.utils.crackerjack.pattern_builder import PatternMappingsBuilder

    builder = PatternMappingsBuilder()
    mappings = (
        builder.add_test_patterns()
        .add_lint_patterns()
        .add_security_patterns()
        .add_quality_patterns()
        .add_progress_patterns()
        .add_coverage_patterns()
        .add_misc_patterns()
        .build()
    )

    assert mappings["pytest_result"] == "pytest_result"
    assert mappings["pyright_error"] == "mypy_error"
    assert mappings["bandit_issue"] == "bandit_finding"
    assert mappings["quality_score"] == "quality_score"
    assert mappings["progress_indicator"] == "progress_indicator"
    assert mappings["coverage_line"] == "coverage_summary"
    assert mappings["coverage_total"] == "coverage_total"
    assert mappings["git_commit"] == "git_commit_hash"
    assert builder.build() == mappings


def test_coverage_total_pattern_matches_mahavishnu_output() -> None:
    """coverage_total regex must match mahavishnu's 'TOTAL N M P%' summary row."""
    from session_buddy.utils.crackerjack.pattern_builder import PatternMappingsBuilder
    from session_buddy.utils.regex_patterns import SAFE_PATTERNS

    mappings = PatternMappingsBuilder().add_coverage_patterns().build()
    pattern = SAFE_PATTERNS[mappings["coverage_total"]]

    match = pattern.search("TOTAL 52464 37163 29.16%")
    assert match is not None
    stmts, missing, percent = match.groups()
    assert int(stmts) == 52464
    assert int(missing) == 37163
    assert float(percent) == 29.16

    # Integer form must also match (regression guard).
    int_match = pattern.search("TOTAL 1000 50 95%")
    assert int_match is not None
    assert int_match.group(3) == "95"
