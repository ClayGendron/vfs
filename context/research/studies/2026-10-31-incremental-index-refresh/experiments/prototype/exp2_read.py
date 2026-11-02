"""Experiment 2: read amplification vs live segment count K.

Base segment 0 over N docs, then 48 delta segments of 500 docs each (half
re-posts of base ids with changed content -> ghost postings in the base;
half new ids). Queries are run with the live set = base + first K deltas.

Experiment 3 reuses this store: see exp3_merge.py.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    RARE_POOL,
    IDENTS,
    PROSE_VOCAB,
    build_segment,
    candidates_kernel_groups,
    candidates_merge_python,
    choose_grams,
    fetch_blobs,
    fetch_meta,
    open_store,
    plan_groups,
    verify,
)

HERE = os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
DELTAS = 48
DELTA_DOCS = 500
DB = os.path.join(HERE, "exp2.db")
STATE = os.path.join(HERE, "exp2_state.json")


def build_store() -> dict:
    for f in (DB, DB + "-wal", DB + "-shm"):
        if os.path.exists(f):
            os.remove(f)
    conn = open_store(DB)
    t = build_segment(conn, 0, [(i, 0) for i in range(1, N + 1)])
    print("base", t.index_s, t.rows, t.bytes, flush=True)
    rng = random.Random(11)
    pool = list(range(1, N + 1))
    rng.shuffle(pool)
    next_new = N + 1
    version: dict[int, int] = {}
    seg_docs: dict[int, list[int]] = {}
    t_delta = []
    for seg in range(1, DELTAS + 1):
        reposts = pool[(seg - 1) * (DELTA_DOCS // 2) : seg * (DELTA_DOCS // 2)]
        new = list(range(next_new, next_new + DELTA_DOCS - DELTA_DOCS // 2))
        next_new += len(new)
        docs = [(d, 1) for d in reposts] + [(d, 0) for d in new]
        for d in reposts:
            version[d] = 1
        seg_docs[seg] = sorted(d for d, _ in docs)
        bt = build_segment(conn, seg, docs)
        t_delta.append(bt.index_s)
    print("delta index_s mean", statistics.mean(t_delta), flush=True)
    conn.close()
    state = {"N": N, "version": version, "seg_docs": seg_docs, "next_new": next_new}
    with open(STATE, "w") as fh:
        json.dump(state, fh)
    return state


def queries() -> list[tuple[str, str, bool]]:
    rng = random.Random(3)
    qs: list[tuple[str, str, bool]] = []
    for i in range(6):
        qs.append((f"rare-{i}", RARE_POOL[rng.randrange(len(RARE_POOL))], True))
    for i in range(4):
        qs.append((f"ident-{i}", IDENTS[rng.randrange(50, 400)], True))
    for i in range(3):
        qs.append((f"word-{i}", PROSE_VOCAB[rng.randrange(20, 200)], True))
    qs.append(("common-kw", "return self", True))
    qs.append(("common-kw2", "is None: raise", True))
    qs.append(("phrase", f"{PROSE_VOCAB[3]} {PROSE_VOCAB[1]}", True))
    qs.append(("regex-alt", r"raise (ValueError|TypeError)\(", False))
    qs.append(("regex-cls", r"fn_[0-9a-f]{3}", False))
    qs.append(("regex-alt2", f"({IDENTS[7]}|{IDENTS[9]})\\(", False))
    qs.append(("phrase2", "def " + IDENTS[2], True))
    return qs


def run_queries(state: dict, ks: tuple[int, ...], covered: list[int] | None = None) -> list[dict]:
    """Queries at each K (live set = base + segments 1..K). `covered` names the original deltas the
    live set holds (defaults to 1..K) so the corpus state used for verification matches."""
    conn = open_store(DB)
    seg_docs = {int(k): v for k, v in state["seg_docs"].items()}
    n_base = state["N"]
    out = []
    for K in ks:
        segments = list(range(0, K + 1))
        version: dict[int, int] = {}
        for s in covered if covered is not None else range(1, K + 1):
            for d in seg_docs[s]:
                version[d] = 1 if d <= n_base else 0
        for name, pattern, fixed in queries():
            groups = plan_groups(pattern, fixed)
            assert groups is not None, pattern
            grams = sorted({g for grp in groups for g in grp})
            t0 = time.perf_counter()
            meta = fetch_meta(conn, segments, grams)
            t_meta = time.perf_counter() - t0
            total = {}
            for (s, g), (dc, bs) in meta.items():
                total[g] = total.get(g, 0) + dc
            chosen = choose_grams(groups, total)
            wanted = sorted({g for grp in chosen if grp for g in grp})
            fr = fetch_blobs(conn, segments, wanted)
            ids_a, total_a, merge_s, kernel_a_s = candidates_merge_python(chosen, segments, fr.blobs)
            ids_b, total_b, kernel_b_s = candidates_kernel_groups(chosen, segments, fr.blobs)
            if total_a <= 25000:  # under the cap both lists are complete; per-segment AND is the tighter superset
                assert set(ids_b) <= set(ids_a), (name, K)
            phantoms = total_a - total_b  # cross-version candidates only the per-gram union admits
            true, ghosts, fp = verify(pattern, fixed, ids_b, version)
            verified = true + ghosts + fp  # a sample when the candidate list is long
            rec = {
                "K": K,
                "query": name,
                "pattern": pattern,
                "groups": len(groups),
                "grams_wanted": len(wanted),
                "meta_rows": len(meta),
                "meta_s": t_meta,
                "rows": fr.rows,
                "bytes": fr.bytes,
                "fetch_s": fr.fetch_s,
                "merge_py_s": merge_s,
                "kernel_merged_s": kernel_a_s,
                "kernel_groups_s": kernel_b_s,
                "candidates": total_b,
                "candidates_merged_union": total_a,
                "phantoms": phantoms,
                "verified": verified,
                "true": true,
                "ghosts": ghosts,
                "fp": fp,
            }
            out.append(rec)
        print("K", K, "done", flush=True)
    conn.close()
    return out


if __name__ == "__main__":
    if os.path.exists(STATE) and "--reuse" in sys.argv:
        with open(STATE) as fh:
            state = json.load(fh)
    else:
        state = build_store()
    results = run_queries(state, (0, 1, 4, 12, 48))
    with open(os.path.join(HERE, "exp2_results.json"), "w") as fh:
        json.dump(results, fh, indent=1)
