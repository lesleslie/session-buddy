# ACB Templates Adapter - Implementation Plan

**Created:** 2025-01-25
**Status:** Implementation - Day 1 Starting
**Timeline:** 3-4 days total
**Target Repository:** `/Users/les/Projects/acb`

______________________________________________________________________

## Implementation Overview

### Day 1-2: Core Adapter Implementation (TODAY)

**Location:** `/Users/les/Projects/acb/acb/adapters/templates/`

**Files to Create:**

```
acb/adapters/templates/
├── __init__.py          # Main TemplatesAdapter export
├── _base.py             # Base classes and settings
├── jinja2.py            # Jinja2 async adapter implementation
├── _filters.py          # Default filter functions
├── README.md            # Usage documentation
```

### Day 3: Testing Suite

**Location:** `/Users/les/Projects/acb/tests/adapters/templates/`

**Files to Create:**

```
tests/adapters/templates/
├── conftest.py                 # Test fixtures
├── test_rendering.py           # Basic rendering tests
├── test_async_rendering.py     # Async-specific tests
├── test_filters.py             # Filter registration tests
├── test_di_integration.py      # DI pattern tests
└── test_error_handling.py      # Error cases
```

### Day 4: Documentation & Examples

**Files to Create/Update:**

```
acb/adapters/templates/README.md    # Detailed usage guide
acb/examples/templates/
├── basic_usage.py                  # Simple rendering example
├── custom_filters.py               # Filter registration
├── di_integration.py               # Dependency injection
└── templates/
    ├── base.html                   # Template inheritance
    ├── index.html                  # Simple template
    └── user_profile.html           # Complex example
```

______________________________________________________________________

## Day 1 Tasks (Today)

### Task 1: Create Directory Structure ✅

```bash
cd /Users/les/Projects/acb
mkdir -p acb/adapters/templates
touch acb/adapters/templates/__init__.py
touch acb/adapters/templates/_base.py
touch acb/adapters/templates/jinja2.py
touch acb/adapters/templates/_filters.py
touch acb/adapters/templates/README.md
```

### Task 2: Implement \_base.py (Settings & Base Classes)

**Pattern:** Follow `acb/adapters/cache/_base.py` pattern

**Code:**

```python
# acb/adapters/templates/_base.py
import typing as t
from pathlib import Path

from acb.config import Config, Settings
from acb.depends import Inject, depends


class TemplatesBaseSettings(Settings):
    """Base settings for templates adapters."""

    template_dir: Path | str | None = None
    enable_async: bool = True
    autoescape: bool = True
    cache_size: int = 400
    auto_reload: bool = True

    @depends.inject
    def __init__(self, config: Inject[Config], **values: t.Any) -> None:
        super().__init__(**values)

        # Default template_dir to cwd/templates if not specified
        if self.template_dir is None:
            self.template_dir = Path.cwd() / "templates"
        elif isinstance(self.template_dir, str):
            self.template_dir = Path(self.template_dir)


class TemplatesBase:
    """Base class for template adapters."""

    def __init__(self, settings: TemplatesBaseSettings | None = None) -> None:
        self.settings = settings or TemplatesBaseSettings()

    async def render(
        self,
        template_name: str,
        context: dict[str, t.Any] | None = None,
        **kwargs: t.Any,
    ) -> str:
        """Render a template file. Must be implemented by subclass."""
        raise NotImplementedError

    async def render_string(
        self,
        template_string: str,
        context: dict[str, t.Any] | None = None,
        **kwargs: t.Any,
    ) -> str:
        """Render a template string. Must be implemented by subclass."""
        raise NotImplementedError

    def add_filter(self, name: str, func: t.Callable[..., t.Any]) -> None:
        """Register a custom template filter. Must be implemented by subclass."""
        raise NotImplementedError

    def add_global(self, name: str, value: t.Any) -> None:
        """Register a global variable. Must be implemented by subclass."""
        raise NotImplementedError
```

### Task 3: Implement jinja2.py (Main Adapter)

**Dependencies to Add:**

```toml
# In acb/pyproject.toml [project.dependencies]
"jinja2-async-environment>=0.14.3"
"jinja2>=3.1.6"
```

**Code:**

````python
# acb/adapters/templates/jinja2.py
from __future__ import annotations

import typing as t
from pathlib import Path

from jinja2 import FileSystemLoader, select_autoescape
from jinja2_async_environment import AsyncEnvironment

from ._base import TemplatesBase, TemplatesBaseSettings
from ._filters import register_default_filters

if t.TYPE_CHECKING:
    from collections.abc import Callable


