# Security Architecture

**Last Updated**: 2026-02-03
**Version**: 1.0
**Status**: ✅ Phase 1 Complete (10 Priority 1 tests passing)

## Overview

Session Buddy implements a defense-in-depth security strategy to protect against:
- **Command Injection** (shell metacharacter, argument injection)
- **Path Traversal** (symlink attacks, null byte injection)
- **Environment Leakage** (sensitive data in subprocess environments)
- **Race Conditions** (concurrent sanitization)

---

## Architecture Components

### 1. Safe Subprocess Execution

**Module**: `session_buddy/utils/subprocess_helper.py`

**Purpose**: Secure subprocess execution with validation and sanitization

**Security Features**:
- ✅ Command allowlist validation
- ✅ Shell metacharacter detection (`; | & $ ` ( ) < > \n \r`)
- ✅ Environment sanitization (removes sensitive variables)
- ✅ Safe defaults enforcement (`shell=False`)
- ✅ Thread-safe operation

**API**:
```python
SafeSubprocess.run_safe(
    command: list[str],
    allowed_commands: set[str]
) -> subprocess.CompletedProcess[str]
```

**Threat Mitigation**:
| Threat | Mitigation |
|--------|------------|
| Command injection | Shell metacharacter blocking |
| Allowlist bypass | Absolute path validation |
| Environment leakage | Sensitive pattern removal |
| Race conditions | Immutable environment copies |

---

### 2. Path Validation

**Module**: `session_buddy/utils/path_validation.py`

**Purpose**: Prevent directory traversal and path-based attacks

**Security Features**:
- ✅ Path traversal detection (`..`, `~`)
- ✅ Null byte blocking (CWE-158)
- ✅ Symlink attack prevention (CWE-59)
- ✅ Length limit enforcement (POSIX PATH_MAX = 4096)
- ✅ Filesystem boundary checks

**API**:
```python
PathValidator.validate_user_path(
    path: str | Path,
    base_dir: Path | None = None
) -> Path
```

**Threat Mitigation**:
| Threat | Mitigation |
|--------|------------|
| Path traversal | Boundary resolution & checks |
| Null byte injection | Pattern matching & rejection |
| Symlink bypass | Realpath validation |
| Buffer overflow | Length limit enforcement |

---

### 3. Argument Parsing

**Module**: `session_buddy/mcp/tools/session/crackerjack_tools.py`

**Purpose**: Secure argument parsing for external tool execution

**Security Features**:
- ✅ Shlex-based quote handling
- ✅ Argument allowlist (flag validation)
- ✅ Unmatched quote detection
- ✅ Shell metacharacter blocking

**API**:
```python
_parse_crackerjack_args(
    args: str,
    allowlist: set[str] | None = None
) -> list[str]
```

**Threat Mitigation**:
| Threat | Mitigation |
|--------|------------|
| Argument injection | Allowlist + metacharacter blocking |
| Quote confusion | Shlex-based parsing |
| Flag bypass | Strict validation |

---

## Threat Model

### Attacker Capabilities

**Assumptions**:
- Attacker can control command arguments
- Attacker can create files and directories
- Attacker can execute commands through Session Buddy
- Attacker has local filesystem access

**What Attacker CANNOT Do**:
- Bypass command allowlist (enforced at execution)
- Access files outside allowed directories
- Inject shell metacharacters (blocked at validation)
- Leak environment through subprocess (sanitized)

### Attack Vectors Prevented

#### 1. Command Injection

**Attack**: `echo; rm -rf /`
**Prevention**: Shell metacharacter detection → ValueError raised

**Attack**: `$(whoami)`
**Prevention**: `$` character blocking → ValueError raised

#### 2. Path Traversal

**Attack**: `../../../etc/passwd`
**Prevention**: Boundary resolution → ValueError raised

**Attack**: `safe\x00../etc/passwd`
**Prevention**: Null byte detection → ValueError raised

#### 3. Symlink Attacks

**Attack**: Create symlink `/tmp/safe -> /etc`
**Prevention**: Realpath validation → ValueError raised

#### 4. Environment Leakage

**Attack**: Set `TOKEN=secret` and read through subprocess
**Prevention**: Pattern matching removes `TOKEN` → empty in subprocess

---

## Testing Strategy

### Test Categories

1. **Unit Tests** (`tests/security/`):
   - Individual function validation
   - Edge case coverage
   - Error condition testing

2. **Integration Tests** (`tests/integration/`):
   - Real filesystem operations
   - Actual subprocess execution
   - Concurrent operation validation

3. **Manual Tests** (`tests/security/manual_penetration_tests.py`):
   - Penetration testing scenarios
   - Attack simulation
   - Validation bypass attempts

### Coverage Targets

| Category | Target | Current |
|----------|--------|---------|
| Command Injection | 100% | ✅ Complete |
| Path Traversal | 100% | ✅ Complete |
| Environment Safety | 100% | ✅ Complete |
| Race Conditions | 90% | ✅ 80% (Priority 2) |

---

## Security Checklist

### Pre-Commit

- [ ] All new code passes security tests
- [ ] No new `suppress(Exception)` or bare `except:`
- [ ] Subprocess calls use `SafeSubprocess.run_safe()`
- [ ] File operations use `PathValidator.validate_user_path()`
- [ ] Environment variables sanitized before subprocess

### Pre-Merge

- [ ] Security tests pass (`pytest tests/security/`)
- [ ] Integration tests pass (`pytest tests/integration/`)
- [ ] Manual penetration tests reviewed
- [ ] Threat model updated for new features
- [ ] Documentation updated

---

## Known Limitations

### Current Scope

✅ **Covered**:
- Command injection prevention (shlex + allowlist)
- Path traversal prevention (validation + resolution)
- Environment sanitization (pattern matching)
- Thread safety (immutable copies)

⚠️ **Partially Covered**:
- Race conditions (80% coverage, 20% Priority 2 tests remaining)
- DoS prevention (argument length limits, no rate limiting)

❌ **Not Covered** (Future Work):
- Network-based attacks (no network operations)
- Memory-based attacks (Python GC handles most)
- Timing attacks (not applicable to current threat model)

### Assumptions

1. **Trusted Execution**: Python environment is trusted
2. **Local Filesystem**: Attacker has filesystem access (mitigated via validation)
3. **No Privilege Escalation**: Runs with user permissions only
4. **Single-Tenant**: No multi-user isolation needed

---

## Incident Response

### Security Issue Discovery

**If vulnerability is found**:

1. **DO NOT** open a public issue
2. Email: security@example.com
3. Include:
   - Vulnerability description
   - Steps to reproduce
   - Impact assessment
   - Suggested fix (if known)

### Response Process

1. **Acknowledge** within 48 hours
2. **Investigate** and validate within 7 days
3. **Fix** and test within 14 days
4. **Release** patch with security advisory
5. **Credit** disclosure (if requested)

---

## References

- **OWASP Command Injection**: https://owasp.org/www-community/attacks/Command_Injection
- **CWE-78: OS Command Injection**: https://cwe.mitre.org/data/definitions/78.html
- **CWE-22: Improper Limitation of a Pathname**: https://cwe.mitre.org/data/definitions/22.html
- **CWE-59: Improper Link Resolution**: https://cwe.mitre.org/data/definitions/59.html
- **CWE-158: Null Byte Injection**: https://cwe.mitre.org/data/definitions/158.html

---

## Changelog

### Version 1.0 (2026-02-03)

✅ **Phase 1 Complete**:
- Implemented SafeSubprocess class
- Implemented PathValidator class
- Added 10 Priority 1 security tests (all passing)
- Created comprehensive security documentation
- Fixed subprocess helper bugs (variable scope, empty command validation)
- Performance optimization: 1.7x speedup in environment sanitization

**Next Steps** (Phase 2):
- Add 20 Priority 2 security tests
- Implement rate limiting for DoS prevention
- Add more comprehensive race condition tests
- Create security best practices guide
