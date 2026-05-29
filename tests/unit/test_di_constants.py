from __future__ import annotations


def test_di_constants_exports() -> None:
    from session_buddy.di.constants import (
        CLAUDE_DIR_KEY,
        COMMANDS_DIR_KEY,
        LOGS_DIR_KEY,
    )

    assert CLAUDE_DIR_KEY == "paths.claude_dir"
    assert LOGS_DIR_KEY == "paths.logs_dir"
    assert COMMANDS_DIR_KEY == "paths.commands_dir"
