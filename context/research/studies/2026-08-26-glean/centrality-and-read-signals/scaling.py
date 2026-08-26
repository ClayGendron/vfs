"""Price centrality at 10^4 / 10^5 / 10^6 nodes on synthetic preferential-attachment
digraphs (m=5 out-edges per node, so ~5N edges): networkx (scipy-backed),
rustworkx, a pure-Python CSR power iteration, and iterative SQL on SQLite
(power iteration as repeated INSERT ... SELECT ... GROUP BY over an edges table).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np
import rustworkx as rx

OUT = Path(__file__).resolve().parent
M = 5
ITERS = 20  # fixed iteration count for the SQL and pure-Python legs (power iteration)


def pa_edges(n: int, m: int, rng: np.random.Generator) -> np.ndarray:
    """Directed preferential attachment: node i links to m earlier nodes chosen ∝ (in-degree+1)."""
    src = np.repeat(np.arange(m, n), m)
    # Copying model: pick a uniformly random earlier edge's target with p=0.7, else a uniform node.
    targets = np.empty(len(src), dtype=np.int64)
    # Bootstrap: a small seed clique
    seed_t = rng.integers(0, m, size=m * m)
    prev = seed_t.copy()
    pos = 0
    chunk = 20000
    for start in range(m, n, chunk):
        stop = min(n, start + chunk)
        cnt = (stop - start) * m
        copy = rng.random(cnt) < 0.7
        pick_copy = prev[rng.integers(0, len(prev), size=cnt)]
        pick_uni = rng.integers(0, start, size=cnt)
        t = np.where(copy, pick_copy, pick_uni)
        targets[pos:pos + cnt] = t
        pos += cnt
        prev = np.concatenate([prev, t]) if len(prev) < 2_000_000 else np.concatenate([prev[-1_000_000:], t])
    e = np.stack([src, targets], axis=1)
    e = e[e[:, 0] != e[:, 1]]
    return np.unique(e, axis=0)


def timed(fn):
    t = time.perf_counter(); r = fn(); return r, time.perf_counter() - t


def pure_python_pagerank(n: int, edges: np.ndarray, iters: int, alpha: float = 0.85) -> list[float]:
    out_deg = [0] * n
    src_l = edges[:, 0].tolist(); tgt_l = edges[:, 1].tolist()
    for s in src_l:
        out_deg[s] += 1
    rank = [1.0 / n] * n
    for _ in range(iters):
        nxt = [0.0] * n
        for s, t in zip(src_l, tgt_l):
            nxt[t] += rank[s] / out_deg[s]
        dangling = sum(rank[i] for i in range(n) if out_deg[i] == 0)
        base = (1 - alpha) / n + alpha * dangling / n
        rank = [base + alpha * x for x in nxt]
    return rank


def numpy_pagerank(n: int, edges: np.ndarray, iters: int, alpha: float = 0.85) -> np.ndarray:
    src = edges[:, 0]; tgt = edges[:, 1]
    out_deg = np.bincount(src, minlength=n).astype(float)
    dangling_mask = out_deg == 0
    rank = np.full(n, 1.0 / n)
    for _ in range(iters):
        contrib = np.bincount(tgt, weights=rank[src] / out_deg[src], minlength=n)
        dangling = rank[dangling_mask].sum()
        rank = (1 - alpha) / n + alpha * (contrib + dangling / n)
    return rank


def sql_pagerank(n: int, edges: np.ndarray, iters: int, alpha: float = 0.85) -> tuple[float, float, float]:
    """Returns (load_s, per_iteration_s, total_s). Power iteration entirely in SQL."""
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA journal_mode=OFF"); con.execute("PRAGMA synchronous=OFF")
    t0 = time.perf_counter()
    con.execute("CREATE TABLE edges(src INTEGER NOT NULL, tgt INTEGER NOT NULL)")
    con.executemany("INSERT INTO edges VALUES (?,?)", edges.tolist())
    con.execute("CREATE INDEX ix_e_src ON edges(src)")
    con.execute("CREATE TABLE outdeg AS SELECT src AS id, COUNT(*) AS d FROM edges GROUP BY src")
    con.execute("CREATE UNIQUE INDEX ix_od ON outdeg(id)")
    con.execute("CREATE TABLE rank(id INTEGER PRIMARY KEY, r REAL NOT NULL)")
    con.executemany("INSERT INTO rank VALUES (?,?)", ((i, 1.0 / n) for i in range(n)))
    con.commit()
    load = time.perf_counter() - t0
    per = []
    for _ in range(iters):
        t1 = time.perf_counter()
        con.execute("CREATE TABLE contrib AS SELECT e.tgt AS id, SUM(r.r / o.d) AS c FROM edges e JOIN rank r ON r.id = e.src JOIN outdeg o ON o.id = e.src GROUP BY e.tgt")
        con.execute("CREATE UNIQUE INDEX ix_c ON contrib(id)")
        (dangling,) = con.execute("SELECT COALESCE(SUM(r.r),0) FROM rank r LEFT JOIN outdeg o ON o.id=r.id WHERE o.id IS NULL").fetchone()
        base = (1 - alpha) / n + alpha * dangling / n
        con.execute("CREATE TABLE rank_next AS SELECT r.id AS id, ? + ? * COALESCE(c.c, 0) AS r FROM rank r LEFT JOIN contrib c ON c.id = r.id", (base, alpha))
        con.execute("DROP TABLE rank"); con.execute("DROP TABLE contrib")
        con.execute("ALTER TABLE rank_next RENAME TO rank")
        con.execute("CREATE UNIQUE INDEX ix_r ON rank(id)")
        con.commit()
        per.append(time.perf_counter() - t1)
    con.close()
    return load, float(np.mean(per)), load + sum(per)


def run(n: int, do_pure: bool, do_sql: bool) -> dict:
    rng = np.random.default_rng(7)
    edges, t_gen = timed(lambda: pa_edges(n, M, rng))
    res = {"nodes": n, "edges": int(len(edges)), "gen_s": round(t_gen, 3)}
    # networkx
    g, t_build = timed(lambda: nx.DiGraph(edges.tolist()))
    g.add_nodes_from(range(n))
    res["nx_build_s"] = round(t_build, 3)
    _, t = timed(lambda: nx.pagerank(g, alpha=0.85, tol=1e-6)); res["nx_pagerank_s"] = round(t, 3)
    _, t = timed(lambda: nx.katz_centrality(g, alpha=0.05, max_iter=1000, tol=1e-6)); res["nx_katz_s"] = round(t, 3)
    if n <= 100_000:
        _, t = timed(lambda: nx.hits(g, max_iter=200, tol=1e-6)); res["nx_hits_s"] = round(t, 3)
    del g
    # rustworkx
    def build_rx():
        rg = rx.PyDiGraph()
        rg.add_nodes_from(range(n))
        rg.add_edges_from_no_data([(int(a), int(b)) for a, b in edges])
        return rg
    rg, t_build = timed(build_rx); res["rx_build_s"] = round(t_build, 3)
    _, t = timed(lambda: rx.pagerank(rg, alpha=0.85, tol=1e-6)); res["rx_pagerank_s"] = round(t, 3)
    _, t = timed(lambda: rx.katz_centrality(rg, alpha=0.05, max_iter=1000, tol=1e-6)); res["rx_katz_s"] = round(t, 3)
    _, t = timed(lambda: rx.hits(rg, max_iter=200, tol=1e-6)); res["rx_hits_s"] = round(t, 3)
    _, t = timed(lambda: rg.in_degree(0)); res["rx_indegree_one_s"] = round(t, 6)
    del rg
    _, t = timed(lambda: numpy_pagerank(n, edges, ITERS)); res[f"numpy_pagerank_{ITERS}it_s"] = round(t, 3)
    if do_pure:
        _, t = timed(lambda: pure_python_pagerank(n, edges, ITERS)); res[f"pure_python_pagerank_{ITERS}it_s"] = round(t, 3)
    if do_sql:
        load, per, total = sql_pagerank(n, edges, ITERS)
        res["sqlite_load_s"] = round(load, 3); res["sqlite_per_iter_s"] = round(per, 3); res[f"sqlite_total_{ITERS}it_s"] = round(total, 3)
    return res


if __name__ == "__main__":
    sizes = [int(x) for x in sys.argv[1:]] or [10_000, 100_000, 1_000_000]
    results = []
    for n in sizes:
        r = run(n, do_pure=True, do_sql=True)
        print(json.dumps(r)); sys.stdout.flush()
        results.append(r)
    (OUT / "scaling.json").write_text(json.dumps(results, indent=2))
