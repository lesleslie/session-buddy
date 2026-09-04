"""Focused coverage tests for causal-chain tracking."""

from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core import causal_chains
from session_buddy.core.causal_chains import (
    CausalChain,
    CausalChainTracker,
    ErrorEvent,
    FixAttempt,
)


class AwaitableValue:
    """Wrap a DB row so the source's await-on-fetch idiom is testable."""

    def __init__(self, value: object) -> None:
        self.value = value

    def __await__(self):
        async def resolve() -> object:
            return self.value

        return resolve().__await__()


class Result:
    """Small result object returned by the synchronous DuckDB connection."""

    def __init__(
        self,
        row: tuple[object, ...] | None = None,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.row = row
        self.rows = rows or []

    def __await__(self):
        async def resolve() -> Result:
            return self

        return resolve().__await__()

    def fetchone(self) -> AwaitableValue:
        return AwaitableValue(self.row)

    def fetchall(self) -> AwaitableValue:
        return AwaitableValue(self.rows)


@pytest.fixture
def connection() -> MagicMock:
    """Return a synchronous DuckDB connection mock."""
    connection = MagicMock()
    connection.execute.return_value = Result()
    return connection


@pytest.fixture
def tracker(connection: MagicMock) -> CausalChainTracker:
    """Return a tracker with an injected database connection."""
    tracker = CausalChainTracker()
    tracker.db = SimpleNamespace(conn=connection)
    return tracker


def test_dataclasses_expose_defaults_and_values() -> None:
    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    event = ErrorEvent(
        "err-1", "boom", "ValueError", {"file": "x.py"}, timestamp, "s-1"
    )
    attempt = FixAttempt("fix-1", event.id, "changed code", timestamp=timestamp)
    chain = CausalChain("chain-1", event, [attempt])

    assert event.embedding is None
    assert attempt.code_changes is None
    assert attempt.successful is False
    assert chain.successful_fix is None
    assert chain.resolution_time_minutes is None


@pytest.mark.asyncio
async def test_initialize_loads_database_and_creates_all_tables() -> None:
    connection = AsyncMock()
    db = SimpleNamespace(conn=connection, initialize=AsyncMock())
    with patch("session_buddy.di.depends.get_sync", return_value=db):
        tracker = CausalChainTracker()
        await tracker.initialize()

    assert tracker.db is db
    assert connection.execute.await_count == 4
    statements = [call.args[0] for call in connection.execute.await_args_list]
    assert any("causal_error_events" in statement for statement in statements)
    assert any("causal_fix_attempts" in statement for statement in statements)
    assert any("causal_chains" in statement for statement in statements)
    assert any(
        "idx_causal_error_events_embeddings" in statement for statement in statements
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("database", [None, SimpleNamespace(conn=None)])
async def test_ensure_tables_without_connection_logs_warning(
    database: object, caplog: pytest.LogCaptureFixture
) -> None:
    tracker = CausalChainTracker()
    tracker.db = database  # type: ignore[assignment]

    with caplog.at_level(logging.WARNING):
        await tracker._ensure_tables()

    assert "No database connection" in caplog.text


@pytest.mark.asyncio
async def test_record_error_event_persists_context_and_embedding(
    tracker: CausalChainTracker, connection: MagicMock
) -> None:
    embedding = [0.25] * 384
    with patch(
        "session_buddy.reflection_tools.generate_embedding",
        new=AsyncMock(return_value=embedding),
    ):
        error_id = await tracker.record_error_event(
            "ImportError: missing module",
            {"error_type": "ImportError", "file": "main.py"},
            "s-1",
        )

    assert error_id.startswith("err-") and len(error_id) == 12
    statement, params = connection.execute.call_args.args
    assert "INSERT INTO causal_error_events" in statement
    assert params[0] == error_id
    assert params[2] == "ImportError"
    assert '"file": "main.py"' in params[3]
    assert params[5] == "s-1"
    assert params[6] == embedding


@pytest.mark.asyncio
async def test_record_error_event_uses_unknown_error_type_without_db() -> None:
    tracker = CausalChainTracker()
    with patch(
        "session_buddy.reflection_tools.generate_embedding",
        new=AsyncMock(return_value=[1.0]),
    ):
        error_id = await tracker.record_error_event("plain error", {}, "s-2")

    assert error_id.startswith("err-")


@pytest.mark.asyncio
async def test_record_fix_attempt_persists_failed_attempt(
    tracker: CausalChainTracker, connection: MagicMock
) -> None:
    fix_id = await tracker.record_fix_attempt(
        "err-12345678", "Try fallback", "diff", successful=False
    )

    assert fix_id.startswith("fix-") and len(fix_id) == 12
    statement, params = connection.execute.call_args.args
    assert "INSERT INTO causal_fix_attempts" in statement
    assert params[:4] == (fix_id, "err-12345678", "Try fallback", "diff")
    assert params[4] is False


@pytest.mark.asyncio
async def test_record_fix_attempt_returns_id_without_database() -> None:
    fix_id = await CausalChainTracker().record_fix_attempt(
        "err-1", "Document failure", successful=True
    )

    assert fix_id.startswith("fix-")


@pytest.mark.asyncio
async def test_record_fix_attempt_success_creates_chain(
    tracker: CausalChainTracker, connection: MagicMock
) -> None:
    error_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    fix_time = error_time + timedelta(minutes=7.5)
    connection.execute.side_effect = [
        Result(),
        Result((error_time,)),
        Result((fix_time,)),
        Result(),
    ]

    with patch("session_buddy.core.causal_chains.utc_now", return_value=fix_time):
        fix_id = await tracker.record_fix_attempt(
            "err-1", "Apply patch", successful=True
        )

    assert fix_id.startswith("fix-")
    assert connection.execute.call_count == 4
    chain_call = connection.execute.call_args_list[-1]
    assert "INSERT INTO causal_chains" in chain_call.args[0]
    assert chain_call.args[1][1] == "err-1"
    assert chain_call.args[1][2] == fix_id
    assert chain_call.args[1][3] == pytest.approx(7.5)


@pytest.mark.asyncio
async def test_create_chain_returns_empty_without_database() -> None:
    tracker = CausalChainTracker()
    assert await tracker._create_causal_chain("err-1", "fix-1") == ""


@pytest.mark.asyncio
async def test_create_chain_returns_empty_when_timestamps_missing(
    tracker: CausalChainTracker, connection: MagicMock
) -> None:
    connection.execute.side_effect = [Result(None), Result((datetime.now(UTC),))]

    assert await tracker._create_causal_chain("err-missing", "fix-1") == ""


@pytest.mark.asyncio
async def test_query_similar_failures_rejects_invalid_limits(
    tracker: CausalChainTracker,
) -> None:
    for limit in (0, -1, 101, "5"):
        with pytest.raises(
            ValueError, match="limit must be an integer between 1 and 100"
        ):
            await tracker.query_similar_failures("boom", limit=limit)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_query_similar_failures_returns_empty_without_database() -> None:
    tracker = CausalChainTracker()
    assert await tracker.query_similar_failures("boom") == []


@pytest.mark.asyncio
async def test_query_similar_failures_maps_rows_and_logs(
    tracker: CausalChainTracker, connection: MagicMock
) -> None:
    connection.execute.return_value = Result(
        rows=[
            ("err-1", "boom", '{"file": "x.py"}', "fix-1", "patch", None, 2.0, 0.91),
            ("err-2", "again", None, "fix-2", "retry", "diff", 3.0, 0.8),
        ]
    )
    with patch(
        "session_buddy.reflection_tools.generate_embedding",
        new=AsyncMock(return_value=[0.1]),
    ):
        results = await tracker.query_similar_failures("boom", limit=2)

    assert len(results) == 2
    assert results[0]["context"] == {"file": "x.py"}
    assert results[0]["successful_fix"] == {
        "action_taken": "patch",
        "code_changes": None,
    }
    assert results[1]["context"] == {}
    assert results[1]["similarity"] == 0.8


@pytest.mark.asyncio
async def test_get_causal_chain_returns_none_without_database() -> None:
    assert await CausalChainTracker().get_causal_chain("chain-1") is None


@pytest.mark.asyncio
async def test_get_causal_chain_returns_none_when_chain_not_found(
    tracker: CausalChainTracker, connection: MagicMock
) -> None:
    connection.execute.return_value = Result(None)
    assert await tracker.get_causal_chain("chain-missing") is None


@pytest.mark.asyncio
async def test_get_causal_chain_builds_complete_chain(
    tracker: CausalChainTracker, connection: MagicMock
) -> None:
    error_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    fix_time = error_time + timedelta(minutes=4)
    connection.execute.side_effect = [
        Result(
            ("err-1", "boom", "RuntimeError", '{"file": "x.py"}', error_time, "s-1")
        ),
        Result(
            rows=[
                (
                    "fix-1",
                    "err-1",
                    "retry",
                    None,
                    False,
                    error_time + timedelta(minutes=1),
                ),
                ("fix-2", "err-1", "patch", "diff", True, fix_time),
            ]
        ),
    ]

    chain = await tracker.get_causal_chain("chain-1")

    assert chain is not None
    assert chain.id == "chain-1"
    assert chain.error_event.context == {"file": "x.py"}
    assert len(chain.fix_attempts) == 2
    assert chain.successful_fix is chain.fix_attempts[1]
    assert chain.resolution_time_minutes == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_get_causal_chain_builds_unresolved_chain(
    tracker: CausalChainTracker, connection: MagicMock
) -> None:
    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    connection.execute.side_effect = [
        Result(("err-1", "boom", "RuntimeError", None, timestamp, "s-1")),
        Result(rows=[("fix-1", "err-1", "retry", None, False, timestamp)]),
    ]

    chain = await tracker.get_causal_chain("chain-2")

    assert chain is not None
    assert chain.successful_fix is None
    assert chain.resolution_time_minutes is None


@pytest.mark.asyncio
async def test_embedding_cache_and_none_result(tracker: CausalChainTracker) -> None:
    embedding = [0.3, 0.4]
    generator = AsyncMock(return_value=embedding)
    with patch("session_buddy.reflection_tools.generate_embedding", new=generator):
        assert await tracker._generate_embedding("same") == embedding
        assert await tracker._generate_embedding("same") == embedding
    generator.assert_awaited_once_with("same")

    with (
        patch(
            "session_buddy.reflection_tools.generate_embedding",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(ValueError, match="Embedding generation returned None"),
    ):
        await tracker._generate_embedding("missing")


def test_public_surface_import_smoke() -> None:
    assert causal_chains.CausalChainTracker is CausalChainTracker
    assert not [
        name
        for name, value in inspect.getmembers(
            causal_chains, inspect.iscoroutinefunction
        )
        if not name.startswith("_")
    ]
