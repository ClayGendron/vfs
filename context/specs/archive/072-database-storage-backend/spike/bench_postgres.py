"""Postgres pg_trgm spike: load a corpus tier, build GIN, benchmark patterns.

Measures: COPY load time, gin_trgm_ops build time and index size, per-pattern
EXPLAIN (ANALYZE, BUFFERS) for `content ~ pattern` — extracting exec time,
rows removed by index recheck, and whether the plan degenerated — plus the
ILIKE-conjunction + client-side Python-verify shape for comparison.

Run: uv run --with psycopg python .../bench_postgres.py <N> [--load] [--skip-build]
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import DATA_DIR  # noqa: E402

DBNAME = "vfs_spike"

# (label, class, pg regex pattern, python regex, required literal runs >= 3 bytes)
PATTERNS = [
    ("zero_hit", "rare", "xyzzy_unlikely_sentinel_42", "xyzzy_unlikely_sentinel_42", ["xyzzy_unlikely_sentinel_42"]),
    ("rare_ident", "rare", "EXPORT_SYMBOL_NS_GPL", "EXPORT_SYMBOL_NS_GPL", ["EXPORT_SYMBOL_NS_GPL"]),
    ("medium_ident", "medium", "kmalloc", "kmalloc", ["kmalloc"]),
    ("hot_ident", "hot", "return", "return", ["return"]),
    ("hot_phrase", "hot", "def __init__", "def __init__", ["def __init__"]),
    ("punct_arrow", "punct", "->next", "->next", ["->next"]),
    ("punct_neq_null", "punct", "!= NULL", "!= NULL", ["!= NULL"]),
    ("regex_probe", "regex", r"static\s+int\s+\w+_probe", r"static\s+int\s+\w+_probe", ["static", "_probe"]),
    ("regex_alt", "regex", r"(kmalloc|vmalloc)\(", r"(kmalloc|vmalloc)\(", None),
    ("sub3_bytes", "unindexable", "ab", "ab", None),
]


def ensure_db() -> None:
    with psycopg.connect(dbname="postgres", autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (DBNAME,)
        ).fetchone()
        if not exists:
            conn.execute(f"CREATE DATABASE {DBNAME}")


def load(n_docs: int) -> dict:
    src = sqlite3.connect(DATA_DIR / "corpus.db")
    t0 = time.monotonic()
    with psycopg.connect(dbname=DBNAME, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS docs")
        conn.execute("CREATE TABLE docs (id int PRIMARY KEY, path text, content text)")
        with conn.cursor() as cur, cur.copy("COPY docs (id, path, content) FROM STDIN") as copy:
            for start in range(0, n_docs, 10_000):
                rows = src.execute(
                    "SELECT id, path, content FROM docs WHERE id >= ? AND id < ?",
                    (start, min(start + 10_000, n_docs)),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    copy.write_row(row)
        heap = conn.execute("SELECT pg_table_size('docs')").fetchone()[0]
    src.close()
    return {"load_s": round(time.monotonic() - t0, 1), "heap_bytes": heap}


def build_index() -> dict:
    with psycopg.connect(dbname=DBNAME, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        conn.execute("SET maintenance_work_mem = '2GB'")
        conn.execute("DROP INDEX IF EXISTS docs_content_trgm")
        t0 = time.monotonic()
        conn.execute("CREATE INDEX docs_content_trgm ON docs USING gin (content gin_trgm_ops)")
        build_s = time.monotonic() - t0
        size = conn.execute("SELECT pg_relation_size('docs_content_trgm')").fetchone()[0]
    return {"gin_build_s": round(build_s, 1), "gin_bytes": size}


def walk_plan(node: dict, acc: dict) -> None:
    acc["recheck_removed"] += node.get("Rows Removed by Index Recheck", 0)
    acc["lossy_blocks"] += node.get("Lossy Heap Blocks", 0)
    acc["exact_blocks"] += node.get("Exact Heap Blocks", 0)
    if node.get("Node Type") == "Seq Scan":
        acc["seq_scan"] = True
    for child in node.get("Plans", []):
        walk_plan(child, acc)


def explain(conn, sql: str, params: tuple) -> dict:
    plan_rows = conn.execute(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
    ).fetchone()[0]
    plan = plan_rows[0]
    acc = {"recheck_removed": 0, "lossy_blocks": 0, "exact_blocks": 0, "seq_scan": False}
    walk_plan(plan["Plan"], acc)
    return {
        "exec_ms": round(plan["Execution Time"], 2),
        "rows": plan["Plan"].get("Actual Rows", 0),
        **acc,
    }


def bench(n_docs: int) -> dict:
    out = {}
    with psycopg.connect(dbname=DBNAME) as conn:
        conn.execute("SET work_mem = '64MB'")
        for label, cls, pg_pat, py_pat, runs in PATTERNS:
            entry = {"class": cls}
            # Shape 1: content ~ pattern, end-to-end in Postgres (best of 2).
            tries = [explain(conn, "SELECT count(*) FROM docs WHERE content ~ %s", (pg_pat,)) for _ in range(2)]
            entry["regex_native"] = min(tries, key=lambda r: r["exec_ms"])
            # Shape 2: ILIKE-conjunction prefilter + client-side Python verify.
            if runs:
                conj = " AND ".join(["content ILIKE %s"] * len(runs))
                params = tuple(f"%{r}%" for r in runs)
                tries = [
                    explain(conn, f"SELECT count(*) FROM docs WHERE {conj}", params)
                    for _ in range(2)
                ]
                entry["ilike_prefilter"] = min(tries, key=lambda r: r["exec_ms"])
                t0 = time.monotonic()
                rx = re.compile(py_pat)
                verified = 0
                with conn.cursor(name="cand") as cur:
                    cur.itersize = 2000
                    cur.execute(f"SELECT content FROM docs WHERE {conj}", params)
                    for (content,) in cur:
                        if rx.search(content):
                            verified += 1
                entry["ilike_plus_verify"] = {
                    "total_ms": round((time.monotonic() - t0) * 1000, 1),
                    "verified": verified,
                }
            out[label] = entry
            print(f"{label}: done", flush=True)
    return out


def main() -> None:
    n_docs = int(sys.argv[1])
    result = {"tier": n_docs}
    ensure_db()
    if "--load" in sys.argv:
        result["load"] = load(n_docs)
        print(f"load: {result['load']}", flush=True)
    if "--skip-build" not in sys.argv:
        result["index"] = build_index()
        print(f"index: {result['index']}", flush=True)
    result["patterns"] = bench(n_docs)
    (DATA_DIR / f"pg_bench_{n_docs}.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1), flush=True)


if __name__ == "__main__":
    main()
