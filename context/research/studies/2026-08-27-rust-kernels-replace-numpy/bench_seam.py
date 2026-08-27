"""Seam-shape costs: survivors as bytes / list / numpy at the ``DocIds`` boundary.

What ``grep_rows`` does with the ladder's survivors after the algebra:
slice to ``CANDIDATE_BUDGET`` (25,000), intersect with a scoped
allow-list, and hand ``tolist()`` to the ``IN``-list chunker. This
times each of those on the three candidate shapes a kernel could
return — packed int64 bytes, a Python list (pyo3 ``Vec<i64>``), and
the current numpy array — at the widest real candidate set the store
produces (``return``: 46,335 entries) and at the budget itself.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import vfs_kernels_rs as rs

import kernels_py as kp
from benchlib import DB, dump, machine, timed_ms

CANDIDATE_BUDGET = 25_000

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
# The widest single posting list stands in for the widest ladder result.
blob = con.execute("SELECT postings FROM vfs_grams_posting_list ORDER BY doc_count DESC LIMIT 1").fetchone()[0]
raw = rs.decode_postings(blob)
ids_list = kp.from_q(raw)
ids_np = np.frombuffer(raw, dtype=np.int64)
n = len(ids_list)
entry_ids = [r[0] for r in con.execute("SELECT id FROM vfs WHERE kind='file' ORDER BY id")]
allow = sorted(random.Random(7).sample(entry_ids, 10_000))
allow_np = np.asarray(allow, dtype=np.int64)
allow_q = kp.to_q(allow)

rows = {
    "widest_ids": n,
    "budget": CANDIDATE_BUDGET,
    # Producing each shape from the kernel's bytes.
    "bytes_to_list_ms": timed_ms(lambda: kp.from_q(raw)),
    "bytes_to_numpy_ms": timed_ms(lambda: np.frombuffer(raw, dtype=np.int64)),
    "kernel_returns_list_ms": timed_ms(lambda: rs.decode_postings_list(blob)) - timed_ms(lambda: rs.decode_postings(blob)),
    # The CANDIDATE_BUDGET slice.
    "slice_bytes_ms": timed_ms(lambda: raw[: CANDIDATE_BUDGET * 8]),
    "slice_list_ms": timed_ms(lambda: ids_list[:CANDIDATE_BUDGET]),
    "slice_numpy_ms": timed_ms(lambda: ids_np[:CANDIDATE_BUDGET]),
    # tolist() for the IN-list chunker (what _entries_for_docs needs).
    "tolist_from_bytes_budget_ms": timed_ms(lambda: kp.from_q(raw[: CANDIDATE_BUDGET * 8])),
    "tolist_from_numpy_budget_ms": timed_ms(lambda: ids_np[:CANDIDATE_BUDGET].tolist()),
    "tolist_from_list_budget_ms": timed_ms(lambda: list(ids_list[:CANDIDATE_BUDGET])),
    # The allow-list intersect (10,000-entry scope) on each shape.
    "allow_numpy_ms": timed_ms(lambda: np.intersect1d(ids_np, allow_np, assume_unique=True)),
    "allow_rust_bytes_ms": timed_ms(lambda: rs.intersect_sorted(raw, allow_q)),
    "allow_rust_bytes_incl_pack_ms": timed_ms(lambda: rs.intersect_sorted(raw, kp.to_q(allow))),
    "allow_stdlib_list_ms": timed_ms(lambda: kp.intersect_sorted(ids_list, allow)),
    "allow_survivors": int(np.intersect1d(ids_np, allow_np, assume_unique=True).size),
    # Memory of each shape (bytes held for the widest set).
    "bytes_payload_kb": len(raw) / 1024,
    "numpy_payload_kb": ids_np.nbytes / 1024,
    "list_payload_kb": (sys.getsizeof(ids_list) + sum(sys.getsizeof(i) for i in ids_list[:1000]) * n / 1000) / 1024,
}
for k, v in rows.items():
    print(f"{k:<32} {v:,.4f}" if isinstance(v, float) else f"{k:<32} {v}")
dump("seam.json", {"machine": machine(), **rows})
