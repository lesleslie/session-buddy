______________________________________________________________________

## status: complete role: historical date: 2026-07-16 last_reviewed: 2026-07-16 superseded_by: null blocks_on: [] topic: convergence-control-plane

# Unified Roadmap: mcp-common + session-buddy

**Date**: 2025-10-28 (original)
**Reconciled**: 2026-07-15 (drift-sync)
**Duration**: 16 weeks (original scope)
**Status**: **Phases 1–2 done; Phases 3+ superseded** by PHASE3_PROPOSAL.md, REFACTORING_PLAN.md, PHASE4_MCP_TOOLS_IMPLEMENTATION.md, and related follow-on plans. <!-- legacy status — see YAML frontmatter -->

### Reconciliation Summary (2026-07-15)

| Week | Original Status | Reconciled Status | Notes |
|---|---|---|---|
| Week 1 | ✅ Complete | ✅ Done | ACB foundation + coverage ratchet operational |
| Week 2 | 🔄 In Progress | ✅ Done | HTTPClientAdapter validated with 11x perf improvement |
| Week 3 | ⏸ Not started | ⚠️ Superseded | HTTPClientAdapter extraction to mcp-common done via REFACTORING_PLAN phases |
| Week 4 | ⏸ Not started | ✅ Done | Phase 2.7 ACB DI at `session_buddy/di/` |
| Week 5 | ⏸ Not started | 🟡 Partial | Shutdown coordinator via `resource_cleanup.py` |
| Week 6 | ⏸ Not started | ⚠️ Superseded | Ecosystem rollout overtaken by PHASE4_MCP_TOOLS_IMPLEMENTATION.md |
| Weeks 7–16 | ⏸ Not started | ⚠️ SUPERSEDED | Template-based formatting, query interface, event-driven orchestration, etc. were superseded by PHASE3_PROPOSAL.md, REFACTORING_PLAN.md, and follow-on plans (see PLAN_INDEX.md for the full lineage). |

### Supersession Pointers

- **Weeks 7–8 (template formatting)** → superseded by `REFACTORING_PLAN.md` (Phase 5 extraction work).
- **Weeks 9–10 (universal query interface)** → superseded by `PHASE3_PROPOSAL.md` + `REFACTORING_PLAN.md` phase 4/5.
- **Weeks 11–12 (event-driven orchestration)** → superseded by `PHASE4_MCP_TOOLS_IMPLEMENTATION.md`.
- **Weeks 13–14 (cross-repo consolidation)** → superseded by `REFACTORING_PLAN.md` and `PHASE3_INTEGRATION_GUIDE.md`.
- **Weeks 15–16 (ecosystem docs + Phase 4 kickoff)** → superseded by `PHASE4_DEPLOYMENT_CHECKLIST.md`.

______________________________________________________________________

## Overview

This roadmap unifies two complementary efforts:

1. **mcp-common**: ACB-native foundation library for 9 MCP servers
1. **session-buddy**: Pilot implementation and validation sandbox

**Key Insight**: session-buddy validates patterns BEFORE they're extracted to mcp-common and rolled out ecosystem-wide.

______________________________________________________________________

## Work Stream Organization

### 🔴 Track 1: Critical Path (Serial)

**Focus**: Foundation validation in session-buddy → extraction to mcp-common → ecosystem rollout
**Timeline**: Weeks 1-6
**Priority**: HIGHEST - Blocks 8 other servers

### 🟡 Track 2: Parallel Infrastructure

**Focus**: Non-blocking infrastructure development
**Timeline**: Weeks 3-5
**Priority**: HIGH - Quality improvements

### 🟢 Track 3: Deep Integration

**Focus**: session-buddy advanced features
**Timeline**: Weeks 7-16
**Priority**: MEDIUM - After foundations complete

______________________________________________________________________

## Week-by-Week Roadmap

### Week 1: ACB Foundation ✅ **COMPLETE**

**Track 1 (Critical Path)**:

- [x] Install ACB framework (`uv add "acb>=0.25.2"`)
- [x] Enable coverage ratchet (35% minimum)
- [x] Enable complexity checks (remove C901 ignore)
- [x] Consolidate config.py with ACB config system (-558 lines)

**Track 2 (Parallel)**:

- [x] Create test stubs for 7 zero-coverage files

