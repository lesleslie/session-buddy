# ACB Templates Adapter Proposal

**Created:** 2025-01-25
**Status:** Proposal for ACB Framework Enhancement
**Target:** acb/adapters/templates/

______________________________________________________________________

## Executive Summary

**Recommendation: YES - Build a templates adapter in ACB**

This is a **high-value, cross-cutting infrastructure component** that would benefit multiple projects (session-buddy, fastblocks, and future ACB users). The investment is justified by:

1. **Pattern Reuse**: Template rendering with DI + async is needed across multiple projects
1. **Standardization**: ACB should provide battle-tested infrastructure components
1. **Simplified Implementation**: Much simpler than fastblocks (no cloud storage, HTMY integration, etc.)
1. **Framework Philosophy**: Elevates repeated patterns to framework level

______________________________________________________________________

## Problem Statement

### Current State

**Projects independently implement template rendering:**

- **fastblocks**: Complex 37KB `jinja2.py` adapter with Redis caching, cloud storage, HTMY integration
- **session-buddy**: About to implement template rendering for Phase 3.1 (128 formatting functions → templates)
- **Future ACB projects**: Will all need similar template rendering capabilities

### Pain Points

1. **Code Duplication**: Each project reimplements Jinja2 + async + DI patterns
1. **Inconsistency**: Different projects use different template patterns
1. **Maintenance Burden**: Bug fixes must be replicated across projects
1. **Learning Curve**: New ACB users must figure out template integration themselves

______________________________________________________________________

## Proposed Solution

### Create `acb.adapters.templates`

A **lightweight, async-first Jinja2 adapter** following ACB patterns:

```python
# acb/adapters/templates/__init__.py
from acb.depends import depends
from jinja2_async_environment import AsyncEnvironment
from jinja2 import FileSystemLoader, select_autoescape


class TemplatesAdapter:
    """Async Jinja2 template rendering with ACB dependency injection."""

    def __init__(
        self,
        template_dir: Path | None = None,
        enable_async: bool = True,
        autoescape: bool = True,
        cache_size: int = 400,
        auto_reload: bool = True,
    ):
        self.template_dir = template_dir or Path.cwd() / "templates"

        # Configure async Jinja2 environment
        self.env = AsyncEnvironment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]) if autoescape else False,
            enable_async=enable_async,
            cache_size=cache_size,
            auto_reload=auto_reload,
        )

        # Register default filters (extensible)
        self._register_default_filters()

    async def render(
        self,
        template_name: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Render a template asynchronously with context."""
        template = self.env.get_template(template_name)
        merged_context = {**(context or {}), **kwargs}
        return await template.render_async(**merged_context)

    async def render_string(
        self,
        template_string: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Render a template string asynchronously."""
        template = self.env.from_string(template_string)
        merged_context = {**(context or {}), **kwargs}
        return await template.render_async(**merged_context)

    def add_filter(self, name: str, func: Callable[..., Any]) -> None:
        """Register a custom template filter."""
        self.env.filters[name] = func

    def add_global(self, name: str, value: Any) -> None:
        """Register a global variable available in all templates."""
        self.env.globals[name] = value

    def _register_default_filters(self) -> None:
        """Register ACB-specific default filters."""
        # Example: Date formatting, JSON encoding, etc.
        pass
```

### Usage in Projects

```text
# session-buddy or any ACB project
from acb.adapters import import_adapter
from acb.depends import depends

# Configure via DI
templates_adapter = TemplatesAdapter(
    template_dir=Path.cwd() / "session_buddy" / "templates",
    enable_async=True,
)
depends.set("templates", templates_adapter)


# Use in tools
@mcp.tool()
async def generate_report(data: dict[str, Any]) -> str:
    templates = depends.get("templates")
    return await templates.render("report.html", context=data)
```

______________________________________________________________________

## Design Principles

### 1. **Simplicity Over Features**

**Core Focus:**

- Async Jinja2 rendering ✅
- ACB DI integration ✅
- FileSystemLoader by default ✅
- Custom filters/globals support ✅

