# 007 - Implementation Notes

This document maps the current implementation for story 007 to [spec.md](./spec.md).

It also records the implementation decisions that were resolved while landing the change:

- `PostgresFileSystem` now has one native pattern-search path; there is no Postgres pattern backend selector
- native pattern search fail-fast requires `pg_trgm`, a partial `path text_pattern_ops` index, a partial `path gin_trgm_ops` index, and a partial `content gin_trgm_ops` index
- full-corpus `glob()` and `grep()` now treat SQL as sound narrowing and keep Python as the authoritative final matcher
- candidate-scoped `glob()` and `grep()` still delegate to `DatabaseFileSystem` and therefore stay in-process over the bounded candidate set

## High-level result

Story 007 landed in five layers:

1. native pattern-schema verification was added to the Postgres backend and wired into `verify_native_search_schema()`
2. full-corpus Postgres `grep()` was tightened around safe literal narrowing plus optional regex pushdown only when whole-content regex remains a sound superset of line-oriented matching
3. full-corpus Postgres `glob()` now combines structural SQL filters, optional `LIKE` narrowing, and SQL regex preselection with authoritative Python glob matching afterward
4. Postgres integration fixtures and tests were expanded to provision and lock in the pattern-search schema, correctness, and indexed plan shapes
5. the repo probe and operator-facing docs now describe the backend contract as "sound pushdown, exact final filtering"

The shipped implementation matches the intent in [spec.md](./spec.md): valid `glob()` and `grep()` patterns still work, PostgreSQL does as much safe narrowing as it can, and Python remains responsible for exact semantics whenever SQL could otherwise risk false negatives.

## 1. One native pattern backend with fail-fast schema verification

Spec coverage:

- [spec.md](./spec.md) "In" items 1 and 2
- [spec.md](./spec.md) "Native behavior contract / Backend mode"
- [spec.md](./spec.md) "Acceptance criteria / Backend surface" and "Schema verification"

Key code:

- [`src/vfs/backends/postgres.py#L192-L206`](../../../src/vfs/backends/postgres.py#L192-L206) defines the operator-facing pattern-schema DDL hint
- [`src/vfs/backends/postgres.py#L272-L280`](../../../src/vfs/backends/postgres.py#L272-L280) wires pattern verification into `verify_native_search_schema()`
- [`src/vfs/backends/postgres.py#L280-L360`](../../../src/vfs/backends/postgres.py#L280-L360) implements `_verify_pattern_schema(...)`

The runtime contract is now explicit:

- `verify_native_search_schema()` always checks the full-text schema first, then the pattern schema, then the native vector schema when pgvector is in use
- `_verify_pattern_schema(...)` rejects startup if `pg_trgm` is missing
- it inspects `pg_index` metadata and requires:
  - a partial B-tree `path text_pattern_ops` index with `deleted_at IS NULL`
  - a partial GIN `path gin_trgm_ops` index with `deleted_at IS NULL`
  - a partial GIN `content gin_trgm_ops` index with `kind = 'file' AND content IS NOT NULL AND deleted_at IS NULL`
- every failure raises `RuntimeError` with a concrete provisioning hint instead of silently falling back to the portable baseline path

That is the main architectural change from the earlier opportunistic behavior. The Postgres backend now declares a real deployment contract for native pattern search instead of merely attempting whatever indexes happen to exist.

## 2. Full-corpus grep now uses safe narrowing and authoritative Python line matching

Spec coverage:

- [spec.md](./spec.md) "In" items 4, 5, and 6
- [spec.md](./spec.md) "Correctness contract" and "Performance contract"
- [spec.md](./spec.md) "Acceptance criteria / Grep"

Key code:

- [`src/vfs/backends/postgres.py#L120-L151`](../../../src/vfs/backends/postgres.py#L120-L151) detects anchor tokens that make whole-content regex pushdown unsound for line-oriented grep
- [`src/vfs/backends/postgres.py#L640-L761`](../../../src/vfs/backends/postgres.py#L640-L761) implements the shipped `_grep_impl(...)`
- [`src/vfs/backends/database.py`](../../../src/vfs/backends/database.py) remains authoritative for candidate-scoped grep and for `_collect_line_matches(...)`

The full-corpus grep path now behaves as follows:

- if `candidates is not None`, Postgres delegates straight to `super()._grep_impl(...)`
- otherwise, Postgres verifies the native pattern schema and builds one SQL query over file rows with structural filters from `_build_structural_sql(...)`
- for `fixed_strings=True`, it adds `LIKE` or `ILIKE` whole-content narrowing
- for regex grep, it extracts literal terms from the compiled Python regex and adds one `LIKE` / `ILIKE` clause per literal term when available
- it only adds a database regex predicate on `content` when the pattern has no unescaped `^`, `$`, `\A`, or `\Z`, because anchored whole-file regex is not a sound superset of Python's line-by-line grep semantics
- after SQL returns candidate rows, `_collect_line_matches(...)` reconstructs the final line-oriented result set, context lines, counts, invert-match behavior, and file-mode behavior in Python

That split is the core correctness decision in the story. PostgreSQL is allowed to reduce the search space aggressively, but it is not allowed to become the final authority for line reconstruction or anchored regex semantics.

## 3. Full-corpus glob uses structural narrowing plus authoritative Python glob matching

Spec coverage:

- [spec.md](./spec.md) "In" items 4, 5, and 6
- [spec.md](./spec.md) "Correctness contract" and "Case behavior"
- [spec.md](./spec.md) "Acceptance criteria / Glob"

Key code:

- [`src/vfs/backends/postgres.py#L763-L867`](../../../src/vfs/backends/postgres.py#L763-L867) implements the shipped `_glob_impl(...)`
- [`src/vfs/patterns.py`](../../../src/vfs/patterns.py) remains the source of glob decomposition, SQL-like translation, and exact Python compilation

The full-corpus glob path now does three narrowing passes before the final Python check:

- structural narrowing through `_build_structural_sql(...)`, including any path scope or extension constraints
- prefix narrowing when `decompose_glob(...)` identifies a stable leading path prefix
- optional `path LIKE ... ESCAPE '\\'` narrowing when `glob_to_sql_like(...)` can safely translate the pattern

It also adds a SQL path regex clause using the translated Python glob regex, but that SQL predicate is still only a preselection step. Every returned row is re-checked with `regex.match(row.path)` in Python before it is emitted.

Important shipped semantics:

- `glob()` remains case-sensitive
- `files_only` glob shapes keep the SQL `kind = 'file'` restriction
- `max_count` is applied after the authoritative Python match, not before SQL narrowing
- candidate-scoped glob still delegates to the baseline in-process implementation

This means hard glob shapes can over-select in SQL, but they still return the same final answers as the baseline matcher.

## 4. Test provisioning and integration coverage

Spec coverage:

- [spec.md](./spec.md) "Expected touch points"
- [spec.md](./spec.md) "Acceptance criteria"
- [spec.md](./spec.md) "Test plan"

Key code:

- [`tests/conftest.py#L136-L200`](../../../tests/conftest.py#L136-L200) provisions the Postgres `search_tsv`, `pg_trgm`, `path text_pattern_ops`, `path gin_trgm_ops`, and `content gin_trgm_ops` artifacts for integration tests
- [`tests/test_postgres_backend.py#L305-L418`](../../../tests/test_postgres_backend.py#L305-L418) locks in native schema verification success and failure cases
- [`tests/test_postgres_backend.py#L561-L658`](../../../tests/test_postgres_backend.py#L561-L658) covers glob correctness and representative indexed plan shapes
- [`tests/test_postgres_backend.py`](../../../tests/test_postgres_backend.py) also includes grep correctness, regex translation, and pushdown-safety coverage for the shipped narrowing rules

The integration suite now verifies:

- native startup passes with the required pattern schema in place
- missing `pg_trgm`, missing path/content pattern indexes, and wrong partial predicates fail clearly
- full-corpus grep returns the same final answers as the baseline implementation for representative patterns
- anchored grep patterns skip unsafe regex pushdown
- full-corpus glob returns the same authoritative answers as the baseline implementation for representative hard shapes such as character classes
- `EXPLAIN (FORMAT JSON)` sees indexed plans for representative prefix and content narrowing queries

The plan assertions are intentionally scoped to plan shape rather than exact planner internals. The tests verify that the expected indexes are reachable for representative query forms without over-constraining PostgreSQL's plan choices.

## 5. Probe and docs

Spec coverage:

- [spec.md](./spec.md) "In" item 7
- [spec.md](./spec.md) "Safety / observability / docs"

Key code and docs:

- [`scripts/postgres_repo_cli_probe.py#L430-L438`](../../../scripts/postgres_repo_cli_probe.py#L430-L438) verifies both full-text and pattern schema on Postgres probe startup
- [`docs/architecture.md#L83-L120`](../../../docs/architecture.md#L83-L120) documents the Postgres pattern contract as native narrowing plus exact Python filtering
- [`docs/index.md#L97-L142`](../../../docs/index.md#L97-L142) documents the backend behavior and the required DDL for the pattern indexes

The docs now describe the important operator reality directly:

- Postgres native pattern search depends on schema that operators provision outside request handling
- the trigram and pattern indexes are there to accelerate narrowing, not to redefine the meaning of valid glob or grep patterns
- Python still owns exact matching semantics where PostgreSQL would otherwise be an unsafe final authority

## 6. Verification that was run

The story was verified with these checks:

- `uv run ruff check src/ tests/`
- `uv run ruff format --check src/ tests/`
- `uv run ty check src/`
- `uv run pytest`
- `uv run pytest tests/test_postgres_backend.py --postgres -k 'TestVerifyNativeSearchSchema or TestGrep or TestGlob or TestPatternSearchPlans or TestRegexPushdownSafety or TestRegexTranslation or TestTsqueryHelpers'`

Those checks covered the shipped native-schema contract, grep/glob correctness, pushdown-safety rules, indexed plan expectations, and the wider repo test suite.

## Summary

Story 007 turned the Postgres pattern path into an explicit contract instead of a best-effort optimization:

- one native backend
- one fail-fast schema contract
- SQL for safe narrowing
- Python for exact final semantics

The public `glob()` and `grep()` APIs did not change. What changed is that `PostgresFileSystem` now makes its native pattern behavior deliberate, documented, and test-locked.
