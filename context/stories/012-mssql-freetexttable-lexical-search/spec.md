# 012 — MSSQL lexical search via FREETEXTTABLE with single-round-trip hydration

- **Status:** draft
- **Date:** 2026-04-23
- **Owner:** Clay Gendron
- **Kind:** feature + backend

## Intent

Replace `MSSQLFileSystem._lexical_search_impl`'s full-corpus `CONTAINSTABLE` path with SQL Server's native `FREETEXTTABLE`, and fold the separate content-hydration query into the ranking query itself.

After this story:

- The ranking ranker on MSSQL is BM25 (OKAPI: `k1=1.2, b=0.75, k3=8.0`) via `FREETEXTTABLE`, not the `CONTAINSTABLE` formula (`HitCount * 16 * log2((2+IndexedRows)/KeyRows) / MaxOccurrence`).
- Tokenization, stemming (inflectional forms), stoplist handling, and thesaurus expansion happen inside SQL Server. The Python OR-expression builder (`_quote_contains_term(...)` usage for the lexical path) is gone.
- Each full-corpus `lexical_search` call is **one** round trip: rank and content are returned in the same result set.
- Results are deterministic for the same query and committed database state — a stable tie-breaker on `o.id` is added to defeat rank collisions that currently make same-query results reorder across calls.
- The `candidates is not None` delegation to `DatabaseFileSystem._lexical_search_impl` is unchanged.
- `_grep_impl`'s `CONTAINSTABLE` pre-filter (literal AND-of-terms) is unchanged — that path wants precision, not BM25 ranking, and it keeps `_quote_contains_term(...)`.

Today (`src/vfs/backends/mssql.py:781`):

- `tokenize_query(query)` + per-term `_quote_contains_term(...)` builds a `"t1" OR "t2" OR …` CONTAINS expression.
- Query 1: `CONTAINSTABLE({table}, content, :expr, :top_n)` joined back for `path`, `kind`, `RANK`, sorted by `RANK DESC`, `TOP (:k)`.
- Query 2: `SELECT path, content FROM {table} WHERE path IN (:p0..:pN)` to hydrate content for the ~15 winners.
- `content_by_path` is assembled in Python and zipped back into `Entry` rows.

After this story:

- One SQL statement. `FREETEXTTABLE({table}, content, :q, :top_n)` joined back, projecting `o.path`, `o.kind`, `o.content`, `ct.[RANK] AS score`, ordered by `score DESC, o.id`, `TOP (:k)`.
- `Entry.score` is the `FREETEXTTABLE` BM25-style rank. Its numeric scale differs from the previous `CONTAINSTABLE` rank.

## Why

- **Better ranker for the use case.** `CONTAINSTABLE` ranks with a hit-count formula whose length normalization buckets document length into ~32 ranges; a 50-word doc and a 100-word doc get the same length adjustment. `FREETEXTTABLE` ranks with BM25, which is the textbook choice for natural-language queries over mixed-length content (code + markdown + docs). Wrapping CONTAINSTABLE terms in `FORMSOF(INFLECTIONAL, ...)` improves recall only; the underlying ranker does not change.
- **Free tokenization / stemming / stoplist.** The current Python OR builder bypasses SQL Server's query-side analyzer. `FREETEXTTABLE` runs the same linguistic pipeline already used to populate the index, which removes a class of skew between index and query tokenization.
- **One round trip instead of two.** The current second query re-reads `content` for the same ~15 rows the ranking query already identified. There is no content-size tradeoff — both queries hit the same rows. Folding them saves a full client↔server hop per call (~1–10 ms LAN, more over WAN).
- **Deterministic ordering.** `FREETEXTTABLE` rank collisions are common; without a tie-breaker, the same query returns the same set in a non-stable order across calls, which defeats higher-level caching and makes tests flaky.
- **Backend coherence.** Story 006 made Postgres lexical search a single native FTS query. MSSQL is the remaining backend with a two-query shape; this closes the gap.

References (validated):

