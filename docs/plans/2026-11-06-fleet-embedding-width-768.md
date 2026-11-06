---
status: draft
role: implementation
date: 2026-11-06
last_reviewed: 2026-11-06
superseded_by: null
blocks_on: []
topic: embeddings
---

# Fleet Embedding Width 768 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Bodai fleet exactly one embedding width — 768 — served by one OpenAI-compatible leg in Oneiric, with Mahavishnu migrated off 384 and Crackerjack's hash pseudo-vectors replaced by real vectors.

**Architecture:** Oneiric's observability `EmbeddingService` gains an OpenAI leg, probed ahead of the existing chain, that reuses the `OpenAIEmbeddingAdapter` Oneiric already ships — so credential resolution, `dimensions` handling, batching, retries, and rate limiting are not re-implemented. Every component that declares a width moves to 768, and every component that writes to a fixed-width vector column **rejects** a vector of any other width rather than coercing it. Crackerjack's per-repo semantic index switches from SHA-256 pseudo-vectors to real embeddings on two paths — OpenAI for the search path, a deterministic local lexical embedder for the fixer path — both at 768, so the index keeps one shape.

**Tech Stack:** Python 3.14, `httpx2` (imported as `import httpx2 as httpx` — the fleet convention), DuckDB 2.0 `FLOAT[N]`, PostgreSQL + pgvector, numpy, pytest.

**Spec:** `session-buddy/docs/specs/2026-11-05-conversation-transcript-ingestion-design.md` (§ *Embedding: one embedder for the fleet*, § *NEW (fleet): Oneiric OpenAI embedding leg*, § *NEW (fleet): Mahavishnu 384 → 768*, § *NEW (fleet): Crackerjack real embeddings*). The spec travels with this plan; executors read both.

**Sequencing:** The operator chose to run this plan **before** the conversation-ingestion plan. That ordering is a preference, not a hard dependency: `session_buddy.memory.embedding_dim.DEFAULT_EMBEDDING_DIM` is already 768 and this plan does not change it. The ingestion plan's own dependency on this one was re-examined during review and found unfounded — it is corrected there.

> **Revised after an 8-agent multi-lens review** (3 lenses × 2 plans, then an adversarial adjudicator per plan). 29 findings were confirmed against the source and are folded in here. The ones that changed the design: the OpenAI leg now **reuses** Oneiric's existing `OpenAIEmbeddingAdapter` rather than adding a parallel implementation; the base-URL convention is now stated once and applied consistently; and the credential wiring now resolves from the environment instead of from a plain `BaseModel` that nothing populated.

## Global Constraints

- **Fleet embedding width: 768.** The source of truth is the module-level constant `FLEET_EMBEDDING_DIM` in `oneiric/adapters/observability/embeddings.py`. Every other repo mirrors it with its own module-level `int` constant (named below) so a cross-repo check can read them without importing across repos.
- **Model:** `text-embedding-3-small` with `dimensions=768` (Matryoshka-shortened). No other model produces the fleet width.
- **Oneiric probe order (after this plan):** `openai_gateway → openai_direct → llama_cpp → minimax → model2vec → mock`.
- **Oneiric `backend_name()` returns `"openai"`** for both OpenAI legs, so `BACKEND_DEFAULT_DIMS["openai"]` resolves. The specific leg is exposed separately as `EmbeddingService.backend_leg()`.
- **Base-URL convention (one rule, applied everywhere in this plan):** a base URL **includes the API prefix** (`https://api.openai.com/v1`, `http://localhost:8471/v1`), and the embeddings endpoint is `{base}/embeddings`. The existing `llama_cpp` leg is the one exception — it uses a bare root plus `/v1/embeddings` — and is left unchanged. Do not mix the two conventions: a base that already ends in `/v1` plus a `/v1/embeddings` suffix produces `/v1/v1/embeddings` and a guaranteed 404.
- **Wrong-width vectors are rejected, never coerced.** A component writing to a fixed-width column (`FLOAT[N]`, `vector(N)`) raises on a width mismatch. This is the invariant that makes the fleet safe when a non-768 fallback leg is selected.
- **`model2vec` (256) and `minimax` (1024) keep their native widths** and are *not* fleet-width-safe. This is documented, not silently tolerated: reaching either leg produces vectors that the fixed-width stores reject.
- **The `mock` fallback widens 384 → 768**, so an offline deployment still writes fleet-width vectors. Assigned to B1 Step 3 and B3 Step 3.
- **Bifrost authentication uses the gateway virtual key** (`BIFROST_VIRTUAL_KEY`), never a provider key — the gateway rejects a provider key with `401 virtual_key_required`.
- **Direct OpenAI authentication uses `OPENAI_API_KEY`.** Read it from the environment at call time; never inline a literal.
- **Pre-1.0 replace, do not extend.** No backwards-compatibility shims for the old widths.
- **Python 3.14.** `from __future__ import annotations` is the first non-comment line of every source file. Imports sorted stdlib → third-party → first-party.
- **HTTP is `httpx2`, imported as `import httpx2 as httpx`.** This is the fleet convention (oneiric's own embeddings adapter, Crackerjack's `skills/github_client.py`, `mcp/oneiric_runtime.py`, and five other Crackerjack modules). A literal `import httpx` fails at module import.
- **Type gate is `ty`, not mypy.** Resolve `ty` from `PATH` and its deps from `$VIRTUAL_ENV`; check both before concluding a type error is real. Never a bare `# type: ignore` — use `# ty: ignore[<code>]`. Mass suppressions are a smell: more than 5 in one file means stop and audit.
- **`logger.exception(...)` inside `except` blocks**, never `logger.error(..., exc_info=True)`.
- **Never bump a Bodai `pyproject.toml` version.** The operator owns version bumps and publishing.

### Per-repo lint and test gates

These differ materially. Do not assume the fleet is uniform.

| Repo | ruff select | max-complexity | max-args | pytest timeout | `--cov-fail-under` |
|---|---|---|---|---|---|
| oneiric | `C901, F, I, UP` | 15 | — | — | 78.75 |
| **session-buddy** | **`BLE001`, `C901, F, I, UP`** | 15 | — (no `P`) | 600 s | 2.45 |
| akosha | `E, W, F, I, B, C4, UP, ARG, SIM, TCH, PTH, ERA, RUF` (E501 ignored) | — | — | — | 89.0 |
| mahavishnu | `I, N, UP, B, C4, SIM, TCH, ASYNC221/230, BLE001, DTZ001, …` + `P` | 15 | **10** | 300 s | 89.0 |
| crackerjack | `C901, F, I, UP` | **25** | — | — | 68.4 |

Consequences that apply to this plan:

- **`BLE001` is selected in session-buddy and mahavishnu** but not in oneiric, akosha, or crackerjack. A blind `except Exception` needs `# noqa: BLE001` plus a justification comment in those two repos only. In akosha (which selects `RUF`) the house form is `# noqa: BLE001, RUF100`.
- **`max-args = 10` is enforced only in mahavishnu** (`P` subset). Keep every new mahavishnu function at 10 parameters or fewer.
- **`DTZ001` is selected in mahavishnu** — every `datetime` must be timezone-aware. Use `datetime.now(UTC)`.
- **Akosha selects `ARG` (unused arguments), `PTH` (use `pathlib`), and `ERA` (no commented-out code).**
- **Markers are per-repo.** `mcp`, `requires_network`, and `requires_auth` exist only in mahavishnu; the other four run pytest with `--strict-markers`, so an unregistered marker aborts the whole session. Use only markers registered in the target repo's `pyproject.toml` `[tool.pytest.ini_options] markers` list.
- **`--cov-fail-under` is set in all five repos' pytest `addopts`**, so running a subset of tests always ends in a coverage-gate failure. **Every per-task pytest command in this plan uses `--no-cov`**, and its pass criterion is "N passed", not a zero exit code. Each repo's full suite, run once at the end of its last task, is the coverage gate.

### Prerequisites (cross-repo publish order)

Oneiric is installed **non-editably** into the dependent venvs. A change to `oneiric/adapters/vector/duckdb_hot_store.py` does not reach Mahavishnu until oneiric is published and the dependent venvs are reinstalled — and this plan forbids the version bump and publish, because the operator owns both.

