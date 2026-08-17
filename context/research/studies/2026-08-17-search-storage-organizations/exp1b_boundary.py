"""Exp 1 follow-up: chunk-boundary false negatives for chunk-granularity postings.

For each bench row, count chunks that contain a matching line yet do NOT
contain all chosen grams (their postings would not nominate the chunk):
the recall hole a chunk-granularity index must close (overlap windows or
boundary-spanning gram emission).
"""

from __future__ import annotations

import json

import numpy as np

from common import OUT, connect
from vfs.native import folded_bytes


def gram_array(data: bytes) -> np.ndarray:
    if len(data) < 3:
        return np.empty(0, dtype=np.int64)
    d = np.frombuffer(data, dtype=np.uint8).astype(np.int64)
    return (d[:-2] << 16) | (d[1:-1] << 8) | d[2:]


con = connect()
with open(f"{OUT}/candidates.json") as f:
    cand = json.load(f)

report = {}
for label, row in cand.items():
    chosen = np.array(row["nominate"]["chosen_grams"], dtype=np.int64)
    path_to_eid = {c["path"]: c["entry_id"] for c in row["candidates"]}
    missed = 0
    total = 0
    examples = []
    paths = list(row["matches"])
    for i in range(0, len(paths), 400):
        batch = paths[i : i + 400]
        eids = [bytes.fromhex(path_to_eid[p]) for p in batch]
        eid_to_path = {e: p for e, p in zip(eids, batch)}
        q = (
            f"SELECT entry_id, line_start, line_end, content FROM vfs_chunks "
            f"WHERE entry_id IN ({','.join('?' * len(eids))})"
        )
        for eid, ls, le, content in con.execute(q, eids):
            lines = row["matches"][eid_to_path[bytes(eid)]]
            if not any(ls <= ln <= le for ln in lines):
                continue
            total += 1
            g = gram_array(folded_bytes(content))
            if not np.isin(chosen, g).all():
                missed += 1
                if len(examples) < 3:
                    examples.append((eid_to_path[bytes(eid)], ls, le))
    report[label] = {"match_chunks": total, "gram_missed_chunks": missed, "examples": examples}
    print(f"{label:28s} match_chunks={total:6d} would-miss={missed:4d} ({100*missed/max(total,1):.2f}%) {examples[:2]}")

with open(f"{OUT}/exp1b_boundary.json", "w") as f:
    json.dump(report, f, indent=1)
