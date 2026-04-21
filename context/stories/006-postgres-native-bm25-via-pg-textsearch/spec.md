# 006 — Postgres-native BM25 via `pg_textsearch`

- **Status:** draft
- **Date:** 2026-04-20
- **Owner:** Clay Gendron
- **Kind:** feature + backend

## Intent

Replace the current `ts_rank_cd` ranking in `PostgresFileSystem._lexical_search_impl` with a true BM25 ranking path, powered by the `pg_textsearch` extension. The swap is opt-in, follows the same deployment-managed pattern as pgvector, and preserves the existing `lexical_search` contract exactly. The existing `"native"` path remains PostgreSQL full-text search compatibility mode, not a second BM25 implementation.

Today:

- `PostgresFileSystem._lexical_search_impl` ([`src/vfs/backends/postgres.py:287`](../../../src/vfs/backends/postgres.py)) ranks with `ts_rank_cd`, which is Postgres's cover-density function. Useful, but it uses no corpus-wide IDF and is not BM25.
- Core PostgreSQL still does not provide BM25 in its documented full-text stack. The built-in path is `tsvector` / `tsquery` plus `ts_rank` / `ts_rank_cd`; BM25 requires an extension.
- The rest of the repo already speaks BM25: `vfs.bm25.BM25Scorer` powers the portable `DatabaseFileSystem` lexical path, and `tokenize_query` feeds both the portable scorer and the Postgres tsquery construction.
- The result is a semantic mismatch: Grover advertises BM25 lexical search, but the Postgres backend scores with a different algorithm than the portable backend.

After this story:

- `PostgresFileSystem` supports a `bm25_backend` selector with values `"pg_textsearch"` and `"native"` (default `"native"` for backward compatibility).
- When `bm25_backend="pg_textsearch"`, `_lexical_search_impl` ranks with the `pg_textsearch` BM25 index using the `<@>` operator.
- When `bm25_backend="native"`, `_lexical_search_impl` continues to use PostgreSQL native FTS ranking. Docs and operator-facing errors must describe this path as native FTS / cover-density ranking, not BM25.
- `verify_native_search_schema` fail-fast-validates the extension and index when `bm25_backend="pg_textsearch"`, analogous to the pgvector verification path.
- `_grep_impl` continues to use the existing native FTS GIN index for literal-term pre-filtering. Pre-filter semantics do not change and do not depend on BM25 backend selection.
- Public VFS contract, `Entry` / `VFSResult` shapes, candidate filtering, user scoping, and error behavior remain unchanged.

## Why

- **Algorithmic correctness.** BM25 is what the repo claims to do. Two backends scoring with two different algorithms is a defect.
- **Terminology correctness.** Core Postgres FTS is valuable, but it is not BM25. The spec and user-facing docs must stop blurring that distinction.
- **Score comparability across backends.** The portable `DatabaseFileSystem` BM25 path and the Postgres-native path should rank with the same algorithm so an agent's hybrid retrieval results don't shift behavior based on which backend happens to back a mount.
- **Performance on large corpora.** `pg_textsearch`'s Block-Max WAND optimization is designed for top-k over large corpora and outperforms native FTS ranking significantly on vendor benchmarks (2.4–11.7× on MS-MARCO short queries at 138M docs). Grover's agent-driven workload is dominated by short, concurrent queries, which is the exact sweet spot.
- **Schema fit.** `pg_textsearch` supports partial and expression BM25 indexes on standard Postgres pages. That matches `vfs_objects` — a single heterogeneous table where only a subset of rows is searchable. The alternative considered (`pg_search`) requires one covering BM25 index per table and does not fit this schema cleanly. See [`context/learnings/2026-04-20-postgres-native-bm25.md`](../../learnings/2026-04-20-postgres-native-bm25.md) for the full comparison.
- **Operational symmetry with pgvector.** Both extensions are deployment-managed, both require `shared_preload_libraries`, both fail-fast-verify at startup. Adding `pg_textsearch` follows the same operational template the repo already teaches operators for pgvector.
- **Constitution fit.** Article 4 backend swap. Public VFS contract unchanged.

