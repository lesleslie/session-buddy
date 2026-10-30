---
status: in-progress
role: implementation
date: 2026-10-29
last_reviewed: 2026-10-29
superseded_by: null
blocks_on: []
topic: embeddings
title: "OpenAI Embedding Provider Chain — Width-Aware Fallback and the 4096→768 Migration"
---

# OpenAI Embedding Provider Chain — 2026-10-29

**Goal:** Give session-buddy a real embedding provider with a fallback
chain, and move the canonical width from 4096 to 768 so that a cloud
provider can serve it.

Continues
[`2026-10-29-embedding-dimension-migration.md`](2026-10-29-embedding-dimension-migration.md),
which established the single source of truth
(`session_buddy/memory/embedding_dim.py::DEFAULT_EMBEDDING_DIM`) and
migrated it from the retired 384 to the llama-server's 4096.

## The constraint that shapes everything

The DuckDB embedding columns are **fixed-size ARRAY** columns:

```sql
embedding FLOAT[4096]
```

The width is a schema-level constant, and it is not negotiable at
runtime:

```
ALTER TABLE t ALTER COLUMN e TYPE FLOAT[1536]
  -> Conversion Error: Cannot cast array of size 4096 to array of size 1536
```

So the provider's output width and the column's width must agree,
exactly, forever. That single fact determines what the provider chain
may contain:

| provider | model | width | usable at 4096 | usable at 768 |
|---|---|---|---|---|
| llama-server (chat) | Qwen3-8B-Q4_K_M | 4096 | yes | **no** |
| llama-server (embed) | EmbeddingGemma-300M | 768 | **no** | yes |
| OpenAI | `text-embedding-3-small` | 1536, shortenable | **no** | yes |

**"OpenAI first, llama-server as fallback" is not achievable at a single
fixed width** unless both legs agree on that width. Two facts make it
achievable here:

* **OpenAI's `text-embedding-3-small` is Matryoshka-trained**, so its
  `dimensions` parameter shortens it to any width. Verified against the
  live gateway: `dimensions=1056` → 1056 dims, `dimensions=768` → 768
  dims. The cloud leg can match whatever width the column uses.
* **A local embedding model can be chosen to match the column.** The
  width is therefore a free choice, not a constraint imposed by the
  cloud.

The width was chosen to be **768**, because that is what
EmbeddingGemma-300M produces natively — and a model whose native width
*is* the canonical width needs no truncation, which matters because
llama.cpp cannot truncate embeddings.

## The measured dimensions

Nothing here is taken from documentation; every figure was measured
against the running services.

| what | measured | how |
|---|---|---|
| EmbeddingGemma-300M via llama.cpp | **768** dims, L2 norm 1.0 | `POST :8082/v1/embeddings` |
| `text-embedding-3-small` via the gateway | **768** dims at `dimensions=768` | `POST :8471/v1/embeddings` |
| `text-embedding-3-small` via the gateway | 1056 dims at `dimensions=1056` | same |
| Qwen3-8B via the chat server | 4096 dims | `POST :8081/v1/embeddings` |

The 768 figure for EmbeddingGemma was the one that changed the design:
the model was expected to be 1056-dim, and the measurement said
otherwise. A local model at 1056 would have been fine — OpenAI matches
it — but 768 buys a *much* better local model, because 768 is the
classic BERT-base width with many strong options behind it.

## What makes the migration affordable

**The gateway already serves the target model.** The local Bifrost
gateway is an OpenAI-compatible endpoint on `127.0.0.1:8471`, and it
answers `POST /v1/embeddings` with `model: text-embedding-3-small`. No
new credential is needed — the gateway's own semantic-cache plugin is
configured for exactly that model at exactly that dimension. There is
also a working `OPENAI_API_KEY` in the environment, so the direct cloud
leg is live too.

**A width mismatch is loud, not corrupting.** Binding a wrong-width
vector raises a clean `ConversionException` and leaves the instance
healthy — `CHECKPOINT` still succeeds afterwards:

```
col=FLOAT[4096] value=1536 -> RAISED ConversionException | healthy
col=FLOAT[1536] value=4096 -> RAISED ConversionException | healthy
col=FLOAT[4096] value=4096 -> OK                        | healthy
```

