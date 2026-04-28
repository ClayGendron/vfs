-- Schema for Postgres-backed grep/glob candidate pushdown.
--
-- Run against:
--   psql -h localhost -d git_repos_vfs -f "grep_glob research/schema.sql"
--
-- For large content indexes on local machines, prefer:
--   psql "host=localhost dbname=git_repos_vfs options='-c max_parallel_maintenance_workers=0 -c maintenance_work_mem=128MB'" \
--     -f "grep_glob research/schema.sql"

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_vfs_entries_path_pattern_live
ON public.vfs_entries (path text_pattern_ops)
WHERE deleted_at IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_vfs_entries_path_trgm_live_gin
ON public.vfs_entries USING GIN (path gin_trgm_ops)
WHERE deleted_at IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_vfs_entries_content_trgm_live_file_gin
ON public.vfs_entries USING GIN (content gin_trgm_ops)
WHERE kind = 'file'
  AND content IS NOT NULL
  AND deleted_at IS NULL;

ANALYZE public.vfs_entries;
