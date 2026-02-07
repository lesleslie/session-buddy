from __future__ import annotations

import typing as t

import pytest
import session_buddy.utils.tool_wrapper as tw


class FakeDB:
    async def search_reflections(self, q: str) -> list[dict[str, t.Any]]:
        return [{"content": q}]


@pytest.mark.asyncio
async def test_execute_database_tool_success(monkeypatch: t.Any) -> None:
    async def fake_require_db() -> FakeDB:
        return FakeDB()

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    async def op(db: FakeDB) -> int:
        res = await db.search_reflections("abc")
        return len(res)

    def fmt(n: int) -> str:
        return f"Found {n}"

    out = await tw.execute_database_tool(op, fmt, "Search")
    assert out == "Found 1"


@pytest.mark.asyncio
async def test_execute_simple_database_tool_unavailable(monkeypatch: t.Any) -> None:
    from session_buddy.utils.error_management import DatabaseUnavailableError

    async def fake_require_db() -> FakeDB:
        msg = "db missing"
        raise DatabaseUnavailableError(msg)

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    async def op(db: FakeDB) -> str:
        return "ok"

    out = await tw.execute_simple_database_tool(op, "Op")
    assert "not available" in out.lower() or out.startswith("❌")


@pytest.mark.asyncio
async def test_execute_database_tool_with_dict_validation(monkeypatch: t.Any) -> None:
    async def fake_require_db() -> FakeDB:
        return FakeDB()

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    async def op(db: FakeDB) -> dict[str, int]:
        res = await db.search_reflections("x")
        return {"count": len(res)}

    def validator() -> None:
        # no-op success
        return None

    result = await tw.execute_database_tool_with_dict(op, "Search", validator)
    assert result["success"] is True
    assert result["data"]["count"] == 1


@pytest.mark.asyncio
async def test_execute_no_database_tool_formatting() -> None:
    async def op() -> dict[str, str]:
        return {"k": "v"}

    def fmt(d: dict[str, str]) -> str:
        return ",".join(sorted(d.keys()))

    out = await tw.execute_no_database_tool(op, fmt, "Fmt")
    assert out == "k"
