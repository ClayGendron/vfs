"""Synthetic corpus for the fused-statement probes: 100 entries x 4 chunks, small dims.

Entries 30..39 mention the rare word "lantern" (the lexical target); the vector
query is a nudged copy of entry 33's second chunk (the vector target). The
glob scope is "src/mod3/**" -> entry ids 3, 13, ..., 93, so the fused top-n
should be dominated by entry 33 (in scope, both legs) and never contain an
out-of-scope entry (e.g. 31, 35: lexical hits outside the scope).
"""

from __future__ import annotations

import random

DIMS = 8
VOCAB = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
         "omicron pi rho sigma tau upsilon phi chi psi omega socket buffer parser token").split()


def build(dims: int = DIMS, entries: int = 100, per_entry: int = 4, seed: int = 7):
    rng = random.Random(seed)
    ents = [(i, f"src/mod{i % 10}/file{i}.py") for i in range(1, entries + 1)]
    chunks = []
    cid = 0
    for eid, _ in ents:
        for ci in range(per_entry):
            cid += 1
            words = [rng.choice(VOCAB) for _ in range(12)]
            if 30 <= eid <= 39:
                words += ["lantern"] * (1 + (eid + ci) % 3)
            vec = [rng.uniform(-1, 1) for _ in range(dims)]
            chunks.append((cid, eid, ci, " ".join(words), vec))
    target = next(c for c in chunks if c[1] == 33 and c[2] == 1)
    query_vec = [x + 0.01 for x in target[4]]
    scope_ids = [i for i, p in ents if p.startswith("src/mod3/")]
    return ents, chunks, query_vec, scope_ids


def as_json(vec) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
