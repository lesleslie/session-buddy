#!/usr/bin/env python3
"""Session command definitions for MCP prompts.

This module contains the SESSION_COMMANDS dictionary with all command
descriptions following crackerjack architecture patterns.
"""

from __future__ import annotations

# Session command definitions for MCP prompts
SESSION_COMMANDS = {
    "init": """# Session Initialization

Initialize Claude session with comprehensive setup and intelligent lifecycle management.

This command will:
- **Set up Claude directory structure** (~/.claude/ for logs, data, cache)
- **Initialize ACB storage adapters** (file, S3, Azure, GCS support)
- **Configure vector database** (DuckDB with FLOAT[384] embeddings)
- **Set up knowledge graph** (DuckPGQ for entity/relationship queries)
- **Initialize quality scoring V2** (filesystem-based assessment)
- **Configure dependency injection** (ACB lifecycle management)
- **Enable auto-session management** (git repos: automatic init/cleanup)
- **Set up conversation memory** (local ONNX embeddings, no external APIs)
- **Configure Crackerjack integration** (quality metrics tracking)
- **Create slash command shortcuts** (/start, /checkpoint, /end)

**Key Features:**
- 🚀 **Automatic for git repos**: Zero manual intervention required
- 🔒 **Local-first privacy**: All embeddings generated locally via ONNX
- 📊 **Quality monitoring**: V2 scoring with project health metrics
- 🧠 **Semantic search**: 384-dimensional vector similarity
- 🔄 **Auto-cleanup**: Crash-resilient session management
- 📦 **ACB integration**: Modern async component lifecycle

**Storage Options** (configurable in settings/session-buddy.yaml):
- `file` - Local file storage (default)
- `s3` - AWS S3/MinIO cloud storage
- `azure` - Azure Blob Storage
- `gcs` - Google Cloud Storage

Run this at the start of any coding session for optimal Claude integration.
""",
    "checkpoint": """# Session Checkpoint

Perform mid-session quality checkpoint with workflow analysis and optimization recommendations.

This command will:
- **Calculate quality score V2** (filesystem-based assessment, 0-100 scale)
- **Analyze project health** (maturity, dependencies, documentation coverage)
- **Review session permissions** (trusted operations for workflow efficiency)
- **Track Crackerjack metrics** (quality trends, test patterns, error resolutions)
- **Optimize storage adapters** (ACB-based vector/graph database performance)
- **Perform strategic cleanup** (when context window is high):
  • DuckDB VACUUM/ANALYZE for vector database optimization
  • Knowledge graph cleanup (orphaned entities/relationships)
  • Session log rotation (retain last 10 files)
  • Cache cleanup (.DS_Store, .coverage files, __pycache__)
  • Git repository optimization (gc --auto, prune remote branches)
  • UV package cache cleanup
- **Analyze context usage** and recommend `/compact` when beneficial
- **Create automatic git commit** with checkpoint metadata
- **Generate workflow recommendations** for productivity improvements

**Quality Score V2 Factors:**
- Project maturity (README, docs structure, test coverage)
- Code quality (Ruff complexity, type hints coverage)
- Session optimization (permissions, tools integration)
- Development workflow (git history, commit patterns)

**RECOMMENDED WORKFLOW:**
1. Run `/session-buddy:checkpoint` for comprehensive analysis
2. Review quality score and workflow recommendations
3. If context compaction is recommended, run: `/compact`
4. Continue with optimized session context

Use this periodically during long coding sessions to maintain optimal productivity and system performance.
""",
    "end": """# Session End

Complete your Claude Code session with comprehensive cleanup, learning capture, and handoff documentation.

This command will:
- **Generate session handoff documentation** with key insights
- **Perform final quality assessment V2** (filesystem-based scoring)
- **Store session reflections** in vector database with embeddings
- **Optimize ACB storage adapters** (compact vector/graph databases)
- **Clean up temporary files** (cache, .DS_Store, test artifacts)
- **Capture Crackerjack insights** (quality trends, successful patterns)
- **Create final commit** with session summary metadata
- **Provide next session recommendations** based on current state

**Handoff Documentation Includes:**
- Quality score V2 with detailed metrics (0-100 scale)
- Actionable recommendations for next session
- Key achievements and technical insights
- Next steps for continuing work
- Session context and environment information
- Reflection database statistics (conversations stored)
- Knowledge graph summary (entities/relationships)

**Automatic for Git Repos:**
If you're in a git repository, session end happens automatically on disconnect, quit, or crash. No manual action needed.

**For Non-Git Projects:**
Run this command at the end of your session to ensure proper closure and knowledge transfer.
""",
    "status": """# Session Status

Get comprehensive status of your current Claude Code session including project health, storage adapters, permissions, and optimization opportunities.

This command provides:
- **Current session state** (active/inactive, duration)
- **Quality score V2** (0-100 with detailed breakdown)
- **Project health metrics** (maturity, dependencies, documentation)
- **Storage adapter status** (ACB backend: file/S3/Azure/GCS)
- **Database status** (vector database + knowledge graph)
- **Session permissions** (trusted operations for workflow efficiency)
- **MCP server integrations** (79+ tools available)
- **Crackerjack metrics** (recent quality scores, trends)
- **Memory usage** (context window, optimization suggestions)
- **Git status** (branch, uncommitted changes, repo health)
- **Recent activity** (last checkpoint, reflections stored)

**Storage Adapters (ACB-Based):**
- Current backend: file, S3, Azure, or GCS
- Connection status and health check
- Vector database: DuckDB with FLOAT[384] embeddings
- Knowledge graph: DuckPGQ entity/relationship queries

**Quality Metrics:**
- Project maturity (README, docs, tests)
- Code quality (complexity, type hints)
- Session optimization (permissions, shortcuts)
- Development workflow (git patterns, automation)

Use this to quickly understand your development environment and identify optimization opportunities.
""",
    "permissions": """# Session Permissions Management

Manage session permissions for trusted operations to avoid repeated prompts during development workflows.

This command allows you to:
- View current permissions and trusted operations
- Trust specific operations (git commits, file operations, etc.)
- Revoke all permissions and reset to default security
- Configure permission scopes and time limits
- Review permission usage history

**Available Actions:**
- `status` - Show current permissions and trusted operations
- `trust <operation>` - Add an operation to trusted list
- `revoke_all` - Reset all permissions to default

Use this to streamline repetitive operations while maintaining security control.
""",
    "reflect": """# Store Session Reflection

Store important insights, learnings, or reflections from your current session for future reference and team knowledge sharing.

This command will:
- Store your reflection with semantic embedding for search
- Tag reflections for easy categorization and retrieval
- Enable cross-project learning and pattern recognition
- Support team knowledge base building
- Provide search and retrieval capabilities

**Usage Examples:**
- Store technical insights: "This pattern solved our async concurrency issues"
- Document decisions: "We chose FastAPI over Flask because of async support"
- Capture learnings: "The key to debugging this was checking the database connection pool"
- Share solutions: "This regex pattern handles edge cases in user input validation"

Reflections become searchable across all your projects and sessions.
""",
    "quick-search": """# Quick Conversation Search

Perform a fast search through your conversation history to find relevant past discussions, solutions, and insights.

This command provides:
- **Quick Overview**: Returns count and top result only for fast scanning
- **Semantic Search**: Uses AI embeddings to find conceptually similar content
- **Cross-Project**: Searches across all your project conversations
- **Recent Priority**: Prioritizes more recent conversations in results
- **Fallback**: Uses text search if AI embeddings unavailable

**Best For:**
- "Did I solve this before?" quick checks
- Finding similar error patterns
- Locating specific technical discussions
- Quick reference to past decisions

**Example Queries:**
- "async database connection issues"
- "React component optimization patterns"
- "Docker deployment configurations"
- "testing strategies for API endpoints"

For detailed results, use the full search tools after getting the quick overview.
""",
    "search-summary": """# Search Summary & Insights

Get aggregated insights from your conversation history without individual result details - perfect for understanding patterns and themes.

This command provides:
- **Pattern Analysis**: Common themes and approaches across conversations
- **Solution Trends**: Frequently used solutions and their contexts
- **Knowledge Gaps**: Areas where you've sought help repeatedly
- **Best Practices**: Patterns that emerged from successful solutions
- **Technology Evolution**: How your approach to technologies has changed

**Best For:**
- Understanding your development patterns
- Identifying recurring challenges
- Finding knowledge consolidation opportunities
- Discovering your most effective approaches
- Planning learning and documentation priorities

**Example Queries:**
- "database performance optimization" → Shows your evolution in DB tuning approaches
- "React testing strategies" → Reveals your preferred testing patterns
- "deployment automation" → Highlights your deployment workflow evolution

Use this for strategic analysis of your development journey and knowledge patterns.
""",
    "reflection-stats": """# Reflection Database Statistics

Get comprehensive statistics about your stored knowledge, conversation history, and learning patterns.

This command provides:
- **Database Health**: Connection status, size, and performance metrics
- **Content Overview**: Total conversations, reflections, and search patterns
- **Usage Patterns**: Most searched topics and retrieval trends
- **Growth Metrics**: Knowledge base expansion over time
- **Search Effectiveness**: Query success rates and pattern analysis
- **Storage Efficiency**: Database optimization opportunities

**Includes:**
- Total stored conversations and reflections
- Most frequently searched topics
- Database size and performance metrics
- Search effectiveness and patterns
- Recent activity and growth trends
- Optimization recommendations

Use this to understand your knowledge base growth and optimize your learning workflow.
""",
    "crackerjack-run": """# Enhanced Crackerjack Execution with Memory Integration

Execute Crackerjack commands with comprehensive analytics, memory integration, and intelligent insights.

**Enhanced Features:**
- **Memory Integration**: Results stored and searchable across sessions
- **Intelligent Insights**: AI analysis of patterns, trends, and recommendations
- **Quality Tracking**: Historical comparison and regression detection
- **Context Awareness**: Project-specific recommendations and best practices
- **Failure Analysis**: Deep dive into error patterns and resolution strategies

**Available Commands:**
- `analyze` - Code quality analysis with trend insights
- `check` - Quick health check with historical comparison
- `test` - Test execution with pattern analysis
- `lint` - Linting with rule effectiveness tracking
- `security` - Security scan with threat trend analysis
- `complexity` - Complexity analysis with refactoring recommendations

**Example Usage:**
- `/session-buddy:crackerjack_run test` - Run tests with intelligent analysis
- `/session-buddy:crackerjack_run analyze` - Full quality analysis with insights

Results include execution output, trend analysis, and actionable recommendations based on your project's history.
""",
    "crackerjack-history": """# Crackerjack Execution History & Trends

View comprehensive history of Crackerjack executions with trend analysis and pattern recognition.

**Features:**
- **Execution Timeline**: Chronological view of all Crackerjack runs
- **Quality Trends**: Track code quality metrics over time
- **Command Patterns**: Most used commands and their success rates
- **Error Evolution**: How error patterns have changed
- **Performance Tracking**: Execution time trends and optimization opportunities
- **Success Metrics**: Pass/fail rates and improvement patterns

**Filters Available:**
- Time range (last 7/30/90 days)
- Command type (test, lint, analyze, etc.)
- Success/failure status
- Project scope

**Insights Provided:**
- Quality improvement trends
- Most effective commands for your workflow
- Recurring issue patterns
- Optimal execution timing
- Workflow efficiency recommendations

Use this to optimize your development workflow and identify quality improvement opportunities.
""",
    "crackerjack-metrics": """# Quality Metrics & Trends Analysis

Get comprehensive quality metrics trends from Crackerjack execution history with actionable insights.

**Metric Categories:**
- **Code Quality**: Complexity, maintainability, technical debt trends
- **Test Coverage**: Coverage percentage evolution and gap analysis
- **Security Posture**: Vulnerability trends and resolution effectiveness
- **Performance**: Build times, test execution speed, and optimization opportunities
- **Compliance**: Code standard adherence and improvement patterns

**Trend Analysis:**
- **Improvement Velocity**: Rate of quality enhancement over time
- **Regression Detection**: Automatic identification of quality drops
- **Comparative Analysis**: Performance vs. industry/team benchmarks
- **Seasonal Patterns**: Quality variations and their causes
- **Predictive Insights**: Projected quality trends and recommendations

**Visualizations:**
- Quality score evolution graphs
- Test coverage heat maps
- Security vulnerability timelines
- Performance benchmark comparisons

**Actionable Recommendations:**
- Priority areas for improvement
- Optimal refactoring timing
- Resource allocation suggestions
- Risk mitigation strategies

Use this for strategic development planning and continuous quality improvement.
""",
    "crackerjack-patterns": """# Test Failure Pattern Analysis

Analyze test failure patterns and trends to identify systematic issues and optimization opportunities.

**Pattern Detection:**
- **Recurring Failures**: Tests that fail consistently across runs
- **Flaky Tests**: Intermittent failures and their triggers
- **Dependency Issues**: Failures caused by external dependencies
- **Environment Sensitivity**: Platform or configuration-specific failures
- **Performance Degradation**: Tests failing due to timing or resource constraints

**Failure Classification:**
- **Systematic Issues**: Code quality problems requiring refactoring
- **Infrastructure Problems**: CI/CD, environment, or dependency issues
- **Test Quality Issues**: Poorly written or maintained tests
- **Coverage Gaps**: Missing test scenarios revealed by failures
- **Performance Issues**: Resource or timing-related problems

**Insights Provided:**
- Most problematic test suites and their root causes
- Optimal test execution strategies and timing
- Resource allocation recommendations for test infrastructure
- Test maintenance priorities and refactoring opportunities
- Quality gate optimization suggestions

**Actionable Recommendations:**
- Immediate fixes for critical failure patterns
- Long-term test suite improvement strategies
- Infrastructure optimization opportunities
- Test quality improvement priorities

Use this to transform test failures from obstacles into learning opportunities and systematic improvements.
""",
}
