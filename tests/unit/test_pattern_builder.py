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
    assert mappings["git_commit"] == "git_commit_hash"
    assert builder.build() == mappings
