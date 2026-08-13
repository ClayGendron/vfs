"""Four-arm decode+intersect bench on the 990K real-code corpus at k=4.

Arms: numpy (live design), py_fused (best stdlib spelling), rust_fused
(vfs_postings_rs.intersect_rarest), rust_decode_only (decode in Rust,
intersect via numpy — isolates decode vs fusion wins).
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import vfs_postings_rs as rs

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
REPEATS = 7


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
        brs = branches_of(build_code_gram_query(pattern))
        if not brs:
            continue
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
            branch_blobs.append([
                index.execute(
                    "SELECT postings FROM posting_list WHERE gram=?", (g,)
                ).fetchone()[0]
                for g, _ in rows[:K]
            ])
        branch_blobs = [b for b in branch_blobs if b]

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

        def run_py_fused() -> int:
            return sum(len(py_fused_intersect(blobs)) for blobs in branch_blobs)

        def run_rust_fused() -> int:
            return sum(len(rs.intersect_rarest(list(blobs))) for blobs in branch_blobs)

        def run_rust_decode_np() -> int:
            total = 0
            for blobs in branch_blobs:
                cand = None
                for blob in blobs:
                    ids = np.asarray(rs.decode_postings(blob), dtype=np.int64)
                    cand = ids if cand is None else np.intersect1d(cand, ids, assume_unique=True)
                    if len(cand) == 0:
                        break
                total += 0 if cand is None else len(cand)
            return total

        arms = {
            "numpy": run_numpy,
            "py_fused": run_py_fused,
            "rust_fused": run_rust_fused,
            "rust_dec+np": run_rust_decode_np,
        }
        row = {"label": label}
        counts = {}
        for name, fn in arms.items():
            times = []
            for _ in range(REPEATS):
                t0 = time.perf_counter()
                counts[name] = fn()
                times.append(time.perf_counter() - t0)
            row[name] = statistics.median(times) * 1000
        assert len(set(counts.values())) == 1, f"{label}: arms disagree {counts}"
        row["candidates"] = counts["numpy"]
        results.append(row)
        print(
            f"{label:<16} cand={row['candidates']:>8,}  "
            f"np={row['numpy']:>7.2f}ms  py={row['py_fused']:>8.2f}ms  "
            f"rust={row['rust_fused']:>6.3f}ms  rust_dec+np={row['rust_dec+np']:>7.2f}ms  "
            f"(rust vs np: {row['numpy'] / row['rust_fused']:>5.1f}x)",
            flush=True,
        )
    (DATA / "bench_rust_arm.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
