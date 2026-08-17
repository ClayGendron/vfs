"""Experiment 4: exact-duplicate content across the corpus + bench-row savings.

One streaming pass hashing every encoded file body (the store also carries a
content_hash column — verified against, then trusted if it matches sha256 on
a sample). Reports duplicate files/bytes corpus-wide and, per bench row, the
fetch/verify bytes a content-addressed layout would save on that row.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict

from common import OUT, connect

con = connect()

# Is the stored content_hash trustworthy? Sample 20 rows.
sample = con.execute(
    "SELECT v.content_hash, c.content FROM vfs v JOIN vfs_content c ON c.entry_id=v.entry_id "
    "WHERE v.kind='file' AND v.encoded=1 LIMIT 20"
).fetchall()
algo = None
for h, content in sample:
    if h == hashlib.sha256(content.encode("utf-8")).hexdigest():
        algo = "sha256(utf8)"
    else:
        algo = None
        break
print("stored content_hash matches sha256(utf8):", algo is not None)

if algo:
    rows = con.execute(
        "SELECT content_hash, size_bytes, path FROM vfs WHERE kind='file' AND encoded=1"
    ).fetchall()
else:
    rows = []
    cur = con.execute(
        "SELECT v.path, v.size_bytes, c.content FROM vfs v JOIN vfs_content c ON c.entry_id=v.entry_id "
        "WHERE v.kind='file' AND v.encoded=1"
    )
    while batch := cur.fetchmany(500):
        for path, size, content in batch:
            rows.append((hashlib.sha256(content.encode("utf-8")).hexdigest(), size, path))

by_hash = defaultdict(list)
for h, size, path in rows:
    by_hash[h].append((size, path))

n_files = len(rows)
total_bytes = sum(size for _h, size, _p in rows)
dup_groups = {h: v for h, v in by_hash.items() if len(v) > 1}
dup_files = sum(len(v) - 1 for v in dup_groups.values())  # redundant copies
dup_bytes = sum((len(v) - 1) * v[0][0] for v in dup_groups.values())
biggest = sorted(dup_groups.values(), key=lambda v: (len(v) - 1) * v[0][0], reverse=True)[:5]

print(f"files={n_files:,} bytes={total_bytes:,}")
print(f"duplicate groups={len(dup_groups):,} redundant copies={dup_files:,} ({100*dup_files/n_files:.2f}%)")
print(f"redundant bytes={dup_bytes:,} ({100*dup_bytes/total_bytes:.2f}%)")
for v in biggest:
    print(f"  group n={len(v)} size={v[0][0]:,} e.g. {v[0][1]}")

hash_of_path = {p: h for h, s, p in rows}
with open(f"{OUT}/candidates.json") as f:
    cand = json.load(f)
bench = {}
for label, row in cand.items():
    counts = Counter(hash_of_path[c["path"]] for c in row["candidates"])
    saved = sum((n - 1) * s for h, n in counts.items() if n > 1
                for s in [by_hash[h][0][0]])
    dup_cand = sum(n - 1 for n in counts.values() if n > 1)
    bench[label] = {
        "candidates": len(row["candidates"]),
        "duplicate_candidates": dup_cand,
        "fetch_bytes_today": row["total_fetch_bytes"],
        "bytes_saved_by_cas": saved,
        "saving_pct": 100 * saved / row["total_fetch_bytes"],
    }
    print(f"{label:28s} dup_candidates={dup_cand:4d} saved={saved/1e6:6.2f}MB ({bench[label]['saving_pct']:.2f}%)")

with open(f"{OUT}/exp4_dedup.json", "w") as f:
    json.dump(
        {
            "hash_source": algo or "recomputed sha256",
            "files": n_files,
            "bytes": total_bytes,
            "dup_groups": len(dup_groups),
            "redundant_files": dup_files,
            "redundant_bytes": dup_bytes,
            "redundant_files_pct": 100 * dup_files / n_files,
            "redundant_bytes_pct": 100 * dup_bytes / total_bytes,
            "bench_rows": bench,
        },
        f,
        indent=1,
    )
