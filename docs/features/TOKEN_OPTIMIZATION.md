# Token Optimization Features

This document describes the comprehensive token optimization system implemented in the session-buddy server to reduce token usage and costs while maintaining functionality.

## Overview

The token optimization system provides multiple strategies to reduce token consumption in conversation search, memory retrieval, and response generation. It includes automatic optimization, intelligent chunking, and detailed usage tracking.

## Core Components

### 1. TokenOptimizer Class (`session_buddy/token_optimizer.py`)

The main optimization engine that provides:

- **Token Counting**: Accurate token counting using tiktoken (GPT-4 encoding)
- **Multiple Optimization Strategies**: 5 different approaches to reduce token usage
- **Response Chunking**: Automatic splitting of large responses
- **Usage Tracking**: Comprehensive metrics and cost estimation
- **Cache Management**: Temporary storage for chunked responses

#### Optimization Strategies

1. **`truncate_old`**: Prioritizes recent conversations and truncates older content
1. **`summarize_content`**: Auto-summarizes long conversations while preserving key information
1. **`prioritize_recent`**: Scores conversations by recency, relevance, and technical content
1. **`filter_duplicates`**: Removes duplicate or very similar conversations
1. **`chunk_response`**: Splits large result sets into manageable chunks

### 2. MCP Tool Integration

Token optimization is implemented as an internal helper and is not currently exposed as a public MCP tool. It is used by internal workflows and can be accessed directly from Python via `session_buddy.token_optimizer`.

### 3. Status Reporting

The `status` tool now includes token optimization information:

```
⚡ Token Optimization:
• get_cached_chunk - Retrieve chunked response data
• get_token_usage_stats - Token usage and savings metrics
• optimize_memory_usage - Consolidate old conversations
• Built-in response chunking and truncation
• Last 24h savings: $0.0125 USD, 1,250 tokens
• Active cached chunks: 3
```

## Usage Examples

### Basic Optimization

```python
# Optimize a result set directly
from session_buddy.token_optimizer import TokenOptimizer

optimizer = TokenOptimizer()
optimized_results, optimization_info = await optimizer.optimize_search_results(
    results,
    max_tokens=2000,
)
```

### Chunked Responses

When responses are large, they're automatically chunked:

```python
# First request returns chunk 1 + cache_key
optimized_results, optimization_info = await optimizer.optimize_search_results(
    results,
    max_tokens=500,
)
```

### Usage Analytics

```python
# View token usage and savings
from session_buddy.token_optimizer import get_token_usage_stats

stats = await get_token_usage_stats(hours=24)
# Shows: requests, tokens used, optimizations applied, estimated cost savings
```

## Token Savings Strategies

### 1. Content Truncation

- **Smart Truncation**: Preserves sentence boundaries when possible
- **Age-Based Priority**: Recent conversations get higher priority
- **Minimum Retention**: Always keeps at least 3 recent conversations

### 2. Content Summarization

- **Extractive Summarization**: Selects most important sentences
- **Template-Based**: Uses patterns to create structured summaries
- **Technical Content Preservation**: Prioritizes code, errors, and solutions

### 3. Response Chunking

- **Automatic Chunking**: Splits responses exceeding token limits
- **Intelligent Caching**: 1-hour cache with automatic cleanup
- **Pagination Support**: Easy navigation through large result sets

### 4. Duplicate Filtering

- **Content Hashing**: Identifies similar conversations
- **Normalized Comparison**: Handles whitespace and formatting differences
- **Preservation Logic**: Keeps most recent of duplicate conversations

### 5. Priority Scoring

Conversations are scored based on:

- **Recency** (0-0.5 points): Newer conversations score higher
- **Relevance** (0-0.3 points): Semantic similarity to query
- **Technical Content** (0-0.2 points): Presence of code, errors, functions
- **Length Penalty** (0 to -0.2 points): Very long content gets penalty

## Performance Characteristics

### Token Counting Performance

- **Small texts (100 chars)**: \<1ms
- **Medium texts (1,000 chars)**: \<5ms
- **Large texts (10,000 chars)**: \<50ms

### Optimization Strategy Performance

- **Truncation**: ~1ms per conversation
- **Prioritization**: ~2ms per conversation
- **Summarization**: ~10ms per conversation
- **Deduplication**: ~3ms per conversation

