-- Which index keeps a listing page bounded on Postgres 16: composite or partial.
DROP TABLE IF EXISTS vfs_entries;
CREATE TABLE vfs_entries (
    id bigserial PRIMARY KEY,
    entry_id varchar(26) NOT NULL UNIQUE,
    parent_id varchar(26),
    path varchar(1024) COLLATE "C" NOT NULL UNIQUE,
    name varchar(255) COLLATE "C" NOT NULL,
    kind varchar(16) NOT NULL,
    mime_type varchar(64),
    content_hash varchar(64),
    size_bytes bigint,
    everyone_level smallint NOT NULL DEFAULT 0,
    owner_id varchar(255),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    deleted_at timestamptz,
    trash_root_id varchar(26),
    CONSTRAINT uq_vfs_entries_parent_name UNIQUE (parent_id, name)
);
CREATE INDEX ix_vfs_entries_deleted_at ON vfs_entries (deleted_at);
CREATE INDEX ix_vfs_entries_everyone_path ON vfs_entries (everyone_level, path);

INSERT INTO vfs_entries (entry_id, parent_id, path, name, kind) VALUES ('root', NULL, '/', '', 'directory');
INSERT INTO vfs_entries (entry_id, parent_id, path, name, kind)
SELECT 'dir' || d, 'root', '/' || d, d, 'directory' FROM unnest(ARRAY['big', 'd', 's']) AS d;
INSERT INTO vfs_entries (entry_id, parent_id, path, name, kind, mime_type, content_hash, size_bytes)
SELECT 'big' || i, 'dirbig', '/big/f' || lpad(i::text, 5, '0') || '.txt', 'f' || lpad(i::text, 5, '0') || '.txt', 'file', 'text/plain', md5(i::text), 1
FROM generate_series(0, 9999) AS i;
INSERT INTO vfs_entries (entry_id, parent_id, path, name, kind, mime_type, content_hash, size_bytes, deleted_at)
SELECT 'd' || i, 'dird', '/d/f' || lpad(i::text, 5, '0') || '.txt', 'f' || lpad(i::text, 5, '0') || '.txt', 'file', 'text/plain', md5(i::text), 1,
       CASE WHEN i < 900 THEN now() END
FROM generate_series(0, 999) AS i;
INSERT INTO vfs_entries (entry_id, parent_id, path, name, kind, mime_type, content_hash, size_bytes, deleted_at)
SELECT 's' || i, 'dirs', '/s/f' || lpad(i::text, 5, '0') || '.txt', 'f' || lpad(i::text, 5, '0') || '.txt', 'file', 'text/plain', md5(i::text), 1,
       CASE WHEN i % 10 <> 0 THEN now() END
FROM generate_series(0, 999) AS i;
-- The rest of a corpus: 200,000 rows in 2,000 directories, a twentieth of them deleted.
INSERT INTO vfs_entries (entry_id, parent_id, path, name, kind)
SELECT 'n' || j, 'root', '/n' || lpad(j::text, 4, '0'), 'n' || lpad(j::text, 4, '0'), 'directory' FROM generate_series(0, 1999) AS j;
INSERT INTO vfs_entries (entry_id, parent_id, path, name, kind, mime_type, content_hash, size_bytes, deleted_at)
SELECT 'x' || i, 'n' || (i / 100), '/n' || lpad((i / 100)::text, 4, '0') || '/x' || i, 'x' || i, 'file', 'text/plain', md5(i::text), 1,
       CASE WHEN i % 20 = 0 THEN now() END
FROM generate_series(0, 199999) AS i;
ANALYZE vfs_entries;
