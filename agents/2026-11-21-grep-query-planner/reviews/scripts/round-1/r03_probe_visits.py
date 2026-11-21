"""Decision 3: is the bounded probe's cost bounded by T when the scope's rows fail its residual terms?

Read-only raw SQL on the sandbox. A Python function counts every row the probe's access path hands to the WHERE
clause, so the figure is rows visited, not time. Residual terms tried: the trash side (`deleted_at IS NOT NULL`, the
probe a grep under /.vfs/trash/<root> issues), and a stand-in for a partial caller's view that admits 10 rows.
"""
from __future__ import annotations

import sqlite3
import sys

conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
visits = [0]


def visit(_: int) -> int:
    visits[0] += 1
    return 1


conn.create_function("visit", 1, visit, deterministic=False)
print("everyone_level:", conn.execute("select everyone_level, count(*) from vfs_entries group by 1").fetchall())
T = 1024
ROOTS = ["/drivers/atm", "/drivers/md", "/drivers/gpu", "/drivers"]
for root in ROOTS:
    lo, hi = root + "/", root + "0"
    in_range = conn.execute("select count(*) from vfs_entries where path > ? and path < ?", (lo, hi)).fetchone()[0]
    visible = {row[0] for row in conn.execute(
        "select id from vfs_entries where kind='file' and path > ? and path < ? order by id limit 10", (lo, hi))}
    conn.create_function("visible", 1, lambda i, v=visible: int(i in v), deterministic=False)
    probes = {
        "live probe (spec)": "kind = 'file' AND deleted_at IS NULL",
        "trash-side probe": "kind = 'file' AND deleted_at IS NOT NULL",
        "partial view (10 rows visible)": "kind = 'file' AND deleted_at IS NULL AND visible(id)",
    }
    for label, residual in probes.items():
        sql = (f"SELECT id, size_bytes, encoded FROM vfs_entries WHERE path > ? AND path < ? "
               f"AND visit(id) AND {residual} LIMIT ?")
        plan = [r[-1] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, (lo, hi, T + 1))]
        visits[0] = 0
        n = len(conn.execute(sql, (lo, hi, T + 1)).fetchall())
        print(f"{root:14} rows_in_range={in_range:6}  {label:32} returned={n:5} visited={visits[0]:6}  plan={plan}")
