# Akosha Sync Implementation Plan

**Status**: 📋 Planning - Awaiting Agent Reviews
**Created**: 2026-02-08
**Effort Estimate**: 16-24 hours
**Priority**: High (architectural alignment)

---

## Executive Summary

Refactor Session-Buddy's Akosha sync from direct HTTP POST to a hybrid cloud + HTTP fallback architecture. This aligns with Akosha's pull-based ingestion design while maintaining dev-friendly simplicity.

**Current State**: Direct HTTP POST to `localhost:8682/mcp/store_memory` (doesn't use Akosha's IngestionWorker)
**Target State**: Cloud upload (S3/R2) with HTTP fallback for dev environments

---

## Problem Statement

### Current Issues

1. **Architectural Mismatch**: Session-Buddy pushes via HTTP, but Akosha pulls from cloud storage
2. **No Integration**: Direct POST bypasses Akosha's `IngestionWorker` and retry queues
3. **Scalability**: Single point of failure, no buffering
4. **Missing Features**: No cloud storage buffer, no retry logic

### User Requirements

- ✅ Global user memory already consolidated in `~/.claude/data/reflection.duckdb` (42MB)
- ✅ Most sessions use same user (no project isolation needed)
- ❌ Avoid `/var` filesystem (no permission issues)
- ✅ Support dev environments (no cloud required)
- ✅ Graceful fallback (cloud → HTTP)

---

## Proposed Solution

### Hybrid Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Session-Buddy                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Global Memory (~/.claude/data/)                             │
│  ├─ reflection.duckdb (42MB)                                 │
│  └─ knowledge_graph.duckdb (58MB)                            │
│                                                              │
│  Sync Trigger (session end / manual)                         │
│    ↓                                                         │
│  HybridAkoshaSync                                            │
│    ├─ Try: Cloud upload (S3/R2)                              │
│    │   └─ CloudMemoryUploader                               │
│    └─ Fallback: HTTP POST (localhost:8682)                  │
│        └─ AkoshaSync (existing)                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
           ↓                    ↓
    ┌──────────┐         ┌──────────┐
    │ Cloud    │         │ HTTP     │
    │ Storage  │         │ Direct   │
    └──────────┘         └──────────┘
         ↓                    ↓
    Akosha IngestionWorker  (bypasses worker)
    (pulls every 30s)
```

---

## Implementation Phases

### Phase 1: Foundation (4 hours)

**Objective**: Create cloud sync infrastructure

#### 1.1 Cloud Memory Uploader Module

**File**: `session_buddy/storage/cloud_sync.py` (new, ~250 lines)

**Key Classes**:
```python
class CloudMemoryUploader:
    """Upload global memory databases to S3/R2 cloud storage."""

    async def upload_memories(
        self,
        upload_reflections: bool = True,
        upload_knowledge_graph: bool = True,
    ) -> dict[str, str]:
        """Upload to systems/{system_id}/"""

    async def _create_manifest(self, uploads: dict) -> None:
        """Create SystemMemoryUploadManifest for Akosha discovery."""
```

**Dependencies**:
- Oneiric S3 adapter (already installed)
- Pydantic validation schemas
- File size checks and retry logic

**Configuration**:
```yaml
akosha_cloud_bucket: "${AKOSHA_CLOUD_BUCKET:-}"
akosha_cloud_endpoint: "${AKOSHA_CLOUD_ENDPOINT:-}"
akosha_cloud_region: "${AKOSHA_CLOUD_REGION:-auto}"
akosha_system_id: "${AKOSHA_SYSTEM_ID:-${HOSTNAME:-}}"
```

#### 1.2 Update Settings Schema

**File**: `session_buddy/settings.py`

**Add Fields**:
```python
# Akosha Cloud Sync
akosha_cloud_bucket: str = Field(default="")
akosha_cloud_endpoint: str = Field(default="")
akosha_cloud_region: str = Field(default="auto")
akosha_system_id: str = Field(default="")
akosha_upload_on_session_end: bool = Field(default=True)
```

---

### Phase 2: Hybrid Sync (6 hours)

**Objective**: Implement graceful fallback pattern

#### 2.1 Hybrid Sync Orchestrator

**File**: `session_buddy/storage/akosha_sync.py` (new, ~300 lines)

**Key Classes**:
```python
class HybridAkoshaSync:
    """Hybrid sync with cloud + HTTP fallback."""

    async def sync_memories(
        self,
        force_method: Literal["cloud", "http", "auto"] = "auto",
    ) -> dict[str, Any]:
        """Auto: Try cloud → fallback to HTTP"""

    async def _sync_auto(self) -> dict[str, Any]:
        """Automatic fallback logic"""

    async def _check_cloud_available(self) -> bool:
        """Detect cloud configuration"""

    async def _check_http_available(self) -> bool:
        """Detect HTTP configuration"""
