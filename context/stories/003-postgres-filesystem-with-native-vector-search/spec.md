# 003 — PostgresFileSystem with native search and pgvector default

- **Status:** draft
- **Date:** 2026-04-20
- **Owner:** Clay Gendron
- **Kind:** feature + backend + migration

## Intent

Introduce a PostgreSQL-native backend, `PostgresFileSystem`, that follows the same architectural pattern as [`src/vfs/backends/mssql.py`](../../../src/vfs/backends/mssql.py): an explicit `DatabaseFileSystem` subclass that keeps the public VFS contract unchanged while pushing search work into the database.

Today:

- PostgreSQL mounts use the portable `DatabaseFileSystem` path, so `lexical_search`, `grep`, and `glob` still do most of their authoritative work in Python after broad SQL pre-filters.
- `vector_search` and `semantic_search` require an explicit external `vector_store`, even when the mount is already backed by PostgreSQL and the deployment wants one database to own file rows, full-text search, and vector similarity.
- The repo already treats PostgreSQL as a first-class storage backend (`--postgres` test mode, `grover[postgres]`, repo probe script), but it does not yet have a dialect-specific backend comparable to `MSSQLFileSystem`.

After this story:

- `PostgresFileSystem` exists as an opt-in backend under `src/vfs/backends/postgres.py`.
- `lexical_search`, `grep`, and `glob` are PostgreSQL-native: full-text ranking and regex/path matching run in Postgres, with Python only doing the result-shaping work that must remain local (for example, line-window reconstruction for grep).
- `vector_search` and `semantic_search` default to native pgvector search inside Postgres.
- If the caller explicitly passes `vector_store=` to `PostgresFileSystem`, that override wins for vector and semantic search. Native pgvector is the default, not an exclusive mode.
- The result envelope, path semantics, candidate filtering, user scoping, and error behavior remain compatible with the rest of VFS.

## Why

- **Parity with MSSQL:** PostgreSQL should have the same “native backend, same public contract” path that MSSQL now has.
- **Single-database operating model:** for the common SaaS / shared knowledge-base deployment, Postgres should be able to own rows, full-text search, and vector search without forcing a second search system by default.
- **Performance:** the portable `DatabaseFileSystem` search path leaves obvious performance on the table for Postgres deployments that already have FTS, regex, and pgvector available server-side.
- **Pluggability remains load-bearing:** external vector stores are still valuable for large or remote corpora. `PostgresFileSystem` must not make that route impossible.
- **Constitution fit:** this is an Article 4 backend swap, not a public-contract rewrite. The backend grows capabilities; the caller keeps the same filesystem API.

## Expected touch points

- Create `src/vfs/backends/postgres.py`
- Update `src/vfs/backends/__init__.py`
- Update `pyproject.toml` (`postgres` extra)
- Update shared helpers in `src/vfs/backends/database.py` only where Postgres support needs a common seam
- Update `src/vfs/vector.py`
- Update `src/vfs/models.py`
- Add `tests/test_postgres_backend.py`
- Update `tests/test_models.py`
- Extend `tests/conftest.py` Postgres provisioning helpers
- Update `scripts/postgres_repo_cli_probe.py` (and the shell wrapper only if its interface needs to change)
- Update PostgreSQL-facing docs/examples (`docs/index.md`, `docs/architecture.md`, and any backend listing that currently mentions only `DatabaseFileSystem` + `MSSQLFileSystem`)

## Scope

### In

1. Add `PostgresFileSystem(DatabaseFileSystem)` as an explicit backend class, exported from `vfs.backends`.

2. Follow the `MSSQLFileSystem` pattern intentionally:
   - explicit subclass, not a flag on `DatabaseFileSystem`
   - raw SQL helpers for schema-qualified table names when `text()` SQL is required
   - fail-fast verification of native search prerequisites
   - no “silently fall back to Python search” behavior inside the subclass when the native path is misconfigured

3. Keep backend selection explicit in public code.
   - A caller opts in by instantiating `PostgresFileSystem(...)`.
   - This story does **not** auto-upgrade every PostgreSQL URL or every `DatabaseFileSystem(engine=postgres_engine)` call to the new subclass.
   - Tests and example probes may opt into the subclass when exercising Postgres-native behavior.