**Explicitly NOT Included (for v1):**

- Redis bytecode caching (advanced use case)
- Cloud storage loaders (project-specific)
- HTMY component integration (fastblocks-specific)
- Template syntax changes (keep standard Jinja2)
- Multi-layer loader system (over-engineering)

**Rationale:** Start minimal, add features when **multiple projects** need them.

### 2. **Async-First Architecture**

```text
# All rendering is async by default
async def render(...) -> str:
    template = self.env.get_template(template_name)
    return await template.render_async(**context)

# Sync fallback if needed
def render_sync(...) -> str:
    """Synchronous rendering (wraps async)."""
    return asyncio.run(self.render(...))
```

### 3. **DI Integration Pattern**

```python
# Standard ACB dependency registration
from acb.depends import depends

# Option 1: Manual registration
templates = TemplatesAdapter(template_dir=Path("templates"))
depends.set("templates", templates)


# Option 2: Factory function
@depends.provider
def create_templates() -> TemplatesAdapter:
    config = depends.get("config")
    return TemplatesAdapter(
        template_dir=Path(config.templates.dir),
        cache_size=config.templates.cache_size,
    )


# Option 3: Auto-discovery (via ACB adapter system)
templates = import_adapter("templates")
```

### 4. **Extensibility via Composition**

```text
# Projects can extend for advanced features
from acb.adapters.templates import TemplatesAdapter


class RedisTemplatesAdapter(TemplatesAdapter):
    """Extended adapter with Redis bytecode caching."""

    def __init__(self, *args, redis_url: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.bytecode_cache = AsyncRedisBytecodeCache(redis_url)
        self.env.bytecode_cache = self.bytecode_cache


# fastblocks continues using its custom implementation
# session-buddy uses the simple base adapter
```

______________________________________________________________________

## Implementation Plan

### Phase 1: Core Adapter (1-2 days)

**Files to Create:**

```
acb/adapters/templates/
├── __init__.py          # TemplatesAdapter class
├── _filters.py          # Default filter functions
├── _loaders.py          # Custom loader implementations (optional)
└── README.md            # Usage documentation
```

**Core Features:**

1. `TemplatesAdapter` class with async rendering
1. FileSystemLoader configuration
1. Filter/global registration API
1. ACB DI integration
1. Basic error handling

**Dependencies:**

- `jinja2-async-environment>=0.14.3` (handles async Environment)
- `jinja2>=3.1.6` (standard Jinja2)

### Phase 2: Testing & Documentation (1 day)

```
acb/tests/adapters/templates/
├── test_rendering.py           # Basic rendering tests
├── test_async_rendering.py     # Async-specific tests
├── test_filters.py             # Filter registration tests
├── test_di_integration.py      # DI pattern tests
└── conftest.py                 # Test fixtures
```

**Coverage Target:** ≥85%

### Phase 3: Examples & Migration (1 day)

**Create examples:**

```
acb/examples/templates/
├── basic_usage.py              # Simple rendering
├── custom_filters.py           # Filter registration
├── di_integration.py           # Dependency injection
└── templates/
    └── example.html            # Sample template
```

**Migration Guide:**

- Document how to migrate from custom Jinja2 setups
- Show fastblocks vs simple adapter comparison
- Provide session-buddy integration example

### Total Effort: ~3-4 days

______________________________________________________________________

## Comparison: Simple vs Complex

### ACB Templates Adapter (Proposed)

**Size:** ~300-400 lines
**Features:**

- Async Jinja2 rendering
- FileSystemLoader
- Custom filters/globals
- ACB DI integration
- Basic caching (Jinja2 built-in)

**Dependencies:**

- `jinja2-async-environment`
- `jinja2`

### FastBlocks Templates Adapter (Current)

**Size:** ~37,000+ lines (total template system)
**Features:**

