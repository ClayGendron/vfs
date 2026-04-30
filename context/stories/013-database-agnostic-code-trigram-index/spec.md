# 013 — Database-Agnostic Code Trigram Index

- **Status:** draft
- **Date:** 2026-04-24
- **Owner:** Clay Gendron
- **Kind:** feature + backend + research

## Intent

Build a database-agnostic code-search candidate index that works for source
code, not just English words.

The feature should let Grover accelerate `grep()` over chunked file content in
any backend by using a code-oriented n-gram inverted index. PostgreSQL can keep
using native `pg_trgm` where appropriate, but MSSQL, PostgreSQL, and other
databases should converge on the portable staged posting-block design when
predictable code semantics matter. The public behavior remains unchanged:

```text
SQL narrows candidates; Python decides correctness.
```

The important shift from prior Postgres work is that the canonical index is not
`pg_trgm`'s word-oriented trigram model. Code search needs punctuation,
operators, whitespace, path separators, and mixed-language bytes to participate
in candidate narrowing.

## Why

The live benchmark in
[`context/learnings/2026-04-24-postgres-trigram-grep-vs-ripgrep.md`](../../learnings/2026-04-24-postgres-trigram-grep-vs-ripgrep.md)
showed that Postgres chunk trigram search can beat ripgrep on selective
corpus-wide searches, but loses badly when candidate sets are broad or Python
verification has to process too many chunks.

MSSQL currently has Full-Text Search and `REGEXP_LIKE` support paths, but those
are not a raw code trigram index:

- Full-Text Search is word-breaker/linguistic-token based.
- `CONTAINSTABLE` is useful for token search, not punctuation-sensitive grep.
- `REGEXP_LIKE` can verify or narrow, but it does not provide an index like
  `pg_trgm`.

Production code-search systems repeatedly converge on n-gram indexes:

- Google Code Search used trigram queries to narrow regex candidates.
- Zoekt/Sourcegraph use trigram indexes for source-code substring/regex search.
- GitHub Blackbird uses n-gram inverted indexes for substring code search.
- Elasticsearch's `wildcard` field uses an n-gram approximate filter plus exact
  verification.
- SQLite FTS5 has a native trigram tokenizer for substring matching.

Grover should make this pattern explicit and portable.

## Research

See [`research.md`](./research.md).

Key conclusions:

- The canonical tokenizer should be code-oriented, not English-word-oriented.
- A raw sliding byte trigram index is the most portable primitive.
- Native database support should be used only behind a common capability
  interface.
- Side-table indexes are required for MSSQL and likely useful for other
  relational backends.
- Final Python/ripgrep-style matching remains mandatory.

## Scope

### In

1. **Define a backend capability for code-gram grep candidates.**

   Add an internal capability shape that can answer:

   ```python
   get_code_gram_candidates(
       pattern: str,
       *,
       case_mode: CaseMode,
       fixed_strings: bool,
       word_regexp: bool,
       glob: str | None,
       paths: tuple[str, ...],
       ext: tuple[str, ...],
       limit: int | None,
   ) -> Iterable[ChunkCandidate]
   ```

   The capability returns chunk candidates only. It must not claim final match
   correctness.

2. **Define canonical code grams.**

   Canonical grams are raw sliding UTF-8 byte trigrams:

   - normalize line endings to `\n`
   - encode content as UTF-8
   - emit every 3-byte window
   - include punctuation, whitespace, operators, and bytes inside non-ASCII
     code points
   - deduplicate grams per chunk before storage

   For case-insensitive grep, support one of:

   - a second folded index generated from `content.casefold()`, or
   - a `gram_kind`/`folded` dimension in the same physical index.

