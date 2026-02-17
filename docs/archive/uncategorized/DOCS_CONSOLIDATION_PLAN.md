# Session-Buddy Documentation Consolidation Plan

**Track 2 of Ecosystem Improvement Plan**

**Status**: Phase 1: Audit Complete
**Created**: 2026-02-09
**Target**: Root directory ≤ 10 markdown files

______________________________________________________________________

## Phase 1: Audit Results ✅

### Current Documentation State

**Total Markdown Files**: 2,667 files
**Root Markdown Files**: 30 files
**Repository Size**: 1.5GB

### Root Directory Files (30 total)

#### Core Files (Keep in Root - 5 files)
- `README.md` - Project overview (23K)
- `CLAUDE.md` - Development guidelines (24K)
- `CONTRIBUTING.md` - Contribution guidelines (11K)
- `CHANGELOG.md` - Version history (14K)
- `QUICKSTART.md` - [TO BE CREATED] Quickstart guide

#### Implementation Reports (Move to Archive - 8 files)
- `AGENT_REVIEWS_SUMMARY.md` → `docs/archive/implementation-plans/`
- `AKOSHA_COMPLETE_SUMMARY.md` → `docs/archive/implementation-plans/`
- `AKOSHA_SETUP_COMPLETE.md` → `docs/archive/phase-completions/`
- `PHASE_0_COMPLETE.md` → `docs/archive/phase-completions/`
- `PHASES_1_2_3_COMPLETE.md` → `docs/archive/phase-completions/`
- `PERFORMANCE_ANALYSIS_PHASE1_SECURITY.md` → `docs/archive/implementation-plans/`
- `PROMETHEUS_METRICS_IMPLEMENTATION.md` → `docs/archive/implementation-plans/`
- `UTILS_REFACTORING_PLAN.md` → `docs/archive/implementation-plans/`

#### Session/Checkpoint Files (Move to Archive - 4 files)
- `SESSION_TRACKER_IMPLEMENTATION.md` → `docs/archive/session-summaries/`
- `SESSION_TRACKER_QUICKREF.md` → `docs/archive/session-summaries/`
- `SESSION_TRACKING_E2E_TEST.md` → `docs/archive/checkpoints/`
- `SESSION_TRACKING_TEST_REPORT.md` → `docs/archive/checkpoints/`

#### Test Reports (Move to Archive - 2 files)
- `TESTING_SUMMARY.md` → `docs/archive/test-reports/`
- `TEST_SUITE_README.md` → `docs/archive/test-reports/`

#### Feature Documentation (Consolidate - 3 files)
- `ENGRAM_FEATURE_1_QUERY_CACHE.md` → Consolidate into `docs/features/`
- `ENGRAM_FEATURE_2_NGRAM_FINGERPRINT.md` → Consolidate into `docs/features/`
- `AI_MAESTRO_FEATURE_STATUS.md` → Consolidate into `docs/features/`

#### Research & Analysis (Move to Archive - 4 files)
- `AKOSHA_SYNC_IMPLEMENTATION_PLAN.md` → `docs/archive/implementation-plans/`
- `CRITICAL_REVIEW_REMEDIATION_PLAN.md` → `docs/archive/implementation-plans/`
- `DEPENDENCY_ANALYSIS.md` → `docs/archive/implementation-plans/`
- `ADMIN_SHELL_TRACKING_MCP_TOOLS.md` → `docs/archive/implementation-plans/`

#### Miscellaneous (Move to Archive - 3 files)
- `manual_shell_test.md` → `docs/archive/test-reports/`
- `NOTES.md` → `docs/archive/uncategorized/`
- `QWEN.md` → `docs/archive/uncategorized/`

#### Special Documentation (Evaluate - 2 files)
- `AGENTS.md` (2.7K) - Keep or consolidate into docs
- `RULES.md` (15K) - Keep or consolidate into docs

### Existing Archive Structure

```
docs/archive/
├── integration-docs/
├── implementation-plans/
├── weekly-progress/
├── completed-migrations/
├── checkpoints/
├── superseded-plans/
├── oneiric-migration/
├── phase-completions/
├── acb-historical/
├── uncategorized/
├── session-handoffs/
└── session-summaries/
```

**Good News**: Archive structure already exists! No need to create directories.

______________________________________________________________________

## Phase 2: File Migration Plan

### Target State

