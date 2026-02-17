# Session-Buddy Lite Mode Implementation Plan

## Executive Summary

Create operational modes for Session-Buddy to simplify setup and deployment, similar to Mahavishnu's mode system.

## Current Architecture Analysis

### Database Layer
- **Primary Database**: DuckDB (`~/.claude/data/reflection.duckdb`)
- **Embedding System**: ONNX Runtime (all-MiniLM-L6-v2)
- **Dependencies**: duckdb, onnxruntime, transformers, numpy

### Storage Layer
- **File Storage**: Local filesystem (`~/.claude/data/sessions`)
- **Optional Backends**: S3, Azure, GCS, Memory

### Key Findings
1. **No PostgreSQL dependency** - Session-Buddy uses DuckDB (embedded)
2. **Already lightweight** - No external database service required
3. **Current complexity**: Multiple optional features and storage backends

## Proposed Mode System

### Lite Mode (NEW)
- **Purpose**: Zero-dependency development mode
- **Database**: In-memory DuckDB (`:memory:`)
- **Storage**: In-memory storage
- **Features**: Core session management only
- **Setup Time**: < 2 minutes
- **Ideal For**: Quick testing, development, CI/CD

### Standard Mode (Default)
- **Purpose**: Full-featured production mode
- **Database**: File-based DuckDB (`~/.claude/data/reflection.duckdb`)
- **Storage**: File-based storage
- **Features**: All features enabled
- **Setup Time**: ~ 5 minutes
- **Ideal For**: Daily development, production

## Feature Comparison Matrix

| Feature | Lite Mode | Standard Mode |
|---------|-----------|---------------|
| **Setup Time** | < 2 min | ~ 5 min |
| **Services** | 1 (Session-Buddy) | 1 (Session-Buddy) |
| **Persistence** | In-memory (ephemeral) | File-based (persistent) |
| **Database** | `:memory:` | `~/.claude/data/reflection.duckdb` |
| **Storage** | In-memory | File-based |
| **Embeddings** | Disabled (optional) | Enabled (ONNX) |
| **Multi-Project** | Disabled | Enabled |
| **Token Optimization** | Disabled | Enabled |
| **Auto-Checkpoint** | Disabled | Enabled |
| **Ideal For** | Testing, CI/CD | Development, Production |

## Implementation Phases

### Phase 1: Create Mode System (2 days)
- [ ] Create `session_buddy/modes/` directory
- [ ] Create `base.py` - Base mode interface
- [ ] Create `lite.py` - Lite mode implementation
- [ ] Create `standard.py` - Standard mode implementation

### Phase 2: Create Configuration (1 day)
- [ ] Create `settings/lite.yaml` - Lite mode config
- [ ] Create `settings/standard.yaml` - Standard mode config
- [ ] Update `settings/session-buddy.yaml` - Base config

### Phase 3: Update Database Layer (1 day)
- [ ] Update `ReflectionDatabase` to support mode-based initialization
- [ ] Add in-memory database support for lite mode
- [ ] Add mode-specific configuration

### Phase 4: CLI Integration (1 day)
- [ ] Update `session_buddy/cli.py` with `--mode` parameter
- [ ] Add mode detection from environment/config
- [ ] Add mode validation

### Phase 5: Create Startup Script (1 day)
- [ ] Create `scripts/dev-start.sh` script
- [ ] Add mode parameter support
- [ ] Add pre-flight checks

### Phase 6: Documentation (1 day)
- [ ] Create `docs/guides/operational-modes.md`
- [ ] Update README with mode comparison
- [ ] Create migration guide

## Success Criteria

- [ ] Lite mode works with in-memory database
- [ ] Standard mode works with file-based database
- [ ] CLI integration complete with `--mode` parameter
- [ ] Startup script created and tested
- [ ] Documentation created and reviewed

## Key Design Decisions

### 1. No PostgreSQL Required
Unlike Mahavishnu, Session-Buddy already uses DuckDB (embedded database). No external database service needed.

### 2. Mode-Based Configuration
Modes will be selected via:
- CLI parameter: `--mode=lite` or `--mode=standard`
- Environment variable: `SESSION_BUDDY_MODE=lite`
- Configuration file: `settings/session-buddy.yaml`

### 3. Feature Flags
Lite mode will disable heavy features:
- Embeddings (ONNX model loading)
- Multi-project coordination
- Token optimization
- Auto-checkpoint

### 4. Database Path Selection
- Lite: `:memory:` (ephemeral, fast startup)
- Standard: `~/.claude/data/reflection.duckdb` (persistent)

### 5. Storage Backend Selection
- Lite: `memory` (in-memory storage)
- Standard: `file` (filesystem storage)

## Testing Strategy

1. **Unit Tests**: Test mode selection and configuration
2. **Integration Tests**: Test database initialization per mode
3. **E2E Tests**: Test full session lifecycle in each mode
4. **Performance Tests**: Verify lite mode startup time < 2 seconds

## Migration Path

Users can migrate from Lite to Standard mode by:
1. Exporting data from lite mode (if needed)
2. Changing mode parameter
3. Restarting Session-Buddy

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data loss in lite mode | High | Clear warnings, no persistence by design |
| Mode switching complexity | Medium | Clear documentation, validation |
| Feature inconsistency | Medium | Feature flags per mode |
| Configuration drift | Low | Base config + mode overrides |

## Timeline

- **Phase 1**: 2 days (Mode system)
- **Phase 2**: 1 day (Configuration)
- **Phase 3**: 1 day (Database layer)
- **Phase 4**: 1 day (CLI integration)
- **Phase 5**: 1 day (Startup script)
- **Phase 6**: 1 day (Documentation)

**Total**: 7 days

## Next Steps

1. Review and approve this plan
2. Begin Phase 1 implementation
3. Create progress tracking document
