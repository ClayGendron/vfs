# Postgres Chunk Trigram Grep vs Ripgrep

> Date: 2026-04-24
> Scope: local `Git/Repos` corpus loaded into `pg_trgrm_test_git_repos`
> Notebook: `grep_glob research/live_grep_to_sql.ipynb`

## Executive Summary

Postgres chunk trigram search is promising, but it is not a universal ripgrep
replacement.

On the local `Git/Repos` corpus, Postgres wins when the predicate is selective
and trigram-friendly, especially fixed strings and distinctive config/search
terms. Ripgrep wins decisively on broad source-code regexes where the SQL side
returns many chunk candidates and then Python has to verify them.

The practical rule is:

- Use Postgres chunk trigram search as an indexed candidate generator.
- Keep Python/ripgrep-style matching as the correctness authority.
- Expect Postgres to beat filesystem grep when the SQL predicate sharply
  narrows candidates.
- Expect ripgrep to beat Postgres when the pattern matches broad language
  structure, common framework names, or many chunks.

## Setup

Database:

```text
database: pg_trgrm_test_git_repos
table:    public.vfs_entries
rows:     kind='file' parent rows + kind='chunk' searchable rows
index:    ix_vfs_entries_chunk_content_trgm_gin
```

Every chunk candidate query must include the partial-index predicate:

```sql
kind = 'chunk'
AND content IS NOT NULL
AND deleted_at IS NULL
```

The test notebook builds candidate SQL with `LIKE`, `ILIKE`, `~`, or `~*`,
then groups chunk paths back to owning file paths and verifies the final match
with Python's compiled grep regex.

The equivalent ripgrep benchmark ran against:

```text
/Users/claygendron/Git/Repos
```

Both sides excluded heavy generated/dependency directories:

```text
.git
node_modules
.venv
dist
build
target
vendor
.next
__pycache__
```

Timing protocol:

- Postgres notebook: 1 warmup, 3 measured runs, best/median recorded.
- Ripgrep shell: 1 warmup, 3 measured runs through `/usr/bin/time -p`.
- Ripgrep output redirected to `/tmp` so terminal rendering did not dominate.

Count caveat: Postgres counts below are verified chunks/files. Ripgrep counts
were output lines. Timing comparison is still useful, but counts are not
one-to-one.

## Results

| case | DB best | DB median | DB chunks | DB files | DB verified | rg best | rg median | rg lines | faster |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `py_defs_classes_anchored` | 24.807s | 25.118s | 239,724 | 40,361 | 239,724 | 0.480s | 0.480s | 75,643 | rg 51.7x |
| `vfs_postgres_types` | 8.323s | 8.351s | 226 | 46 | 226 | 0.390s | 0.390s | 849 | rg 21.3x |
| `async_sqlalchemy_postgres` | 2.105s | 2.111s | 4,781 | 1,463 | 4,781 | 0.380s | 0.390s | 1,214 | rg 5.5x |
| `todo_fixme_hack` | 3.681s | 3.706s | 36,632 | 16,134 | 36,632 | 4.360s | 4.390s | 19,328 | DB 1.2x |
| `react_hooks_tsx` | 12.292s | 12.710s | 411 | 223 | 411 | 0.340s | 0.360s | 912 | rg 36.2x |
| `config_env_tokens` | 1.334s | 1.338s | 1,096 | 393 | 1,096 | 4.360s | 4.380s | 764 | DB 3.3x |
| `sql_trigram_indexes` | 3.504s | 3.527s | 331 | 131 | 331 | 4.300s | 4.320s | 401 | DB 1.2x |
| `api_router_models` | 22.917s | 23.015s | 13,927 | 4,822 | 13,927 | 0.400s | 0.410s | 8,842 | rg 57.3x |
| `vector_search_terms` | 11.181s | 11.211s | 34,919 | 15,422 | 34,919 | 4.410s | 4.490s | 18,693 | rg 2.5x |
| `fixed_postgres_casefold` | 0.774s | 0.777s | 4,412 | 1,222 | 4,412 | 4.340s | 4.450s | 4,390 | DB 5.6x |

## Patterns Tested

The benchmark cases intentionally mixed several real corpus shapes:

- anchored Python declaration regex:
  `^[ \t]*(async[ \t]+def|def|class)[ \t]+[A-Za-z_][A-Za-z0-9_]*`
- VFS/Postgres backend symbols:
  `\b(Postgres(FileSystem|Backend)|DatabaseFileSystem|VirtualFileSystem)\b`
