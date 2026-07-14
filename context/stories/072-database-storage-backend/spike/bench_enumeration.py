"""Subtree-enumeration spike (R7): path-prefix LIKE vs parent_id recursive CTE.

Builds a realistic filesystem tree from the corpus's file paths (option-(c)
shape: nodes with parent_id + materialized path, UNIQUE(parent_id, name),
unique path index), then measures subtree enumeration per engine across
subtree sizes and depths, plus the shallow-list comparison.

Run: SPIKE_OUT=<dir> uv run python .../bench_enumeration.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import DATA_DIR  # noqa: E402

OUT_DIR = Path(os.environ.get("SPIKE_OUT", DATA_DIR))
REPEATS = 5


def build_tree(db: Path) -> sqlite3.Connection:
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        PRAGMA journal_mode = WAL; PRAGMA synchronous = OFF;
        PRAGMA case_sensitive_like = ON;
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY, parent_id INTEGER, name TEXT NOT NULL,
            path TEXT NOT NULL, kind TEXT NOT NULL,
            UNIQUE (parent_id, name)
        );
        """
    )
    src = sqlite3.connect(DATA_DIR / "corpus.db")
    seen_files: set[str] = set()
    for (p,) in src.execute("SELECT path FROM docs"):
        seen_files.add(p.rsplit("#", 1)[0])
    src.close()

    dir_ids: dict[str, int] = {"": 1}
    next_id = 2
    rows: list[tuple] = [(1, None, "", "/", "directory")]
    for fp in sorted(seen_files):
        parts = fp.split("/")
        parent = ""
        for d in parts[:-1]:
            cur = f"{parent}/{d}" if parent else d
            if cur not in dir_ids:
                dir_ids[cur] = next_id
                rows.append((next_id, dir_ids[parent], d, "/" + cur, "directory"))
                next_id += 1
            parent = cur
        rows.append((next_id, dir_ids[parent], parts[-1], "/" + fp, "file"))
        next_id += 1
    conn.executemany("INSERT INTO nodes VALUES (?,?,?,?,?)", rows)
    conn.execute("CREATE UNIQUE INDEX idx_path ON nodes (path)")
    conn.commit()
    print(f"tree: {len(rows):,} nodes ({len(dir_ids):,} dirs, {len(seen_files):,} files)")
    return conn


def pick_roots(conn: sqlite3.Connection) -> list[tuple[str, int, int, int]]:
    """(path, id, n_descendants, depth) at spread-out size/depth points."""
    sizes = {}
    for pid, path in conn.execute("SELECT id, path FROM nodes WHERE kind='directory'"):
        prefix = path.rstrip("/") + "/"
        n = conn.execute(
            "SELECT count(*) FROM nodes WHERE path LIKE ? ESCAPE '\\'",
            (prefix.replace("%", r"\%").replace("_", r"\_") + "%",),
        ).fetchone()[0]
        sizes[pid] = (path, n)
    targets = [10, 100, 1_000, 10_000, 100_000]
    picked: list[tuple[str, int, int, int]] = []
    used: set[int] = set()
    for t in targets:
        best = min(
            (pid for pid in sizes if pid not in used),
            key=lambda pid: abs(sizes[pid][1] - t),
        )
        used.add(best)
        path, n = sizes[best]
        picked.append((path, best, n, path.count("/")))
    # Deepest directory with a non-trivial subtree (the deep-narrow probe).
    deep = max(
        (pid for pid in sizes if sizes[pid][1] >= 5 and pid not in used),
        key=lambda pid: sizes[pid][0].count("/"),
    )
    path, n = sizes[deep]
    picked.append((path, deep, n, path.count("/")))
    return picked


def best_of(fn) -> float:
    best = float("inf")
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best * 1e3


def like_prefix(path: str) -> str:
    return (path.rstrip("/") + "/").replace("%", r"\%").replace("_", r"\_") + "%"


def bench_root(conn: sqlite3.Connection, path: str, node_id: int) -> dict:
    prefix = like_prefix(path)

    def like_count() -> None:
        conn.execute(
            "SELECT count(*) FROM nodes WHERE path LIKE ? ESCAPE '\\'", (prefix,)
        ).fetchone()

    def like_rows() -> None:
        conn.execute(
            "SELECT id, path FROM nodes WHERE path LIKE ? ESCAPE '\\'", (prefix,)
        ).fetchall()

    def cte_count() -> None:
        conn.execute(
            """
            WITH RECURSIVE sub(id) AS (
                SELECT id FROM nodes WHERE id = ?
                UNION ALL
                SELECT n.id FROM nodes n JOIN sub ON n.parent_id = sub.id
            )
            SELECT count(*) - 1 FROM sub
            """,
            (node_id,),
        ).fetchone()

    def cte_rows() -> None:
        conn.execute(
            """
            WITH RECURSIVE sub(id, path) AS (
                SELECT id, path FROM nodes WHERE id = ?
                UNION ALL
                SELECT n.id, n.path FROM nodes n JOIN sub ON n.parent_id = sub.id
            )
            SELECT id, path FROM sub
            """,
            (node_id,),
        ).fetchall()

    return {
        "like_count_ms": best_of(like_count),
        "cte_count_ms": best_of(cte_count),
        "like_rows_ms": best_of(like_rows),
        "cte_rows_ms": best_of(cte_rows),
    }


def bench_shallow(conn: sqlite3.Connection, path: str, node_id: int) -> dict:
    prefix = like_prefix(path)

    def by_parent() -> None:
        conn.execute("SELECT id, name FROM nodes WHERE parent_id = ?", (node_id,)).fetchall()

    def by_like_depth() -> None:
        conn.execute(
            "SELECT id, name FROM nodes WHERE path LIKE ? ESCAPE '\\' "
            "AND path NOT LIKE ? ESCAPE '\\'",
            (prefix, prefix.rstrip("%") + "%/%"),
        ).fetchall()

    return {"parent_eq_ms": best_of(by_parent), "like_depthfilter_ms": best_of(by_like_depth)}


def main() -> None:
    conn = build_tree(OUT_DIR / "enum_tree.db")
    roots = pick_roots(conn)
    results = {"subtrees": [], "shallow": []}
    for path, node_id, n, depth in roots:
        r = bench_root(conn, path, node_id)
        r.update({"path": path, "descendants": n, "depth": depth})
        results["subtrees"].append(r)
        print(
            f"  {path[:48]:<48} n={n:>7,} d={depth:>2} | "
            f"count: LIKE {r['like_count_ms']:8.2f} ms vs CTE {r['cte_count_ms']:8.2f} ms | "
            f"rows: LIKE {r['like_rows_ms']:8.2f} ms vs CTE {r['cte_rows_ms']:8.2f} ms",
            flush=True,
        )
    for path, node_id, n, depth in roots:
        s = bench_shallow(conn, path, node_id)
        n_children = conn.execute(
            "SELECT count(*) FROM nodes WHERE parent_id = ?", (node_id,)
        ).fetchone()[0]
        s.update({"path": path, "children": n_children, "subtree": n})
        results["shallow"].append(s)
        print(
            f"  shallow {path[:40]:<40} kids={n_children:>5} (subtree {n:>7,}) | "
            f"parent= {s['parent_eq_ms']:6.3f} ms vs LIKE+filter {s['like_depthfilter_ms']:8.2f} ms",
            flush=True,
        )
    out = OUT_DIR / "bench_enumeration.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
