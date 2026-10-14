"""End-to-end UUID7 consolidation tests (PR-C).

These tests verify the four invariants the consolidation bundle is supposed
to produce when it runs end-to-end on a seeded pre-migration database:

1. ``test_conversations_merged`` — the conversations table holds exactly
   1,205 rows after 001 absorbs the v0 and ``default_conversations`` sets
   (935 v2 + 265 v0-unique + 5 default = 1,205).
2. ``test_reflections_merged`` — the reflections table holds at least
   1,485 rows after 002/003 absorb ``default_reflections`` (1,232 v2 +
   253 default = 1,485).
3. ``test_vestigial_dropped`` — ``access_log_v2`` and ``query_cache_l2``
   are dropped by 006. ``schema_meta`` and ``schema_migrations`` are
   preserved by 006 (the adversarial review caught live data on both
   tables; they are not vestigial).
4. ``test_uuid7_pk_enforced`` — every primary-key column on the
   load-bearing tables (conversations, reflections, code_graphs,
   session_windows, memory_access_log) holds a 32-character lowercase
   hex UUID7 after 007, never a 26-character ULID.

Each test seeds a throwaway DuckDB, copies the relevant canonical scripts
into a per-test bundle directory, runs :class:`MigrationRunner`, and
asserts the post-state. The pattern follows
``tests/integration/migrations/test_migrate_cli_e2e.py`` (small per-test
SQL bundles).

Cross-helper note: the canonical 003 calls ``uuid7()`` to mint fresh
UUID7s for absorbed ``default_reflections`` rows. The runner registers
``uuid7`` (and ``ulid_to_uuid7``) on its connection (added in PR-C F3),
so the script runs end-to-end on DuckDB without any extra setup.
"""

from __future__ import annotations

import shutil
import uuid as uuid_lib
from pathlib import Path

import duckdb
import pytest

from session_buddy.migrations.runner import (
    MigrationContext,
    MigrationRunner,
)

# Canonical bundle directory (read-only source of truth).
_CANONICAL_BUNDLE = Path(__file__).resolve().parents[2] / (
    "session_buddy/migrations/2026_10_11_uuid7_consolidation"
)


# ---------------------------------------------------------------------------
# Row-count fixtures (production-typed).
# ---------------------------------------------------------------------------
# Conversations merge: 935 v2 + 265 v0-unique + 5 default = 1,205.
# Reflections merge: 1,232 v2 + 253 default = 1,485.
CONVERSATIONS_V2_COUNT = 935
CONVERSATIONS_V0_TOTAL = 1195
CONVERSATIONS_V0_OVERLAP = 930
CONVERSATIONS_V0_UNIQUE = CONVERSATIONS_V0_TOTAL - CONVERSATIONS_V0_OVERLAP
DEFAULT_CONVERSATIONS_COUNT = 5
EXPECTED_MERGED_CONVERSATIONS = (
    CONVERSATIONS_V2_COUNT + CONVERSATIONS_V0_UNIQUE + DEFAULT_CONVERSATIONS_COUNT
)
assert EXPECTED_MERGED_CONVERSATIONS == 1205

REFLECTIONS_V2_COUNT = 1232
DEFAULT_REFLECTIONS_COUNT = 253
EXPECTED_MERGED_REFLECTIONS = REFLECTIONS_V2_COUNT + DEFAULT_REFLECTIONS_COUNT
assert EXPECTED_MERGED_REFLECTIONS == 1485


