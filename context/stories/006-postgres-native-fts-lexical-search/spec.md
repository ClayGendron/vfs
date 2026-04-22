# 006 — Postgres lexical search via native FTS (tsvector + GIN + ts_rank_cd)

- **Status:** draft
- **Date:** 2026-04-21
- **Owner:** Clay Gendron
- **Kind:** feature + backend

## Intent

Replace `PostgresFileSystem._lexical_search_impl`'s mixed ranking path with a pure PostgreSQL native full-text search implementation:

- A stored generated `search_tsv tsvector` column plus a partial `GIN` index owns recall.
- A single SQL query ranks and limits results using `ts_rank_cd` with `[0, 1)`-bounded normalization.
- The returned `Entry.score` is the `ts_rank_cd` value — no Python BM25 rerank step.

This is the right shape for standard PostgreSQL deployments: core PostgreSQL ships full-text search and `GIN`, but it does not ship a built-in BM25 lexical rank primitive. We should stop pretending this backend returns BM25 and make the native FTS path honest instead.

Today:

- `PostgresFileSystem._lexical_search_impl` ([`src/vfs/backends/postgres.py`](../../../src/vfs/backends/postgres.py)) runs a native FTS candidate query, hydrates the candidate rows, then reranks them in Python through `vfs.bm25.BM25Scorer` and `DatabaseFileSystem`'s corpus-stat helpers. Two query round-trips, two scoring systems, one result.
- `DatabaseFileSystem._lexical_search_impl` ([`src/vfs/backends/database.py`](../../../src/vfs/backends/database.py)) computes true BM25 in Python. Its full-corpus prefilter path relies on SQL `ILIKE` + term-count sorting, which does not scale.

After this story:

- `PostgresFileSystem` runs one ranked SQL query against `search_tsv` using `ts_rank_cd(..., 1|32)` and returns top-`k` directly.
- No BM25 scorer, no `_LexicalDoc` hydration pass, no corpus-stat fetch, no second round-trip for the full-corpus path.
- `Entry.score` is `ts_rank_cd` bounded to `[0, 1)`. The contract change is documented in public docs.
- Candidate-scoped lexical search (`candidates is not None`) continues to delegate to `DatabaseFileSystem._lexical_search_impl` unchanged. That path takes a small in-memory candidate set (typically produced by vector search) and BM25-ranks it in Python; it is **not** a rerank over native FTS output, and it stays as-is.
- `verify_native_search_schema()` keeps enforcing the stored `search_tsv` column and partial `GIN` index.
- `_grep_impl` and `_glob_impl` are unchanged.
- Public VFS contract, `Entry` / `VFSResult` shapes, candidate filtering, user scoping, and error behavior remain unchanged apart from the documented `score` semantics.

## Why

- **Standard PostgreSQL compatibility.** Core PostgreSQL FTS with a `GIN` index is available on ordinary Postgres installations. No extra search extension is required.
- **Simplicity.** One SQL query, one scoring system, one round-trip. The current hybrid path maintains two scoring models with a partial implementation of each; removing the Python BM25 rerank eliminates a large coupling surface between `PostgresFileSystem` and `DatabaseFileSystem`'s BM25 internals (`_LexicalDoc`, `_tokenize_doc`, `_fetch_corpus_stats`, `_estimate_average_idf`).
- **Honest score semantics.** `ts_rank_cd` is a cover-density score, not BM25. Returning it directly and documenting it is better than returning a BM25 value whose quality is capped by a coarse FTS candidate cut.
- **Scale.** Native FTS with `GIN` is strictly better than `content ILIKE '%term%'` prefiltering as corpora grow.
- **Minimal public-surface change.** Backend swap. Same `lexical_search` signature, same `VFSResult`/`Entry` shape, same user scoping, same error messages for bad input. Only `Entry.score` semantics change, and that is called out.
- **Constitution fit.** Article 4 backend swap.

## Expected touch points

