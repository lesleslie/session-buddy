# Prompt Adapter Decision - Quick Reference

## Recommendation: Option C (Hybrid)

**Vote:** ✅ **STRONG RECOMMENDATION**

## One-Liner Summary

Place interfaces in `mcp-common`, implementations in `Mahavishnu` - matches existing patterns, no circular dependencies, clean testing.

## Architecture Diagram

```
Foundation (mcp-common)          Services (Mahavishnu, etc.)
┌─────────────────────┐          ┌─────────────────────────────┐
│ PromptAdapterProtocol│ ←───────│ Implementation classes       │
│ PromptRequest       │          │ - PyObjCPromptAdapter        │
│ PromptResponse      │          │ - TUIPromptAdapter           │
│ NotificationRequest │          │ - factory.create_adapter()   │
└─────────────────────┘          └─────────────────────────────┘
         ↑                                  ↑
         │ Imports from                     │ Imports from
         │ mcp_common                       │ mcp_common + implements
```

## Why Not Option A (Oneiric)?

**Problem:** Violates role taxonomy

```python
# WRONG: Orchestrator depending on Resolver
from oneiric.modes.prompt import PromptAdapter  # ❌ Circular dependency

# Mahavishnu (orchestrator) should NOT depend on Oneiric (resolver)
# Role taxonomy says: Orchestrator coordinates, Resolver resolves
```

## Why Not Option B (mcp-common-only)?

**Problem:** Violates single responsibility + bloats foundation

```python
# WRONG: Foundation carrying platform-specific code
from mcp_common.ui.prompt_adapter import PromptAdapter  # Forces PyObjC on Linux servers

# mcp-common is for MCP PROTOCOL, not PLATFORM implementation
# Would require all services to install PyObjC (even Linux servers)
```

## Why Option C (Hybrid) Works

### 1. Matches Existing Patterns

```python
# Current pattern (proven to work)
from mcp_common.code_graph import CodeGraphAnalyzer  # Interface/factory
analyzer = CodeGraphAnalyzer(repo_path)  # Service creates instance

# Proposed pattern (same approach)
from mcp_common.interfaces.prompt import PromptAdapterProtocol  # Interface
adapter = MahavishnuPromptAdapter(backend="pyobjc")  # Service creates instance
```

### 2. Clean Import Flow

```python
# All imports flow toward foundation (no circles)

# Mahavishnu → mcp-common
from mcp_common.interfaces.prompt import PromptAdapterProtocol

# Session-Buddy → mcp-common
from mcp_common.interfaces.prompt import PromptAdapterProtocol

# Oneiric → mcp-common (if needed)
from mcp_common.interfaces.prompt import PromptAdapterProtocol
```

### 3. Easy Testing

```python
# Unit tests: Mock the protocol
class MockPromptAdapter(PromptAdapterProtocol):
    async def prompt(self, request):
        return PromptResponse(submitted=True, value="test")

# Integration tests: Test real backends
@pytest.mark.parametrize("backend", ["pyobjc", "tui"])
async def test_backend(backend):
    adapter = create_backend(backend)
    result = await adapter.prompt("Test")
```

### 4. Deployment Flexibility

```bash
# macOS: Install PyObjC backend
pip install mahavishnu[prompt-pyobjc]

# Linux: Install TUI backend only
pip install mahavishnu[prompt-core]

# Docker: Skip entirely
ENV MAHAVISHNU_PROMPT__ENABLED=false
```

## File Structure

```
mcp-common/
└── mcp_common/
    └── interfaces/
        └── prompt.py          # Protocol + dataclasses

mahavishnu/
├── mahavishnu/
│   ├── ui/
│   │   ├── prompt_adapter.py      # Factory + base class
│   │   └── backends/
│   │       ├── pyobjc_backend.py   # macOS native
│   │       └── tui_backend.py      # Terminal (prompt-toolkit)
│   └── integrations/
│       └── prompt_integration.py   # Service-level wiring
└── settings/
    └── mahavishnu.yaml             # Configuration
```

## Implementation Time

- **Phase 1 (mcp-common):** 1 day - Protocols + dataclasses
- **Phase 2 (Mahavishnu):** 2-3 days - Backend implementations
- **Phase 3 (Integration):** 1 day - Wire into app
- **Phase 4 (Tests):** 2 days - Unit + integration tests
- **Phase 5 (Docs):** 1 day - API + user docs

**Total:** ~8 days

## Decision Matrix

| Criteria | Option A (Oneiric) | Option B (mcp-common) | Option C (Hybrid) |
|----------|-------------------|----------------------|-------------------|
| Circular Dependencies | ❌ YES | ✅ No | ✅ No |
| Import Consistency | ❌ Breaks patterns | ⚠️ Bloats foundation | ✅ Matches patterns |
| Testing | ❌ Complex mocks | ⚠️ Foundation bloat | ✅ Easy to mock |
| Deployment | ❌ Tight coupling | ❌ Heavy deps | ✅ Flexible |
| Role Compliance | ❌ Violates | ⚠️ Gray area | ✅ Compliant |
| Platform Isolation | ❌ Coupled | ❌ No isolation | ✅ Isolated |
| Implementation Time | 5 days | 6 days | 8 days |
| Maintenance Burden | High (Oneiric) | High (Foundation) | Low (Service) |

## Recommendation

**Choose Option C (Hybrid)**

**Rationale:**
1. ✅ Zero circular dependencies
2. ✅ Matches existing CodeGraphAnalyzer pattern
3. ✅ Clean testing (mock protocol, test implementations)
4. ✅ Flexible deployment (platform-specific backends)
5. ✅ Single responsibility (foundation = protocol, service = implementation)
6. ✅ Role taxonomy compliance (Mahavishnu owns implementation)

**Next Steps:**
1. Review architecture decision document
2. Approve Phase 1 (mcp-common interfaces)
3. Implement Phase 2 (Mahavishnu backends)
4. Add comprehensive tests
5. Update documentation

---

**Status:** ✅ **RECOMMENDED**
**Confidence:** 95%
**Architect:** Backend Developer (Claude Sonnet 4.5)
**Date:** 2025-02-09
