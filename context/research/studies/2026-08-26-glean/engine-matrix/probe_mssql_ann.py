"""SQL Server 2025 (on-prem CU8): DiskANN vector index + VECTOR_SEARCH with the TOP_N syntax, scoped and unscoped."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from corpus import as_json, build  # noqa: E402
from probe_common import dump, run  # noqa: E402

ents, chunks, qvec, scope = build()
DECL = "declare @qv vector(8) = cast(:q as vector(8)); "
VS = ("from vector_search(table = glean_chunks as t, column = embedding, similar_to = @qv, "
      "metric='cosine', top_n = 5) as r")


async def main():
    steps = [
        ("drop_c", "if object_id('glean_chunks') is not null drop table glean_chunks"),
        ("chunks", "create table glean_chunks (id int not null primary key, entry_id int not null, chunk_index int, "
                   "content nvarchar(max), embedding vector(8))"),
    ]
    for i in range(0, len(chunks), 200):
        steps.append((f"ins_c{i}", "insert into glean_chunks values " +
                      ",".join(f"({c[0]},{c[1]},{c[2]},'{c[3]}','{as_json(c[4])}')" for c in chunks[i:i+200])))
    steps += [
        ("preview_on", "alter database scoped configuration set preview_features = on"),
        ("vec_index", "create vector index glean_vidx on glean_chunks (embedding) with (metric='cosine', type='diskann')"),
        ("index_meta", "select i.name, i.type_desc from sys.indexes i where i.object_id=object_id('glean_chunks')"),
        ("exact_top5", "select top (5) id, vector_distance('cosine', embedding, cast(:q as vector(8))) d from glean_chunks order by d",
         {"q": as_json(qvec)}),
        ("vs_top_n", DECL + "select t.id, r.distance " + VS + " order by r.distance", {"q": as_json(qvec)}),
        ("vs_scoped_postfilter", DECL + "select t.id, r.distance " + VS + " where t.entry_id in :ids order by r.distance",
         {"q": as_json(qvec), "ids": scope}, ["ids"]),
        ("vs_in_cte", DECL + "with v as (select t.id, r.distance " + VS + ") select id, row_number() over (order by distance) rnk from v",
         {"q": as_json(qvec)}),
        ("dml_after_index", "update glean_chunks set chunk_index = chunk_index where id = 1"),
        ("insert_after_index", "insert into glean_chunks values (9999, 1, 9, 'x', '[0,0,0,0,0,0,0,1]')"),
        ("vs_plan", DECL + "set showplan_text off; select t.id, r.distance " + VS + " order by r.distance option (recompile)", {"q": as_json(qvec)}),
        ("drop_vidx", "drop index glean_vidx on glean_chunks"),
        ("drop_c2", "drop table glean_chunks"),
        ("preview_off", "alter database scoped configuration set preview_features = off"),
    ]
    res = await run("mssql2025_glean", steps)
    dump(__file__.rsplit("/", 1)[0] + "/results_mssql_ann.json", res)


asyncio.run(main())