- [`src/vfs/backends/postgres.py`](../../../src/vfs/backends/postgres.py) — rewrite `_lexical_search_impl` full-corpus branch to a single ranked query. Remove `BM25Scorer` / `_LexicalDoc` imports and usage. Remove `LEXICAL_CANDIDATE_LIMIT`, `LEXICAL_CANDIDATE_MULTIPLIER`, `LEXICAL_CANDIDATE_FLOOR`, and `_lexical_candidate_target`.
- [`src/vfs/bm25.py`](../../../src/vfs/bm25.py) and the BM25 helpers in [`src/vfs/backends/database.py`](../../../src/vfs/backends/database.py) — untouched. They still serve `DatabaseFileSystem._lexical_search_impl` and therefore the Postgres candidate-scoped path.
- [`tests/conftest.py`](../../../tests/conftest.py) — provisioning of the generated `search_tsv` column and partial `GIN` index stays. No change expected beyond confirming the DDL matches the index predicate used in the ranking query.
- [`tests/test_postgres_backend.py`](../../../tests/test_postgres_backend.py) — update lexical-search expectations: scores are in `[0, 1)`, ordering matches `ts_rank_cd(..., 1|32)`, no bounded-hydration behavior to assert.
- [`scripts/postgres_repo_cli_probe.py`](../../../scripts/postgres_repo_cli_probe.py) — probe the single-query FTS path; assert the result shape and that scores are bounded.
- [`docs/architecture.md`](../../../docs/architecture.md), [`docs/index.md`](../../../docs/index.md) — describe Postgres lexical search as native FTS via `tsvector` + `GIN` + `ts_rank_cd`, explicitly *not* BM25.

## Scope

### In

1. **Full-corpus lexical search is a single native FTS query.**

   `PostgresFileSystem._lexical_search_impl(query, k, candidates=None, ...)` must:

   - tokenize the incoming query with `tokenize_query(...)`
   - construct an OR tsquery from those terms using `plainto_tsquery('simple', :term)` composed with the tsquery `||` operator (see item 4)
   - run one SQL statement that filters on `search_tsv @@ q`, orders by `ts_rank_cd(search_tsv, q, 1|32) DESC`, and applies `LIMIT :k`
   - project `path`, `kind`, `content`, and the computed score in that one query
   - return `VFSResult(function="lexical_search", entries=[Entry(path, kind, content, score), ...])`

   No second round-trip for hydration. No Python rerank.

2. **Candidate-scoped lexical search is unchanged.**

   When `candidates is not None`, the method continues to delegate to `DatabaseFileSystem._lexical_search_impl(...)`. That path's Python BM25 is not "post-ranking native FTS output"; it ranks an in-memory set (typically from vector search). It stays.

3. **Require a stored `search_tsv` column and a partial `GIN` index.**

   Required DDL (unchanged from the previous spec draft):

   ```sql
   ALTER TABLE vfs_objects
   ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS (
       to_tsvector('simple', coalesce(content, ''))
   ) STORED;

   CREATE INDEX ix_vfs_objects_search_tsv_gin
       ON vfs_objects
       USING GIN (search_tsv)
       WHERE content IS NOT NULL
         AND deleted_at IS NULL
         AND kind != 'version';
   ```

   Notes:

   - Generated columns can use only immutable functions. Use the two-argument `to_tsvector('simple', ...)` form with an explicit config literal; do not rely on the session's default text-search configuration.
   - `'simple'` is deliberate. It lowercases and splits on non-word characters; it does **not** stem or drop stopwords. This is the right fit for a corpus that mixes code, paths, and natural language. `'english'` would stem identifiers like `tests`/`testing` together and blur code-search intent.
   - The partial predicate should stay aligned with the runtime `WHERE`. PostgreSQL can use a partial index only when the query predicate mathematically implies the index predicate; in practice, keeping the live-search predicates textually aligned is the safest way to preserve index usage.
   - A stored generated column is preferred over recomputing `to_tsvector(...)` in every query because it keeps the indexed search document explicit and lets the ranking query filter and rank against the same `search_tsv` value.