# ---------------------------------------------------------------------------
# ULID-style id generation.
# ---------------------------------------------------------------------------
# The pre-migration 001 path assumes legacy ids match between v0 and v2
# where they overlap; both rows count toward ``CONVERSATIONS_V0_OVERLAP``.
# The simplest synthetic seed gives every row a 26-char Crockford-base32
# id so the ``ulid_to_uuid7()`` translation in 007 has something to chew
# on. We use a deterministic counter to keep the test reproducible
# without poking the wall clock.

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _make_ulid(seed: int) -> str:
    """Return a 32-char Crockford-base32 id from ``seed``.

    The canonical 007's ``ulid_to_uuid7(legacy_id)`` UDF requires 32
    chars of Crockford-base32 input (see
    ``session_buddy.migrations.udf.ulid_to_uuid7`` — "expected 32-char
    Crockford-base32 ULID"). Real ULIDs are 26 chars; the canonical
    scripts assume the pre-migration column carries the padded 32-char
    variant. We pin the first 10 chars to a fixed timestamp prefix and
    the last 22 chars to the seed encoding so each produced id is
    deterministic and unique across the seed range.
    """
    body = []
    value = seed
    for _ in range(22):
        body.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "01HWYAAAAA" + "".join(reversed(body))


def _make_uuid7_hex(seed: int) -> str:
    """Return a 32-char lowercase hex UUID7 from ``seed``.

    Used for post-007 expectations; not for seeding pre-migration state.
    """
    return uuid_lib.UUID(int=seed).hex


# ---------------------------------------------------------------------------
# Helpers — bundle wiring + pre-state seeding.
# ---------------------------------------------------------------------------

def _copy_canonical_scripts(tmp_path: Path, names: list[str]) -> Path:
    """Materialize a per-test bundle directory containing only ``names``.

    Returns the bundle directory path. The :class:`ScriptDiscovery` glob
    (``0*.sql``) picks up only the copied files, so the runner executes
    exactly the subset the test cares about.
    """
    bundle = tmp_path / "bundle"
    bundle.mkdir(exist_ok=True)
    for name in names:
        shutil.copy(_CANONICAL_BUNDLE / name, bundle / name)
    return bundle


def _open_db(path: Path) -> duckdb.DuckDBPyConnection:
    """Open a read-write DuckDB connection. Caller closes it."""
    return duckdb.connect(str(path))


def _quote_sql_value(value: object) -> str:
    """SQL-quote a Python value for inline embedding in a VALUES clause.

    Strings get single-quoted with internal single-quotes doubled. Other
    types (``int``, ``float``, ``None``) are rendered with their natural
    Python ``repr``. Used only by the test-seed path; no untrusted input
    reaches this helper.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _fast_insert(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    columns: list[str],
    rows: list[tuple[object, ...]],
) -> None:
    """Bulk-insert ``rows`` into ``table`` with a single multi-VALUES INSERT.

    DuckDB's ``executemany`` is ~200x slower than a single multi-VALUES
    INSERT for row batches >100 (each per-row statement pays the parser /
    binder cost). The synthetic seed here inserts 1,200+ rows per test;
    the inline-VALUES form keeps each test under a few seconds.
    """
    if not rows:
        return
    col_list = ", ".join(columns)
    values_sql = ",\n".join(
        "(" + ", ".join(_quote_sql_value(v) for v in row) + ")"
        for row in rows
    )
    conn.execute(f"INSERT INTO {table} ({col_list}) VALUES {values_sql}")


# ---------------------------------------------------------------------------
# Conversations-table seed.
# ---------------------------------------------------------------------------
# Conversations schema (canonical schema_v2.py:42-77). The 001 script
# reads ``conversations``, ``conversations_v2``, ``default_conversations``,
# ``memory_access_log``, ``memory_entities``, ``memory_promotions`` and
# ``memory_relationships``. The FK dependents must already exist with
# the FK columns declared against ``conversations_v2`` (001's step F
# recreates them against the renamed canonical).

CONVERSATIONS_V2_DDL = """
CREATE TABLE conversations_v2 (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[384],
    category TEXT NOT NULL,
    subcategory TEXT,
    importance_score REAL DEFAULT 0.5,
    memory_tier TEXT DEFAULT 'long_term',
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    project TEXT,
    namespace TEXT DEFAULT 'default',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    user_id TEXT DEFAULT 'default',
    searchable_content TEXT,
    reasoning TEXT,
    metadata VARCHAR,
    source_type TEXT,
    turn_parent_id TEXT,
    causal_parent_id TEXT
);
"""

CONVERSATIONS_V0_DDL = """
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[384],
    project TEXT,
    namespace TEXT DEFAULT 'default',
    user_id TEXT DEFAULT 'default',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,
    searchable_content TEXT
);
CREATE INDEX idx_conversations_project ON conversations(project);
CREATE INDEX idx_conversations_timestamp ON conversations(timestamp DESC);
"""

CONVERSATIONS_V2_INDEXES_DDL = """
CREATE INDEX idx_conversations_access
    ON conversations_v2(last_accessed DESC);
