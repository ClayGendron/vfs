"""Decisions 7 and 8: does turning the literal test on change the statistic that turns it on?

Raw SQL on the read-only sandbox. One content batch of the same 600 bodies is fetched twice: as today, and with
decision 7's `instr(content, :lit) > 0`. For each: median of 7 warm runs, bytes returned, bytes the server read.
c_byte, "the observed body bytes per second of content batches", is computed both ways it could be read.

    uv run python r3_05_cbyte_feedback.py linux.db
"""

import sqlite3
import statistics
import sys
import time

DB = sys.argv[1]
raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
ids = [
    r[0]
    for r in raw.execute(
        "SELECT entry_id FROM vfs_entries WHERE kind='file' AND encoded AND path > '/fs/' AND path < '/fs0' "
        "AND size_bytes < 200000 ORDER BY id LIMIT 600"
    )
]
scanned = raw.execute(
    f"SELECT sum(length(CAST(content AS BLOB))) FROM vfs_content WHERE entry_id IN ({','.join('?' * len(ids))})", ids
).fetchone()[0]
marks = ",".join("?" * len(ids))
plain = f"SELECT entry_id, content FROM vfs_content WHERE entry_id IN ({marks})"
tested = plain + " AND instr(content, ?) > 0"


def run(sql, params):
    times, got = [], 0
    for _ in range(8):
        t = time.perf_counter()
        rows = raw.execute(sql, params).fetchall()
        times.append(time.perf_counter() - t)
        got = sum(len(c.encode("utf-8", "surrogatepass")) for _, c in rows)
    return statistics.median(times[1:]), got, len(rows)


for label, sql, params in (("today", plain, ids), ("instr", tested, [*ids, "__follow_mount_rcu"])):
    secs, returned, n = run(sql, params)
    print(
        f"{label:6} rows {n:4} returned {returned:>11,} B  server read {scanned:>11,} B  {secs * 1e3:7.2f} ms  "
        f"c_byte by returned {secs / max(returned, 1) * 1e9:9.2f} ns/B  by read {secs / scanned * 1e9:6.2f} ns/B"
    )