Therefore:

- **B4 must not depend on B2 taking effect.** B4 pins Mahavishnu's `DuckdbHotStore` to an explicit `embedding_dim=768` rather than relying on the installed default.
- The operator publishes oneiric (and bumps its version) as a separate step after this plan lands. The runbook in B4 Step 7 records that order.

## Review Focus

The five inputs the spec implies but no single task's tests exercise — most likely to bite first. Each line gets its test added to the task that owns the code.

1. **No Bifrost gateway and no `OPENAI_API_KEY`** — every OpenAI probe fails, the chain falls through to `llama_cpp`/`minimax`/`model2vec`/`mock`, and the width is not 768. A reasonable person expects the write to be **refused with a message naming the actual width and the required width**, not a raw binder error and not a silently coerced vector.
2. **A stale DuckDB file written before this plan** — its `CREATE TABLE` baked in `FLOAT[384]`, and `CREATE TABLE IF NOT EXISTS` will not widen it. Expected: a clear "rebuild required" error naming the file path, not a `Conversion Error` at insert time.
3. **A Postgres row in `search.document_embeddings` whose `embedding_dim` still reads 384** after the column widened to `vector(768)` — `embedding_dim` is a separate `INT NOT NULL` column and does not auto-update. Expected: the backfill rewrites it to 768, and a query filtering `embedding_dim = 384` returns nothing rather than mismatched rows.
4. **A Crackerjack per-repo index holding 384-wide BLOBs** after the upgrade. The `embeddings` table has no width column, so a stale BLOB is read as if it were 768. Expected: the index records its width, a mismatch is **detected and the index rebuilt** — and the current failure mode is a loud numpy shape `ValueError`, not a silent mis-score.
5. **A session-buddy `FLOAT[768]` column receiving a 384-wide vector** — the class of bug that has already poisoned this fleet's DuckDB WAL. Expected: the insert fails cleanly and the WAL is not left in a poisoned state; the failure names both widths.

---

### Task B1: Oneiric — the OpenAI embedding leg

**Files:**
- Modify: `oneiric/oneiric/adapters/observability/embedding_settings.py` — the two OpenAI legs' settings + a `from_env()` factory
- Modify: `oneiric/oneiric/adapters/observability/embeddings.py` — probe order, encode path, `FLEET_EMBEDDING_DIM`, `backend_leg()`, env-backed credential resolution
- Modify: `oneiric/oneiric/adapters/observability/queries.py` — the hard-coded 384 shape check
- Modify: `oneiric/oneiric/adapters/observability/models.py` — `Vector(FLEET_EMBEDDING_DIM)`
- Modify: `oneiric/oneiric/adapters/observability/settings.py` — `embedding_dimension` default
- Modify: `oneiric/oneiric/adapters/observability/migrations.py` — recreate `otel_traces.embedding` as `VECTOR(768)`
- Test: `oneiric/tests/adapters/test_observability_embeddings.py` — the probe-chain tests live here, along with the `_install_mock_client` MockTransport helper
- Test: `oneiric/tests/adapters/observability/test_embeddings.py` — extend for the new leg

**Interfaces:**
- Consumes: nothing (first task in the plan). Reuses `oneiric.adapters.embedding.openai.OpenAIEmbeddingAdapter` / `OpenAIEmbeddingSettings` and `oneiric.adapters.embedding.embedding_interface.EmbeddingBaseSettings`.
- Produces:
  - `oneiric.adapters.observability.embeddings.FLEET_EMBEDDING_DIM: int = 768`
  - `EmbeddingSettings.from_env() -> EmbeddingSettings` — classmethod factory that populates the credential and endpoint fields from the environment.
  - `EmbeddingSettings.openai_gateway_enabled: bool = True`
  - `EmbeddingSettings.openai_gateway_base_url: str = "http://localhost:8471/v1"` (includes the API prefix)
  - `EmbeddingSettings.openai_gateway_api_key: str | None = None`
  - `EmbeddingSettings.openai_gateway_model: str = "text-embedding-3-small"`
  - `EmbeddingSettings.openai_gateway_dimensions: int = 768`
  - `EmbeddingSettings.openai_direct_enabled: bool = True`
  - `EmbeddingSettings.openai_direct_base_url: str = "https://api.openai.com/v1"` (includes the API prefix)
  - `EmbeddingSettings.openai_direct_api_key: str | None = None`
  - `EmbeddingSettings.openai_direct_model: str = "text-embedding-3-small"`
  - `EmbeddingSettings.openai_direct_dimensions: int = 768`
  - `EmbeddingSettings.mock_dimension: int = 768` (was 384)
  - `EmbeddingService.backend_leg() -> str` — one of `"openai_gateway"`, `"openai_direct"`, `"llama_cpp"`, `"minimax"`, `"model2vec"`, `"mock"`, `"uninitialized"`.
  - `EmbeddingService.backend_name() -> str` — unchanged contract, but now returns `"openai"` for **both** OpenAI legs. Existing callers that key on `"llama_cpp"`/`"minimax"`/`"model2vec"`/`"mock"` are unaffected.

**Why the OpenAI leg reuses `OpenAIEmbeddingAdapter`.** Oneiric already ships `oneiric/adapters/embedding/openai.py` with `OpenAIEmbeddingSettings(EmbeddingBaseSettings)` and `OpenAIEmbeddingAdapter(EmbeddingBase)`. `EmbeddingBaseSettings` is a pydantic `BaseSettings` with `env_prefix="EMBEDDING_"`, `env_nested_delimiter="__"`, `extra="allow"`, and `api_key: SecretStr | None`; the OpenAI subclass adds `dimensions: int | None`, and `_prepare_request_params` adds the `dimensions` field **only** for `text-embedding-3*` models (`openai.py:217-218`). It also handles batching, retries, and rate limiting. Re-implementing an OpenAI client next to it would duplicate all of that.

The credential gap is closed by the same mechanism: `EmbeddingService.__init__` currently does `settings or EmbeddingSettings()` against a plain `BaseModel` that **nothing ever populates** — `otel.py:31` and `akosha/processing/embeddings.py:162` both construct it with defaults, so every key field stays `None`. `EmbeddingSettings.from_env()` plus `settings or EmbeddingSettings.from_env()` fixes every construction site at once.

- [ ] **Step 1: Write the failing tests**

Add to `oneiric/tests/adapters/test_observability_embeddings.py` (this file already holds the probe-chain tests and the `_install_mock_client` MockTransport helper — model the new class on it, and import `httpx2 as httpx`):

```python
class TestOpenAIBackend:
    async def test_gateway_probe_selects_openai_and_reports_768(self) -> None:
        """The gateway leg is probed first and sets the live dimension."""

    async def test_gateway_wins_over_direct(self) -> None:
        """Both legs reachable -> gateway is selected, backend_leg() == "openai_gateway"."""

    async def test_direct_used_when_gateway_unreachable(self) -> None:
        """Gateway probe fails, direct probe succeeds -> backend_name() == "openai"."""

    async def test_encode_posts_to_base_plus_embeddings(self) -> None:
        """The endpoint is {base}/embeddings with the configured base, not /v1/v1/embeddings."""

    async def test_encode_sends_dimensions_768(self) -> None:
        """The request body carries "dimensions": 768."""

    async def test_openai_failure_falls_through_to_llama_cpp(self) -> None:
        """Both OpenAI probes fail -> the chain continues to llama_cpp."""

    def test_fleet_embedding_dim_is_768(self) -> None:
        """FLEET_EMBEDDING_DIM == 768."""

    def test_from_env_populates_the_gateway_key(self, monkeypatch) -> None:
        """from_env() reads BIFROST_VIRTUAL_KEY into the gateway key field."""

    def test_from_env_populates_the_direct_key(self, monkeypatch) -> None:
        """from_env() reads OPENAI_API_KEY into the direct key field."""
```

