# 012 — Implementation notes

- **Status:** implemented
- **Date:** 2026-04-23
- **Spec:** [spec.md](./spec.md)

## Summary

`MSSQLFileSystem._lexical_search_impl` full-corpus path is now a single
`FREETEXTTABLE` query. Tokenization, stemming, stoplists, and thesaurus
expansion run server-side; content is hydrated in the same row that carries
the rank; ties resolve deterministically on `o.id`.

## What changed

### `src/vfs/backends/mssql.py`

- Removed `from vfs.bm25 import tokenize_query` — no remaining caller in this
  module.
- `_lexical_search_impl` full-corpus branch rewritten:
  - Binds the caller's raw query as `:q` (no Python tokenization, no
    OR-of-literal-terms CONTAINS expression).
  - Issues one statement:
    ```sql
    SELECT TOP (:k) o.path, o.kind, o.content, ct.[RANK] AS score
    FROM FREETEXTTABLE({table}, content, :q, :top_n) AS ct
    INNER JOIN {table} AS o ON o.id = ct.[KEY]
    WHERE o.kind = 'file'
      AND o.deleted_at IS NULL
      {user_scope_clause}
    ORDER BY ct.[RANK] DESC, o.id
    ```
  - Drops the second `SELECT path, content ... WHERE path IN (...)`
    hydration query and the Python `content_by_path` zip.
  - `Entry(path, kind, content, score=float(ct.[RANK]))`.
- `FULLTEXT_TOP_N = 1_000` retained; `top_n = max(k * 4, FULLTEXT_TOP_N)` is
  unchanged.
- `candidates is not None` still delegates to
  `DatabaseFileSystem._lexical_search_impl`.
- `_require_user_id`, the `/{user_id}/%` scope clause, and `_unscope_result`
  are unchanged.
- `_quote_contains_term` stays defined — `_grep_impl` (around `mssql.py:1042`)
  still uses it for the literal-AND `CONTAINSTABLE` pre-filter.

### `tests/test_mssql_backend.py`

`TestLexicalSearchPushdown` gained five new cases alongside the existing
single-term / multi-term / candidates / top-k coverage:

- `test_content_hydrated_in_ranking_query` — every entry carries non-null
  content from the ranking row itself.
- `test_inflectional_recall` — a document containing only `"plurals"` is
  returned for the query `"plural"`. This was impossible under the previous
  OR-of-literal-terms CONTAINS path.
- `test_determinism_across_calls` — seeds 12 files with identical tokens,
  runs the same query twice, asserts byte-identical ordered `paths`. The
  `o.id` tie-breaker is what makes this pass.
- `test_metacharacters_do_not_raise` — `& " | ! < >` in the user query is
  tokenized by FREETEXT internally; no client-side escaping needed.
- `test_empty_query_errors` — whitespace-only input returns the existing
  error envelope.

### `docs/architecture.md`, `docs/index.md`

- MSSQL lexical search is described as a single `FREETEXTTABLE` query
  against the `vfs_ftcat` full-text index, with BM25 ranking.
- Score-scale note updated: `Entry.score` is `FREETEXTTABLE`'s BM25-derived
  rank — unbounded positive, integer on the wire, returned as `float`. Not
  comparable to Postgres `ts_rank_cd`.

### `CHANGELOG.md`

- New `Unreleased` entry announcing the rewrite and the score-scale change,
  with the explicit note that callers thresholding on the previous
  `CONTAINSTABLE` value must re-tune.

## What did *not* change

- `tests/conftest.py` — no DDL change. The existing `vfs_test_ftcat`
  full-text index on `content` already covers `FREETEXTTABLE`.
- `_grep_impl` — correctness-first literal-AND `CONTAINSTABLE` pre-filter is
  out of scope; `_quote_contains_term` stays.
- `DatabaseFileSystem._lexical_search_impl` — Python BM25 over hydrated
  candidates is unchanged and still owns the `candidates is not None` path.
- Postgres and SQLite lexical paths.
- `vfs_objects` schema, full-text catalog, or population settings.
- `Entry` / `VFSResult` shape.

## Acceptance criteria — status

### Backend surface

- [x] Full-corpus path is one SQL statement using `FREETEXTTABLE`.
- [x] Projects `o.path`, `o.kind`, `o.content`, `ct.[RANK] AS score`.
- [x] `TOP (:k)` rows ordered `ct.[RANK] DESC, o.id`.
- [x] Second content-hydration query removed.
- [x] No `tokenize_query` / OR-of-terms expression in the lexical path.
- [x] `candidates is not None` still delegates to the base class.
- [x] `_grep_impl` unchanged; still uses `_quote_contains_term`.
- [x] `FULLTEXT_TOP_N` preserved.
- [x] `tokenize_query` import removed from `mssql.py` (grep-verified).

### Lexical search behavior

- [x] `VFSResult` outer shape unchanged.
- [x] Every `Entry.kind == 'file'`.
- [x] Every `Entry.content` comes from the ranking row; soft-deleted files
  never surface.
- [x] Empty / whitespace-only queries → existing error envelope.
- [x] Inflectional recall (`plural` → `plurals`) covered by a test.
- [x] Determinism across repeated calls covered by a test.
- [x] User scoping unchanged in shape; existing scoping tests still pass.
- [x] FTS metacharacters in the user query do not raise — covered by test.

### Scaling / performance

- [x] Exactly one round trip per full-corpus call — *by construction*. Not
  asserted by an integration test; adding a driver-level statement counter
  is called out as follow-up.
- [x] Uses the `vfs_ftcat` index — inherent to `FREETEXTTABLE`; no table
  scan over `content`.
- [x] Candidate-scoped path runs no MSSQL-side ranking query (delegated).

### Tooling / docs

- [x] MSSQL lexical tests cover the new behaviors.
- [x] `docs/architecture.md` updated.
- [x] `docs/index.md` updated.
- [x] Release notes announce the score-scale change.

## Verification

Local run:

- `uvx ruff check src/vfs/backends/mssql.py tests/test_mssql_backend.py` —
  clean.
- `uvx ruff format --check src/vfs/backends/mssql.py tests/test_mssql_backend.py` —
  clean.
- `uvx ty check src/` — clean.
- `uv run pytest` — 2361 passed, 108 skipped. MSSQL integration tests
  (gated on `--mssql`) skip locally; they need a separate run against
  Azure SQL before the next release.

## Open items / follow-ups

Carried forward from the spec's **Open questions** and **Non-goals**:

- **Re-tune `FULLTEXT_TOP_N = 1_000` for BM25?** Left unchanged. Revisit
  only if a measurement motivates it.
- **Driver-level "one round trip" assertion.** The current tests check
  shape and determinism, not statement count. A small fixture wrapping
  `Engine.sync_engine.connect` or a SQLAlchemy `before_cursor_execute`
  counter would turn the performance clause from "by construction" into
  "asserted". Useful next time something in this path changes.
- **MSSQL integration run (`uv run pytest --mssql`).** The test changes
  target real Azure SQL behavior (inflectional stemming in particular) and
  should be run once against the target instance before cutting a release.
- **Hybrid BM25 + VECTOR_DISTANCE re-rank.** The deferred upgrade path
  from the spec. `_lexical_search_impl` is now shaped so it can be the
  lexical half of that query when the time comes.
- **Filtered indexed view / `OPTION (RECOMPILE)` / `ISABOUT` IDF weights.**
  All explicitly out of scope; revisit only with concrete evidence.