**Root Directory**: 5-10 markdown files maximum
- Core files only (README, CLAUDE, CONTRIBUTING, CHANGELOG, QUICKSTART, ARCHITECTURE)
- All implementation reports moved to archive
- All test reports moved to archive
- All session/checkpoint files moved to archive

### Migration Commands

```bash
cd /Users/les/Projects/session-buddy

# Implementation reports
mv AGENT_REVIEWS_SUMMARY.md docs/archive/implementation-plans/
mv AKOSHA_COMPLETE_SUMMARY.md docs/archive/implementation-plans/
mv AKOSHA_SETUP_COMPLETE.md docs/archive/phase-completions/
mv AKOSHA_SYNC_IMPLEMENTATION_PLAN.md docs/archive/implementation-plans/
mv CRITICAL_REVIEW_REMEDIATION_PLAN.md docs/archive/implementation-plans/
mv DEPENDENCY_ANALYSIS.md docs/archive/implementation-plans/
mv PERFORMANCE_ANALYSIS_PHASE1_SECURITY.md docs/archive/implementation-plans/
mv PROMETHEUS_METRICS_IMPLEMENTATION.md docs/archive/implementation-plans/
mv UTILS_REFACTORING_PLAN.md docs/archive/implementation-plans/

# Phase completions
mv PHASE_0_COMPLETE.md docs/archive/phase-completions/
mv PHASES_1_2_3_COMPLETE.md docs/archive/phase-completions/

# Session tracking
mv SESSION_TRACKER_IMPLEMENTATION.md docs/archive/session-summaries/
mv SESSION_TRACKER_QUICKREF.md docs/archive/session-summaries/
mv SESSION_TRACKING_E2E_TEST.md docs/archive/checkpoints/
mv SESSION_TRACKING_TEST_REPORT.md docs/archive/checkpoints/

# Test reports
mv TESTING_SUMMARY.md docs/archive/test-reports/
mv TEST_SUITE_README.md docs/archive/test-reports/
mv manual_shell_test.md docs/archive/test-reports/

# Feature docs (consolidate or archive)
mv ENGRAM_FEATURE_1_QUERY_CACHE.md docs/archive/implementation-plans/
mv ENGRAM_FEATURE_2_NGRAM_FINGERPRINT.md docs/archive/implementation-plans/
mv AI_MAESTRO_FEATURE_STATUS.md docs/archive/implementation-plans/

# Miscellaneous
mv NOTES.md docs/archive/uncategorized/
mv QWEN.md docs/archive/uncategorized/
```

### Files Requiring Decision

**AGENTS.md** (2.7K):
- Option 1: Keep in root (agent configuration reference)
- Option 2: Move to `docs/reference/agents.md`
- **Recommendation**: Keep in root (frequently referenced)

**RULES.md** (15K):
- Option 1: Keep in root (coding standards)
- Option 2: Consolidate into `docs/developer/standards.md`
- **Recommendation**: Move to `docs/developer/coding-standards.md`

______________________________________________________________________

## Phase 3: Documentation Creation

### 3.1 Create QUICKSTART.md (Root)

**Based on**: Mahavishnu QUICKSTART.md format
**Length**: 5-minute progressive guide
**Structure**:
- Level 1: Basic Session Management (1 minute) ✅
- Level 2: Memory Integration (2 minutes) 🧠
- Level 3: Integration with Mahavishnu (2 minutes) 🔄

**Content Draft**:

```markdown
# Session-Buddy Quickstart (5 minutes)

Get started with Session-Buddy in 5 minutes with this progressive guide.

---

## Level 1: Basic Session Management (1 minute) ✅

**Goal**: Start your first session

```bash
# Install (30 seconds)
pip install session-buddy

# Start server (10 seconds)
session-buddy start

# Initialize session (20 seconds)
session-buddy create-session "My Project"
```

**What you learned**:
- ✅ Installation
- ✅ Server startup
- ✅ Session initialization

---

## Level 2: Memory Integration (2 minutes) 🧠

**Goal**: Capture and search insights

```bash
# Store an insight (30 seconds)
session-buddy store-reflection \
  --content "Always use async/await for database operations" \
  --tags "database,best-practices"

# Search insights (1 minute)
session-buddy quick-search "database"

# View statistics (30 seconds)
session-buddy reflection-stats
```

**What you learned**:
- ✅ Storing reflections
- ✅ Semantic search
- ✅ Statistics tracking

---

## Level 3: Integration with Mahavishnu (2 minutes) 🔄

**Goal**: Cross-project intelligence

```bash
# Start with MCP (30 seconds)
session-buddy start --mcp

