# MCP Schema Reference for AI Agents

This document provides the complete MCP tool schema for AI agents integrating with the Session Management MCP server.

## Tool Categories

### 🚀 Session Management Tools

#### `mcp__session-buddy__start`

**Purpose**: Complete session initialization with workspace verification

```typescript
interface StartParameters {
  working_directory?: string  // Optional working directory override
}

interface StartResponse {
  success: boolean
  project_context: {
    name: string
    type: string
    health_score: number  // 0-100
    structure_analysis: object
  }
  dependencies_synced: boolean
  memory_initialized: boolean
  permissions_setup: boolean
  recommendations: string[]
}
```

**When to use**: Always at the start of every session
**AI Integration**: Automatically sets up optimal working environment

______________________________________________________________________

#### `mcp__session-buddy__checkpoint`

**Purpose**: Mid-session quality monitoring with workflow analysis

```typescript
interface CheckpointParameters {}

interface CheckpointResponse {
  success: boolean
  quality_score: {
    overall: number        // 0-100
    project_health: number // 0-100
    permissions: number    // 0-100
    tools_available: number // 0-100
  }
  recommendations: string[]
  git_checkpoint_created: boolean
  optimization_suggestions: string[]
  workflow_insights: object
}
```

**When to use**: Every 30-45 minutes during active development
**AI Integration**: Provides real-time feedback for workflow optimization

______________________________________________________________________

#### `mcp__session-buddy__end`

**Purpose**: Complete session cleanup with learning capture

```typescript
interface EndParameters {}

interface EndResponse {
  success: boolean
  final_quality_score: number
  learning_captured: {
    insights: string[]
    solutions: string[]
    patterns: string[]
  }
  handoff_file_created: boolean
  handoff_file_path?: string
  memory_persisted: boolean
  cleanup_performed: boolean
}
```

**When to use**: At the end of every development session
**AI Integration**: Creates continuity for future sessions

______________________________________________________________________

#### `mcp__session-buddy__status`

**Purpose**: Current session status with health checks

```typescript
interface StatusParameters {
  working_directory?: string
}

interface StatusResponse {
  success: boolean
  session_active: boolean
  project_context: object
  available_tools: string[]
  memory_system_status: {
    enabled: boolean
    conversations_stored: number
    embeddings_available: boolean
  }
  permissions_status: object
  health_checks: object
}
```

**When to use**: When you need to understand current session state
**AI Integration**: Essential for context-aware assistance

### 🧠 Memory & Search Tools

Use `quick_search` or `search_summary` for fast semantic retrieval, then expand with `get_more_results`, `search_by_concept`, or `search_by_file` for deeper exploration.

```typescript
interface ConversationResult {
  content: string
  project: string
  timestamp: string
  similarity_score: number        // 0.0-1.0
  context: string                // Surrounding conversation context
}
```

______________________________________________________________________

#### `mcp__session-buddy__store_reflection`

**Purpose**: Store important insights for future reference

```typescript
interface StoreReflectionParameters {
  content: string                 // REQUIRED: Insight content
  tags?: string[]                 // Optional categorization tags
}

interface StoreReflectionResponse {
  success: boolean
  reflection_id: string
  stored_at: string              // ISO timestamp
  embedding_generated: boolean
  tags_applied: string[]
}
```

**When to use**: After solving complex problems or gaining important insights
**AI Integration**: Builds project knowledge base for future sessions

______________________________________________________________________

#### `mcp__session-buddy__quick_search`

**Purpose**: Fast search with count and top result only

```typescript
interface QuickSearchParameters {
  query: string                   // REQUIRED
  project?: string | null
  min_score?: number             // Default: 0.7
}

interface QuickSearchResponse {
  success: boolean
  total_count: number
  top_result: ConversationResult | null
  has_more: boolean
  cache_key?: string             // For getting more results
}
```

**When to use**: When you need a quick overview before diving deeper
**AI Integration**: Efficient way to check if relevant context exists

______________________________________________________________________

#### `mcp__session-buddy__search_summary`

**Purpose**: Aggregate insights without returning full result lists

```typescript
interface SearchSummaryParameters {
  query: string                   // REQUIRED
  project?: string | null
  min_score?: number             // Default: 0.7
}

interface SearchSummaryResponse {
  success: boolean
  summary: string
  total_count: number
}
```

**When to use**: When you want a concise summary of relevant context
**AI Integration**: Useful for scoping work before deeper retrieval

______________________________________________________________________

#### `mcp__session-buddy__get_more_results`

**Purpose**: Pagination support after initial searches

```typescript
interface GetMoreResultsParameters {
  query: string                   // Original search query
  offset?: number                 // Default: 3
  limit?: number                  // Default: 3
  project?: string | null
}

interface GetMoreResultsResponse {
  success: boolean
  results: ConversationResult[]
  has_more: boolean
  total_available: number
}
```

**When to use**: After quick_search indicates more results available
**AI Integration**: Allows progressive discovery of relevant context

### 🔍 Advanced Search Tools

#### `mcp__session-buddy__search_by_file`

**Purpose**: Find conversations analyzing specific files

```typescript
interface SearchByFileParameters {
  file_path: string              // REQUIRED: File path to search for
  limit?: number                 // Default: 10
  project?: string | null
}
```

**When to use**: When you need to understand previous work on specific files
**AI Integration**: Perfect for file-specific context and change history

______________________________________________________________________

#### `mcp__session-buddy__search_by_concept`

**Purpose**: Search for conversations about development concepts

