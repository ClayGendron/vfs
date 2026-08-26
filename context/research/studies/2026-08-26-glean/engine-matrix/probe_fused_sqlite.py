"""Fused statement on SQLite: FTS5 bm25() + sqlite-vec (vec0 KNN with rowid IN scope, and scalar vec_distance_cosine)."""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from corpus import as_json, build  # noqa: E402
from probe_common import dump, run  # noqa: E402

ents, chunks, qvec, scope = build()
DB = "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/9aca8a65-866f-4cbb-bc2b-685f1963370c/scratchpad/glean_probe.sqlite"

# Variant A: vec0 virtual table KNN with rowid-IN prefilter (scope pushed into the KNN).
FUSED_VEC0 = """
WITH scope AS (SELECT id FROM glean_entries WHERE id IN :ids),
vec_top AS (
  SELECT v.rowid AS chunk_id, c.entry_id, v.distance AS dist
  FROM glean_vec v JOIN glean_chunks c ON c.id = v.rowid
  WHERE v.embedding MATCH :q AND k = :kv
    AND v.rowid IN (SELECT id FROM glean_chunks WHERE entry_id IN (SELECT id FROM scope))
), vec AS (
  SELECT chunk_id, entry_id, ROW_NUMBER() OVER (ORDER BY dist) AS rnk FROM vec_top
), lex_top AS (
  SELECT f.rowid AS chunk_id, c.entry_id, bm25(glean_fts) AS score
  FROM glean_fts f JOIN glean_chunks c ON c.id = f.rowid
  WHERE glean_fts MATCH :qt
    AND f.rowid IN (SELECT id FROM glean_chunks WHERE entry_id IN (SELECT id FROM scope))
  ORDER BY score LIMIT :kl
), lex AS (
  SELECT chunk_id, entry_id, ROW_NUMBER() OVER (ORDER BY score) AS rnk FROM lex_top
), legs AS (
  SELECT chunk_id, entry_id, 1.0 / (:k + rnk) AS rrf FROM vec
  UNION ALL
  SELECT chunk_id, entry_id, 1.0 / (:k + rnk) AS rrf FROM lex
), per_chunk AS (
  SELECT chunk_id, entry_id, SUM(rrf) AS rrf FROM legs GROUP BY chunk_id, entry_id
)
SELECT entry_id, MAX(rrf) AS score, COUNT(*) AS chunks_hit
FROM per_chunk GROUP BY entry_id ORDER BY score DESC, entry_id LIMIT :n
"""
# Variant B: no vec0 -- scalar vec_distance_cosine over a BLOB column (exact scan in C, ordinary SQL joins).
FUSED_SCALAR = FUSED_VEC0.replace("""  SELECT v.rowid AS chunk_id, c.entry_id, v.distance AS dist
  FROM glean_vec v JOIN glean_chunks c ON c.id = v.rowid
  WHERE v.embedding MATCH :q AND k = :kv
    AND v.rowid IN (SELECT id FROM glean_chunks WHERE entry_id IN (SELECT id FROM scope))
""", """  SELECT c.id AS chunk_id, c.entry_id, vec_distance_cosine(c.embedding, :q) AS dist
  FROM glean_chunks c JOIN scope s ON s.id = c.entry_id
  ORDER BY dist LIMIT :kv
""")
PARAMS = {"ids": scope, "q": as_json(qvec), "qt": "lantern", "kv": 20, "kl": 20, "k": 60, "n": 5}


async def main():
    if os.path.exists(DB):
        os.remove(DB)
    steps = [
        ("entries", "create table glean_entries (id integer primary key, path text not null)"),
        ("chunks", "create table glean_chunks (id integer primary key, entry_id int not null, chunk_index int, "
                   "content text, embedding blob)"),
        ("fts", "create virtual table glean_fts using fts5(content, content='glean_chunks', content_rowid='id', "
                "tokenize='porter unicode61')"),
        ("vec0", "create virtual table glean_vec using vec0(embedding float[8] distance_metric=cosine)"),
        ("ins_e", "insert into glean_entries values " + ",".join(f"({i},'{p}')" for i, p in ents)),
        ("ins_c", "insert into glean_chunks values " +
         ",".join(f"({c[0]},{c[1]},{c[2]},'{c[3]}',vec_f32('{as_json(c[4])}'))" for c in chunks)),
        ("fts_rebuild", "insert into glean_fts(glean_fts) values ('rebuild')"),
        ("ins_vec", "insert into glean_vec(rowid, embedding) select id, embedding from glean_chunks"),
        ("fused_vec0", FUSED_VEC0, PARAMS, ["ids"]),
        ("fused_scalar", FUSED_SCALAR, PARAMS, ["ids"]),
        ("plan_vec0", "EXPLAIN QUERY PLAN " + FUSED_VEC0, PARAMS, ["ids"]),
        ("bm25_sign", "select rowid, bm25(glean_fts), rank from glean_fts where glean_fts match 'lantern' order by rank limit 3"),
    ]
    res = await run("sqlite", steps, sqlite_path=DB)
    dump(__file__.rsplit("/", 1)[0] + "/results_fused_sqlite.json", res)
    os.remove(DB)


asyncio.run(main())
