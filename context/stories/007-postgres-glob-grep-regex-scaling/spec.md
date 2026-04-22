# 007 — Postgres-native glob / grep with sound pushdown

- **Status:** draft
- **Date:** 2026-04-21
- **Owner:** Clay Gendron
- **Kind:** feature + backend

## Intent

Make `PostgresFileSystem` pattern matching behave like a good `vfs` product surface:

- any valid `glob()` / `grep()` pattern should work
- PostgreSQL should do as much sound narrowing as it can
- Python remains the authoritative final matcher when SQL can only produce a safe superset
- false negatives are never acceptable

For full-corpus Postgres `glob()` and `grep()`, the backend should aggressively use native indexes and operators to reduce the working set, but it must not reject valid patterns merely because they are hard to index. The contract is "best available native narrowing, then exact final filtering," which is the same product shape MSSQL already follows even though the specific database primitives differ.

Today:

- `PostgresFileSystem._glob_impl` uses `LIKE` as a coarse pre-filter and `~` as the authoritative path match.
- `PostgresFileSystem._grep_impl` optionally adds an FTS literal pre-filter, but general regex qualification still depends on database regex over `content`.
- `verify_native_search_schema()` validates full-text and vector artifacts, but it does not validate the pattern-search schema required for scalable path and content narrowing.
- The resulting behavior is opportunistic rather than deliberate: some queries push down well, some do not, and the product contract is not stated clearly.

After this story:

- `PostgresFileSystem` always requires the pattern-search schema (`pg_trgm`, path prefix index, path trigram index, content trigram index).
- `verify_native_search_schema()` fail-fast-validates those artifacts.
- Full-corpus `glob()` and `grep()` push down every sound narrowing step available for the query shape.
- SQL may over-select, but the backend must not leave out true matches.
- Python remains the authoritative final matcher whenever PostgreSQL cannot express the exact semantics without risking false negatives.
- Candidate-scoped operations (`candidates is not None`) continue to run in process; that is already the right bounded behavior for pipelines.

## Why

- **Product correctness.** `vfs grep` and `vfs glob` are user-facing query primitives. Users care first that valid patterns work and results are correct. Missing hits because the backend refused a hard pattern is the worse product failure.
- **Pushdown still matters.** PostgreSQL can materially reduce work with `text_pattern_ops`, `pg_trgm`, and literal-term/FTS narrowing. We should use those aggressively even when they only produce a superset.
- **Pipeline fit.** The query language naturally produces bounded candidate sets through pipelines. That means the backend should support both modes well: aggressive SQL narrowing for full-corpus search, pure in-process filtering for bounded candidate sets.
- **MSSQL parity in product behavior.** SQL Server is more capable at server-side regex qualification, but the important product lesson is not "reject what the engine cannot index." It is "push down what you can, preserve correctness, and finish authoritatively in process when needed."
- **Constitution fit.** Article 4 backend swap. The Postgres backend becomes more explicit and more scalable without changing the public query language.

## Expected touch points

- [`src/vfs/backends/postgres.py`](../../../src/vfs/backends/postgres.py) — replace opportunistic pattern pushdown with an explicit "sound narrowing + authoritative final filter" strategy for full-corpus `glob()` / `grep()`
- [`src/vfs/backends/database.py`](../../../src/vfs/backends/database.py) — only if a small shared helper seam is useful for authoritative post-filtering or literal extraction
- [`tests/conftest.py`](../../../tests/conftest.py) — provision the required Postgres pattern-search schema
- [`tests/test_postgres_backend.py`](../../../tests/test_postgres_backend.py) or a dedicated `tests/test_postgres_patterns.py` — verification, plan-shape, and no-false-negative tests
- [`scripts/postgres_repo_cli_probe.py`](../../../scripts/postgres_repo_cli_probe.py) — probe the accelerated path and verify correctness on hard patterns
- [`docs/architecture.md`](../../../docs/architecture.md), [`docs/index.md`](../../../docs/index.md) — document the Postgres pattern backend as sound pushdown plus authoritative final filtering

## Scope

### In

1. **Remove the pattern backend selector.**

   There is one Postgres-native pattern backend. Delete the `pattern_backend` split from the story design.

   Keep only:

   ```python
   class PostgresFileSystem(DatabaseFileSystem):
       def __init__(self, **kwargs) -> None:
           super().__init__(**kwargs)
   ```

   Notes:

   - There is no `"baseline"` mode and no `"trigram"` mode.
   - If the required schema is missing, `PostgresFileSystem` is misconfigured for native pattern search and must raise.