- Everything above PLUS:
- Redis bytecode caching
- Cloud storage loaders
- Template synchronization (cache ↔ storage ↔ filesystem)
- HTMY component integration
- Custom delimiters (`[[/]]` instead of `{{/}}`)
- Fragment rendering
- Performance optimization
- Language server integration

**Dependencies:**

- `starlette-async-jinja`
- `jinja2-async-environment`
- `redis`
- Cloud storage clients
- HTMY adapter

### Complexity Ratio

| Aspect | ACB Adapter | FastBlocks Adapter | Ratio |
|--------|-------------|-------------------|-------|
| **Lines of Code** | ~400 | ~37,000+ | 92x simpler |
| **Dependencies** | 2 | 7+ | 3.5x fewer |
| **Features** | Core only | Kitchen sink | Focused |
| **Learning Curve** | 10 minutes | 2-3 hours | 12x easier |
| **Maintenance** | Low | High | Much easier |

______________________________________________________________________

## Benefits Analysis

### For ACB Framework

1. **Standardization** ✅

   - Canonical way to do templates in ACB projects
   - Consistent patterns across ecosystem
   - Reduces "how do I integrate Jinja2?" questions

1. **Discoverability** ✅

   - New users find `import_adapter("templates")` immediately
   - Documentation in one place
   - Examples in ACB repo

1. **Maintenance Leverage** ✅

   - Bug fixes benefit all ACB projects
   - Security updates centralized
   - Performance improvements shared

### For Session-Mgmt-MCP

1. **Faster Phase 3.1 Implementation**

   - No need to design custom template integration
   - Skip Jinja2 + async + DI research
   - Focus on template content, not infrastructure

1. **Proven Patterns**

   - Based on fastblocks battle-tested approach
   - ACB-native DI integration
   - Async-first from day one

1. **Future-Proof**

   - Upgrades come from ACB
   - Community contributions benefit us
   - Migration path if needs grow

### For Future ACB Projects

1. **Zero Template Setup**

   - `import_adapter("templates")` → done
   - No custom integration code
   - Instant async rendering

1. **Extensibility Path**

   - Start simple, extend when needed
   - Redis caching? Extend the adapter
   - Cloud storage? Extend the adapter
   - Core stays clean

______________________________________________________________________

## Risk Analysis

### Risks of Building in ACB

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Maintenance burden** | Low | Medium | Keep it simple, ~400 LOC is manageable |
| **Feature creep** | Medium | Medium | Strict "say no" policy for v1 |
| **Breaking changes** | Low | Low | Follow ACB adapter versioning |
| **Adoption slow** | Low | Low | Use it immediately in session-buddy |

### Risks of NOT Building in ACB

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Code duplication** | High | High | Each project reimplements templates |
| **Inconsistent patterns** | High | Medium | No standard way to do templates |
| **Maintenance multiplier** | High | High | Bug fixes needed in N projects |
| **User confusion** | Medium | Medium | "How do I use templates in ACB?" |

**Overall Assessment:** Risks of building are LOW, risks of NOT building are HIGH.

______________________________________________________________________

## Recommendation

### ✅ YES - Build `acb.adapters.templates`

**Why:**

1. **High ROI**: 3-4 days investment, benefits all ACB projects forever
1. **Clear Need**: Already needed by 2+ projects (fastblocks, session-buddy)
1. **Low Complexity**: ~400 lines of well-understood code
1. **Framework Fit**: Perfect match for ACB's adapter philosophy

### Implementation Strategy

**Option A: Build in ACB First, Then Use** ⭐ **RECOMMENDED**

1. Create `acb.adapters.templates` (3-4 days)
1. Release ACB version with templates adapter
1. Use in session-buddy Phase 3.1 immediately
1. Fastblocks can optionally migrate later (or keep custom version)

**Timeline:**

- Week 1: Build ACB templates adapter
- Week 2: Use in session-buddy Phase 3.1
- Total: ~1 week delay to Phase 3.1, but huge long-term benefit

**Option B: Build in Session-Mgmt-MCP, Extract to ACB Later**