This matters for the migration ordering. The "poison" signature
investigated in the sibling plan (*"Operation requires a flat or
constant vector"*) comes from the **WAL-replay HNSW rebuild**, not from
a wrong-width write. So new code meeting an old schema costs failed
writes, not the database. The sibling plan's attribution of the poison
to the width mismatch was wrong, and has been corrected in
`session_buddy/memory/embedding_dim.py`.

**The store is nearly empty.** The live reflection database holds 10
rows, 1 with an embedding. The ~3 600 rows cleared by the sibling plan
are gone, so there is no 8–10 hour backfill: 10 rows through the
gateway is sub-second.

## Design: a width-aware provider chain

Each leg declares the width it produces. A leg is **eligible** only if
its width matches the canonical dimension. The chain tries eligible legs
in order and returns the first vector.

```
openai_gateway  (768)  ->  primary: the local Bifrost gateway
openai_direct   (768)  ->  api.openai.com, when a key is present
llama_embed     (768)  ->  the local EmbeddingGemma server on :8082
llama_server    (4096) ->  skipped at a 768 canonical width
```

Two independent guards keep the chain honest:

1. **Eligibility** — a leg whose declared width differs from the
   canonical dimension is skipped without a network call.
2. **Validation** — every returned vector is length-checked against the
   canonical dimension before it leaves the chain. This is the
   authoritative gate, and it is what makes the design robust to a
   *wrong* declared width: a leg that lies about its width is caught
   here rather than at the DuckDB bind.

The chat-server leg is **not deleted** — it is skipped because its width
does not match. Change the canonical width and it becomes eligible again
with no code change.

## Changes

| File | Change |
|---|---|
| `session_buddy/memory/embedding_dim.py` | `DEFAULT_EMBEDDING_DIM` 4096 → **768**; the poison attribution corrected |
| `session_buddy/reflection/embeddings.py` | Width-aware chain: `openai_gateway`, `openai_direct`, `llama_embed`, `llama_server`; each declares its width |
| `session_buddy/reflection/embeddings.py` | `get_embedding_system_info()` reports the eligible legs, the skipped ones and the active one |
| `scripts/migrate_embedding_dim.py` | **New.** Migrates a live DuckDB file to a new width |
| `tests/unit/reflection/test_embeddings_provider_chain.py` | **New.** Chain selection, width gating, validation |
| `tests/unit/scripts/test_migrate_embedding_dim.py` | **New.** The migration: width, rows, HNSW options, foreign keys |

The width is derived everywhere from `DEFAULT_EMBEDDING_DIM` already —
`reflection/schema.py`, `memory/schema_v2.py`,
`adapters/knowledge_graph_adapter_oneiric.py`,
`core/causal_chains.py`, `adapters/settings.py`. Only the constant
moves.

## The migration

DuckDB cannot widen a fixed-size ARRAY column, and it cannot drop one
either: a column cannot be dropped while an index covers a later column,
and a table cannot be altered while a foreign key points at it. The
migration therefore **rebuilds the database**.

The rebuild uses DuckDB's own `EXPORT DATABASE` / `IMPORT DATABASE`
machinery, because that is the only route that reproduces the schema
faithfully. Every constraint, check, foreign key and index — including
the HNSW indexes with their `WITH (M = ..., ef_construction = ...)`
options — comes back exactly as it was.

The sequence:

1. `EXPORT DATABASE` the source to a temporary directory.
2. Rewrite `FLOAT[4096]` → `FLOAT[768]` in the exported schema. The
   rewrite is **validated to be width-only**: mapping the new width back
   to the old one must reproduce the original text exactly.
3. Create the tables (without the indexes), copy every row **minus the
   vector columns**, then create the indexes.

The vectors are dropped, not converted: they were produced by the old
provider in the old vector space and carry no meaning in the new one.
They are re-embedded from the row's text.

The indexes are created *after* the data load, deliberately: rebuilding
an HNSW index over rows that came from a WAL replay is the operation
that poisons the instance (see `session_buddy/memory/duckdb_open.py`).

The script is **non-destructive by default** — it writes the rebuilt
database to a new path and leaves the input alone. `--replace` is
required to put it in place, and it backs the original up first.

## Integration contract

- **Triggered from** — `generate_embedding()`, the reflection adapter's
  quantization path, `SkillsEmbeddingService`, `store_reflection`.
- **Returns to** — callers receive 768-dim vectors, or `None` when no
  eligible leg is reachable.
- **Demonstrable by** —
  `tests/unit/reflection/test_embeddings_provider_chain.py`; a live
  probe of the gateway's `/v1/embeddings`; the live database showing
  `FLOAT[768]` columns with non-NULL embeddings.
- **Rollback signal** — `generate_embedding()` returns `None` while the
  gateway is reachable, or the width-mismatch warning from
  `coerce_embedding` fires.
- **Observability added** — `get_embedding_system_info()` reports the
  eligible legs and which one served the last vector.

## Still open

- **The live database has not been migrated yet.** It is still
  `FLOAT[4096]`, and the code is now at 768, so the running server
  would fail every vector write until the migration runs. The migration
  needs the server stopped (DuckDB is single-writer).
- **The embedding server is not yet durable.** EmbeddingGemma-300M runs
  on `:8082` alongside the chat server on `:8081`; one llama.cpp instance
  cannot serve both models. It needs its own launchd plist.
- **`skills_embeddings`** packs vectors as fixed-width blobs. Its
  on-disk format changes with the dimension, so any existing packed
  blobs become unreadable. The live skills store is not populated, but
  the format version is not recorded in the blob header.
- **The test suite runs at 384** while production will run at 768.
  Those are self-consistent test worlds (deliberate, per the sibling
  plan) — `tests/unit/conftest.py` stubs the provider with a 384-dim
  fake — but the gap is now wider, and a test that exercises the chain
  has to restore the real function to escape the stub.
- **The legacy `ReflectionDatabase` write path** still targets the
  retired V1 tables (unchanged by this work; see the sibling plan).
- **`OPENAI_API_KEY` is absent** from `~/.config/secrets.env` even
  though it is set in the environment, so a launchd-spawned server does
  not get the direct cloud leg — only the gateway one.
