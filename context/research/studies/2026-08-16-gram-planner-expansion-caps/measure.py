"""Refusal-set delta measurement for the gram-planner expansion caps.

Run:  uv run python context/research/studies/2026-08-16-gram-planner-expansion-caps/measure.py

Loads the mined field corpus (field_corpus.json beside this script; regenerate
with mine_field_patterns.py) plus the vfs query-ladder and differential
battery pattern sets, validates the prototype's off-configuration against the
live planner, then measures per-upgrade rescues, cap sweeps, composition
risk, narrowing, and soundness spot checks.

ERE→Python normalization (disclosed): POSIX classes ([[:space:]] etc.) map to
Python equivalents; \\< \\> map to \\b. vfs users write Python re, so the
normalized spelling is what the planner would actually receive.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from proto_planner import Caps, plan
from vfs.models.code_grams import (
    GramAnd,
    GramAny,
    GramOr,
    build_code_gram_query,
    unique_code_grams,
)

HERE = Path(__file__).parent

POSIX = {
    "[:space:]": r"\s",
    "[:blank:]": " \\t",
    "[:digit:]": "0-9",
    "[:alpha:]": "a-zA-Z",
    "[:alnum:]": "a-zA-Z0-9",
    "[:upper:]": "A-Z",
    "[:lower:]": "a-z",
    "[:xdigit:]": "0-9A-Fa-f",
}

LADDER = [
    "xyzzy_unlikely_sentinel_42", "rare_sentinel_needle", "medium_ident_alpha",
    "def __init__", r"static\s+int\s+\w+_probe", ".*alloc_page.*",
    "(?i)Mutex_Lock", "return", "ab", "medium_ident_a|ab",
]
BATTERY = [
    "needle", "NEEDLE", "Needle", "a.b", "cat", "alpha|beta", "alpha.*omega",
    "bn_ending_at", "bn_across_cut", "bn_after_cut", "one.still",
    "still first", "needle after ff", "needle nel", "needle usep",
    "needle crlf",
]

# (pattern, matching line) soundness spot checks for the upgraded planner:
# the folded line's grams must satisfy at least one variant of the plan.
SOUNDNESS = [
    ("[fF]oo", "seen Foo here"),
    ("^(import|from)", "from vfs import base"),
    ("foo_(bar|baz)", "call foo_baz(x)"),
    ("MAP_(UNINITIALIZED|TYPE|SHARED_VALIDATE)", "flags & MAP_TYPE"),
    ("ext[234]|jfs|xfs", "mount -t ext3 /dev/sda1"),
    (r"^#define HWCAP[0-9]*_[A-Z0-9_]+", "#define HWCAP2_SVE2 (1 << 1)"),
    (r"Sherlock$", "you know my methods, Sherlock"),
    (r"foo\bbar", "no such line exists"),  # unsatisfiable: vacuously sound
    ("(?i)mutex_lock", "called Mutex_Lock(&lock)"),
    ("^(#|Using)", "# a comment line"),
]


def load_corpus() -> list[dict]:
    corpus = json.loads((HERE / "field_corpus.json").read_text())
    for pattern in LADDER:
        corpus.append({"pattern": pattern, "source": "vfs-ladder"})
    for pattern in BATTERY:
        corpus.append({"pattern": pattern, "source": "vfs-battery"})
    seen: set[str] = set()
    out: list[dict] = []
    for item in corpus:
        p = item["pattern"]
        for posix, py in POSIX.items():
            p = p.replace(posix, py)
        p = p.replace(r"\>", r"\b").replace(r"\<", r"\b")
        if p not in seen:
            seen.add(p)
            out.append({"pattern": p, "source": item["source"]})
    return out


def shape(query) -> object:
    """Canonical comparable form of a GramQuery."""
    if isinstance(query, GramAny):
        return "ANY"
    if isinstance(query, GramAnd):
        return frozenset(query.grams)
    if isinstance(query, GramOr):
        return frozenset(shape(b) for b in query.branches)
    raise AssertionError(query)


def indexable(query) -> bool:
    return not isinstance(query, GramAny)


def parses(pattern: str) -> bool:
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def main() -> None:
    corpus = load_corpus()
    print(f"corpus: {len(corpus)} unique patterns")
    print(Counter(i["source"].split(":")[0] for i in corpus))

    # -- validation: off-configuration == live planner -------------------
    off = Caps()
    mismatches = []
    for item in corpus:
        p = item["pattern"]
        live = build_code_gram_query(p)
        proto, _w = plan(p, off)
        if shape(live) != shape(proto):
            mismatches.append(p)
    print(f"\nvalidation (proto-off vs live): {len(mismatches)} mismatches")
    for p in mismatches[:20]:
        print("  MISMATCH:", repr(p))
    if mismatches:
        return

    # -- baseline buckets ------------------------------------------------
    parse_fail = [i for i in corpus if not parses(i["pattern"])]
    ok = [i for i in corpus if parses(i["pattern"])]
    baseline_ix = [i for i in ok if indexable(build_code_gram_query(i["pattern"]))]
    refused = [i for i in ok if not indexable(build_code_gram_query(i["pattern"]))]
    print(f"\nparse-fail (not Python re; excluded): {len(parse_fail)}")
    print(f"parseable: {len(ok)}  indexable today: {len(baseline_ix)}  "
          f"refused today: {len(refused)} ({100*len(refused)/len(ok):.0f}%)")

    # -- rescue attribution (generous caps) ------------------------------
    generous = dict(member_cap=1024, width_cap=4096)
    configs = {
        "classes": Caps(classes=True, **generous),
        "branches": Caps(branches=True, **generous),
        "anchors": Caps(anchors=True, **generous),
        "classes+branches": Caps(classes=True, branches=True, **generous),
        "classes+anchors": Caps(classes=True, anchors=True, **generous),
        "branches+anchors": Caps(branches=True, anchors=True, **generous),
        "all": Caps(classes=True, branches=True, anchors=True, **generous),
    }
    rescued_by: dict[str, list[str]] = {k: [] for k in configs}
    for item in refused:
        for name, caps in configs.items():
            q, _w = plan(item["pattern"], caps)
            if indexable(q):
                rescued_by[name].append(item["pattern"])
    print("\nrescues out of", len(refused), "refused (generous caps):")
    for name, pats in rescued_by.items():
        print(f"  {name:18s} {len(pats)}")
    all_rescued = rescued_by["all"]
    never = [i["pattern"] for i in refused if i["pattern"] not in all_rescued]
    print(f"  unrescuable by the three upgrades: {len(never)}")
    print("  unrescuable sample:", [repr(p) for p in never[:12]])

    # -- width demand of rescued patterns --------------------------------
    unbounded = Caps(classes=True, branches=True, anchors=True,
                     member_cap=10**6, width_cap=10**6)
    widths = []
    for p in all_rescued:
        _q, w = plan(p, unbounded)
        widths.append((w, p))
    widths.sort(reverse=True)
    print("\nfinal-width demand of rescued patterns (uncapped):")
    dist = Counter(w for w, _ in widths)
    for bound in (1, 2, 4, 8, 16, 32, 64, 128, 256, 1024, 10**6):
        n = sum(c for w, c in dist.items() if w <= bound)
        print(f"  width <= {bound:>7}: {n}/{len(widths)} rescued patterns")
    print("  widest 10:", [(w, repr(p)[:60]) for w, p in widths[:10]])

    # -- shared-ceiling sweep (shape A: one constant, member cap = W) ----
    print("\nshape A — one shared width ceiling W (member cap = W):")
    for w_cap in (4, 8, 16, 32, 64, 128, 256, 1024):
        caps = Caps(classes=True, branches=True, anchors=True,
                    member_cap=w_cap, width_cap=w_cap)
        n = sum(1 for i in refused if indexable(plan(i["pattern"], caps)[0]))
        print(f"  W={w_cap:>4}: rescued {n}/{len(refused)}")

    # -- W sweep at fixed small member cap (the both-caps shape) ---------
    print("\nboth-caps shape — W sweep at fixed M=8:")
    for w_cap in (4, 8, 16, 32, 64, 128, 256, 1024):
        caps = Caps(classes=True, branches=True, anchors=True,
                    member_cap=8, width_cap=w_cap)
        n = sum(1 for i in refused if indexable(plan(i["pattern"], caps)[0]))
        print(f"  W={w_cap:>4}: rescued {n}/{len(refused)}")

    # -- member-cap sweep at fixed W=64 ----------------------------------
    print("\nmember cap M sweep at fixed W=64:")
    for m_cap in (2, 4, 8, 16, 32, 64, 128):
        caps = Caps(classes=True, branches=True, anchors=True,
                    member_cap=m_cap, width_cap=64)
        n = sum(1 for i in refused if indexable(plan(i["pattern"], caps)[0]))
        print(f"  M={m_cap:>3}: rescued {n}/{len(refused)}")

    # -- composition risk: per-upgrade caps with NO shared ceiling -------
    for m_cap in (8, 16):
        caps_b = Caps(classes=True, branches=True, anchors=True,
                      member_cap=m_cap, width_cap=10**6)
        all_widths = sorted(
            ((plan(i["pattern"], caps_b)[1], i["pattern"]) for i in ok),
            reverse=True)
        print(f"\ncomposition risk — M={m_cap}, no width ceiling, whole corpus:")
        print("  widest 5:", [(w, repr(p)[:60]) for w, p in all_widths[:5]])

    # -- rescued list, and the target population --------------------------
    print("\nrescued patterns (all upgrades, generous caps):")
    for p in all_rescued:
        print("   ", repr(p))
    structured = [i for i in refused
                  if any(c in i["pattern"] for c in "|[^$(") or "\\b" in i["pattern"]]
    print(f"\nrefused patterns WITH class/alt/anchor/group structure "
          f"(the upgrades' target population): {len(structured)}")
    print(f"  rescued: {sum(1 for i in structured if i['pattern'] in all_rescued)}"
          f"/{len(structured)}")

    # -- who dies at each W with member cap tied to W (the pathology) ----
    for w_cap in (64, 128):
        caps = Caps(classes=True, branches=True, anchors=True,
                    member_cap=w_cap, width_cap=w_cap)
        lost = [p for p in all_rescued if not indexable(plan(p, caps)[0])]
        print(f"\nrescued-at-generous but lost at W={w_cap} (member_cap=W): {lost}")

    # -- narrowing sweep: how many plans strengthen as M rises (W=64) ----
    print("\nnarrowing sweep (already-indexable plans that strengthen, W=64):")
    for m_cap in (0, 2, 4, 8, 16, 32, 100):
        caps = Caps(classes=m_cap > 0, branches=True, anchors=True,
                    member_cap=max(m_cap, 1), width_cap=64)
        n = sum(1 for i in baseline_ix
                if shape(build_code_gram_query(i["pattern"]))
                != shape(plan(i["pattern"], caps)[0]))
        print(f"  M={m_cap:>3}: {n}/{len(baseline_ix)} strengthened")

    # -- soundness spot checks -------------------------------------------
    print("\nsoundness spot checks (upgraded plan vs known matching line):")
    caps_a = Caps(classes=True, branches=True, anchors=True,
                  member_cap=8, width_cap=64)
    failures = 0
    for pattern, line in SOUNDNESS:
        q, _w = plan(pattern, caps_a)
        if not re.search(pattern, line):
            print(f"  n/a   {pattern!r} (line does not match; vacuous)")
            continue
        line_grams = unique_code_grams(line, folded=True)
        if isinstance(q, GramAny):
            verdict = "ANY (no constraint — trivially sound)"
        elif isinstance(q, GramAnd):
            okq = q.grams <= line_grams
            verdict = "ok" if okq else "FALSE NEGATIVE"
            failures += not okq
        else:
            okq = any(b.required_grams() <= line_grams for b in q.branches)
            verdict = "ok" if okq else "FALSE NEGATIVE"
            failures += not okq
        print(f"  {verdict:6s} {pattern!r}")
    print(f"soundness failures: {failures}")


if __name__ == "__main__":
    main()
