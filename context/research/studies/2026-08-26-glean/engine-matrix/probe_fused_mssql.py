"""Fused statement on SQL Server 2025: VECTOR_DISTANCE leg + CONTAINSTABLE/FREETEXTTABLE leg + RRF + scope + MaxP + TOP.

Also probes the preview DiskANN path (PREVIEW_FEATURES, CREATE VECTOR INDEX, VECTOR_SEARCH)
and how pyodbc sees a VECTOR column on the wire.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from corpus import as_json, build  # noqa: E402
from probe_common import dump, run  # noqa: E402

ents, chunks, qvec, scope = build()

VEC_LEG = """
  SELECT TOP (:kv) c.id AS chunk_id, c.entry_id,
         VECTOR_DISTANCE('cosine', c.embedding, CAST(:q AS VECTOR(8))) AS dist
  FROM glean_chunks c JOIN glean_entries e ON e.id = c.entry_id
  WHERE e.id IN :ids
  ORDER BY dist
"""
LEX_LEG = """
  SELECT TOP (:kl) c.id AS chunk_id, c.entry_id, ft.[RANK] AS score
  FROM glean_chunks c
  JOIN FREETEXTTABLE(glean_chunks, content, :qt) AS ft ON ft.[KEY] = c.id
  JOIN glean_entries e ON e.id = c.entry_id
  WHERE e.id IN :ids
  ORDER BY score DESC
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
SELECT TOP (:n) entry_id, MAX(rrf) AS score, COUNT(*) AS chunks_hit
FROM per_chunk GROUP BY entry_id ORDER BY score DESC, entry_id
"""
PARAMS = {"ids": scope, "q": as_json(qvec), "qt": "lantern", "kv": 20, "kl": 20, "k": 60, "n": 5}


async def main():
    steps = [
        ("drop_c", "if object_id('glean_chunks') is not null drop table glean_chunks"),
        ("drop_e", "if object_id('glean_entries') is not null drop table glean_entries"),
        ("entries", "create table glean_entries (id int primary key, path nvarchar(400) not null)"),
        ("chunks", "create table glean_chunks (id int not null constraint pk_glean_chunks primary key, entry_id int not null, "
                   "chunk_index int, content nvarchar(max), embedding vector(8))"),
        ("catalog", "if not exists (select 1 from sys.fulltext_catalogs where name='glean_cat') create fulltext catalog glean_cat"),
        ("ftindex", "create fulltext index on glean_chunks (content language 1033) key index pk_glean_chunks on glean_cat with change_tracking auto"),
        ("ins_e", "insert into glean_entries values " + ",".join(f"({i},'{p}')" for i, p in ents)),
    ]
    for i in range(0, len(chunks), 200):
        steps.append((f"ins_c{i}", "insert into glean_chunks (id, entry_id, chunk_index, content, embedding) values " +
                      ",".join(f"({c[0]},{c[1]},{c[2]},'{c[3]}','{as_json(c[4])}')" for c in chunks[i:i+200])))
    steps += [
        ("wait_pop", "declare @i int = 0; while (fulltextcatalogproperty('glean_cat','PopulateStatus') <> 0 "
                     "or (select count(*) from glean_chunks c join freetexttable(glean_chunks, content, 'lantern') f on f.[KEY]=c.id) = 0) "
                     "and @i < 60 begin waitfor delay '00:00:01'; set @i += 1; end; select @i as waited_s"),
        ("wire_type", "select top 1 embedding from glean_chunks"),
        ("declared_type", "select t.name, c.max_length from sys.columns c join sys.types t on t.user_type_id=c.user_type_id where c.object_id=object_id('glean_chunks') and c.name='embedding'"),
        ("fused", FUSED, PARAMS, ["ids"]),
        ("contains_rank", "select top 3 c.id, ft.[RANK] from glean_chunks c join containstable(glean_chunks, content, 'lantern') ft on ft.[KEY]=c.id order by ft.[RANK] desc"),
        ("preview_on", "alter database scoped configuration set preview_features = on"),
        ("vec_index_8", "create vector index glean_vidx on glean_chunks (embedding) with (metric='cosine', type='diskann')"),
        ("vector_search", "select top (5) with approximate t.id, r.distance from vector_search(table = glean_chunks as t, column = embedding, "
                          "similar_to = cast(:q as vector(8)), metric='cosine') as r order by r.distance", {"q": as_json(qvec)}),
        ("vector_search_scoped", "select top (5) with approximate t.id, r.distance from vector_search(table = glean_chunks as t, column = embedding, "
                          "similar_to = cast(:q as vector(8)), metric='cosine') as r where t.entry_id in :ids order by r.distance",
         {"q": as_json(qvec), "ids": scope}, ["ids"]),
        ("max_dim", "create table glean_big (id int primary key, v vector(1998))"),
        ("max_dim_drop", "drop table glean_big"),
        ("over_dim", "create table glean_big2 (id int primary key, v vector(1999))"),
        ("drop_ft", "drop fulltext index on glean_chunks"),
        ("drop_c2", "drop table glean_chunks"),
        ("drop_e2", "drop table glean_entries"),
        ("drop_cat", "drop fulltext catalog glean_cat"),
        ("preview_off", "alter database scoped configuration set preview_features = off"),
    ]
    await run("mssql2025", [("mkdb", "if db_id('glean') is null create database glean")])
    res = await run("mssql2025_glean", steps)
    dump(__file__.rsplit("/", 1)[0] + "/results_fused_mssql.json", res)


asyncio.run(main())
