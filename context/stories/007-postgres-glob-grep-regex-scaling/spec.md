# 007 — Postgres glob / grep / regex scaling

- **Status:** draft
- **Date:** 2026-04-20
- **Owner:** Clay Gendron
- **Kind:** feature + backend

## Intent

Harden `PostgresFileSystem`'s glob / grep / regex paths for large Postgres corpora by making the pattern-search schema contract explicit, routing simple cases through cheaper operators, and bounding pathological regex execution.

Today:

- `PostgresFileSystem._glob_impl` uses `LIKE` as a coarse pre-filter and `~` as the authoritative path match.
- `PostgresFileSystem._grep_impl` pushes some regex narrowing into Postgres and optionally uses native FTS for token-like literal pre-filtering, but it still depends heavily on general regex execution over `content`.
- `verify_native_search_schema()` validates full-text and vector artifacts, but it does not validate any path-pattern or trigram indexes.
- The resulting performance story is opportunistic. Prefix-heavy path queries can be fine, but behavior depends on locale, planner choices, and the specific regex shape. Untrusted regex also has no backend-level timeout guard.

After this story:

- `PostgresFileSystem` supports a `pattern_backend` selector with values `"baseline"` and `"trigram"` (default `"baseline"` for backward compatibility).
- When `pattern_backend="trigram"`, `verify_native_search_schema()` fail-fast-validates the pattern-search artifacts needed for scalable glob / grep / regex execution.
- `glob()` keeps the same user-visible semantics, but it gains a predictable indexed path for prefix-heavy patterns and a second indexed path for non-prefix path regex/glob cases.
- `grep()` keeps the same user-visible semantics, but it routes fixed-string and safe literal cases through cheaper row-level operators before any Python line reconstruction.
- Regex execution in the database runs under a local timeout guard so untrusted patterns cannot tie up the backend indefinitely.
- Public VFS result shapes, case behavior, invert-match semantics, user scoping, candidate filtering, and Python-authoritative line grouping remain unchanged.

## Why

- **Scale.** PostgreSQL's best-practice access paths differ by query shape: B-tree for prefix tests, trigram indexes for contains / regex-like search, and raw regex only when necessary.
- **Planner predictability.** The current backend has the right SQL shape in places, but it does not declare the schema artifacts that make those shapes reliably fast across deployments and collations.
- **Safety.** PostgreSQL explicitly warns that regex and `SIMILAR TO` patterns can consume arbitrary time and memory. Grover should not run unbounded regex against shared databases.
- **Explicit rollout.** As with pgvector and `pg_textsearch`, extension-backed acceleration should be deployment-managed and opt-in, not silently assumed.
- **Constitution fit.** Article 4 backend swap. The backend gets stricter and faster; the public VFS API stays the same.

## Expected touch points

- Update [`src/vfs/backends/postgres.py`](../../../src/vfs/backends/postgres.py)
- Update shared pattern helpers in [`src/vfs/backends/database.py`](../../../src/vfs/backends/database.py) only where Postgres needs a common seam
- Extend [`tests/conftest.py`](../../../tests/conftest.py) with trigram/pattern provisioning helpers
- Extend [`tests/test_postgres_backend.py`](../../../tests/test_postgres_backend.py) or add `tests/test_postgres_patterns.py`
- Update [`scripts/postgres_repo_cli_probe.py`](../../../scripts/postgres_repo_cli_probe.py) if it exercises grep / glob under the Postgres-native backend
- Update [`docs/architecture.md`](../../../docs/architecture.md) and [`docs/index.md`](../../../docs/index.md)

## Scope

### In

1. **Add a `pattern_backend` selector to `PostgresFileSystem`.**

   ```python
   from typing import Literal

   PatternBackend = Literal["baseline", "trigram"]

   class PostgresFileSystem(DatabaseFileSystem):
       def __init__(
           self,
           *,
           pattern_backend: PatternBackend = "baseline",
           regex_statement_timeout_ms: int | None = 2000,
           **kwargs,
       ) -> None:
           super().__init__(**kwargs)
           self._pattern_backend = pattern_backend
           self._regex_statement_timeout_ms = regex_statement_timeout_ms
   ```

   Notes:

   - `"baseline"` preserves current behavior and current schema requirements.
   - `"trigram"` enables the scaled path described by this story and requires explicit schema provisioning.
   - `regex_statement_timeout_ms=None` disables the local timeout guard, but the default should be safe for shared deployments.
   - Composes with `bm25_backend` from story 006 on the same `PostgresFileSystem.__init__`; whichever story lands first, the other must add its kwarg alongside rather than replace.

