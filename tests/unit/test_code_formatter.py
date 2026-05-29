from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.mcp.code_formatter import MCPCodeFormatter


@pytest.mark.asyncio
async def test_mcp_code_formatter_returns_false_for_all_files(tmp_path: Path) -> None:
    formatter = MCPCodeFormatter()

    assert await formatter.format_file(tmp_path / "example.py") is False
