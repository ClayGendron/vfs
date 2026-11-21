"""E1: what the existing path index answers about a scope, and at what cost.

For each scope root, on a read-only connection to the sandbox:

- ``probe(T)``: ``SELECT id, size_bytes FROM vfs_entries WHERE kind='file' AND path > root||'/' AND path < root||'0'
  LIMIT T+1``, the bounded question "does the scope hold more than T files, and if not, which and how big".
- ``range_ids``: the same predicate unbounded, the exact scope id set by path range.
- ``segment_ids``: today's allow-list shape for the root, the rarest-first segment self-join over the root's components,
  plus the parent-only arm that admits the root entry itself.

    uv run python agents/2026-11-21-grep-query-planner/experiments/e1_scope_probe.py linux.db
"""

from __future__ import annotations

import sqlite3
import statistics
import sys
import time

SCOPES = ("mm/tests", "kernel/kcsan", "drivers/atm", "drivers/md", "drivers/gpu/drm/amd/display/dc", "drivers/media",
          "drivers/gpu", "drivers", "fs", "include")  # fmt: skip
THRESHOLDS = (256, 1024, 4096)
REPS = 7


def timed(conn: sqlite3.Connection, sql: str, params: tuple) -> tuple[float, int]:
    times = []
    count = 0
    for repetition in range(REPS + 1):
        started = time.perf_counter()
        count = len(conn.execute(sql, params).fetchall())
        if repetition:
            times.append((time.perf_counter() - started) * 1000)
    return statistics.median(times), count


def segment_sql(components: list[str]) -> tuple[str, tuple]:
    joins = " ".join(f"JOIN vfs_segments s{i} ON s{i}.entry_id = s0.entry_id" for i in range(1, len(components)))
    where = " AND ".join(f"s{i}.segment = ?" for i in range(len(components)))
    sql = f"SELECT e.id FROM vfs_segments s0 {joins} JOIN vfs_entries e ON e.entry_id = s0.entry_id WHERE {where}"
    return sql, tuple(components)


def main() -> None:
    conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    counts = dict(conn.execute("SELECT segment, count(*) FROM vfs_segments GROUP BY segment"))
    rng = "kind = 'file' AND path > ? AND path < ?"
    print("| scope | files | range_ids ms | segment allow-list ms (ids) | " +
          " | ".join(f"probe T={t} ms" for t in THRESHOLDS) + " |")  # fmt: skip
    print("|---|---|---|---|" + "---|" * len(THRESHOLDS))
    for scope in SCOPES:
        low, high = f"/{scope}/", f"/{scope}0"
        range_ms, files = timed(conn, f"SELECT id FROM vfs_entries WHERE {rng}", (low, high))
        components = sorted(scope.split("/"), key=lambda term: counts.get(term, 0))[:4]
        subtree_sql, subtree_params = segment_sql(components)
        parent = scope.split("/")[:-1]
        segment_ms, segment_ids = timed(conn, subtree_sql, subtree_params)
        if parent:
            parent_sql, parent_params = segment_sql(sorted(parent, key=lambda term: counts.get(term, 0))[:4])
            parent_ms, parent_ids = timed(conn, parent_sql, parent_params)
            segment_ms += parent_ms
            segment_ids += parent_ids
        probes = []
        for threshold in THRESHOLDS:
            probe_ms, _ = timed(
                conn, f"SELECT id, size_bytes FROM vfs_entries WHERE {rng} LIMIT ?", (low, high, threshold + 1)
            )
            probes.append(f"{probe_ms:.2f}")
        print(f"| {scope} | {files} | {range_ms:.2f} | {segment_ms:.2f} ({segment_ids}) | {' | '.join(probes)} |")
    plan = conn.execute(f"EXPLAIN QUERY PLAN SELECT id, size_bytes FROM vfs_entries WHERE {rng} LIMIT 5",
                        ("/a/", "/a0")).fetchall()  # fmt: skip
    print("\nprobe plan:", [row[-1] for row in plan])


if __name__ == "__main__":
    main()
