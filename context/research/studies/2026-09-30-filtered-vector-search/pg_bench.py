"""Filtered nearest-neighbour search on Postgres + pgvector: exact, HNSW-filtered and post-filtered.

The schema mirrors vfs's: ``entries(entry_id, path COLLATE "C" UNIQUE)`` and
``chunks(id, entry_id, embedding vector(dim))`` with an HNSW cosine index.
Strategies, each answering "the 10 nearest chunks this caller may see":

- ``exact like``: today's arms (``path = :p OR path LIKE :p || '/%'``) on the
  joined entry, exact distance (``+ 0`` keeps the planner off the HNSW index).
- ``exact range-cte``: admitted entry ids first through byte-range arms
  the path index serves, then exact distance over their chunks.
- ``hnsw like`` / ``hnsw range``: the arms inside an HNSW-ordered query with
  ``hnsw.iterative_scan = relaxed_order`` — what vfs runs today when indexed.
  The planner may still choose an exact plan; the ``plan`` table says which.
- ``hnsw range ef100 top40``: the range arms under HNSW with ``ef_search = 100``,
  the top 40 re-sorted exactly in a materialised CTE (pgvector's advice for
  relaxed order), first 10 kept.
- ``hnsw post-W``: HNSW top ``W`` (``ef_search = min(W, 1000)``, iterative
  past 1000) with no arm, the permission check in app code.
- ``planner``: count admitted entries through the range arms; exact
  range-cte when few, HNSW post-filter with ``W = 3k / selectivity`` (deepening) when many.

    VFS_PG=postgresql://vfs:vfs@localhost:54320/vfs uv run --no-sync python pg_bench.py --dim 384

Every table this creates is dropped on exit. Study code only.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import asyncpg

from corpus import K, Caller, admits, callers, paths, queries, recall, vectors

HERE = os.path.dirname(os.path.abspath(__file__))
PLANNER_PREFILTER_ROWS = 5_000
EF_SEARCH_MAX = 1000

Search = Callable[[str], Awaitable[list[int]]]


def literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def like_arms(prefixes: list[str], first: int) -> tuple[str, list[str]]:
    parts, args, n = [], [], first
    for p in prefixes:
        parts.append(f"(e.path = ${n} OR e.path LIKE ${n + 1})")
        args += [p, p + "/%"]
        n += 2
    return " OR ".join(parts), args


def range_arms(prefixes: list[str], first: int) -> tuple[str, list[str]]:
    parts, args, n = [], [], first
    for p in prefixes:
        parts.append(f"(e.path = ${n} OR (e.path > ${n + 1} AND e.path < ${n + 2}))")
        args += [p, p + "/", p + "0"]
        n += 3
    return " OR ".join(parts), args


async def build(conn: asyncpg.Connection, t: str, dim: int) -> dict[str, float]:
    times: dict[str, float] = {}
    t0 = time.perf_counter()
    await conn.execute(f'CREATE TABLE {t}_e (entry_id bigint PRIMARY KEY, path text COLLATE "C" NOT NULL UNIQUE)')
    await conn.execute(f"CREATE TABLE {t}_c (id bigint PRIMARY KEY, entry_id bigint NOT NULL, embedding vector({dim}))")
    await conn.execute(f"CREATE INDEX ON {t}_c (entry_id)")
    ps = paths()
    await conn.copy_records_to_table(f"{t}_e", records=[(i + 1, p) for i, p in enumerate(ps)])
    rows = [(i + 1, i + 1, literal(v)) for i, v in enumerate(vectors(dim))]
    await conn.executemany(f"INSERT INTO {t}_c VALUES ($1, $2, $3::vector)", rows)
    times["load"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    await conn.execute("SET max_parallel_maintenance_workers = 0")
    await conn.execute("SET maintenance_work_mem = '512MB'")
    await conn.execute(f"CREATE INDEX {t}_hnsw ON {t}_c USING hnsw (embedding vector_cosine_ops)")
    times["hnsw build"] = time.perf_counter() - t0
    await conn.execute(f"VACUUM ANALYZE {t}_e")
    await conn.execute(f"VACUUM ANALYZE {t}_c")
    return times


def strategies(conn: asyncpg.Connection, t: str, caller: Caller, total: int) -> dict[str, Search]:
    granted = set(caller.prefixes)
    join = f"FROM {t}_c c JOIN {t}_e e ON e.entry_id = c.entry_id"

    def exact_like() -> Search:
        where, args = like_arms(caller.prefixes, 2)
        sql = f"SELECT c.id {join} WHERE {where} ORDER BY (c.embedding <=> $1::vector) + 0, c.id LIMIT {K}"
        return lambda q: fetch_ids(sql, [q, *args])

    def exact_range_cte() -> Search:
        where, args = range_arms(caller.prefixes, 2)
        sql = (
            f"WITH v AS MATERIALIZED (SELECT e.entry_id FROM {t}_e e WHERE {where}) "
            f"SELECT c.id FROM v JOIN {t}_c c ON c.entry_id = v.entry_id "
            f"ORDER BY (c.embedding <=> $1::vector) + 0, c.id LIMIT {K}"
        )
        return lambda q: fetch_ids(sql, [q, *args])

    def hnsw_filtered(arms: Callable[[list[str], int], tuple[str, list[str]]]) -> Search:
        where, args = arms(caller.prefixes, 2)
        sql = f"SELECT c.id {join} WHERE {where} ORDER BY c.embedding <=> $1::vector LIMIT {K}"

        async def run(q: str) -> list[int]:
            async with conn.transaction():
                await conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
                return [r[0] for r in await conn.fetch(sql, q, *args)]

        return run

    def hnsw_wide(ef: int, window: int) -> Search:
        where, args = range_arms(caller.prefixes, 2)
        sql = (
            f"WITH w AS MATERIALIZED (SELECT c.id, c.embedding <=> $1::vector AS d {join} WHERE {where} "
            f"ORDER BY c.embedding <=> $1::vector LIMIT {window}) SELECT id FROM w ORDER BY d, id LIMIT {K}"
        )

        async def run(q: str) -> list[int]:
            async with conn.transaction():
                await conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
                await conn.execute(f"SET LOCAL hnsw.ef_search = {ef}")
                return [r[0] for r in await conn.fetch(sql, q, *args)]

        return run

    async def hnsw_top(q: str, window: int) -> list[tuple[int, str]]:
        sql = f"SELECT c.id, e.path {join} ORDER BY c.embedding <=> $1::vector LIMIT {window}"
        async with conn.transaction():
            await conn.execute(f"SET LOCAL hnsw.ef_search = {min(window, EF_SEARCH_MAX)}")
            if window > EF_SEARCH_MAX:
                await conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
                await conn.execute(f"SET LOCAL hnsw.max_scan_tuples = {max(20_000, 2 * window)}")
            return [(r[0], r[1]) for r in await conn.fetch(sql, q)]

    def keep(rows: list[tuple[int, str]]) -> list[int]:
        return [i for i, p in rows if admits(granted, p)][:K]

    def post(window: int) -> Search:
        async def run(q: str) -> list[int]:
            return keep(await hnsw_top(q, window))

        return run

    count_where, count_args = range_arms(caller.prefixes, 1)
    count_sql = f"SELECT count(*) FROM {t}_e e WHERE {count_where}"
    prefilter = exact_range_cte()

    async def planner(q: str) -> list[int]:
        admitted = await conn.fetchval(count_sql, *count_args)
        if admitted <= PLANNER_PREFILTER_ROWS:
            return await prefilter(q)
        window = min(total, int(3 * K * total / max(1, admitted)))
        while True:
            found = keep(await hnsw_top(q, window))
            if len(found) >= K or window >= total:
                return found
            window = min(total, window * 4)

    async def fetch_ids(sql: str, args: list[object]) -> list[int]:
        return [r[0] for r in await conn.fetch(sql, *args)]

    return {
        "exact like (today, no index)": exact_like(),
        "exact range-cte": prefilter,
        "hnsw like (today, indexed)": hnsw_filtered(like_arms),
        "hnsw range": hnsw_filtered(range_arms),
        "hnsw range ef100 top40": hnsw_wide(100, 4 * K),
        "hnsw post-100": post(100),
        "hnsw post-1000": post(1000),
        "hnsw post-4000": post(4000),
        "planner": planner,
    }


async def plan_of(conn: asyncpg.Connection, t: str, caller: Caller, q: str, arms_kind: str) -> str:
    arms = like_arms if arms_kind == "like" else range_arms
    where, args = arms(caller.prefixes, 2)
    sql = (
        f"EXPLAIN SELECT c.id FROM {t}_c c JOIN {t}_e e ON e.entry_id = c.entry_id "
        f"WHERE {where} ORDER BY c.embedding <=> $1::vector LIMIT {K}"
    )
    async with conn.transaction():
        await conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
        text = "\n".join(r[0] for r in await conn.fetch(sql, q, *args))
    return "HNSW" if "_hnsw" in text else "exact"


async def main(url: str, dim: int, n_queries: int) -> None:
    conn = await asyncpg.connect(url)
    t = f"fvs_{uuid4().hex[:8]}"
    lines: list[str] = []
    try:
        version = await conn.fetchval("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        server = await conn.fetchval("SHOW server_version")
        times = await build(conn, t, dim)
        qs = [literal(v) for v in queries(dim, n_queries)]
        total = len(paths())
        lines.append(
            f"## postgres {server} + pgvector {version} — {total:,} chunks, dim {dim}, HNSW m=16 ef_construction=64, "
            f"k={K}, {n_queries} queries, median ms · mean recall@10 · mean hits "
            f"(load {times['load']:.0f}s, HNSW build {times['hnsw build']:.0f}s)\n"
        )
        samples = []
        for q in qs:
            t0 = time.perf_counter()
            await conn.fetch(f"SELECT id FROM {t}_c ORDER BY (embedding <=> $1::vector) + 0 LIMIT {K}", q)
            samples.append((time.perf_counter() - t0) * 1000)
        lines.append(f"Whole-mount exact scan (no filter): {statistics.median(samples):.1f} ms")
        samples = []
        for q in qs:
            t0 = time.perf_counter()
            await conn.fetch(f"SELECT id FROM {t}_c ORDER BY embedding <=> $1::vector LIMIT {K}", q)
            samples.append((time.perf_counter() - t0) * 1000)
        exact_sql = f"SELECT id FROM {t}_c ORDER BY (embedding <=> $1::vector) + 0, id LIMIT {K}"
        ann_sql = f"SELECT id FROM {t}_c ORDER BY embedding <=> $1::vector LIMIT {K}"
        whole_recall = statistics.mean(
            [
                recall([r[0] for r in await conn.fetch(ann_sql, q)], [r[0] for r in await conn.fetch(exact_sql, q)])
                for q in qs
            ]
        )
        lines.append(
            f"Whole-mount HNSW (ef_search 40): {statistics.median(samples):.1f} ms, recall@10 {whole_recall:.2f}\n"
        )
        print("\n".join(lines), flush=True)
        header: list[str] | None = None
        for caller in callers():
            plans = strategies(conn, t, caller, total)
            truths = [await plans["exact range-cte"](q) for q in qs]
            where, args = range_arms(caller.prefixes, 1)
            admitted = await conn.fetchval(f"SELECT count(*) FROM {t}_e e WHERE {where}", *args)
            if header is None:
                header = list(plans)
                lines += [
                    "| caller (admitted) | plan like/range | " + " | ".join(header) + " |",
                    "|---|---|" + "---|" * len(header),
                ]
            chosen = f"{await plan_of(conn, t, caller, qs[0], 'like')}/{await plan_of(conn, t, caller, qs[0], 'range')}"
            cells = []
            for name in header:
                search = plans[name]
                await search(qs[0])
                samples, recalls, counts = [], [], []
                for q, truth in zip(qs, truths, strict=True):
                    t0 = time.perf_counter()
                    found = await search(q)
                    samples.append((time.perf_counter() - t0) * 1000)
                    recalls.append(recall(found, truth))
                    counts.append(len(found))
                cells.append(
                    f"{statistics.median(samples):.1f} · {statistics.mean(recalls):.2f} · {statistics.mean(counts):.1f}"
                )
            row = f"| {caller.label} ({admitted:,}) | {chosen} | " + " | ".join(cells) + " |"
            print(row, flush=True)
            lines.append(row)
    finally:
        await conn.execute(f"DROP TABLE IF EXISTS {t}_c, {t}_e")
        await conn.close()
    out = os.path.join(HERE, "runs", f"postgres-dim{dim}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"→ {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dim", type=int, default=384)
    ap.add_argument("--queries", type=int, default=20)
    a = ap.parse_args()
    url = os.environ.get("VFS_PG", "postgresql://vfs:vfs@localhost:54320/vfs")
    asyncio.run(main(url, a.dim, a.queries))
