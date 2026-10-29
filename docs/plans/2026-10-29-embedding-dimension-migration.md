---
status: shipped
role: implementation
date: 2026-10-29
last_reviewed: 2026-10-29
superseded_by: null
blocks_on: []
topic: embeddings
title: "Embedding Dimension Migration — Canonical Width and Calibration"
---

# Embedding Dimension Migration — 2026-10-29

**Goal:** Make every embedding path agree with the provider that actually
serves vectors. The provider (llama-server on `:8081`, Qwen3-8B) returns
**4096-dim** vectors; seven modules still carried the retired
all-MiniLM-L6-v2 **384**-dim width, which made the entire reflection and
semantic-search path silently inert.

## The defect

Two independent gates blocked every embedding:

1. **The URL.** `reflection/embeddings.py` defaulted
   `MAHAVISHNU__LLAMA_SERVER_URL` to `http://localhost:8080/v1`. Nothing
   listens on 8080 — the server is on 8081. Every call failed with
   `ConnectionRefused`.
2. **The width.** `_try_llama_server` accepted a vector only when
   `len(embedding) == 384`. The served model returns 4096, so even with the
   right URL every vector was rejected.

Neither raises. `generate_embedding()` returned `None`, `coerce_embedding`
dropped the row, and the feature looked alive while doing nothing. The
*only* symptom was that the semantic path never found anything.

