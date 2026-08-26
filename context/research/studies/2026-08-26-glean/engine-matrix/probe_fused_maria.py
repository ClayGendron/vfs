"""Fused statement on MariaDB 11.8 (VEC_DISTANCE_COSINE + InnoDB FULLTEXT) and MySQL 9 (lexical leg only)."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from corpus import as_json, build  # noqa: E402
from probe_common import dump, run  # noqa: E402

ents, chunks, qvec, scope = build()

VEC_LEG = """
  SELECT c.id AS chunk_id, c.entry_id, VEC_DISTANCE_COSINE(c.embedding, VEC_FromText(:q)) AS dist
  FROM glean_chunks c JOIN glean_entries e ON e.id = c.entry_id
  WHERE e.id IN :ids
  ORDER BY dist LIMIT :kv
"""
LEX_LEG = """
  SELECT c.id AS chunk_id, c.entry_id, MATCH(c.content) AGAINST (:qt IN NATURAL LANGUAGE MODE) AS score
  FROM glean_chunks c JOIN glean_entries e ON e.id = c.entry_id
  WHERE e.id IN :ids AND MATCH(c.content) AGAINST (:qt IN NATURAL LANGUAGE MODE)
  ORDER BY score DESC LIMIT :kl
"""
FUSED = f"""
WITH vec_top AS ({VEC_LEG}), vec AS (
  SELECT chunk_id, entry_id, ROW_NUMBER() OVER (ORDER BY dist) AS rnk FROM vec_top
), lex_top AS ({LEX_LEG}), lex AS (
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
LEX_ONLY = f"""
WITH lex_top AS ({LEX_LEG})
SELECT chunk_id, entry_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rnk, score FROM lex_top
"""
PARAMS = {"ids": scope, "q": as_json(qvec), "qt": "lantern", "kv": 20, "kl": 20, "k": 60, "n": 5}


def ddl(vector: bool):
    emb = "embedding VECTOR(8) NOT NULL, VECTOR INDEX (embedding) DISTANCE=cosine" if vector else "embedding VECTOR(8)"
    return [
        ("drop_c", "drop table if exists glean_chunks"),
        ("drop_e", "drop table if exists glean_entries"),
        ("entries", "create table glean_entries (id int primary key, path varchar(255) not null) engine=innodb"),
        ("chunks", f"create table glean_chunks (id int primary key, entry_id int not null, chunk_index int, "
                   f"content text, {emb}, fulltext (content), key (entry_id)) engine=innodb"),
        ("ins_e", "insert into glean_entries values " + ",".join(f"({i},'{p}')" for i, p in ents)),
    ]


async def main():
    out = {}
    fn = "VEC_FromText" 
    steps = ddl(True) + [
        ("ins_c", "insert into glean_chunks (id, entry_id, chunk_index, content, embedding) values " +
         ",".join(f"({c[0]},{c[1]},{c[2]},'{c[3]}',{fn}('{as_json(c[4])}'))" for c in chunks)),
        ("fused", FUSED, PARAMS, ["ids"]),
        ("explain_fused", "EXPLAIN " + FUSED, PARAMS, ["ids"]),
        ("explain_vec_unscoped",
         "EXPLAIN SELECT id FROM glean_chunks ORDER BY VEC_DISTANCE_COSINE(embedding, VEC_FromText(:q)) LIMIT 20",
         {"q": as_json(qvec)}),
        ("explain_vec_scoped_where",
         "EXPLAIN SELECT id FROM glean_chunks WHERE entry_id IN :ids "
         "ORDER BY VEC_DISTANCE_COSINE(embedding, VEC_FromText(:q)) LIMIT 20", {"q": as_json(qvec), "ids": scope}, ["ids"]),
        ("big_dim", "create table glean_big (id int primary key, v vector(16383) not null)"),
        ("big_dim_drop", "drop table if exists glean_big"),
        ("too_big_dim", "create table glean_big2 (id int primary key, v vector(65536) not null)"),
        ("too_big_drop", "drop table if exists glean_big2"),
        ("drop_c2", "drop table glean_chunks"),
        ("drop_e2", "drop table glean_entries"),
    ]
    out["mariadb118"] = await run("mariadb118", steps)
    steps = ddl(False) + [
        ("ins_c", "insert into glean_chunks (id, entry_id, chunk_index, content, embedding) values " +
         ",".join(f"({c[0]},{c[1]},{c[2]},'{c[3]}',STRING_TO_VECTOR('{as_json(c[4])}'))" for c in chunks)),
        ("fused_should_fail", FUSED, PARAMS, ["ids"]),
        ("lex_only", LEX_ONLY, PARAMS, ["ids"]),
        ("explain_lex", "EXPLAIN " + LEX_ONLY, PARAMS, ["ids"]),
        ("max_dim", "create table glean_big (id int primary key, v vector(16383))"),
        ("max_dim_drop", "drop table if exists glean_big"),
        ("drop_c2", "drop table glean_chunks"),
        ("drop_e2", "drop table glean_entries"),
    ]
    out["mysql9"] = await run("mysql9", steps)
    dump(__file__.rsplit("/", 1)[0] + "/results_fused_maria_mysql.json", out)


asyncio.run(main())
