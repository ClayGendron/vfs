"""Oracle 26ai Free with a vector pool: HNSW DDL, FETCH APPROX plans (scoped/unscoped), hybrid index without a model."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from corpus import as_json, build  # noqa: E402
from probe_common import dump, run  # noqa: E402

ents, chunks, qvec, scope = build()
APPROX = ("select id from glean_chunks order by vector_distance(embedding, to_vector(:q), cosine) "
          "fetch approx first 5 rows only with target accuracy 90")
APPROX_SCOPED = ("select id from glean_chunks where entry_id in :ids order by vector_distance(embedding, to_vector(:q), cosine) "
                 "fetch approx first 5 rows only with target accuracy 90")
PLAN_OUT = "select plan_table_output from table(dbms_xplan.display(null, null, 'BASIC'))"


async def main():
    out = {}
    out["system"] = await run("oracle_regular_system", [
        ("vector_pool", "select name, value from v$parameter where name = 'vector_memory_size'"),
        ("grant_cat", "grant select_catalog_role to vfs"),
    ])
    steps = [
        ("drop_c", "begin execute immediate 'drop table glean_chunks purge'; exception when others then null; end;"),
        ("chunks", "create table glean_chunks (id number primary key, entry_id number not null, chunk_index number, "
                   "content clob, embedding vector(8, float32))"),
        ("ins_c", "insert into glean_chunks values (:id, :eid, :ci, :content, to_vector(:emb))",
         [{"id": c[0], "eid": c[1], "ci": c[2], "content": c[3], "emb": as_json(c[4])} for c in chunks]),
        ("commit", "commit"),
        ("hnsw", "create vector index glean_hnsw on glean_chunks (embedding) organization inmemory neighbor graph "
                 "distance cosine with target accuracy 95"),
        ("approx", APPROX, {"q": as_json(qvec)}),
        ("hnsw_cursor_plan", "select plan_table_output from table(dbms_xplan.display_cursor(null, null, 'BASIC'))"),
        ("approx_scoped", APPROX_SCOPED, {"q": as_json(qvec), "ids": scope}, ["ids"]),
        ("hnsw_scoped_cursor_plan", "select plan_table_output from table(dbms_xplan.display_cursor(null, null, 'BASIC'))"),
        ("exact_scoped", "select id from glean_chunks where entry_id in :ids order by vector_distance(embedding, to_vector(:q), cosine) "
                         "fetch first 5 rows only", {"q": as_json(qvec), "ids": scope}, ["ids"]),
        ("drop_hnsw", "drop index glean_hnsw"),
        ("ivf", "create vector index glean_ivf on glean_chunks (embedding) organization neighbor partitions "
                "distance cosine with target accuracy 95 parameters (type ivf, neighbor partitions 4)"),
        ("ivf_approx", APPROX, {"q": as_json(qvec)}),
        ("ivf_cursor_plan", "select plan_table_output from table(dbms_xplan.display_cursor(null, null, 'BASIC'))"),
        ("ivf_approx_scoped", APPROX_SCOPED, {"q": as_json(qvec), "ids": scope}, ["ids"]),
        ("ivf_scoped_cursor_plan", "select plan_table_output from table(dbms_xplan.display_cursor(null, null, 'BASIC'))"),
        ("drop_ivf", "drop index glean_ivf"),
        ("hybrid_no_model", "create hybrid vector index glean_hyb on glean_chunks (content) parameters ('vector_idxtype ivf')"),
        ("hybrid_search", "select dbms_hybrid_vector.search(json('{\"hybrid_index_name\":\"glean_hyb\",\"search_text\":\"lantern\"}')) from dual"),
        ("drop_c2", "drop table glean_chunks purge"),
    ]
    out["vfs"] = await run("oracle_regular", steps)
    dump(__file__.rsplit("/", 1)[0] + "/results_oracle_hnsw.json", out)


asyncio.run(main())
