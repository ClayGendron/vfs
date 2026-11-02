"""Experiment 1: delta build cost vs the full base build.

Base: N docs under segment 0. Deltas: dirty sets of 100..25000 docs, each a
fresh segment, half re-posts (version 1 of a base id), half new ids above N.
"""

from __future__ import annotations

import json
import os
import random
import resource
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import open_store, build_segment  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
DB = os.path.join(HERE, "exp1.db")
for f in (DB, DB + "-wal", DB + "-shm"):
    if os.path.exists(f):
        os.remove(f)
conn = open_store(DB)

results = []
base = build_segment(conn, 0, [(i, 0) for i in range(1, N + 1)])
rss_base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
results.append({"set": f"base N={N}", **base.__dict__, "index_s": base.index_s, "maxrss_mb": rss_base})
print(json.dumps(results[-1]), flush=True)

rng = random.Random(7)
next_new = N + 1
seg = 1
for dirty in (100, 500, 2000, 6000, 25000):
    reposts = rng.sample(range(1, N + 1), dirty // 2)
    new = list(range(next_new, next_new + dirty - dirty // 2))
    next_new += len(new)
    docs = [(d, 1) for d in reposts] + [(d, 0) for d in new]
    t = build_segment(conn, seg, docs)
    seg += 1
    results.append({"set": f"delta {dirty}", **t.__dict__, "index_s": t.index_s})
    print(json.dumps(results[-1]), flush=True)

with open(os.path.join(HERE, "exp1_results.json"), "w") as fh:
    json.dump(results, fh, indent=1)

size = sum(os.path.getsize(DB + s) for s in ("", "-wal") if os.path.exists(DB + s))
print("db bytes", size)
