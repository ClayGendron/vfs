-- Repeatable grep/glob pushdown probes.
--
-- Usage:
--   psql -h localhost -d git_repos_vfs -f "grep_glob research/benchmark.sql"

\timing on

SET statement_timeout = '120s';

SELECT
  count(*) FILTER (WHERE kind = 'file' AND deleted_at IS NULL) AS live_files,
  pg_size_pretty(sum(pg_column_size(content)) FILTER (
    WHERE kind = 'file' AND deleted_at IS NULL AND content IS NOT NULL
  )) AS live_content_bytes
FROM public.vfs_entries;

SELECT
  indexname,
  pg_size_pretty(pg_relation_size((schemaname || '.' || indexname)::regclass)) AS size,
  indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'vfs_entries'
ORDER BY indexname;

-- Prefix glob: should prefer ix_vfs_entries_path_pattern_live or another path
-- btree path index when the planner estimates prefix selectivity well.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT path
FROM public.vfs_entries
WHERE deleted_at IS NULL
  AND path LIKE '/src/%' ESCAPE '\'
ORDER BY path
LIMIT 100;

-- Infix/suffix path filter: should use path trigram GIN.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT path
FROM public.vfs_entries
WHERE deleted_at IS NULL
  AND path ILIKE '%.py' ESCAPE '\'
ORDER BY path
LIMIT 100;

-- Glob-style path regex preselection: database returns a candidate set, Python
-- remains authoritative for exact glob semantics.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT path
FROM public.vfs_entries
WHERE deleted_at IS NULL
  AND kind IN ('file', 'directory')
  AND path ~ '^/(?:.*/)?[^/]*\.py$'
ORDER BY path
LIMIT 100;

-- Fixed string grep candidate generation.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT path
FROM public.vfs_entries
WHERE kind = 'file'
  AND deleted_at IS NULL
  AND content IS NOT NULL
  AND content LIKE '%Postgres%' ESCAPE '\'
ORDER BY path
LIMIT 100;

-- Case-insensitive fixed string grep candidate generation.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT path
FROM public.vfs_entries
WHERE kind = 'file'
  AND deleted_at IS NULL
  AND content IS NOT NULL
  AND content ILIKE '%postgres%' ESCAPE '\'
ORDER BY path
LIMIT 100;

-- Regex grep candidate generation. This should use content gin_trgm_ops when
-- extractable trigrams exist.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT path
FROM public.vfs_entries
WHERE kind = 'file'
  AND deleted_at IS NULL
  AND content IS NOT NULL
  AND content ~ 'Postgres(FileSystem|Backend)'
ORDER BY path
LIMIT 100;

-- Anchored line-style regex candidate generation. (?n) makes PostgreSQL ARE
-- newline-sensitive, so ^/$ can match around newlines instead of only the
-- beginning/end of the full file content.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT path
FROM public.vfs_entries
WHERE kind = 'file'
  AND deleted_at IS NULL
  AND content IS NOT NULL
  AND content ~ '(?n)^class[[:space:]]+Test'
ORDER BY path
LIMIT 100;

-- Weak regex: useful as a warning case. Patterns with no extractable trigrams
-- can degenerate toward broad index scans or sequential work.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT path
FROM public.vfs_entries
WHERE kind = 'file'
  AND deleted_at IS NULL
  AND content IS NOT NULL
  AND content ~ '^[[:space:]]*$'
ORDER BY path
LIMIT 100;
