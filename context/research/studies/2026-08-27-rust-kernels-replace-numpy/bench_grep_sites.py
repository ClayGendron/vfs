"""Sites 1 and 2 on the full linux store: posting decode and the ladder's set algebra.

For each pattern the live planner's choice is reproduced exactly —
``build_code_gram_query`` → ``_plan_groups`` → ``_posting_meta`` →
``_choose_grams`` (k=4 rarest-first under the byte budget) →
``_posting_blobs`` — so every arm runs over the blobs ``grep_rows``
would decode. Arms: numpy (live code), stdlib (kernels_py), Rust
(vfs_kernels_rs). Results are asserted identical before timing.

    uv run --project <repo> --with <wheel> python bench_grep_sites.py
"""

from __future__ import annotations

import asyncio
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import vfs_kernels_rs as rs

import kernels_py as kp
import vfs.storage.backends.database.grep as grep_mod
from benchlib import DB, REPEATS, dump, machine, peak_kb, timed_ms
from vfs.models.code_grams import build_code_gram_query
from vfs.models.postings import decode_postings
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.indexing import current_epoch

PATTERNS = [
    ("zero_hit", "xyzzy_no_such_symbol_42"),
    ("rare_ident", "randomize_kstack_offset"),
    ("rare_macro", "EXPORT_SYMBOL_NS_GPL"),
    ("medium_ident", "kmalloc"),
    ("word_heavy", "pr_debug"),
    ("regex_probe", r"static\s+int\s+\w+_probe"),
    ("punct_arrow", "->next"),
    ("punct_neq_null", "!= NULL"),
    ("alloc_page", "alloc_page"),
    ("hot_ident", "return"),
    ("hot_alt", r"(mutex_lock|spin_lock)"),
]
ALLOW_SIZES = (1_000, 10_000)


def numpy_ladder(chosen_blobs: list[list[bytes]]) -> np.ndarray:
    """The live ``_index_doc_ids`` post-fetch algebra, verbatim in shape."""
    parts = [np.empty(0, dtype=np.int64)]
    for blobs in chosen_blobs:
        ids = None
        for blob in blobs:
            decoded = decode_postings(blob)
            ids = decoded if ids is None else np.intersect1d(ids, decoded, assume_unique=True)
            if ids.size == 0:
                break
        if ids is not None:
            parts.append(ids)
    return np.unique(np.concatenate(parts))


def stdlib_ladder(chosen_blobs: list[list[bytes]]) -> list[int]:
    parts = [kp.intersect_rarest(blobs) for blobs in chosen_blobs if blobs]
    return kp.union_sorted(parts) if parts else []