**Deliverables**:

- ✅ ACB framework operational
- ✅ Config system ACB-native
- ✅ Coverage ratchet protecting quality

**Status**: ✅ Complete | **Ecosystem Impact**: Foundation established

______________________________________________________________________

### Week 2: HTTPClientAdapter Validation 🔄 **IN PROGRESS**

**Track 1 (Critical Path)**:

- [x] Day 1-3: Implement HTTPClientAdapter in session-buddy ✅ **DONE**
- [ ] Day 4: Load testing (validate 11x performance improvement)
- [ ] Day 5: Integration testing with real traffic patterns
- [ ] Document HTTPClientAdapter patterns for extraction

**Track 2 (Parallel)**:

- [ ] Create testing utilities documentation
- [ ] Begin cache adapter replacement planning

**Deliverables**:

- ✅ HTTPClientAdapter implemented and validated
- ✅ Performance benchmarks showing 11x improvement
- ✅ Integration tests passing
- ✅ Pattern documentation for mcp-common extraction

**Status**: 60% complete | **Blockers**: None | **Risk**: 🟢 Low

**Critical**: This blocks mailgun critical bug fix (Week 3)

______________________________________________________________________

### Week 3: Extraction + Critical Bug Fixes

**Track 1 (Critical Path)**:

- [ ] Day 1: Extract HTTPClientAdapter to mcp-common
- [ ] Day 2-3: Fix mailgun-mcp critical bug (HTTP client reuse)
  - Apply HTTPClientAdapter
  - Validate 10x performance improvement
  - Integration testing
- [ ] Day 4-5: Apply HTTPClientAdapter to 5 remaining standalone servers
  - unifi-mcp (also fix tool registration)
  - excalidraw-mcp (also fix hardcoded paths)
  - opera-cloud-mcp
  - raindropio-mcp (already best practices, minimal changes)
  - session-buddy (already using it)

**Track 2 (Parallel)**:

- [ ] Extract RateLimiter from crackerjack/mcp/rate_limiter.py
- [ ] Begin security adapter development (sanitization/filtering)

**Deliverables**:

- ✅ mcp-common v2.0.0-alpha released (HTTPClientAdapter)
- ✅ mailgun-mcp bug fixed (critical)
- ✅ unifi-mcp tools working
- ✅ excalidraw-mcp portable
- ✅ RateLimiter in mcp-common

**Status**: Not started | **Blockers**: Week 2 completion | **Risk**: 🟡 Medium

**Impact**: 6/9 servers using HTTPClientAdapter, 3 critical bugs fixed

______________________________________________________________________

### Week 4: DI Validation + Pattern Extraction

**Track 1 (Critical Path)**:

- [ ] Day 1-3: session-buddy Phase 2.7 - ACB Dependency Injection
  - Implement `session_buddy/di/` package
  - Apply `depends.inject` to core, quality, tool layers
  - Migration: Server core, tool modules to DI
- [ ] Day 4: Validate DI patterns (70%+ coverage on new code)
- [ ] Day 5: Extract DI patterns to `mcp-common/di/`

**Track 2 (Parallel)**:

- [ ] Extract health check pattern to `mcp-common/health.py`
- [ ] Complete security adapters (SanitizerAdapter, FilterAdapter)
- [ ] Testing utilities finalization

**Deliverables**:

- ✅ Phase 2.7 complete (DI operational in session-buddy)
- ✅ mcp-common v2.0.0-beta released (HTTP, DI, health)
- ✅ Security adapters implemented
- ✅ Pattern documentation complete

**Status**: Not started | **Blockers**: Week 3 completion | **Risk**: 🟡 Medium

**Milestone 1 Gate**: Foundation Validated

- If passed → proceed with ecosystem rollout
- If failed → delay 1 week, fix issues

______________________________________________________________________

### Week 5: Ecosystem Rollout (Part 1)

**Track 1 (Critical Path)**:

- [ ] Day 1-2: Apply DI patterns to 3 standalone servers
  - mailgun-mcp (already using HTTPClientAdapter)
  - opera-cloud-mcp
  - raindropio-mcp (minor changes)
- [ ] Day 3-5: Extract shutdown coordinator pattern
  - Document graceful shutdown from session-buddy
  - Add to `mcp-common/lifecycle/shutdown.py`

