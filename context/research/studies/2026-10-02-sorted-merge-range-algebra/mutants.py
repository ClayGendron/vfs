"""Mutation check: break algebra.py three ways in memory; the fuzz invariants must flag each.

Run from the repo root: uv run --no-sync python context/research/studies/2026-10-02-sorted-merge-range-algebra/mutants.py
"""
import io, random, sys, contextlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[3]))
import algebra, fuzz

ORIG = {k: getattr(algebra, k) for k in ("split_to_pieces", "subtract", "meet")}

def m1_no_sibling_fix(rs):  # ship hi as it is, like the shipped _split
    pts, ops = [], []
    for lo, hi in rs:
        if hi == lo + algebra.NEXT: pts.append(lo); continue
        low = lo[:-1] if lo.endswith(algebra.NEXT) else lo
        if low == lo and (lo == "/" or not lo.endswith("/")): pts.append(lo)
        ops.append((low, hi))
    return algebra.Pieces(tuple(pts), tuple(ops))

def m2_subtract_keeps_cut_start(keep, cut):  # off by one: a cut's start is kept
    out = []
    j = 0
    for lo, hi in keep:
        while j < len(cut) and cut[j][1] <= lo: j += 1
        k = j
        while k < len(cut) and cut[k][0] < hi:
            clo, chi = cut[k]
            if clo > lo: out.append((lo, clo + algebra.NEXT))
            lo = max(lo, chi)
            if chi >= hi: break
            k += 1
        if lo < hi: out.append((lo, hi))
    return tuple(out)

def m3_meet_drops_one_direction(left, right):
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        if algebra.covers(a, b): out.append(b); j += 1
        elif algebra.tree_key(a) < algebra.tree_key(b): i += 1
        else: j += 1
    return tuple(out)

for name, target, mutant in (("m1 no sibling fix", "split_to_pieces", m1_no_sibling_fix),
                             ("m2 subtract off-by-one", "subtract", m2_subtract_keeps_cut_start),
                             ("m3 meet one-directional", "meet", m3_meet_drops_one_direction)):
    for k in fuzz.INVARIANTS: fuzz.INVARIANTS[k] = 0
    setattr(algebra, target, mutant)
    rng = random.Random(1)
    ex = {}
    for _ in range(1500):
        try: fuzz.check_case(rng, ex)
        except Exception as e: ex.setdefault("exception", repr(e)[:150]); fuzz.INVARIANTS["I1 admits: oracle == shipped == new (every probe, every owner)"] += 1
    setattr(algebra, target, ORIG[target])
    hit = {k.split(" ")[0]: v for k, v in fuzz.INVARIANTS.items() if v}
    print(f"{name}: flagged by {hit}")
