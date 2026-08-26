"""pgvector at 50k chunks: does the planner keep HNSW when a scope predicate is present? Plus dimension caps."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from probe_common import dump, run  # noqa: E402

Q = "[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8]"
VEC_IN = ("SELECT c.id, c.embedding <=> CAST(:q AS vector) AS dist FROM glean_chunks c "
          "WHERE c.entry_id IN :ids ORDER BY dist LIMIT 20")
VEC_RANGE = ("SELECT c.id, c.embedding <=> CAST(:q AS vector) AS dist FROM glean_chunks c "
             "WHERE c.entry_id BETWEEN :lo AND :hi ORDER BY dist LIMIT 20")
VEC_JOIN = ("SELECT c.id, c.embedding <=> CAST(:q AS vector) AS dist FROM glean_chunks c "
            "JOIN glean_entries e ON e.id = c.entry_id WHERE e.path LIKE :pfx ORDER BY dist LIMIT 20")


async def main():
    small = list(range(1, 5001, 500))  # 10 entries -> 100 chunks
    steps = [
        ("entries", "create table glean_entries (id int primary key, path text not null)"),
        ("chunks", "create table glean_chunks (id int primary key, entry_id int not null, embedding vector(8))"),
        ("ins_e", "insert into glean_entries select g, 'src/mod' || (g % 10) || '/file' || g || '.py' from generate_series(1, 5000) g"),
        ("ins_c", "insert into glean_chunks select g, (g - 1) / 10 + 1, "
                  "('[' || array_to_string(array(select random() from generate_series(1, 8)), ',') || ']')::vector "
                  "from generate_series(1, 50000) g"),
        ("hnsw", "create index glean_chunks_hnsw on glean_chunks using hnsw (embedding vector_cosine_ops)"),
        ("eidx", "create index on glean_chunks (entry_id)"),
        ("pidx", "create index on glean_entries (path text_pattern_ops)"),
        ("analyze", "analyze glean_chunks; analyze glean_entries"),
        ("plan_small_scope", "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) " + VEC_IN, {"q": Q, "ids": small}, ["ids"]),
        ("plan_half_scope", "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) " + VEC_RANGE, {"q": Q, "lo": 1, "hi": 2500}),
        ("plan_join_scope", "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) " + VEC_JOIN, {"q": Q, "pfx": "src/mod3/%"}),
        ("iter", "set hnsw.iterative_scan = relaxed_order"),
        ("plan_half_scope_iter", "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) " + VEC_RANGE, {"q": Q, "lo": 1, "hi": 2500}),
        ("plan_join_scope_iter", "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) " + VEC_JOIN, {"q": Q, "pfx": "src/mod3/%"}),
        ("plan_small_scope_iter", "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) " + VEC_IN, {"q": Q, "ids": small}, ["ids"]),
        ("dim_16000", "create table glean_big (id int primary key, v vector(16000))"),
        ("dim_16001", "create table glean_big2 (id int primary key, v vector(16001))"),
        ("hnsw_2001", "create table glean_big3 (id int primary key, v vector(2001)); "
                      "create index on glean_big3 using hnsw (v vector_cosine_ops)"),
        ("halfvec_hnsw_4000", "create table glean_big4 (id int primary key, v halfvec(4000)); "
                              "create index on glean_big4 using hnsw (v halfvec_cosine_ops)"),
        ("cleanup", "drop table if exists glean_big, glean_big2, glean_big3, glean_big4, glean_chunks, glean_entries"),
    ]
    res = await run("pgvector", steps)
    dump(__file__.rsplit("/", 1)[0] + "/results_pg_scale.json", res)


asyncio.run(main())