**Track 2 (Parallel)**:

- [ ] Replicate health checks across ecosystem (2 hours per server)
- [ ] Replicate shutdown handlers (1 hour per server)

**Deliverables**:

- ✅ 3 servers with full mcp-common adoption
- ✅ Shutdown coordinator in mcp-common
- ✅ Health checks deployed ecosystem-wide

**Status**: Not started | **Blockers**: Week 4 completion | **Risk**: 🟢 Low

______________________________________________________________________

### Week 6: Ecosystem Rollout (Part 2)

**Track 1 (Critical Path)**:

- [ ] Day 1-3: Apply DI + patterns to remaining servers
  - unifi-mcp (most complex, thorough testing needed)
  - excalidraw-mcp (hybrid Python/TypeScript architecture)
  - session-buddy (already using patterns, formalize)
- [ ] Day 4: ACB-integrated servers enhancement
  - Add rate limiting to ACB mcp
  - Simplify crackerjack mcp (use shared RateLimiter)
  - FastBlocks inherits improvements via ACB
- [ ] Day 5: mcp-common v2.0.0 final release

**Deliverables**:

- ✅ All 9 servers using mcp-common v2.0.0
- ✅ Ecosystem health: 74 → 82 (+8 points)
- ✅ mcp-common v2.0.0 production release

**Status**: Not started | **Blockers**: Week 5 completion | **Risk**: 🟢 Low

**Milestone 2 Gate**: Ecosystem Adoption Complete

- If passed → session-buddy continues Phase 3
- If failed → extend ecosystem work 1 week

**🎉 MAJOR MILESTONE**: mcp-common foundation deployed across all 9 servers!

______________________________________________________________________

### Week 7-8: Template-Based Formatting (session-buddy Phase 3.1)

**Track 3 (Deep Integration)**:

- [ ] Week 7: Build `session_buddy/templates/` hierarchy
  - Register Jinja2 loader via DI
  - Document data models for template families
  - Create TemplateRenderer service
- [ ] Week 8: Migrate formatting functions to templates
  - 128 functions from `utils/server_helpers.py`
  - Quality engine formatters
  - Snapshot testing for regression detection

**Deliverables**:

- ✅ Template bundle with versioned naming
- ✅ Renderer service with caching
- ✅ 128 formatting functions replaced (-2,500 lines)
- ✅ Golden transcript tests passing

**Status**: Not started | **Blockers**: Week 6 completion | **Risk**: 🟢 Low

**LOC Impact**: 28,113 → 25,613 (-8.9%)

______________________________________________________________________

### Week 9-10: Universal Query Interface (session-buddy Phase 3.2)

**Track 3 (Deep Integration)**:

- [ ] Week 9: Create `session_buddy/adapters/database.py`
  - ACB query client with connection pooling
  - Query composition helpers
  - Parameterized builders
- [ ] Week 10: Convert query consumers
  - `reflection_tools.py` to query adapter
  - Analytics modules
  - Scoring helpers
  - Integration tests (80% coverage target)

**Deliverables**:

- ✅ ACB-backed query adapter operational
- ✅ Refactored modules using abstractions
- ✅ Query layer documentation
- ✅ Load test validation (10 concurrent queries)

**Status**: Not started | **Blockers**: Week 8 completion | **Risk**: 🟡 Medium

**LOC Impact**: 25,613 → 24,613 (-3.9%)

**Optional**: Evaluate DuckPGQ knowledge graph for mcp-common extraction

______________________________________________________________________

### Week 11-12: Event-Driven Orchestration (session-buddy Phase 3.3)

**Track 3 (Deep Integration)**:

- [ ] Week 11: Map lifecycle hooks to EventBus
  - Define canonical event schema
  - Implement `session_buddy/events.py`
  - EventBus configuration via DI
- [ ] Week 12: Refactor listeners
  - Server core subscribers
  - Monitoring module subscribers
  - Notification module subscribers
  - Add telemetry and replay protection

**Deliverables**:

- ✅ Event schema catalog
- ✅ EventBus configuration
- ✅ Subscriber modules with metrics
- ✅ End-to-end scenario tests

**Status**: Not started | **Blockers**: Week 10 completion | **Risk**: 🟡 Medium