## Expected touch points

- Update [`src/vfs/backends/postgres.py`](../../../src/vfs/backends/postgres.py) — add the selector, extend verification, add the BM25 SQL path to `_lexical_search_impl`.
- Update [`pyproject.toml`](../../../pyproject.toml) — no new Python dependency; `pg_textsearch` is a server-side extension only.
- Update [`tests/conftest.py`](../../../tests/conftest.py) — Postgres provisioning for `pg_textsearch` when the test environment supports it.
- Add `tests/test_postgres_bm25.py` (or extend `tests/test_postgres_backend.py`) — verification, ranking, error paths, and grep-path non-regression.
- Update [`scripts/postgres_repo_cli_probe.py`](../../../scripts/postgres_repo_cli_probe.py) — probe the BM25 path when `pg_textsearch` is present.
- Update public docs — [`docs/architecture.md`](../../../docs/architecture.md), [`docs/index.md`](../../../docs/index.md), and any backend doc that currently describes the Postgres lexical search path.
- Reference the learning memo: [`context/learnings/2026-04-20-postgres-native-bm25.md`](../../learnings/2026-04-20-postgres-native-bm25.md).

## Scope

### In

1. **Add a `bm25_backend` selector to `PostgresFileSystem`.**

   ```python
   from typing import Literal

   BM25Backend = Literal["pg_textsearch", "native"]

   class PostgresFileSystem(DatabaseFileSystem):
       def __init__(
           self,
           *,
           bm25_backend: BM25Backend = "native",
           **kwargs,
       ) -> None:
           super().__init__(**kwargs)
           self._bm25_backend = bm25_backend
   ```

   - Instance-level, not class-level: multi-tenant deployments may run different backends per mount.
   - Default is `"native"` so this story is strictly additive — existing deployments keep working without configuration.
   - Changing the default to `"pg_textsearch"` is a separate, follow-up story once the extension is broadly deployed.
   - Composes with `pattern_backend` from story 007 on the same `PostgresFileSystem.__init__`; whichever story lands first, the other must add its kwarg alongside rather than replace.

2. **Extend `verify_native_search_schema` to validate the BM25 backend when selected.**

   When `bm25_backend == "pg_textsearch"`:
   - Verify the `pg_textsearch` extension is installed (`SELECT 1 FROM pg_extension WHERE extname = 'pg_textsearch'`).
   - Verify a BM25 index exists on `vfs_objects.content` using `am = 'bm25'`.
   - Verify the index is partial on the expected predicate (`content IS NOT NULL AND deleted_at IS NULL AND kind != 'version'`) — either by exact match or by inspecting `pg_index.indpred` for equivalence.
   - Raise `RuntimeError` with an actionable `CREATE EXTENSION` + `CREATE INDEX` pair if any precondition fails, analogous to the pgvector error messages at [`src/vfs/backends/postgres.py:210`](../../../src/vfs/backends/postgres.py) and [`src/vfs/backends/postgres.py:272`](../../../src/vfs/backends/postgres.py).

   When `bm25_backend == "native"`: existing FTS verification behavior unchanged.

   The existing `_native_fulltext_verified` memoization pattern extends to a parallel `_native_bm25_verified` flag. Both checks run independently.

