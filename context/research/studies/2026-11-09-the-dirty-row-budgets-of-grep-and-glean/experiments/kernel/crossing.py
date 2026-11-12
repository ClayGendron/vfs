"""The boundary crossing: the kernel called from Python on the 2,000 bodies.

Status quo (what _overlay_blocks does per body) against the batched kernel
call and a per-document kernel call, all on the same bodies as Python strs.
Reports median seconds per pass over 7 passes, and µs per body.
"""
import json, os, statistics, sys, time
from collections import Counter

import overlay_counts
from vfs.models.lexical import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
bodies_dir = os.path.join(HERE, "bodies")
names = sorted(n for n in os.listdir(bodies_dir) if n.endswith(".txt"))
bodies = [open(os.path.join(bodies_dir, n), encoding="utf-8").read() for n in names]
docs = [(i + 1, b) for i, b in enumerate(bodies)]
queries = json.load(open(os.path.join(HERE, "queries.json")))
n = len(bodies)
nbytes = sum(len(b.encode()) for b in bodies)
PASSES = 7


def timed(fn):
    samples = []
    fn()
    for _ in range(PASSES):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples)


def status_quo(terms):
    total = 0
    for _, body in docs:
        toks = tokenize(body)
        total += len(toks)
        counts = Counter(toks)
        for t in terms:
            total += counts.get(t, 0)
    return total


def tokenize_only():
    return sum(len(tokenize(body)) for _, body in docs)


def batched(terms):
    per_term, total_dl = overlay_counts.overlay_postings(docs, terms)
    return total_dl


def per_doc(terms):
    total = 0
    for _, body in docs:
        dl, tfs = overlay_counts.count_terms(body, terms)
        total += dl
    return total


print(f"bodies {n} bytes {nbytes} passes {PASSES}")
print("| call | query | terms | s per pass | us per body | MB/s |")
print("|---|---|---|---|---|---|")
s = timed(tokenize_only)
print(f"| vfs tokenize (pyo3, Vec<String> -> list[str]) | (no terms) | 0 | {s:.4f} | {s*1e6/n:.1f} | {nbytes/s/1e6:.0f} |")
for name, terms in queries.items():
    s0 = timed(lambda: status_quo(terms))
    print(f"| status quo: tokenize + Counter + get | {name} | {len(terms)} | {s0:.4f} | {s0*1e6/n:.1f} | {nbytes/s0/1e6:.0f} |")
    s1 = timed(lambda: batched(terms))
    print(f"| kernel overlay_postings, one call per batch | {name} | {len(terms)} | {s1:.4f} | {s1*1e6/n:.1f} | {nbytes/s1/1e6:.0f} |")
    s2 = timed(lambda: per_doc(terms))
    print(f"| kernel count_terms, one call per document | {name} | {len(terms)} | {s2:.4f} | {s2*1e6/n:.1f} | {nbytes/s2/1e6:.0f} |")
# Parity of the kernel against the status quo on every body and query.
for name, terms in queries.items():
    per_term, total_dl = overlay_counts.overlay_postings(docs, terms)
    expect = [[] for _ in terms]
    total = 0
    for doc_id, body in docs:
        toks = tokenize(body)
        total += len(toks)
        c = Counter(toks)
        for p, t in enumerate(terms):
            if c.get(t, 0):
                expect[p].append((doc_id, c[t], len(toks)))
    assert total == total_dl, (total, total_dl)
    assert [list(map(tuple, pt)) for pt in per_term] == expect, name
print("parity: kernel postings equal tokenize + Counter on every body and query")
