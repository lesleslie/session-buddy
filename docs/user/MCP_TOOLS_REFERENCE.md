---
status: active
role: canonical
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: mcp-design
---

# Session Buddy - MCP Tools Reference

Complete reference guide for all Session Management MCP tools. Use these slash commands directly in Claude Code for comprehensive session management and intelligent conversation memory.

## 🚀 Core Session Management

### `/session-buddy:start` - Session Initialization

**Purpose**: Complete session setup with project analysis and dependency management

**Usage**:

```
/session-buddy:start
```

**What it does**:

- ✅ **Project Analysis**: Scans and analyzes your project structure, health, and maturity
- ✅ **Dependency Management**: Syncs UV, npm, pip, and other package managers automatically
- ✅ **Memory System**: Initializes conversation storage with semantic search capabilities
- ✅ **Permission Setup**: Configures trusted operations to reduce future prompts
- ✅ **Quality Baseline**: Establishes project health metrics for monitoring

**Returns**:

- Project context analysis with health score (0-100)
- Dependencies synchronization status
- Memory system initialization confirmation
- Personalized recommendations based on project type

**💡 Best Practice**: Run this at the start of every Claude Code session

______________________________________________________________________

### `/session-buddy:checkpoint` - Quality Monitoring

**Purpose**: Mid-session quality assessment with workflow optimization

**Usage**:

```
/session-buddy:checkpoint
```

**What it does**:

- 📊 **Quality Scoring**: Real-time analysis of project health, permissions, and tool availability
- 🔄 **Workflow Analysis**: Detects drift from optimal development patterns
- 📝 **Git Checkpoints**: Automatically creates meaningful commit with progress metadata
- 🎯 **Optimization Tips**: Provides specific recommendations for workflow improvements
- ⏱️ **Progress Tracking**: Monitors development velocity and goal alignment

**Returns**:

- Multi-dimensional quality score breakdown
- Workflow optimization recommendations
- Git checkpoint confirmation (if in repository)
- Personalized productivity insights

**💡 Best Practice**: Run every 30-45 minutes during active development

______________________________________________________________________

### `/session-buddy:end` - Session Cleanup

**Purpose**: Comprehensive session termination with learning capture

**Usage**:

```
/session-buddy:end
```

**What it does**:

- 📋 **Handoff Documentation**: Creates detailed session summary for continuity
- 🎓 **Learning Extraction**: Captures key insights, solutions, and patterns discovered
- 🧹 **Workspace Cleanup**: Optimizes temporary files and session artifacts
- 💾 **Memory Persistence**: Ensures all conversations are properly stored and indexed
- 📈 **Final Assessment**: Provides comprehensive session quality report

**Returns**:

- Final quality assessment and session metrics
- Handoff file path for future reference
- Learning insights categorized by type
- Memory persistence confirmation

**💡 Best Practice**: Always run at the end of development sessions

______________________________________________________________________

### `/session-buddy:status` - Session Overview

**Purpose**: Current session status with comprehensive health checks

**Usage**:

```
/session-buddy:status
```

**What it does**:

- 🔍 **Session State**: Reports current session status and active features
- 🏗️ **Project Context**: Analyzes current project structure and health
- 🛠️ **Tool Availability**: Lists available MCP tools and their status
- 🧠 **Memory Status**: Shows conversation storage and embedding system health
- 🔐 **Permissions**: Displays trusted operations and security settings

**Returns**:

- Complete session state overview
- Project health diagnostics
- Available tools inventory
- Memory system statistics
- Permission and security status

**💡 Best Practice**: Use when resuming sessions or troubleshooting issues

## 🧠 Memory & Search System

Start with `/session-buddy:quick_search` or `/session-buddy:search_summary` to get fast signal, then pivot to more focused tools like `/session-buddy:search_by_concept` or `/session-buddy:search_by_file` for deeper retrieval.

______________________________________________________________________

### `/session-buddy:store_reflection` - Save Insights

**Purpose**: Store important insights and solutions for future reference

**Usage**:

```
/session-buddy:store_reflection [content] [--tags=tag1,tag2,tag3]
```

**Parameters**:

- `content` (required): The insight, solution, or important information to store
- `tags` (optional): Comma-separated tags for organization and retrieval

**Examples**:

```
/session-buddy:store_reflection "JWT refresh token rotation pattern: use sliding window expiration with Redis storage for optimal security/UX balance" --tags=auth,jwt,security,redis

/session-buddy:store_reflection "Database migration best practice: always include rollback scripts and test on production-like data volumes"

/session-buddy:store_reflection "React state management: use Zustand for simple cases, Redux Toolkit for complex state with time-travel debugging" --tags=react,state,frontend
```

**What it does**:

- 💾 **Persistent Storage**: Saves insights to searchable knowledge base
- 🏷️ **Smart Tagging**: Automatically extracts relevant tags from content
- 🔍 **Searchable**: Instantly findable via semantic search
- 📊 **Cross-Reference**: Links to related conversations and contexts
- 🧠 **AI-Enhanced**: Generates embeddings for precise retrieval

**Returns**:

- Confirmation of storage with unique reflection ID
- Applied tags (automatic + manual)
- Embedding generation status
- Storage timestamp and metadata

**💡 Best Practice**: Use immediately after solving complex problems or gaining important insights

______________________________________________________________________

### `/session-buddy:quick_search` - Fast Overview Search

**Purpose**: Quick search with count and top result for rapid context assessment

**Usage**:

```
/session-buddy:quick_search [query] [--project=current] [--similarity=0.7]
```

**Examples**:

```
/session-buddy:quick_search Docker deployment strategies

/session-buddy:quick_search testing patterns --project=current
```

**What it does**:

- ⚡ **Fast Results**: Returns immediately with count and best match
- 📊 **Overview Mode**: Gives you the lay of the land without detail
- 🎯 **Relevance Check**: Tells you if deeper search is worth it
- 🔄 **Progressive Discovery**: Sets up for detailed search if needed

**Returns**:

- Total count of relevant conversations
- Single best matching result
- Indication if more results are available
- Cache key for retrieving additional results

**💡 Best Practice**: Use first to gauge available context before deeper searches

______________________________________________________________________

### `/session-buddy:get_more_results` - Pagination

**Purpose**: Retrieve additional results after initial searches

**Usage**:

```
/session-buddy:get_more_results [query] [--offset=3] [--limit=5]
```

**What it does**:

- 📄 **Pagination**: Efficiently retrieves additional search results
- 🎯 **Consistent Ranking**: Maintains same relevance ordering
- ⚡ **Performance**: Uses cached search state for speed
- 📊 **Progressive Loading**: Load results as needed

## 🔍 Specialized Search Tools

### `/session-buddy:search_by_file` - File-Specific Search

**Purpose**: Find all conversations that discussed specific files

**Usage**:

```
/session-buddy:search_by_file [file_path] [--limit=10] [--project=current]
```

**Examples**:

```
/session-buddy:search_by_file src/auth/middleware.py

/session-buddy:search_by_file package.json --limit=5

/session-buddy:search_by_file components/UserDashboard.tsx --project=current
```

**What it does**:

- 📁 **File-Centric**: Finds conversations where specific files were discussed
- 🔍 **Change History**: Shows evolution of file-related decisions
- 🏗️ **Context Reconstruction**: Rebuilds the story of how files developed
- 🔗 **Relationship Mapping**: Shows connections between related files

**💡 Best Practice**: Use before modifying existing files to understand previous decisions

______________________________________________________________________

### `/session-buddy:search_by_concept` - Concept Search

**Purpose**: Explore conversations about development concepts and patterns

**Usage**:

```
/session-buddy:search_by_concept [concept] [--include_files] [--limit=10] [--project=current]
```

**Examples**:

```
/session-buddy:search_by_concept "error handling patterns"

/session-buddy:search_by_concept authentication --include_files --limit=15

/session-buddy:search_by_concept "state management" --project=current
```

**What it does**:

- 🎯 **Concept-Focused**: Searches for abstract development concepts
- 📚 **Pattern Discovery**: Finds how concepts were implemented across projects
- 🔗 **Cross-Reference**: Shows related files and implementations when requested
- 🧠 **Knowledge Mining**: Extracts architectural decisions and reasoning

**💡 Best Practice**: Use when exploring how to implement new concepts or patterns

## 📊 Analytics & Insights

### `/session-buddy:search_summary` - Aggregated Insights

**Purpose**: Get high-level insights without individual result details

**Usage**:

```
/session-buddy:search_summary [query] [--project=current] [--similarity=0.7]
```

**What it does**:

- 📈 **Aggregated View**: Provides summary statistics and insights
- 🎯 **Pattern Recognition**: Identifies common themes and approaches
- 📊 **Trend Analysis**: Shows evolution of techniques over time
- 🧠 **Knowledge Synthesis**: Combines insights from multiple conversations

**💡 Best Practice**: Use for high-level understanding of how topics have been handled

______________________________________________________________________

### `/session-buddy:reflection_stats` - Knowledge Base Statistics

**Purpose**: Get comprehensive statistics about your stored knowledge

**Usage**:

```
/session-buddy:reflection_stats
```

**What it does**:

- 📊 **Storage Overview**: Total conversations, reflections, and projects tracked
- 🧠 **Memory Health**: Embedding coverage and system performance
- 📅 **Timeline**: Oldest to most recent conversation spans
- 💾 **Usage Metrics**: Storage utilization and optimization opportunities

**Returns**:

- Total conversations and reflections stored
- Number of projects tracked
- Embedding system coverage percentage
- Storage size and health metrics
- Timeline of stored knowledge

**💡 Best Practice**: Use periodically to understand the scope of your knowledge base

## 🔧 Advanced Features

### Smart Permission System

The MCP server learns your permission preferences over time:

- ✅ **UV sync operations** - Automatically trusted after first approval
- ✅ **Git operations** - Checkpoint commits become seamless
- ✅ **File operations** - Reading project files for analysis
- ✅ **Quality tools** - Running linters and formatters

### Cross-Project Intelligence

Your knowledge base spans all projects:

- 🔗 **Related Projects**: Automatically identifies connections between repositories
- 📊 **Pattern Mining**: Finds common solutions across different codebases
- 🎯 **Context Bridging**: Applies insights from one project to another
- 🧠 **Cumulative Learning**: Builds expertise that compounds over time

### Token Optimization

Large responses are automatically managed:

- 📄 **Auto-Chunking**: Responses >4000 tokens split into manageable pieces
- 🔄 **Progressive Loading**: Retrieve additional chunks as needed
- 📊 **Smart Summarization**: Important information prioritized
- ⚡ **Performance**: Optimized for Claude Code's context window

## 🚨 Troubleshooting

### Common Issues

#### "Memory system not available"

```bash
# Ensure all dependencies are installed (embeddings are included by default)
uv sync
# or
pip install session-buddy
```

#### "No conversations found"

- Ensure you've run `/session-buddy:start` to initialize the database
- Check that `~/.claude/data/` directory exists and is writable

#### "Project not detected"

- Make sure you're in a project directory
- Use the `working_directory` parameter in init if needed
- Verify git repository status if using git features

#### "Permission errors"

- Check file permissions on `~/.claude/` directory
- Verify MCP server configuration in `.mcp.json`
- Use `/session-buddy:status` to diagnose permission issues

### Performance Tips

- Use `/session-buddy:quick_search` before full searches to check relevance
- Higher similarity thresholds (0.8-0.9) for more precise results
- Lower thresholds (0.6-0.7) for broader exploration
- Use project filtering for large knowledge bases
- Regular checkpoints improve quality scoring accuracy

## 📊 Advanced Integration Tools

### Crackerjack Quality Integration (11 tools)

**Code Quality & Testing Integration** - Deep integration with the Crackerjack development platform:

- **`/session-buddy:crackerjack_run`** - Execute crackerjack commands with real-time analytics
- **`/session-buddy:execute_crackerjack_command`** - Run with enhanced AI integration
- **`/session-buddy:crackerjack_help`** - Comprehensive command selection help
- **`/session-buddy:crackerjack_metrics`** - Quality metrics trends over time
- **`/session-buddy:crackerjack_quality_trends`** - Trend analysis with insights
- **`/session-buddy:crackerjack_patterns`** - Test failure pattern analysis
- **`/session-buddy:crackerjack_history`** - Command execution history
- **`/session-buddy:crackerjack_health_check`** - Integration health diagnostics

### LLM Provider Management (5 tools)

- **`/session-buddy:list_llm_providers`** - List available providers and models
- **`/session-buddy:test_llm_providers`** - Test provider availability
- **`/session-buddy:generate_with_llm`** - Generate text using any provider
- **`/session-buddy:chat_with_llm`** - Have conversations with LLMs
- **`/session-buddy:configure_llm_provider`** - Configure credentials and settings

### Serverless Session Management (8 tools)

**External Storage Integration** - Redis, S3, or local storage:

- **`/session-buddy:create_serverless_session`** - Create with external storage
- **`/session-buddy:get_serverless_session`** - Retrieve session state
- **`/session-buddy:update_serverless_session`** - Update session data
- **`/session-buddy:delete_serverless_session`** - Remove session
- **`/session-buddy:list_serverless_sessions`** - List by user/project
- **`/session-buddy:test_serverless_storage`** - Test storage backend
- **`/session-buddy:cleanup_serverless_sessions`** - Remove expired sessions
- **`/session-buddy:configure_serverless_storage`** - Configure backends

### Team Collaboration (4 tools)

- **`/session-buddy:create_team`** - Create team for knowledge sharing
- **`/session-buddy:search_team_knowledge`** - Search with access control
- **`/session-buddy:get_team_statistics`** - Team activity metrics
- **`/session-buddy:vote_on_reflection`** - Vote on insights (upvote/downvote)

### Multi-Project Coordination (4 tools)

- **`/session-buddy:create_project_group`** - Group related projects
- **`/session-buddy:add_project_dependency`** - Define dependencies
- **`/session-buddy:search_across_projects`** - Cross-project search
- **`/session-buddy:get_project_insights`** - Cross-project insights

### Activity Monitoring (5 tools)

- **`/session-buddy:start_app_monitoring`** - Track IDE/browser activity
- **`/session-buddy:stop_app_monitoring`** - Stop monitoring
- **`/session-buddy:get_activity_summary`** - Activity summary
- **`/session-buddy:get_context_insights`** - Behavior insights
- **`/session-buddy:get_active_files`** - Recently active files

### Interruption Management (7 tools)

- **`/session-buddy:start_interruption_monitoring`** - Smart detection
- **`/session-buddy:stop_interruption_monitoring`** - Disable monitoring
- **`/session-buddy:create_session_context`** - Create snapshot
- **`/session-buddy:preserve_current_context`** - Force preservation
- **`/session-buddy:restore_session_context`** - Restore context
- **`/session-buddy:get_interruption_history`** - Interruption history
- **`/session-buddy:get_interruption_statistics`** - Analytics

### Natural Language Scheduling (5 tools)

- **`/session-buddy:create_natural_reminder`** - Create from natural language
- **`/session-buddy:list_user_reminders`** - List pending reminders
- **`/session-buddy:cancel_user_reminder`** - Cancel reminder
- **`/session-buddy:start_reminder_service`** - Start service
- **`/session-buddy:stop_reminder_service`** - Stop service

### Git Worktree Management (3 tools)

- **`/session-buddy:git_worktree_add`** - Create new worktree
- **`/session-buddy:git_worktree_remove`** - Remove worktree
- **`/session-buddy:git_worktree_switch`** - Switch with context preservation

## 📚 Related Documentation

## 🧱 Migration & Schema Tools

### `/session-buddy:migration_status`

Inspect schema version (v1/v2), migration history, and counts.

### `/session-buddy:trigger_migration`