4. Add a Postgres-native schema verification method on the backend.

   Recommended shape:

   ```python
   async def verify_native_search_schema(self) -> None: ...
   ```

   Verification must check:

   - the schema-qualified `vfs_objects` table resolves
   - the `content` column exists
   - a usable Postgres full-text index exists for lexical/grep prefiltering
   - when `self._vector_store is None`:
     - the `vector` extension (pgvector) is installed
     - the `vfs_objects.embedding` column exists
     - the `embedding` column is a native `vector(<N>)` column, not the portable JSON/text storage form
     - the vector dimension is declared and matches the database column
     - a usable ANN index exists for cosine search on `vfs_objects.embedding`

   Verification must raise clear, actionable `RuntimeError`s analogous to `MSSQLFileSystem.verify_fulltext_schema()`.

5. Define the native Postgres search schema contract.

   `PostgresFileSystem` should assume deployment-managed native search artifacts, not create them implicitly at request time.

   The native vector path uses the shared `VFSObject.embedding` column itself. There is no sidecar embeddings table in this story.

   `VectorType` and the `embedding` model field are the schema-level declaration of native vector storage on Postgres.

   Required model/type contract:

   - `VFSObject.embedding` is the canonical native-vector column for `PostgresFileSystem`
   - `VectorType` must compile to Postgres `vector(<N>)` when native pgvector mode is active
   - native pgvector mode requires a fixed dimension; a dimensionless `VectorType()` is invalid for native Postgres vector search unless the caller supplies an explicit external `vector_store`
   - the fixed dimension belongs to the model declaration, not only to mount/runtime config
   - `PostgresFileSystem` does not carry a separate runtime `embedding_dimension` source of truth; native vector shape comes from the resolved model declaration itself
   - the portable base model may remain dimensionless for non-native backends, but native Postgres mode must run against a model whose `embedding` field is declared with `VectorType(dimension=<N>, postgres_native=True, ...)`
   - `VectorType` must expose enough Postgres-specific metadata for provisioning code to know:
     - this column is the vector-index target
     - which ANN index method to create (`hnsw` preferred)
     - which operator class to use (`vector_cosine_ops`)
   - the backend and provisioning helpers should discover the index target from the model/type metadata rather than hard-coding a separate sidecar schema

   Required backend/model-construction contract:

   - callers may provide a predeclared Postgres-native model explicitly
   - callers that want native pgvector must select/build the right Postgres-native model up front; the backend constructor should not keep separate dimension state
   - `PostgresFileSystem` should not need a custom constructor beyond what `DatabaseFileSystem` already provides
   - `verify_native_search_schema()` compares the live database schema to the resolved model declaration and raises on mismatch
   - if an existing table was created under the old serialized `embedding` storage, the backend must not automatically alter that column during normal initialization or schema verification; it must raise and require an explicit migration step instead

   Recommended declaration shape:

   ```python
   embedding: Vector | None = Field(
       default=None,
       sa_type=VectorType(
           dimension=<N>,
           postgres_native=True,
           postgres_index_method="hnsw",
           postgres_operator_class="vector_cosine_ops",
       ),
   )
   ```

   Exact keyword names may differ, but the contract is fixed: the `embedding` column and its `VectorType` are what tell the Postgres provisioning path where to create the vector index.

   Recommended explicit-model shape:

   ```python
   model = postgres_native_vfs_object_model(dimension=1536)

   fs = PostgresFileSystem(
       engine=engine,
       model=model,
   )
   ```

   The model declaration is the schema contract. `PostgresFileSystem` consumes that model; it does not remember a second dimension value on the filesystem instance.

   Canonical shape for a correctly provisioned native Postgres table:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;

   CREATE INDEX ix_vfs_objects_embedding_cosine_hnsw
     ON vfs_objects USING hnsw (embedding vector_cosine_ops)
     WHERE embedding IS NOT NULL;
   ```

   Existing tables created before native pgvector support are a migration concern, not a runtime auto-repair concern. Normal backend initialization and schema verification must not rewrite the `embedding` column in place.

   Required indexing contract:

   - full-text: GIN index over an equivalent of `to_tsvector('simple', coalesce(content, ''))`
   - vector: ANN index using cosine ops on `vfs_objects.embedding`
   - `hnsw` is preferred; `ivfflat` is acceptable

   The verification method may accept either:

   - an expression index directly on `to_tsvector(...)`, or
   - a generated/stored `tsvector` column with an equivalent GIN index

6. Override the five search entry points:

   - `_lexical_search_impl`
   - `_grep_impl`
   - `_glob_impl`
   - `_vector_search_impl`
   - `_semantic_search_impl`

7. `lexical_search` must use PostgreSQL full-text search natively.

   Required behavior:

   - Preserve the current `DatabaseFileSystem` public semantics:
     - search anything with content
     - exclude versions
     - preserve user scoping and candidate filtering
     - return `VFSResult(function="lexical_search", entries=[Entry(...)])`
   - Use the repo’s existing tokenization boundary (`tokenize_query`) so query behavior stays close to the portable backend.
   - Build a Postgres tsquery from those tokens under the `simple` text search configuration by default.
   - Rank with a Postgres ranking function (`ts_rank_cd` preferred).
   - Keep the ranking query narrow: rank first, then hydrate only the top-`k` rows needed to preserve the existing `Entry(kind, content, score)` shape.
   - The ranking phase must not project `vfs_objects.content` or `vfs_objects.embedding` for the full candidate set.

8. `grep` must use PostgreSQL regex pushdown, but preserve VFS grep semantics exactly.

   Required behavior:

   - Reuse the existing regex-construction rules from `DatabaseFileSystem` (`case_mode`, `fixed_strings`, `word_regexp`).
   - Push positive-match row narrowing into Postgres via regex operators on `content`.
   - Reuse the literal-term extraction idea from `MSSQLFileSystem` for an optional sound prefilter when the pattern contains guaranteed literals.
   - Keep authoritative line grouping, line counts, and context-window reconstruction in Python using the shared helper path that already exists in `DatabaseFileSystem`.
   - `invert_match=True` remains Python-authoritative. Do **not** replace it with a row-level SQL `NOT regex` shortcut that would change per-line semantics.
   - Support all existing grep modes: `lines`, `files`, `count`, plus `max_count`, `paths`, `ext`, `ext_not`, `globs`, `globs_not`, and user scoping.

9. `glob` must use PostgreSQL regex/path pushdown.

   Required behavior:

   - Use `glob_to_sql_like()` as the coarse prefilter when it is sound.
   - Use a case-sensitive Postgres regex operator on `path` (`~`, not `~*`) as the authoritative database-side match.
   - Preserve the current `DatabaseFileSystem` behavior around visibility and filtering:
     - files/directories by default
     - candidate filtering
     - `paths`, `ext`, and `max_count`
     - user scoping
   - Portable `compile_glob()` behavior is the reference contract here; Postgres glob matching must not become case-insensitive unless that becomes an explicit cross-backend feature

10. Native vector search is the default when no explicit `vector_store` is supplied.

   Required behavior for `_vector_search_impl`:

    - If `self._vector_store is not None`, delegate to `DatabaseFileSystem` behavior for vector search.
    - Otherwise:
      - require pgvector-native schema to be present
      - read vectors directly from `vfs_objects.embedding`
      - exclude soft-deleted rows
      - exclude rows where `embedding IS NULL`
      - preserve candidate filtering and user scoping
      - rank by cosine distance in Postgres
      - translate distance into the VFS `score` field in descending-similarity order
      - return only `path` + `score` on the result rows

    Specific contract details:

    - Candidate filtering should use a Postgres-native array bind (`path = ANY(:paths)` or equivalent), not thousands of scalar placeholders.
    - The vector ranking query may touch `vfs_objects.embedding`, but the projected result rows must not expose raw embedding blobs through `Entry`.
    - Native vector search must work for direct `vector_search([...])` calls even when no `embedding_provider` is configured.

11. `_semantic_search_impl` must be overridden as well.

    This is mandatory because the base `DatabaseFileSystem` implementation currently hard-requires `_vector_store`.

    Required behavior:

    - If `self._vector_store is not None`, delegate to the base semantic-search behavior.
    - Otherwise:
      - require an `embedding_provider`
      - embed the query text
      - delegate to the native `_vector_search_impl`
    - Error messages for missing query text or missing `embedding_provider` should stay aligned with existing behavior.

12. Honor the user-provided `vector_store` override exactly as stated by product intent.

    This story’s vector precedence rule is:

    1. Explicit `vector_store` on `PostgresFileSystem` wins.
    2. Otherwise use native pgvector.

    Consequences:

    - native pgvector is the default vector path, not the only vector path
    - lexical search / grep / glob remain Postgres-native regardless of vector-store override
    - the backend must not dual-query both native pgvector and the external store for one call
    - missing pgvector schema must not block vector/semantic search when an explicit external `vector_store` is present

13. Make `VFSObject.embedding` + `VectorType` the canonical Postgres vector declaration.

    Required behavior:

    - `src/vfs/vector.py` must grow a Postgres-native path for `VectorType` instead of always serializing to JSON text
    - `VectorType` implements the native Postgres storage path by overriding `TypeDecorator.load_dialect_impl()` to return a lazily imported `pgvector.sqlalchemy.Vector(dimension)` when `dialect.name == "postgresql"` and `postgres_native=True`
    - `VectorType` must preserve the portable storage behavior for non-Postgres dialects
    - all other dialects, and Postgres when `postgres_native=False`, continue to use `Text` with JSON serialization
    - the `pgvector` package must not be imported at module load time
    - the Postgres path must be explicit enough that schema/provisioning code can inspect the model and know:
      - which column should receive the ANN index
      - which dimension the index expects
      - which operator class/metric should be used
    - `src/vfs/models.py` must declare `embedding` in a way that is valid for Postgres native vector indexing
    - native Postgres declarations require a fixed vector dimension; `postgres_native=True` with `dimension=None` is an invalid declaration and must fail immediately rather than deferring the error until search time
    - values returned through the native Postgres path must still be wrapped back into the repo's `Vector` runtime type so the Python-side contract stays uniform across dialects

14. Include a concrete migration/backfill path for existing Postgres deployments.

    This architecture changes the shared `embedding` column from portable serialized storage to a native Postgres vector column for Postgres-backed mounts that opt into the new backend.

    Required behavior:

    - the story must ship a documented migration path for existing Postgres databases whose `embedding` column was created under the old `VectorType` behavior
    - the migration may be an explicit admin/deployment step; it does not need to run automatically during request handling
    - the migration path must preserve existing embedding values
    - the migration path must end with a native `vector(<N>)` column plus the ANN index on that same column

15. Add the minimal shared write-path support required to keep native pgvector usable.

    The current shared write helpers persist content and metadata, but updates to `embedding` on existing rows are not threaded through reliably. This story must close that gap. This is a first-class shared-write-path change, not a Postgres-only footnote.

    Required behavior:

    - When a write/update object explicitly carries `embedding`, that value must be persisted on the `vfs_objects` row for both inserts and updates.
    - Under native Postgres mode, that persisted value must land in the native `vfs_objects.embedding` vector column directly.
    - Writes that do not explicitly set `embedding` must not accidentally clobber an existing stored embedding.
    - The implementation must distinguish:
      - embedding omitted by the caller -> preserve the stored value
      - embedding explicitly set to `None` -> clear the stored value
    - Plain `write(path, content)` / `edit()` calls do **not** auto-generate embeddings. They only preserve whatever embedding is already stored unless the caller explicitly clears it.

    This keeps the story honest:

    - `PostgresFileSystem` owns native vector search by default
    - it does **not** introduce automatic embedding generation or background indexing

16. Keep move/delete semantics correct under the direct-column design.

    - `move` should not require any vector rewrite because the embedding remains on the same `vfs_objects` row.
    - soft-deleted objects must disappear from native vector results via `vfs_objects.deleted_at IS NULL`
    - permanent delete should remove vectors naturally as part of row deletion; no second cleanup path should be required

17. Update packaging and developer ergonomics.

    - Add the Python pgvector adapter package to the `postgres` optional dependency group.
    - Export `PostgresFileSystem` from `vfs.backends`.
    - Update the repo’s Postgres probe script to exercise native search, including vector search when embeddings are present.
    - Document the explicit vector precedence rule and the required Postgres-native schema artifacts.

### Out

- No automatic content-to-embedding generation on `write`, `edit`, `copy`, or `move`
- No background worker or indexer integration in this story
- No auto-selection of `PostgresFileSystem` for every Postgres engine/dialect in the generic mount path
- No simultaneous dual-write or dual-query behavior across pgvector and an explicit external `vector_store`
- No metric-selection surface beyond one default similarity metric for native pgvector search
- No attempt to change the public `VectorStore` protocol
- No separate Postgres-only sidecar vector table; native pgvector lives on `vfs_objects.embedding`

## Native behavior contract

### Text search configuration

Use Postgres’s `simple` text search configuration by default.

Why:

- it is closer to code/document token semantics than `english` stemming
- it keeps behavior closer to the current `tokenize_query()` + BM25 path
- it avoids silently rewriting programmer identifiers into stemmed lexemes

This story does **not** add a public constructor/config surface for alternate FTS configs.

### Vector similarity metric

Use cosine similarity for the native pgvector path.

Why:

- it is the least surprising default for modern embedding vectors
- it aligns with the repo’s existing “higher score is better” search result shape
- pgvector supports cosine operator classes directly

`Entry.score` should be documented as a backend-local similarity score that is comparable within one result set, not a globally stable absolute measure across all backends.

### Result-shape parity

`PostgresFileSystem` must preserve existing result shapes:

- `lexical_search` returns ranked `Entry` rows with `path`, `kind`, `content`, `score`
- `grep` returns the same line-match structure and `function="grep"`
- `glob` returns the same path-oriented envelope
- `vector_search` returns `function="vector_search"` with `Entry(path, score)`
- `semantic_search` returns `function="semantic_search"` with `Entry(path, score)`

No backend-specific result envelope or Postgres-only row type is allowed.

## Acceptance criteria

### Backend surface

- [ ] `from vfs.backends import PostgresFileSystem` works.
- [ ] `PostgresFileSystem(engine=postgres_engine)` can be mounted and used without changing the public VFS API.
- [ ] `DatabaseFileSystem(engine=postgres_engine)` remains available for callers who do **not** want the native backend.

### Schema verification

- [ ] `verify_native_search_schema()` succeeds against a correctly provisioned Postgres database.
- [ ] Missing pgvector extension produces a clear error when native vector mode is active.
- [ ] A non-native or dimensionless `embedding` column produces a clear error when native vector mode is active.
- [ ] A mismatch between the database `embedding` dimension and the resolved model declaration produces a clear error when native vector mode is active.
- [ ] Missing ANN index on `vfs_objects.embedding` produces a clear error when native vector mode is active.
- [ ] Missing full-text index produces a clear error for the native lexical/grep path.
- [ ] When an explicit `vector_store` is supplied, vector-related verification is skipped or not required, but full-text verification still applies.
- [ ] Schema verification does not auto-alter an existing legacy `embedding` column; it raises and points the caller at the explicit migration path.

### Lexical / grep / glob

- [ ] `lexical_search()` ranks in Postgres and preserves the current `Entry` shape.
- [ ] `grep()` respects `case_mode`, `fixed_strings`, `word_regexp`, `output_mode`, `max_count`, and context-window semantics exactly as the portable backend does today.
- [ ] `grep(invert_match=True)` remains semantically correct and is not replaced by a lossy row-level SQL negation.
- [ ] `glob()` uses Postgres-native path matching and preserves existing candidate/path/ext/user-scope semantics.
- [ ] Postgres `glob()` remains case-sensitive, matching the current portable `compile_glob()` behavior.

### Vector / semantic search

- [ ] With no explicit `vector_store`, `vector_search()` uses native pgvector.
- [ ] With no explicit `vector_store`, `semantic_search()` uses `embedding_provider` + native pgvector.
- [ ] With an explicit `vector_store`, `vector_search()` delegates to that store instead of pgvector.
- [ ] With an explicit `vector_store`, `semantic_search()` delegates to the existing external-store behavior instead of requiring pgvector.
- [ ] Candidate filtering and user scoping work in both native and override vector paths.
- [ ] Native vector result rows do not project raw `embedding` data into `Entry`.

### Native vector column / migration

- [ ] Writes that explicitly provide `embedding` persist it on the object row for both inserts and updates.
- [ ] Under native Postgres mode, vector search reads directly from `vfs_objects.embedding`.
- [ ] Writes that do not explicitly touch `embedding` preserve the existing stored embedding value.
- [ ] Native Postgres mode resolves its required vector dimension from the model declaration, not from filesystem instance state alone.
- [ ] A documented migration/backfill path exists for legacy Postgres databases whose `embedding` column predates the native pgvector type.
- [ ] Soft-deleted objects never appear in native vector results.
- [ ] Permanent deletes remove vectors naturally because the embedding lives on the same row.

### Tooling / docs

- [ ] `pyproject.toml`’s `postgres` extra includes the Python package(s) needed for pgvector adaptation.
- [ ] `tests/conftest.py --postgres` can provision the native Postgres search artifacts needed for backend integration tests.
- [ ] The Postgres probe script covers the native backend rather than the generic `DatabaseFileSystem` path.
- [ ] Public docs describe the pgvector-default plus explicit-`vector_store` override rule.

## Test plan

The implementation is not complete until the tests below exist and pass.

### 1. Pure unit tests

Add pure-Python tests for backend-local helpers that do not require a live database, for example:

- tsquery term quoting / token-to-tsquery builder
- schema-qualified table-name resolver
- any shared literal-term extraction helper hoisted from MSSQL for grep prefiltering
- vector-dimension parsing/introspection helpers, if split out

These should run in the default suite with no `--postgres` flag.

### 2. Postgres integration tests

Add `tests/test_postgres_backend.py` gated on `--postgres`.

Minimum coverage:

- `test_verify_native_search_schema_success`
- `test_verify_native_search_schema_missing_vector_extension`
- `test_verify_native_search_schema_rejects_non_native_embedding_column`
- `test_verify_native_search_schema_dimension_mismatch`
- `test_verify_native_search_schema_missing_fts_index`
- `test_verify_native_search_schema_missing_vector_index`
- `test_verify_native_search_schema_does_not_auto_alter_legacy_embedding_column`
- `test_lexical_search_ranks_in_postgres_and_hydrates_top_k_only`
- `test_grep_regex_pushdown_preserves_line_matches`
- `test_grep_invert_match_stays_python_authoritative`
- `test_glob_pushdown_matches_path_regex`
- `test_glob_pushdown_is_case_sensitive`
- `test_vector_search_uses_native_pgvector_by_default`
- `test_semantic_search_uses_embedding_provider_plus_pgvector`
- `test_vector_store_override_bypasses_pgvector`
- `test_vector_search_candidates_filter_with_native_pgvector`
- `test_vector_search_user_scope_with_native_pgvector`
- `test_vector_search_reads_from_vfs_objects_embedding`
- `test_write_with_embedding_persists_native_vector_column`
- `test_update_embedding_rewrites_native_vector_column`
- `test_write_without_embedding_preserves_existing_embedding`
- `test_legacy_embedding_column_migration_path`
- `test_soft_deleted_rows_are_excluded_from_native_vector_search`

### 3. Cross-backend regression coverage

Update existing shared tests where appropriate so `PostgresFileSystem` is held to the same contract as other backends:

- `tests/test_vector_store.py`
- `tests/test_backend_projection.py`
- CLI hydration/projection tests when the native backend is mounted under `--postgres`

Important assertion:

- native vector ranking may consult `vfs_objects.embedding`, but the projected `vfs_objects` row fetch must still omit `embedding` unless the caller explicitly requests it

### 4. Postgres fixture provisioning

Extend `tests/conftest.py` with a Postgres-native provisioning helper analogous to `_provision_mssql_fulltext(...)`.

It should:

- install/verify the `vector` extension in the test database
- ensure the `embedding` column is created as native `vector(<N>)` for the Postgres-native test path
- create the ANN index
- create the full-text index used by the backend

This provisioning is test/development infrastructure, not the production runtime path.

### 5. Manual smoke

Reviewer smoke checks:

- `uv run pytest --postgres tests/test_postgres_backend.py`
- `uv run pytest --postgres`
- `uv run python scripts/postgres_repo_cli_probe.py`

The probe script should include at least one native vector-search check when embeddings are available in the seeded corpus.

## References

- Existing native backend pattern: `src/vfs/backends/mssql.py`
- Portable baseline: `src/vfs/backends/database.py`
- Vector-store protocol and current override path: `src/vfs/vector_store.py`
- Current embedding model field: `src/vfs/models.py`
- Postgres deployment direction: `docs/plans/cloud_architecture_research.md`
- Background research: `context/learnings/2026-02-17-database-vfs-patterns.md`
- Constitution articles: 2 (agent-first contract), 4 (backend-agnostic contract), 5 (operational discipline)

## Decisions resolved by this spec

- **Explicit vector-store override wins.** Native pgvector is the default for `PostgresFileSystem`, but a caller-provided `vector_store` takes precedence for vector/semantic search.
- **Native vector storage lives on `VFSObject.embedding`.** `VectorType` and the model field are the source of truth for where Postgres native vector indexing happens.
- **Native vector dimension is model-declared.** Schema verification compares the live column to the resolved model and raises on mismatch. `PostgresFileSystem` does not carry a separate `embedding_dimension=` constructor surface.
- **Native grep/lexical/glob are part of the backend.** `PostgresFileSystem` is not “vector only”; it is the Postgres-native search backend analogous to `MSSQLFileSystem`.
- **No auto-embedding generation.** The backend owns native search execution and native storage on `embedding`, not content analysis or embedding production.
- **Legacy `embedding` columns are not auto-rewritten at runtime.** Verification raises; migration is explicit.
- **`simple` FTS config and cosine similarity are the defaults.** No public tuning surface ships in this story.

## Non-goals made explicit

- Shipping a general-purpose indexing service
- Replacing external vector stores
- Redesigning the public search API
- Changing VFS result-envelope semantics for backend-specific features