- async SQLAlchemy/Postgres terms:
  `\b(create_async_engine|AsyncSession|asyncpg|postgresql\+asyncpg|sqlalchemy)\b`
- code-comment markers:
  `\b(TODO|FIXME|XXX|HACK|BUG)\b`
- React hooks/components:
  `\b(useEffect|useMemo|useCallback|useLayoutEffect|React\.FC|createRoot)\b`
- config token names:
  `\b(OPENAI_API_KEY|ANTHROPIC_API_KEY|DATABASE_URL|SECRET_KEY|TOKEN|AUTH_SECRET)\b`
- trigram/index SQL terms:
  `\b(CREATE[ \t]+(UNIQUE[ \t]+)?INDEX|USING[ \t]+GIN|gin_trgm_ops|pg_trgm|EXPLAIN[ \t]*\([A-Z, \t]+\))`
- Python API/router/model terms:
  `\b(FastAPI|APIRouter|BaseModel|pydantic|Request|Response)\b`
- graph/vector/search vocabulary:
  `\b(pagerank|centrality|embedding|vector(_search|store)?|BM25|semantic[ \t]+search)\b`
- fixed case-insensitive baseline:
  `postgres`

## Interpretation

### Where Postgres Won

Postgres was strongest on selective corpus-wide searches:

- `fixed_postgres_casefold`: 0.774s vs ripgrep 4.340s.
- `config_env_tokens`: 1.334s vs ripgrep 4.360s.
- `sql_trigram_indexes`: slight win, 3.504s vs ripgrep 4.300s.
- `todo_fixme_hack`: slight win, 3.681s vs ripgrep 4.360s.

These are good fits for pg_trgm because the index can narrow the corpus before
the application receives rows.

### Where Ripgrep Won

Ripgrep dominated broad code-structure scans:

- Python declarations: 0.480s vs Postgres 24.807s.
- API/router/model terms: 0.400s vs Postgres 22.917s.
- React hook terms: 0.340s vs Postgres 12.292s.
- VFS/Postgres symbol alternation: 0.390s vs Postgres 8.323s, despite the DB
  returning only 226 verified chunks.

Likely causes:

- round-trip and row materialization overhead,
- Python verification over chunk content,
- chunk overlap creating more candidate rows than line-oriented grep output,
- broad predicates that defeat the intended selectivity advantage,
- path/glob filtering that is still weaker than ripgrep's filesystem/type
  traversal shortcuts.

## Design Implications

1. Do not frame Postgres trigram grep as a faster ripgrep for every query.
   It is an indexed candidate generator with a different performance envelope.

2. Push down the strongest safe predicate:
   fixed strings should use `LIKE`/`ILIKE`; regexes should use `~`/`~*`; anchored
   line regexes can use PostgreSQL newline-sensitive mode where safe.

3. Keep the partial-index predicate mandatory:

   ```sql
   kind = 'chunk'
   AND content IS NOT NULL
   AND deleted_at IS NULL
   ```

4. Improve glob/path pushdown before judging broad language scans. The current
   candidate path narrowing still leaves Postgres doing too much work for some
   extension-scoped searches.

5. Avoid returning large chunk payloads when the caller only needs file names or
   counts. A two-stage query that returns only chunk ids/paths first may reduce
   DB-side losses.

6. Add benchmark modes for:

   - SQL candidate time only,
   - SQL fetch plus Python verification,
   - final result shaping,
   - whole-file verification for exact context.

   The current benchmark mixes these costs, which is useful end-to-end but less
   useful for optimization.

7. For interactive agent search, prefer routing:

   - use Postgres for selective fixed strings, rare identifiers, config keys,
     cross-repo metadata-like terms, and DB-resident corpora;
   - use ripgrep for broad source scans, language declarations, common
     framework names, and repo-local filesystem searches.

## Next Experiments

- Run `EXPLAIN (ANALYZE, BUFFERS)` for the slow-but-selective cases, especially
  `vfs_postgres_types` and `react_hooks_tsx`, to see whether time is index scan,
  heap recheck, sorting, transfer, or Python verification.
- Split notebook timings into SQL-only and Python-filter phases.
- Add `SELECT count(*)` candidate probes so we can compare candidate selectivity
  without transferring content.
- Test path predicates that use `original_path` or a normalized owner-file path
  if available, instead of deriving owner paths from chunk metadata paths.
- Test smaller/larger chunk sizes and overlap values. The current chunk overlap
  may be increasing duplicate candidate work for common terms.
- Compare `rg` with `--count-matches`, `--files-with-matches`, and output
  suppression variants to separate search time from match formatting.
