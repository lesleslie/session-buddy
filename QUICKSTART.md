# Session-Buddy Quickstart (5 minutes)

Get started with Session-Buddy in 5 minutes with this progressive guide.

______________________________________________________________________

## Level 1: Basic Session Management (1 minute) ✅

**Goal**: Create and manage sessions

```bash
# Install (30 seconds)
pip install session-buddy

# Start in lite mode (10 seconds)
session-buddy start --mode=lite

# Create your first session (20 seconds)
session-buddy create-session "My Project"

# List all sessions
session-buddy list-sessions
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
session-buddy add-message \
  --session "My Project" \
  "Analyzed API structure for user authentication"

# Store a reflection (30 seconds)
session-buddy store-reflection \
  --content "Use JWT tokens for stateless auth" \
  --tags "authentication,best-practices"

# Search across sessions (1 minute)
session-buddy search "authentication"

# View reflection statistics
session-buddy reflection-stats
```

**What you learned**:

- ✅ Message tracking
- ✅ Reflection storage
- ✅ Cross-session search
- ✅ Analytics viewing

______________________________________________________________________

## Level 3: Integration with Mahavishnu (2 minutes) 🔄

**Goal**: Connect Session-Buddy to the Mahavishnu orchestrator

```bash
# Start with MCP server enabled (10 seconds)
session-buddy start --mode=standard --mcp

# Verify MCP server is running (10 seconds)
session-buddy health

# Create a project group (30 seconds)
session-buddy create-project-group \
  --name "microservices" \
  --projects "auth,user,api"

# Search across all projects in group (1 minute)
session-buddy search-across-projects \
  --group "microservices" \
  --query "database schema"

# Export session data (30 seconds)
session-buddy export "my-project.json"
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
session-buddy start --mode=standard --analytics

# Generate session summary (1 minute)
session-buddy summarize-session \
  --session "My Project" \
  --format markdown

# Find patterns across sessions (2 minutes)
session-buddy find-patterns \
  --query "API design patterns" \
  --min-occurrences 3

# Get insights dashboard (1 minute)
session-buddy insights-dashboard

# Export analytics data (30 seconds)
session-buddy export-analytics \
  --format csv \
  --output "analytics.csv"
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
session-buddy start --port 8679
```

**Problem**: "Cannot connect to Mahavishnu"
**Solution**:

```bash
# Verify Mahavishnu is running
mahavishnu health

# Check Session-Buddy MCP server
session-buddy health

# Use lite mode for standalone operation
session-buddy start --mode=lite
```

**Problem**: "Search returns no results"
**Solution**:

```bash
# Check if sessions have data
session-buddy list-sessions

# Add some test data
session-buddy add-message --session "My Project" "Test message"

# Verify reflection storage
session-buddy reflection-stats
```

**Problem**: "Analytics not working"
**Solution**:

```bash
# Verify DuckDB is installed
pip install duckdb

# Check analytics mode is enabled
session-buddy health | grep analytics

# Restart with analytics enabled
session-buddy start --mode=standard --analytics
```

______________________________________________________________________

## Need Help?

- 📖 [Full Documentation](docs/)
- 🌐 [Architecture Overview](ARCHITECTURE.md)
- 💬 [Community Discussions](https://github.com/lesleslie/session-buddy)
- 🐛 [Report Issues](https://github.com/lesleslie/session-buddy/issues)

______________________________________________________________________

**Quickstart Version**: v1.0
**Last Updated**: 2026-02-09
**Status**: Production Ready
