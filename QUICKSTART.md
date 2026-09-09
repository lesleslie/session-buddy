______________________________________________________________________

## status: active role: canonical date: 2026-07-16 last_reviewed: 2026-07-16 superseded_by: null blocks_on: [] topic: lifecycle

# Session-Buddy Quickstart (5 minutes)

Get started with Session-Buddy in 5 minutes with this progressive guide.

______________________________________________________________________

## Level 1: Basic Session Management (1 minute) ✅

**Goal**: Create and manage sessions

```bash
# Install (30 seconds)
pip install session-buddy

# Start the MCP server (10 seconds)
uv run session-buddy server start

# Create your first session (20 seconds)
# Note: `session-buddy` itself doesn't create sessions — that's an MCP tool.
# Use the MCP interface (mcp__session-buddy__start, mcp__session-buddy__checkpoint,
# mcp__session-buddy__end) or the programmatic API
# (session_buddy.reflection.ReflectionDatabase).

# List all sessions (analytics subcommand)
uv run session-buddy analytics sessions --days 30

**What you learned**: `session-buddy` is a CLI for server lifecycle and analytics. Session management, reflections, and search are exposed as MCP tools (the `mcp__session-buddy__*` namespace), not as CLI subcommands. Use the MCP tools directly, or call the underlying Python API (`session_buddy.reflection.ReflectionDatabase`).
```

**What you learned**:

- ✅ Basic installation
- ✅ Lite mode startup
- ✅ Session creation and listing

______________________________________________________________________

## Level 2: Memory Integration (2 minutes) 🧠

**Goal**: Store and search session memories

```bash
# Add a message to your session (30 seconds)
# Note: `session-buddy` doesn't have a `add-message` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__add_message` (or call
# `session_buddy.reflection.ReflectionDatabase.store(...)` programmatically).

# Store a reflection (30 seconds)
# Note: `session-buddy` doesn't have a `store-reflection` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__store_reflection` (or call
# `session_buddy.reflection.ReflectionDatabase.store(...)` programmatically).

# Search across sessions (1 minute)
# Note: `session-buddy` doesn't have a `search` CLI subcommand.
# Use the MCP tools `mcp__session-buddy__quick_search`,
# `mcp__session-buddy__search_summary`, or
# `mcp__session-buddy__search_by_concept`.

# View reflection statistics
# Note: `session-buddy` doesn't have a `reflection-stats` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__reflection_stats`.
```

**What you learned**: `session-buddy` is a CLI for server lifecycle and analytics. Session management, reflections, and search are exposed as MCP tools (the `mcp__session-buddy__*` namespace), not as CLI subcommands. Use the MCP tools directly, or call the underlying Python API (`session_buddy.reflection.ReflectionDatabase`).

- ✅ Message tracking
- ✅ Reflection storage
- ✅ Cross-session search
- ✅ Analytics viewing

______________________________________________________________________

## Level 3: Integration with Mahavishnu (2 minutes) 🔄

**Goal**: Connect Session-Buddy to the Mahavishnu orchestrator

```bash
# Start with MCP server enabled (10 seconds)
uv run session-buddy server start

# Verify MCP server is running (10 seconds)
session-buddy health

# Create a project group (30 seconds)
# Note: `session-buddy` doesn't have a `create-project-group` CLI subcommand.
# Project groups are managed via MCP tools (`mcp__session-buddy__*`), not the CLI.

# Search across all projects in group (1 minute)
# Note: `session-buddy` doesn't have a `search-across-projects` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__search_by_concept` (or call the
# programmatic API).

# Export session data (30 seconds)
# Note: `session-buddy` doesn't have an `export` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__export_data` or the programmatic API.
```

**What you learned**:

- ✅ MCP server startup
- ✅ Project group management
- ✅ Cross-project search
- ✅ Session data export

______________________________________________________________________

## Level 4: Advanced Analytics (5 minutes) 📊

**Goal**: Use DuckDB-powered analytics and insights

```bash
# Start with full analytics (10 seconds)
uv run session-buddy server start

# Generate session summary (1 minute)
# Note: `session-buddy` doesn't have a `summarize-session` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__summarize_session` or the
# programmatic API (session_buddy.reflection.ReflectionDatabase).

# Find patterns across sessions (2 minutes)
# Note: `session-buddy` doesn't have a `find-patterns` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__search_by_concept` or
# `mcp__session-buddy__quick_search` instead.

# Get insights dashboard (1 minute)
# Note: `session-buddy` doesn't have an `insights-dashboard` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__insights_dashboard` instead.

# Export analytics data (30 seconds)
uv run session-buddy analytics report --days 30 --output report.csv
```

**What you learned**:

- ✅ Session summarization
- ✅ Pattern detection
- ✅ Insights dashboard
- ✅ Analytics export

______________________________________________________________________

## Next Steps

📚 **Progressive Complexity Guide**: Learn about different operational modes
→ `docs/guides/operational-modes.md`

🧠 **Intelligence Features**: Explore AI-powered features
→ `docs/features/INTELLIGENCE_QUICK_START.md`

🔧 **Configuration Reference**: Customize your setup
→ `docs/user/CONFIGURATION.md`

🌐 **Architecture**: Understand the system design
→ `ARCHITECTURE.md`

______________________________________________________________________

## Troubleshooting

**Problem**: "Session-Buddy won't start"
**Solution**:

```bash
# Check what's blocking the port
lsof -i :8678

# Use a different port
uv run session-buddy server start --port 8679

# Or override the default port via settings YAML at settings/session-buddy.yaml
# (server_port: 8678) — Oneiric's layered loader merges YAML + env vars
# last-wins, so env takes precedence at process start.
```

**Problem**: "Cannot connect to Mahavishnu"
**Solution**:

```bash
# Verify Mahavishnu is running
mahavishnu health

# Check Session-Buddy MCP server
session-buddy health

# Use lite mode for standalone operation
uv run session-buddy server start
```

**Problem**: "Search returns no results"
**Solution**:

```bash
# Check if sessions have data
uv run session-buddy analytics sessions --days 30

# Add some test data
# Note: `session-buddy` doesn't have a `add-message` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__add_message` or the programmatic API
# (session_buddy.reflection.ReflectionDatabase).

# Verify reflection storage
# Note: `session-buddy` doesn't have a `reflection-stats` CLI subcommand.
# Use the MCP tool `mcp__session-buddy__reflection_stats` instead.
```

**Problem**: "Analytics not working"
**Solution**:

```bash
# Verify DuckDB is installed
pip install duckdb

# Check analytics mode is enabled
session-buddy health

# Restart with analytics enabled
uv run session-buddy server start
```

______________________________________________________________________

## Need Help?

- 📖 [Full Documentation](docs/)
- 🌐 [Architecture Overview](ARCHITECTURE.md)
- 💬 Community Discussions
- 🐛 Report Issues

______________________________________________________________________

**Quickstart Version**: v1.0
**Last Updated**: 2026-02-09
**Status**: Production Ready <!-- legacy status — see YAML frontmatter -->