2. **Extend `verify_native_search_schema()` to validate the trigram profile.**

   When `pattern_backend == "trigram"`:

   - verify the `pg_trgm` extension is installed
   - verify a `text_pattern_ops` B-tree index exists for `path` so left-anchored `LIKE '/prefix/%'` remains indexable across collations
   - verify a trigram index exists for `path` so non-prefix glob / regex on paths can use `pg_trgm`
   - verify a partial trigram index exists for live file content so fixed-string / regex grep pre-filters can use `pg_trgm`
   - raise clear `RuntimeError`s with actionable `CREATE EXTENSION` / `CREATE INDEX` statements if any requirement is missing

   When `pattern_backend == "baseline"`:

   - existing verification behavior is unchanged
   - missing `pg_trgm` does not block the baseline backend

3. **Define the required scaled pattern-search schema.**

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

   - The existing unique B-tree on `path` remains useful for equality lookups. The `text_pattern_ops` index exists specifically for predictable prefix matching.
   - GIN is the default trigram index family in this story because the workload is read-heavy and does not need ordered similarity retrieval.
   - Partial predicates should mirror the runtime filters so the planner can use the indexes directly.

4. **Keep `glob()` semantically identical, but make the fast path explicit.**

   Required behavior:

   - preserve current case-sensitive glob semantics
   - preserve candidate filtering, `paths`, `ext`, `max_count`, user scoping, and file/directory visibility behavior
   - continue using literal-prefix decomposition as the first optimization
   - under the trigram profile, route prefix-heavy patterns through the path-pattern index and allow non-prefix path regex/glob cases to use the path trigram index
   - keep the regex/glob matcher authoritative after any SQL pre-filter; no lossy glob approximation is allowed

5. **Route `grep()` through the cheapest sound row-level operator before Python line reconstruction.**

   Required behavior:

   - `fixed_strings=True` uses `LIKE` / `ILIKE`-style row pre-filters on `content` before Python line matching
   - safe literal extraction remains allowed as a complementary pre-filter
   - token-like literals may continue to use the native FTS pre-filter when that is sound
   - `invert_match=True` remains Python-authoritative; do not replace it with row-level SQL negation
   - line grouping, context windows, counts, and final result shaping remain in Python

   The existing FTS literal-term pre-filter in `_grep_impl` already guards against unsoundness from negative lookarounds (via `_extract_literal_terms`) and the Postgres regex translator already respects escape pairs and char-class boundaries (via `_python_regex_to_postgres`). Trigram pre-filters composed by this story must compose with — not replace — those guards; any trigram narrowing must be intersectable with the existing sound pre-filter without widening the false-negative surface.

6. **Only use whole-row regex pre-filters when they are safe for grep's line semantics.**

   This story does **not** promise that every regex gets a trigram-accelerated SQL pre-filter.

   Required behavior:

   - if pattern analysis can prove a row-level pre-filter cannot introduce false negatives relative to line-oriented grep semantics, it may be used
   - if that proof is not available, skip the row-level regex pre-filter and fall back to the safer baseline path
   - correctness wins over speed for anchored, multiline-sensitive, or otherwise tricky patterns

7. **Bound database regex execution with a local timeout.**

   Required behavior:

   - regex-backed SQL issued by `_grep_impl` and regex-backed glob narrowing run under `SET LOCAL statement_timeout` or an equivalent transaction-local mechanism
   - timeout failures surface as clear, user-actionable errors instead of hanging the request
   - the timeout guard must not leak outside the current transaction / session scope

8. **Document the scaled-pattern rollout clearly.**

   Minimum:

   - [`docs/architecture.md`](../../../docs/architecture.md) explains the `pattern_backend` selector, the required indexes, and why prefix and non-prefix path search use different index families
   - [`docs/index.md`](../../../docs/index.md) distinguishes baseline native regex support from the trigram-accelerated profile
   - operator-facing docs call out the write/storage cost of the extra trigram indexes

### Out

- Changing grep or glob semantics
- Adding fuzzy ranking, similarity search UX, or user-facing typo tolerance
- Guaranteeing that every regex is index-accelerated
- Replacing Python-authoritative line reconstruction for grep
- Automatic `CREATE EXTENSION pg_trgm` at runtime
- Partitioning, sharding, or regex workload isolation beyond the local timeout guard
- Collation redesign or a broader case-folding strategy outside the existing grep flags

## Native behavior contract

### Rollout mode

`pattern_backend="baseline"` remains the compatibility path. `pattern_backend="trigram"` is the explicit scaled profile. There is no silent auto-upgrade based on extension presence.

### Case behavior