3. **Adopt a portable inverted-index storage model.**

   The target architecture is the MSSQL design documented in
   [`mssql-trigram-inverted-index-design.md`](./mssql-trigram-inverted-index-design.md),
   generalized for every backend that needs predictable code-search semantics:

   ```text
   chunk writes -> gram staging rows -> periodic flush -> immutable posting blocks
   ```

   Logical artifacts:

   - a chunk metadata/content table, currently `vfs_entries`
   - a staging table with one row per distinct `(index_id, gram_kind, gram, chunk_id)`
   - posting-block storage with compressed sorted chunk ids per gram
   - optional gram statistics for selectivity-aware query planning
   - tombstone/update metadata or equivalent delete handling

   Queries fetch postings for required grams, union posting blocks within each
   gram, intersect across required grams, filter deletes and structural metadata,
   then fetch candidate chunk content for Python verification.

   Freshness is part of the correctness contract. A backend that uses staging and
   posting blocks must do one of:

   - query both flushed posting blocks and pending staging rows
   - synchronously flush affected grams before a grep that needs them
   - fall back to a scan over unflushed chunks

   Search freshness may be tuned, but the candidate path must not lose committed
   chunks that the public grep path would otherwise find.

4. **Keep a row-per-gram store as the MVP adapter, not the final contract.**

   The first implementation may use a simple relational row store to prove
   tokenizer, regex-planning, maintenance, and no-false-negative behavior:

   ```text
   vfs_entry_chunk_grams (
       gram_kind      smallint not null,  -- 0 raw, 1 folded
       gram_key       <packed-int-or-binary3> not null,
       chunk_id       text not null,
       owner_path     text not null,
       line_start     integer null,
       line_end       integer null,
       primary key (gram_kind, gram_key, chunk_id)
   )
   ```

   Backend-specific physical representations can vary behind the shared
   tokenizer/query API:

   - MSSQL: `tinyint` for kind, `binary(3)` or packed `int` for gram,
     `nvarchar(36)`/`uniqueidentifier` for chunk ids, `nvarchar(...)` for paths
   - Postgres: `smallint`, `bytea(3)` or `integer`, `text`/`uuid`
   - SQLite: `integer`, `blob(3)` or `integer`, `text`

   Required row-store indexes:

   - primary lookup by `(gram_kind, gram_key, chunk_id)`
   - reverse maintenance lookup by `chunk_id`
   - optional `owner_path` prefix/pattern helper for glob narrowing

5. **Implement candidate queries by gram intersection.**

   Row-store fixed string query shape:

   ```sql
   SELECT chunk_id
   FROM vfs_entry_chunk_grams
   WHERE gram_kind = :kind
     AND gram_key IN (:g1, :g2, :g3, ...)
   GROUP BY chunk_id
   HAVING COUNT(DISTINCT gram_key) = :required_count
   ```

   Then join back to chunk rows in `vfs_entries`:

   ```sql
   SELECT c.path, c.line_start, c.line_end, c.content
   FROM vfs_entries AS c
   JOIN candidate_chunks AS cc ON cc.chunk_id = c.id
   WHERE c.kind = 'chunk'
     AND c.content IS NOT NULL
     AND c.deleted_at IS NULL
   ```

   Posting-block adapters implement the same logical intersection in application
   code after loading compressed postings. Every backend may tune this physically,
   but the logical candidate behavior must be the same.

6. **Compile regexes conservatively into gram predicates.**

   The first implementation may be conservative:

   - fixed strings: exact byte-gram AND
   - simple regex literal runs: AND guaranteed literals
   - alternation with literal branches: OR of branch conjunctions when safe
   - hard regexes: no gram predicate, only structural filters

   False negatives are forbidden. Weak candidate predicates are acceptable.

   A later implementation can adopt the fuller Russ Cox / Google Code Search
   regex-to-trigram query algorithm.

7. **Keep Python authoritative.**

   After candidate chunks are fetched:

   - convert chunk paths back to owner file paths
   - apply exact glob matcher
   - run `_compile_grep_regex(...)` and exact Python line matching
   - return the same `VFSResult` shape as existing grep