Run v1 → v2 migration (supports `--create_backup_first` and `--dry_run`).

### `/session-buddy:rollback_migration`

Restore the database from a previous backup path.

## 📥 Extraction & Persistence

### `/session-buddy:extract_and_store_memory`

Multi-provider extraction (OpenAI→Anthropic→Gemini→pattern) and persistence into v2 tables.

Parameters include `activity_score` (0–1) to blend with LLM importance (70/30).

## 🧠 Conscious Agent

### `/session-buddy:start_conscious_agent` / `/session-buddy:stop_conscious_agent`

Start/stop background optimization (analysis, promotions/demotions).

### `/session-buddy:force_conscious_analysis`

Run one-time analysis; returns promoted/demoted counts.

## 📊 Access Metrics

### `/session-buddy:access_log_stats`

Inspect recent access activity with breakdowns `by_type` and `by_provider` and top memory candidates.

## 🧩 Feature Flags & Rollout

### `/session-buddy:feature_flags_status`

Show current feature flags for schema_v2, extraction, providers, agent, and filesystem integration.

### `/session-buddy:rollout_plan`

Staged enablement plan with daily steps and rollback guidance.

## 📎 Appendix: Registered Tools (Canonical)

Alphabetical list of all tools currently registered by the server:

Note: `*_validated` tools are internal validation wrappers used by the server and are not intended for direct user invocation.

- `access_log_stats`

- `add_observation`

- `batch_create_entities`

- `chat_with_llm`

- `checkpoint`

- `cleanup_serverless_sessions`

- `configure_llm_provider`

- `configure_serverless_storage`

- `create_entity`

- `create_relation`

- `create_serverless_session`

- `create_session_context`

- `create_team`

- `delete_serverless_session`

- `end`

- `extract_and_store_memory`

- `extract_entities_from_context`

- `feature_flags_status`

- `find_path`

- `force_conscious_analysis`

- `generate_with_llm`

- `get_active_files`

- `get_activity_summary`

- `get_context_insights`

- `get_entity_relationships`

- `get_interruption_history`

- `get_knowledge_graph_stats`

- `get_more_results`

- `get_serverless_session`

- `get_team_statistics`

- `health_check`

- `list_llm_providers`

- `list_serverless_sessions`

- `migration_status`

- `ping`

- `preserve_current_context`

- `quick_search`

- `quick_search_validated`

- `reflection_stats`

- `reset_reflection_database`

- `restore_session_context`

- `rollback_migration`

- `rollout_plan`

- `search_by_concept`

- `search_by_concept_validated`

- `search_by_file`

- `search_by_file_validated`

- `search_code`

- `search_entities`

- `search_errors`

- `search_summary`

- `search_team_knowledge`

- `search_temporal`

- `server_info`

- `start`

- `start_app_monitoring`

- `start_conscious_agent`

- `start_interruption_monitoring`

- `status`

- `stop_app_monitoring`

- `stop_conscious_agent`

- `stop_interruption_monitoring`

- `store_reflection`

- `store_reflection_validated`

- `test_llm_providers`

- `test_serverless_storage`

- `trigger_migration`

- `update_serverless_session`

- `vote_on_reflection`

- **[README.md](../../README.md)** - Project overview with complete tool inventory (70+ tools)

- **[Quick Start Guide](QUICK_START.md)** - Get up and running in 5 minutes

- **[MCP Schema Reference](../reference/MCP_SCHEMA_REFERENCE.md)** - Complete API reference

- **[AI Integration Patterns](../features/AI_INTEGRATION.md)** - Advanced patterns

- **[CLAUDE.md](../../CLAUDE.md)** - Development guide for contributors

- **[Configuration Reference](CONFIGURATION.md)** - Advanced setup options

______________________________________________________________________

*This reference lists all registered MCP tools provided by session-buddy. For implementation details, see the codebase.*

**Need help?** Use `/session-buddy:status` to diagnose issues or check [GitHub Issues](https://github.com/lesleslie/session-buddy/issues) for support.
