"""Experiment 7: line-offset sidecar — what fraction of verify is line scanning.

Times the real Rust verify (hit_lines, count_lines) over the mutex_lock@drm
candidate bodies, then the candidate line-boundary work in isolation:
utf-8 encode, full-body newline count (upper bound of any line scanning the
core could do), and Python splitlines. RUNS=5 medians.
"""

from __future__ import annotations

import json
import statistics
import time

from common import OUT, connect, fetch_contents
from vfs.pattern_matching.grep import compile_verifier

RUNS = 5

con = connect()
with open(f"{OUT}/candidates.json") as f:
    row = json.load(f)["mutex_lock@drm"]
texts = list(fetch_contents(con, [bytes.fromhex(c["entry_id"]) for c in row["candidates"]]).values())
total_bytes = sum(len(t.encode()) for t in texts)
print(f"{len(texts)} bodies, {total_bytes/1e6:.1f}MB")

verifier = compile_verifier("mutex_lock", fixed_strings=False, word_regexp=False, case_mode="smart")

def med(fn):
    times = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times), sorted(times)

hit_ms, hit_all = med(lambda: verifier.hit_lines(texts, before=0, after=0, cap=None, invert=False, budget=None))
cnt_ms, cnt_all = med(lambda: verifier.count_lines(texts, cap=1, invert=False, budget=None))
bodies = [t.encode("utf-8", "surrogatepass") for t in texts]
enc_ms, enc_all = med(lambda: [t.encode("utf-8", "surrogatepass") for t in texts])
nl_ms, nl_all = med(lambda: sum(b.count(b"\n") for b in bodies))
split_ms, split_all = med(lambda: [t.split("\n") for t in texts])

out = {
    "bodies": len(texts),
    "bytes": total_bytes,
    "verify_hit_lines_ms": hit_ms,
    "verify_count_lines_cap1_ms": cnt_ms,
    "utf8_encode_ms": enc_ms,
    "newline_count_ms": nl_ms,
    "python_splitlines_ms": split_ms,
    "runs": {"hit": hit_all, "count": cnt_all, "encode": enc_all, "newline": nl_all, "split": split_all},
}
for k, v in out.items():
    if k != "runs":
        print(f"{k:28s}: {v}")
with open(f"{OUT}/exp7_lineoffsets.json", "w") as f:
    json.dump(out, f, indent=1)
