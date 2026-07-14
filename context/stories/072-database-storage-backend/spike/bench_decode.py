"""Posting-decode microbenchmark: the number that decides ENCODING_ROARING.

Synthetic sorted doc-id sets at densities n of N=1,000,000 docs; times
pure-Python gamma decode (the v1 spec encoding), pure-Python varint decode,
numpy-vectorized varint decode, and (if installed) pyroaring deserialize +
intersect. Also times numpy intersect1d on decoded arrays.

Run: uv run --with pyroaring python .../bench_decode.py   (pyroaring optional)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import (  # noqa: E402
    DATA_DIR,
    decode_postings_gamma,
    encode_postings_gamma,
    gaps_from_segmented_docs,
    varint_decode_np,
    varint_decode_py,
    varint_encode_segments,
)

try:
    from pyroaring import BitMap
    HAVE_ROARING = True
except ImportError:
    HAVE_ROARING = False

N_CORPUS = 1_000_000
DENSITIES = [1_000, 10_000, 100_000, 1_000_000]


def timeit(fn, reps: int) -> float:
    best = float("inf")
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def main() -> None:
    rng = np.random.default_rng(42)
    out = {"n_corpus": N_CORPUS, "have_roaring": HAVE_ROARING, "densities": {}}
    for n in DENSITIES:
        docs = np.sort(rng.choice(N_CORPUS, size=n, replace=False)).astype(np.int64)
        gaps = gaps_from_segmented_docs(docs, np.array([0]))
        vblob, _ = varint_encode_segments(gaps, np.array([0]))
        gblob = encode_postings_gamma(docs.tolist())
        reps = 5 if n >= 100_000 else 20

        r = {
            "varint_bytes": len(vblob),
            "gamma_bytes": len(gblob),
            "gamma_py_s": timeit(lambda: decode_postings_gamma(gblob, n), reps),
            "varint_py_s": timeit(lambda: varint_decode_py(vblob), reps),
            "varint_np_s": timeit(lambda: varint_decode_np(vblob), reps),
        }
        r["gamma_py_vals_per_s"] = int(n / r["gamma_py_s"])
        r["varint_py_vals_per_s"] = int(n / r["varint_py_s"])
        r["varint_np_vals_per_s"] = int(n / r["varint_np_s"])

        docs2 = np.sort(rng.choice(N_CORPUS, size=n, replace=False)).astype(np.uint32)
        d1 = docs.astype(np.uint32)
        r["np_intersect_s"] = timeit(
            lambda: np.intersect1d(d1, docs2, assume_unique=True), reps
        )
        if HAVE_ROARING:
            bm_ser = BitMap(d1.tolist()).serialize()
            bm2 = BitMap(docs2.tolist())
            r["roaring_bytes"] = len(bm_ser)
            r["roaring_deser_and_s"] = timeit(
                lambda: BitMap.deserialize(bm_ser) & bm2, reps
            )
        out["densities"][str(n)] = {
            k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()
        }
        print(f"n={n}: done", flush=True)
    (DATA_DIR / "decode_bench.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1), flush=True)


if __name__ == "__main__":
    main()
