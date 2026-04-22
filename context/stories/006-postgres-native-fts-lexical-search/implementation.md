# 006 - Implementation Notes

This document maps the current implementation for story 006 to [spec.md](./spec.md).

It also records the implementation decisions that were resolved while landing the change:

- full-corpus Postgres lexical search is now a single native FTS query; there is no Python BM25 rerank on that path
- candidate-scoped lexical search remains delegated to `DatabaseFileSystem._lexical_search_impl(...)` and therefore still uses Python BM25 over the provided in-memory candidate set
- schema verification now requires the stored generated `search_tsv` column plus a matching partial `GIN` index instead of accepting the earlier expression-index-only contract

## High-level result

Story 006 landed in four layers:

1. the Postgres lexical path was rewritten from hybrid FTS-plus-BM25 into one ranked SQL query
2. native FTS schema verification was tightened around the stored generated `search_tsv` column and aligned partial `GIN` index
3. Postgres integration tests and the repo probe were updated to lock in the new score semantics
4. operator-facing docs now describe Postgres lexical scores as native `ts_rank_cd`, not BM25

The current implementation matches the intent in [spec.md](./spec.md): the public `lexical_search(...)` shape is unchanged, but full-corpus `Entry.score` values on `PostgresFileSystem` are now bounded native FTS ranks.

## 1. Single-query native lexical search

Spec coverage:

- [spec.md](./spec.md) "In" items 1, 4, 5, and 8
- [spec.md](./spec.md) "Native behavior contract / Score semantics"
- [spec.md](./spec.md) "Acceptance criteria / Backend surface"

Key code:

- [`src/vfs/backends/postgres.py#L48-L60`](../../../src/vfs/backends/postgres.py#L48-L60) adds `_build_plainto_tsquery(...)`
- [`src/vfs/backends/postgres.py#L416-L486`](../../../src/vfs/backends/postgres.py#L416-L486) implements the new `_lexical_search_impl(...)` full-corpus branch

The shipped query shape is:

- tokenize the user query with `tokenize_query(...)`
- deduplicate terms with `dict.fromkeys(...)`
- build `plainto_tsquery('simple', :t0) || ...` with one bound parameter per token
- run one `WITH query AS (...) SELECT ... FROM vfs_objects AS o CROSS JOIN query ...` statement
- filter on `o.search_tsv @@ query.q`
- rank with `ts_rank_cd(o.search_tsv, query.q, 1|32)`
- project `o.path`, `o.kind`, `o.content`, and the computed score directly from that one statement

The earlier hybrid path from story 003 is gone on the full-corpus branch:

- no `BM25Scorer`
- no `_LexicalDoc` hydration pass
- no corpus-stat query
- no second `SELECT path, content FROM ... WHERE path = ANY(...)`

The result contract stays the same:

- `VFSResult(function="lexical_search", entries=[...])`
- stable ordering by `score DESC, path`
- user scoping still uses `o.path LIKE :user_scope ESCAPE '\\'`
- `_unscope_result(...)` still restores caller-visible paths on the way out

## 2. Candidate-scoped BM25 path stays intact

Spec coverage:

- [spec.md](./spec.md) "In" item 2
- [spec.md](./spec.md) "Out" item 1

Key code:

- [`src/vfs/backends/postgres.py#L425-L432`](../../../src/vfs/backends/postgres.py#L425-L432) keeps the early delegation to `super()._lexical_search_impl(...)` when `candidates is not None`
- [`src/vfs/backends/database.py#L2495-L2576`](../../../src/vfs/backends/database.py#L2495-L2576) remains the authoritative BM25 implementation

This is an intentional split in the final implementation:

- full-corpus Postgres lexical search is native FTS only
- candidate-scoped lexical search is still Python BM25 over the already-provided candidate rows

That preserves the existing chaining behavior for flows like vector-search-then-lexical-rerank without reintroducing the old hybrid full-corpus path.

## 3. Fail-fast schema verification now matches the runtime contract

Spec coverage:

- [spec.md](./spec.md) "In" items 3 and 7
- [spec.md](./spec.md) "Failure mode"

Key code:

- [`src/vfs/backends/postgres.py#L157-L194`](../../../src/vfs/backends/postgres.py#L157-L194) defines the DDL hint and catalog-normalization helpers
- [`src/vfs/backends/postgres.py#L208-L315`](../../../src/vfs/backends/postgres.py#L208-L315) verifies the native FTS schema

The verification logic now checks, in order:

1. the target table exists
2. the table still has a `content` column
3. `search_tsv` exists
4. `search_tsv` is a `tsvector`
5. the generation expression resolves to a stored `to_tsvector('simple', coalesce(content, ''))` shape
6. at least one `GIN` index exists on `search_tsv`
7. at least one such index carries the live-search predicate:
   `content IS NOT NULL AND deleted_at IS NULL AND kind != 'version'`

The important behavioral change from story 003 is that verification is now aligned with the runtime lexical query. The backend no longer accepts a looser expression-index setup while the search path itself reads from `o.search_tsv`.

Runtime failure behavior remains unchanged in spirit:

- raise `RuntimeError`
- include a concrete DDL hint
- do not silently fall back to the portable SQL `LIKE` prefilter path

## 4. Test provisioning and integration coverage

Spec coverage:

- [spec.md](./spec.md) "Expected touch points"
- [spec.md](./spec.md) "Acceptance criteria"
- [spec.md](./spec.md) "Test plan"

Key code:

- [`tests/conftest.py#L136-L180`](../../../tests/conftest.py#L136-L180) provisions the generated `search_tsv` column plus partial `GIN` index for Postgres integration tests
- [`tests/test_postgres_backend.py#L229-L317`](../../../tests/test_postgres_backend.py#L229-L317) covers native-schema verification success and failure modes
- [`tests/test_postgres_backend.py#L320-L393`](../../../tests/test_postgres_backend.py#L320-L393) covers the new lexical-search behavior

The new integration assertions lock in the story contract:

- `verify_native_search_schema()` passes against the expected generated-column setup
- missing `search_tsv` fails clearly
- missing `GIN` index fails clearly
- wrong partial predicate fails clearly
- a non-generated `search_tsv` column fails clearly
- lexical search scores are bounded to `[0, 1)`
- lexical search emits hydrated `content` directly from the ranking query
- multi-term queries build an OR of bound `plainto_tsquery(...)` terms
- single-term queries emit only one `plainto_tsquery(...)`
- candidate-scoped lexical search still avoids the native `search_tsv @@ query.q` path

## 5. Probe and docs

Spec coverage:

- [spec.md](./spec.md) "In" item 10
- [spec.md](./spec.md) "Native behavior contract / Score semantics"

Key code and docs:

- [`scripts/postgres_repo_cli_probe.py#L434-L441`](../../../scripts/postgres_repo_cli_probe.py#L434-L441) verifies the native FTS schema when constructing the Postgres-backed probe client
- [`scripts/postgres_repo_cli_probe.py#L683-L698`](../../../scripts/postgres_repo_cli_probe.py#L683-L698) asserts lexical-search result shape and bounded score semantics
- [`docs/architecture.md#L55-L87`](../../../docs/architecture.md#L55-L87) documents the one-query `search_tsv` + `GIN` + `ts_rank_cd` design
- [`docs/index.md#L95-L118`](../../../docs/index.md#L95-L118) documents the Postgres score semantics and required DDL

The docs now describe the native backend split plainly:

- MSSQL lexical scores are server-side BM25-style ranks from `CONTAINSTABLE`
- Postgres lexical scores are native `ts_rank_cd` cover-density scores in `[0, 1)`

That is the visible behavior change this story was meant to make explicit.

## 6. Verification that was run

The story was verified with the following focused checks:

- `uv run ruff check src/vfs/backends/postgres.py tests/test_postgres_backend.py scripts/postgres_repo_cli_probe.py`
- `uv run pytest tests/test_postgres_backend.py -k 'TestTsqueryHelpers or TestRegexTranslation or TestParseVectorDimension or TestPgvectorMetricHelpers'`
- `uv run pytest --postgres tests/test_postgres_backend.py -k 'TestVerifyNativeSearchSchema or TestLexicalSearch'`

A broader `uv run pytest --postgres tests/test_postgres_backend.py` run also completed far enough to show that the story-006 lexical path is green. The remaining failures on that full-file run were outside this story: they came from native vector write/delete tests hitting an existing `VectorType` readback issue when asyncpg/pgvector returned `ndarray` values.

## Summary

Story 006 replaced the old Postgres hybrid lexical path with a simpler and more honest contract:

- one SQL query
- one native ranking primitive
- one stored `search_tsv` schema contract
- one bounded score semantics story

The public `lexical_search(...)` envelope did not change. What changed is that `PostgresFileSystem` is now explicit about being a native PostgreSQL FTS backend rather than a partial BM25 emulation layer over FTS candidates.