The `encode_posts_to_base_plus_embeddings` test is the one that catches the doubled-`/v1` bug: assert the request URL equals `f"{base}/embeddings"` for the configured base.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/oneiric && .venv/bin/pytest tests/adapters/test_observability_embeddings.py tests/adapters/observability/test_embeddings.py -k "OpenAI or fleet" --no-cov -v`
Expected: FAIL — `FLEET_EMBEDDING_DIM` does not exist, `from_env` does not exist, and the probe chain has no OpenAI leg.

- [ ] **Step 3: Add the OpenAI settings and the env factory**

In `embedding_settings.py`:

- Add the fields listed in the Interfaces block, in an `# OpenAI-compatible legs` section placed before the llama.cpp section.
- Add the two OpenAI fields to the class docstring's `Attributes:` list.
- Add the classmethod:
  ```python
  @classmethod
  def from_env(cls) -> EmbeddingSettings:
      """Populate the OpenAI credential and endpoint fields from the environment."""
  ```
  It reads `BIFROST_VIRTUAL_KEY` into `openai_gateway_api_key`, `OPENAI_API_KEY` into `openai_direct_api_key`, and `EMBEDDING_BASE_URL` into `openai_gateway_base_url` **when that variable is set** (so an operator can point the gateway leg at a Bifrost on a non-default host). It must not raise when a variable is absent — the corresponding leg simply stays unconfigured and its probe returns `False`.
- Change `mock_dimension: int = Field(default=384, ...)` to `default=768`, and update its docstring.

- [ ] **Step 4: Implement the probe and encode legs**

In `embeddings.py`:

- Add the module-level `FLEET_EMBEDDING_DIM: int = 768`.
- Add `self._backend_leg: str = "uninitialized"` in `__init__`, mirroring `_backend`.
- Change `self._settings = settings or EmbeddingSettings()` to `self._settings = settings or EmbeddingSettings.from_env()`.
- Add `async def _probe_openai(self, leg: str) -> bool` — one implementation, parameterised by leg name. It:
  - reads the leg's `enabled` flag, base URL, api key, model, and dimensions from `self._settings`;
  - returns `False` immediately when the key is absent;
  - builds the endpoint as `f"{base_url.rstrip('/')}/embeddings"` — **the base already includes `/v1`**;
  - POSTs `{"model": model, "input": ["probe"], "dimensions": dimensions}` with `Authorization: Bearer <key>`;
  - on HTTP 200 with `body["data"][0]["embedding"]`, sets `self._backend_dim = len(embedding)` and returns `True`.
- Add `async def _probe_openai_gateway(self) -> bool` and `async def _probe_openai_direct(self) -> bool`, each delegating to `_probe_openai("openai_gateway" | "openai_direct")`.
- Insert the two OpenAI legs at the **front** of the `probe_order` tuple in `initialize()`, and set `self._backend_leg = name` alongside `self._backend = name`. For the OpenAI legs set `self._backend = "openai"`.
- Add `async def _encode_openai(self, texts: list[str]) -> list[np.ndarray]` that POSTs the same body shape and returns one `np.ndarray` per `body["data"]` entry.
- In `encode()` and `encode_batch()`, route `self._backend == "openai"` to `self._encode_openai(...)`.
- Add `def backend_leg(self) -> str` returning `self._backend_leg`.
- Update the module docstring's backend list to the new probe order and note that `backend_name()` collapses both OpenAI legs to `"openai"`.

- [ ] **Step 5: Widen the observability subsystem's hard-coded 384**

Oneiric's own observability layer hard-codes 384 in four more places, so the OTel trace-similarity path would reject every 768-wide vector the new leg produces:

- `queries.py` — widen the shape check to the configured dimension, or drop the hard-coded check.
- `models.py` — `Vector(FLEET_EMBEDDING_DIM)`.
- `settings.py` — `embedding_dimension` default → 768.
- `migrations.py` — a migration that recreates `otel_traces.embedding` as `VECTOR(768)`. **Rebuild, not ALTER** — a stored 384-wide vector cannot be widened in place.

**Mahavishnu inherits this default.** `mahavishnu/core/config.py:990`'s `OTelStorageConfig` takes `embedding_dimension` from it, so `mahavishnu/tests/unit/test_mahavishnu_config.py:230` (`assert config.embedding_dimension == 384`) must be re-pinned to 768. That test file is changed in **B4**, not here — list it in B4's Files block.

- [ ] **Step 6: Update the five assertions that pin the old mock width**

Widening `mock_dimension` to 768 breaks existing oneiric assertions. Locate them by grepping the oneiric test tree for `384` in an embedding-dimension context and re-pin each to 768. Add the file paths you changed to this task's commit command.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd ~/Projects/oneiric && .venv/bin/pytest tests/adapters/test_observability_embeddings.py tests/adapters/observability/test_embeddings.py --no-cov -v`
Expected: PASS — all pre-existing tests plus the nine new ones.

- [ ] **Step 8: Run the wider oneiric suite for the touched area**

Run: `cd ~/Projects/oneiric && .venv/bin/pytest tests/adapters/observability/ tests/adapters/test_observability_embeddings.py tests/adapters/test_duckdb_hot_store_spans.py --no-cov -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd ~/Projects/oneiric
git add oneiric/adapters/observability/embeddings.py oneiric/adapters/observability/embedding_settings.py oneiric/adapters/observability/queries.py oneiric/adapters/observability/models.py oneiric/adapters/observability/settings.py oneiric/adapters/observability/migrations.py oneiric/tests/adapters/test_observability_embeddings.py oneiric/tests/adapters/observability/test_embeddings.py <the mock-assertion test files you changed>
git commit --only <the same paths> -F /tmp/oneiric-openai-leg.txt
```

Commit message subject: `feat(embeddings): add the OpenAI leg at 768 to the oneiric probe chain`

---

### Task B2: Oneiric — fleet width constant and the DuckDB hot-store default

**Files:**
- Modify: `oneiric/oneiric/adapters/vector/duckdb_hot_store.py` — `DEFAULT_EMBEDDING_DIM`
- Test: `oneiric/tests/adapters/vector/test_duckdb_hot_store_dim.py` (create)

**Interfaces:**
- Consumes: `FLEET_EMBEDDING_DIM` from Task B1.
- Produces: `oneiric.adapters.vector.duckdb_hot_store.DEFAULT_EMBEDDING_DIM: int = 768`. `DuckdbHotStore.__init__`'s `embedding_dim` parameter keeps its `None` default, which now resolves to 768 instead of 384.

- [ ] **Step 1: Write the failing test**

Create `oneiric/tests/adapters/vector/test_duckdb_hot_store_dim.py`:

```python
def test_default_embedding_dim_is_fleet_width() -> None:
    """The hot store's default schema width equals the fleet width."""
    assert DEFAULT_EMBEDDING_DIM == FLEET_EMBEDDING_DIM
    assert DEFAULT_EMBEDDING_DIM == 768


async def test_created_table_uses_768(tmp_path: Path) -> None:
    """A hot store created without an explicit dimension bakes FLOAT[768]."""
    store = DuckdbHotStore(database_path=tmp_path / "hot.duckdb")
    await store.initialize()
    # Read the conversations.embedding column type from information_schema.
    assert "FLOAT[768]" in <the type string>
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/oneiric && .venv/bin/pytest tests/adapters/vector/test_duckdb_hot_store_dim.py --no-cov -v`
Expected: FAIL — `assert 384 == 768`.

- [ ] **Step 3: Change the constant**