3. **Implement the `pg_textsearch` branch of `_lexical_search_impl`.**

   Canonical query shape:

   ```sql
   WITH ranked AS (
       SELECT
           o.path,
           o.kind,
           (o.content <@> to_bm25query(:query, 'ix_vfs_objects_bm25_content')) AS raw_score
       FROM {table} AS o
       WHERE o.content IS NOT NULL
         AND o.deleted_at IS NULL
         AND o.kind != 'version'
         {user_scope_clause}
   )
   SELECT path, kind, -raw_score AS score
   FROM ranked
   ORDER BY raw_score ASC, path
   LIMIT :k
   ```

   Required behavior:

   - Use the explicit `to_bm25query(query, index_name)` form. The implicit `content <@> 'query'` form depends on planner hooks that don't fire inside PL/pgSQL, and we want deterministic index selection regardless of caller context.
   - Reuse `tokenize_query(...)` for input normalization.
   - Preserve the current multi-term match-set semantics of the native Postgres path: a query with terms `t1 t2 ...` must continue to match documents containing **any** token, not silently narrow to all-token matching.
   - The implementation may not assume that whitespace-joining tokens preserves that behavior. It must construct the `pg_textsearch` query text in whatever explicit form is required to keep the current any-term semantics, and tests must lock that behavior down.
   - Negate the `<@>` result before writing into `Entry.score`. The operator returns a negative score so Postgres sort-ascending yields best-first; `Entry.score` is documented as "higher is better."
   - Rank-then-hydrate just as the current path does: first query returns `(path, kind, score)`, second query fetches `content` for only the top-k paths via `WHERE path = ANY(:paths)`.
   - Preserve `candidates is not None` delegation to the base `DatabaseFileSystem._lexical_search_impl` (the candidate-scoped path already uses Python BM25; it stays as-is).
   - Preserve user scoping via the existing `/{user_id}/%` LIKE clause.
   - Preserve the `kind != 'version'` and `deleted_at IS NULL` filters.

4. **Keep the existing native-FTS grep pre-filter unchanged.**

   `_grep_impl` ([`src/vfs/backends/postgres.py:372`](../../../src/vfs/backends/postgres.py)) uses `to_tsquery(...)` with AND semantics for literal-term pre-filtering. `pg_textsearch` 1.0 is OR-only and lacks phrase positions, so it is not a valid replacement for this pre-filter.

   Consequence: when `bm25_backend="pg_textsearch"`, the database carries both indexes:

   - the existing GIN `to_tsvector` index used for grep pre-filtering
   - the new `pg_textsearch` BM25 index used for lexical ranking

   This is intentional. They serve different purposes and cost disk, not query-time work. The alternative — removing the grep pre-filter — would regress grep latency on large corpora.

   Document this explicitly in the operator-facing error messages and docs. Operators who provision `pg_textsearch` must still provision the GIN FTS index.