The irony worth recording: `session_buddy/memory/embedding_dim.py` had
**already** been migrated to 4096 — with a docstring explaining exactly this
failure mode ("Historically this was 384 … The llama-server now serves
Qwen3-8B, whose `/v1/embeddings` endpoint returns 4096-dim vectors").
`reflection/search.py` and `adapters/settings.py` both imported the canonical
constant. The reflection gate was the last holdout, and it was the only one
on the request path.

## Why the width alone was not the fix

Fixing only the gate would have converted a *silent* no-op into a *loud*
failure in two dependents:

- `adapters/reflection_adapter_oneiric.py` built its quantization
  calibration as `np.full((384,), ...)`. A 4096-element vector broadcast
  against a 384-element array raises on shape mismatch.
- `storage/skills_embeddings.py` packed embeddings as 1536-byte blobs and
  asserted `shape == (384,)`.

So the migration had to reach every site that hardcoded a width, not just
the gate.

## Changes

| File | Change |
|---|---|
| `reflection/embeddings.py` | URL default → `:8081`; `EMBEDDING_DIM` → `DEFAULT_EMBEDDING_DIM`; the width gate → `len(embedding) == EMBEDDING_DIM` |
| `storage/skills_embeddings.py` | `EMBEDDING_DIM` → `DEFAULT_EMBEDDING_DIM` (the packed-blob format follows) |
| `health_checks.py` | llama-server probe URL default → `:8081` |
| `adapters/reflection_adapter_oneiric.py` | calibration arrays → `(self.embedding_dim,)` |
| `utils/lazy_imports.py` | mock vectors → canonical width; `create_embedding_mock()` deleted (dead) |
| `reflection/database.py`, `core/causal_chains.py`, `storage/skills_storage.py`, `adapters/knowledge_graph_adapter_oneiric.py`, `session_commands.py` | stale width references in docstrings |

Test fixtures in `tests/test_skills_semantic.py`,
`tests/test_skills_workflow.py`, `tests/unit/test_embedding_cache.py` and
`tests/unit/test_embedding_quantization.py` now derive their vectors from
`DEFAULT_EMBEDDING_DIM` instead of a literal.

### The dead ONNX embedding machinery

ONNX was removed in Phase 5, but its mock scaffolding survived with no
production consumer:

- `session_buddy/utils/lazy_imports.py::create_embedding_mock()` — a
  sentence-transformers-shaped mock with no production caller.
- `tests/helpers.py::MockingHelper.mock_embedding_system()` and
  `mock_onnx_session_with_specific_return()` — both unused outside a test
  that asserted the mock's own shape.
- `tests/conftest.py::mock_onnx_session` and `mock_tokenizer` — pytest
  fixtures no test requested.

All removed, along with the docstrings that still described ONNX as the
embedding mechanism (`reflection/__init__.py`, `storage/skills_embeddings.py`,
`modes/base.py`, `modes/lite.py`, `modes/standard.py`,
`memory/schema_v2.py`).

### The quantization calibration is a second, separate constant

`_get_calibration_data` returns a fixed `±0.15`, inherited from the
MiniLM era. That constant is a property of the model's *output
distribution*, not of the code. Measured against live embeddings:

The served vectors are L2-normalised (unit norm), with a median |component|
of ~0.003 and a tail reaching ~0.55. Scalar quantisation maps
`[min, max]` onto 256 levels, so the range must cover the tail — clipping
it costs more cosine similarity than a wider range costs in step size.

| Range | Min cosine over sampled embeddings |
|---|---|
| ±0.15 (old) | **0.893** — below the 0.95 accuracy threshold |
| ±0.25 | 0.951 |
| **±0.50** | **0.988** |
| ±1.00 | 0.959 |

The fixed fallback is now `±0.5`, with the measurements recorded in the
code. `_update_calibration_data` (per-dimension, computed from stored
embeddings) is the data-derived alternative and remains unwired — it is the
right long-term answer, and it removes the model-specific constant entirely.

`enable_quantization` defaults to `False`, so this path is opt-in.

## Test changes

- `test_quantization_accuracy_with_random_embeddings` generated vectors
  scaled to norm 0.1. The provider returns **unit-norm** vectors, so the
  synthetic data was 10× smaller than reality and the signal-to-quantisation
  ratio was wrong by two orders of magnitude. The scaling was removed.
- `test_batch_embedding_generation` asserted a 10 s budget for 32
  embeddings. It only ever passed *because the provider was dead* — every
  call failed fast with `ConnectionRefused`, so the timing assertion was
  vacuous. Against the live CPU-only server a batch of 32 takes ~150 s, so
  the test is now marked `@pytest.mark.slow` + `@pytest.mark.external` with
  a 300 s hang/regression budget.

## Deliberately out of scope

`tests/conftest.py` and `tests/unit/conftest.py` configure
`embedding_dim=384` for their fixtures. Those are **self-consistent** test
worlds (384-dim vectors with `FLOAT[384]` columns, and
`enable_embeddings=False` / `enable_vss=False` where the width only picks
the column type). The width there is a deliberate parameter for speed, not
drift. Aligning them with production would change every unit-test DuckDB
schema width — 10× wider embedding columns — with no defect to fix, and
would have made the quantization-broadcast bug above invisible to the suite.

## Integration contract

- **Triggered from** — any embedding request; `generate_embedding`,
  `SkillsEmbeddingService`, the reflection adapter's quantization path.
- **Returns to** — callers now receive 4096-dim vectors (or `None` when the
  provider is unreachable, as before).
- **Demonstrable by** — `tests/unit/test_embedding_cache.py`,
  `tests/unit/test_embedding_quantization.py`, `tests/test_skills_semantic.py`,
  `tests/test_skills_workflow.py`; live probe of `:8081/v1/embeddings`.
- **Rollback signal** — `generate_embedding` returns `None` while the
  provider is reachable, or a width mismatch warning from
  `coerce_embedding`.
- **Observability added** — the `coerce_embedding` width-mismatch warning
  now fires on the real dimension, which is how the drift was detected.

## Still open

- **`ReflectionDatabase` never generates an embedding.**
  `session_buddy/reflection/database.py` gates every embedding call on
  `if self.onnx_session:` — a backward-compat stub that always returns
  `None`, left over from the ONNX removal. `get_embedding()` itself works
  (it calls the HTTP provider), so the gate is the only thing blocking it.
  The consequence is measurable in the live database: **2696 stored rows**
  across `conversations`, `default_conversations` and `reflections` have
  **no embedding at all**, and `get_stats()` always reports
  `"text-search-only"`.

  Flipping the gate is width-safe — every embedding column in the live
  database is already `FLOAT[4096]` — but the vector query filters
  `WHERE embedding IS NOT NULL` and there is no hybrid merge with the text
  path. So enabling it *without* a backfill would hide those 2696 existing
  rows from semantic search; enabling it *with* a backfill is a
  migration against a live database. Both are decisions, not a mechanical
  fix, so neither was taken here. The modern adapter
  (`adapters/reflection_adapter_oneiric.py`) shows the intended pattern:
  gate on `settings.enable_embeddings`, call the HTTP provider, and fall
  back to text search when it returns `None`.
- **Per-dimension calibration.** The fixed `±0.5` fallback is correct for
  the current model and must be re-derived whenever the model changes.
  `_update_calibration_data` already computes calibration from stored
  embeddings; wiring it into the default path would retire the constant.
- **The test suite runs at a different width than production** (384 vs
  4096), so width-dependent bugs in the shared conftest world stay
  invisible. A fixture that parameterises the width would close that gap.
- **`tests/conftest.py::sample_embedding`** returns a 384-dim vector and is
  dead code — no test references it.
- **Six pre-existing test failures** in `tests/functional/test_simple_validation.py`
  and `tests/security/test_input_validation.py` fail with *"Table with name
  conversations does not exist! Did you mean conversations_v2?"*. v1 was
  retired in `cebc6a79` (schema v2 promotion, 2026-10-04) and these tests
  still expect the v1 table. Reproduces identically at pristine HEAD.
