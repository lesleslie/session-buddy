"""The credential store is read the way the store is written.

The operator's store (``~/.config/secrets.env``) is sourced by shell rc
files, so its assignments carry the ``export`` keyword. A reader that
compares the raw left-hand side against the key name never matches any
of them.

That failure is invisible in an interactive shell, where the variable is
also in the environment and the environment wins. It shows up in the
launchd-spawned server, which inherits no interactive environment: there
the store is the only source of the credential, and a parser that cannot
read it finds nothing. The server then answers an authenticated request
with 401 and falls through to a different provider -- and a corpus
written by two providers is a corpus whose vectors cannot be compared.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.reflection import embeddings


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the credential store at a temporary file."""
    config = tmp_path / ".config"
    config.mkdir()
    path = config / "secrets.env"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return path


def test_an_exported_assignment_is_read(store: Path) -> None:
    """The store's own convention: ``export KEY=value``."""
    store.write_text("export BIFROST_VIRTUAL_KEY=the-key\n", encoding="utf-8")
    assert embeddings._secret_from_store("BIFROST_VIRTUAL_KEY") == "the-key"


def test_a_bare_assignment_is_read(store: Path) -> None:
    """A store without the keyword still works."""
    store.write_text("BIFROST_VIRTUAL_KEY=the-key\n", encoding="utf-8")
    assert embeddings._secret_from_store("BIFROST_VIRTUAL_KEY") == "the-key"


def test_a_quoted_value_is_unquoted(store: Path) -> None:
    """Quotes are shell syntax, not part of the value."""
    store.write_text('export BIFROST_VIRTUAL_KEY="the-key"\n', encoding="utf-8")
    assert embeddings._secret_from_store("BIFROST_VIRTUAL_KEY") == "the-key"


def test_comments_and_blanks_are_skipped(store: Path) -> None:
    """A commented-out assignment is not a credential."""
    store.write_text(
        "# export BIFROST_VIRTUAL_KEY=the-wrong-key\n"
        "\n"
        "export BIFROST_VIRTUAL_KEY=the-key\n",
        encoding="utf-8",
    )
    assert embeddings._secret_from_store("BIFROST_VIRTUAL_KEY") == "the-key"


def test_a_missing_store_is_not_an_error(store: Path) -> None:
    """No store means no credential, not a crash."""
    assert embeddings._secret_from_store("BIFROST_VIRTUAL_KEY") is None


def test_the_environment_wins_over_the_store(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator who exports a value for this process means it."""
    store.write_text("export BIFROST_VIRTUAL_KEY=from-the-store\n", encoding="utf-8")
    monkeypatch.setenv("BIFROST_VIRTUAL_KEY", "from-the-environment")
    assert embeddings._resolve_secret("BIFROST_VIRTUAL_KEY") == "from-the-environment"


def test_the_store_is_the_fallback_when_the_environment_is_empty(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launchd case: no environment, so the store is the only source."""
    store.write_text("export BIFROST_VIRTUAL_KEY=from-the-store\n", encoding="utf-8")
    monkeypatch.delenv("BIFROST_VIRTUAL_KEY", raising=False)
    assert embeddings._resolve_secret("BIFROST_VIRTUAL_KEY") == "from-the-store"