8. **Support MSSQL first as the non-native proof.**

   MSSQL should get the first portable adapter because it lacks a native
   `pg_trgm` equivalent and already has a backend grep path. The row-store table
   is acceptable for the MVP, but the desired durable design is staging plus
   immutable posting blocks.

   The MSSQL path should:

   - maintain the row-store MVP or the staged posting-block artifacts
   - use binary-safe gram keys (`binary(3)` or canonical packed integer)
   - preserve freshness by querying pending rows/blocks or falling back to scan
   - optionally combine gram candidates with `REGEXP_LIKE` on SQL Server 2025+
   - keep `CONTAINSTABLE` as a separate optional token prefilter, not the code
     gram index

9. **Preserve the existing Postgres path while targeting the portable design.**

   Postgres should keep using `pg_trgm` for the current chunk-search notebook
   and backend path until the portable posting-block path is proven. The eventual
   goal is to implement the same portable staged posting-block design for
   Postgres too, so punctuation-sensitive code search is not limited by
   `pg_trgm` tokenizer semantics. This must not regress the existing native
   `pg_trgm` implementation.

10. **Add a benchmark harness.**

   Extend the notebook or add a new one to compare:

   - Postgres `pg_trgm`
   - MSSQL portable code-gram index
   - Postgres portable code-gram index
   - ripgrep

   Required timing splits:

   - SQL candidate ids only
   - SQL candidate content fetch
   - Python verification
   - end-to-end

### Out

- Replacing ripgrep/Python as the final semantic authority
- Fuzzy search, typo tolerance, or similarity ranking
- A full custom search server
- Token/lexical search replacement for BM25 or SQL FTS
- Query ranking beyond candidate generation
- Supporting invalid text/binary files as searchable code
- Making every database use identical physical SQL

## Native/Portable Backend Matrix

| Backend | Native option | Story behavior |
|---|---|---|
| PostgreSQL | `pg_trgm` GIN/GiST | Keep native path; add portable staged posting-block adapter for raw code grams. |
| MSSQL | none equivalent | Implement row-store MVP first, then staged posting-block adapter. |
| SQLite | FTS5 trigram tokenizer | Prefer native FTS5 trigram for local adapter; portable storage optional. |
| MySQL | ngram full-text parser | Treat as optional adapter; portable storage preferred for predictable code semantics. |
| ClickHouse | `ngrambf_v1` skipping index | Not row-exact; use only as scan-pruning inspiration. |
| Elasticsearch/OpenSearch | wildcard/ngram fields | External search adapter, not database VFS primary storage. |

## Data Model

### Logical Chunk Candidate

```python
@dataclass(frozen=True)
class ChunkCandidate:
    chunk_id: str
    chunk_path: str
    owner_path: str
    line_start: int | None
    line_end: int | None
    content: str | None
```

### Gram Key

Pack three bytes into an integer:

```python
gram_key = (b0 << 16) | (b1 << 8) | b2
```

This avoids collation behavior and keeps storage compact.

### Gram Kind

```text
0 = raw UTF-8 bytes from normalized content
1 = UTF-8 bytes from content.casefold()
```

## Query Semantics

The code gram index is a safe candidate generator:

- it may return false positives
- it must not introduce false negatives
- if a pattern has no safe grams, the backend must fall back to weaker
  structural narrowing
- final grep/glob semantics are unchanged

## Acceptance Criteria

1. A shared code-gram tokenizer emits raw byte trigrams including punctuation,
   whitespace, and operators.

2. Unit tests prove tokenizer behavior for examples like:

   ```text
   foo|bar
   content ~ 'Postgres(FileSystem|Backend)'
   a?.b
   path/to/file.py
   ```

3. Unit tests prove gram extraction is conservative:

   - fixed string `postgres` emits all byte trigrams
   - regex `Postgres(FileSystem|Backend)` emits a safe OR/AND predicate or a
     documented weaker predicate
   - regexes with no required grams degrade to `ANY`

4. Schema provisioning creates the gram index artifacts required by the selected
   adapter:

   - row-store MVP: `vfs_entry_chunk_grams` and required indexes
   - posting-block target: staging, posting blocks, statistics, and delete
     metadata

5. MSSQL chunk writes/deletes maintain gram index state atomically with chunk
   rows and preserve committed-write freshness by querying pending state,
   flushing synchronously, or falling back to scan.

