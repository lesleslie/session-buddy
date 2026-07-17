"""C1 sweep: prepend YAML frontmatter to session-buddy loose docs.

User-authorized. Mechanical. Mirrors mahavishnu's _orphan_sweep_C1_2.py but
adapts to session-buddy's flat docs/ + docs/plans/ structure (no 6-store layout).

Reads each file, prepends a uniform frontmatter block + adds a trailing HTML
legacy comment on the existing Status line so the validator's --allow-nonstandard
mode stays green.
"""
from pathlib import Path

FM_TEMPLATE = (
    "---\n"
    "status: {status}\n"
    "role: {role}\n"
    "date: 2026-07-16\n"
    "last_reviewed: 2026-07-16\n"
    "superseded_by: null\n"
    "blocks_on: []\n"
    "topic: {topic}\n"
    "---\n"
    "\n"
)

REPO_ROOT = Path("/Users/les/Projects/session-buddy")


# Per-file explicit assignments. Filename-keyed. Anything not listed falls into
# DEFAULT_BY_SUBDIR plus filename heuristics.
ASSIGNMENTS: dict[str, tuple[str, str, str]] = {
    # ----- docs/plans/ (active plans) -----
    "docs/plans/2026-07-16-checkpoint-async-refactor.md":
        ("shipped", "implementation", "persistence"),
    # NOTE: docs/plans/PLAN_INDEX.md is generated; excluded.

    # ----- Loose docs (status: complete, role: historical is the common default) -----
    "docs/MIGRATION_STRATEGY.md": ("complete", "historical", "oneiric-config"),
    "docs/PATHWAY_1_IMPLEMENTATION_PLAN.md": ("complete", "historical", "mcp-design"),
    "docs/PHASE2_3_SINGLETON_CLEANUP_PLAN.md": ("complete", "historical", "architecture"),
    "docs/PHASE3_ARCHITECTURE.md": ("complete", "historical", "architecture"),
    "docs/PHASE3_INTEGRATION_GUIDE.md": ("complete", "historical", "architecture"),
    "docs/PHASE3_README.md": ("complete", "historical", "architecture"),
    "docs/PHASE4_MCP_TOOLS_IMPLEMENTATION.md": ("complete", "historical", "mcp-design"),
    "docs/REFACTORING_PLAN.md": ("complete", "historical", "architecture"),
    "docs/REFACTORING_PHASE3_PLAN.md": ("complete", "historical", "architecture"),
    "docs/REFACTORING_PHASE4_PLAN.md": ("complete", "historical", "architecture"),
    "docs/ROLLOUT_PLAN.md": ("complete", "historical", "architecture"),
    "docs/TEST_PLAN.md": ("complete", "historical", "architecture"),
    "docs/test_improvement_plan.md": ("complete", "historical", "architecture"),
    "docs/test_improvements_documentation.md": ("complete", "historical", "architecture"),
    "docs/TEST_IMPROVEMENTS.md": ("complete", "historical", "architecture"),
    "docs/UNIFIED_ROADMAP.md": ("complete", "historical", "convergence-control-plane"),
    "docs/AKOSHA_API_REFERENCE.md": ("complete", "canonical", "mcp-design"),
    "docs/AKOSHA_USER_GUIDE.md": ("complete", "canonical", "mcp-design"),
    "docs/API_KEY_SETUP.md": ("complete", "canonical", "auth"),
    "docs/ADMIN_SHELL_TRACKING_QUICKREF.md": ("complete", "canonical", "architecture"),
    "docs/CLAUDE_QWEN_CONFIG_SYNC.md": ("complete", "canonical", "oneiric-config"),
    "docs/CRACKERJACK.md": ("complete", "canonical", "adapter-architecture"),
    "docs/CRACKERJACK_METRICS_MONITORING.md": ("complete", "canonical", "observability"),
    "docs/CRACKERJACK_MONITORING_IMPLEMENTATION.md": ("complete", "implementation", "observability"),
    "docs/CRACKERJACK_MONITORING_QUICK_START.md": ("complete", "canonical", "observability"),
    "docs/DEAD_CODE_DETECTION.md": ("complete", "canonical", "architecture"),
    "docs/DEAD_CODE_TOOLS_COMPARISON.md": ("complete", "canonical", "architecture"),
    "docs/DI_USAGE_GUIDE.md": ("complete", "canonical", "architecture"),
    "docs/ENCRYPTION_IMPLEMENTATION.md": ("complete", "canonical", "auth"),
    "docs/FASTMCP_UNHASHABLE_BUG.md": ("complete", "historical", "mcp-design"),
    "docs/JWT_AUTHENTICATION.md": ("complete", "canonical", "auth"),
    "docs/JWT_AUTH_QUICKREF.md": ("complete", "canonical", "auth"),
    "docs/MEMORI_INTEGRATION_PATHWAYS.md": ("complete", "historical", "adapter-architecture"),
    "docs/ONEIRIC_MCP_ANALYSIS.md": ("complete", "historical", "oneiric-config"),
    "docs/POOL_IMPLEMENTATION.md": ("complete", "historical", "architecture"),
    "docs/PROMETHEUS_METRICS.md": ("complete", "canonical", "observability"),
    "docs/PROTOBUF_USAGE_ANALYSIS.md": ("complete", "historical", "architecture"),
    "docs/QUALITY_TRACKING_PROPOSAL.md": ("complete", "historical", "lifecycle"),
    "docs/README.md": ("active", "canonical", "lifecycle"),
    "docs/SECURITY_AUDIT_2025-12-31.md": ("complete", "historical", "auth"),
    "docs/SESSION_ANALYTICS.md": ("complete", "canonical", "observability"),
    "docs/SESSION_ANALYTICS_IMPLEMENTATION.md": ("complete", "historical", "observability"),
    "docs/SESSION_ANALYTICS_QUICKREF.md": ("complete", "canonical", "observability"),
    "docs/SESSION_ID_PATTERNS.md": ("complete", "canonical", "architecture"),
    "docs/SYNC_IMPLEMENTATION.md": ("complete", "historical", "storage-consolidation"),
    "docs/TEST_OPTIMIZATION_GUIDE.md": ("complete", "canonical", "architecture"),
    "docs/ULID_MIGRATION_ANALYSIS.md": ("complete", "historical", "storage-consolidation"),
    "docs/UNHASHABLE_TYPE_BUG_RESOLUTION.md": ("complete", "historical", "mcp-design"),
    "docs/causal_chains.md": ("complete", "canonical", "observability"),
    "docs/collaborative_filtering.md": ("complete", "canonical", "learning-pipeline"),
    "docs/hooks_system.md": ("complete", "canonical", "architecture"),
    "docs/intelligence_engine.md": ("complete", "canonical", "learning-pipeline"),
    "docs/natural_language_intent_detection.md": ("complete", "canonical", "learning-pipeline"),

    # ----- Loose root-level .md -----
    "ARCHITECTURE.md": ("active", "canonical", "architecture"),
    "CHANGELOG.md": ("active", "canonical", "lifecycle"),
    "CHECKPOINT_2025-02-10.md": ("complete", "historical", "persistence"),
    "ANALYTICS_ENGINE_USAGE.md": ("complete", "canonical", "observability"),
    "PHASE3_PROPOSAL.md": ("complete", "historical", "architecture"),
    "PHASE4_DEPLOYMENT_CHECKLIST.md": ("complete", "historical", "architecture"),
    "QUICKSTART.md": ("active", "canonical", "lifecycle"),
    "THIRD_PARTY_NOTICES.md": ("active", "canonical", "lifecycle"),
    "TRIAGE_REPORT_153_FAILURES.md": ("complete", "historical", "quality"),
    "collaborative_filtering_quick_reference.md": ("complete", "canonical", "learning-pipeline"),
    "PROMETHEUS_QUICK_START.md": ("complete", "canonical", "observability"),
    "CONTRIBUTING.md": ("active", "canonical", "lifecycle"),
    "PROMPTING_ADAPTER_QUICK_REFERENCE.md": ("complete", "canonical", "mcp-design"),
    "RULES.md": ("active", "canonical", "lifecycle"),
    "scripts/TAXONOMY_INITIALIZATION_QUICKSTART.md": ("complete", "canonical", "architecture"),
    "tests/README.md": ("active", "canonical", "lifecycle"),
    "tests/README_CRACKERJACK_TESTS.md": ("active", "canonical", "lifecycle"),
    "session_buddy/trailing_period_removal_summary.md": ("complete", "historical", "architecture"),

    # ----- docs/api/ -----
    "docs/api/SESSION_BUDDY_API.md": ("complete", "canonical", "mcp-design"),

    # ----- docs/design/ -----
    "docs/design/DI_CONTAINER.md": ("complete", "canonical", "architecture"),
    "docs/design/INTERRUPTION_MANAGER.md": ("complete", "canonical", "architecture"),
    "docs/design/MULTI_PROJECT_COORDINATOR.md": ("complete", "canonical", "architecture"),
    "docs/design/REFLECTION_DATABASE.md": ("complete", "canonical", "memory-architecture"),
    "docs/design/REFLECTION_SYSTEM.md": ("complete", "canonical", "memory-architecture"),
    "docs/design/SERVERLESS_MODE.md": ("complete", "canonical", "storage-consolidation"),
    "docs/design/SESSION_LIFECYCLE.md": ("complete", "canonical", "lifecycle"),
    "docs/design/WORKTREE_MANAGER.md": ("complete", "canonical", "worktree-management"),

    # ----- docs/developer/ -----
    "docs/developer/EXTENDING.md": ("complete", "canonical", "lifecycle"),
    "docs/developer/MCP_TOOL_DEVELOPMENT.md": ("complete", "canonical", "mcp-design"),

    # ----- docs/features/ -----
    "docs/features/AUTO_LIFECYCLE.md": ("complete", "canonical", "lifecycle"),
    "docs/features/INSIGHTS_CAPTURE.md": ("complete", "canonical", "learning-pipeline"),
    "docs/features/INTELLIGENCE_QUICK_START.md": ("complete", "canonical", "learning-pipeline"),
    "docs/features/SELECTIVE_AUTO_STORE.md": ("complete", "canonical", "lifecycle"),
    "docs/features/TOKEN_OPTIMIZATION.md": ("complete", "canonical", "lifecycle"),
    "docs/features/hooks_and_causal_chains.md": ("complete", "canonical", "architecture"),

    # ----- docs/grafana/ -----
    "docs/grafana/SETUP.md": ("complete", "canonical", "observability"),

    # ----- docs/guides/ -----
    "docs/guides/operational-modes-architecture.md": ("complete", "canonical", "architecture"),
    "docs/guides/operational-modes.md": ("complete", "canonical", "architecture"),

    # ----- docs/initialization/ -----
    "docs/initialization/TAXONOMY_INITIALIZATION.md": ("complete", "canonical", "architecture"),

    # ----- docs/integration/ -----
    "docs/integration/phase3_intelligence_integration_complete.md": ("complete", "historical", "learning-pipeline"),

    # ----- docs/migrations/ -----
    "docs/migrations/ONEIRIC_MIGRATION_COMPLETE.md": ("complete", "historical", "oneiric-config"),
    "docs/migrations/ONEIRIC_MIGRATION_PLAN.md": ("complete", "historical", "oneiric-config"),
    "docs/migrations/README.md": ("complete", "canonical", "oneiric-config"),
    "docs/migrations/V3_TO_V4_MIGRATION_GUIDE.md": ("complete", "historical", "oneiric-config"),
    "docs/migrations/health-check-implementation.md": ("complete", "historical", "lifecycle"),
    "docs/migrations/http-client-adapter.md": ("complete", "historical", "mcp-design"),

    # ----- docs/monitoring/ -----
    "docs/monitoring/MONITORING.md": ("complete", "canonical", "observability"),

    # ----- docs/performance/ -----
    "docs/performance/embedding_cache_results.md": ("complete", "historical", "observability"),
    "docs/performance/embedding_quantization_results.md": ("complete", "historical", "observability"),
    "docs/performance/hnsw_benchmark_results.md": ("complete", "historical", "observability"),

    # ----- docs/realtime/ -----
    "docs/realtime/IMPLEMENTATION_SUMMARY.md": ("complete", "historical", "mcp-design"),
    "docs/realtime/WEBSOCKET_DELIVERY_REPORT.md": ("complete", "historical", "mcp-design"),
    "docs/realtime/WEBSOCKET_SERVER.md": ("complete", "canonical", "mcp-design"),

    # ----- docs/reference/ -----
    "docs/reference/API_REFERENCE.md": ("complete", "canonical", "mcp-design"),
    "docs/reference/MCP_SCHEMA_REFERENCE.md": ("complete", "canonical", "mcp-design"),
    "docs/reference/service-dependencies.md": ("complete", "canonical", "architecture"),
    "docs/reference/slash-command-shortcuts.md": ("complete", "canonical", "mcp-design"),

    # ----- docs/security/ -----
    "docs/security/PHASE1_COVERAGE_SUMMARY.md": ("complete", "historical", "auth"),
    "docs/security/PHASE1_TEST_COVERAGE_ANALYSIS.md": ("complete", "historical", "auth"),
    "docs/security/SECURITY_ARCHITECTURE.md": ("complete", "canonical", "auth"),

    # ----- docs/user/ -----
    "docs/user/CONFIGURATION.md": ("active", "canonical", "oneiric-config"),
    "docs/user/DEPLOYMENT.md": ("active", "canonical", "lifecycle"),
    "docs/user/MCP_TOOLS_REFERENCE.md": ("active", "canonical", "mcp-design"),
    "docs/user/QUICK_START.md": ("active", "canonical", "lifecycle"),

    # ----- Second-pass additions for files not in C1.1 sweep -----
    "docs/JSON_SCHEMA_REFERENCE.md": ("complete", "canonical", "mcp-design"),
    "docs/design/SKILL_METRICS_ARCHITECTURE.md": ("complete", "canonical", "learning-pipeline"),
    "docs/design/SKILL_METRICS_AGGREGATION.md": ("complete", "canonical", "learning-pipeline"),
    "docs/design/SKILL_METRICS_IMPLEMENTATION.md": ("complete", "canonical", "learning-pipeline"),
    "docs/developer/ARCHITECTURE.md": ("complete", "canonical", "architecture"),
    "docs/developer/INTEGRATION.md": ("complete", "canonical", "architecture"),
    "docs/developer/PARAMETER_VALIDATION.md": ("complete", "canonical", "architecture"),
    "docs/developer/TESTING-QUICK-REFERENCE.md": ("complete", "canonical", "lifecycle"),
    "docs/developer/TESTING.md": ("complete", "canonical", "lifecycle"),
    "docs/developer/QUALITY_SCORING_V2.md": ("complete", "canonical", "lifecycle"),
    "docs/features/AI_INTEGRATION.md": ("complete", "canonical", "learning-pipeline"),
    "docs/api/WEBSOCKET_API.md": ("complete", "canonical", "mcp-design"),
    "session_buddy/analytics/README.md": ("complete", "canonical", "observability"),

    # ----- Plugin / slash command templates (carry session-buddy-plugin lifecycle) -----
    "commands/session-buddy-end.md": ("active", "canonical", "plugin-standardization"),
    "commands/session-buddy-start.md": ("active", "canonical", "plugin-standardization"),
    "commands/session-buddy-checkpoint.md": ("active", "canonical", "plugin-standardization"),
    "templates/session/checkpoint.md": ("active", "canonical", "plugin-standardization"),
    "templates/session/handoff.md": ("active", "canonical", "plugin-standardization"),
}