- `glob()` stays case-sensitive
- `grep()` case behavior continues to be controlled by `case_mode`
- no nondeterministic-collation dependency is introduced by this story

### Safety

Regex timeout is a backend safety feature, not a semantic feature. A timed-out query should fail clearly; it must not return partial matches or silently retry without the timeout guard.

### Write-path cost

The trigram profile adds real database-side cost:

- more disk for `path` and `content` trigram indexes
- more write amplification on `content` updates
- more maintenance overhead for autovacuum / index cleanup

That cost is intentional. The scaled profile is for deployments that need it.

## Acceptance criteria

### Backend surface

- [ ] `PostgresFileSystem(engine=engine, pattern_backend="baseline")` preserves existing behavior.
- [ ] `PostgresFileSystem(engine=engine, pattern_backend="trigram")` constructs without error.
- [ ] `regex_statement_timeout_ms` can be configured or disabled per backend instance.

### Schema verification

- [ ] `verify_native_search_schema()` passes against a Postgres database with `pg_trgm` installed and the required pattern indexes present when `pattern_backend="trigram"`.
- [ ] Missing `pg_trgm` produces a clear `RuntimeError` with a `CREATE EXTENSION` hint.
- [ ] Missing path prefix / path trigram / content trigram indexes each produce clear `RuntimeError`s with actionable `CREATE INDEX` statements.
- [ ] `pattern_backend="baseline"` does not require `pg_trgm`.

### Glob

- [ ] `glob()` results are identical between `pattern_backend="baseline"` and `pattern_backend="trigram"` for the same inputs.
- [ ] Prefix-heavy glob patterns continue to use SQL prefix narrowing before authoritative regex matching.
- [ ] Non-prefix path glob patterns remain correct under the trigram profile.
- [ ] `glob()` remains case-sensitive.

### Grep

- [ ] `grep()` results are identical between `pattern_backend="baseline"` and `pattern_backend="trigram"` for the same inputs across `case_mode`, `fixed_strings`, `word_regexp`, `invert_match`, `output_mode`, `max_count`, `paths`, `ext`, `ext_not`, `globs`, `globs_not`, and user scoping.
- [ ] `fixed_strings=True` uses a cheaper row-level pre-filter than general regex execution.
- [ ] `invert_match=True` remains Python-authoritative.
- [ ] Regex patterns that are unsafe to pre-filter at row level fall back to the safer baseline path instead of risking false negatives.

### Safety / docs

- [ ] Pathological regex can time out with a clear error when the timeout guard is enabled.
- [ ] The timeout guard is transaction-local and does not leak to unrelated queries.
- [ ] `docs/architecture.md` and `docs/index.md` document the scaled pattern-search profile and its operational cost.

## Test plan

### 1. Pure unit tests

Add unit coverage for backend-local helpers such as:

- pattern-backend selector validation
- timeout configuration handling
- safe vs unsafe whole-row regex pre-filter classification
- any path-index / trigram index detection helper split out for verification

### 2. Postgres integration tests

Add Postgres-gated coverage for:

- successful trigram-profile schema verification
- missing `pg_trgm`
- missing path pattern index
- missing path trigram index
- missing content trigram index
- glob parity between baseline and trigram profiles
- grep parity between baseline and trigram profiles
- fixed-string grep using the cheaper row-level pre-filter
- regex timeout behavior
- timeout disabled behavior

### 3. Fixture provisioning

Extend [`tests/conftest.py`](../../../tests/conftest.py) with trigram provisioning helpers that:

- install `pg_trgm`
- create the path prefix index
- create the path trigram index
- create the content trigram index

This is test/development infrastructure, not request-time runtime behavior.

### 4. Manual smoke

Reviewer smoke checks:

- `uv run pytest --postgres tests/test_postgres_backend.py`
- `uv run pytest --postgres tests/test_postgres_patterns.py`
- `uv run python scripts/postgres_repo_cli_probe.py`

## References

- Existing Postgres backend: [`src/vfs/backends/postgres.py`](../../../src/vfs/backends/postgres.py)
- Shared pattern semantics: [`src/vfs/backends/database.py`](../../../src/vfs/backends/database.py)
- PostgreSQL pattern matching docs: [postgresql.org/docs/current/functions-matching.html](https://www.postgresql.org/docs/current/functions-matching.html)
- PostgreSQL trigram docs: [postgresql.org/docs/current/pgtrgm.html](https://www.postgresql.org/docs/current/pgtrgm.html)
- PostgreSQL operator-class docs: [postgresql.org/docs/current/indexes-opclass.html](https://www.postgresql.org/docs/current/indexes-opclass.html)
