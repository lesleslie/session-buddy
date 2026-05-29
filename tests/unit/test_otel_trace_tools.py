from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest


def test_otel_trace_filters_cover_all_branches() -> None:
    from session_buddy.mcp.tools.memory import otel_trace_tools

    now = datetime.now(tz=UTC)
    result = {
        "system_id": "alpha",
        "timestamp": now,
        "metadata": {
            "system_id": "alpha",
            "attributes": {"task.class": ["build", "test"]},
        },
    }

    assert otel_trace_tools._filter_result_by_system_id(result, "alpha") is False
    assert (
        otel_trace_tools._filter_result_by_system_id(
            {"metadata": {"system_id": "beta"}},
            "alpha",
        )
        is True
    )
    assert (
        otel_trace_tools._filter_result_by_system_id({"metadata": {}}, "alpha")
        is False
    )

    assert (
        otel_trace_tools._filter_result_by_time_range(
            result,
            start_time=(now - timedelta(minutes=1)).isoformat(),
            end_time=(now + timedelta(minutes=1)).isoformat(),
        )
        is False
    )
    assert (
        otel_trace_tools._filter_result_by_time_range(
            {"timestamp": "not-a-timestamp"},
            start_time=now.isoformat(),
            end_time=None,
        )
        is False
    )
    assert (
        otel_trace_tools._filter_result_by_time_range(
            {"timestamp": now.replace(tzinfo=None)},
            start_time=(now - timedelta(minutes=1)).isoformat(),
            end_time=(now + timedelta(minutes=1)).isoformat(),
        )
        is False
    )
    assert (
        otel_trace_tools._filter_result_by_time_range(
            result,
            start_time=(now + timedelta(minutes=1)).isoformat(),
            end_time=None,
        )
        is True
    )

    assert (
        otel_trace_tools._filter_result_by_task_class(result, "build") is False
    )
    assert (
        otel_trace_tools._filter_result_by_task_class(result, "deploy") is True
    )
    assert (
        otel_trace_tools._filter_result_by_task_class(
            {"metadata": {"attributes": {"task_class": "deploy"}}},
            "deploy",
        )
        is False
    )
    assert (
        otel_trace_tools._filter_result_by_task_class(
            {"metadata": {"attributes": {"task.class": "other"}}},
            "deploy",
        )
        is True
    )


def test_query_local_traces_and_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    from session_buddy.mcp.tools.memory import otel_trace_tools

    class FakeDB:
        async def search_conversations(self, query: str, limit: int, threshold: float):
            assert query == "alpha"
            assert limit == 10
            assert threshold == 0.0
            now = datetime.now(tz=UTC)
            return [
                {
                    "id": "1",
                    "content": "keep",
                    "timestamp": now,
                    "metadata": {
                        "system_id": "alpha",
                        "attributes": {"task.class": ["build"]},
                    },
                },
                {
                    "id": "2",
                    "content": "wrong system",
                    "timestamp": now,
                    "metadata": {
                        "system_id": "beta",
                        "attributes": {"task.class": ["build"]},
                    },
                },
                {
                    "id": "3",
                    "content": "wrong class",
                    "timestamp": now,
                    "metadata": {
                        "system_id": "alpha",
                        "attributes": {"task.class": ["test"]},
                    },
                },
            ]

    async def fake_get_reflection_database():
        return FakeDB()

    fake_module = SimpleNamespace(get_reflection_database=fake_get_reflection_database)
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        fake_module,
    )

    result = asyncio.run(
        otel_trace_tools.query_local_traces(
            "alpha",
            task_class="build",
            limit=10,
        ),
    )

    assert result == [
        {
            "conversation_id": "1",
            "content": "keep",
            "timestamp": str(result[0]["timestamp"]),
            "metadata": {
                "system_id": "alpha",
                "attributes": {"task.class": ["build"]},
            },
            "attributes": {"task.class": ["build"]},
        }
    ]

    class FakeMCP:
        def __init__(self) -> None:
            self.tools = []

        def tool(self):
            def decorator(func):
                self.tools.append(func)
                return func

            return decorator

    mcp = FakeMCP()
    otel_trace_tools.register_otel_trace_tools(mcp)
    assert mcp.tools == [otel_trace_tools.query_local_traces]

    async def broken_get_reflection_database():
        raise RuntimeError("boom")

    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        SimpleNamespace(get_reflection_database=broken_get_reflection_database),
    )
    assert asyncio.run(otel_trace_tools.query_local_traces("alpha")) == []