# Create project group (1 minute)
session-buddy create-project-group \
  --name "microservices" \
  --projects "auth-service,user-service,api-gateway"

# Cross-project search (30 seconds)
session-buddy search-across-projects \
  --group "microservices" \
  --query "authentication"
```

**What you learned**:
- ✅ MCP integration
- ✅ Project groups
- ✅ Cross-project search

---

## Next Steps

📚 **Intelligence Features**: Learn about automatic insights capture
→ `docs/features/INTELLIGENCE_QUICK_START.md`

🔧 **Configuration Reference**: Customize your setup
→ `docs/user/CONFIGURATION.md`

🌐 **MCP Tools**: Complete tool reference
→ `docs/user/MCP_TOOLS_REFERENCE.md`

## Troubleshooting

**Problem**: "Server won't start"
**Solution**: Check port 8678 is available: `lsof -i :8678`

**Problem**: "Search returns no results"
**Solution**: Ensure you've stored reflections: `session-buddy reflection-stats`

**Problem**: "MCP connection fails"
**Solution**: Verify PYTHONPATH is set in `.mcp.json`

## Need Help?

- 📖 [Full Documentation](docs/)
- 💬 [Community Discussions](https://github.com/lesleslie/session-buddy/discussions)
- 🐛 [Report Issues](https://github.com/lesleslie/session-buddy/issues)
```

### 3.2 Create ARCHITECTURE.md (Root)

**Based on**: Mahavishnu ARCHITECTURE.md format
**Length**: Comprehensive architecture overview
**Structure**:
- Executive Summary
- Architecture Overview
- Component Architecture
- Data Flow
- Security Architecture
- Integration Points
- Technology Stack

**Key Sections**:

```markdown
# Session-Buddy Architecture

**Single Source of Truth for Session-Buddy Architecture**

**Last Updated**: 2026-02-09
**Status**: Production Ready

______________________________________________________________________

## Executive Summary

Session-Buddy is the **Manager** role in the Mahavishnu ecosystem, responsible for session management, memory persistence, and knowledge aggregation across all projects.

### Core Responsibilities

- **Session Lifecycle**: Initialize, monitor, and cleanup Claude Code sessions
- **Memory Persistence**: Store and search conversations with semantic embeddings
- **Knowledge Capture**: Automatic insights extraction with deduplication
- **Cross-Project Intelligence**: Share knowledge across related projects
- **MCP Integration**: 79+ tools for session and memory management

### Current State

**Production Ready**:
- ✅ Session lifecycle management (auto and manual modes)
- ✅ DuckDB memory storage with local ONNX embeddings
- ✅ Automatic insights capture (SHA-256 deduplication)
- ✅ Cross-project search with dependency awareness
- ✅ FastMCP server with 79+ tools
- ✅ Integration with Mahavishnu, Akosha, and Crackerjack

______________________________________________________________________

## Architecture Overview

### Core Components

```
Session-Buddy
├── Core Application (session_buddy/core/)
│   ├── app.py                  # SessionBuddyApp - main application
│   ├── config.py               # Configuration with Oneiric patterns
│   ├── memory.py               # Memory management with DuckDB
│   └── insights.py             # Automatic insights capture
│
├── MCP Server (session_buddy/mcp/)
│   ├── server.py               # FastMCP server
│   └── tools/
│       ├── session_tools.py    # Session lifecycle (start, checkpoint, end)
│       ├── memory_tools.py     # Memory search and storage
│       ├── insights_tools.py   # Insights capture and search
│       └── project_tools.py    # Cross-project intelligence
│
├── Intelligence (session_buddy/intelligence/)
│   ├── embeddings.py           # ONNX-based semantic embeddings
│   ├── insights_extractor.py   # Pattern-based insights extraction
│   └── project_groups.py       # Cross-project coordination
│
├── Integration (session_buddy/integration/)
│   ├── mahavishnu.py           # Mahavishnu orchestrator integration
│   ├── akosha.py               # Akosha analytics integration
│   └── crackerjack.py          # Crackerjack QC integration
│
└── CLI (session_buddy/cli.py)  # Typer-based CLI
```

______________________________________________________________________

## Data Flow

### Session Lifecycle

```mermaid
stateDiagram-v2
    [*] --> GitRepo: Claude Code Connects
    [*] --> ManualInit: Non-Git Project

    GitRepo --> AutoStart: Auto-detect Git
    AutoStart --> Working: Development

    ManualInit --> ManualStart: User runs /start
    ManualStart --> Working: Development

    Working --> Checkpoint: /checkpoint
    Checkpoint --> Working: Continue

    Working --> AutoEnd: Disconnect/Quit
    Working --> ManualEnd: User runs /end

    AutoEnd --> [*]: Session Handoff
    ManualEnd --> [*]: Session Handoff
