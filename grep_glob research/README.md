# Grep/Glob Pushdown Research

Date: 2026-04-24

This directory researches how to push ripgrep-style `grep` and repo `glob`
queries into PostgreSQL without changing user-visible semantics.

The target database inspected locally is:

```text
database: git_repos_vfs
schema:   public
table:    public.vfs_entries
server:   PostgreSQL 18.0, Homebrew, aarch64
```

Observed live data:

```text
live files:              221,141
live file content rows:  221,141
live content size:       1,724 MB
live directories:        729,337
live versions:           221,141
initial indexes:         btree indexes only; no pg_trgm indexes
```

## Bottom line

Use PostgreSQL trigram indexes as a candidate generator, not as the semantic
authority. For maximum query-time optimization, add a file-chunk candidate
table; do not make a line table. The fast path should be:

1. Apply structural filters first: `kind`, `deleted_at`, `content IS NOT NULL`,
   `ext`, explicit path scopes, and literal path prefixes.
2. Prefer chunk-level candidate selection for content grep. Store newline-aligned
   chunks so a grep line is never split across chunks.
3. Apply the strongest sound text predicate PostgreSQL can use:
   `LIKE`/`ILIKE` for fixed strings and literals, `~`/`~*` for regexes with
   extractable trigrams, and `path ~` for glob regex preselection.
4. Fetch only candidate file ids/paths from SQL, then fetch full content only
   for those candidates.
5. Run the exact ripgrep-style line matcher and exact glob matcher in Python.

PostgreSQL already implements regex-to-trigram extraction for `~` and `~*` on a
`gin_trgm_ops` index. That means the application usually should not try to
materialize trigrams itself for the final SQL predicate. The application should
extract guaranteed literals and structural constraints so the planner has more
selective predicates, then let `pg_trgm` do its native lossy candidate scan.

## Required schema

See [schema.sql](./schema.sql) for direct `vfs_entries` indexes and
[chunk-table.sql](./chunk-table.sql) for the chunk candidate table.

Recommended index family:

- `path text_pattern_ops` partial btree for left-anchored path/prefix glob.
- `path gin_trgm_ops` partial GIN for path regex, suffix, infix, and glob-like
  narrowing.
- `content gin_trgm_ops` partial GIN for fixed string, regex, and literal grep
  narrowing over live file content.

The content trigram index is large and expensive because it indexes 1.7 GB of
text. On the local database, parallel GIN builds hit memory pressure even with
an 8 GB maintenance memory allowance. The reliable local build profile is serial
maintenance workers with high `maintenance_work_mem`.

## Query strategy

### Grep Without Chunks

For full-corpus grep, the current repo shape is directionally right:

- Compile the authoritative Python regex from ripgrep-like flags.
- If `invert_match=True`, do not push content text predicates; a positive SQL
  content predicate would be unsound for inverted line matching.
- For `fixed_strings=True`, add a `content LIKE/ILIKE '%literal%'` predicate.
- Extract guaranteed literal runs from the effective regex and add them as
  conjunctive `LIKE/ILIKE` predicates only when every match must contain them.
- Add `content ~/~*` only when whole-file regex matching is a sound superset of
  line-oriented Python grep.
- Always run final line matching in Python.

Important refinement: line-anchored patterns like `^TODO` and `TODO$` can be
pushed more often than the current code allows. PostgreSQL ARE supports
newline-sensitive mode with embedded option `(?n)`. That makes `^` and `$`
match around newlines, while `.` stops crossing newline. For Python's current
line-by-line grep semantics, `content ~ '(?n)^TODO'` is a sound candidate
predicate for `^TODO`. Translate Python `\A` and `\Z` to `^`/`$` first, as the
current code already does, because Python evaluates them against each line.

### Grep With File Chunks

The aggressive design is a chunk table:

- one row per live file chunk
- chunks target 32-128 KiB
- chunk boundaries are newline-aligned; a very long line is allowed to exceed
  the target chunk size
- chunk rows carry `entry_id`, `path`, `ext`, `chunk_no`, `line_start`,
  `line_end`, and `content`
- chunk `content` gets its own `gin_trgm_ops` index

Candidate SQL then runs against chunks:

```sql
SELECT DISTINCT c.entry_id, c.path
FROM public.vfs_entry_chunks AS c
WHERE c.content ~ '(?n)Postgres(FileSystem|Backend)';
```

Then Python fetches the corresponding full file content from `vfs_entries` and
does the final line matcher. For `output_mode='files'` and no context, a later
implementation can avoid fetching full content and use chunk line counts plus a
secondary verification pass, but full-file Python verification is the simplest
zero-false-negative contract.

See [chunk-table.sql](./chunk-table.sql) and
[build_chunk_table.py](./build_chunk_table.py).

### Glob

Use path filters in this order:

- Structural `kind IN ('file', 'directory')` and `deleted_at IS NULL`.
- Extension filter when the glob tail proves `**/*.<literal-ext>`.
- Literal prefix to use `path text_pattern_ops`, for example `/src/%`.
- `path LIKE ... ESCAPE '\'` when the glob can be translated to a safe
  over-selecting LIKE pattern.
- `path ~ :translated_regex` as an additional trigram-backed preselection.
- Final exact `compile_glob(...).match(path)` in Python.

Do not apply `max_count` before the Python authoritative filter. SQL can
over-select.

## Current repo code notes

See [repo-code-notes.md](./repo-code-notes.md).

## Experiments

See [benchmark.sql](./benchmark.sql) for repeatable `EXPLAIN ANALYZE` probes.
The probes are built around the actual `public.vfs_entries` shape and should be
run after [schema.sql](./schema.sql).

## Prototype

See [pushdown_extract.py](./pushdown_extract.py) for a small conservative
extractor. It is intentionally less ambitious than PostgreSQL internals. Its
job is to find safe literals and glob prefixes that can improve candidate
generation without risking false negatives.

## Primary sources

- PostgreSQL `pg_trgm` docs:
  https://www.postgresql.org/docs/current/pgtrgm.html
- PostgreSQL pattern matching docs:
  https://www.postgresql.org/docs/current/functions-matching.html
- PostgreSQL `trgm_regexp.c` source comments:
  https://doxygen.postgresql.org/trgm__regexp_8c_source.html
- Python `fnmatch` docs:
  https://docs.python.org/3/library/fnmatch.html