In `duckdb_hot_store.py`, change `DEFAULT_EMBEDDING_DIM = 384` to `DEFAULT_EMBEDDING_DIM = FLEET_EMBEDDING_DIM`, importing `FLEET_EMBEDDING_DIM` from `oneiric.adapters.observability.embeddings`. Update the constructor docstring that reads *"(384)"* to reference the fleet width instead of a literal.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/Projects/oneiric && .venv/bin/pytest tests/adapters/vector/test_duckdb_hot_store_dim.py tests/adapters/test_duckdb_hot_store_spans.py --no-cov -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/oneiric
git add oneiric/adapters/vector/duckdb_hot_store.py oneiric/tests/adapters/vector/test_duckdb_hot_store_dim.py
git commit --only oneiric/adapters/vector/duckdb_hot_store.py oneiric/tests/adapters/vector/test_duckdb_hot_store_dim.py -F /tmp/oneiric-hot-store-dim.txt
```

Commit message subject: `fix(vector): widen the DuckDB hot store default dimension to the fleet width`

---

### Task B3: Akosha — resolve the width instead of hardcoding 384

**Files:**
- Modify: `akosha/akosha/processing/embedding_dim.py` — add `FLEET_EMBEDDING_DIM`, add the `openai` entry, widen `DEFAULT_DIMENSION` and the `mock` entry
- Modify: `akosha/akosha/mcp/tools/session_buddy_tools.py` — replace **every** 384 literal
- Modify: `akosha/akosha/ingestion/worker.py` — the hard-coded 384-wide zero vector
- Modify: `akosha/akosha/ingestion/bodai_event_subscriber.py` — the hard-coded 384-wide zero vector
- Modify: `akosha/tests/test_embedding_dim_match.py` — re-pin the 384 fallback to 768
- Modify: `akosha/tests/test_hot_store_coverage.py` — derive the fixture width from the resolved dim
- Test: `akosha/tests/test_embedding_dim_match.py` — add `TestFleetWidth`

**Interfaces:**
- Consumes: nothing (Akosha cannot import Oneiric's constant without taking a new dependency edge — it reads the value from its own table, which Task B6 checks for drift).
- Produces:
  - `akosha.processing.embedding_dim.FLEET_EMBEDDING_DIM: int = 768`
  - `BACKEND_DEFAULT_DIMS["openai"] == 768` (new entry) and `BACKEND_DEFAULT_DIMS["mock"] == 768` (widened)
  - `DEFAULT_DIMENSION == 768` (was 384)
  - No literal `384` remains in `akosha/mcp/tools/session_buddy_tools.py`.

- [ ] **Step 1: Write the failing tests**

In `akosha/tests/test_embedding_dim_match.py`, add:

```python
class TestFleetWidth:
    def test_fleet_embedding_dim_is_768(self) -> None:
        """Akosha's declared fleet width matches the fleet."""

    def test_openai_backend_default_is_768(self) -> None:
        """A live oneiric 'openai' backend resolves to 768."""

    def test_mock_backend_default_is_768(self) -> None:
        """The mock leg is fleet-width-safe."""

    def test_default_dimension_is_768(self) -> None:
        """The no-service fallback is the fleet width, not the legacy 384."""
```

And **rename** the existing `test_main_start_no_service_falls_back_to_384` to
`test_main_start_no_service_falls_back_to_768`, updating its assertions from
`384` to `768` — the fallback must become the fleet width, or an uninitialized
service silently creates a 384-wide hot store.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/akosha && .venv/bin/pytest tests/test_embedding_dim_match.py --no-cov -v`
Expected: FAIL — `assert 384 == 768` in the new tests and in the re-pinned fallback test.

- [ ] **Step 3: Update the dimension table**

In `akosha/processing/embedding_dim.py`:

- Add `FLEET_EMBEDDING_DIM: int = 768`.
- Add `"openai": FLEET_EMBEDDING_DIM` to `BACKEND_DEFAULT_DIMS`, and change its `"mock": 384` entry to `FLEET_EMBEDDING_DIM`.
- Change `DEFAULT_DIMENSION: int = 384` to `DEFAULT_DIMENSION: int = FLEET_EMBEDDING_DIM`.
- Update the module docstring's numbered resolution order to say the final fallback is now 768, and note that `BACKEND_DEFAULT_DIMS` now carries `openai` and `mock` keys matching Oneiric's `backend_name()` values.

- [ ] **Step 4: Remove every hardcoded 384 from the MCP tool**

In `akosha/mcp/tools/session_buddy_tools.py`, **ten** more `384` literals remain besides the validation one: `:64`, `:84`, `:105`, `:112`, `:149` (inside an error message), `:169`, `:170`, `:216`, `:222`. Replace every one with the resolved width — interpolate it into the error message so it names the actual requirement, and update the docstring examples.

- [ ] **Step 5: Validate against the store's baked width, not the live embedder**

The width check must compare against the width the hot store actually baked into its DDL — `hot_store._embedding_dim` — not the live embedder's dimension. A vector the embedder accepts but the store rejects is exactly the failure this check exists to prevent. Raise a clear error naming **both** the required width and the received width.

Add a test that builds the store at 768 and asserts a 384-wide vector is rejected with both widths in the message.

- [ ] **Step 6: Fix the ingestion worker's zero vector**

`akosha/ingestion/worker.py` and `akosha/ingestion/bodai_event_subscriber.py` still inject a 384-wide zero embedding into what is now a 768-wide store, breaking the Session-Buddy → Akosha push path. Replace the hard-coded width with the store's own `_embedding_dim`.

Add a test that uploads a conversation **without** an embedding and asserts the row is stored at the store's width.

- [ ] **Step 7: Fix the hot-store coverage fixture**

`akosha/tests/test_hot_store_coverage.py` inserts 384-wide vectors into a store whose schema width becomes 768 — the whole file fails. Make it width-agnostic: derive the width from `resolve_embedding_dim(get_embedding_service())`, or construct the store with an explicit `embedding_dim=384` so the fixture keeps its intent. Fix the stale comment on line 13.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd ~/Projects/akosha && .venv/bin/pytest tests/test_embedding_dim_match.py tests/test_hot_store_coverage.py --no-cov -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd ~/Projects/akosha
git add akosha/processing/embedding_dim.py akosha/mcp/tools/session_buddy_tools.py akosha/ingestion/worker.py akosha/ingestion/bodai_event_subscriber.py akosha/tests/test_embedding_dim_match.py akosha/tests/test_hot_store_coverage.py
git commit --only <the same paths> -F /tmp/akosha-fleet-width.txt
```

Commit message subject: `fix(embeddings): resolve the fleet width instead of hardcoding 384`

---

### Task B4: Mahavishnu — 384 → 768, with the Postgres and DuckDB rebuilds

**Files:**
- Modify: `mahavishnu/mahavishnu/core/resilient_embeddings.py` — `STANDARD_EMBEDDING_DIMENSION`
- Modify: `mahavishnu/mahavishnu/core/embeddings_oneiric.py` — the `384` in the `get_embeddings_with_oneiric` docstring example
- Modify: `mahavishnu/mahavishnu/core/repositories/embeddings.py` — `embedding_dim` field default
- Modify: `mahavishnu/mahavishnu/ingesters/otel_ingester.py` — `_embedding_dimension` **and the four embedder wrappers that overwrite it**
- Modify: `mahavishnu/mahavishnu/adapters/pgvector_adapter.py` — the `dimension=384` docstring example
- Modify: `mahavishnu/tests/unit/test_mahavishnu_config.py` — the `embedding_dimension == 384` assertion (line ~230)
- Create: `mahavishnu/migrations/versions/V202611060001__widen_document_embeddings_to_768.sql`
- Create: `mahavishnu/scripts/backfill_document_embeddings_768.py`
- Test: `mahavishnu/tests/unit/test_resilient_embeddings.py` — add `TestFleetWidth`
- Test: `mahavishnu/tests/unit/test_backfill_document_embeddings_768.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks. **Mahavishnu's DuckDB hot-store width is pinned explicitly to 768 here**, not inherited from the installed oneiric default — see *Prerequisites*.
- Produces:
  - `mahavishnu.core.resilient_embeddings.STANDARD_EMBEDDING_DIMENSION: int = 768`
  - `mahavishnu/scripts/backfill_document_embeddings_768.py` exposing `async def backfill(batch_size: int = 100) -> dict[str, int]` returning `{"scanned": int, "embedded": int, "failed": int}`, and a `main()` that runs it against the configured database.

- [ ] **Step 1: Write the failing tests**

In `mahavishnu/tests/unit/test_resilient_embeddings.py`, add:

```python
class TestFleetWidth:
    def test_standard_embedding_dimension_is_768(self) -> None:
        """Mahavishnu's declared fleet width matches the fleet."""

    def test_validate_dimension_rejects_a_384_vector(self) -> None:
        """A 384-wide vector is rejected, not coerced."""
        client = ResilientEmbeddingClient(standard_dimension=768)
        assert client._validate_dimension([0.0] * 384, "test") is False
        assert client._validate_dimension([0.0] * 768, "test") is True
```