```

**Features**:
- Automatic method detection
- Graceful fallback with logging
- Method tracking for observability
- Error handling without data loss

#### 2.2 Deprecate Old HTTP Sync

**File**: `session_buddy/sync.py` (modify existing)

**Changes**:
```python
# Add deprecation warning
class AkoshaSync:
    """[DEPRECATED] Use HybridAkoshaSync instead.

    Migration:
        OLD: sync = AkoshaSync(embedding_service)
        NEW: sync = HybridAkoshaSync()

    This class is now used internally as HTTP fallback.
    """
```

**Keep Functionality**:
- All existing HTTP sync code
- Tests continue passing
- No breaking changes

---

### Phase 3: Integration (4 hours)

**Objective**: Wire into Session-Buddy lifecycle

#### 3.1 Session End Hook

**File**: `session_buddy/server.py` (modify existing)

**Changes**:
```python
# In end_session() lifecycle
async def end_session():
    # ... existing cleanup ...

    # Upload to Akosha if enabled
    if settings.akosha_sync_enabled and settings.akosha_upload_on_session_end:
        from session_buddy.storage.akosha_sync import sync_to_akosha

        try:
            result = await sync_to_akosha(method="auto")
            logger.info(f"✅ Akosha sync: {result['method']}")
        except Exception as e:
            logger.warning(f"⚠️ Akosha sync failed: {e}")
            # Don't fail session end on sync error
```

#### 3.2 MCP Tool

**File**: `session_buddy/mcp/tools/memory/akosha_tools.py` (new)

**Tool**:
```python
@mcp.tool()
async def sync_to_akosha(
    method: str = "auto",
    enable_fallback: bool = True,
) -> dict[str, Any]:
    """Sync memories to Akosha with automatic fallback.

    Examples:
        # Automatic: Try cloud → HTTP
        await sync_to_akosha()

        # Force HTTP (dev mode)
        await sync_to_akosha(method="http")

        # Cloud only, no fallback
        await sync_to_akosha(method="cloud", enable_fallback=False)
    """
```

---

### Phase 4: Testing (6 hours)

**Objective**: Comprehensive test coverage

#### 4.1 Unit Tests

**File**: `tests/unit/test_cloud_sync.py` (new)

**Test Cases**:
- ✅ Cloud uploader initialization
- ✅ File upload with retry
- ✅ Manifest creation
- ✅ System ID detection
- ✅ Error handling (missing bucket, auth failures)

**Coverage**: 90%+

#### 4.2 Integration Tests

**File**: `tests/integration/test_akosha_sync.py` (new)

**Test Cases**:
- ✅ Hybrid sync with cloud available
- ✅ Hybrid sync with HTTP fallback
- ✅ Hybrid sync with no methods available
- ✅ Forced method selection
- ✅ Session end integration
- ✅ MCP tool execution

**Coverage**: 85%+

#### 4.3 Performance Tests

**File**: `tests/performance/test_sync_performance.py` (new)

**Benchmarks**:
- Cloud upload time (42MB file)
- HTTP sync time (1000 memories)
- Fallback latency
- Memory usage during upload

---

### Phase 5: Documentation (4 hours)

**Objective**: Clear user and developer docs

#### 5.1 User Documentation

**File**: `docs/user/AKOSHA_SYNC_GUIDE.md` (new)

**Sections**:
- Quick start (cloud + dev setup)
- Configuration options
- Environment variables
- Troubleshooting
- FAQ

#### 5.2 Developer Documentation

**File**: `docs/developer/AKOSHA_SYNC_ARCHITECTURE.md` (new)

**Sections**:
- Architecture diagrams
- Class relationships
- Error handling strategy
- Testing patterns
- Migration guide

#### 5.3 Update README

**File**: `README.md` (modify)

**Add Section**:
```markdown
## Akosha Integration

Session-Buddy integrates with Akosha for cross-system memory aggregation.

- **Production**: Cloud sync (S3/R2) for scalability
- **Development**: HTTP sync fallback for simplicity
- **Automatic**: Graceful fallback between methods