def rust_ladder(chosen_blobs: list[list[bytes]]) -> bytes:
    parts = [rs.intersect_rarest(blobs) for blobs in chosen_blobs if blobs]
    if len(parts) == 1:
        return parts[0]
    return rs.union_sorted(parts)


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    host = storage._host
    tables, budget = host.tables, host.membership_budget
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    entry_ids = [r[0] for r in con.execute("SELECT id FROM vfs WHERE kind='file' AND encoded=1 ORDER BY id")]
    rng = random.Random(7)
    allow_lists = {n: sorted(rng.sample(entry_ids, n)) for n in ALLOW_SIZES}

    results = []
    site1 = []
    async with host.session_factory() as session:
        epoch = await current_epoch(session, tables)
        for label, pattern in PATTERNS:
            plan = build_code_gram_query(pattern)
            groups = grep_mod._plan_groups(plan)
            grams = sorted({g for group in groups for g in group})
            meta = await grep_mod._posting_meta(session, tables, budget, epoch, grams)
            chosen = grep_mod._choose_grams(groups, meta)
            wanted = sorted({g for gc in chosen if gc for g in gc})
            blobs = await grep_mod._posting_blobs(session, tables, budget, epoch, wanted)
            chosen_blobs = [[blobs[g] for g in gc] for gc in chosen if gc]
            blob_bytes = sum(len(b) for gc in chosen_blobs for b in gc)
            postings = sum(meta[g].doc_count for gc in chosen if gc for g in gc)

            # --- site 2: the whole ladder -----------------------------------
            ref = numpy_ladder(chosen_blobs).tolist()
            assert ref == stdlib_ladder(chosen_blobs) == kp.from_q(rust_ladder(chosen_blobs)), label
            row = {
                "label": label,
                "pattern": pattern,
                "groups": len(chosen_blobs),
                "grams_fetched": len(wanted),
                "postings_decoded": postings,
                "blob_bytes": blob_bytes,
                "candidates": len(ref),
                "ladder_numpy_ms": timed_ms(lambda: numpy_ladder(chosen_blobs)),
                "ladder_stdlib_ms": timed_ms(lambda: stdlib_ladder(chosen_blobs)),
                "ladder_rust_ms": timed_ms(lambda: rust_ladder(chosen_blobs)),
                "ladder_rust_tolist_ms": timed_ms(lambda: kp.from_q(rust_ladder(chosen_blobs))),
                "ladder_numpy_peak_kb": peak_kb(lambda: numpy_ladder(chosen_blobs)),
                "ladder_stdlib_peak_kb": peak_kb(lambda: stdlib_ladder(chosen_blobs)),
            }
            # --- allow-list intersect (scoped grep) ------------------------
            laddered_np = numpy_ladder(chosen_blobs)
            laddered_py = stdlib_ladder(chosen_blobs)
            laddered_rs = rust_ladder(chosen_blobs)
            for n, allow in allow_lists.items():
                allow_np = np.asarray(allow, dtype=np.int64)
                allow_q = kp.to_q(allow)
                a = np.intersect1d(laddered_np, allow_np, assume_unique=True).tolist()
                b = kp.intersect_sorted(laddered_py, allow)
                c = kp.from_q(rs.intersect_sorted(laddered_rs, allow_q))
                assert a == b == c, (label, n)
                row[f"allow{n}_survivors"] = len(a)
                row[f"allow{n}_numpy_ms"] = timed_ms(
                    lambda: np.intersect1d(laddered_np, np.asarray(allow, dtype=np.int64), assume_unique=True)
                )
                row[f"allow{n}_stdlib_ms"] = timed_ms(lambda: kp.intersect_sorted(laddered_py, allow))
                row[f"allow{n}_rust_ms"] = timed_ms(lambda: rs.intersect_sorted(laddered_rs, kp.to_q(allow)))
            results.append(row)
            print(
                f"{label:<15} cand={row['candidates']:>7,} post={postings:>9,} bytes={blob_bytes:>9,}  "
                f"np={row['ladder_numpy_ms']:>7.2f}  py={row['ladder_stdlib_ms']:>8.2f}  "
                f"rs={row['ladder_rust_ms']:>6.3f}ms  mem np={row['ladder_numpy_peak_kb']:>8.0f}K "
                f"py={row['ladder_stdlib_peak_kb']:>8.0f}K",
                flush=True,
            )

            # --- site 1: per-blob decode, the largest chosen blob ------------
            if chosen_blobs:
                big = max((b for gc in chosen_blobs for b in gc), key=len)
                assert decode_postings(big).tolist() == kp.decode_postings_fused(big) == kp.from_q(rs.decode_postings(big))
                site1.append(
                    {
                        "label": label,
                        "blob_bytes": len(big),
                        "doc_count": len(kp.decode_postings_fused(big)),
                        "numpy_ms": timed_ms(lambda: decode_postings(big)),
                        "stdlib_two_pass_ms": timed_ms(lambda: kp.decode_postings(big)),
                        "stdlib_fused_ms": timed_ms(lambda: kp.decode_postings_fused(big)),
                        "rust_bytes_ms": timed_ms(lambda: rs.decode_postings(big)),
                        "rust_bytes_to_np_ms": timed_ms(lambda: np.frombuffer(rs.decode_postings(big), dtype=np.int64)),
                        "rust_bytes_tolist_ms": timed_ms(lambda: kp.from_q(rs.decode_postings(big))),
                        "rust_list_ms": timed_ms(lambda: rs.decode_postings_list(big)),
                        "numpy_peak_kb": peak_kb(lambda: decode_postings(big)),
                        "stdlib_fused_peak_kb": peak_kb(lambda: kp.decode_postings_fused(big)),
                    }
                )
    for r in site1:
        print(
            f"decode {r['label']:<15} n={r['doc_count']:>7,} np={r['numpy_ms']:.3f} py2={r['stdlib_two_pass_ms']:.2f} "
            f"py1={r['stdlib_fused_ms']:.2f} rs={r['rust_bytes_ms']:.3f} rs->np={r['rust_bytes_to_np_ms']:.3f} "
            f"rs->list={r['rust_bytes_tolist_ms']:.3f} rs_list={r['rust_list_ms']:.3f}ms"
        )
    await storage.close()
    dump("grep_sites.json", {"machine": machine(), "repeats": REPEATS, "ladder": results, "decode": site1})


asyncio.run(main())
