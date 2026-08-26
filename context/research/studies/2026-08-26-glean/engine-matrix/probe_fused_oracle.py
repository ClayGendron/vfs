"""Fused statement on Oracle 26ai Free (regular image): VECTOR_DISTANCE leg + Oracle Text CONTAINS/SCORE leg + RRF.

Also probes HNSW index DDL (vector pool), FETCH APPROX, the hybrid vector index
(does it accept external embeddings?), DBMS_HYBRID_VECTOR presence, and dimension caps.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from corpus import as_json, build  # noqa: E402
from probe_common import dump, run  # noqa: E402

ents, chunks, qvec, scope = build()

VEC_LEG = """
  SELECT c.id AS chunk_id, c.entry_id, VECTOR_DISTANCE(c.embedding, TO_VECTOR(:q), COSINE) AS dist
  FROM glean_chunks c JOIN glean_entries e ON e.id = c.entry_id
  WHERE e.id IN :ids
  ORDER BY dist FETCH FIRST :kv ROWS ONLY
"""
LEX_LEG = """
  SELECT c.id AS chunk_id, c.entry_id, SCORE(1) AS score
  FROM glean_chunks c JOIN glean_entries e ON e.id = c.entry_id
  WHERE e.id IN :ids AND CONTAINS(c.content, :qt, 1) > 0
  ORDER BY score DESC FETCH FIRST :kl ROWS ONLY
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
FROM per_chunk GROUP BY entry_id ORDER BY score DESC, entry_id FETCH FIRST :n ROWS ONLY
"""
PARAMS = {"ids": scope, "q": as_json(qvec), "qt": "lantern", "kv": 20, "kl": 20, "k": 60, "n": 5}


async def main():
    out = {}
    out["system"] = await run("oracle_regular_system", [
        ("ctxsys", "select count(*) from all_users where username='CTXSYS'"),
        ("grant", "grant ctxapp to vfs"),
        ("vector_pool", "select name, value from v$parameter where name in ('vector_memory_size','sga_target')"),
        ("hybrid_pkg", "select owner, object_type from all_objects where object_name='DBMS_HYBRID_VECTOR'"),
        ("version", "select banner_full from v$version"),
    ])
    steps = [
        ("drop_c", "begin execute immediate 'drop table glean_chunks purge'; exception when others then null; end;"),
        ("drop_e", "begin execute immediate 'drop table glean_entries purge'; exception when others then null; end;"),
        ("entries", "create table glean_entries (id number primary key, path varchar2(400) not null)"),
        ("chunks", "create table glean_chunks (id number primary key, entry_id number not null, chunk_index number, "
                   "content clob, embedding vector(8, float32))"),
        ("ctx", "create index glean_ctx on glean_chunks (content) indextype is ctxsys.context parameters ('sync (on commit)')"),
    ]
    steps += [("ins_e", "insert into glean_entries values (:id, :path)", [{"id": i, "path": p} for i, p in ents])]
    steps += [("ins_c", "insert into glean_chunks values (:id, :eid, :ci, :content, to_vector(:emb))",
               [{"id": c[0], "eid": c[1], "ci": c[2], "content": c[3], "emb": as_json(c[4])} for c in chunks])]
    steps += [
        ("commit", "commit"),
        ("sync", "begin ctx_ddl.sync_index('glean_ctx'); end;"),
        ("score_probe", "select id, score(1) from glean_chunks where contains(content, 'lantern', 1) > 0 order by score(1) desc fetch first 3 rows only"),
        ("fused", FUSED, PARAMS, ["ids"]),
        ("plan", "explain plan for " + FUSED, PARAMS, ["ids"]),
        ("plan_out", "select plan_table_output from table(dbms_xplan.display(null, null, 'BASIC'))"),
        ("hnsw", "create vector index glean_hnsw on glean_chunks (embedding) organization inmemory neighbor graph "
                 "distance cosine with target accuracy 95"),
        ("approx", "select id from glean_chunks order by vector_distance(embedding, to_vector(:q), cosine) "
                   "fetch approx first 5 rows only with target accuracy 90", {"q": as_json(qvec)}),
        ("approx_scoped", "select id from glean_chunks where entry_id in :ids order by vector_distance(embedding, to_vector(:q), cosine) "
                   "fetch approx first 5 rows only with target accuracy 90", {"q": as_json(qvec), "ids": scope}, ["ids"]),
        ("plan_approx", "explain plan for select id from glean_chunks order by vector_distance(embedding, to_vector(:q), cosine) "
                   "fetch approx first 5 rows only with target accuracy 90", {"q": as_json(qvec)}),
        ("plan_approx_out", "select plan_table_output from table(dbms_xplan.display(null, null, 'BASIC'))"),
        ("hybrid_idx_no_model", "create hybrid vector index glean_hyb on glean_chunks (content) parameters ('vector_idxtype ivf')"),
        ("hybrid_idx_ext_vec", "create hybrid vector index glean_hyb2 on glean_chunks (embedding) parameters ('vector_idxtype ivf')"),
        ("dbms_hybrid_search", "select dbms_hybrid_vector.search(json('{\"hybrid_index_name\":\"glean_hyb\",\"search_text\":\"lantern\"}')) from dual"),
        ("max_dim", "create table glean_big (id number primary key, v vector(65535, float32))"),
        ("max_dim_drop", "drop table glean_big purge"),
        ("over_dim", "create table glean_big2 (id number primary key, v vector(65536, float32))"),
        ("drop_c2", "drop table glean_chunks purge"),
        ("drop_e2", "drop table glean_entries purge"),
    ]
    out["vfs"] = await run("oracle_regular", steps)
    dump(__file__.rsplit("/", 1)[0] + "/results_fused_oracle.json", out)


asyncio.run(main())
