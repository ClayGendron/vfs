# Plan — Database-Agnostic Code Trigram Index

## Phase 1 — Shared Code-Gram Library

Create a small backend-neutral module for code gram generation and query
planning.

Expected shape:

- `iter_code_grams(content: str, *, folded: bool = False) -> Iterator[int]`
- `unique_code_grams(content: str, *, folded: bool = False) -> set[int]`
- `grams_for_fixed_string(pattern: str, *, folded: bool = False) -> set[int]`
- `build_code_gram_query(regex_pattern: str, ...) -> GramQuery`

Start conservative. The first `GramQuery` implementation only needs:

- `ANY`
- `AND(set[int])`
- `OR(tuple[GramQuery, ...])`

The regex planner may initially reuse existing literal extraction and return
`ANY` for hard patterns. No false negatives are allowed.

## Phase 2 — Side-Table Schema Contract

Define backend DDL for the logical side table:

```text
vfs_entry_chunk_grams(
  gram_kind,
  gram_key,
  chunk_id,
  owner_path,
  line_start,
  line_end
)
```

Keep this as a backend contract, not a public model. Physical types and DDL may
vary per database.

Required operations:

- create/provision gram artifacts
- delete grams for a chunk
- insert grams for a chunk
- query candidate chunk ids from a `GramQuery`
- join candidate ids back to chunk rows

## Phase 3 — MSSQL Adapter

Implement MSSQL first because it proves the non-native story.

Work items:

- add DDL for `dbo.vfs_entry_chunk_grams`
- add provisioning/check helper
- update chunk write/load path to maintain grams
- add candidate query builder using grouped gram intersection
- integrate with `_grep_impl` before final Python verification
- optionally add `REGEXP_LIKE` as a second SQL narrowing step when available

Do not remove the current `CONTAINSTABLE` path immediately. Keep it as a
separate token-search prefilter until benchmarks show whether it helps.

## Phase 4 — Benchmark Harness

Extend `grep_glob research/live_grep_to_sql.ipynb` or add a sibling notebook.

Measure:

- candidate-id query only
- candidate content fetch
- Python verification
- end-to-end

Compare:

- ripgrep
- Postgres `pg_trgm`
- MSSQL code-gram side table
- optional Postgres side table

Use the same benchmark cases from
`context/learnings/2026-04-24-postgres-trigram-grep-vs-ripgrep.md`, plus
punctuation-heavy patterns such as:

- `content ~ 'Postgres(FileSystem|Backend)'`
- `async def _grep_impl(`
- `path LIKE '/.vfs/%/__meta__/chunks/%'`
- `foo|bar`
- `a?.b`

## Phase 5 — Optional Native Adapters

After MSSQL is proven:

- SQLite: evaluate FTS5 trigram tokenizer for local development.
- MySQL: evaluate `WITH PARSER ngram`, but keep side table as the predictable
  semantic fallback.
- Postgres: compare side-table raw byte grams against native `pg_trgm` on
  punctuation-heavy code patterns.

## Testing Strategy

Unit tests:

- byte-gram packing/unpacking
- line-ending normalization
- punctuation-preserving gram generation
- folded gram generation
- conservative regex-to-gram planning

Integration tests:

- no false negatives versus portable in-memory grep
- fixed string, regex, word regexp, case-insensitive grep
- punctuation-heavy code strings
- chunk delete/update gram cleanup

Benchmark tests:

- marked slow/manual by default
- produce machine-readable timing summaries
- compare candidate counts and final match counts separately

## Migration Strategy

This feature should be opt-in per backend until measured.

Suggested config:

```python
MSSQLFileSystem(..., pattern_index="code_grams")
```

or a backend capability flag once the constructor surface is settled.

For bulk-loaded repo databases, build grams after chunks using a batch process.
For interactive writes, maintain grams transactionally with chunk rows.

## Rollback

The side table is additive. Rollback is:

1. Disable the code-gram grep path.
2. Drop or ignore `vfs_entry_chunk_grams`.
3. Fall back to existing backend grep behavior.

No public VFS API or result shape changes are required.