class Jinja2Templates(TemplatesBase):
    """Async Jinja2 template adapter for ACB projects.

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
        templates = Jinja2Templates(template_dir="templates")
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
        settings: TemplatesBaseSettings | None = None,
    ) -> None:
        """Initialize Jinja2 templates adapter.

        Args:
            template_dir: Directory containing templates (default: ./templates)
            enable_async: Enable async template rendering (default: True)
            autoescape: Enable HTML/XML autoescaping (default: True)
            cache_size: Compiled template cache size (default: 400)
            auto_reload: Auto-reload templates when changed (default: True)
            settings: Optional settings object (overrides other params)
        """
        # Initialize base with settings
        if settings is None:
            settings = TemplatesBaseSettings(
                template_dir=template_dir,
                enable_async=enable_async,
                autoescape=autoescape,
                cache_size=cache_size,
                auto_reload=auto_reload,
            )
        super().__init__(settings)

        # Ensure template directory exists
        self.template_dir = Path(self.settings.template_dir)
        self.template_dir.mkdir(parents=True, exist_ok=True)

        # Configure async Jinja2 environment
        self.env = AsyncEnvironment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"])
            if self.settings.autoescape
            else False,
            enable_async=self.settings.enable_async,
            cache_size=self.settings.cache_size,
            auto_reload=self.settings.auto_reload,
        )

        # Register default filters
        register_default_filters(self)

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

        Raises:
            TemplateNotFound: If template file doesn't exist

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


# Alias for convenience
TemplatesAdapter = Jinja2Templates

__all__ = ["Jinja2Templates", "TemplatesAdapter", "TemplatesBaseSettings"]
````

### Task 4: Implement \_filters.py (Default Filters)

```python
# acb/adapters/templates/_filters.py
from __future__ import annotations

import typing as t
from datetime import datetime

if t.TYPE_CHECKING:
    from .jinja2 import Jinja2Templates


def register_default_filters(adapter: Jinja2Templates) -> None:
    """Register default ACB template filters.

    Args:
        adapter: Templates adapter instance
    """
    adapter.add_filter("json", json_filter)
    adapter.add_filter("datetime", datetime_filter)
    adapter.add_filter("filesize", filesize_filter)


def json_filter(value: t.Any, indent: int | None = None) -> str:
    """JSON encoding filter.

    Example:
        {{ data|json }}
        {{ data|json(2) }}  # Pretty print with indent
    """
    import json

    return json.dumps(value, indent=indent, default=str)


def datetime_filter(value: t.Any, format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Datetime formatting filter.

    Example:
        {{ timestamp|datetime }}
        {{ timestamp|datetime("%B %d, %Y") }}
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return value.strftime(format)
    return str(value)


def filesize_filter(value: int | float, binary: bool = True) -> str:
    """File size formatting filter.

    Args:
        value: Size in bytes
        binary: Use binary (1024) vs decimal (1000) units

    Example:
        {{ file_size|filesize }}        # "1.5 KiB"
        {{ file_size|filesize(False) }} # "1.5 KB"
    """
    units = (
        ["B", "KiB", "MiB", "GiB", "TiB"] if binary else ["B", "KB", "MB", "GB", "TB"]
    )
    divisor = 1024 if binary else 1000

    size = float(value)
    for unit in units[:-1]:
        if abs(size) < divisor:
            return f"{size:.1f} {unit}"
        size /= divisor
    return f"{size:.1f} {units[-1]}"


__all__ = [
    "register_default_filters",
    "json_filter",
    "datetime_filter",
    "filesize_filter",
]
```

### Task 5: Update __init__.py (Public API)

````python
# acb/adapters/templates/__init__.py
"""ACB Templates Adapter - Async Jinja2 template rendering.

Provides lightweight, async-first Jinja2 template rendering with ACB
dependency injection integration.

Usage:
    ```python
    from acb.adapters.templates import TemplatesAdapter
    from acb.depends import depends

    # Configure
    templates = TemplatesAdapter(template_dir="templates")
    depends.set("templates", templates)

    # Render
    html = await templates.render("index.html", title="Hello")
    ```
"""

from ._base import TemplatesBase, TemplatesBaseSettings
from ._filters import (
    datetime_filter,
    filesize_filter,
    json_filter,
    register_default_filters,
)
from .jinja2 import Jinja2Templates, TemplatesAdapter

__all__ = [
    "TemplatesAdapter",
    "Jinja2Templates",
    "TemplatesBase",
    "TemplatesBaseSettings",
    "register_default_filters",
    "json_filter",
    "datetime_filter",
    "filesize_filter",
]
````

______________________________________________________________________

## Integration Steps

### 1. Update ACB pyproject.toml

Add dependencies:

```toml
[project.dependencies]
# ... existing dependencies ...
"jinja2-async-environment>=0.14.3"
"jinja2>=3.1.6"
```

### 2. Update ACB Main Adapters README

Add templates to the list of available adapters in `acb/adapters/README.md`.

### 3. Test Locally in ACB

```bash
cd /Users/les/Projects/acb
uv sync
python -m pytest tests/adapters/templates/ -v
```

### 4. Use in Session-Mgmt-MCP

```bash
cd /Users/les/Projects/session-buddy
# Update pyproject.toml to use local ACB
uv add --editable /Users/les/Projects/acb
```

______________________________________________________________________

## Success Criteria

### Day 1-2 (Core Implementation)

- [ ] All core files created
- [ ] TemplatesAdapter renders templates asynchronously
- [ ] Custom filters can be registered
- [ ] DI integration works with `depends`
- [ ] Passes basic smoke tests

### Day 3 (Testing)

- [ ] ≥85% test coverage
- [ ] All async patterns tested
- [ ] Error handling validated
- [ ] DI override patterns demonstrated

### Day 4 (Documentation)

- [ ] README with usage examples
- [ ] Example code runs successfully
- [ ] API documentation complete
- [ ] Migration guide available

______________________________________________________________________

## Risk Mitigation

**Risk:** Jinja2-async-environment compatibility issues
**Mitigation:** Use proven library (used in fastblocks), test thoroughly

**Risk:** ACB DI pattern breaks
**Mitigation:** Follow existing adapter patterns exactly (cache, logger)

**Risk:** Performance concerns
**Mitigation:** Use Jinja2's built-in caching, profile if needed

______________________________________________________________________

## Next Steps After Completion

1. **Release ACB Version**

   - Bump version (e.g., 0.25.3 → 0.26.0)
   - Update CHANGELOG
   - Publish to PyPI

1. **Integrate into Session-Mgmt-MCP**

   - Update dependency to ACB 0.26.0
   - Begin Phase 3.1 implementation
   - Create session-buddy templates

1. **Optional: Notify FastBlocks**

   - Document how fastblocks could use base adapter
   - Offer migration path (optional, not required)

______________________________________________________________________

*Implementation plan for ACB templates adapter*
*Start Date: 2025-01-25*
*Expected Completion: 2025-01-28*