**LOC Impact**: 24,613 → 22,613 (-8.1%)

**ACB Integration**: 0/10 → 9/10 ✅

______________________________________________________________________

### Week 13-14: Test Coverage Sprint (session-buddy Phase 4)

**Track 3 (Excellence)**:

- [ ] Week 13: Systematic test creation
  - All untested paths
  - Integration test expansion
  - Property-based tests (Hypothesis)
- [ ] Week 14: Advanced testing
  - Performance regression tests
  - Chaos engineering tests
  - Mutation testing validation

**Deliverables**:

- ✅ Test coverage: 34.6% → 70%
- ✅ Integration test suite expanded
- ✅ Chaos tests validating resilience
- ✅ Mutation testing score 80%+

**Status**: Not started | **Blockers**: Week 12 completion | **Risk**: 🟢 Low

**Quality Impact**: Coverage ratchet protecting improvements

______________________________________________________________________

### Week 15-16: Performance & Polish (session-buddy Phase 4)

**Track 3 (Excellence)**:

- [ ] Week 15: ACB-enabled optimizations
  - Performance profiling
  - Query optimization
  - Cache tuning
  - Memory optimization
- [ ] Week 16: Production preparation
  - Documentation updates
  - API reference completion
  - Deployment guide
  - Production monitoring setup

**Deliverables**:

- ✅ Performance improved (+30-50%)
- ✅ Test coverage: 70% → 85%+
- ✅ Quality score: 71 → 95 (+24)
- ✅ Production deployment ready
- ✅ Comprehensive documentation

**Status**: Not started | **Blockers**: Week 14 completion | **Risk**: 🟢 Low

**🎉 FINAL MILESTONE**: World-class reference implementation achieved!

______________________________________________________________________

## Milestone Checkpoints

### Milestone 1: Foundation Validated (End of Week 4)

**Gate Criteria**:

- [ ] HTTPClientAdapter proven (11x performance improvement)
- [ ] DI patterns validated (Phase 2.7 complete)
- [ ] mcp-common v2.0.0-beta released
- [ ] session-buddy using mcp-common adapters

**Go/No-Go Decision**:

- **GO**: Proceed with ecosystem rollout (Weeks 5-6)
- **NO-GO**: Delay 1 week, fix issues, re-evaluate

**Status**: Scheduled for end of Week 4

______________________________________________________________________

### Milestone 2: Ecosystem Adoption (End of Week 6)

**Gate Criteria**:

- [ ] All 9 servers using HTTPClientAdapter
- [ ] mailgun-mcp critical bug fixed (10x improvement)
- [ ] unifi-mcp tools registered and working
- [ ] excalidraw-mcp portable (no hardcoded paths)
- [ ] Health checks + shutdown replicated
- [ ] mcp-common v2.0.0 final release

**Go/No-Go Decision**:

- **GO**: session-buddy continues Phase 3 (deep integration)
- **NO-GO**: Extend ecosystem rollout, address issues

**Status**: Scheduled for end of Week 6

**Success Metrics**:

- Ecosystem health: 74 → 82 (+8)
- Critical bugs: 3 → 0
- Servers with rate limiting: 2/9 → 9/9
- Code duplication: Reduced by 50%

______________________________________________________________________

### Milestone 3: Excellence (End of Week 16)

**Gate Criteria**:

- [ ] session-buddy quality score 95/100
- [ ] Test coverage 85%+
- [ ] ACB integration 9/10
- [ ] Production ready
- [ ] Performance optimized (+30-50%)
- [ ] Documentation complete

**Success Criteria**:

- session-buddy is world-class reference implementation
- Ecosystem average quality 85/100
- Zero critical issues across all 9 servers

**Status**: Scheduled for end of Week 16

______________________________________________________________________

## Success Metrics Dashboard

### Current State (Week 2)

```
session-buddy Metrics
├── Quality Score:        71/100
├── Architecture:         90/100 ✅ (modular)
├── ACB Integration:      0/10 (Phase 2.7 starting)
├── Test Coverage:        34.6%
└── LOC:                  28,113

mcp-common Metrics
├── Status:               Week 2 Days 1-3
├── HTTPClientAdapter:    🔄 Implementing
├── Version:              Not yet released
└── Servers Adopted:      0/9 (session-buddy testing)

Ecosystem Metrics
├── Average Health:       74/100
├── Critical Bugs:        3 (mailgun, unifi, excalidraw)
├── Servers w/ Rate Limit: 2/9 (22%)
└── Code Duplication:     High
```