- [Microsoft Learn — Limit Search Results with RANK (ver17)](https://learn.microsoft.com/en-us/sql/relational-databases/search/limit-search-results-with-rank?view=sql-server-ver17) — `CONTAINSTABLE` vs. `FREETEXTTABLE` ranker formulas and BM25 constants.
- [Microsoft Learn — Improve the Performance of Full-Text Queries](https://learn.microsoft.com/en-us/sql/relational-databases/search/improve-the-performance-of-full-text-queries?view=sql-server-ver16).
- [Azure SQL Dev Blog — Hybrid Search and RRF Re-Ranking](https://devblogs.microsoft.com/azure-sql/enhancing-search-capabilities-in-sql-server-and-azure-sql-with-hybrid-search-and-rrf-re-ranking/) — context for the future hybrid upgrade path.
- [Brent Ozar — Why Full Text's CONTAINS Queries Are So Slow](https://www.brentozar.com/archive/2020/11/why-full-texts-contains-queries-are-so-slow/).

## Target environment (verified)

- Azure SQL Database, Mar 2026 build, engine edition 5.
- Full-text catalog `vfs_ftcat` on `content`, 364,829 rows indexed, `CHANGE_TRACKING = AUTO`, population idle.
- Native `VECTOR` type available (relevant only to the deferred hybrid upgrade path).

## Expected touch points

- [`src/vfs/backends/mssql.py`](../../../src/vfs/backends/mssql.py)
  - `_lexical_search_impl` full-corpus branch rewritten as a single `FREETEXTTABLE` statement that returns `path`, `kind`, `content`, `score` and is ordered with an `o.id` tie-breaker.
  - `tokenize_query(...)` and the ranking-side OR construction via `_quote_contains_term(...)` are removed from the lexical path.
  - `_quote_contains_term` remains in the file; `_grep_impl` (around mssql.py:1042) still uses it for its `CONTAINSTABLE` pre-filter.
  - `FULLTEXT_TOP_N` is retained unchanged (same `top_n_by_rank` semantics apply to `FREETEXTTABLE`).
- [`tests/test_mssql_backend.py`](../../../tests/test_mssql_backend.py) (or the equivalent MSSQL-facing lexical tests) — update score-scale expectations, add a determinism assertion (same query twice returns the same ordered result set), add a ranker-behavior assertion that exercises an inflectional match (e.g. `plurals` matches `plural`) that the previous CONTAINSTABLE OR-of-literals path would miss.
- [`tests/conftest.py`](../../../tests/conftest.py) MSSQL fixture — no DDL change expected; the existing full-text index on `content` already covers `FREETEXTTABLE`.
- [`docs/architecture.md`](../../../docs/architecture.md), [`docs/index.md`](../../../docs/index.md) — describe MSSQL lexical search as native `FREETEXTTABLE` BM25 via the `vfs_ftcat` full-text index. Call out that `Entry.score` is `FREETEXTTABLE`'s rank (BM25-derived, unbounded positive integer scale) — still not directly comparable to Postgres `ts_rank_cd`.
- Release notes — announce the score-scale change.

## Scope

### In

1. **Full-corpus lexical search is one `FREETEXTTABLE` query.**

   Canonical shape:

   ```sql
   SELECT TOP (:k) o.path, o.kind, o.content, ct.[RANK] AS score
   FROM FREETEXTTABLE({table}, content, :q, :top_n) AS ct
   INNER JOIN {table} AS o ON o.id = ct.[KEY]
   WHERE o.kind = 'file'
     AND o.deleted_at IS NULL
     {user_scope_clause}
   ORDER BY ct.[RANK] DESC, o.id
   ```

   - `:q` is the caller's raw query string, bound as a parameter.
   - `:top_n` is `max(k * 4, FULLTEXT_TOP_N)` — same posture as today.
   - `:k` binds the outer `TOP`.
   - `o.id` is the stable tie-breaker.
   - `content` is projected in the same row as `score`. No second query.

2. **Candidate-scoped lexical search is unchanged.**

   When `candidates is not None`, `_lexical_search_impl` keeps delegating to `DatabaseFileSystem._lexical_search_impl(...)`. That path runs Python BM25 over an in-memory candidate set (typically from vector search). It does not interact with `FREETEXTTABLE` and is not in scope.

3. **User scoping is unchanged in shape.**

   `_require_user_id(user_id)` is still called. When `self._user_scoped and user_id`, the clause stays `o.path LIKE :user_scope ESCAPE '\\'` with `:user_scope = f"/{user_id}/%"`. `_unscope_result(result, user_id)` still wraps the return.

4. **Error behavior is unchanged for empty / whitespace queries.**

   `if not query or not query.strip(): return self._error("lexical_search requires a query")`. The "no searchable terms in query" error is retired because `FREETEXTTABLE` does its own tokenization; a query that strips to all stopwords is allowed to return zero rows rather than synthesize an error. (See Open Questions.)

5. **`FULLTEXT_TOP_N` is reused as-is.**

   `FREETEXTTABLE` honors `top_n_by_rank` with the same semantics as `CONTAINSTABLE`. Keep the existing `FULLTEXT_TOP_N: ClassVar[int] = 1_000` and the `max(k * 4, FULLTEXT_TOP_N)` composition.

6. **`tokenize_query` and `_quote_contains_term` use on the lexical path is removed.**

   - Delete the `tokenize_query(query)` call inside `_lexical_search_impl`.
   - Delete the `" OR ".join(_quote_contains_term(t) for t in unique_terms)` construction.
   - Delete the `terms` / `unique_terms` / `contains_expr` locals.
   - Keep the `from vfs.bm25 import tokenize_query` import only if it still has callers after the edit; otherwise drop it.
   - `_quote_contains_term` stays defined — `_grep_impl` continues to use it for the literal-AND `CONTAINSTABLE` pre-filter, which is out of scope here.

7. **`Entry` shape is unchanged.**

   `Entry(path=..., kind=..., content=..., score=float(row.score))`. `score` is `float(ct.[RANK])`; the numeric scale differs from the previous CONTAINSTABLE rank but the field type is unchanged.

8. **Determinism is part of the contract.**

   The new `ORDER BY ct.[RANK] DESC, o.id` is a hard requirement, not an optimization. Tests must assert that the exact same query, run twice against the same committed state, returns the same ordered list of paths.

### Out

1. **Filtered indexed view as the FTS target.** `SCHEMABINDING` constraints and maintenance overhead are not justified by current evidence. Revisit only if the `kind = 'file' AND deleted_at IS NULL` post-filter is demonstrably the latency bottleneck.
2. **`OPTION (RECOMPILE)` on the lexical-search query.** No authoritative Microsoft or notable-MVP recommendation ties `RECOMPILE` to FTS queries specifically. Skip unless plan-cache pathology is observed.
3. **Per-term IDF weights via `ISABOUT(... WEIGHT(...))`.** No vetted recipe exists for deriving these from corpus statistics; `FREETEXTTABLE`'s BM25 already handles term weighting.
4. **Semantic Search (`sp_fulltext_semantic_*`).** Requires a Semantic Language Statistics Database not attached to this server; feature is soft-deprecated. Not available, not pursued.
5. **Hybrid lexical + vector re-rank.** Documented separately as a future upgrade path (see *Future upgrade path* below). Not in this story.
6. **Changes to `_grep_impl`** (the `CONTAINSTABLE` literal-AND pre-filter path). Out of scope; that path is correctness-first, not relevance-first.
7. **Removing `_quote_contains_term`.** It is still used by `_grep_impl`.
8. **Changes to the Postgres, SQLite, or base `DatabaseFileSystem` lexical paths.**
9. **Schema changes to `vfs_objects`**, the full-text catalog, or population settings. The existing index on `content` already supports `FREETEXTTABLE`.
10. **`Entry` / `VFSResult` shape changes.**

## Native behavior contract

### Score semantics

`Entry.score` is the `FREETEXTTABLE` rank — BM25-derived, integer-valued on the wire, returned as `float`. The scale is unbounded on the positive side and is **not** in `[0, 1)`. Callers comparing MSSQL scores to Postgres `ts_rank_cd` values were already comparing incomparable quantities; after this story they remain incomparable.

The previous `CONTAINSTABLE` rank and the new `FREETEXTTABLE` rank are numerically different even for the same query against the same index. Downstream consumers that persisted or thresholded on `score` must be notified via release notes.

### Result shape

Unchanged: `VFSResult(function="lexical_search", entries=[Entry(path, kind, content, score), ...])`, ordered by descending score with `o.id` as a stable tie-breaker. `kind` is always `'file'` because the ranking query constrains `o.kind = 'file'`.

### Query behavior

- Multi-term natural-language queries preserve any-term recall via `FREETEXTTABLE`'s built-in tokenization and inflectional expansion — **more** recall than the previous OR-of-literal-terms shape, not less.
- Empty / whitespace input returns the same error shape the current path returns.
- Tokenization happens inside SQL Server, not in Python. Punctuation and tsquery-style metacharacters in the user query are not hazardous because the query string is bound as a plain parameter; `FREETEXTTABLE` defines `FREETEXT`-style interpretation (no operators).

### User scoping

Unchanged. `_require_user_id`, the `path LIKE /{user_id}/%` scope clause, and `_unscope_result` are used identically.

### Failure mode

If the full-text catalog or index is missing, `FREETEXTTABLE` raises a SQL Server error; the call surfaces that error. This matches the current `CONTAINSTABLE` behavior — there is no silent fallback to a `LIKE` scan.

### Write-path impact

None. `vfs_ftcat` population is unchanged; `CHANGE_TRACKING = AUTO` on `content` continues to drive it.

## Acceptance criteria

### Backend surface

- [ ] `MSSQLFileSystem._lexical_search_impl` full-corpus path runs a single SQL statement using `FREETEXTTABLE`.
- [ ] The statement projects `o.path`, `o.kind`, `o.content`, and `ct.[RANK] AS score`, and returns `TOP (:k)` rows ordered by `ct.[RANK] DESC, o.id`.
- [ ] No second query hydrates `content` after the ranking query. The two-query `SELECT path, content FROM {table} WHERE path IN (...)` path is removed.
- [ ] `_lexical_search_impl` no longer calls `tokenize_query(...)` or builds an OR-of-terms `CONTAINSTABLE` expression.
- [ ] `candidates is not None` continues to delegate to `DatabaseFileSystem._lexical_search_impl(...)` with no behavior change.
- [ ] `_grep_impl` is unchanged and still uses `_quote_contains_term(...)` for its `CONTAINSTABLE` pre-filter.
- [ ] `FULLTEXT_TOP_N` is preserved with unchanged value and unchanged role (`top_n_by_rank` argument).
- [ ] Import of `tokenize_query` is removed from `mssql.py` iff no other caller remains; otherwise retained. Final state must be grep-verified.

### Lexical search behavior

- [ ] `lexical_search(query)` under `MSSQLFileSystem` returns `VFSResult(function="lexical_search", entries=[Entry(path, kind, content, score), ...])` with the same outer shape as before.
- [ ] Every `Entry.kind` is `'file'`.
- [ ] Every `Entry.content` is populated from the same row that produced `Entry.score` (i.e. from the ranking query, not a second read). Soft-deleted files are never returned.
- [ ] Empty / whitespace-only queries return the existing error result (`"lexical_search requires a query"`).
- [ ] A natural-language query whose inflectional form matches indexed content (e.g. `"plural"` matches a document containing only `"plurals"`) returns that document. This is a new capability vs. the previous OR-of-literal-terms path.
- [ ] Running the same query twice against the same committed state returns byte-identical ordered result lists.
- [ ] User scoping (`/{user_id}/%`) works identically to the previous implementation. Out-of-scope files are never returned.
- [ ] Tokens containing FTS metacharacters (e.g. `&`, `|`, `!`, `<`, `>`, `:`, `'`, `"`, backslash) inside the user query do not raise — they are part of the bound parameter that `FREETEXTTABLE` tokenizes internally.

### Scaling / performance contract

- [ ] Exactly one round trip to SQL Server is issued per full-corpus `lexical_search` call. Verified by counting statements issued on the session / raw driver connection.
- [ ] The ranking query uses the `vfs_ftcat` full-text index (no table scan over `content`).
- [ ] Candidate-scoped lexical search performs no MSSQL-side ranking query.

### Tooling / docs

- [ ] MSSQL backend lexical-search tests cover: `FREETEXTTABLE` ranking behavior, inflectional recall, determinism across repeated calls, user scoping, metacharacter safety, and the error shape on empty queries.
- [ ] `docs/architecture.md` describes MSSQL lexical search as a single `FREETEXTTABLE` query with server-side content hydration; documents the BM25 ranker.
- [ ] `docs/index.md` updates MSSQL lexical-search wording to reflect the `FREETEXTTABLE` ranker and the removed score-scale equivalence claim vs. Postgres.
- [ ] Release notes announce the score-scale change (`CONTAINSTABLE` rank → `FREETEXTTABLE` rank; still `float`, different magnitude, still not cross-backend-comparable).

## Rollout and rollback

Rollout:

- Land the code change.
- No DDL is required in production — `FREETEXTTABLE` uses the existing `vfs_ftcat` index.
- Announce the `Entry.score` scale change in release notes. Any caller thresholding on the previous `CONTAINSTABLE` value must be re-tuned.

Rollback:

- Code-only revert from git history. No schema change to undo.
- No feature flag is introduced; the change is small and the project's [no-migration-scripts](../../../../.claude/projects/-Users-claygendron-Git-Repos-grover/memory/feedback_no_migration_scripts.md) posture rules out parallel-path gating.

## Non-goals / follow-up candidates

- **Filtered indexed view over live files.** Revisit only if `kind = 'file' AND deleted_at IS NULL` becomes a measured latency bottleneck.
- **`OPTION (RECOMPILE)`** for the lexical query — only if parameter-sniffing pathology is observed.
- **`ISABOUT(... WEIGHT(...))` IDF-weighted terms** — only with a vetted pipeline deriving weights from corpus stats.
- **Hybrid BM25 + vector re-rank** (see below).
- **Unifying MSSQL and Postgres lexical scoring scales** — they are architecturally different rankers; papering over the difference is worse than documenting it.

### Future upgrade path: hybrid BM25 + vector re-rank

If BM25 alone hits a relevance ceiling on concept-style queries (e.g. *"how do we handle auth"* not matching files that say *"login middleware"*), the modern path, supported by the verified native `VECTOR` type on this server, is:

1. Add a `VECTOR` column storing an embedding of `content`.
2. Run `FREETEXTTABLE` for top-N lexical.
3. Run `VECTOR_DISTANCE(..., :query_embedding)` for top-N semantic.
4. Fuse with Reciprocal Rank Fusion (`SUM(1.0 / (60 + rank))`) across the two lists and re-sort.

The `_lexical_search_impl` rewrite in this story becomes the lexical half of that query when the time comes. Not in scope here.

## Open questions

1. Should `FULLTEXT_TOP_N = 1000` be re-tuned for `FREETEXTTABLE`? The CONTAINSTABLE-era choice was picked for a different ranker; `FREETEXTTABLE`'s BM25 may behave differently at the same cap. Default: leave unchanged and revisit only if measured.
2. `ORDER BY ct.[RANK] DESC, o.id` — is `o.id` the right tie-breaker vs. `o.path`? `o.id` is cheaper (primary key, no collation work) and stable within a row's lifetime; `o.path` would give lexicographic ordering users can predict from the path alone. Leaning `o.id`.
3. Does any test / downstream consumer depend on the old score scale? If yes, a short compatibility note in release notes is not enough and the rollout step needs a coordinated consumer update.
4. Should the lexical path error on queries that `FREETEXTTABLE` strips to zero tokens (e.g. all stopwords, all punctuation)? Current proposal: no — return an empty result, because distinguishing "no tokens survived" from "tokens matched nothing" is not something we can do cleanly from the client side without a second round trip, which is exactly what this story is eliminating.
5. Keep the `from vfs.bm25 import tokenize_query` import if any other MSSQL-backend caller uses it, or prune entirely. Grep-driven decision during implementation.