```

### Insights Capture Flow

```mermaid
flowchart LR
    A[Conversation] --> B[Pattern Matcher]
    B --> C{Insight Found?}
    C -->|Yes| D[SHA-256 Hash]
    C -->|No| E[Skip]
    D --> F{Duplicate?}
    F -->|No| G[Store with Embeddings]
    F -->|Yes| E
    G --> H[Searchable Memory]
```

______________________________________________________________________

## Security Architecture

### Local-First Privacy

- ✅ **100% Local Processing**: No external API calls
- ✅ **Local AI Models**: ONNX embeddings on your machine
- ✅ **Your Data Stays Yours**: Nothing leaves your system
- ✅ **Fast Performance**: <50ms extraction, <20ms search

### Encryption

- **Database**: Encrypted SQLite with AES-256-GCM
- **API Keys**: Environment variables only
- **Session Data**: Local filesystem with user permissions

______________________________________________________________________

## Integration Architecture

### Mahavishnu Integration

**Role**: Memory and session provider

```python
# Mahavishnu queries Session-Buddy for context
context = await session_buddy.get_project_context("auth-service")
insights = await session_buddy.search_insights("authentication patterns")
```

### Akosha Integration

**Role**: Analytics aggregation

```python
# Session-Buddy sends metrics to Akosha
await akosha.track_session_duration(session_id, duration)
await akosha.aggregate_insights(insights_data)
```

### Crackerjack Integration

**Role**: Quality tracking

```python
# Session-Buddy learns from quality checks
await session_buddy.store_quality_results(test_results)
await session_buddy.search_error_patterns(error_type)
```

______________________________________________________________________

## Technology Stack

### Core Technologies

- **FastMCP**: MCP server framework
- **DuckDB**: Local vector database (FLOAT[384] embeddings)
- **ONNX Runtime**: Local AI model inference
- **Oneiric**: Configuration management
- **Typer**: CLI framework

### Dependencies

```python
# Core dependencies
fastapi>=0.127.0
duckdb>=1.0.0
onnxruntime>=1.17.0
sentence-transformers>=2.2.0

# MCP integration
mcp-common>=0.1.0
fastmcp>=0.1.0

# Configuration
oneiric>=0.1.0
pydantic>=2.0.0
```

______________________________________________________________________

## Performance Characteristics

### Response Times

- **Session Start**: <100ms (excluding UV sync)
- **Insights Extraction**: <50ms per message
- **Semantic Search**: <20ms per query
- **Reflection Storage**: <10ms per insight

### Scalability

- **Sessions**: Unlimited (local filesystem)
- **Reflections**: Tested to 100K+ (DuckDB handles millions)
- **Projects**: Unlimited with project groups
- **Concurrent Users**: Single-user design (MCP limitation)

______________________________________________________________________

## Documentation

- **[README.md](README.md)**: Project overview and features
- **[CLAUDE.md](CLAUDE.md)**: Development guidelines
- **[docs/user/QUICK_START.md](docs/user/QUICK_START.md)**: Detailed user guide
- **[docs/user/MCP_TOOLS_REFERENCE.md](docs/user/MCP_TOOLS_REFERENCE.md)**: Complete tool reference
- **[docs/features/INTELLIGENCE_QUICK_START.md](docs/features/INTELLIGENCE_QUICK_START.md)**: Intelligence features

______________________________________________________________________

**Document Status**: Single source of truth for Session-Buddy architecture
**Last Reviewed**: 2026-02-09
**Next Review**: After next feature release
```

### 3.3 Create Service Dependencies Doc

**Location**: `docs/reference/service-dependencies.md`