2. **Make pattern-schema verification mandatory.**

   `verify_native_search_schema()` must validate all of the following for Postgres native pattern search:

   - `pg_trgm` extension installed
   - a partial B-tree `text_pattern_ops` index for `path`
   - a partial trigram index for `path`
   - a partial trigram index for live file `content`

   Missing any artifact is a hard `RuntimeError` with actionable `CREATE EXTENSION` / `CREATE INDEX` statements.

3. **Define the required schema.**

   Canonical shape:

   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;

   CREATE INDEX ix_vfs_objects_path_pattern
     ON vfs_objects (path text_pattern_ops)
     WHERE deleted_at IS NULL;

   CREATE INDEX ix_vfs_objects_path_trgm_gin
     ON vfs_objects USING GIN (path gin_trgm_ops)
     WHERE deleted_at IS NULL;

   CREATE INDEX ix_vfs_objects_content_trgm_gin
     ON vfs_objects USING GIN (content gin_trgm_ops)
     WHERE kind = 'file'
       AND content IS NOT NULL
       AND deleted_at IS NULL;
   ```

   Notes:

   - `text_pattern_ops` exists so left-anchored `LIKE '/prefix/%'` stays predictably indexable across non-`C` collations.
   - `pg_trgm` indexes support `LIKE`, `ILIKE`, `~`, and `~*`. Some patterns still produce weak selectivity or full-index scans; that is a performance concern, not a correctness reason to reject a valid user pattern.
   - GIN is the default index family here because the workload is read-heavy and does not require ordered similarity retrieval.
   - Partial predicates should stay aligned with the runtime `WHERE` clauses so the planner can use the indexes directly.

4. **Glob uses sound narrowing first, Python as the source of truth.**

   Full-corpus `glob()` must:

   - preserve current case-sensitive glob semantics
   - preserve `paths`, `ext`, `max_count`, candidate filtering, and user scoping behavior
   - use literal-prefix decomposition first
   - use the `path text_pattern_ops` index for left-anchored prefixes where available
   - use the `path gin_trgm_ops` index for residual path regex narrowing where useful
   - allow SQL to over-select, then apply the authoritative glob matcher before returning results

   Required product rule:

   - if PostgreSQL can narrow the pattern soundly, do so
   - if PostgreSQL cannot narrow much, the query still works
   - final returned rows must match the exact glob semantics

   The backend must never rely on an approximation that can drop a true hit.

5. **Grep uses sound row narrowing first, Python as the source of truth.**

   Full-corpus `grep()` must:

   - preserve `case_mode`, `fixed_strings`, `word_regexp`, `invert_match`, `output_mode`, `before_context`, `after_context`, `max_count`, structural filters, and user scoping
   - use PostgreSQL to narrow the candidate row set as much as soundly possible
   - keep Python authoritative for final line reconstruction and exact line-oriented match semantics

   Required execution shape:

   - `fixed_strings=True` uses `LIKE` / `ILIKE` over `content`, relying on the content trigram index when useful
   - regex search may use `content ~ :pattern` or `content ~* :pattern` as a narrowing predicate when that is a sound superset relative to final line matching
   - extracted literal runs may be added as conjunctive pre-filters (`LIKE` / `ILIKE` and/or FTS literal-term narrowing) when they cannot introduce false negatives
   - the query must keep the live-row predicates (`kind = 'file'`, `content IS NOT NULL`, `deleted_at IS NULL`) aligned with the partial trigram index

   Product rule:

   - SQL narrowing is an optimization
   - Python matching is authoritative
   - no valid grep hit may be lost because a pre-filter was too aggressive

6. **Candidate-scoped grep and glob remain in-process.**

   When `candidates is not None`, continue to use the bounded in-memory path. This is already the right product behavior for pipelines because:

   - the candidate set is caller-bounded
   - correctness is simpler
   - the user intent is already "filter these results further," not "search the whole corpus efficiently"

7. **Document the contract clearly.**

   Minimum:

   - [`docs/architecture.md`](../../../docs/architecture.md) explains that Postgres pattern search uses native narrowing where possible and authoritative Python filtering for exact semantics
   - [`docs/index.md`](../../../docs/index.md) explains that the trigram/pattern indexes improve narrowing and throughput but do not redefine the meaning of valid patterns
   - operator-facing docs include the required schema and the write/storage cost of the trigram indexes

### Out

- Rejecting valid full-corpus patterns purely because they are hard to index
- Any SQL pre-filter that can introduce false negatives
- Automatic `CREATE EXTENSION pg_trgm` at runtime
- Replacing Python final matching for exact grep/glob semantics
- Fuzzy ranking or typo-tolerant UX
- Partitioning or sharding work beyond this backend contract

## Native behavior contract

### Backend mode

There is one Postgres-native pattern backend. It requires the pattern-search schema and uses sound pushdown plus authoritative final filtering.

### Case behavior

- `glob()` stays case-sensitive
- `grep()` case behavior continues to follow `case_mode`
- no new collation-dependent semantics are introduced

### Correctness contract

For Postgres `glob()` / `grep()`:

- SQL may return a safe superset
- Python is allowed to do the final exact filtering
- no true match may be dropped by backend pushdown

### Performance contract

For full-corpus Postgres `glob()` / `grep()`:

- the backend should use every sound native narrowing step available
- prefix-, literal-, and trigram-friendly patterns should become materially faster than the current opportunistic path
- hard patterns may still require broader over-selection, but they must remain correct

### Semantics

This story intentionally prefers correctness over strict admission:

- some hard patterns may still be expensive
- that is acceptable if the backend has already applied every sound narrowing step it can
- the product promise is correctness first, acceleration second

## Acceptance criteria

### Backend surface

- [ ] `PostgresFileSystem(engine=engine)` exposes one native pattern backend only.
- [ ] No `pattern_backend="baseline"` / `"trigram"` selector remains in the Postgres design.

### Schema verification

- [ ] `verify_native_search_schema()` passes only when `pg_trgm`, the path prefix index, the path trigram index, and the content trigram index are all present.
- [ ] Missing `pg_trgm` raises a clear `RuntimeError` with a `CREATE EXTENSION` hint.
- [ ] Missing path prefix / path trigram / content trigram indexes each raise clear `RuntimeError`s with actionable `CREATE INDEX` statements.

### Glob

- [ ] `glob()` remains semantically correct for all valid patterns.
- [ ] Prefix-anchored glob patterns use the `path text_pattern_ops` index path when available.
- [ ] Non-prefix glob patterns use `path gin_trgm_ops` narrowing when useful.
- [ ] SQL narrowing may over-select, but final results match exact glob semantics.
- [ ] `glob()` remains case-sensitive.

### Grep

- [ ] `grep()` remains semantically correct for all valid patterns.
- [ ] `fixed_strings=True` uses indexed `LIKE` / `ILIKE`-style narrowing when useful.
- [ ] Regex grep adds literal/trigram/FTS narrowing when sound.
- [ ] `invert_match=True` remains correct.
- [ ] Python remains responsible for final line reconstruction and exact line-oriented matching after SQL narrowing.
- [ ] No SQL pre-filter used by the Postgres backend can introduce false negatives.

### Safety / observability / docs

- [ ] `docs/architecture.md` and `docs/index.md` document the Postgres backend as sound pushdown plus authoritative final filtering.
- [ ] A Postgres integration test runs `EXPLAIN (FORMAT JSON)` for representative supported `glob()` / `grep()` shapes and asserts the expected path/content indexes appear in the plan.
- [ ] Tests cover hard patterns that are only weakly narrowed in SQL and verify they still return the same results as authoritative in-process matching.

## Test plan

### 1. Unit tests

Add unit coverage for:

- glob narrowing classification
- grep literal extraction / narrowing composition
- no-false-negative behavior of SQL pre-filters

### 2. Postgres integration tests

Add Postgres-gated coverage for:

- successful schema verification
- missing `pg_trgm`
- missing path prefix index
- missing path trigram index
- missing content trigram index
- supported prefix glob uses the prefix access path
- supported non-prefix glob uses trigram narrowing when useful
- supported grep uses content trigram narrowing when useful
- hard regex patterns still return correct results
- `invert_match=True` remains correct

### 3. Fixture provisioning

Extend [`tests/conftest.py`](../../../tests/conftest.py) with helpers that:

- install `pg_trgm`
- create the path prefix index
- create the path trigram index
- create the content trigram index

This is deployment/test setup, not runtime request handling.

### 4. Manual smoke

- `uv run pytest --postgres tests/test_postgres_backend.py`
- `uv run pytest --postgres tests/test_postgres_patterns.py`
- `uv run python scripts/postgres_repo_cli_probe.py`