6. MSSQL grep can use the code-gram index to fetch chunk candidates and then
   uses Python final matching.

7. A no-false-negative integration test compares MSSQL code-gram grep against
   the portable in-memory grep path across fixed strings, regexes, punctuation,
   path-like strings, case-sensitive patterns, and case-insensitive patterns.

8. A Postgres follow-up adapter can use the same logical staged posting-block
   design while preserving existing `pg_trgm` behavior and tests.

9. Benchmarks report candidate-only, fetch, verification, and end-to-end timing.

10. Documentation clearly states that code grams are not lexical search and not
   final match semantics.

11. Existing Postgres `pg_trgm` behavior and tests continue to pass.

## Risks

- **Storage growth.** Raw byte grams can produce many postings per chunk.
  Mitigation: dedupe per chunk, chunk size caps, compressed posting blocks, and
  file skip limits for high unique-gram files.

- **Hot grams.** Whitespace and common punctuation produce enormous posting
  lists. Mitigation: query planner should choose the most selective grams first
  where backend supports it; optionally drop ultra-hot grams from candidate
  predicates if doing so is still safe only as a weaker filter.

- **Case-fold storage cost.** Folded grams may nearly double index size.
  Mitigation: make folded index optional and fall back to raw plus Python for
  case-sensitive workloads.

- **Regex compiler unsoundness.** Regex-to-gram extraction can accidentally
  create false negatives. Mitigation: start conservative and add tests from
  Russ Cox-style boolean regex analysis before optimizing.

- **Write latency.** Maintaining grams on every write can be expensive.
  Mitigation: staging rows for cheap writes, batch flushes into posting blocks,
  and scan fallback for unflushed chunks when required by freshness.

- **Freshness gaps.** Periodic flushes can hide newly committed chunks if queries
  read only posting blocks. Mitigation: include staging in queries, flush before
  grep, or scan unflushed chunks.

## Open Questions

1. Should the canonical code-gram index be per chunk or per file? Default:
   chunk-level, because it bounds content fetch and aligns with current
   Postgres research.

2. Should folded grams always be stored? Default: no; make it configurable per
   backend/index profile.

3. Should hot grams be globally ignored? Default: no; ignoring grams weakens
   selectivity but is safe. It should be query-planner-driven, not tokenizer
   semantics.

4. Should Postgres add the portable posting-block adapter immediately after the
   MSSQL MVP? Default: yes after MSSQL proves the interface and benchmarks justify
   the storage cost, while keeping `pg_trgm` as the native comparison path.

5. Should grams be 3 bytes or configurable n-grams? Default: 3 bytes. Production
   systems repeatedly find trigrams to be the best default compromise.

## References

- Russ Cox, "Regular Expression Matching with a Trigram Index":
  https://swtch.com/~rsc/regexp/regexp4.html
- Sourcegraph Zoekt:
  https://github.com/sourcegraph/zoekt
- Sourcegraph search admin docs:
  https://sourcegraph.com/docs/admin/search
- Sourcegraph architecture note on Zoekt trigram indexes:
  https://sourcegraph.com/docs/cody/core-concepts/enterprise-architecture
- GitHub Blackbird:
  https://github.blog/2023-02-06-the-technology-behind-githubs-new-code-search/
- PostgreSQL `pg_trgm`:
  https://www.postgresql.org/docs/current/pgtrgm.html
- SQLite FTS5 trigram tokenizer:
  https://sqlite.org/fts5.html
- SQL Server Full-Text Search:
  https://learn.microsoft.com/en-us/sql/relational-databases/search/full-text-search
- MySQL ngram full-text parser:
  https://dev.mysql.com/doc/refman/8.0/en/fulltext-search-ngram.html
- Elasticsearch wildcard field:
  https://www.elastic.co/blog/find-strings-within-strings-faster-with-the-new-elasticsearch-wildcard-field
- ClickHouse data skipping indexes:
  https://clickhouse.com/docs/en/optimize/skipping-indexes
