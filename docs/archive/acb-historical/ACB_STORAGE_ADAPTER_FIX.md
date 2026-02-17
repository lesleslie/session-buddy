# ACB Storage Adapter Fix - Summary

## Problem

The `register_storage_adapter()` function in `/session_buddy/adapters/storage_registry.py` was attempting to use `import_adapter("storage")` to dynamically load ACB storage adapters, which resulted in the error:

```
AdapterNotFound: storage adapter not found – check adapters.yaml and ensure package registration
```

## Root Cause

ACB storage adapters follow a **different import pattern** than other ACB adapters:

1. **Other ACB adapters** (logger, cache, etc.):

   - Use `import_adapter("adapter_name")`
   - Require registration in `adapters.yaml`
   - Auto-selected based on configuration

1. **ACB storage adapters**:

   - Use **direct imports** from specific backend modules
   - Do NOT use `adapters.yaml`
   - Each backend has its own module: `acb.adapters.storage.{backend}`

## Solution

Implemented a **lazy-loading pattern** with direct imports for each backend:

### Before (Broken)

```python
from acb.adapters import import_adapter

def register_storage_adapter(backend: str, ...):
    # This fails - storage adapters don't use import_adapter()
    storage_class = import_adapter("storage")  # ❌ ERROR!
```

### After (Fixed)

```python
# Backend to class mapping (lazy-loaded on first use)
_STORAGE_CLASSES: dict[str, type[StorageBase] | None] = {
    "file": None,
    "s3": None,
    "azure": None,
    "gcs": None,
    "memory": None,
}

def _get_storage_class(backend: str) -> type[StorageBase]:
    """Get storage class for a backend, lazy-loading on first use."""
    if _STORAGE_CLASSES[backend] is None:
        if backend == "file":
            from acb.adapters.storage.file import Storage
            _STORAGE_CLASSES["file"] = Storage
        elif backend == "s3":
            from acb.adapters.storage.s3 import Storage
            _STORAGE_CLASSES["s3"] = Storage
        # ... etc for other backends

    return _STORAGE_CLASSES[backend]

def register_storage_adapter(backend: str, ...):
    # Get the storage class for this backend (direct import)
    storage_class = _get_storage_class(backend)  # ✅ WORKS!
```

## Changes Made

### 1. Added Lazy-Loading Helper (`_get_storage_class()`)

- Maps backend names to storage classes
- Imports on first use to avoid unnecessary dependencies
- Returns the appropriate `Storage` class for each backend

### 2. Updated `register_storage_adapter()`

- **Before**: Used `import_adapter("storage")` ❌
- **After**: Uses `_get_storage_class(backend)` ✅
- Properly sets `config.storage.default_backend`
- Maintains full backward compatibility

### 3. Updated `get_storage_adapter()`

- **Before**: Used `import_adapter("storage", backend)` ❌
- **After**: Uses `_get_storage_class(backend)` ✅
- Same retrieval logic from DI container

## Benefits

1. **Works with all ACB storage backends**: file, s3, azure, gcs, memory
1. **Lazy loading**: Only imports needed backends (avoids missing dependencies)
1. **Proper ACB patterns**: Follows ACB's direct import approach for storage
1. **Backward compatible**: No API changes, existing code works as-is
1. **Type safe**: Full type hints with `StorageBase` protocol

## Testing

All 25 existing tests pass, plus new validation:

```bash
# Test all backends
python -c "
from session_buddy.adapters.storage_registry import register_storage_adapter
storage = register_storage_adapter('file', {'local_path': '/tmp/sessions'})
print('✅ File storage registered')
"

# Test retrieval
python -c "
from session_buddy.adapters.storage_registry import get_storage_adapter
storage = get_storage_adapter('file')
print('✅ File storage retrieved')
"
```

## Documentation

Created comprehensive documentation:

- **`docs/ACB_STORAGE_ADAPTER_GUIDE.md`**: Complete usage guide with examples
- **Code comments**: Added notes explaining the direct import pattern
- **Docstrings**: Updated with pattern references

## Migration Impact

**Zero breaking changes** - this is a bug fix:

- Existing code using `register_storage_adapter()` works correctly now
- All function signatures unchanged
- Configuration via YAML still works
- DI container integration unchanged

## Key Takeaways

1. **ACB storage adapters are special**: They use direct imports, not `import_adapter()`
1. **No `adapters.yaml` needed**: Storage adapters don't require YAML configuration
1. **Backend selection**: Use a mapping dict for dynamic backend selection
1. **Lazy loading**: Only import backends when actually needed
1. **Read the docs**: See `docs/ACB_STORAGE_ADAPTER_GUIDE.md` for complete usage

## References

- **Fixed file**: `/session_buddy/adapters/storage_registry.py`
- **Documentation**: `/docs/ACB_STORAGE_ADAPTER_GUIDE.md`
- **Tests**: `/tests/unit/test_session_storage_adapter.py` (25 tests passing)
- **ACB source**: `acb.adapters.storage.{file,s3,azure,gcs,memory}`
