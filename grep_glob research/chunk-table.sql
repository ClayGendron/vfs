-- Optional maximum-query-time optimization: file chunk candidate table.
--
-- This is not a line-level table. It stores newline-aligned file chunks so
-- trigram and regex predicates can narrow candidate files without scanning the
-- full 1.7 GB content corpus on every grep.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS public.vfs_entry_chunks (
  entry_id varchar(36) NOT NULL,
  path varchar(1024) NOT NULL,
  ext varchar(32),
  chunk_no integer NOT NULL,
  line_start integer NOT NULL,
  line_end integer NOT NULL,
  content text NOT NULL,
  content_hash varchar(64),
  updated_at timestamp with time zone,
  PRIMARY KEY (entry_id, chunk_no)
);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_vfs_entry_chunks_path_pattern
ON public.vfs_entry_chunks (path text_pattern_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_vfs_entry_chunks_path_trgm_gin
ON public.vfs_entry_chunks USING GIN (path gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_vfs_entry_chunks_ext_path
ON public.vfs_entry_chunks (ext, path);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_vfs_entry_chunks_content_trgm_gin
ON public.vfs_entry_chunks USING GIN (content gin_trgm_ops);

ANALYZE public.vfs_entry_chunks;

-- Candidate examples:
--
-- Fixed-string grep:
-- SELECT DISTINCT entry_id, path
-- FROM public.vfs_entry_chunks
-- WHERE content LIKE '%Postgres%' ESCAPE '\';
--
-- Case-insensitive grep:
-- SELECT DISTINCT entry_id, path
-- FROM public.vfs_entry_chunks
-- WHERE content ILIKE '%postgres%' ESCAPE '\';
--
-- Line-anchor-aware regex grep. The (?n) embedded option makes ^/$ newline
-- sensitive and keeps . from crossing newlines.
-- SELECT DISTINCT entry_id, path
-- FROM public.vfs_entry_chunks
-- WHERE content ~ '(?n)^class[[:space:]]+Postgres';
