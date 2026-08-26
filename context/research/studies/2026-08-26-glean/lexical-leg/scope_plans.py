"""Diagnose the scope-driven statement: EXPLAIN QUERY PLAN and alternative shapes.

    uv run python context/research/studies/2026-08-26-glean/lexical-leg/scope_plans.py --corpus ~/Git/Repos/linux/drivers/gpu --max-chunks 10000
"""

from __future__ import annotations

import argparse
import random
import statistics
import time
from pathlib import Path as FsPath

from build_and_time import EPOCH, build_index, load_corpus, pick_queries

SHAPES = {
    "term_driven_join_ids": (
        "SELECT t.chunk_id, SUM(t.weight) AS score FROM lex_terms t "
        "JOIN lex_docs sd ON sd.epoch = t.epoch AND sd.chunk_id = t.chunk_id AND sd.entry_id IN ({ids}) "
        "WHERE t.epoch = ? AND t.term IN ({terms}) GROUP BY t.chunk_id ORDER BY score DESC, t.chunk_id LIMIT 10"
    ),
    "scope_driven_join": (
        "SELECT t.chunk_id, SUM(t.weight) AS score FROM lex_docs sd "
        "JOIN lex_terms t ON t.epoch = sd.epoch AND t.chunk_id = sd.chunk_id "
        "WHERE sd.epoch = ? AND sd.entry_id IN ({ids}) AND t.term IN ({terms}) "
        "GROUP BY t.chunk_id ORDER BY score DESC, t.chunk_id LIMIT 10"
    ),
    "term_driven_semijoin": (
        "SELECT t.chunk_id, SUM(t.weight) AS score FROM lex_terms t "
        "WHERE t.epoch = ? AND t.term IN ({terms}) "
        "AND t.chunk_id IN (SELECT chunk_id FROM lex_docs WHERE epoch = ? AND entry_id IN ({ids})) "
        "GROUP BY t.chunk_id ORDER BY score DESC, t.chunk_id LIMIT 10"
    ),
    "scope_driven_pk_probe": (
        "SELECT t.chunk_id, SUM(t.weight) AS score FROM lex_docs sd "
        "CROSS JOIN lex_terms t ON t.epoch = sd.epoch AND t.chunk_id = sd.chunk_id AND t.term IN ({terms}) "
        "WHERE sd.epoch = ? AND sd.entry_id IN ({ids}) "
        "GROUP BY t.chunk_id ORDER BY score DESC, t.chunk_id LIMIT 10"
    ),
}


def params(shape: str, ids: list[int], terms: list[str]) -> tuple:
    if shape == "term_driven_join_ids":
        return (*ids, EPOCH, *terms)
    if shape == "scope_driven_join":
        return (EPOCH, *ids, *terms)
    if shape == "term_driven_semijoin":
        return (EPOCH, *terms, EPOCH, *ids)
    return (*terms, EPOCH, *ids)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--max-chunks", type=int, default=10000)
    ap.add_argument("--no-analyze", action="store_true")
    args = ap.parse_args()
    rng = random.Random(7)
    entries, _ = load_corpus(FsPath(args.corpus).expanduser(), args.max_chunks, None)
    con, stats, *_ = build_index(entries)
    con.execute("CREATE INDEX ix_lex_terms_chunk ON lex_terms(epoch, chunk_id)")
    if not args.no_analyze:
        con.execute("ANALYZE")
    n_entries = len(entries)
    print(f"chunks={stats['n_chunks']} entries={n_entries} rows={stats['n_terms_rows']}")
    queries = pick_queries(con, stats["n_chunks"], rng, per_arity=10)
    for width_label, frac in (("5%", 0.05), ("0.5%", 0.005)):
        ids = sorted(rng.sample(range(1, n_entries + 1), max(1, int(n_entries * frac))))
        print(f"\n== allow-list {width_label}: {len(ids)} entries ==")
        for shape, template in SHAPES.items():
            for arity in (1, 3, 6):
                ms = []
                for terms in queries[arity]:
                    sql = template.format(ids=",".join("?" * len(ids)), terms=",".join("?" * len(terms)))
                    p = params(shape, ids, terms)
                    reps = []
                    for _ in range(3):
                        t0 = time.perf_counter()
                        con.execute(sql, p).fetchall()
                        reps.append(time.perf_counter() - t0)
                    ms.append(statistics.median(reps) * 1000)
                print(f"{shape:24s} arity={arity} median={statistics.median(ms):9.3f} ms max={max(ms):9.3f} ms")
            sql = template.format(ids=",".join("?" * len(ids)), terms=",".join("?" * 3))
            plan = con.execute("EXPLAIN QUERY PLAN " + sql, params(shape, ids, queries[3][0])).fetchall()
            for row in plan:
                print("    plan:", row[-1])


if __name__ == "__main__":
    main()
