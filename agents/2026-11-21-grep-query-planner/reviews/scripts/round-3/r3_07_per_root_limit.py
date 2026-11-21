"""Decisions 3 and 5: the probe limit is per root. Rows the probe reads with k roots, per-root LIMIT vs one LIMIT over the union.

Raw SQL, read-only sandbox. Limit L = min(U, SCAN_TIER_BUDGET) + 1 = 25,001 for a pattern whose U exceeds the budget
(`struct`, U = 57,528 in r3_03), and L = T + 1 = 141 for the first probe.
"""
import sqlite3, sys
raw = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
tops = [p for (p,) in raw.execute("SELECT path FROM vfs_entries WHERE kind='directory' AND parent_id = (SELECT entry_id FROM vfs_entries WHERE path='/') AND path NOT LIKE '/.%' ORDER BY path")]
drv = [p for (p,) in raw.execute("SELECT path FROM vfs_entries WHERE kind='directory' AND parent_id = (SELECT entry_id FROM vfs_entries WHERE path='/drivers') ORDER BY path")]
for label, roots in (("top-level dirs", tops), ("/drivers/* dirs", drv)):
    for limit in (141, 25001):
        per_root = 0
        for r in roots:
            per_root += len(raw.execute("SELECT id FROM vfs_entries WHERE path > ? AND path < ? LIMIT ?", (r + "/", r + "0", limit)).fetchall())
        union = " UNION ALL ".join("SELECT id FROM (SELECT id FROM vfs_entries WHERE path > ? AND path < ? LIMIT ?)" for _ in roots)
        params = [x for r in roots for x in (r + "/", r + "0", limit)]
        one = len(raw.execute(f"SELECT id FROM ({union}) LIMIT ?", [*params, limit]).fetchall())
        print(f"{label:16} k={len(roots):4} L={limit:6}: per-root LIMIT reads {per_root:>7,} rows; one outer LIMIT returns {one:>6,}")
