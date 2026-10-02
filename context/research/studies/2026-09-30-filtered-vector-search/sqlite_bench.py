"""Filtered nearest-neighbour search on SQLite + sqlite-vec: pre-filter vs post-filter.

Strategies, each answering "the 10 nearest chunks this caller may see":

- ``like-arms``: today's shape. ``vec_distance_cosine`` over the rows an
  OR of ``path = :p OR path LIKE :p || '/%'`` arms admits, sorted, limited.
- ``range-arms``: the same pre-filter spelled as byte ranges
  (``path = :p OR (path > :p/ AND path < :p0)``) that the path index can serve.
- ``… join``: the same two, with ``path`` on an entries table joined to the
  chunks, as vfs's schema has it; ``range-arms cte`` materialises the
  admitted entry ids first, then joins the chunks.
- ``temp-allow``: the caller's visible chunk ids materialised once into a
  temp table (a per-caller cache), joined to the distance scan.
- ``post-W``: brute force over every row with no filter, top ``W``, then
  the permission check in app code; ``W`` fixed.
- ``post-deepen``: as ``post-W`` from ``W = 10k``, deepening ×4 until k admitted.
- ``vec0-post``: the same post-filter over sqlite-vec's ``vec0`` KNN (k ≤ 4096).
- ``planner``: count admitted rows through the range arms first; pre-filter
  when the count is small, post-filter with ``W = 3k / selectivity`` otherwise, deepening ×4 if short.

    uv run --no-sync python sqlite_bench.py --dim 64
    uv run --no-sync python sqlite_bench.py --dim 384

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import statistics
import tempfile
import time
from collections.abc import Callable

import sqlite_vec

from corpus import K, Caller, admits, callers, pack, paths, queries, recall, vectors

HERE = os.path.dirname(os.path.abspath(__file__))
VEC0_MAX_K = 4096
PLANNER_PREFILTER_ROWS = 5_000

Search = Callable[[bytes], list[int]]


def build(dim: int) -> tuple[sqlite3.Connection, float]:
    tmp = tempfile.mkdtemp(prefix="vfs-fvs-")
    conn = sqlite3.connect(f"{tmp}/fvs.sqlite")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute("PRAGMA case_sensitive_like = ON")
    t0 = time.perf_counter()
    conn.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, path TEXT NOT NULL, embedding BLOB NOT NULL)")
    conn.execute("CREATE INDEX ix_chunks_path ON chunks (path)")
    conn.execute("CREATE TABLE entries (entry_id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE)")
    conn.execute("CREATE TABLE echunks (id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL, embedding BLOB NOT NULL)")
    conn.execute("CREATE INDEX ix_echunks_entry ON echunks (entry_id)")
    conn.execute(f"CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[{dim}] distance_metric=cosine)")
    rows = [(i + 1, p, pack(v)) for i, (p, v) in enumerate(zip(paths(), vectors(dim), strict=True))]
    conn.executemany("INSERT INTO chunks VALUES (?, ?, ?)", rows)
    conn.executemany("INSERT INTO entries VALUES (?, ?)", [(r[0], r[1]) for r in rows])
    conn.executemany("INSERT INTO echunks VALUES (?, ?, ?)", [(r[0], r[0], r[2]) for r in rows])
    conn.executemany("INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)", [(r[0], r[2]) for r in rows])
    conn.commit()
    conn.execute("ANALYZE")
    return conn, time.perf_counter() - t0


def like_arms(prefixes: list[str]) -> tuple[str, list[str]]:
    sql = " OR ".join("(path = ? OR path LIKE ? ESCAPE '\\')" for _ in prefixes)
    return sql, [x for p in prefixes for x in (p, p + "/%")]


def range_arms(prefixes: list[str]) -> tuple[str, list[str]]:
    sql = " OR ".join("(path = ? OR (path > ? AND path < ?))" for _ in prefixes)
    return sql, [x for p in prefixes for x in (p, p + "/", p + "0")]


def strategies(conn: sqlite3.Connection, caller: Caller) -> dict[str, Search]:
    granted = set(caller.prefixes)
    like_sql, like_args = like_arms(caller.prefixes)
    range_sql, range_args = range_arms(caller.prefixes)
    conn.execute("DROP TABLE IF EXISTS temp.allow")
    conn.execute("CREATE TEMP TABLE allow (id INTEGER PRIMARY KEY)")
    conn.execute(f"INSERT INTO temp.allow SELECT id FROM chunks WHERE {range_sql}", range_args)
    total = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]

    def filtered(where: str, args: list[str]) -> Search:
        sql = "SELECT id FROM chunks WHERE " + where + " ORDER BY vec_distance_cosine(embedding, ?), id LIMIT ?"
        return lambda q: [r[0] for r in conn.execute(sql, [*args, q, K])]

    def joined(where: str, args: list[str]) -> Search:
        sql = (
            "SELECT c.id FROM echunks c JOIN entries e ON e.entry_id = c.entry_id WHERE "
            + where
            + " ORDER BY vec_distance_cosine(c.embedding, ?), c.id LIMIT ?"
        )
        return lambda q: [r[0] for r in conn.execute(sql, [*args, q, K])]

    def admitted_first(where: str, args: list[str]) -> Search:
        sql = (
            "WITH v AS MATERIALIZED (SELECT entry_id FROM entries e WHERE " + where + ")"
            " SELECT c.id FROM v JOIN echunks c ON c.entry_id = v.entry_id"
            " ORDER BY vec_distance_cosine(c.embedding, ?), c.id LIMIT ?"
        )
        return lambda q: [r[0] for r in conn.execute(sql, [*args, q, K])]

    def temp_allow(q: bytes) -> list[int]:
        sql = (
            "SELECT c.id FROM temp.allow a JOIN chunks c ON c.id = a.id"
            " ORDER BY vec_distance_cosine(c.embedding, ?), c.id LIMIT ?"
        )
        return [r[0] for r in conn.execute(sql, [q, K])]

    def brute_top(q: bytes, window: int) -> list[tuple[int, str]]:
        sql = "SELECT id, path FROM chunks ORDER BY vec_distance_cosine(embedding, ?), id LIMIT ?"
        return list(conn.execute(sql, [q, window]))

    def vec0_top(q: bytes, window: int) -> list[tuple[int, str]]:
        sql = (
            "SELECT v.rowid, c.path FROM vec_chunks v JOIN chunks c ON c.id = v.rowid"
            " WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance"
        )
        return list(conn.execute(sql, [q, min(window, VEC0_MAX_K)]))

    def keep(rows: list[tuple[int, str]]) -> list[int]:
        return [i for i, p in rows if admits(granted, p)][:K]

    def post(window: int, top: Callable[[bytes, int], list[tuple[int, str]]]) -> Search:
        return lambda q: keep(top(q, window))

    def deepen(q: bytes) -> list[int]:
        window = 10 * K
        while True:
            found = keep(brute_top(q, window))
            if len(found) >= K or window >= total:
                return found
            window *= 4

    def planner(q: bytes) -> list[int]:
        admitted = conn.execute(f"SELECT count(*) FROM chunks WHERE {range_sql}", range_args).fetchone()[0]
        if admitted <= PLANNER_PREFILTER_ROWS:
            return filtered(range_sql, range_args)(q)
        window = min(total, int(3 * K * total / max(1, admitted)))
        while True:
            found = keep(brute_top(q, window))
            if len(found) >= K or window >= total:
                return found
            window = min(total, window * 4)

    return {
        "like-arms (today)": filtered(like_sql, like_args),
        "range-arms": filtered(range_sql, range_args),
        "like-arms join": joined(like_sql.replace("path", "e.path"), like_args),
        "range-arms join": joined(range_sql.replace("path", "e.path"), range_args),
        "range-arms cte": admitted_first(range_sql.replace("path", "e.path"), range_args),
        "temp-allow": temp_allow,
        "post-100": post(100, brute_top),
        "post-1000": post(1000, brute_top),
        "post-deepen": deepen,
        "vec0-post-1000": post(1000, vec0_top),
        "vec0-post-4096": post(4096, vec0_top),
        "planner": planner,
    }


def timed(search: Search, qs: list[bytes], truths: list[list[int]]) -> tuple[float, float, float]:
    search(qs[0])
    samples, recalls, counts = [], [], []
    for q, truth in zip(qs, truths, strict=True):
        t0 = time.perf_counter()
        found = search(q)
        samples.append((time.perf_counter() - t0) * 1000)
        recalls.append(recall(found, truth))
        counts.append(len(found))
    return statistics.median(samples), statistics.mean(recalls), statistics.mean(counts)


def main(dim: int, n_queries: int) -> None:
    conn, t_build = build(dim)
    qs = [pack(v) for v in queries(dim, n_queries)]
    lines = [
        f"## sqlite {sqlite3.sqlite_version} + sqlite-vec — 50,000 chunks, dim {dim}, k={K}, "
        f"{n_queries} queries, median ms · mean recall@10 · mean hits (build {t_build:.0f}s)\n"
    ]
    whole = "SELECT id FROM chunks ORDER BY vec_distance_cosine(embedding, ?), id LIMIT ?"
    samples = []
    for q in qs:
        t0 = time.perf_counter()
        conn.execute(whole, [q, K]).fetchall()
        samples.append((time.perf_counter() - t0) * 1000)
    lines.append(f"Whole-mount brute force (no filter): {statistics.median(samples):.1f} ms\n")
    print(lines[-1], flush=True)
    header: list[str] | None = None
    for caller in callers():
        plans = strategies(conn, caller)
        range_sql, range_args = range_arms(caller.prefixes)
        exact = plans["range-arms"]
        truths = [exact(q) for q in qs]
        admitted = conn.execute(f"SELECT count(*) FROM chunks WHERE {range_sql}", range_args).fetchone()[0]
        if header is None:
            header = list(plans)
            lines += ["| caller (admitted) | " + " | ".join(header) + " |", "|---|" + "---|" * len(header)]
        cells = []
        for name in header:
            ms, rec, hits = timed(plans[name], qs, truths)
            cells.append(f"{ms:.1f} · {rec:.2f} · {hits:.1f}")
        row = f"| {caller.label} ({admitted:,}) | " + " | ".join(cells) + " |"
        print(row, flush=True)
        lines.append(row)
    out = os.path.join(HERE, "runs", f"sqlite-dim{dim}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"→ {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dim", type=int, default=64)
    ap.add_argument("--queries", type=int, default=20)
    a = ap.parse_args()
    main(a.dim, a.queries)