```markdown
# Session-Buddy Service Dependencies

## Required Services

**None** - Session-Buddy is a standalone service that can run independently.

## Optional Integrations

### Mahavishnu (Orchestrator)

**Purpose**: Workflow orchestration and repository management
**Integration**: MCP protocol
**Benefits**: Session-Buddy provides memory and context for orchestrated workflows

**Configuration**:
```yaml
# .mcp.json
{
  "mcpServers": {
    "session-buddy": {
      "command": "python",
      "args": ["-m", "session_buddy.server"],
      "cwd": "/path/to/session-buddy"
    }
  }
}
```

### Akosha (Analytics)

**Purpose**: Analytics and insights aggregation
**Integration**: HTTP API
**Benefits**: Session-Buddy sends session metrics for analysis

**Configuration**:
```yaml
# settings/session-buddy.yaml
akosha:
  enabled: true
  url: "http://localhost:8682/mcp"
```

### Crackerjack (Quality Control)

**Purpose**: Code quality and testing
**Integration**: MCP protocol
**Benefits**: Session-Buddy learns from quality patterns and test results

**Configuration**:
```yaml
# settings/session-buddy.yaml
crackerjack:
  enabled: true
  track_quality: true
  learn_from_tests: true
```

### PostgreSQL (Persistence - Optional)

**Purpose**: Persistent session storage (alternative to DuckDB)
**Integration**: SQLAlchemy ORM
**Benefits**: Multi-user support, cloud backup

**Configuration**:
```yaml
# settings/session-buddy.yaml
database:
  backend: "postgresql"
  url: "postgresql://user:pass@localhost/sessionbuddy"
```

## Dependency Graph

```mermaid
graph TB
    SB[Session-Buddy]

    SB --> MB{Mahavishnu}
    SB --> AK{Akosha}
    SB --> CJ{Crackerjack}
    SB --> DB{(Database)}

    MB -.Optional.-> SB
    AK -.Optional.-> SB
    CJ -.Optional.-> SB

    DB -->|DuckDB| SB
    DB -.Optional PostgreSQL.-> SB

    style SB fill:#90EE90
    style MB fill:#FFD700
    style AK fill:#FFD700
    style CJ fill:#FFD700
    style DB fill:#87CEEB
```

## Startup Order

**Standalone Mode**:
1. Session-Buddy (no dependencies)

**Full Ecosystem Mode**:
1. PostgreSQL (if enabled)
2. Akosha (optional)
3. Session-Buddy
4. Mahavishnu
5. Crackerjack

## Health Checks

```bash
# Check Session-Buddy health
session-buddy health

# Check Mahavishnu connectivity
session-buddy check-integration mahavishnu

# Check Akosha connectivity
session-buddy check-integration akosha
```
```

______________________________________________________________________

## Phase 4: Consolidation Checklist

### File Migration

- [ ] Move 8 implementation reports to `docs/archive/implementation-plans/`
- [ ] Move 2 phase completions to `docs/archive/phase-completions/`
- [ ] Move 4 session tracking files to `docs/archive/session-summaries/`
- [ ] Move 3 test reports to `docs/archive/test-reports/`
- [ ] Move 3 feature docs to `docs/archive/implementation-plans/`
- [ ] Move 3 miscellaneous files to `docs/archive/uncategorized/`
- [ ] Move `RULES.md` to `docs/developer/coding-standards.md`

### Documentation Creation

- [ ] Create `QUICKSTART.md` in root (5-minute guide)
- [ ] Create `ARCHITECTURE.md` in root (comprehensive architecture)
- [ ] Create `docs/reference/service-dependencies.md`

### Verification

- [ ] Root directory has ≤ 10 markdown files
- [ ] All core files remain accessible (README, CLAUDE, CONTRIBUTING, CHANGELOG)
- [ ] Archive structure is organized and logical
- [ ] No broken links to moved files
- [ ] Documentation follows Mahavishnu format standards

______________________________________________________________________

## Success Metrics

### Before Consolidation

- Root markdown files: 30
- Documentation sprawl: High
- New user onboarding time: 15+ minutes

### After Consolidation

- Root markdown files: 6-8
- Documentation sprawl: Low
- New user onboarding time: 5 minutes

### Quality Metrics

- ✅ All documentation follows consistent format
- ✅ Progressive disclosure (quickstart → detailed → reference)
- ✅ Clear navigation paths
- ✅ Archive properly organized for historical reference

______________________________________________________________________

## Timeline

**Phase 1 (Audit)**: ✅ Complete (2026-02-09)
**Phase 2 (Migration)**: 1 day
**Phase 3 (Creation)**: 1 day
**Phase 4 (Verification)**: 0.5 days

**Total Estimated Time**: 2.5 days

______________________________________________________________________

**Plan Status**: Ready for execution
**Next Action**: Execute file migration commands