### Memory Usage

- **Base memory overhead**: ~5MB
- **Per 1,000 conversations**: ~2MB additional
- **Cache overhead**: ~1KB per cached chunk

## Configuration Options

### TokenOptimizer Initialization

```python
optimizer = TokenOptimizer(
    max_tokens=4000,  # Default token limit
    chunk_size=2000,  # Size of each chunk
)
```

### Retention Policies (Memory Optimization)

```python
policy = {
    "max_age_days": 365,  # Keep conversations for 1 year
    "max_conversations": 10000,  # Maximum total conversations
    "importance_threshold": 0.3,  # Minimum score to keep
    "consolidation_age_days": 30,  # Consolidate after 30 days
    "compression_ratio": 0.5,  # Target 50% size reduction
}
```

## Cost Savings

### Typical Savings by Strategy

- **Truncation**: 20-40% token reduction
- **Summarization**: 30-60% token reduction
- **Prioritization**: 15-35% token reduction
- **Deduplication**: 5-25% token reduction (depends on duplicate rate)
- **Combined**: 40-70% token reduction

### Cost Estimation

Based on GPT-4 pricing (~$0.01 per 1K tokens):

- **100 optimized requests/day**: ~$0.50-2.00 daily savings
- **1,000 optimized requests/day**: ~$5.00-20.00 daily savings
- **Annual savings**: $180-7,300 depending on usage

## Testing Coverage

### Unit Tests (`tests/unit/test_token_optimizer.py`)

- Token counting accuracy and performance
- All optimization strategies with various inputs
- Edge cases and error handling
- Cache operations and cleanup
- Usage metrics and statistics

### Integration Tests (`tests/integration/test_token_optimization_mcp.py`)

- MCP tool integration
- End-to-end optimization workflows
- Error handling and fallback behavior
- Async operation correctness

### Performance Tests (`tests/performance/test_token_optimization_performance.py`)

- Scalability with large datasets (1,000+ conversations)
- Memory usage efficiency
- Concurrent optimization performance
- Benchmarks across different dataset sizes

## Dependencies

### Required

- `tiktoken>=0.5.0` - Token counting
- `fastmcp>=2.0.0` - MCP server framework
- `duckdb>=0.9.0` - Conversation storage

### Optional (for advanced features)

- `psutil>=5.9.0` - Memory usage monitoring (testing)
- `onnxruntime` - Semantic search embeddings
- `transformers` - Text processing utilities

## Future Enhancements

### Planned Features

1. **Adaptive Optimization**: Learn from usage patterns to optimize strategy selection
1. **Real-time Cost Monitoring**: Live token usage dashboards
1. **Custom Summarization**: User-defined summary templates
1. **Compression Analytics**: Detailed breakdown of optimization effectiveness
1. **Smart Prefetching**: Predict and pre-optimize likely queries

### Integration Opportunities

- **Claude API Integration**: Direct token usage monitoring
- **Usage-based Billing**: Automatic cost tracking and alerts
- **Team Analytics**: Multi-user optimization reporting
- **CI/CD Integration**: Automated optimization in development workflows

## Security and Privacy

### Data Handling

- **No External Calls**: All optimization runs locally
- **Temporary Caching**: Chunks expire after 1 hour
- **Privacy Preservation**: No conversation data leaves the local system
- **Audit Trail**: Full logging of optimization operations

### Performance Monitoring

- **Non-intrusive**: Minimal performance impact (\<5ms overhead)
- **Optional Tracking**: Usage statistics can be disabled
- **Local Storage**: All metrics stored in local DuckDB database

______________________________________________________________________

## Quick Start

1. **Install dependencies**:

   ```bash
   uv add tiktoken
   ```

1. **Optimize a search result set**:

   ```python
   from session_buddy.token_optimizer import TokenOptimizer

   optimizer = TokenOptimizer()
   optimized_results, optimization_info = await optimizer.optimize_search_results(
       results,
       max_tokens=2000,
   )
   ```

1. **Monitor usage**:

   ```python
   stats = await get_token_usage_stats()
   ```

The token optimization system is designed to be transparent, efficient, and cost-effective while preserving the quality and usefulness of conversation search and memory features.