4. **Safe, injection-free OR tsquery construction.**

   The ranking query constructs its tsquery from tokens via per-term `plainto_tsquery(...)` folded with the tsquery `||` (OR) operator. Canonical shape, with one bound parameter per token:

   ```sql
   WITH query AS (
       SELECT (
           plainto_tsquery('simple', :t0)
           || plainto_tsquery('simple', :t1)
           || plainto_tsquery('simple', :t2)
       ) AS q
   )
   SELECT
       o.path,
       o.kind,
       o.content,
       ts_rank_cd(o.search_tsv, query.q, 1|32) AS score
   FROM {table} AS o
   CROSS JOIN query
   WHERE o.kind != 'version'
     AND o.deleted_at IS NULL
     AND o.content IS NOT NULL
     AND o.search_tsv @@ query.q
     {user_scope_clause}
   ORDER BY score DESC, o.path
   LIMIT :k
   ```

   Required properties of the tsquery builder:

   - tokens are bound as parameters, never interpolated; `plainto_tsquery` sanitizes punctuation and operators
   - tokens are deduplicated before binding (`dict.fromkeys` on the `tokenize_query` output, as today)
   - empty and whitespace-only queries continue to return the existing error result
   - a tokenization result that yields zero terms continues to return the existing error result
   - single-term queries produce a bare `plainto_tsquery('simple', :t0)` expression (no dangling `||`)

   The current `_build_tsquery` / `_quote_tsquery_term` helpers that manually build a `to_tsquery` string may be removed for the lexical path. The identical helper used by `_grep_impl` (literal-term tsquery for the FTS pre-filter) stays — that path has a different risk profile and is not in scope here.

5. **Ranking uses `ts_rank_cd` with normalization flags `1|32`.**

   Bit semantics (per the Postgres docs):

   | bit | effect |
   | --- | --- |
   | 1 | divide by `1 + log(document length)` — dampens length bias |
   | 2 | divide by document length — too aggressive for short snippets |
   | 4 | divide by mean harmonic distance between extents (cd only) — compounds oddly with cover density |
   | 8 | divide by unique word count |
   | 16 | divide by `1 + log(unique words)` |
   | 32 | divide by `rank + 1` — bounds output to `[0, 1)` |

   `1|32` is the recommended combination for vfs's mixed code/prose corpus: gentle length dampening via log, plus a stable bounded score suitable for a public API response. This replaces the previous hybrid spec's `2|8|32`.

6. **Scaling posture: single-query is the MVP; two-stage is a documented follow-up.**

   A straight `ORDER BY ts_rank_cd(...) DESC LIMIT k` is the right default MVP. `GIN` accelerates `@@`, but ranking still happens over the matching rows, so very broad queries can degrade as match counts grow.

   This story does **not** implement a two-stage candidate-cap CTE. If future profiling shows broad-match queries spending too much time in ranking, the mitigation is a CTE that caps the candidate set before ranking:

   ```sql
   WITH candidates AS (
       SELECT path, kind, content, search_tsv
       FROM {table}
       WHERE <partial preds> AND search_tsv @@ q
       LIMIT :candidate_cap
   )
   SELECT path, kind, content, ts_rank_cd(search_tsv, q, 1|32) AS score
   FROM candidates ORDER BY score DESC LIMIT :k
   ```

   That trades off global top-`k` correctness for earlier termination on broad match sets. Capture it as a non-goal here and implement it only if profiling shows the single-query plan is no longer adequate.

7. **Schema verification stays as the fail-fast entry point.**

   `verify_native_search_schema()` must continue to enforce:

   - the target table exists
   - a `content` column exists
   - a `search_tsv` column exists, is `tsvector`, is `GENERATED ... STORED`, and its generation expression mentions `to_tsvector`, `content`, and `FULLTEXT_CONFIG` (`'simple'`)
   - a `GIN` index exists on `search_tsv`
   - at least one such index has the live-search partial predicate: `content IS NOT NULL AND deleted_at IS NULL AND kind <> 'version'`

   Failure mode is unchanged: raise `RuntimeError` with the `_fulltext_schema_hint()` DDL example. No silent fallback to `DatabaseFileSystem`'s `ILIKE` path.

8. **User scoping.**

   User scoping continues to ride on the existing path-prefix clause (`o.path LIKE :user_scope ESCAPE '\\'` with `:user_scope = f"/{user_id}/%"`). No new tenant column, no new scope model. `_require_user_id`, `_unscope_result`, and the candidate-scoping helpers are used identically to today.

9. **Grep and glob are out of scope.**

   `_grep_impl` and `_glob_impl` keep their current Postgres-native implementations. `_grep_impl` still uses a `to_tsquery` pre-filter over literal terms for the regex path — that helper is unrelated to this rewrite and is not touched.