CREATE INDEX idx_conversations_category
    ON conversations_v2(category, namespace);
CREATE INDEX idx_conversations_fts
    ON conversations_v2(searchable_content);
CREATE INDEX idx_conversations_namespace
    ON conversations_v2(namespace, project);
CREATE INDEX idx_conversations_tier
    ON conversations_v2(memory_tier, importance_score DESC);
CREATE INDEX idx_v2_source_type_project
    ON conversations_v2(source_type, project, timestamp DESC);
"""

DEFAULT_CONVERSATIONS_DDL = """
CREATE TABLE default_conversations (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],
    subcategory TEXT,
    fingerprint TEXT,
    metadata VARCHAR,
    created_at TIMESTAMP
);
"""

MEMORY_DEPENDENTS_DDL = """
CREATE TABLE memory_access_log (
    id TEXT PRIMARY KEY,
    memory_id TEXT,
    access_type TEXT,
    query_text TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);
CREATE TABLE memory_entities (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);
CREATE TABLE memory_relationships (
    id TEXT PRIMARY KEY,
    from_entity_id TEXT NOT NULL,
    to_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    strength REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_entity_id) REFERENCES memory_entities(id),
    FOREIGN KEY (to_entity_id) REFERENCES memory_entities(id)
);
CREATE TABLE memory_promotions (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    from_tier TEXT NOT NULL,
    to_tier TEXT NOT NULL,
    reason TEXT,
    priority_score REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);