### Target State (Week 6 - Milestone 2)

```
session-buddy Metrics
├── Quality Score:        75/100 (+4)
├── Architecture:         90/100 (maintained)
├── ACB Integration:      6/10 (+6)
├── Test Coverage:        55% (+20.4pp)
└── LOC:                  28,113 (stable)

mcp-common Metrics
├── Status:               v2.0.0 released
├── HTTPClientAdapter:    ✅ Production
├── Version:              2.0.0
└── Servers Adopted:      9/9 (100%)

Ecosystem Metrics
├── Average Health:       82/100 (+8)
├── Critical Bugs:        0 (-3)
├── Servers w/ Rate Limit: 9/9 (100%)
└── Code Duplication:     -50%
```

### Final State (Week 16 - Milestone 3)

```
session-buddy Metrics
├── Quality Score:        95/100 (+24 from start)
├── Architecture:         95/100 (+5)
├── ACB Integration:      9/10 (+9)
├── Test Coverage:        85%+ (+50.4pp)
└── LOC:                  16,000 (-43%)

mcp-common Metrics
├── Status:               v2.0.0 stable
├── HTTPClientAdapter:    ✅ Proven
├── Version:              2.0.0
└── Servers Adopted:      9/9 (100%)

Ecosystem Metrics
├── Average Health:       85/100 (+11)
├── Critical Bugs:        0
├── Servers w/ Rate Limit: 9/9 (100%)
└── Code Duplication:     -70%
```

______________________________________________________________________

## Risk Matrix

| Risk | Probability | Impact | Week | Mitigation |
|------|------------|---------|------|------------|
| **HTTPClientAdapter validation delays** | 🟡 Medium (20%) | 🔴 High | 2 | Load testing, fallback plan |
| **mailgun fix complications** | 🟢 Low (10%) | 🔴 High | 3 | HTTPClientAdapter proven first |
| **DI pattern complexity** | 🟡 Medium (25%) | 🟡 Medium | 4 | Simple cases first, gradual adoption |
| **Ecosystem rollout issues** | 🟢 Low (15%) | 🟡 Medium | 5-6 | Incremental per-server rollout |
| **Template migration bugs** | 🟡 Medium (20%) | 🟢 Low | 7-8 | Snapshot testing, gradual migration |
| **Query interface regressions** | 🟡 Medium (25%) | 🟡 Medium | 9-10 | Output validation, benchmarking |
| **Event system race conditions** | 🟡 Medium (30%) | 🔴 High | 11-12 | Parallel run, extensive testing |
| **Test coverage timeline pressure** | 🟢 Low (15%) | 🟢 Low | 13-14 | Coverage is additive, can extend |
| **Overall Risk** | 🟢 **LOW** | - | - | Clear critical path, proven patterns |

### Risk Mitigation Strategy

**General Principles**:

1. ✅ **Feature flags** - All major changes behind toggles
1. ✅ **Parallel running** - Old and new systems during transition
1. ✅ **Incremental migration** - Never big-bang changes
1. ✅ **70%+ coverage** - All new code before merge
1. ✅ **Monitoring** - Metrics for all critical paths

**Emergency Rollback**:

- Git tags: `phase-1-complete`, `phase-2-complete`, etc.
- Toggle flags: `ACB_CONFIG`, `ACB_CACHE`, `ACB_DI`, etc.
- Original code retained 4 weeks post-migration

______________________________________________________________________

## Key Decisions & Trade-offs

### Decision 1: session-buddy as Pilot

**Rationale**: Most complex standalone server, best validation for ecosystem patterns
**Trade-off**: Delays session-buddy Phase 3 work, but de-risks ecosystem
**Status**: ✅ Validated - Phase 2 completion proves value

### Decision 2: Extract Health Checks + Shutdown

**Rationale**: "Extra" work proves production-ready patterns
**Trade-off**: Adds 2-3 hours per server to rollout (acceptable)
**Status**: ✅ Approved - Integration into unified plan (Week 4-5)

### Decision 3: Templates in session-buddy Only