1. Implement templates in session-buddy (Phase 3.1)
1. Extract to ACB when pattern proven
1. Migrate session-buddy to use ACB adapter

**Timeline:**

- Week 1-2: Phase 3.1 with custom templates
- Week 3: Extract to ACB
- Week 4: Migrate back to ACB adapter
- Total: Extra work, but validates pattern first

### Recommended: Option A

**Rationale:**

- We already have proven pattern (fastblocks)
- 3-4 day investment is small
- Immediate reuse in session-buddy
- Sets good precedent for ACB ecosystem

______________________________________________________________________

## Next Steps

### If Approved

1. **Create ACB Issue/PR**

   - Title: "Add templates adapter with async Jinja2 support"
   - Link this proposal document
   - Assign to ACB maintainer

1. **Implementation (3-4 days)**

   - Day 1-2: Core adapter implementation
   - Day 3: Testing suite
   - Day 4: Documentation & examples

1. **Release ACB Version**

   - Bump ACB version (e.g., 0.25.3 → 0.26.0)
   - Publish to PyPI
   - Update ACB docs

1. **Use in Session-Mgmt-MCP**

   - Update `pyproject.toml`: `acb>=0.26.0`
   - Begin Phase 3.1 using new adapter
   - Create example templates

### If Deferred

1. **Document Decision**

   - Why deferred (timing, priorities, etc.)
   - Revisit criteria

1. **Proceed with Session-Mgmt-MCP Custom Implementation**

   - Build templates system in Phase 3.1
   - Extract to ACB later if pattern successful

______________________________________________________________________

## Appendix A: Minimal Adapter Code Example

````python
# acb/adapters/templates/__init__.py
from __future__ import annotations

import typing as t
from pathlib import Path

from jinja2 import FileSystemLoader, select_autoescape
from jinja2_async_environment import AsyncEnvironment

if t.TYPE_CHECKING:
    from collections.abc import Callable


class TemplatesAdapter:
    """Lightweight async Jinja2 template adapter for ACB projects.

    Features:
    - Async-first rendering via jinja2-async-environment
    - ACB dependency injection integration
    - FileSystemLoader with configurable template directory
    - Custom filter and global registration
    - Auto-escaping for HTML/XML by default

    Example:
        ```python
        from acb.adapters import import_adapter
        from acb.depends import depends

        # Configure via DI
        templates = import_adapter("templates", template_dir="templates")
        depends.set("templates", templates)

        # Render template
        html = await templates.render("index.html", title="Hello World")
        ```
    """

    def __init__(
        self,
        template_dir: Path | str | None = None,
        *,
        enable_async: bool = True,
        autoescape: bool = True,
        cache_size: int = 400,
        auto_reload: bool = True,
    ) -> None:
        """Initialize templates adapter.

        Args:
            template_dir: Directory containing templates (default: ./templates)
            enable_async: Enable async template rendering (default: True)
            autoescape: Enable HTML/XML autoescaping (default: True)
            cache_size: Compiled template cache size (default: 400)
            auto_reload: Auto-reload templates when changed (default: True)
        """
        self.template_dir = Path(template_dir or Path.cwd() / "templates")
        self.template_dir.mkdir(parents=True, exist_ok=True)

        # Configure async Jinja2 environment
        self.env = AsyncEnvironment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]) if autoescape else False,
            enable_async=enable_async,
            cache_size=cache_size,
            auto_reload=auto_reload,
        )

        # Register default filters
        self._register_default_filters()

    async def render(
        self,
        template_name: str,
        context: dict[str, t.Any] | None = None,
        **kwargs: t.Any,
    ) -> str:
        """Render a template file asynchronously.

        Args:
            template_name: Template filename (relative to template_dir)
            context: Template context dictionary
            **kwargs: Additional context variables

        Returns:
            Rendered template string

        Example:
            ```python
            html = await templates.render(
                "user_profile.html",
                user={"name": "Alice", "email": "alice@example.com"},
            )
            ```
        """
        template = self.env.get_template(template_name)
        merged_context = {**(context or {}), **kwargs}
        return await template.render_async(**merged_context)

    async def render_string(
        self,
        template_string: str,
        context: dict[str, t.Any] | None = None,
        **kwargs: t.Any,
    ) -> str:
        """Render a template string asynchronously.

        Args:
            template_string: Jinja2 template string
            context: Template context dictionary
            **kwargs: Additional context variables

        Returns:
            Rendered template string

        Example:
            ```python
            html = await templates.render_string("Hello {{ name }}!", name="World")
            ```
        """
        template = self.env.from_string(template_string)
        merged_context = {**(context or {}), **kwargs}
        return await template.render_async(**merged_context)

    def add_filter(self, name: str, func: Callable[..., t.Any]) -> None:
        """Register a custom template filter.

        Args:
            name: Filter name (used in templates)
            func: Filter function

        Example:
            ```python
            templates.add_filter("uppercase", lambda x: x.upper())
            # Template: {{ name|uppercase }}
            ```
        """
        self.env.filters[name] = func

    def add_global(self, name: str, value: t.Any) -> None:
        """Register a global variable available in all templates.

        Args:
            name: Global variable name
            value: Variable value (can be any type)

        Example:
            ```python
            templates.add_global("site_name", "My Awesome Site")
            # Template: {{ site_name }}
            ```
        """
        self.env.globals[name] = value

    def _register_default_filters(self) -> None:
        """Register ACB-specific default filters."""
        # Example default filters (can be expanded)
        self.add_filter("json", _json_filter)
        self.add_filter("datetime", _datetime_filter)