```typescript
interface SearchByConceptParameters {
  concept: string                 // REQUIRED: e.g., "error handling", "authentication"
  include_files?: boolean         // Default: true
  limit?: number                 // Default: 10
  project?: string | null
}
```

**When to use**: When exploring how concepts were implemented across the project
**AI Integration**: Ideal for learning patterns and architectural decisions

______________________________________________________________________

#### `mcp__session-buddy__search_code`

**Purpose**: Search code-related conversations by pattern type

```typescript
interface SearchCodeParameters {
  query: string                   // REQUIRED
  pattern_type?: string | null
  limit?: number                 // Default: 10
  project?: string | null
}
```

**When to use**: When you need prior code snippets or implementation notes

______________________________________________________________________

#### `mcp__session-buddy__search_errors`

**Purpose**: Search error and failure-related conversations

```typescript
interface SearchErrorsParameters {
  query: string                   // REQUIRED
  error_type?: string | null
  limit?: number                 // Default: 10
  project?: string | null
}
```

**When to use**: When debugging recurring issues

______________________________________________________________________

#### `mcp__session-buddy__search_temporal`

**Purpose**: Search conversations using time expressions

```typescript
interface SearchTemporalParameters {
  time_expression: string         // REQUIRED (e.g., "last week")
  query?: string | null
  limit?: number                 // Default: 10
  project?: string | null
}
```

**When to use**: When you want context within a time window

### 📊 Analytics & Insights Tools

#### `mcp__session-buddy__reflection_stats`

**Purpose**: Get statistics about stored knowledge

```typescript
interface ReflectionStatsResponse {
  success: boolean
  total_conversations: number
  total_reflections: number
  projects_tracked: number
  embedding_coverage: number     // Percentage with embeddings
  storage_size_mb: number
  oldest_conversation: string    // ISO timestamp
  most_recent: string           // ISO timestamp
}
```

**When to use**: To understand the scope of stored knowledge
**AI Integration**: Helps gauge available context depth

______________________________________________________________________

#### `mcp__session-buddy__reset_reflection_database`

**Purpose**: Reset the reflection database (use with caution)

```typescript
interface ResetReflectionDatabaseResponse {
  success: boolean
  message: string
}
```

**When to use**: When you need to wipe local reflection data for a fresh start

## Response Patterns

### Success Response

```typescript
interface SuccessResponse {
  success: true
  // Tool-specific data
}
```

### Error Response

```typescript
interface ErrorResponse {
  success: false
  error: string
  error_code?: string
  suggestions?: string[]
}
```

### Chunked Response (Large Results)

```typescript
interface ChunkedResponse {
  success: true
  chunked: true
  current_chunk: number
  total_chunks: number
  cache_key: string
  // Partial tool-specific data
}
```

## AI Integration Best Practices

### 1. Session Lifecycle Management

```typescript
// Always start sessions with start
await mcp_tool("mcp__session-buddy__start", {
  working_directory: "/path/to/project"
})

// Regular checkpoints during development
await mcp_tool("mcp__session-buddy__checkpoint", {})

// Always end sessions cleanly
await mcp_tool("mcp__session-buddy__end", {})
```

### 2. Context-Aware Development

```typescript
// Before starting new work, search for related context
const context = await mcp_tool("mcp__session-buddy__quick_search", {
  query: "authentication implementation",
  min_score: 0.75
})

if (context.success && context.top_result) {
  // Use context to inform current implementation
}
```

### 3. Knowledge Building

```typescript
// After solving complex problems
await mcp_tool("mcp__session-buddy__store_reflection", {
  content: "Implemented JWT refresh token rotation with Redis storage. Key insight: Use sliding window expiration to balance security and UX.",
  tags: ["authentication", "jwt", "redis", "security"]
})
```

### 4. Progressive Search Strategy

```typescript
// Start with quick search
const quick = await mcp_tool("mcp__session-buddy__quick_search", {
  query: "database migration patterns"
})

if (quick.has_more) {
  // Get more detailed results
  const detailed = await mcp_tool("mcp__session-buddy__get_more_results", {
    query: "database migration patterns",
    limit: 10
  })
}
```

## Error Handling

### Common Error Codes

- `MEMORY_UNAVAILABLE`: Embedding system not initialized
- `PROJECT_NOT_FOUND`: Working directory not accessible
- `SEARCH_FAILED`: Database query failed
- `PERMISSION_DENIED`: Insufficient access rights

### Graceful Degradation

The MCP server is designed to degrade gracefully:

- Semantic search falls back to text search when embeddings unavailable
- Tools continue working even if memory system fails
- Project analysis works without Git repository

### Retry Patterns

```typescript
async function robustSearch(query: string, retries = 2) {
  for (let i = 0; i <= retries; i++) {
    try {
      const result = await mcp_tool("mcp__session-buddy__quick_search", { query })
      if (result.success) return result
    } catch (error) {
      if (i === retries) throw error
      await delay(1000 * (i + 1)) // Exponential backoff
    }
  }
}
```

## Performance Considerations

### Token Optimization

- Responses >4000 tokens are automatically chunked
- Use `quick_search` before full searches to minimize token usage
- Search results include similarity scores to help filter relevance

### Database Performance

- Semantic search is optimized with vector indices
- Text search fallback uses FTS5 full-text search
- Connection pooling minimizes database overhead

### Memory Usage

- ONNX models are loaded lazily and cached
- Embedding generation uses executor threads to prevent blocking
- Conversation storage includes automatic cleanup of old entries

______________________________________________________________________

**Next Steps**: See [AI Integration Patterns](../features/AI_INTEGRATION.md) for detailed usage examples and workflow patterns.