See [Akosha Sync Guide](docs/user/AKOSHA_SYNC_GUIDE.md) for details.
```

---

## Configuration Matrix

| Environment | Cloud Config | HTTP Config | Result |
|-------------|--------------|-------------|--------|
| **Production** | `AKOSHA_CLOUD_BUCKET` set | Default | Cloud sync ✅ |
| **Production + Fallback** | Cloud set | `ENABLE_FALLBACK=true` | Cloud → HTTP if fails |
| **Production (Strict)** | Cloud set | `ENABLE_FALLBACK=false` | Cloud only ❌ if fails |
| **Dev (Default)** | Not set | Default | HTTP sync ✅ |
| **Dev (Cloud Test)** | Test bucket set | Default | Cloud sync ✅ |
| **Offline** | Not set | Akosha not running | No sync (logged) |

---

## Migration Strategy

### For Existing Users

**No Breaking Changes**:
- Existing HTTP sync continues working
- Cloud sync is opt-in (set env var to enable)
- Automatic fallback if cloud unavailable

**Migration Path**:
1. Current deployment: HTTP sync (unchanged)
2. Add cloud bucket: Automatic cloud sync
3. Remove HTTP sync: Disable fallback

### For New Users

**Recommended Setup**:
```bash
# Production
export AKOSHA_CLOUD_BUCKET="session-buddy-memories"
export AKOSHA_CLOUD_ENDPOINT="https://..."
export AKOSHA_ENABLE_FALLBACK="true"  # Safety net

# Dev
# No config needed - uses HTTP sync to localhost
```

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cloud dependency | High | HTTP fallback enabled by default |
| Breaking existing setups | High | Zero breaking changes, opt-in cloud |
| Performance regression | Medium | Benchmarks, upload optimization |
| Auth failures | Medium | Retry logic, clear error messages |
| Test coverage gaps | Low | Comprehensive test plan |

---

## Success Criteria

### Functional
- ✅ Cloud sync uploads 42MB database successfully
- ✅ HTTP fallback works when cloud unavailable
- ✅ Akosha IngestionWorker discovers uploads
- ✅ Session end triggers sync (when enabled)
- ✅ MCP tool works with all methods

### Non-Functional
- ✅ 90%+ test coverage
- ✅ All tests passing
- ✅ Zero breaking changes
- ✅ Clear logging and observability
- ✅ Documentation complete

### Performance
- ✅ Cloud upload < 30 seconds (42MB file)
- ✅ HTTP fallback < 60 seconds (1000 memories)
- ✅ No memory leaks during upload
- ✅ Session end not blocked by sync failures

---

## Open Questions

1. **Upload Frequency**: Session end only, or periodic?
   - **Recommendation**: Session end + manual trigger
   - **Rationale**: Simpler, less resource usage

2. **Incremental vs Full**: Upload full DB or incremental changes?
   - **Recommendation**: Full DB (simpler, more reliable)
   - **Rationale**: 42MB is manageable, Akosha handles deduplication

3. **Retry Strategy**: How many retries on cloud failure?
   - **Recommendation**: 3 retries with exponential backoff
   - **Rationale**: Balance reliability vs speed

4. **Manifest Format**: Match Akosha's `SystemMemoryUploadManifest`?
   - **Recommendation**: Yes, exact schema match
   - **Rationale**: Compatibility with IngestionWorker

---

## Timeline

| Phase | Duration | Dependencies | Deliverable |
|-------|----------|--------------|-------------|
| Phase 1: Foundation | 4h | None | Cloud sync module |
| Phase 2: Hybrid Sync | 6h | Phase 1 | Hybrid orchestrator |
| Phase 3: Integration | 4h | Phase 2 | MCP tool + hooks |
| Phase 4: Testing | 6h | Phase 3 | Test suite |
| Phase 5: Documentation | 4h | Phase 4 | User + dev docs |
| **Total** | **24h** | - | Production-ready feature |

---

## Dependencies

### External
- ✅ Oneiric (already installed)
- ✅ Pydantic (already installed)
- ✅ Akosha (separate project, pull-based ingestion)

### Internal
- ✅ Session paths (`~/.claude/data/`)
- ✅ Settings system
- ✅ MCP tool framework
- ✅ Logging infrastructure

---

## Agent Review Checklist

When reviewing this plan, agents should verify:

- **Architecture**: Aligns with Akosha's pull-based design
- **Code Quality**: Type hints, docstrings, error handling
- **Testing**: Comprehensive coverage, edge cases
- **Documentation**: Clear for users and developers
- **Performance**: No regressions, acceptable latency
- **Security**: No hardcoded credentials, proper auth
- **Compatibility**: Zero breaking changes

---

## Next Steps

1. ✅ Create implementation plan (this document)
2. **Await agent reviews** (7 agents)
3. Address feedback and revise plan
4. Begin Phase 1 implementation
5. Continuous testing and validation

---

**Document Version**: 1.0
**Last Updated**: 2026-02-08
**Status**: 🔄 Awaiting Reviews