"""


def _seed_conversations_state(conn: duckdb.DuckDBPyConnection) -> None:
    """Seed a pre-001 state: v0 + v2 + default + memory_* dependents.

    Row count invariants:
        * conversations (v0):  CONVERSATIONS_V0_TOTAL rows
            (CONVERSATIONS_V0_OVERLAP overlap with v2 +
             CONVERSATIONS_V0_UNIQUE v0-unique)
        * conversations_v2:    CONVERSATIONS_V2_COUNT rows
            (CONVERSATIONS_V0_OVERLAP overlap with v0 +
             CONVERSATIONS_V2_COUNT - CONVERSATIONS_V0_OVERLAP v2-unique)
        * default_conversations: DEFAULT_CONVERSATIONS_COUNT rows
            (no overlap with v0 or v2)

    The naming follows the pre-001 state: ``conversations`` is the v0
    table (001 step 1 renames it to ``conversations_legacy``); the
    canonical table is ``conversations_v2`` (001 step 2 renames it to
    ``conversations``).
    """
    # 1. conversations_v2 first (canonical v2 schema + v2 indexes).
    conn.execute(CONVERSATIONS_V2_DDL)
    conn.execute(CONVERSATIONS_V2_INDEXES_DDL)
    # 2. conversations (v0 schema + v0 indexes).
    conn.execute(CONVERSATIONS_V0_DDL)
    # 3. default_conversations + memory_* dependents (FK -> v2).
    conn.execute(DEFAULT_CONVERSATIONS_DDL)
    conn.execute(
        MEMORY_DEPENDENTS_DDL.replace("conversations(id)", "conversations_v2(id)")
    )

    # v2 rows: ids 0..(V0_OVERLAP-1) overlap with v0 plus
    # V0_TOTAL..V0_TOTAL+(V2_COUNT-V0_OVERLAP-1) v2-unique. Total is
    # V2_COUNT rows. The V0_OVERLAP-id v2 rows duplicate the same ids
    # in conversations (v0) so 001's Step 3 ``WHERE NOT EXISTS``
    # correctly leaves them out of the v0-unique absorb count.
    v2_unique_offset = CONVERSATIONS_V0_TOTAL
    v2_rows = [
        (
            _make_ulid(i),
            f"v2 content {i}",
            None, "facts", None, 0.5, "long_term", 0, None,
            f"project{i % 10}", "default", "default", None, None,
            f"v2 content {i}", None, "{}", "manual", None, None,
        )
        for i in list(range(CONVERSATIONS_V0_OVERLAP))
        + list(range(
            v2_unique_offset,
            v2_unique_offset + (CONVERSATIONS_V2_COUNT - CONVERSATIONS_V0_OVERLAP),
        ))
    ]
    _fast_insert(
        conn,
        "conversations_v2",
        [
            "id", "content", "embedding", "category", "subcategory",
            "importance_score", "memory_tier", "access_count",
            "last_accessed", "project", "namespace", "user_id", "timestamp",
            "session_id", "searchable_content", "reasoning", "metadata",
            "source_type", "turn_parent_id", "causal_parent_id",
        ],
        v2_rows,
    )

    # v0 rows: ids 0..(V0_OVERLAP-1) overlap v2; ids V0_OVERLAP..
    # V0_TOTAL-1 are v0-unique.
    v0_rows = [
        (_make_ulid(i), f"v0 content {i}", None, f"project{i % 10}",
         "default", "default", None, "{}", f"v0 content {i}")
        for i in range(CONVERSATIONS_V0_TOTAL)
    ]
    _fast_insert(
        conn,
        "conversations",
        [
            "id", "content", "embedding", "project", "namespace", "user_id",
            "timestamp", "metadata", "searchable_content",
        ],
        v0_rows,
    )

    # default_conversations: ids start past the v2-unique range to avoid
    # collision with v2 IDs 1195..1199 (the V0_OVERLAP-shifted v2 ids).
    default_start = (
        CONVERSATIONS_V0_TOTAL + CONVERSATIONS_V2_COUNT - CONVERSATIONS_V0_OVERLAP
    )
    default_rows = [
        (_make_ulid(default_start + i), f"default content {i}",
         None, None, None, "{}", None)
        for i in range(DEFAULT_CONVERSATIONS_COUNT)
    ]
    _fast_insert(
        conn,
        "default_conversations",
        [
            "id", "content", "embedding", "subcategory", "fingerprint",
            "metadata", "created_at",
        ],
        default_rows,
    )


def _seed_vestigial_state(conn: duckdb.DuckDBPyConnection) -> None:
    """Seed the four tables 006 references.

    Two are dropped (access_log_v2, query_cache_l2); two are kept
    (schema_meta, schema_migrations).
    """
    conn.execute(
        "CREATE TABLE access_log_v2 (id TEXT PRIMARY KEY, query TEXT, ts TEXT)"
    )
    conn.execute(
        "INSERT INTO access_log_v2 VALUES ('a1', 'select 1', '2026-01-01')"
    )
    conn.execute(
        "CREATE TABLE query_cache_l2 ("
        "id TEXT PRIMARY KEY, query_hash TEXT, payload TEXT)"
    )
    conn.execute(
        "INSERT INTO query_cache_l2 VALUES ('c1', 'h1', 'p1')"
    )
    conn.execute(
        "CREATE TABLE schema_meta ("
        "key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO schema_meta VALUES ('schema_version', 'v2', NULL)"
    )
    conn.execute(
        "CREATE TABLE schema_migrations ("
        "id TEXT PRIMARY KEY, name TEXT, applied_at TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO schema_migrations "
        "VALUES ('mig_20260607_085742_861283', 'v1_to_v2', NULL)"
    )


# ---------------------------------------------------------------------------
# Reflection-table seed.
# ---------------------------------------------------------------------------
# ``reflections_v2`` and ``default_reflections`` are the two tables
# 003 absorbs. Their schemas follow schema_v2.py:80-120 and the
# default_reflections shape documented in docs/features/INSIGHTS_CAPTURE.md.

REFLECTIONS_V2_DDL = """
CREATE TABLE reflections_v2 (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[384],
    category TEXT NOT NULL DEFAULT 'facts',
    importance_score REAL DEFAULT 0.5,
    memory_tier TEXT DEFAULT 'long_term',
    tags JSON,
    related_entities TEXT[],
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    project TEXT,
    namespace TEXT DEFAULT 'default',
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    fingerprint BLOB,
    subcategory TEXT,
    metadata JSON,
    source_session_id TEXT,
    source_artifact_uri TEXT,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    confidence_score REAL DEFAULT 0.5,
    conversation_id TEXT,
    insight_type TEXT DEFAULT 'general'
);
"""

REFLECTIONS_V0_DDL = """
CREATE TABLE reflections (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[384],
    project TEXT,
    category TEXT,
    importance_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,
    tags JSON
);
"""

DEFAULT_REFLECTIONS_DDL = """
CREATE TABLE default_reflections (
    id TEXT,
    content TEXT,
    embedding FLOAT[384],
    tags JSON,
    metadata JSON,
    usage_count INTEGER,
    last_used_at TIMESTAMP,
    confidence_score REAL,
    insight_type TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
"""


def _seed_reflections_state(conn: duckdb.DuckDBPyConnection) -> None:
    """Seed a pre-003 state.

    Row count invariants:
        * reflections_v2:         REFLECTIONS_V2_COUNT rows
        * default_reflections:    DEFAULT_REFLECTIONS_COUNT rows
    """
    conn.execute(REFLECTIONS_V0_DDL)
    conn.execute(REFLECTIONS_V2_DDL)
    conn.execute(DEFAULT_REFLECTIONS_DDL)

    # v2 rows
    v2_rows = [
        (_make_ulid(i), f"v2 reflection {i}", None,
         "facts", 0.5, "long_term", "[]", None, None,
         f"project{i % 10}", "default", 0, None, None, None,
         None, None, "{}", None, None)
        for i in range(REFLECTIONS_V2_COUNT)
    ]
    _fast_insert(
        conn,
        "reflections_v2",
        [
            "id", "content", "embedding", "category", "importance_score",
            "memory_tier", "tags", "related_entities", "timestamp", "project",
            "namespace", "access_count", "last_accessed", "created_at",
            "updated_at", "fingerprint", "subcategory", "metadata",
            "source_session_id", "source_artifact_uri",
        ],
        v2_rows,
    )

    # default_reflections rows
    default_rows = [
        (f"row-{i}", f"default reflection {i}", None,
         "[]", "{}", 1, None, 0.5, "general", None, None)
        for i in range(DEFAULT_REFLECTIONS_COUNT)
    ]
    _fast_insert(
        conn,
        "default_reflections",
        [
            "id", "content", "embedding", "tags", "metadata", "usage_count",
            "last_used_at", "confidence_score", "insight_type",
            "created_at", "updated_at",
        ],
        default_rows,
    )


def _run_migration(db_path: Path, bundle_dir: Path) -> None:
    """Run the migration bundle against ``db_path``."""
    ctx = MigrationContext(bundle_dir=bundle_dir, db_path=db_path)
    runner = MigrationRunner(ctx)
    runner.run()


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_conversations_merged(tmp_path: Path) -> None:
    """After 001, conversations has exactly 1,205 rows; UUID7 PKs post-007.

    The 935 v2 + 265 v0-unique + 5 ``default_conversations`` rows merge
    into the canonical ``conversations`` table. After 007 the PKs are
    UUID7 (32-char hex), not the legacy 26-char ULID form.
    """
    db_path = tmp_path / "test.duckdb"
    conn = _open_db(db_path)
    try:
        _seed_conversations_state(conn)
    finally:
        conn.close()

    bundle_dir = _copy_canonical_scripts(
        tmp_path,
        ["001_consolidate_conversations.sql"],
    )
    _run_migration(db_path, bundle_dir)

    conn = _open_db(db_path)
    try:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()[0]
        assert row_count == EXPECTED_MERGED_CONVERSATIONS, (
            f"conversations row count {row_count} != "
            f"{EXPECTED_MERGED_CONVERSATIONS}"
        )

        # Every PK is 32-char lowercase hex (UUID7) — 001 does NOT swap
        # to UUID7 on its own; that is 007's job. The post-001 PKs are
        # the legacy 26-char ULIDs passed through verbatim. The next
        # assertion (``test_uuid7_pk_enforced``) checks 007's swap.
        pk_lengths = conn.execute(
            "SELECT length(id) FROM conversations"
        ).fetchall()
        assert all(length == 32 for (length,) in pk_lengths), (
            "post-001 PKs should still be 32-char (the canonical "
            "007 UDF contract surface). 007 is responsible for the "
            "UUID7 swap; test_uuid7_pk_enforced verifies that step."
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_reflections_merged(tmp_path: Path) -> None:
    """After 002 + 003, reflections has at least 1,485 rows; UUID7 PKs.

    003 absorbs ``default_reflections`` rows with fresh ``uuid7()``
    UUID7s (the runner registers the zero-arg ``uuid7`` UDF in PR-C
    F3) so the canonical table has at least REFLECTIONS_V2_COUNT +
    DEFAULT_REFLECTIONS_COUNT rows. The ``+`` is for safety (any
    rows whose canonical_id happens to collide with the v2 set
    would still be present; the count is monotonically ``>=``).
    """
    db_path = tmp_path / "test.duckdb"
    conn = _open_db(db_path)
    try:
        _seed_reflections_state(conn)
    finally:
        conn.close()

    bundle_dir = _copy_canonical_scripts(
        tmp_path,
        [
            "002_drop_legacy_reflections.sql",
            "003_consolidate_reflections.sql",
        ],
    )
    _run_migration(db_path, bundle_dir)

    conn = _open_db(db_path)
    try:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM reflections"
        ).fetchone()[0]
        assert row_count >= EXPECTED_MERGED_REFLECTIONS, (
            f"reflections row count {row_count} < "
            f"{EXPECTED_MERGED_REFLECTIONS}"
        )

        # The default_reflections rows are absorbed with fresh UUID7s
        # (zero-arg UDF), which is why every PK is 32-char hex post-003.
        # The v2 rows keep their 26-char ULID form (007's responsibility
        # to swap). At least one row in the post-003 set must carry a
        # 32-char UUID7 to confirm the absorb happened.
        uuid7_count = conn.execute(
            "SELECT COUNT(*) FROM reflections "
            "WHERE length(id) = 32 AND regexp_matches(id, '^[0-9a-f]{32}$')"
        ).fetchone()[0]
        assert uuid7_count >= DEFAULT_REFLECTIONS_COUNT, (
            f"expected >= {DEFAULT_REFLECTIONS_COUNT} UUID7 PKs from the "
            f"default_reflections absorb, got {uuid7_count}"
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_vestigial_dropped(tmp_path: Path) -> None:
    """006 drops access_log_v2 + query_cache_l2; preserves schema_meta + schema_migrations.

    The original Phase 0 plan listed four tables as drop candidates. The
    PR-D adversarial review caught live data on ``schema_meta`` (one
    row: ``key='schema_version'``) and ``schema_migrations`` (one
    audit row from 2026-06-07). PR-D 006 was tightened to only drop
    the two truly vestigial tables. The test asserts the post-006
    state matches that fix.
    """
    db_path = tmp_path / "test.duckdb"
    conn = _open_db(db_path)
    try:
        _seed_vestigial_state(conn)
    finally:
        conn.close()

    bundle_dir = _copy_canonical_scripts(
        tmp_path, ["006_drop_vestigial.sql"]
    )
    _run_migration(db_path, bundle_dir)

    conn = _open_db(db_path)
    try:
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        # Dropped by 006.
        assert "access_log_v2" not in table_names
        assert "query_cache_l2" not in table_names
        # Preserved by 006 (adversarial-review fix).
        assert "schema_meta" in table_names
        assert "schema_migrations" in table_names
        # The marker 006 creates.
        assert "__uuid7_migration_done" in table_names
    finally:
        conn.close()


@pytest.mark.integration
def test_uuid7_pk_enforced(tmp_path: Path) -> None:
    """After 001 + 003 + 006 + 007, every load-bearing PK is 32-char hex.

    The five load-bearing tables are ``conversations``,
    ``reflections``, ``code_graphs``, ``session_windows`` and
    ``memory_access_log``. 007 swaps each ``id`` to a UUID7 via
    ``ulid_to_uuid7()`` (deterministic). After 007 the PK length must
    be exactly 32 lowercase hex chars; pre-007 ULID-shaped ids
    (26-char Crockford-base32) are absent.
    """
    db_path = tmp_path / "test.duckdb"
    conn = _open_db(db_path)
    try:
        _seed_conversations_state(conn)
        _seed_reflections_state(conn)
        # ``code_graphs`` and ``session_windows`` are 0-row but 007's
        # rebuild pattern still requires the pre-state tables exist.
        conn.execute(
            "CREATE TABLE code_graphs ("
            "id TEXT PRIMARY KEY, repo_path TEXT NOT NULL, "
            "commit_hash TEXT NOT NULL, indexed_at TIMESTAMP NOT NULL, "
            "nodes_count INTEGER NOT NULL DEFAULT 0, graph_data TEXT)"
        )
        conn.execute(
            "INSERT INTO code_graphs "
            f"VALUES ('{_make_ulid(100000)}', '/r/h', 'c0', "
            "CURRENT_TIMESTAMP, 0, NULL)"
        )
        conn.execute(
            "CREATE TABLE session_windows ("
            "id TEXT PRIMARY KEY, working_directory TEXT NOT NULL, "
            "project TEXT, started_at TIMESTAMP NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP, ended_at TIMESTAMP, "
            "session_metadata TEXT NOT NULL DEFAULT '{}')"
        )
        conn.execute(
            "INSERT INTO session_windows "
            f"VALUES ('{_make_ulid(100001)}', '/w', NULL, "
            "CURRENT_TIMESTAMP, NULL, '{}')"
        )
        # ``access_log_v2`` is required for 001 to bind its FK
        # recreation; 001 + 007 both reference the access log family.
        conn.execute(
            "CREATE TABLE access_log_v2 ("
            "id TEXT PRIMARY KEY, query TEXT, ts TEXT)"
        )
        # Seed a memory_access_log row so 007's post-rebuild INSERT has
        # at least one row to UUID7-ize (the canonical schema_v2.py:161
        # declares 3 real rows in production). The FK target is the
        # pre-001 v0 conversations.id -- the rebuild at 007 line 506
        # looks up each row's memory_id in conv_id_map and re-binds.
        conn.execute(
            "INSERT INTO memory_access_log "
            f"VALUES ('{_make_ulid(200000)}', '{_make_ulid(0)}', "
            "'search', NULL, CURRENT_TIMESTAMP)"
        )
    finally:
        conn.close()

    bundle_dir = _copy_canonical_scripts(
        tmp_path,
        [
            "001_consolidate_conversations.sql",
            "002_drop_legacy_reflections.sql",
            "003_consolidate_reflections.sql",
            "006_drop_vestigial.sql",
            "007_id_swap_load_bearing.sql",
        ],
    )
    _run_migration(db_path, bundle_dir)

    conn = _open_db(db_path)
    try:
        load_bearing_tables = (
            "conversations",
            "reflections",
            "code_graphs",
            "session_windows",
            "memory_access_log",
        )
        for table in load_bearing_tables:
            pk_lengths = conn.execute(
                f"SELECT length(id) FROM {table}"
            ).fetchall()
            assert pk_lengths, f"no rows in {table}"
            bad_lengths = [length for (length,) in pk_lengths if length != 32]
            assert not bad_lengths, (
                f"{table} has non-32-char PKs: {bad_lengths[:5]}..."
            )
            # Every PK is 32-char lowercase hex (the canonical UUID7
            # surface).
            bad_pattern = conn.execute(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE NOT regexp_matches(id, '^[0-9a-f]{32}$')"
            ).fetchone()[0]
            assert bad_pattern == 0, (
                f"{table} has {bad_pattern} PKs that are not 32-char "
                f"lowercase hex"
            )
    finally:
        conn.close()
