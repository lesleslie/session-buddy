"""The width-aware embedding provider chain.

The chain's job is to return a vector of the canonical width, and to
refuse one that is not. A wrong-width vector cannot be bound into the
DuckDB ``FLOAT[N]`` column, so the check has to happen before the vector
leaves the chain -- not at the database.
"""

from __future__ import annotations

import pytest

from session_buddy.memory.embedding_dim import DEFAULT_EMBEDDING_DIM
from session_buddy.reflection import embeddings

#: The real chain, captured at import time.
#:
#: ``tests/unit/conftest.py`` stubs ``_try_http_embedding_providers``
#: with a deterministic canonical-width fake so the suite needs no live
#: service.
#: That stub short-circuits the chain entirely. The module is imported
#: during collection -- before any fixture runs -- so this reference is
#: the genuine function, and restoring it inside the test body puts it
#: back after the stub has been installed.
_REAL_CHAIN = embeddings._try_http_embedding_providers


def _use_real_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the genuine chain back after the unit conftest's stub."""
    monkeypatch.setattr(embeddings, "_try_http_embedding_providers", _REAL_CHAIN)


@pytest.fixture(autouse=True)
def _clear_state() -> None:
    """The cache and the active-leg marker are process-wide."""
    embeddings.clear_embedding_cache()
    embeddings._ACTIVE_LEG = None


def _leg(name: str, width: int, result: list[float] | None) -> embeddings.ProviderLeg:
    """A provider leg that always answers with ``result``."""

    async def fetch(_text: str) -> list[float] | None:
        return result

    return embeddings.ProviderLeg(name, width, fetch)


def test_only_width_matching_legs_are_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leg whose width differs cannot fill a column of the other width."""
    matching = _leg("matching", DEFAULT_EMBEDDING_DIM, [0.1] * DEFAULT_EMBEDDING_DIM)
    other = _leg("other", DEFAULT_EMBEDDING_DIM + 1, [0.1] * (DEFAULT_EMBEDDING_DIM + 1))
    monkeypatch.setattr(embeddings, "_PROVIDER_LEGS", (matching, other))

    eligible = embeddings._eligible_legs()

    assert [leg.name for leg in eligible] == ["matching"]


async def test_the_chain_returns_the_first_eligible_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legs are tried in order and the first answer wins."""
    _use_real_chain(monkeypatch)
    first = _leg("first", DEFAULT_EMBEDDING_DIM, [0.5] * DEFAULT_EMBEDDING_DIM)
    second = _leg("second", DEFAULT_EMBEDDING_DIM, [0.9] * DEFAULT_EMBEDDING_DIM)
    monkeypatch.setattr(embeddings, "_PROVIDER_LEGS", (first, second))

    vector = await embeddings.generate_embedding("hello")

    assert vector == [0.5] * DEFAULT_EMBEDDING_DIM
    assert embeddings.get_embedding_system_info()["active_provider"] == "first"


async def test_the_chain_falls_through_when_a_leg_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leg that cannot answer hands over to the next one."""
    _use_real_chain(monkeypatch)
    dead = _leg("dead", DEFAULT_EMBEDDING_DIM, None)
    alive = _leg("alive", DEFAULT_EMBEDDING_DIM, [0.3] * DEFAULT_EMBEDDING_DIM)
    monkeypatch.setattr(embeddings, "_PROVIDER_LEGS", (dead, alive))

    vector = await embeddings.generate_embedding("hello")

    assert vector == [0.3] * DEFAULT_EMBEDDING_DIM
    assert embeddings.get_embedding_system_info()["active_provider"] == "alive"


async def test_a_wrong_width_vector_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leg that lies about its width is caught before the vector escapes.

    This is the authoritative gate. The eligibility check only skips legs
    whose *declared* width differs; a leg that returns a vector of the
    wrong width has to be caught here, or the DuckDB bind would fail.
    """
    _use_real_chain(monkeypatch)
    liar = _leg("liar", DEFAULT_EMBEDDING_DIM, [0.1] * (DEFAULT_EMBEDDING_DIM + 1))
    honest = _leg("honest", DEFAULT_EMBEDDING_DIM, [0.7] * DEFAULT_EMBEDDING_DIM)
    monkeypatch.setattr(embeddings, "_PROVIDER_LEGS", (liar, honest))

    vector = await embeddings.generate_embedding("hello")

    assert vector == [0.7] * DEFAULT_EMBEDDING_DIM
    assert embeddings.get_embedding_system_info()["active_provider"] == "honest"


async def test_the_chain_returns_none_when_no_leg_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No eligible provider means no vector, not a broken one."""
    _use_real_chain(monkeypatch)
    monkeypatch.setattr(
        embeddings,
        "_PROVIDER_LEGS",
        (_leg("dead", DEFAULT_EMBEDDING_DIM, None),),
    )

    assert await embeddings.generate_embedding("hello") is None


def test_the_system_info_reports_the_skipped_legs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator can see which provider is eligible and which is not."""
    matching = _leg("matching", DEFAULT_EMBEDDING_DIM, None)
    other = _leg("other", 4096, None)
    monkeypatch.setattr(embeddings, "_PROVIDER_LEGS", (matching, other))

    info = embeddings.get_embedding_system_info()

    assert info["model_dim"] == DEFAULT_EMBEDDING_DIM
    assert info["eligible_providers"] == ["matching"]
    skipped = {entry["name"]: entry for entry in info["skipped_providers"]}
    assert skipped["other"]["width"] == 4096
    assert skipped["other"]["reason"] == "width mismatch"


def test_the_shipped_chain_has_a_local_and_a_cloud_leg() -> None:
    """The chain carries both a cloud provider and a local fallback."""
    names = {leg.name for leg in embeddings._PROVIDER_LEGS}

    assert "openai_gateway" in names
    assert "llama_embed" in names
    # The chat server's width does not match, so it is present but
    # ineligible -- it comes back if the canonical width changes.
    assert "llama_server" in names


async def test_the_harness_stub_returns_the_canonical_width() -> None:
    """The stubbed provider has to honour the width contract too.

    ``tests/unit/conftest.py`` replaces the HTTP provider legs with a
    deterministic fake, and that fake *stands in for* the provider -- so
    its width is part of the contract, not an implementation detail. A
    vector of the wrong width cannot be bound into the ``FLOAT[N]``
    column, and every test that writes a row then fails with a
    ``ConversionException``.

    The stub is autouse, so its width governs every test under
    ``tests/unit/``. That is how a stale width in the harness turned
    into 265 failures with one stack trace.
    """
    stubbed = await embeddings._try_http_embedding_providers("hello")

    assert stubbed is not None
    assert len(stubbed) == DEFAULT_EMBEDDING_DIM

    vector = await embeddings.generate_embedding("hello")

    assert vector is not None
    assert len(vector) == DEFAULT_EMBEDDING_DIM
