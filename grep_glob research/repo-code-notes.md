# Repo Code Notes

The current implementation already follows the right high-level contract:
Postgres narrows; Python decides final grep/glob semantics.

## CLI and AST path

- `src/vfs/query/parser.py` parses a ripgrep-like `grep` command.
- `GrepCommand` in `src/vfs/query/ast.py` carries already-resolved fields:
  `ext`, `ext_not`, `globs`, `globs_not`, `case_mode`, `fixed_strings`,
  `word_regexp`, `invert_match`, context windows, output mode, and `max_count`.
- `src/vfs/query/executor.py` forwards these fields into `filesystem.grep`.
- `tests/test_query_executor.py::TestGrepRipgrepFieldForwarding` protects
  against accidentally dropping a field.

This is good for pushdown work because backend code does not need to parse CLI
flags. It receives semantic knobs.

## Effective regex compilation

`src/vfs/backends/database.py` contains the authoritative grep compilation:

- `_regex_flags_for_mode(case_mode, pattern)` implements sensitive,
  insensitive, and smart case. Smart case is case-insensitive only when the raw
  pattern is all lowercase.
- `_compile_grep_regex(...)` applies `fixed_strings` first by `re.escape`, then
  wraps `word_regexp=True` as `\b(?:pattern)\b`, then compiles with case flags.
- `_collect_line_matches(...)` scans `content.split("\n")` line-by-line and
  emits final candidates, context, scores, and output modes.

This means final grep semantics are Python `re` semantics over individual
lines, not PostgreSQL whole-string regex semantics.

## Literal extraction

`_extract_literal_terms(pattern)` is deliberately conservative:

- Rejects quantified groups such as `(...)+`.
- Rejects negative lookahead/lookbehind.
- Rejects alternation outside escaped tokens and character classes.
- Drops escaped pairs, classes, dot/anchors, and quantified word atoms.
- Keeps up to eight alphanumeric/underscore runs of length at least three.

That is sound for conjunctive `LIKE` prefilters, but it leaves performance on
the table for common alternations. Example: `foo|bar` cannot become
`content LIKE '%foo%' AND content LIKE '%bar%'`, but it could become an OR
candidate expression. PostgreSQL's native regex trigram analysis already handles
many of these cases when the backend emits `content ~ :pattern`.

## Postgres translation

`src/vfs/backends/postgres.py` adds two important pieces:

- `_python_regex_to_postgres` translates only the small subset this repo
  synthesizes: `\b` to `\y`, `\A` to `^`, `\Z` to `$`, and `(?:` to `(`.
- `_contains_unescaped_anchor` suppresses whole-content regex pushdown for
  `^`, `$`, `\A`, and `\Z`.

That suppression is safe, but it is more conservative than necessary. PostgreSQL
ARE supports embedded newline-sensitive mode `(?n)`, where `^` and `$` match
around newlines and `.` does not cross newlines. Because this repo's Python grep
matches one line at a time, the Postgres prefilter can translate anchored grep
patterns into newline-sensitive whole-content regex predicates:

```sql
content ~ '(?n)^TODO'
content ~* '(?n)\ypostgres\y'
```

The final Python matcher should still remain authoritative. This is a candidate
selection improvement, not a semantics handoff.

## Postgres grep path

`PostgresFileSystem._grep_impl` currently:

- Delegates candidate-scoped grep to `DatabaseFileSystem`.
- Verifies the pattern schema for full-corpus grep.
- Builds structural SQL.
- Adds fixed string `LIKE/ILIKE` when applicable.
- Adds guaranteed literal `LIKE/ILIKE` clauses.
- Adds `content ~/~*` when unanchored and not inverted.
- Runs `_collect_line_matches` in Python.

Recommended refinements:

- Add plan/telemetry counters: SQL candidate rows, final matched files, and
  candidate-to-match ratio.
- Special-case short fixed strings under three word characters. `pg_trgm` will
  be weak or unusable; use structural filters and maybe a bounded fallback.
- Replace the current anchor-suppression branch with newline-sensitive Postgres
  regex preselection where the translated pattern is valid PostgreSQL ARE.
- Consider optional OR literal extraction for simple top-level alternations:
  `(foo|bar)` can safely become `(content LIKE '%foo%' OR content LIKE '%bar%')`
  when each branch has a guaranteed literal. Keep Python final matching.
- Prefer chunk-table candidate generation for query-time optimization at scale.
  Store newline-aligned chunks, not per-line rows, and run trigram predicates on
  the chunk content.

## Postgres glob path

`PostgresFileSystem._glob_impl` currently:

- Delegates candidate-scoped glob to `DatabaseFileSystem`.
- Compiles the authoritative Python glob regex.
- Uses `decompose_glob` for literal path prefix and extension narrowing.
- Uses `glob_to_sql_like` when possible.
- Adds `path ~ :glob_regex`.
- Applies `max_count` only after Python exact matching.

Recommended refinements:

- Ensure prefix decomposition is scoped correctly for user-scoped mounts. The
  current code decomposes `unscoped_pattern` and later uses structural SQL with
  `user_id`; keep tests around this path.
- For `**/*.<ext>`, prefer `kind='file' AND ext=:ext` plus path prefix before
  regex. This is usually more selective than path regex alone.
- For basename-only globs like `**/foo.py`, add `name = 'foo.py'` if a `name`
  btree index exists or is worth adding.
- For simple suffix globs like `**/*.py`, the current btree `(ext, kind)` index
  can outperform trigram path regex. Use ext first.

## Biggest correctness boundary

Do not let SQL become authoritative unless the semantics are exactly the same.
Postgres ARE, Python `re`, and this repo's custom glob semantics differ at
word boundaries, anchors, path separators, noncapturing groups, escapes, and
line-vs-whole-content matching.