Create `mahavishnu/tests/unit/test_backfill_document_embeddings_768.py`:

```python
async def test_backfill_reembeds_null_embeddings_and_sets_dim_768(...) -> None:
    """Rows with a NULL embedding are re-embedded; embedding_dim becomes 768 and
    model_name is set to the new embedder's model id."""

async def test_backfill_leaves_populated_rows_alone(...) -> None:
    """A row that already has a 768-wide vector is not re-embedded."""
```

Both use a stubbed connection that records the executed statements and parameters; assert `embedding_dim` is `768` and `model_name` is `"text-embedding-3-small"` on every insert.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/mahavishnu && .venv/bin/pytest tests/unit/test_resilient_embeddings.py -k FleetWidth --no-cov -v`
Expected: FAIL — `assert 384 == 768`.

- [ ] **Step 3: Widen the Mahavishnu constants and the embedder wrappers**

- `mahavishnu/core/resilient_embeddings.py`: `STANDARD_EMBEDDING_DIMENSION = 384` → `768`. Update the comment above it (it currently reads *"# Ecosystem standard embedding dimension"*) to record that 768 is the Oneiric-served fleet width.
- `mahavishnu/core/embeddings_oneiric.py`: the `384` in the `get_embeddings_with_oneiric` docstring example → `768`.
- `mahavishnu/core/repositories/embeddings.py`: `embedding_dim: int = Field(default=384, ge=128, le=1024, ...)` → `default=768`.
- `mahavishnu/adapters/pgvector_adapter.py`: the `dimension=384` docstring example → `dimension=768`.
- `mahavishnu/tests/unit/test_mahavishnu_config.py`: the `assert config.embedding_dimension == 384` assertion → `768` (the default is inherited from oneiric's observability settings, changed in B1 Step 5).

**`mahavishnu/ingesters/otel_ingester.py` needs more than the constant.** Changing `self._embedding_dimension = 384` to 768 has **no effect**: `initialize()` overwrites it with the embedder's own dimension, and every embedder wrapper in the same file still reports 384. Widen all four wrapper dimension defaults to 768 (or construct them explicitly, e.g. `AkoshaEmbedder(akosha_url=..., dimension=768)` / `TextOnlyEmbedder(dimension=768)`), and add them to this task's Files block.

Add a test asserting `ingester.embedding_dimension == 768` **after** `initialize()` — that is the assertion that catches the overwrite.

- [ ] **Step 4: Pin the DuckDB hot store explicitly**

`mahavishnu/ingesters/otel_ingester.py:609` constructs `DuckdbHotStore(database_path=self._duckdb_path)` with **no dimension**, so it inherits the installed oneiric default — which stays 384 until oneiric is published and the venvs reinstalled. Pass `embedding_dim=768` explicitly so this task does not depend on the publish order.

- [ ] **Step 5: Write the Postgres migration**

Create `mahavishnu/migrations/versions/V202611060001__widen_document_embeddings_to_768.sql`. It must, in order:

1. `DROP INDEX IF EXISTS search.idx_document_embeddings_hnsw;` — the HNSW index is bound to the old column type.
2. `ALTER TABLE search.document_embeddings ALTER COLUMN embedding DROP NOT NULL;`
3. `ALTER TABLE search.document_embeddings ALTER COLUMN embedding TYPE vector(768) USING NULL;` — `USING NULL` sets every existing vector to NULL. **Do not** use a `::vector(768)` cast: pgvector zero-pads or truncates on a dimension cast, which would leave 384-wide vectors masquerading as 768 and produce silently wrong similarity scores.
4. `CREATE INDEX idx_document_embeddings_hnsw ON search.document_embeddings USING hnsw (embedding vector_cosine_ops);`
5. A comment recording that the column is nullable *because* it holds "not yet embedded" rows, matching Session-Buddy's `embedding_status` pattern, and that the backfill repopulates it.

Leave `embedding_dim` alone in the migration — it is a separate `INT NOT NULL` column holding the *old* width for existing rows. The backfill rewrites it.

- [ ] **Step 6: Write the backfill script**

Create `mahavishnu/scripts/backfill_document_embeddings_768.py`:

- **Resolve the database through the same source the application uses.** `hybrid_search.py` never reads a Postgres DSN from settings — it receives an already-built `asyncpg.Pool` or `Database`. Resolve the URL via `mahavishnu.core.migrations.get_database_url()` (or the `Database` singleton `HybridSearchEngine` accepts), so the script and the application cannot target different databases.
- Select rows from `search.document_embeddings` joined to `search.documents` where `embedding IS NULL`.
- For each row, embed the document's content with the configured embedding service, then upsert.
- **The exact DML.** Write these columns: `document_id` (unchanged), `model_name` = the new embedder's model id (`text-embedding-3-small`; the column is `NOT NULL` with no default), `embedding_dim` = `768`, `embedding` = the new vector, `created_at` = `now()`. **Do not** reference a `metadata` column — the versioned schema does not define one, even though the repository's own upsert mentions it.
- Process in batches of 100, committing per batch.
- Return `{"scanned": int, "embedded": int, "failed": int}`. `main()` prints those counts and exits non-zero if `failed > 0`.
- **Must be idempotent** — a second run scans zero NULL rows and changes nothing.
- **Index lifecycle:** the HNSW index was created in Step 5 against all-NULL rows. State the chosen lifecycle explicitly — either `REINDEX INDEX search.idx_document_embeddings_hnsw;` after the backfill completes, or a DELETE-and-INSERT strategy in the backfill instead of UPDATE. Verify the chosen approach against the installed pgvector version before committing to it.
- Use timezone-aware datetimes (`DTZ001` is selected in mahavishnu).
- Keep every function at 10 parameters or fewer (`max-args = 10` is enforced there).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd ~/Projects/mahavishnu && .venv/bin/pytest tests/unit/test_resilient_embeddings.py tests/unit/test_backfill_document_embeddings_768.py tests/unit/test_core_embeddings_oneiric.py tests/unit/test_mahavishnu_config.py --no-cov -v`
Expected: PASS.

- [ ] **Step 8: Document the destructive rebuild and the publish order**

Add `mahavishnu/docs/runbooks/rebuild-vector-stores-768.md` recording, for operators:

- The Postgres migration to apply, then the backfill command.
- The DuckDB OTel hot-store rebuild: the file is `<platformdirs.user_data_path('mahavishnu')>/mahavishnu_otel.duckdb` **when `hot_store_path` resolves to a file**. Under the default configuration the hot store is **in-memory** (`:memory:`), so there is normally **no file to delete** — state that explicitly rather than sending an operator looking for one.
- The order: **widen schema and embedder first, then re-embed.** A row written during the mixed-width window cannot bind either way.
- The **publish order**: this plan's B1/B2 change oneiric, which is installed non-editably. The operator publishes oneiric and reinstalls the dependent venvs afterwards. Until then, Mahavishnu's hot store is pinned explicitly to 768 (Step 4) and does not depend on the published default.

- [ ] **Step 9: Commit**

```bash
cd ~/Projects/mahavishnu
git add mahavishnu/core/resilient_embeddings.py mahavishnu/core/embeddings_oneiric.py mahavishnu/core/repositories/embeddings.py mahavishnu/ingesters/otel_ingester.py mahavishnu/adapters/pgvector_adapter.py mahavishnu/tests/unit/test_mahavishnu_config.py mahavishnu/migrations/versions/V202611060001__widen_document_embeddings_to_768.sql mahavishnu/scripts/backfill_document_embeddings_768.py mahavishnu/tests/unit/test_resilient_embeddings.py mahavishnu/tests/unit/test_backfill_document_embeddings_768.py mahavishnu/docs/runbooks/rebuild-vector-stores-768.md
git commit --only <the same paths> -F /tmp/mahavishnu-fleet-width.txt
```

Commit message subject: `feat(embeddings): migrate Mahavishnu to the 768 fleet width`

---

### Task B5: Crackerjack — real embeddings at 768, and the `file_types` filter fix