10. **Probe script and docs.**

    - [`scripts/postgres_repo_cli_probe.py`](../../../scripts/postgres_repo_cli_probe.py) — probe lexical search, assert non-empty top-`k` on a known-match query, assert each returned score is in `[0, 1)`.
    - [`docs/architecture.md`](../../../docs/architecture.md) — Postgres lexical search runs as a single `tsvector` + `GIN` + `ts_rank_cd` query; document the required schema and the score semantics.
    - [`docs/index.md`](../../../docs/index.md) — remove any language implying Postgres returns BM25 scores. MSSQL and Postgres are no longer architecturally identical here: MSSQL produces server-side BM25-style ranks via `CONTAINSTABLE`; Postgres produces native `ts_rank_cd` values. Call that out plainly.

### Out

- **Python BM25 post-ranking of Postgres FTS output.** Explicitly removed.
- **Server-side BM25 extensions.** No `pg_textsearch`. No `pg_search`.
- **SQL-only BM25.** No sidecar inverted-index tables (`doc_terms`, `term_stats`, `corpus_stats`) in this story.
- **Two-stage candidate-cap CTE.** Documented as a future mitigation; not implemented now.
- **RUM index.** Not assumed by the standard-Postgres baseline for this story.
- **Hybrid lexical + vector search redesign.**
- **Typo / fuzzy matching (`pg_trgm`).**
- **Phrase / field-weighted search as new public contract.**
- **Changes to grep or glob behavior.**

## Native behavior contract

### Score semantics

`Entry.score` is `ts_rank_cd(search_tsv, q, 1|32)`. The value is in `[0, 1)` by construction and is a cover-density score, not BM25.

This is a deliberate behavior change from the previous hybrid path. The change must be documented in `docs/architecture.md` and `docs/index.md`. Callers that compared Postgres and MSSQL lexical scores against each other were already comparing incomparable values; after this story they are incomparable in a more obvious way.

### Result shape

Unchanged: `VFSResult(function="lexical_search", entries=[Entry(path, kind, content, score), ...])`, ordered by descending score with a stable tiebreaker on `path`.

### Query behavior

- Multi-term queries preserve any-term recall semantics via `plainto_tsquery(:ti) || plainto_tsquery(:tj) || ...`.
- Empty / whitespace / punctuation-only input returns the same error shape the base path returns today.
- Tokenization continues to use `tokenize_query(...)`.

### User scoping

Unchanged. Path-prefix `LIKE /{user_id}/%` on the ranking query; `_unscope_result` on the way out.

### Failure mode

If `PostgresFileSystem` is selected against a database missing the required `search_tsv` column or partial `GIN` index, `verify_native_search_schema()` raises `RuntimeError` with an actionable DDL hint. No silent fallback to `ILIKE` prefiltering.

### Write-path impact

None. The generated column and its `GIN` index are maintained automatically by Postgres. No application-side write logic added.

## Acceptance criteria

### Backend surface

- [ ] `PostgresFileSystem(engine=engine, model=model)` full-corpus `lexical_search(...)` runs a single ranked SQL query against `search_tsv` and returns top-`k` directly with `ts_rank_cd` scores.
- [ ] `lexical_search(..., candidates=some_result)` still delegates to `DatabaseFileSystem._lexical_search_impl(...)` unchanged.
- [ ] No BM25 scorer, corpus-stat fetch, `_LexicalDoc` hydration, or second round-trip exists on the full-corpus Postgres path.
- [ ] `_grep_impl` and `_glob_impl` behavior is unchanged.
- [ ] `BM25Scorer` and `_LexicalDoc` are no longer imported in `src/vfs/backends/postgres.py`. `LEXICAL_CANDIDATE_LIMIT`, `LEXICAL_CANDIDATE_MULTIPLIER`, `LEXICAL_CANDIDATE_FLOOR`, and `_lexical_candidate_target` are removed.

### Schema verification

