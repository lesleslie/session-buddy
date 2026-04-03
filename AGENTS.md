# Repository Guidelines

## Project Structure & Module Organization

- `session_buddy/` hosts the runtime server (`server.py`), CLI entrypoint (`cli.py`), and integration adapters such as `crackerjack_integration.py`.
- Feature logic belongs in `session_buddy/core/`, `session_buddy/tools/`, and `session_buddy/utils/`; keep new modules narrow, protocol-driven, and well-typed.
- Tests reside in `tests/` with fixtures under `tests/fixtures/` and strategy notes in `tests/README.md`; mirror package paths when adding cases.
- Documentation lives in `docs/`; generated assets (`dist/`, `htmlcov/`, coverage outputs) should remain untouched.

## Build, Test, and Development Commands

- `uv sync --group dev` installs reproducible runtime and development dependencies.
- `uv run session-buddy --start-mcp-server --verbose` boots the MCP server locally; add `--status` to confirm ports 8677/8678.
- `uv run pre-commit run --all-files` executes Ruff, Pyright, Bandit, Complexipy, and related quality gates while applying safe fixes.
- Use Crackerjack as the canonical repo-wide quality and CI/CD gate when validating larger changes or matching CI locally.
- `uv run pytest --cov=session_buddy --cov-report=term-missing` runs the suite with coverage; append `--maxfail=1` during rapid iteration.

## Coding Style & Naming Conventions

- Target Python 3.13 with explicit type hints; import typing as `import typing as t` and reference annotations via `t.` prefixes.
- Prefer `pathlib.Path`, f-strings, dataclasses, and protocol interfaces; avoid docstrings unless an API contract demands them.
- Keep functions short (cognitive complexity ≤13), adopt descriptive snake_case, and consolidate shared helpers within `utils/`.

## Testing Guidelines

- Pair every module with pytest cases that mirror its path (e.g., `session_buddy/foo.py` → `tests/unit/test_foo.py`).
- Reuse the async fixtures provided; mark temporary failures with `@pytest.mark.xfail` and link the tracking issue.
- Maintain the march toward 85% coverage; regenerate HTML via `uv run pytest --cov ... --cov-report=html` and review `htmlcov/index.html` before submitting.

## Commit & Pull Request Guidelines

- Adopt conventional commits with scope, e.g., `fix(core): tighten session cleanup`; avoid bundling unrelated fixes.
- Provide PR descriptions that state intent, list executed checks, include coverage deltas, and link issues or MCP transcripts.
- Attach redacted logs or screenshots when altering CLI output or websocket telemetry; request review after pre-commit, pytest, and server smoke tests pass.

## Security & Configuration Tips

- Store MCP client configs as `example.mcp.json` derivatives and keep secrets out of version control.
- Audit runtime settings with `uv run session-buddy --config`; rely on `tempfile` utilities for ephemeral paths.
- Review permission updates through the `permissions` MCP tool to uphold least-privilege defaults.
