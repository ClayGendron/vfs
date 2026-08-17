"""Index maintenance cost: 10k bulk insert (encoded=0) and the reindex-shaped
flag flip, per index variant. Sync sqlite3 — this measures SQLite index
maintenance, not vfs code.

Run: uv run python bench_maint.py  → maint_results.json
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

from time import perf_counter

HERE = Path(__file__).parent
CLONES = HERE / "clones"
SOURCE = CLONES / "empty.sqlite"

VARIANTS = {
    "v_base": [],  # existing schema: full index ix_vfs_encoded
    "v_partial": ["CREATE INDEX ix_vfs_pending ON vfs (encoded) WHERE NOT encoded"],
    "v_composite_add": ["CREATE INDEX ix_vfs_encoded_kind ON vfs (encoded, kind)"],
    "v_composite_repl": [
        "DROP INDEX ix_vfs_encoded",
        "CREATE INDEX ix_vfs_encoded_kind ON vfs (encoded, kind)",
    ],
}


def timed(con: sqlite3.Connection, label: str, fn) -> float:
    t0 = perf_counter()
    fn()
    con.commit()
    return (perf_counter() - t0) * 1e3  # ms


def run_variant(name: str, ddl: list[str]) -> dict:
    db = CLONES / f"maint_{name}.sqlite"
    db.unlink(missing_ok=True)
    Path(str(db) + "-wal").unlink(missing_ok=True)
    Path(str(db) + "-shm").unlink(missing_ok=True)
    subprocess.run(["cp", "-c", str(SOURCE), str(db)], check=True)
    out: dict = {"variant": name}
    con = sqlite3.connect(db)
    try:
        # prep: everything pending, the pre-reindex state (untimed)
        con.execute("UPDATE vfs SET encoded = 0 WHERE kind = 'file'")
        con.commit()
        t0 = perf_counter()
        for stmt in ddl:
            con.execute(stmt)
        con.commit()
        out["ddl_ms"] = (perf_counter() - t0) * 1e3
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        rows = [
            (
                bytes([i % 256, (i >> 8) % 256]) + bytes(14),
                f"/probe-study/d{i % 97}/f{i}.txt",
                f"f{i}.txt",
                "file",
                "txt",
            )
            for i in range(10_000)
        ]

        def insert_10k():
            con.executemany(
                "INSERT INTO vfs (entry_id, parent_id, path, name, kind, ext,"
                " lines, size_bytes, chunked, encoded, indexable)"
                " VALUES (?, NULL, ?, ?, ?, ?, 0, 0, 0, 0, 0)",
                [(eid + bytes([j % 256, j // 256]), p, n, k, e) for j, (eid, p, n, k, e) in enumerate(rows)],
            )

        out["insert_10k_ms"] = timed(con, "insert", insert_10k)
        out["pending_files"] = con.execute(
            "SELECT count(*) FROM vfs WHERE NOT encoded AND kind = 'file'"
        ).fetchone()[0]
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        def flip_all():
            con.execute("UPDATE vfs SET encoded = 1 WHERE encoded = 0 AND kind = 'file'")

        out["flip_all_ms"] = timed(con, "flip", flip_all)
        out["flipped"] = con.total_changes

        # index sizes (dbstat aggregated per index)
        try:
            sizes = con.execute(
                "SELECT name, sum(pgsize)/1024 AS kib, count(*) AS pages FROM dbstat"
                " WHERE name LIKE 'ix_vfs_encoded%' OR name LIKE 'ix_vfs_pending%'"
                " GROUP BY name"
            ).fetchall()
            out["index_sizes_kib"] = {n: k for n, k, _ in sizes}
        except sqlite3.OperationalError as exc:
            out["index_sizes_kib"] = f"dbstat unavailable: {exc}"
    finally:
        con.close()
    return out


def main() -> None:
    results = [run_variant(name, ddl) for name, ddl in VARIANTS.items()]
    (HERE / "maint_results.json").write_text(json.dumps(results, indent=2))
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
