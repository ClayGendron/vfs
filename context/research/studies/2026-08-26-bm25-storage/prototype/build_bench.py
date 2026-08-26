"""Drive the Option B builds: Python at 128; Rust at 64/128/256 (each in a
fresh subprocess so peak RSS is the build's own), then sizes from dbstat,
and a blob-level identity check between the Python and Rust builds.

    uv run --no-sync python build_bench.py
"""

from __future__ import annotations

import json
import resource
import sqlite3
import subprocess
import sys
import time

from common import HERE, OPTION_B_PY, OPTION_B_RS, RUSTBENCH, SCRATCH, STORE, dbstat_bytes, dump_json


def run_child(cmd: list[str]) -> tuple[dict, float, float]:
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    t0 = time.perf_counter()
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    wall = time.perf_counter() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return json.loads(out.strip().splitlines()[-1]), wall, after / 2**20 if after != before or True else 0.0


def sizes(path) -> dict:
    conn = sqlite3.connect(path)
    by_table = dbstat_bytes(conn)
    rows = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("lex_postings", "lex_docs", "lex_df", "lex_stats")}
    conn.close()
    return {"dbstat_bytes": by_table, "total_bytes": sum(v for k, v in by_table.items() if k.startswith("lex_")), "rows": rows}


def main() -> None:
    results: dict = {"store": str(STORE), "builds": {}}
    # Rust: block-size sweep. Each in its own process; RUSAGE_CHILDREN's maxrss is the max over children so far,
    # so run the sweep in ascending expected-memory order and note the value is a running max.
    for block in (64, 128, 256):
        out = SCRATCH / f"optionb_rs_{block}.sqlite"
        report, wall, child_rss = run_child([str(RUSTBENCH), "build", str(STORE), str(out), str(block)])
        report["wrapper_wall_s"] = round(wall, 3)
        report["peak_rss_mb_children_running_max"] = round(child_rss, 1)
        report.update(sizes(out))
        results["builds"][f"rust_{block}"] = report
        print("rust", block, json.dumps(report))
    subprocess.run(["cp", str(SCRATCH / "optionb_rs_128.sqlite"), str(OPTION_B_RS)], check=True)
    # Python at 128 in a fresh interpreter (its own RSS).
    report, wall, _ = run_child([sys.executable, str(HERE / "build_b_python.py"), str(OPTION_B_PY), "128"])
    report["wrapper_wall_s"] = round(wall, 3)
    report.update(sizes(OPTION_B_PY))
    results["builds"]["python_128"] = report
    print("python 128", json.dumps(report))
    # Identity: every block row (and df/docs/stats) identical between the two 128 builds.
    a, b = sqlite3.connect(OPTION_B_PY), sqlite3.connect(OPTION_B_RS)
    identical = True
    for table, order in (("lex_postings", "term, block_no"), ("lex_docs", "chunk_id"), ("lex_df", "term"), ("lex_stats", "epoch")):
        q = f"SELECT * FROM {table} ORDER BY {order}"
        ca, cb = a.execute(q), b.execute(q)
        n = 0
        while True:
            ra, rb = ca.fetchmany(5000), cb.fetchmany(5000)
            if ra != rb:
                identical = False
                results["first_difference"] = {"table": table, "after_rows": n, "a": str(ra[:1]), "b": str(rb[:1])}
                break
            if not ra:
                break
            n += len(ra)
        if not identical:
            break
    results["python_rust_tables_identical"] = identical
    # Option A reference sizes from the store (dbstat over vfs_lex_*).
    store = sqlite3.connect(STORE)
    stat = dbstat_bytes(store)
    results["option_a"] = {
        "dbstat_bytes": {k: v for k, v in stat.items() if k.startswith("vfs_lex")},
        "total_bytes": sum(v for k, v in stat.items() if k.startswith("vfs_lex")),
        "rows": {t: store.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("vfs_lex_terms", "vfs_lex_docs", "vfs_lex_df", "vfs_lex_stats")},
        "landing_note": {"build_add_s": 28.8, "term_rows": 3_094_397, "bytes_mb": 120},
    }
    out = dump_json("build.json", results)
    print("identical:", identical, out)


if __name__ == "__main__":
    main()