**Rationale**: Unique to session-buddy's verbose output formatting needs
**Trade-off**: Not extracted to mcp-common (may reconsider later)
**Status**: 🟡 Deferred - Evaluate at Week 9 for potential extraction

### Decision 4: DuckPGQ as Optional Feature

**Rationale**: Knowledge graph pattern valuable but not universal
**Trade-off**: Not all 9 servers need semantic memory
**Status**: 🟡 Optional - Document as optional mcp-common feature (Week 9)

______________________________________________________________________

## Dependencies External to Plan

### Python Ecosystem

- **Python 3.13+** - Required for modern type hints
- **ACB ≥0.25.2** - Framework foundation
- **DuckDB** - Already in dependencies (no new deps)

### Development Tools

- **UV package manager** - For ACB and dependency management
- **pytest + hypothesis** - Testing framework
- **crackerjack** - Code quality enforcement

### Infrastructure

- **Git 2.30+** - For worktree features
- **8GB+ RAM** - For embedding model
- **10GB+ disk** - For test data

**Status**: ✅ All dependencies already met in session-buddy

______________________________________________________________________

## Communication & Coordination

### Weekly Progress Updates

**Schedule**: Every Friday EOD
**Format**: Markdown report with metrics dashboard
**Distribution**: Architecture Council (you)

**Template**:

```markdown
## Week N Progress Report
**Track 1 (Critical Path)**: [Status]
**Track 2 (Parallel)**: [Status]
**Track 3 (Deep Work)**: [Status]

**Completed**:
- [x] Item 1
- [x] Item 2

**In Progress**:
- [ ] Item 3

**Blocked**:
- [ ] Item 4 (blocker: reason)

**Metrics**:
- Quality: X/100 (ΔY)
- Coverage: X% (ΔY%)
- LOC: X (ΔY)

**Next Week Focus**: [Priority items]
```

### Milestone Reviews

**Schedule**: End of Weeks 4, 6, 16
**Format**: Architecture Council review session
**Deliverables**: Go/No-Go decision, risk reassessment

### Risk Reviews

**Schedule**: Bi-weekly (every 2 weeks)
**Format**: Risk matrix update
**Action**: Update mitigation strategies

______________________________________________________________________

## Appendices

### Appendix A: HTTPClientAdapter Validation Criteria

**Checklist for Week 2 Day 4-5**:

- [ ] Load test: 100 concurrent requests sustained
- [ ] Performance: 11x improvement vs. baseline
- [ ] Connection pooling: Max 100 connections, reuse validated
- [ ] Error handling: Timeout, retry, circuit breaker tested
- [ ] Memory: No leaks over 1000 requests
- [ ] Integration: Works with all session-buddy MCP tools

### Appendix B: DI Pattern Validation Criteria

**Checklist for Week 4**:

- [ ] Simple injection: Logger, config working
- [ ] Complex injection: Database, HTTP client working
- [ ] Override pattern: Tests can mock dependencies
- [ ] Lifecycle: Async resources properly managed
- [ ] Coverage: ≥70% on new DI code
- [ ] Documentation: Pattern guide with examples

### Appendix C: Ecosystem Rollout Checklist

**Per Server**:

- [ ] Install mcp-common≥2.0.0
- [ ] Register package with ACB (`register_pkg`)
- [ ] Migrate to MCPBaseSettings
- [ ] Use HTTPClientAdapter via DI
- [ ] Add rate limiting (`@rate_limit`)
- [ ] Add security adapters (sanitize/filter)
- [ ] Write tests with DI mocking
- [ ] Add ServerPanels for UI
- [ ] Update documentation
- [ ] Health checks operational
- [ ] Graceful shutdown working

### Appendix D: Quality Gates

**Every Commit**:

- [ ] Ruff, Pyright, Bandit passing
- [ ] Complexity ≤15 per function
- [ ] Coverage maintained or increased
- [ ] Tests passing

**Every Phase**:

- [ ] Architecture review
- [ ] Performance benchmarks
- [ ] Integration tests passing
- [ ] Documentation updated

______________________________________________________________________

**Document Status**: 🟢 **ACTIVE ROADMAP**
**Next Review**: End of Week 4 (Milestone 1)
**Owner**: Architecture Council
**Last Updated**: 2025-10-28