**Files:**
- Create: `crackerjack/crackerjack/services/ai/dimensions.py` — the leaf constant module
- Create: `crackerjack/crackerjack/services/ai/local_embedder.py`
- Modify: `crackerjack/crackerjack/services/ai/embeddings.py` — real backend chain, import the constant from the leaf module
- Modify: `crackerjack/crackerjack/models/semantic_models.py` — `embedding_dimension` default
- Modify: `crackerjack/crackerjack/services/vector_store.py` — `file_types` normalization, index width column
- Modify: `crackerjack/crackerjack/fixers/semantic.py` — the module docstring that documents the `file_types` bug as "preserved verbatim"
- Test: `crackerjack/tests/services/test_vector_store_file_types.py` (create)
- Test: `crackerjack/tests/fixers/test_semantic.py` — invert the two bug-pinning cases, add the semantic-quality regression

**Interfaces:**
- Consumes: nothing from earlier tasks (Crackerjack reaches the OpenAI-compatible endpoint directly over HTTP; it does not import Oneiric's service).
- Produces:
  - `crackerjack.services.ai.dimensions.EMBEDDING_DIMENSION: int = 768` — **a leaf module.** `crackerjack/models/semantic_models.py` and `crackerjack/services/ai/embeddings.py` both import it. It imports nothing from `crackerjack.*`.
  - `crackerjack.services.ai.embeddings.EmbeddingService.backend_name() -> str` — one of `"openai_gateway"`, `"openai_direct"`, `"local_llama"`, `"local_lexical"`, `"hash"`.
  - `crackerjack.services.ai.embeddings.EmbeddingService.is_model_available() -> bool` — `False` **only** for the legacy `"hash"` backend; `True` for every real backend. (Today it returns `False` unconditionally, because no ONNX session ever loads.)
  - `crackerjack.services.ai.local_embedder.LocalEmbedder` with `embed(text: str) -> list[float]` (768 floats, L2-normalized) and `embed_batch(texts: list[str]) -> list[list[float]]`.
  - `crackerjack.services.vector_store.VectorStore` accepts `file_types` entries with or without a leading dot and matches either form.
  - `crackerjack.services.vector_store.VectorStore` records the index's embedding width and rebuilds on mismatch.

**Why the constant lives in a leaf module.** `crackerjack/services/ai/embeddings.py:27` already imports `SemanticConfig` from `crackerjack/models/semantic_models.py` at module scope, and `semantic_models.py` currently imports nothing from `crackerjack.*`. Making `semantic_models.py` import `EMBEDDING_DIMENSION` from `services/ai/embeddings.py` closes the cycle `semantic_models → embeddings → semantic_models`; `vector_store.py` imports `semantic_models` first, so `import crackerjack.models.semantic_models` then raises `ImportError: cannot import name 'SemanticConfig' from partially initialized module`. `services/ai/dimensions.py` breaks it: both modules import *it*, and it imports neither.

**The defect being fixed.** `_generate_fallback_embedding` SHA-256s the whole text, takes 48 bytes, divides each by 255, and repeats each 8 times → 384 floats. Every value is in `[0, 1]`, so the vector carries a large shared DC offset and every pair's cosine floor sits near 0.58. Measured: 500 random unrelated text pairs score cosine 0.577–0.901 (mean 0.752), and **81.4% clear Crackerjack's default `min_similarity=0.7`**. A genuine paraphrase scores *below* an unrelated string. `crackerjack/fixers/semantic.py:31-37` already documents this.

**The two backends, and why there are two.**

- **Search path** (`VectorStore` indexing and `VectorStore.search`) → OpenAI-compatible, 768.
- **Fixer path** (`crackerjack/fixers/semantic.py`) → must stay deterministic, offline, and download-free. `crackerjack/fixers/semantic.py` documents that its tests exercise a real `VectorStore` against a `tmp_path` SQLite with "no network access and no slow model download", and Crackerjack's `pyproject.toml` keeps the neural dependency group intentionally empty (no `sentence-transformers`, `torch`, `fastembed`, or `onnxruntime`).

So the fixer path uses a **local deterministic lexical embedder** (`local_lexical`), not a neural model: a hashed character-trigram + word-unigram TF-IDF projection to 768 dimensions, pure numpy, no downloads, no egress. It is genuinely similarity-bearing — shared vocabulary raises cosine, disjoint vocabulary drives it toward 0 — which is exactly the property the hash pseudo-vectors violated. It is **not** a neural semantic embedding and its docstring must say so plainly: it fixes the "everything scores 0.75" defect and restores meaningful relative ranking, but paraphrase matching requires the OpenAI path.

The **OpenAI path** is where true semantics live, and it is what the search path uses.

**The routing mechanism.** The fixer and the search path must not share one lazily-resolved chain — they need different backend policies. Make the backend a **per-service policy**:

- `SemanticConfig.embedding_backend` gains real meanings: `"auto"` (the chain), `"openai"` (OpenAI legs only), `"local"` (local legs only).
- `VectorStore.__init__` builds its `EmbeddingService` with that policy, so a caller can pin one.
- `crackerjack/fixers/semantic.py` constructs a service pinned to the local legs.
- The two services each expose their own `backend_name()`.

- [ ] **Step 1: Write the failing tests**

Create `crackerjack/tests/services/test_vector_store_file_types.py`:

```python
def test_file_types_matches_with_and_without_leading_dot(tmp_path: Path) -> None:
    """file_types=["py"] and file_types=[".py"] return the same rows."""

def test_file_types_normalizes_mixed_forms(tmp_path: Path) -> None:
    """A single query listing both "py" and ".py" does not double-count rows."""

def test_index_rebuilds_when_the_stored_width_differs(tmp_path: Path) -> None:
    """A 384-wide index is detected and rebuilt rather than mis-scored."""
```

In `crackerjack/tests/fixers/test_semantic.py`, add:

```python
class TestRealEmbeddings:
    def test_unrelated_strings_score_below_default_threshold(self) -> None:
        """Two semantically unrelated strings score below 0.7."""

    def test_similar_strings_score_above_unrelated(self) -> None:
        """A near-paraphrase scores higher than an unrelated string."""

    def test_backend_is_not_the_legacy_hash(self) -> None:
        """The resolved backend is a real one and is_model_available() is True."""

    def test_embeddings_are_768_wide(self) -> None:
        """Every vector is EMBEDDING_DIMENSION wide."""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/crackerjack && .venv/bin/pytest tests/fixers/test_semantic.py -k RealEmbeddings --no-cov -v && .venv/bin/pytest tests/services/test_vector_store_file_types.py --no-cov -v`
Expected: FAIL — the similarity assertion fails (unrelated strings score ~0.75) and the `file_types` query returns zero rows.

- [ ] **Step 3: Create the leaf constant module**

Create `crackerjack/services/ai/dimensions.py`:

```python
EMBEDDING_DIMENSION: int = 768
```

It imports nothing from `crackerjack.*`. Add a docstring explaining that it exists as a leaf so that both `models/semantic_models.py` and `services/ai/embeddings.py` can depend on it without an import cycle.

- [ ] **Step 4: Implement the local lexical embedder**

Create `crackerjack/services/ai/local_embedder.py`:

```python
class LocalEmbedder:
    """Deterministic lexical embedder — 768 dims, pure numpy, no downloads.

    Hashes character trigrams and word unigrams into a fixed 768-dimensional
    space with sublinear term weighting, then L2-normalizes. Two texts
    sharing vocabulary score higher than two unrelated texts.

    This is a *lexical* embedder, not a neural semantic model: it has no
    notion of paraphrase. The OpenAI path provides that. This backend
    exists so the fixer's offline, deterministic, download-free contract
    holds while producing vectors whose similarity is meaningful rather
    than an artifact of a shared DC offset.
    """

    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

Implementation requirements: use `hashlib.blake2b` (not Python's salted `hash()`) so the output is stable across processes; weight each term as `1 + log(count)`; L2-normalize; return exactly 768 floats. An empty or whitespace-only input returns a zero vector of length 768 (not an exception) — `EmbeddingService.generate_embedding` already rejects empty text before reaching here, but the embedder itself must not raise.

- [ ] **Step 5: Replace the backend chain in `EmbeddingService`**

In `crackerjack/services/ai/embeddings.py`:

- Import `EMBEDDING_DIMENSION` from `crackerjack.services.ai.dimensions`.
- Add a backend chain resolved at first use: `openai_gateway` → `openai_direct` → `local_llama` → `local_lexical` → `hash`.
  - `openai_gateway`: base URL from `get_router().resolve(LLMProvider.OPENAI)` — **Crackerjack already uses this resolver** in `crackerjack/adapters/ai/unified.py:68`. The resolved value is an OpenAI-compatible base that already includes the API prefix; the endpoint is `{base}/embeddings`. Credential: `BIFROST_VIRTUAL_KEY`.
  - `openai_direct`: `https://api.openai.com/v1` + `/embeddings`. Credential: `OPENAI_API_KEY`.
  - `local_llama`: `http://localhost:8080` (bare root, matching oneiric's `llama_cpp_base_url`) + `/v1/embeddings`. No auth, `model=nomic-embed-text`.
  - **Per-leg request body.** `{"model", "input", "dimensions": 768}` for `openai_gateway` and `openai_direct`. `{"model", "input"}` — **no `dimensions` key** — for `local_llama`, because that is the same llama.cpp server B1 describes as rejecting unknown body fields. Sending `dimensions` to it is a contradiction the plan previously carried.
  - Use **synchronous** `httpx2.Client`, imported as `import httpx2 as httpx` — the repo convention. A literal `import httpx` fails at module import. `EmbeddingService.generate_embedding` is a sync method and must stay sync.
  - A leg is skipped when its credential is absent or its request fails; the chain continues.
  - `hash` is the legacy pseudo-vector, retained only as a last resort, widened to 768.
- `generate_embedding` dispatches to the resolved backend; `generate_embeddings_batch` likewise.
- `backend_name()` returns the resolved backend's name.
- `is_model_available()` returns `self._backend != "hash"`.
- `get_model_info()` reports `embedding_dimension: EMBEDDING_DIMENSION` and the resolved backend name.
- The `_generate_fallback_embedding` helper becomes the `"hash"` backend's implementation, widened to 768 — keep the name so the diff stays reviewable, and add a docstring saying it is not semantic.

**Honour the per-service policy** (Step 0 of the design): `SemanticConfig.embedding_backend` selects which legs are eligible, and `fixers/semantic.py` pins a local-only service.

- [ ] **Step 6: Widen `SemanticConfig` and every explicit call site**

- In `crackerjack/models/semantic_models.py`, change `embedding_dimension: int = Field(default=384, ...)` to `default=EMBEDDING_DIMENSION` (import from `crackerjack.services.ai.dimensions`). The `ge=128, le=1024` bounds stay.
- **The default alone is not enough.** Every real construction site passes `embedding_dimension=384` explicitly — **six** of them. Replace all six with `EMBEDDING_DIMENSION`, and update the three affected default-constructed test assertions from 384 to 768.

- [ ] **Step 7: Fix the `file_types` filter**

In `crackerjack/services/vector_store.py`, in `_get_all_embeddings` (the `WHERE file_type IN (?)` filter), normalize each requested type before binding: if it does not start with `"."`, prepend one. The stored value is `Path.suffix`, always dotted.

Do **not** change the call site at `crackerjack/fixers/semantic.py:346` (`file_types=["py"]`) — the store now resolves it.

- [ ] **Step 8: Record the index width and rebuild on mismatch**

The `embeddings` table has no width column, so a stale 384-wide BLOB is read as if it were 768. Add an `embedding_dim INTEGER` column (or a `meta` table) recording the index's width. On open, compare it with `EMBEDDING_DIMENSION`; on mismatch, **rebuild the index** rather than scoring against it. The current failure mode is a loud numpy shape `ValueError`, not a silent mis-score — the rebuild makes it a clean, deliberate action instead.

- [ ] **Step 9: Invert the two bug-pinning test classes**

Two existing classes deliberately pin the behaviour this task fixes. They must be **inverted, not regressed**:

- `TestDiscoverSemanticPatternsFileTypeBug` — assert the row **IS** returned for `file_types=["py"]` and that `related_patterns` is **non-empty**. Rewrite the class docstring.
- `TestFallbackEmbeddingIsNotSemantic::test_unrelated_snippets_score_high_similarity` — delete or invert it. **Keep** `test_identical_text_scores_perfect_similarity`, which still holds. Rewrite the class docstring to describe the new lexical backend.

- [ ] **Step 10: Re-pin the four other affected test files**

Steps 4, 5, and 6 break four more pre-existing test files that assert a 384-wide embedding dimension. List them explicitly and re-pin the assertions to 768:

- `crackerjack/tests/models/test_semantic_models.py`
- `crackerjack/tests/test_mcp_semantic_tools.py`
- `crackerjack/tests/mcp_test_helpers/tools/test_semantic_tools.py`
- `crackerjack/tests/unit/services/ai/test_ai_embeddings.py`

(plus `crackerjack/tests/fixers/test_semantic.py` from Step 9).

- [ ] **Step 11: Update the `fixers/semantic.py` docstring**

That module's docstring currently states the `file_types` bug is *"preserved verbatim (not fixed), pinned by a test"*. After this task the bug **is** fixed. Rewrite that passage to describe the bug as fixed and to point at the new test. Leaving the "preserved verbatim" wording in place would make the file lie about its own behaviour. Also update the passage describing the hash pseudo-embedding as the current state.

- [ ] **Step 12: Run the tests to verify they pass**

Run: `cd ~/Projects/crackerjack && .venv/bin/pytest tests/fixers/test_semantic.py tests/services/ tests/models/test_semantic_models.py tests/test_mcp_semantic_tools.py tests/mcp_test_helpers/tools/test_semantic_tools.py tests/unit/services/ai/test_ai_embeddings.py --no-cov -v`
Expected: PASS — the two inverted classes now assert the *fixed* behaviour, and the four re-pinned files assert 768.

- [ ] **Step 13: Commit**

```bash
cd ~/Projects/crackerjack
git add crackerjack/services/ai/dimensions.py crackerjack/services/ai/local_embedder.py crackerjack/services/ai/embeddings.py crackerjack/models/semantic_models.py crackerjack/services/vector_store.py crackerjack/fixers/semantic.py crackerjack/tests/services/test_vector_store_file_types.py crackerjack/tests/fixers/test_semantic.py crackerjack/tests/models/test_semantic_models.py crackerjack/tests/test_mcp_semantic_tools.py crackerjack/tests/mcp_test_helpers/tools/test_semantic_tools.py crackerjack/tests/unit/services/ai/test_ai_embeddings.py
git commit --only <the same paths> -F /tmp/crackerjack-real-embeddings.txt
```

Commit message subject: `feat(embeddings): replace hash pseudo-vectors with real 768-wide embeddings`

---

### Task B6: Fleet embedding width agreement

**Files:**
- Create: `mahavishnu/scripts/check_fleet_embedding_width.py`
- Modify: `session-buddy/tests/unit/test_reflection_adapter_live_embedding_width.py` — add the Session-Buddy assertion
- Test: `mahavishnu/tests/unit/test_check_fleet_embedding_width.py` (create)

**Interfaces:**
- Consumes: `FLEET_EMBEDDING_DIM` (Oneiric), `DEFAULT_EMBEDDING_DIM` (Session-Buddy), `FLEET_EMBEDDING_DIM` (Akosha), `STANDARD_EMBEDDING_DIMENSION` (Mahavishnu), `EMBEDDING_DIMENSION` (Crackerjack).
- Produces: `mahavishnu/scripts/check_fleet_embedding_width.py` exposing `def check_fleet_embedding_width(repo_root: Path) -> list[str]` returning a list of human-readable mismatch strings (empty = consistent) and `def main() -> int` returning `0` when consistent, `1` otherwise.

**Why AST parsing rather than imports.** Session-Buddy cannot import Akosha, Mahavishnu, or Crackerjack; Mahavishnu can import Oneiric and Crackerjack but not Akosha. A cross-repo *import* test is impossible. The check **parses the five source files with `ast`** and reads the module-level integer assignment by name — robust to line drift, unlike a line-pinned test or a regex.

**Why `ast.AnnAssign` matters.** Three of the five constants are **annotated** assignments (`NAME: int = 768`), which `ast` parses as `ast.AnnAssign`, not `ast.Assign`. Walking only `ast.Assign` reports three false mismatches and fails the check's own test.

**Portability.** The check must not hard-depend on `~/Projects`. Resolve the fleet root with `resolve_projects_root()` from `mahavishnu/scripts/bodai_paths.py`, and `pytest.skip` the real-fleet test when any checkout is absent. The **script** path stays strict — a missing checkout is a mismatch, never a silent pass. The `tmp_path`-based mismatch test is the hard gate.

- [ ] **Step 1: Write the failing test**

Create `mahavishnu/tests/unit/test_check_fleet_embedding_width.py`:

```python
def test_check_reports_a_mismatch(tmp_path: Path) -> None:
    """A repo whose declared width differs is reported by name and by width."""

def test_check_reads_annotated_assignments(tmp_path: Path) -> None:
    """A module declaring `Y: int = 2` is read, not reported missing."""

def test_check_passes_on_the_real_fleet() -> None:
    """The four repos plus oneiric currently agree at 768."""
    if not all_repos_present():
        pytest.skip("fleet checkouts not available")
    assert check_fleet_embedding_width(resolve_projects_root()) == []
```

The second test feeds the checker a synthetic module containing **both** `X = 1` and `Y: int = 2`, so the `AnnAssign` branch is pinned.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/mahavishnu && .venv/bin/pytest tests/unit/test_check_fleet_embedding_width.py --no-cov -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'check_fleet_embedding_width'`.

- [ ] **Step 3: Implement the check**

Create `mahavishnu/scripts/check_fleet_embedding_width.py`:

- A table of five `(repo, relative_path, attribute_name)` entries:
  - `("oneiric", "oneiric/adapters/observability/embeddings.py", "FLEET_EMBEDDING_DIM")`
  - `("session-buddy", "session_buddy/memory/embedding_dim.py", "DEFAULT_EMBEDDING_DIM")`
  - `("akosha", "akosha/processing/embedding_dim.py", "FLEET_EMBEDDING_DIM")`
  - `("mahavishnu", "mahavishnu/core/resilient_embeddings.py", "STANDARD_EMBEDDING_DIMENSION")`
  - `("crackerjack", "crackerjack/services/ai/dimensions.py", "EMBEDDING_DIMENSION")`
- For each, read the file, parse with `ast.parse`, and read the module-level integer assignment **by handling both node kinds**:
  - `ast.Assign` — check every target is an `ast.Name` matching the attribute name, and the value is an `ast.Constant` int.
  - `ast.AnnAssign` — the target is an `ast.Name` matching the attribute name, and the value is an `ast.Constant` int.
- Compare all five to the first (Oneiric's) value. Return one string per mismatch: `"<repo>: declares <n>, fleet is <m>"`.
- A missing repo directory or an unparsable file yields a mismatch string naming the problem — **not** a silent pass.
- `main()` prints each mismatch to stderr and returns `1`; returns `0` and prints `fleet embedding width: 768` when consistent.
- Resolve the fleet root with `resolve_projects_root()` from `scripts/bodai_paths.py`, accepting an explicit path override for the test.

- [ ] **Step 4: Add the Session-Buddy assertion**

In `session-buddy/tests/unit/test_reflection_adapter_live_embedding_width.py`, add a test asserting `session_buddy.memory.embedding_dim.DEFAULT_EMBEDDING_DIM == 768`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd ~/Projects/mahavishnu && .venv/bin/pytest tests/unit/test_check_fleet_embedding_width.py --no-cov -v`
Expected: PASS (the real-fleet test may skip if the checkouts are not all present).
Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_reflection_adapter_live_embedding_width.py --no-cov -v`
Expected: PASS.

- [ ] **Step 6: Run the check as a script**

Run: `cd ~/Projects/mahavishnu && .venv/bin/python scripts/check_fleet_embedding_width.py`
Expected: prints `fleet embedding width: 768` and exits `0`.

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/mahavishnu
git add scripts/check_fleet_embedding_width.py tests/unit/test_check_fleet_embedding_width.py
git commit --only scripts/check_fleet_embedding_width.py tests/unit/test_check_fleet_embedding_width.py -F /tmp/mahavishnu-fleet-width-check.txt
```

```bash
cd ~/Projects/session-buddy
git add tests/unit/test_reflection_adapter_live_embedding_width.py
git commit --only tests/unit/test_reflection_adapter_live_embedding_width.py -F /tmp/sb-fleet-width-assertion.txt
```

Commit message subjects: `feat(checks): add the cross-repo fleet embedding width check` and `test(embeddings): pin the session-buddy fleet width at 768`.

---

## Plan Self-Review

**Spec coverage.** Goal #8 (one embedder fleet-wide) → Tasks B1–B6. The spec's three "NEW (fleet)" sections → B1 (Oneiric leg), B4 (Mahavishnu 384→768), B5 (Crackerjack real embeddings). The spec's Akosha hardcoded-384 replacement → B3. The spec's "widen-then-re-embed ordering" and "rebuild, not ALTER" → B4 Steps 5, 6, 8. The spec's "fleet embedding width agreement" test → B6. ✅

**Gaps closed beyond the spec.** (a) The spec's `BACKEND_DEFAULT_DIMS` key is `"openai"` while its probe legs are `openai_gateway`/`openai_direct` — resolved by having `backend_name()` collapse both to `"openai"` (B1) and adding `backend_leg()`. (b) The spec does not mention Oneiric's mock width — widened in B1 Step 3 and B3 Step 3. (c) The spec does not mention `model2vec` (256) and `minimax` (1024) being unreachable at 768 — resolved by the Global Constraint that those legs are not fleet-width-safe and stores reject rather than coerce. (d) The spec does not mention Crackerjack's Blob index having no width column — resolved by B5 Step 8. (e) The spec does not mention `search.document_embeddings.embedding_dim` going stale — resolved by B4 Step 6's exact DML. (f) **The spec does not mention that oneiric's own observability subsystem hard-codes 384** in four files, which would reject every 768-wide vector the new leg produces — resolved by B1 Step 5.

**Review findings folded in.** 29 confirmed findings from the multi-lens review are addressed above. The design-changing ones: B1 now **reuses** `OpenAIEmbeddingAdapter`/`OpenAIEmbeddingSettings` and resolves credentials through `EmbeddingSettings.from_env()` (fixing the "both probes always return False" defect at the root); the base-URL convention is stated once and applied consistently (fixing the `/v1/v1/embeddings` 404); B4 Step 3 widens the embedder wrappers that overwrite the constant (fixing an inert change); B5 puts the constant in a leaf module (fixing a reproduced `ImportError`); B5 makes the backend a per-service policy (fixing an unimplementable split); B6 handles `ast.AnnAssign` (fixing a check that reported permanent drift); every pytest command carries `--no-cov` (fixing commands that always exited 1); and B4 Step 4 pins the hot store explicitly (fixing a dependency on an unpublished release).

**Review Focus coverage.** Item 1 (no credential) → B1 Step 1's `from_env` tests plus B4's `test_validate_dimension_rejects_a_384_vector`. Item 2 (stale DuckDB) → B4 Step 8's runbook. Item 3 (stale `embedding_dim`) → B4 Step 1's backfill test. Item 4 (stale Crackerjack Blob) → B5 Step 8's width detection. Item 5 (poisoned WAL) → B2's `test_created_table_uses_768` plus B4's rejection test. ✅

**Type consistency.** `FLEET_EMBEDDING_DIM` is defined once (B1) and consumed in B2. `EMBEDDING_DIMENSION` is defined in B5's leaf module and consumed by B5 and B6. `STANDARD_EMBEDDING_DIMENSION` is pre-existing and modified in B4. `DEFAULT_EMBEDDING_DIM` is pre-existing and modified in B2. `backend_leg()` is introduced in B1 and referenced nowhere else — deliberately, since it is diagnostic surface. ✅

**Proportion.** Six tasks, each with one independently testable deliverable and a reviewable boundary: B1 (Oneiric embeddings) could be rejected while B2 (the hot-store constant) is approved. ✅
