"""Fused statement on Postgres + pgvector: vector CTE + lexical CTE + RRF + scope + MaxP + LIMIT."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from corpus import as_json, build  # noqa: E402
from probe_common import dump, run  # noqa: E402

ents, chunks, qvec, scope = build()

FUSED = """
WITH scope AS (
  SELECT id FROM glean_entries WHERE id IN :ids
), vec_top AS (
  SELECT c.id AS chunk_id, c.entry_id, c.embedding <=> CAST(:q AS vector) AS dist
  FROM glean_chunks c JOIN scope s ON s.id = c.entry_id
  WHERE c.embedding IS NOT NULL
  ORDER BY dist LIMIT :kv
), vec AS (
  SELECT chunk_id, entry_id, ROW_NUMBER() OVER (ORDER BY dist) AS rnk FROM vec_top
), lex_top AS (
  SELECT c.id AS chunk_id, c.entry_id,
         ts_rank_cd(c.tsv, plainto_tsquery('english', :qt)) AS score
  FROM glean_chunks c JOIN scope s ON s.id = c.entry_id
  WHERE c.tsv @@ plainto_tsquery('english', :qt)
  ORDER BY score DESC LIMIT :kl
), lex AS (
  SELECT chunk_id, entry_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rnk FROM lex_top
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

PARAMS = {"ids": scope, "q": as_json(qvec), "qt": "lantern", "kv": 20, "kl": 20, "k": 60, "n": 5}


async def main():
    steps = [
        ("ext", "create extension if not exists vector"),
        ("drop_c", "drop table if exists glean_chunks"),
        ("drop_e", "drop table if exists glean_entries"),
        ("entries", "create table glean_entries (id int primary key, path text not null)"),
        ("chunks", "create table glean_chunks (id int primary key, entry_id int references glean_entries(id), "
                   "chunk_index int, content text, embedding vector(8), "
                   "tsv tsvector generated always as (to_tsvector('english', content)) stored)"),
        ("gin", "create index glean_chunks_tsv on glean_chunks using gin (tsv)"),
        ("hnsw", "create index glean_chunks_hnsw on glean_chunks using hnsw (embedding vector_cosine_ops)"),
    ]
    steps += [(f"ins_e", "insert into glean_entries values " + ",".join(f"({i},'{p}')" for i, p in ents))]
    steps += [("ins_c", "insert into glean_chunks (id, entry_id, chunk_index, content, embedding) values " +
               ",".join(f"({c[0]},{c[1]},{c[2]},'{c[3]}','{as_json(c[4])}')" for c in chunks))]
    steps += [
        ("fused", FUSED, PARAMS, ["ids"]),
        ("fused_explain", "EXPLAIN (COSTS OFF) " + FUSED, PARAMS, ["ids"]),
        ("vector_only_explain",
         "EXPLAIN (COSTS OFF) SELECT id FROM glean_chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT 20",
         {"q": as_json(qvec)}),
        ("drop_c2", "drop table glean_chunks"),
        ("drop_e2", "drop table glean_entries"),
    ]
    res = await run("pgvector", steps)
    dump(__file__.rsplit("/", 1)[0] + "/results_fused_pg.json", res)


asyncio.run(main())
