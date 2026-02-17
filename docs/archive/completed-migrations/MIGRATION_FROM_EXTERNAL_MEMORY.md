# Migration from External Memory Server

**Purpose**: Import existing knowledge graph data from `@modelcontextprotocol/server-memory` or `mcp-knowledge-graph` JSONL files into the new DuckPGQ-based knowledge graph.

______________________________________________________________________

## Overview

This migration script will be implemented in **Phase 5** of the knowledge graph implementation plan.

### What Gets Migrated

From external memory JSONL files:

- ✅ **Entities** (nodes with names, types, observations)
- ✅ **Relations** (edges between entities)
- ✅ **Observations** (facts attached to entities)
- ✅ **Metadata** (source tracking, timestamps)

### JSONL Format Examples

**Entity format:**

```json
{"type":"entity","name":"session-buddy","entityType":"project","observations":["MCP server","Session management","DuckDB storage"]}
```

**Relation format:**

```json
{"type":"relation","from":"session-buddy","to":"ACB","relationType":"uses"}
```

______________________________________________________________________

## Migration Script Specifications

### File Location

`scripts/migrate_from_external_memory.py`

### Command-Line Interface

```bash
# Dry-run (preview what would be imported)
python scripts/migrate_from_external_memory.py --dry-run

# Migrate from specific directory
python scripts/migrate_from_external_memory.py --projects ~/Projects

# Migrate specific file
python scripts/migrate_from_external_memory.py --file ~/Projects/crackerjack/memory.jsonl

# Verbose output
python scripts/migrate_from_external_memory.py --verbose

# Skip duplicates (don't error on existing entities)
python scripts/migrate_from_external_memory.py --skip-duplicates
```

### Features

1. **Auto-discovery**

   - Scans all projects in `~/Projects/` by default
   - Finds all `memory*.jsonl` files
   - Detects both `@modelcontextprotocol/server-memory` and `mcp-knowledge-graph` formats

1. **Safety markers detection**

   - Recognizes `mcp-knowledge-graph` safety markers
   - Skips marker lines automatically
   - Validates JSONL format before import

1. **Deduplication**

   - Checks if entity already exists by name + type
   - Updates existing entities (adds new observations)
   - Creates new entities only if not found
   - For relations: creates only if exact triplet doesn't exist

1. **Import statistics**

   - Count of files processed
   - Entities created vs updated
   - Relations created
   - Errors encountered
   - Full import report

1. **Error handling**

   - Continues on individual record errors
   - Logs all errors to file
   - Final success/failure summary
   - Rollback capability on critical errors

______________________________________________________________________

## Post-Migration Cleanup

After successful migration:

1. **Verify data quality**
1. **Remove external memory servers from .mcp.json**
1. **Backup migrated JSONL files**

______________________________________________________________________

**Status**: Planned for Phase 5 implementation
**Duration**: ~2-3 hours to implement and test
