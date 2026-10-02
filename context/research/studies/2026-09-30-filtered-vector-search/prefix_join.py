"""A caller's prefixes as rows, not binds: one statement for any grant count.

The prefixes go into a temp table ``grant_ranges(lo, hi)`` (inserted in
chunks, so no statement grows with the grant count), and the admitted
entries are a range join on the path index. Compared against the
admitted-first CTE with the arms inlined as binds.

    uv run --no-sync python prefix_join.py

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import os
import sqlite3
import statistics
import time

from corpus import FILES, FOLDERS, TOPS, pack, paths, queries
from sqlite_bench import build, range_arms

HERE = os.path.dirname(os.path.abspath(__file__))
DIM = 64


def main() -> None:
    conn, _ = build(DIM)
    folders = [f"/t{t:02d}/f{f:03d}" for t in range(TOPS) for f in range(FOLDERS)]
    files = paths()
    cases = {
        "10% · 100 folder grants": folders[::10],
        "50% · 500 folder grants": folders[::2],
        "1% · 500 file grants": files[::100],
        "10% · 5,000 file grants": files[::10],
    }
    qs = [pack(v) for v in queries(DIM, 10)]
    tail = (
        " SELECT c.id FROM v CROSS JOIN echunks c WHERE c.entry_id = v.entry_id"
        " ORDER BY vec_distance_cosine(c.embedding, ?), c.id LIMIT 10"
    )
    lines = [f"## prefixes as rows vs arms as binds — sqlite, 50,000 chunks ({TOPS}×{FOLDERS}×{FILES}), dim {DIM}\n"]
    lines += ["| caller | arms as binds (CTE) | prefixes as rows (range join) | same top 10 |", "|---|---|---|---|"]
    for label, prefixes in cases.items():
        conn.execute("DROP TABLE IF EXISTS temp.grant_ranges")
        conn.execute("CREATE TEMP TABLE grant_ranges (lo TEXT PRIMARY KEY, hi TEXT NOT NULL, exact TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO temp.grant_ranges VALUES (?, ?, ?)", [(p + "/", p + "0", p) for p in prefixes]
        )
        joined = (
            "WITH v AS MATERIALIZED (SELECT e.entry_id FROM temp.grant_ranges g CROSS JOIN entries e"
            " WHERE e.path > g.lo AND e.path < g.hi"
            " UNION SELECT e.entry_id FROM temp.grant_ranges g CROSS JOIN entries e WHERE e.path = g.exact)" + tail
        )
        cells = []
        results = []
        if len(prefixes) * 3 < 32_000:
            where, args = range_arms(prefixes)
            inlined = f"WITH v AS MATERIALIZED (SELECT entry_id FROM entries WHERE {where})" + tail
            shapes = [(inlined, args), (joined, [])]
        else:
            shapes = [(None, []), (joined, [])]
        for sql, args in shapes:
            if sql is None:
                cells.append("over SQLite's bind cap")
                results.append(None)
                continue
            samples, found = [], []
            try:
                for q in qs:
                    t0 = time.perf_counter()
                    found.append([r[0] for r in conn.execute(sql, [*args, q])])
                    samples.append((time.perf_counter() - t0) * 1000)
            except sqlite3.OperationalError as exc:
                cells.append(f"refused: {exc}")
                results.append(None)
                continue
            cells.append(f"{statistics.median(samples):.1f} ms")
            results.append(found)
        same = "—" if None in results else str(results[0] == results[1])
        lines.append(f"| {label} | {cells[0]} | {cells[1]} | {same} |")
        print(lines[-1], flush=True)
    with open(os.path.join(HERE, "runs", "prefix-join.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