# Files / directories excluded from normalization.
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "docs/archive",
    "docs/schemas",  # the new schema docs carry their own logical marker
    ".pytest_cache",
    ".complexipy_cache",
    ".claude-plugin",
    ".claude",
    ".superpowers",
    "playwright-mcp",
    "settings",
    ".playwright-mcp",
}

EXCLUDED_PATHS = {
    "docs/schemas/document-frontmatter-v1.md",
    "docs/schemas/topic-vocabulary-v1.md",
    "docs/plans/PLAN_INDEX.md",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",  # top-level README (project, not docs)
}


def add_legacy_comment(text: str) -> str:
    """Append a trailing HTML legacy comment on the first 'Status:' / '**Status**' line.

    Mirrors _orphan_sweep_C1_2.py — only touches the first match.
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("**Status") and "Status" in stripped:
            original = stripped.rstrip("\n")
            if "<!-- legacy status" not in original:
                lines[i] = original + "  <!-- legacy status — see YAML frontmatter -->\n"
            break
    return "".join(lines)


def collect_targets() -> list[Path]:
    """Walk repo, return every .md under docs/ or repo root that should be normalized."""
    paths: list[Path] = []
    for p in REPO_ROOT.rglob("*.md"):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if rel in EXCLUDED_PATHS:
            continue
        if any(rel.startswith(d.rstrip("/") + "/") for d in EXCLUDED_DIRS):
            continue
        # Skip top-level project README — let the team add frontmatter themselves.
        if rel == "README.md":
            continue
        # Skip the 2 schema files (carrying generator), and PLAN_INDEX (generated artifact)
        paths.append(p)
    return paths


def main() -> None:
    targets = collect_targets()
    results: list[tuple[str, str, str, str]] = []
    skipped: list[str] = []
    for path in targets:
        rel = path.relative_to(REPO_ROOT).as_posix()
        original = path.read_text(encoding="utf-8")
        if original.lstrip().startswith("---\n"):
            skipped.append(f"already-framed: {rel}")
            continue
        assignment = ASSIGNMENTS.get(rel)
        if assignment is None:
            skipped.append(f"no assignment: {rel}")
            continue
        status, role, topic = assignment
        frontmatter = FM_TEMPLATE.format(status=status, role=role, topic=topic)
        body_with_comment = add_legacy_comment(original)
        new_content = frontmatter + body_with_comment
        path.write_text(new_content, encoding="utf-8")
        results.append((rel, status, role, topic))

    print(f"\nEdited {len(results)} files:")
    for rel, st, rl, tp in results:
        print(f"  {rel}: status={st} role={rl} topic={tp}")
    print(f"\nSkipped {len(skipped)} files:")
    for line in skipped:
        print(f"  {line}")


if __name__ == "__main__":
    main()