- [ ] `verify_native_search_schema()` passes against a database with the stored `search_tsv tsvector` column and a partial `GIN` index whose predicate matches the runtime WHERE clause.
- [ ] Missing `search_tsv` column raises `RuntimeError` with an `ALTER TABLE ... ADD COLUMN ... GENERATED ALWAYS AS ...` hint.
- [ ] `search_tsv` present but not `tsvector` raises `RuntimeError` with the hint.
- [ ] `search_tsv` present but not `GENERATED ... STORED` with the expected expression raises `RuntimeError` with the hint.
- [ ] Missing `GIN` index raises `RuntimeError` with the expected `CREATE INDEX ... USING GIN ...` statement.
- [ ] `GIN` index present without the expected partial predicate raises `RuntimeError`; no warn-and-continue.

### Lexical search

- [ ] `lexical_search(query)` under `PostgresFileSystem` returns `VFSResult(function="lexical_search", entries=[Entry(path, kind, content, score)])` with the same shape as before.
- [ ] Multi-term queries preserve any-term recall semantics; constructing the tsquery must use `||` (OR) across per-term `plainto_tsquery(...)` calls, never AND.
- [ ] Single-term queries produce a bare `plainto_tsquery('simple', :t0)` expression.
- [ ] Every returned `Entry.score` is in `[0, 1)`.
- [ ] Result ordering matches `ts_rank_cd(..., 1|32) DESC` with `path ASC` tiebreaker.
- [ ] The ranking SQL keeps the live-search predicates in a planner-recognizable form (`content IS NOT NULL`, `deleted_at IS NULL`, `kind != 'version'` / `<> 'version'`) so the planner can use the partial `GIN` index.
- [ ] User scoping (`/{user_id}/%`) works identically to the previous implementation.
- [ ] Empty / whitespace / punctuation-only queries preserve the current error behavior.
- [ ] Tokens containing tsquery metacharacters (`&`, `|`, `!`, `<`, `>`, `:`, `'`, backslash) are handled safely because they pass through `plainto_tsquery` bound parameters rather than hand-quoting.

### Scaling / performance contract

- [ ] The full-corpus lexical path uses the `search_tsv` `GIN` index (verifiable via `EXPLAIN`), not a table scan over `content ILIKE '%term%'`.
- [ ] Exactly one round-trip is issued per full-corpus `lexical_search` call.
- [ ] Candidate-scoped lexical search performs no extra native Postgres query and continues to use the base Python BM25 path directly.

### Tooling / docs

- [ ] `tests/conftest.py --postgres` still provisions the generated `search_tsv` column and partial `GIN` index.
- [ ] Postgres lexical-search tests cover: bounded score range, `ts_rank_cd` ordering, any-term recall for multi-term input, user scoping, token-with-metacharacter safety, and the error shape on empty/whitespace queries.
- [ ] `scripts/postgres_repo_cli_probe.py` exercises the single-query FTS path and asserts score bounds.
- [ ] `docs/architecture.md` documents the single-query native FTS design and required schema.
- [ ] `docs/index.md` describes Postgres lexical search as native FTS with `ts_rank_cd` scores and states explicitly that it is not BM25.

### Production readiness

- [ ] `docs/architecture.md` includes the schema-rollout runbook (ADD COLUMN, `CREATE INDEX CONCURRENTLY`, `ANALYZE`) for adding `search_tsv` to a live table.
- [ ] An integration test in `tests/test_postgres_backend.py` runs `EXPLAIN (FORMAT JSON)` on the ranking query and asserts `ix_vfs_objects_search_tsv_gin` (or a `Bitmap Index Scan` / `Index Scan` over `search_tsv`) appears in the plan.
- [ ] `_lexical_search_impl` emits a structured debug log per invocation with term count, returned row count, and query duration; tagged to distinguish the native-FTS path from the candidate-delegated path.
- [ ] `PostgresFileSystem.LEXICAL_MAX_TERMS` caps the tokenized query at 64 terms before binding; truncation emits a debug log and is non-fatal.
- [ ] Release notes announce the `Entry.score` semantic change (`ts_rank_cd` in `[0, 1)`, not BM25) so downstream consumers are warned.
## Production deployment

These items are required for the story to land production-ready, not just merge-ready.

### Schema rollout on a live table

Adding the generated column and GIN index to an existing Postgres deployment should be treated as an explicit operational rollout, not hidden inside application startup. The documented runbook is:

```sql
-- 1. Add the generated column. Adding a STORED generated column can be
--    disruptive on a large live table because PostgreSQL must materialize
--    the stored value for existing rows. Plan a maintenance window or
--    low-write period appropriate to the target version and table size.
ALTER TABLE vfs_objects
ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(content, ''))
) STORED;

-- 2. Build the GIN index without blocking writes.
CREATE INDEX CONCURRENTLY ix_vfs_objects_search_tsv_gin
    ON vfs_objects USING GIN (search_tsv)
    WHERE content IS NOT NULL
      AND deleted_at IS NULL
      AND kind != 'version';

-- 3. Refresh planner stats so the partial GIN is actually chosen.
ANALYZE vfs_objects;
```

`tests/conftest.py` uses `CREATE INDEX IF NOT EXISTS` (no `CONCURRENTLY`) because the fixture table is empty at creation time. Production callers must use the `CONCURRENTLY` form. Call this out in [`docs/architecture.md`](../../../docs/architecture.md).

### `EXPLAIN`-based index-use test

Add a Postgres-integration test that runs `EXPLAIN (FORMAT JSON)` against the lexical ranking SQL with a representative query and asserts a `Bitmap Index Scan` / `Index Scan` over `search_tsv` appears in the plan. This catches two silent regressions:

- the query WHERE drops one of the partial-index predicates and the planner falls back to a seq scan
- someone edits the DDL in `conftest.py` or the runtime SQL and the predicates drift out of sync

Failure should print the offending plan body so regressions are obvious.

### Observability

The single-query path must emit the signals needed to decide when the two-stage candidate-cap CTE follow-up is worth doing. Minimum:

- debug-level log line per invocation: term count, returned row count, query duration
- path tag distinguishing `native_fts` (full-corpus path) from `candidate_delegated` (super call)

Use whatever logging surface the rest of the backend already uses; do not introduce a new metrics dependency. If no metrics surface exists yet, a structured log line is sufficient — production readiness here means the signal exists and is parseable, not that it is wired into a dashboard.

### Input bounds

Cap the number of terms that reach the tsquery builder. `tokenize_query(...)` already bounds token length, but does not bound count. A caller passing thousands of tokens produces an enormous `plainto_tsquery(...) || ...` expression and wastes planner and executor time.

Required:

- introduce `PostgresFileSystem.LEXICAL_MAX_TERMS = 64`
- truncate the deduplicated token list to that cap before binding parameters
- emit a debug log when truncation fires

Do not error on truncation — any-term recall degrades gracefully as terms drop, and callers that exceed the cap are almost always machine-generated queries where recall-on-all-terms was never the intent.

### Rollout and rollback

Rollout:

- land the code change
- run the schema runbook against each target database
- announce the `Entry.score` semantic change in release notes so any downstream consumer comparing Postgres scores to BM25-scale values is notified before the change ships

Rollback:

- the previous hybrid implementation is recoverable from git history; there is no data migration to reverse
- the `search_tsv` column and GIN index remain valid for the old code (which also queries `search_tsv`), so a code-only revert is sufficient
- no feature flag is introduced; the change is small and the project's [no-migration-scripts](../../../../.claude/projects/-Users-claygendron-Git-Repos-grover/memory/feedback_no_migration_scripts.md) posture rules out parallel-path gating

Suggested release-note line: "Postgres `lexical_search` now returns `ts_rank_cd` scores in `[0, 1)` instead of BM25 scores. Cross-backend score comparison was never well-defined; it is now also numerically distinct."

## Non-goals / follow-up candidates

Not in this story; tracked for future:

- Two-stage candidate-cap CTE (`WITH candidates AS (... LIMIT :cap)`) once measured broad-match queries show the single-query plan's ranking cost is material.
- Persisted lexical term-stat tables for true BM25 at scale on Postgres (would require the sidecar inverted-index design that is explicitly out of scope).
- Field-weighted ranking (`setweight` on path vs. content tsvectors).
- Typo-tolerant retrieval via `pg_trgm`.
- Phrase / proximity search as a new public contract.
- Shared "common lexical backend abstraction" across MSSQL and Postgres — the backends are now architecturally distinct on the score dimension (MSSQL: server-side BM25-ish via `CONTAINSTABLE`; Postgres: `ts_rank_cd`), and forcing a shared abstraction would paper over that.
