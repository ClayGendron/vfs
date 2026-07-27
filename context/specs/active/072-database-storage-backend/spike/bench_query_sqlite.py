"""Query benchmark over a built gram index tier.

Uses the LIVE vfs planner (build_code_gram_query, folded) to get required
grams per pattern, then measures the full ladder per k (number of rarest
grams intersected): SQL blob fetch -> numpy varint decode -> intersect ->
content fetch for candidates -> authoritative Python re verify.

Also times pure-Python gamma decode on the same fetched blobs (re-encoded
on the fly — encode cost not charged), and the scan tier for calibration.

Run: uv run python .../bench_query_sqlite.py <N> [--scan]
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import DATA_DIR, decode_postings_gamma, encode_postings_gamma, varint_decode_np  # noqa: E402

from vfs.models.code_grams import GramAnd, GramOr, build_code_gram_query  # noqa: E402

# (label, class, pattern, regex flags)
PATTERNS = [
    ("zero_hit", "rare", "xyzzy_unlikely_sentinel_42", 0),
    ("rare_ident", "rare", "EXPORT_SYMBOL_NS_GPL", 0),
    ("medium_ident", "medium", "kmalloc", 0),
    ("hot_ident", "hot", "return", 0),
    ("hot_phrase", "hot", "def __init__", 0),
    ("punct_arrow", "punct", "->next", 0),
    ("punct_neq_null", "punct", "!= NULL", 0),
    ("regex_probe", "regex", r"static\s+int\s+\w+_probe", 0),
    ("regex_wrapped", "regex", r".*alloc_page.*", 0),
    ("regex_alt", "regex", r"(kmalloc|vmalloc)\(", 0),
    ("case_insens", "fold", r"(?i)Mutex_Lock", 0),
    ("sub3_bytes", "unindexable", "ab", 0),
    ("class_prefix", "unindexable", r"[fF]oo_bar", 0),
    ("alt_short_branch", "unindexable", r"kmalloc|ab", 0),
]

K_SWEEP = [1, 2, 3, 4, 8, 0]  # 0 = all required grams


def required_gram_sets(query) -> list[set[int]]:
    """OR of AND-sets; a plain AND is a single branch."""
    if isinstance(query, GramAnd):
        return [set(query.grams)]
    if isinstance(query, GramOr):
        out = []
        for br in query.branches:
            out.extend(required_gram_sets(br))
        return out
    return []


def run_branch(index: sqlite3.Connection, corpus: sqlite3.Connection,
               grams: set[int], k: int, pattern: str, flags: int,
               n_real: int) -> dict:
    t = {}
    t0 = time.monotonic()
    rows = index.execute(
        f"SELECT gram, doc_count, byte_size FROM posting_list "
        f"WHERE gram IN ({','.join('?' * len(grams))})",
        list(grams),
    ).fetchall()
    t["meta_ms"] = (time.monotonic() - t0) * 1000
    if len(rows) < len(grams):
        return {**t, "result": "empty_short_circuit", "candidates": 0, "verified": 0}
    rows.sort(key=lambda r: r[1])
    chosen = rows if k == 0 else rows[:k]
    t0 = time.monotonic()
    blobs = [
        index.execute("SELECT postings, doc_count FROM posting_list WHERE gram=?", (g,)).fetchone()
        for g, _, _ in chosen
    ]
    t["fetch_ms"] = (time.monotonic() - t0) * 1000
    t["posting_bytes"] = sum(len(b[0]) for b in blobs)
    t0 = time.monotonic()
    cand = None
    for blob, _count in blobs:
        ids = varint_decode_np(blob)
        cand = ids if cand is None else np.intersect1d(cand, ids, assume_unique=True)
        if len(cand) == 0:
            break
    t["decode_intersect_ms"] = (time.monotonic() - t0) * 1000
    n_cand = int(len(cand)) if cand is not None else 0
    t["candidates"] = n_cand

    # Pure-python gamma decode timing on the same blobs (re-encoded on the fly).
    gtime = 0.0
    for blob, count in blobs:
        ids = varint_decode_np(blob)
        gblob = encode_postings_gamma(ids.tolist())
        g0 = time.monotonic()
        decode_postings_gamma(gblob, count)
        gtime += time.monotonic() - g0
    t["gamma_decode_ms"] = gtime * 1000

    if n_cand == 0:
        return {**t, "result": "no_candidates", "verified": 0}
    t0 = time.monotonic()
    rx = re.compile(pattern, flags)
    verified = 0
    fetch_s = 0.0
    cap = 200_000
    # Doubled tiers wrap ids back onto the real corpus (content is identical).
    for chunk_start in range(0, min(n_cand, cap), 500):
        chunk = cand[chunk_start : chunk_start + 500]
        f0 = time.monotonic()
        rows2 = corpus.execute(
            f"SELECT content FROM docs WHERE id IN ({','.join('?' * len(chunk))})",
            [int(c) % n_real for c in chunk],
        ).fetchall()
        fetch_s += time.monotonic() - f0
        for (content,) in rows2:
            if rx.search(content):
                verified += 1
    t["content_fetch_ms"] = fetch_s * 1000
    t["verify_ms"] = (time.monotonic() - t0) * 1000 - t["content_fetch_ms"]
    t["verified"] = verified
    t["truncated"] = n_cand > cap
    t["result"] = "ok"
    return t


def scan_tier(corpus: sqlite3.Connection, n_docs: int, pattern: str, flags: int) -> dict:
    rx = re.compile(pattern, flags)
    t0 = time.monotonic()
    hits = 0
    for start in range(0, n_docs, 5000):
        rows = corpus.execute(
            "SELECT content FROM docs WHERE id >= ? AND id < ?", (start, start + 5000)
        ).fetchall()
        for (content,) in rows:
            if rx.search(content):
                hits += 1
    return {"scan_ms": (time.monotonic() - t0) * 1000, "hits": hits}


def main() -> None:
    n_docs = int(sys.argv[1])
    do_scan = "--scan" in sys.argv
    index = sqlite3.connect(DATA_DIR / f"gram_index_{n_docs}.db")
    corpus = sqlite3.connect(DATA_DIR / "corpus.db")
    out = {"tier": n_docs, "patterns": {}}
    n_real = corpus.execute("SELECT count(*) FROM docs").fetchone()[0]
    for label, cls, pattern, flags in PATTERNS:
        entry = {"class": cls, "pattern": pattern}
        q = build_code_gram_query(pattern, folded=True)
        if q.is_any():
            entry["plan"] = "GramAny -> REFUSED (allow_scan opt-out)"
            if do_scan and n_docs <= 100_000:
                entry["scan"] = scan_tier(corpus, n_docs, pattern, flags)
            out["patterns"][label] = entry
            continue
        branches = required_gram_sets(q)
        entry["plan"] = f"{len(branches)} branch(es), grams/branch={[len(b) for b in branches]}"
        entry["k"] = {}
        for k in K_SWEEP:
            # Warm run then timed run; union across OR branches.
            for _warm in range(2):
                agg = {"candidates": 0, "verified": 0, "ms": {}}
                total = {}
                for br in branches:
                    r = run_branch(index, corpus, br, k, pattern, flags, n_real)
                    for key, v in r.items():
                        if isinstance(v, (int, float)) and key != "candidates":
                            total[key] = total.get(key, 0) + v
                    agg["candidates"] += r.get("candidates", 0)
                    agg["verified"] += r.get("verified", 0)
                agg["ms"] = {k2: round(v, 2) for k2, v in total.items() if k2.endswith("_ms")}
                agg["posting_bytes"] = total.get("posting_bytes", 0)
            entry["k"][str(k) if k else "all"] = agg
        if do_scan and n_docs <= 100_000:
            entry["scan"] = scan_tier(corpus, n_docs, pattern, flags)
        out["patterns"][label] = entry
        print(f"{label}: done", flush=True)
    result_path = DATA_DIR / f"query_bench_{n_docs}.json"
    result_path.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1), flush=True)


if __name__ == "__main__":
    main()
