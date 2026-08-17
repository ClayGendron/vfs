"""Experiment 3: content clustering by path — fetch order timing + physical scatter.

Timing: fetch the mutex_lock@drm candidate bodies under four orders —
pipeline (path-ordered 32MB batches, entry_id-sorted within batch, the live
code's shape), path order, surrogate-id order, and vfs_content rowid
(physical) order. Cold = fresh `cp -c` clone + fresh connection per run
(page cache is keyed by vnode, so a new clone defeats it without sudo);
warm = repeat on the same connection. RUNS=5 medians.

Scatter: map each candidate row to its true pages via dbstat (leaves in
path order are cells in rowid order; overflow paths name their cell) and
compare pages touched vs the contiguous minimum.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
from collections import defaultdict

from common import DB, OUT, SP, connect

RUNS = 5
CONTENT_BYTE_BUDGET = 32 * 1024 * 1024
CHUNK = 500

with open(f"{OUT}/candidates.json") as f:
    row = json.load(f)["mutex_lock@drm"]
cands = row["candidates"]  # path-ordered already

con = connect()
# rowid + vfs.id mapping for candidates.
eids = [bytes.fromhex(c["entry_id"]) for c in cands]
eid_hex_to_meta = {c["entry_id"]: c for c in cands}
rowid_of = {}
for i in range(0, len(eids), 500):
    b = eids[i : i + 500]
    for rid, eid in con.execute(
        f"SELECT rowid, entry_id FROM vfs_content WHERE entry_id IN ({','.join('?' * len(b))})", b
    ):
        rowid_of[bytes(eid).hex()] = rid

# --- orders ---------------------------------------------------------------
def order_pipeline():
    """32MB path-ordered batches; entry_id-sorted, 500-chunked within batch."""
    batches, batch, total = [], [], 0
    for c in cands:
        if batch and total + c["size_bytes"] > CONTENT_BYTE_BUDGET:
            batches.append(batch)
            batch, total = [], 0
        batch.append(c)
        total += c["size_bytes"]
    if batch:
        batches.append(batch)
    chunks = []
    for b in batches:
        ordered = sorted(bytes.fromhex(c["entry_id"]) for c in b)
        for i in range(0, len(ordered), CHUNK):
            chunks.append(ordered[i : i + CHUNK])
    return chunks


def chunked_order(keyed):
    ordered = [bytes.fromhex(c["entry_id"]) for c in keyed]
    return [ordered[i : i + CHUNK] for i in range(0, len(ordered), CHUNK)]


ORDERS = {
    "pipeline (path batches, uuid within)": order_pipeline(),
    "path order": chunked_order(cands),
    "surrogate id order": chunked_order(sorted(cands, key=lambda c: c["id"])),
    "physical rowid order": chunked_order(sorted(cands, key=lambda c: rowid_of[c["entry_id"]])),
}

CLONE = f"{SP}/storage-org-arith/clone.sqlite"


def clone():
    for suf in ("", "-wal", "-shm"):
        dst = CLONE + suf
        if os.path.exists(dst):
            os.unlink(dst)
        if os.path.exists(DB + suf):
            subprocess.run(["cp", "-c", DB + suf, dst], check=True)


def fetch(conn, chunks):
    t0 = time.perf_counter()
    n = 0
    total = 0
    for ch in chunks:
        q = f"SELECT entry_id, content FROM vfs_content WHERE entry_id IN ({','.join('?' * len(ch))})"
        for _eid, content in conn.execute(q, ch):
            n += 1
            total += len(content)
    return (time.perf_counter() - t0) * 1000, n, total


timing = {}
for name, chunks in ORDERS.items():
    cold, warm = [], []
    for _ in range(RUNS):
        clone()
        c2 = connect(CLONE)
        ms, n, total = fetch(c2, chunks)
        cold.append(ms)
        ms2, _, _ = fetch(c2, chunks)
        warm.append(ms2)
        c2.close()
    timing[name] = {
        "cold_ms": sorted(cold),
        "warm_ms": sorted(warm),
        "cold_median_ms": statistics.median(cold),
        "warm_median_ms": statistics.median(warm),
        "rows": n,
        "bytes": total,
    }
    print(f"{name:38s} cold={statistics.median(cold):8.1f}ms warm={statistics.median(warm):8.1f}ms rows={n}")

for suf in ("", "-wal", "-shm"):
    if os.path.exists(CLONE + suf):
        os.unlink(CLONE + suf)

# --- physical scatter via dbstat ------------------------------------------
all_rowids = [r[0] for r in con.execute("SELECT rowid FROM vfs_content ORDER BY rowid")]
rank = {rid: i for i, rid in enumerate(all_rowids)}
stat = con.execute(
    "SELECT path, pageno, pagetype, ncell FROM dbstat WHERE name='vfs_content'"
).fetchall()
leaves = sorted((p, pageno, ncell) for p, pageno, ptype, ncell in stat if ptype == "leaf")
overflow = defaultdict(list)  # (leafpath, cellhex) -> [pageno,...] in chain order
for p, pageno, ptype, _nc in stat:
    if ptype == "overflow":
        leafpath, cell = p.rsplit("/", 1)
        cellhex, chain = cell.split("+")
        overflow[(leafpath + "/", cellhex)].append((int(chain, 16), pageno))

# ordinal -> (leafpath, leaf pageno, cell index)
cum = 0
ordinal_leaf = []
for p, pageno, ncell in leaves:
    ordinal_leaf.append((cum, cum + ncell, p, pageno))
    cum += ncell
assert cum == len(all_rowids), (cum, len(all_rowids))


def pages_for(ordinal):
    import bisect
    lo, hi = 0, len(ordinal_leaf) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if ordinal_leaf[mid][1] <= ordinal:
            lo = mid + 1
        else:
            hi = mid
    start, _end, p, pageno = ordinal_leaf[lo]
    cellhex = format(ordinal - start, "03x")
    chain = sorted(overflow.get((p, cellhex), []))
    return pageno, [pg for _i, pg in chain]


cand_pages = set()
leaf_pages = set()
for c in cands:
    ordv = rank[rowid_of[c["entry_id"]]]
    leaf, chain = pages_for(ordv)
    leaf_pages.add(leaf)
    cand_pages.add(leaf)
    cand_pages.update(chain)

total_bytes = row["total_fetch_bytes"]
page_size = 16384
min_pages = -(-total_bytes // (page_size - 4))
pages_sorted = sorted(cand_pages)
runs = 1 + sum(1 for a, b in zip(pages_sorted, pages_sorted[1:]) if b != a + 1)
span = pages_sorted[-1] - pages_sorted[0] + 1
scatter = {
    "candidates": len(cands),
    "candidate_bytes": total_bytes,
    "pages_touched": len(cand_pages),
    "leaf_pages_touched": len(leaf_pages),
    "min_contiguous_pages": min_pages,
    "page_overhead_factor": len(cand_pages) / min_pages,
    "contiguous_runs": runs,
    "page_span": span,
    "table_pages": len(stat),
}
print(scatter)
with open(f"{OUT}/exp3_clustering.json", "w") as f:
    json.dump({"timing": timing, "scatter": scatter}, f, indent=1)
