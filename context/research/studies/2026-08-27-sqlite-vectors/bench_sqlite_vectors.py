"""SQLite cosine top-10 over a BLOB column: sqlite-vec vs vectorlite scalar vs the Rust kernel over fetched bytes.

One table (id INTEGER PRIMARY KEY, v BLOB) of N unit vectors of D float32,
packed little-endian exactly as vfs stores chunk embeddings. Each arm answers
the same question — the ten nearest ids by cosine to one query — and is
timed best-of-3 after one warm-up. Results are checked to agree.
"""

from __future__ import annotations

import random
import sqlite3
import struct
import sys
import time
from pathlib import Path

import sqlite_vec

from vfs.models.vector import cosine_topk

try:
    import vectorlite_py  # type: ignore[import-not-found]
except ImportError:
    vectorlite_py = None

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/bench_sqlite_vectors")
SIZES = [(10_000, 64), (10_000, 256), (10_000, 1536), (100_000, 64), (100_000, 256), (100_000, 1536)]
K = 10


def unit(rng: random.Random, dim: int) -> list[float]:
    values = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values]


def build(n: int, dim: int) -> tuple[Path, list[float]]:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"n{n}_d{dim}.sqlite"
    rng = random.Random(7)
    query = unit(rng, dim)
    if not path.exists():
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v BLOB NOT NULL)")
        rows = ((i + 1, struct.pack(f"<{dim}f", *unit(rng, dim))) for i in range(n))
        conn.executemany("INSERT INTO t VALUES (?, ?)", rows)
        conn.commit()
        conn.close()
    return path, query


def timed(fn, repeats: int = 3) -> tuple[float, object]:
    fn()
    best, answer = float("inf"), None
    for _ in range(repeats):
        started = time.perf_counter()
        answer = fn()
        best = min(best, time.perf_counter() - started)
    return best, answer


def main() -> None:
    print(f"vectorlite: {'present' if vectorlite_py else 'absent'}; sqlite-vec {sqlite_vec.__version__}")
    print(f"{'N':>7} {'D':>5} | {'sqlite-vec':>11} {'vectorlite':>11} {'fetch+rust':>11} | agree")
    for n, dim in SIZES:
        path, query = build(n, dim)
        packed = struct.pack(f"<{dim}f", *query)
        conn = sqlite3.connect(path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        if vectorlite_py:
            conn.load_extension(vectorlite_py.vectorlite_path())
        conn.enable_load_extension(False)

        def vec() -> list[int]:
            rows = conn.execute("SELECT id FROM t ORDER BY vec_distance_cosine(v, ?) LIMIT ?", (packed, K)).fetchall()
            return [r[0] for r in rows]

        def lite() -> list[int]:
            rows = conn.execute(
                "SELECT id FROM t ORDER BY vector_distance(v, ?, 'cosine') LIMIT ?", (packed, K)
            ).fetchall()
            return [r[0] for r in rows]

        def rust() -> list[int]:
            ids: list[int] = []
            chunks: list[bytes] = []
            for row_id, blob in conn.execute("SELECT id, v FROM t ORDER BY id"):
                ids.append(row_id)
                chunks.append(blob)
            return [i for i, _ in cosine_topk(query, ids, b"".join(chunks), K)]

        t_vec, a_vec = timed(vec)
        t_lite, a_lite = timed(lite) if vectorlite_py else (float("nan"), a_vec)
        t_rust, a_rust = timed(rust)
        agree = a_vec == a_lite == a_rust
        print(f"{n:>7} {dim:>5} | {t_vec * 1e3:>9.1f}ms {t_lite * 1e3:>9.1f}ms {t_rust * 1e3:>9.1f}ms | {agree}")
        conn.close()


main()
