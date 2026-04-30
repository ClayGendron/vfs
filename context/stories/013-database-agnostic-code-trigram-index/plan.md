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

## Phase 2 — Portable Inverted-Index Contract

Define a backend-neutral contract for code-gram candidate indexes. The logical
interface is:

```text
chunk content -> distinct code grams -> durable inverted index -> candidate chunk ids
```

The target physical design is:

```text
chunk writes -> staging rows -> periodic flush -> immutable posting blocks
```

Required artifacts:

- staging rows keyed by `(index_id, gram_kind, gram, chunk_id)`
- compressed posting blocks keyed by `(index_id, gram_kind, gram, block_id)`
- gram statistics for selectivity planning
- delete/update metadata or equivalent tombstone handling
- candidate lookup that merges flushed blocks with pending writes or otherwise
  preserves committed-write freshness

Keep this as a backend contract, not a public model. Physical types, compression,
DDL, and query execution may vary per database.

## Phase 3 — Row-Store MVP Adapter

Build the simpler row-per-gram adapter first to validate behavior:

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

Required operations:

- create/provision gram artifacts
- delete grams for a chunk
- insert grams for a chunk
- query candidate chunk ids from a `GramQuery`
- join candidate ids back to chunk rows
- preserve no-false-negative freshness for committed chunks

The row store is a proving implementation, not the desired long-term storage
shape.

## Phase 4 — MSSQL Portable Adapter

Implement MSSQL first because it proves the non-native story.

Work items:

- add DDL for `dbo.vfs_entry_chunk_grams` as the MVP
- add provisioning/check helper
- update chunk write/load path to maintain grams
- add candidate query builder using grouped gram intersection
- integrate with `_grep_impl` before final Python verification
- optionally add `REGEXP_LIKE` as a second SQL narrowing step when available
- require query-time freshness for committed chunks

Do not remove the current `CONTAINSTABLE` path immediately. Keep it as a
separate token-search prefilter until benchmarks show whether it helps.

## Phase 5 — Posting-Block Storage

Move the MSSQL adapter from row-store MVP to the target physical model from
`mssql-trigram-inverted-index-design.md`:

- `TrigramStage`
- `TrigramBatches`
- `TrigramPostingBlocks`
- `TrigramStats`
- tombstones or equivalent delete/update filtering
- app-side decompression, union, and intersection
- compaction for many small blocks

The same storage contract is the future Postgres portable adapter. Postgres can
keep `pg_trgm` as a native comparison path while the portable path provides
punctuation-preserving byte-gram semantics.

## Phase 6 — Benchmark Harness

Extend `grep_glob research/live_grep_to_sql.ipynb` or add a sibling notebook.

Measure:

- candidate-id query only
- candidate content fetch
- Python verification
- end-to-end

Compare:

- ripgrep
- Postgres `pg_trgm`
- MSSQL row-store MVP
- MSSQL posting-block code-gram index
- Postgres posting-block code-gram index

Use the same benchmark cases from
`context/learnings/2026-04-24-postgres-trigram-grep-vs-ripgrep.md`, plus
punctuation-heavy patterns such as:

- `content ~ 'Postgres(FileSystem|Backend)'`
- `async def _grep_impl(`
- `path LIKE '/.vfs/%/__meta__/chunks/%'`
- `foo|bar`
- `a?.b`

## Phase 7 — Optional Native Adapters

After the portable storage model is proven:

- SQLite: evaluate FTS5 trigram tokenizer for local development.
- MySQL: evaluate `WITH PARSER ngram`, but keep the portable posting-block
  adapter as the predictable semantic fallback.
- Postgres: keep comparing portable raw byte grams against native `pg_trgm` on
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
- freshness across unflushed staging rows and flushed posting blocks

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

For bulk-loaded repo databases, build grams after chunks using a batch process
that writes posting blocks. For interactive writes, write staging rows
transactionally with chunks and make grep query the pending stage or scan
unflushed chunks.

## Rollback

The code-gram index is additive. Rollback is:

1. Disable the code-gram grep path.
2. Drop or ignore row-store/staging/posting-block artifacts.
3. Fall back to existing backend grep behavior.

No public VFS API or result shape changes are required.
