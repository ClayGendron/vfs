"""Spelling probe: the range branch and the derived count under each hint, with plans. SQL Server and Oracle.

    uv run --no-sync python probe.py --engine mssql --n 10000

Builds the world once, then times the ordinary caller's ``unionall`` statements under every
knob combination the dialect offers, printing plans. Writes ``runs/<engine>-probe.md``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pickle
import random
import time
from uuid import uuid4

from sqlalchemy import text

import bench
from bench import READ, Caller, Dialect, build, callers, compile_rights, load, make_engine, ms, public_level, recall, schema, statements, timed, write_lines

KNOBS = {
    "postgresql": [
        {"pg_nudge": False},
        {"pg_nudge": True},
    ],
    "mariadb": [
        {"mariadb_force": False, "plus_zero": False},
        {"mariadb_force": False, "plus_zero": True},
        {"mariadb_force": True, "plus_zero": False},
    ],
    "mssql": [
        {"apply": False, "loop_join": False, "force_order": False, "plus_zero": False},
        {"apply": False, "loop_join": False, "force_order": False, "plus_zero": True},
        {"apply": False, "loop_join": True, "force_order": False, "plus_zero": False},
        {"apply": True, "loop_join": False, "force_order": False, "plus_zero": False},
        {"apply": False, "loop_join": False, "force_order": True, "plus_zero": False},
    ],
    "oracle": [
        {"oracle_cardinality": False, "oracle_one_index": False, "oracle_derived_nl": False},
        {"oracle_cardinality": True, "oracle_one_index": False, "oracle_derived_nl": False},
        {"oracle_cardinality": True, "oracle_one_index": True, "oracle_derived_nl": False},
        {"oracle_cardinality": True, "oracle_one_index": True, "oracle_derived_nl": True},
        {"oracle_cardinality": False, "oracle_one_index": False, "oracle_derived_nl": False, "oracle_leading": True},
    ],
}


async def run(engine_name: str, n: int, reps: int) -> None:
    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    w = build(n)
    rows = [(rid, p, o, public_level(w.star, p)) for rid, p, o in w.rows]
    traps = {rid for rid, p, _ in w.rows if p.endswith("-x")}
    rng = random.Random(7)
    files = [rid for rid, p, _ in w.rows if p.endswith(".md")]
    scores = rng.sample(range(len(files) * 4), len(files))
    chunks = [(i, fid, scores[i]) for i, fid in enumerate(files)]  # one chunk per file
    score_of = {i: s for i, _, s in chunks}
    ns = f"ts_{uuid4().hex[:8]}_"
    md, entry, chunk = schema(ns)
    engine = make_engine(engine_name, None)
    d = Dialect(engine.dialect.name)
    cache = os.path.join(bench.SPIKE_SCRATCH, f"truth-{n}.pkl")
    with open(cache, "rb") as f:
        exact = pickle.load(f)
    spec = callers(w)["ordinary"]
    caller = Caller(compile_rights(w, spec["subjects"], READ), False, False)
    vis = exact["ordinary"]
    visible_chunks = [i for i, eid, _ in chunks if eid in vis]
    scope = ("/shared/s0001/", "/shared/s00010")
    in_scope = {rid for rid, p, _ in w.rows if scope[0] < p < scope[1]}
    truths = {"entries": vis, "scoped": vis & in_scope, "count": len(visible_chunks), "top10": set(sorted(visible_chunks, key=score_of.__getitem__)[:10])}
    try:
        say(f"## {engine_name} probe — N={n:,}, ordinary caller ({caller.pieces} pieces), {'disjoint' if d.name == 'postgresql' else 'unionall'} shape; warm = median of {reps}")
        say()
        secs = await load(engine, d, entry, chunk, rows, chunks)
        say(f"Load {secs:.0f}s.")
        say()
        say("| knobs | statement | cold / warm / recall |")
        say("|---|---|---|")
        plans = []
        for knobs in KNOBS[d.name]:
            for k, v in knobs.items():
                setattr(d, k, v)
            label = ", ".join(f"{k}={v}" for k, v in knobs.items())
            for statement in ("entries", "scoped", "count", "top10"):
                v = statements(d, entry.name, chunk.name, "disjoint" if d.name == "postgresql" else "unionall", caller, READ, scope)[statement]
                cold, warm, answer = await timed(engine, d, v, reps)
                say(f"| {label} | {statement} | {ms(cold)} / {ms(warm)} / {recall(statement, answer, truths[statement], traps)} |")
                if statement in ("entries", "count"):
                    async with engine.connect() as conn:
                        plans.append((label, statement, await d.plan(conn, v.sql, v.params)))
        say()
        for label, statement, p in plans:
            say(f"**{label} / {statement}**")
            say()
            say("```")
            say(p)
            say("```")
            say()
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(md.drop_all)
        await engine.dispose()
    write_lines(f"{engine_name}-probe.md", lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["mssql", "oracle", "mariadb", "postgres"])
    ap.add_argument("--chunks", type=int, default=1)
    ap.add_argument("--n", type=int, default=10_000)
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    asyncio.run(run(a.engine, a.n, a.reps))
