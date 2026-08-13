"""Real-corpus grep bench: numpy vs pure-Python decode+intersect at k=4.

Runs the same rarest-4 posting blobs per pattern through three arms:
  numpy    - varint_decode_np + np.intersect1d (live design)
  py_naive - varint_decode_py for every blob, then set intersection
  py_fused - decode rarest blob to a set, stream-decode the rest checking
             membership inline (never materializes later lists)

Reports each arm's decode+intersect time next to the pipeline total so
"meaningfully adds latency" is judged against the whole grep, not in a vacuum.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

import numpy as np

SPIKE = Path("/Users/claygendron/Git/Repos/vfs/context/specs/active/072-database-storage-backend/spike")
sys.path.insert(0, str(SPIKE))
from spikelib import varint_decode_np, varint_decode_py  # noqa: E402

from vfs.models.code_grams import GramAnd, GramOr, build_code_gram_query  # noqa: E402

DATA = Path(
    "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/"
    "48cb69ff-7e4c-4af7-bf09-6b6e44c28f87/scratchpad/spike-data"
)

PATTERNS = [
    ("zero_hit", "xyzzy_unlikely_sentinel_42"),
    ("rare_ident", "EXPORT_SYMBOL_NS_GPL"),
    ("medium_ident", "kmalloc"),
    ("hot_ident", "return"),
    ("hot_phrase", "def __init__"),
    ("punct_arrow", "->next"),
    ("punct_neq_null", "!= NULL"),
    ("regex_probe", r"static\s+int\s+\w+_probe"),
    ("regex_wrapped", r".*alloc_page.*"),
    ("case_insens", r"(?i)Mutex_Lock"),
    ("class_prefix", r"[fF]oo_bar"),
]

K = 4
REPEATS = 5


def branches_of(query) -> list[set[int]]:
    if isinstance(query, GramAnd):
        return [set(query.grams)]
    if isinstance(query, GramOr):
        out = []
        for br in query.branches:
            out.extend(branches_of(br))
        return out
    return []


def py_fused_intersect(blobs: list[bytes]) -> list[int]:
    """Decode blob 0 into a set; stream-decode the rest, keeping members only."""
    current = set(varint_decode_py(blobs[0]))
    for blob in blobs[1:]:
        if not current:
            break
        keep = set()
        doc = -1
        val = 0
        shift = 0
        for byte in blob:
            val |= (byte & 0x7F) << shift
            if byte & 0x80:
                shift += 7
            else:
                doc += val
                if doc in current:
                    keep.add(doc)
                val = 0
                shift = 0
        current = keep
    return sorted(current)


def main() -> None:
    index = sqlite3.connect(DATA / "gram_index_990000.db")
    results = []
    for label, pattern in PATTERNS:
        q = build_code_gram_query(pattern)
        brs = branches_of(q)
        if not brs:
            continue
        # Gather the rarest-K blobs per branch, exactly as the planner would.
        branch_blobs: list[list[bytes]] = []
        for grams in brs:
            rows = index.execute(
                f"SELECT gram, doc_count FROM posting_list "
                f"WHERE gram IN ({','.join('?' * len(grams))})",
                list(grams),
            ).fetchall()
            if len(rows) < len(grams):
                branch_blobs.append([])
                continue
            rows.sort(key=lambda r: r[1])
            blobs = [
                index.execute(
                    "SELECT postings FROM posting_list WHERE gram=?", (g,)
                ).fetchone()[0]
                for g, _ in rows[:K]
            ]
            branch_blobs.append(blobs)

        def run_numpy() -> int:
            total = 0
            for blobs in branch_blobs:
                cand = None
                for blob in blobs:
                    ids = varint_decode_np(blob)
                    cand = ids if cand is None else np.intersect1d(cand, ids, assume_unique=True)
                    if len(cand) == 0:
                        break
                total += 0 if cand is None else len(cand)
            return total

        def run_py_naive() -> int:
            total = 0
            for blobs in branch_blobs:
                cand = None
                for blob in blobs:
                    ids = set(varint_decode_py(blob))
                    cand = ids if cand is None else cand & ids
                    if not cand:
                        break
                total += 0 if cand is None else len(cand)
            return total

        def run_py_fused() -> int:
            return sum(len(py_fused_intersect(blobs)) for blobs in branch_blobs if blobs)

        arms = {"numpy": run_numpy, "py_naive": run_py_naive, "py_fused": run_py_fused}
        row = {"label": label, "posting_bytes": sum(len(b) for bl in branch_blobs for b in bl)}
        counts = {}
        for name, fn in arms.items():
            times = []
            for _ in range(REPEATS):
                t0 = time.perf_counter()
                counts[name] = fn()
                times.append(time.perf_counter() - t0)
            row[name + "_ms"] = statistics.median(times) * 1000
        assert len(set(counts.values())) == 1, f"{label}: arms disagree {counts}"
        row["candidates"] = counts["numpy"]
        results.append(row)
        print(
            f"{label:<16} cand={row['candidates']:>8,}  bytes={row['posting_bytes']:>10,}  "
            f"np={row['numpy_ms']:>8.2f}ms  py_naive={row['py_naive_ms']:>8.2f}ms  "
            f"py_fused={row['py_fused_ms']:>8.2f}ms",
            flush=True,
        )
    (DATA / "bench_py_vs_np.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