def _json_filter(value: t.Any, indent: int | None = None) -> str:
    """JSON encoding filter."""
    import json

    return json.dumps(value, indent=indent, default=str)


def _datetime_filter(value: t.Any, format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Datetime formatting filter."""
    from datetime import datetime

    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return value.strftime(format)
    return str(value)


__all__ = ["TemplatesAdapter"]
````

**Size:** ~200 lines (with docstrings)
**Dependencies:** `jinja2-async-environment`, `jinja2`
**Complexity:** Low - straightforward wrapper around Jinja2

______________________________________________________________________

## Appendix B: Comparison with FastBlocks

### What FastBlocks Has That ACB Adapter Doesn't Need

1. **Redis Bytecode Caching** - Advanced performance optimization
1. **Cloud Storage Loaders** - S3/R2 template storage
1. **Template Synchronization** - Sync between cache/storage/filesystem
1. **Custom Delimiters** - `[[/]]` instead of `{{/}}`
1. **HTMY Component Integration** - Bidirectional component system
1. **Fragment Rendering** - Partial template updates
1. **Advanced Caching** - Multi-layer cache strategy
1. **Language Server** - IDE support for custom syntax
1. **Performance Optimizer** - Template compilation optimization

### What ACB Adapter Should Have

1. ✅ **Async Rendering** - via `jinja2-async-environment`
1. ✅ **FileSystemLoader** - standard template loading
1. ✅ **Custom Filters** - extensibility
1. ✅ **Auto-escaping** - security by default
1. ✅ **DI Integration** - ACB `depends` pattern
1. ✅ **Basic Caching** - Jinja2 built-in template caching

**Principle:** ACB adapter provides **80% of use cases with 5% of complexity**.

______________________________________________________________________

## Conclusion

Building a templates adapter in ACB is a **high-value, low-risk investment** that:

1. **Standardizes** template rendering across ACB projects
1. **Simplifies** integration (400 lines vs 37,000+)
1. **Accelerates** Phase 3.1 implementation
1. **Benefits** the entire ACB ecosystem

**Recommendation:** Proceed with **Option A** (build in ACB first, then use).

**Timeline:** 3-4 days to implement, immediate use in session-buddy.

______________________________________________________________________

*Proposal created for ACB framework enhancement discussion*
*Author: Claude Code with input from session-buddy Phase 3 planning*