5. **Define the required BM25 index shape.**

   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_textsearch;

   CREATE INDEX ix_vfs_objects_bm25_content
       ON vfs_objects
       USING bm25 (content)
       WITH (text_config = 'simple')
       WHERE content IS NOT NULL
         AND deleted_at IS NULL
         AND kind != 'version';
   ```

   Notes:

   - `text_config = 'simple'` matches the existing `FULLTEXT_CONFIG` constant. No stemming; keeps behavior aligned with the portable BM25 scorer that tokenizes on whitespace/punctuation.
   - The partial-index predicate mirrors the runtime `WHERE` clause so the planner uses the index directly.
   - The schema-qualified table name follows `_resolve_table()`.

6. **Expose the selector through the public surface.**

   - Document the new `bm25_backend` kwarg in the `PostgresFileSystem` docstring.
   - Keep construction simple; no factory, no registry:

     ```python
     fs = PostgresFileSystem(
         engine=engine,
         model=model,
         bm25_backend="pg_textsearch",
     )
     ```

   - No settings module, no environment variable. Story 003 already established that deployment decisions about native backends live at the construction site, not in global config.

7. **Update the Postgres probe script.**

   Extend [`scripts/postgres_repo_cli_probe.py`](../../../scripts/postgres_repo_cli_probe.py) so that when it is exercising the BM25 path, it instantiates `PostgresFileSystem(bm25_backend="pg_textsearch", ...)` and exercises `lexical_search` through the probe's normal flow.

   If the extension or BM25 index is absent, the probe must surface that misconfiguration clearly and fail or skip the BM25 portion explicitly. It must **not** silently substitute native FTS for a requested BM25 probe.

8. **Update docs.**

   Minimum:

   - [`docs/architecture.md`](../../../docs/architecture.md) — describe the `bm25_backend` selector, the required index shape, and the "both indexes coexist" constraint for grep.
   - [`docs/index.md`](../../../docs/index.md) — backend capability matrix gains a BM25 row, and the native Postgres fallback is described as FTS rather than BM25.
   - Reference [`context/learnings/2026-04-20-postgres-native-bm25.md`](../../learnings/2026-04-20-postgres-native-bm25.md) for the decision trail.

### Out

- **Default flip to `pg_textsearch`.** Stays `"native"` in this story. A separate story decides when deployment readiness supports flipping.
- **`pg_search` support.** Explicitly rejected per [`context/learnings/2026-04-20-postgres-native-bm25.md`](../../learnings/2026-04-20-postgres-native-bm25.md). Do not add a third selector value.
- **Custom `k1` / `b` tuning.** Use `pg_textsearch` defaults. No public tuning surface in this story.
- **Alternate text configs.** `'simple'` only, matching the current `FULLTEXT_CONFIG`. Language-aware analyzers are a follow-up.
- **Phrase queries.** Not in the current `lexical_search` contract. `pg_textsearch` does not support them anyway.
- **Hybrid search changes.** The hybrid lexical + vector composition stays in application code. This story only changes how the lexical step scores.
- **Automatic extension installation.** Like pgvector, `pg_textsearch` is deployment-managed. The backend does not `CREATE EXTENSION` at runtime.
- **Migration of existing `ts_rank_cd` scores.** Scores are not persisted; the change is transparent at the next query.
- **Multiple BM25 indexes per table.** One partial index on `content` is enough for this story. Multi-language or per-kind indexes are a follow-up if ever needed.
- **Treating `bm25_backend="native"` as BM25.** It remains PostgreSQL native FTS compatibility mode. Only the `pg_textsearch` path is BM25.

## Native behavior contract

### Score polarity

`pg_textsearch`'s `<@>` operator returns a **negative** BM25 score so default Postgres sort-ascending yields best-first. `Entry.score` is documented as "higher is better, comparable within a result set." The backend negates the operator result before filling `Entry.score`. Callers continue to see positive scores in the VFSResult, unchanged from the `ts_rank_cd` contract.

### Backend selection visibility

`_lexical_search_impl` does not advertise which backend produced a score. `Entry.score` is a local, within-result-set quantity regardless of backend — that rule is already documented in story 003. Callers comparing scores across mounts must do so with awareness; this story does not strengthen or weaken that contract.

### Failure mode

If `bm25_backend="pg_textsearch"` is selected against a database where the extension or index is missing, the first `lexical_search` call raises `RuntimeError` with an actionable message containing the exact `CREATE EXTENSION` + `CREATE INDEX` pair required. Same pattern as pgvector. No silent degradation. No auto-fallback to native FTS — silently changing the ranking algorithm mid-deployment would defeat the purpose.

### Write-path impact

No application write-path code changes. `pg_textsearch` indexes are transactionally maintained by the extension, so Grover's shared write path ([`src/vfs/backends/database.py:1226`](../../../src/vfs/backends/database.py)) does not need changes.

However, the operational write cost does increase when operators provision both:

- the existing GIN FTS index for grep pre-filtering, and
- the BM25 index for lexical ranking.

This story changes read-path behavior only in Grover code; it does not claim zero database-side indexing overhead.

## Acceptance criteria

### Backend surface

- [ ] `PostgresFileSystem(engine=engine, model=model, bm25_backend="pg_textsearch")` constructs without error.
- [ ] `bm25_backend="native"` (the default) preserves existing behavior exactly — no observable change in `lexical_search` output for existing deployments.
- [ ] `_grep_impl` behavior is unchanged across both selector values.

### Schema verification

- [ ] `verify_native_search_schema()` passes against a database with `pg_textsearch` installed, the partial BM25 index present, and the native FTS GIN index present, when `bm25_backend="pg_textsearch"`.
- [ ] Missing `pg_textsearch` extension produces a clear `RuntimeError` with a `CREATE EXTENSION` hint.
- [ ] Missing BM25 index produces a clear `RuntimeError` with the exact `CREATE INDEX` statement.
- [ ] BM25 index present but lacking the expected partial predicate produces a clear `RuntimeError`; the backend does not warn-and-continue.
- [ ] Verification for `bm25_backend="native"` is unchanged and continues to pass against deployments that have not provisioned `pg_textsearch`.

### Lexical search

- [ ] `lexical_search(query)` under `bm25_backend="pg_textsearch"` returns `VFSResult(function="lexical_search", entries=[Entry(path, kind, content, score)])` with the same shape as the native path.
- [ ] `Entry.score` is positive (negation of the `<@>` operator's negative BM25 score).
- [ ] Results are ordered by descending `score`, with stable secondary ordering by `path`.
- [ ] Multi-term queries preserve the current any-term recall semantics of the native Postgres path; selecting BM25 must not silently narrow matches to all-term queries.
- [ ] User scoping (`/{user_id}/%`) works identically to the native path.
- [ ] `candidates is not None` delegates to the base Python BM25 path, unchanged.
- [ ] Empty/whitespace queries return the same `_error("lexical_search requires a query")` shape.
- [ ] The ranking query does not project `content` or `embedding` for the full candidate set; hydration happens only for the top-k paths.

### Grep non-regression

- [ ] `grep(pattern, ...)` with any combination of `case_mode`, `fixed_strings`, `word_regexp`, `invert_match`, `output_mode`, `max_count`, `paths`, `ext`, `ext_not`, `globs`, `globs_not`, and user scoping returns identical results under `bm25_backend="pg_textsearch"` and `bm25_backend="native"`.
- [ ] The grep literal pre-filter continues to use the native FTS GIN index, regardless of BM25 backend.

### Tooling / docs

- [ ] `tests/conftest.py` can provision `pg_textsearch` when the test environment supports it, gated similarly to existing `--postgres` fixtures.
- [ ] Tests for `pg_textsearch` skip cleanly when the extension is unavailable; they do not fail the suite.
- [ ] `scripts/postgres_repo_cli_probe.py` exercises `bm25_backend="pg_textsearch"` when the extension is present.
- [ ] `docs/architecture.md` documents the selector, the required index shape, and the "both indexes coexist" rule for grep.
- [ ] `docs/index.md` mentions BM25 as a supported ranking mode for Postgres and distinguishes it from the native FTS fallback.
- [ ] A test verifies that choosing `bm25_backend="pg_textsearch"` against a misconfigured database raises with the expected error messages.

## Test plan

### 1. Pure unit tests (no live database)

- BM25 score negation: verify the post-processing that flips `<@>`-returned negatives into positive `Entry.score`.
- Query text construction: verify `tokenize_query` feeds a `pg_textsearch` query string that preserves the current any-term semantics for multi-term queries.
- Selector default: verify `bm25_backend` defaults to `"native"` and that the stored attribute is preserved.
- Verification branching: a unit-level test that confirms the verification dispatch picks the right SQL path for each selector value (using a stub session).

### 2. Postgres integration tests (`--postgres --pg-textsearch` or equivalent)

Gate integration tests that require the extension behind a new pytest marker/flag so they skip cleanly when the environment lacks `pg_textsearch`.

Minimum coverage:

- `test_verify_bm25_schema_success`
- `test_verify_bm25_schema_missing_extension`
- `test_verify_bm25_schema_missing_index`
- `test_verify_bm25_schema_rejects_wrong_partial_predicate`
- `test_lexical_search_uses_bm25_when_selected`
- `test_lexical_search_score_is_positive_under_bm25`
- `test_lexical_search_multi_term_query_preserves_any_term_semantics`
- `test_lexical_search_candidates_delegates_to_python_bm25`
- `test_lexical_search_user_scope_under_bm25`
- `test_grep_unchanged_under_bm25_selector`
- `test_grep_literal_prefilter_still_uses_fts_gin`
- `test_bm25_failure_when_extension_missing_raises_actionable_error`

### 3. Cross-backend regression coverage

Update shared lexical-search tests so they run under both selector values on Postgres and confirm the public contract is held equal:

- `tests/test_backend_projection.py` — projection equivalence under BM25.
- Any shared test that asserts specific `lexical_search` behavior should pass under both `bm25_backend="native"` and `bm25_backend="pg_textsearch"`.

### 4. Postgres fixture provisioning

Extend [`tests/conftest.py`](../../../tests/conftest.py) with a `pg_textsearch` provisioning helper:

- detect whether the test Postgres supports `CREATE EXTENSION pg_textsearch`
- install the extension and create the partial BM25 index during fixture setup
- expose a fixture (e.g. `postgres_bm25_db`) analogous to `postgres_native_db`
- skip cleanly when the extension cannot be installed

### 5. Manual smoke

- `uv run --extra postgres pytest --postgres --pg-textsearch tests/test_postgres_bm25.py`
- `uv run --extra postgres pytest --postgres --pg-textsearch`
- `uv run --extra postgres python scripts/postgres_repo_cli_probe.py`

## References

- Current backend: [`src/vfs/backends/postgres.py`](../../../src/vfs/backends/postgres.py)
- Sibling native backend (pgvector pattern): story 003, [`context/stories/003-postgres-filesystem-with-native-vector-search/`](../003-postgres-filesystem-with-native-vector-search/)
- Portable BM25 scorer: [`src/vfs/bm25.py`](../../../src/vfs/bm25.py) (used by base `DatabaseFileSystem` and kept in place for candidate-scoped search)
- Decision trail: [`context/learnings/2026-04-20-postgres-native-bm25.md`](../../learnings/2026-04-20-postgres-native-bm25.md)
- Upstream extension: [`timescale/pg_textsearch`](https://github.com/timescale/pg_textsearch)
- Constitution articles: 2 (agent-first contract), 4 (backend-agnostic contract), 5 (operational discipline)

## Decisions resolved by this spec

- **BM25 extension choice is `pg_textsearch`, not `pg_search`.** Partial-index fit to `vfs_objects` and Grover's narrower `lexical_search` contract drove the choice. `pg_search`'s one-BM25-index-per-table constraint is incompatible with the heterogeneous schema.
- **Selector is instance-level, not a new subclass.** `PostgresFileSystem` already represents "the Postgres-native backend." BM25 vs native-FTS ranking is a configuration of that backend, not a separate backend.
- **Default stays `"native"`.** Strict backward compatibility. Flipping the default is a future story once deployment readiness catches up.
- **Grep pre-filter stays on native FTS.** `pg_textsearch` 1.0 lacks AND / phrase semantics. Both indexes coexist.
- **Text config stays `'simple'`.** Matches portable BM25 tokenization; no stemming surprises for code/document corpora.
- **No auto-fallback.** If `bm25_backend="pg_textsearch"` is selected against a misconfigured database, raise. Silently degrading to a different ranking algorithm mid-deployment is a correctness defect.

## Non-goals made explicit

- Replacing the grep path's pre-filter with `pg_textsearch`.
- Adding `pg_search` as an alternate BM25 backend.
- Tuning `k1` / `b` or exposing them publicly.
- Language-aware analyzers, stemming, or multi-config indexes.
- Phrase queries, faceting, highlighting.
- Automatic extension installation.
- Changing the hybrid lexical + vector composition layer.
