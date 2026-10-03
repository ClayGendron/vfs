"""Fuzz the sibling and low-byte space: random prefixes over hostile alphabets.

Each case builds a small world whose prefixes are drawn from segments that
sort around ``/``: ``0`` (just above), ``-`` ``.`` ``!`` and space (below),
``~`` and non-ASCII (far above), plus derived siblings ``p + "0"``,
``p + "-x"``, ``p + "/x"``, nested holes, a hole equal to a grant, a hole
on the root, grants from several members, and groups with no rows. Every
case checks the invariants listed in ``INVARIANTS`` and counts any break.

Run from the repo root:

    uv run --no-sync python context/research/studies/2026-10-02-sorted-merge-range-algebra/fuzz.py --cases 100000
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from itertools import pairwise
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from algebra import (  # noqa: E402
    FULL,
    RangeSet,
    Row,
    contains,
    cover,
    cover_all,
    everyone_region,
    intersect,
    meet,
    minimise,
    normalise,
    pieces_hold,
    resolve_rights,
    split_to_pieces,
    subtract,
    union,
    union_many,
)
from tests.support.oracles.grants import GrantWorld, everyone_rank, set_rank  # noqa: E402
from vfs.storage.grants import LEVEL_RANK, GrantRow, resolve  # noqa: E402
from vfs.storage.grants import covers as s_covers  # noqa: E402
from vfs.storage.grants import meet as s_meet  # noqa: E402
from vfs.storage.grants import minimise as s_minimise  # noqa: E402

SEGMENTS = ("a", "b", "0", "00", "a0", "a-", "a.", "b!", "a a", "~", "é", "日本", "-", ".", "!", "a-b", "z0", "A", "~a")
USERS = ("u1", "u2", "u3")
GROUPS = ("group:g1", "group:g2", "group:g3")
LEVELS = ("none", "read", "read_write")

INVARIANTS = {
    "I1 admits: oracle == shipped == new (every probe, every owner)": 0,
    "I2 new pieces well-formed: sorted, disjoint, no NUL, no bound ending below space, every bound in {p, p/, p0, /, 0}": 0,
    "I3 new pieces == new range set pointwise; owner pieces == owner range set pointwise": 0,
    "I4 shipped pieces == new pieces pointwise (arms and owners)": 0,
    "I5 new pieces identical to shipped pieces whenever the shipped pieces are well-formed": 0,
    "I6 whole is True exactly when the arm range set is the whole mount": 0,
    "I7 range-set laws: union/intersect/subtract pointwise; (A-B) and B disjoint; (A-B) | (A&B) == A; normalise idempotent; union == union_many == normalise(A+B)": 0,
    "I8 cover_all(meet(a, b)) == intersect(cover_all(a), cover_all(b)); meet == shipped meet as a set; minimise == shipped minimise as a set": 0,
    "I9 everyone_region == oracle everyone_rank pointwise": 0,
    "I10 covers_subtree(p) implies every probe under p is covered; shipped covers_subtree implies new": 0,
    "I11 the new resolver never emits a span bound outside the input prefixes' closure {p, p+NUL, p/, p0, /, 0}": 0,
    "I12 an empty subject set resolves to the whole mount in both resolvers (shipped vs new only; the oracle cannot answer)": 0,
}
COUNTS = {"shipped NUL bounds (the sibling bug)": 0, "cases": 0, "probes": 0}


def rand_prefix(rng: random.Random) -> str:
    return "/" + "/".join(rng.choice(SEGMENTS) for _ in range(rng.randint(1, 3)))


def rand_prefixes(rng: random.Random) -> list[str]:
    base = [rand_prefix(rng) for _ in range(rng.randint(1, 4))]
    out = set(base)
    for p in base:
        for shape in rng.sample(("0", "-x", "/x", "00", "/x/y", ".", "!", " x", "~"), rng.randint(0, 3)):
            out.add(p + shape)
    if rng.random() < 0.3:
        out.add("/")
    return sorted(out)


def probes_for(prefixes: list[str], rng: random.Random) -> list[str]:
    out = {"/", "/zzz", "/0", "/-"}
    for p in prefixes:
        out.update((p, p + "0", p + "/x", p + "-x", p + "00", p + "/x/y", p + " ", p + "!"))
        parent = p.rsplit("/", 1)[0] or "/"
        out.add(parent)
    lawful = [q for q in out if q == "/" or (not q.endswith("/") and not q.endswith(" ") and "//" not in q)]
    return rng.sample(lawful, min(len(lawful), 14))


def rand_world(rng: random.Random) -> tuple[GrantWorld, list[str]]:
    prefixes = rand_prefixes(rng)
    rows: list[GrantRow] = []
    if rng.random() < 0.85:
        rows.append(GrantRow("*", "/", rng.choice(LEVELS)))
    for p in rng.sample(prefixes, rng.randint(0, min(4, len(prefixes)))):
        if p != "/" or not rows:
            rows.append(GrantRow("*", p, rng.choice(LEVELS)))
    star = {r.path_prefix for r in rows}
    principals = (*USERS, *GROUPS)
    named = {(rng.choice(principals), rng.choice(prefixes)) for _ in range(rng.randint(0, 8))}
    rows += [GrantRow(pid, p, rng.choice(("read", "read_write"))) for pid, p in sorted(named)]
    if rng.random() < 0.3 and star:
        hole = rng.choice(sorted(star))
        rows.append(GrantRow(rng.choice(principals), hole, "read"))  # hole == grant
    member_of: dict[str, set[str]] = {u: set(rng.sample(GROUPS, rng.randint(0, 2))) for u in USERS}
    for i, g in enumerate(GROUPS):
        member_of[g] = {h for h in GROUPS[i + 1 :] if rng.random() < 0.4}
    return GrantWorld(grants=rows, member_of=member_of, owners={}), prefixes


def bounds_ok(found, prefixes: set[str]) -> bool:
    bounds = [*found.points, *(b for pair in found.opens for b in pair)]
    allowed = {"/", "0"} | prefixes | {p + "/" for p in prefixes} | {p + "0" for p in prefixes}
    return (
        list(found.points) == sorted(set(found.points))
        and all(lo < hi for lo, hi in found.opens)
        and all(left[1] <= right[0] for left, right in pairwise(found.opens))
        and not any("\x00" in b for b in bounds)
        and not any(b[-1] < " " for b in bounds)
        and all(b in allowed for b in bounds)
        and not any(any(lo < p < hi for lo, hi in found.opens) for p in found.points)
    )


def shipped_holds(found, path: str) -> bool:
    return path in found.points or any(lo < path < hi for lo, hi in found.opens)


def shipped_well_formed(found) -> bool:
    bounds = [*found.points, *(b for pair in found.opens for b in pair)]
    return not any(b[-1] < " " for b in bounds)


def span_bounds_ok(rs: RangeSet, prefixes: set[str]) -> bool:
    allowed = {"/", "0"} | prefixes | {p + "\x00" for p in prefixes} | {p + "/" for p in prefixes} | {p + "0" for p in prefixes}
    return all(lo in allowed and hi in allowed for lo, hi in rs)


def check_case(rng: random.Random, examples: dict[str, str]) -> None:
    world, prefixes = rand_world(rng)
    prefix_set = {r.path_prefix for r in world.grants}
    rows = [Row(*r) for r in world.grants]
    probes = probes_for(prefixes, rng)
    COUNTS["cases"] += 1
    COUNTS["probes"] += len(probes)

    def broke(key: str, detail: str) -> None:
        INVARIANTS[key] += 1
        examples.setdefault(key, detail)

    # I7: range-set laws on two random cover unions.
    a = cover_all(rng.sample(prefixes, rng.randint(0, len(prefixes))))
    b = cover_all(rng.sample(prefixes, rng.randint(0, len(prefixes))))
    u, x, d = union(a, b), intersect(a, b), subtract(a, b)
    law_ok = (
        normalise(u) == u
        and u == union_many([a, b]) == normalise(a + b)
        and intersect(d, b) == ()
        and union(d, x) == a
        and all(
            contains(u, q) == (contains(a, q) or contains(b, q))
            and contains(x, q) == (contains(a, q) and contains(b, q))
            and contains(d, q) == (contains(a, q) and not contains(b, q))
            for q in probes
        )
    )
    if not law_ok:
        broke("I7 range-set laws: union/intersect/subtract pointwise; (A-B) and B disjoint; (A-B) | (A&B) == A; normalise idempotent; union == union_many == normalise(A+B)", f"a={a} b={b}")

    # I8: meet on prefixes is intersect on range sets, and agrees with the shipped meet.
    pa = minimise(rng.sample(prefixes, rng.randint(0, len(prefixes))))
    pb = minimise(rng.sample(prefixes, rng.randint(0, len(prefixes))))
    m = meet(pa, pb)
    if cover_all(m) != intersect(cover_all(pa), cover_all(pb)) or set(m) != set(s_meet(pa, pb)) or set(pa) != set(s_minimise(pa)):
        broke("I8 cover_all(meet(a, b)) == intersect(cover_all(a), cover_all(b)); meet == shipped meet as a set; minimise == shipped minimise as a set", f"pa={pa} pb={pb} meet={m} shipped={s_meet(pa, pb)}")

    # I9: the everyone region.
    star = {r.path_prefix: r.level for r in world.grants if r.principal_id == "*"}
    for level in ("read", "read_write"):
        need = LEVEL_RANK[level]
        region = everyone_region(star, need)
        if any(contains(region, q) != (everyone_rank(world, q) >= need) for q in probes):
            broke("I9 everyone_region == oracle everyone_rank pointwise", f"star={star} level={level}")

    subject_sets = [rng.sample(USERS, rng.randint(1, 3)) for _ in range(2)]
    for subjects in subject_sets:
        closures = world.closures(subjects)
        for level in ("read", "read_write"):
            need = LEVEL_RANK[level]
            shipped = resolve(closures, world.grants, level)
            new = resolve_rights(closures, rows, level)
            ranges = shipped.ranges()
            new_pieces = new.pieces()
            new_owner_pieces = new.owner_pieces()
            shipped_owned = dict(ranges.owners)
            if not bounds_ok(new_pieces, prefix_set) or any(not bounds_ok(f, prefix_set) for f in new_owner_pieces.values()):
                broke("I2 new pieces well-formed: sorted, disjoint, no NUL, no bound ending below space, every bound in {p, p/, p0, /, 0}", f"{world.grants} {subjects} {level} -> {new_pieces}")
            if not span_bounds_ok(new.arms, prefix_set) or any(not span_bounds_ok(rs, prefix_set) for rs in new.owners.values()):
                broke("I11 the new resolver never emits a span bound outside the input prefixes' closure {p, p+NUL, p/, p0, /, 0}", f"{world.grants} {subjects} {level} -> {new.arms}")
            if new.whole != (new.arms == FULL):
                broke("I6 whole is True exactly when the arm range set is the whole mount", f"{world.grants} {subjects} {level}")
            if shipped_well_formed(ranges.arms):
                if (tuple(ranges.arms.points), tuple(ranges.arms.opens)) != (new_pieces.points, new_pieces.opens):
                    broke("I5 new pieces identical to shipped pieces whenever the shipped pieces are well-formed", f"{world.grants} {subjects} {level}: {ranges.arms} vs {new_pieces}")
            else:
                COUNTS["shipped NUL bounds (the sibling bug)"] += 1
            for owner, found in shipped_owned.items():
                if shipped_well_formed(found) and owner in new_owner_pieces:
                    nf = new_owner_pieces[owner]
                    if (tuple(found.points), tuple(found.opens)) != (nf.points, nf.opens):
                        broke("I5 new pieces identical to shipped pieces whenever the shipped pieces are well-formed", f"owner {owner}: {world.grants} {subjects} {level}")
                elif not shipped_well_formed(found):
                    COUNTS["shipped NUL bounds (the sibling bug)"] += 1
            for q in probes:
                if pieces_hold(new_pieces, q) != new.covers(q) or any(pieces_hold(f, q) != contains(new.owners[o], q) for o, f in new_owner_pieces.items()):
                    broke("I3 new pieces == new range set pointwise; owner pieces == owner range set pointwise", f"{world.grants} {subjects} {level} at {q!r}")
                if shipped_holds(ranges.arms, q) != pieces_hold(new_pieces, q):
                    broke("I4 shipped pieces == new pieces pointwise (arms and owners)", f"{world.grants} {subjects} {level} at {q!r}")
                if not new.whole:
                    for o in set(shipped_owned) | set(new_owner_pieces):
                        s_h = o in shipped_owned and shipped_holds(shipped_owned[o], q)
                        n_h = o in new_owner_pieces and pieces_hold(new_owner_pieces[o], q)
                        if s_h != n_h:
                            broke("I4 shipped pieces == new pieces pointwise (arms and owners)", f"owner {o}: {world.grants} {subjects} {level} at {q!r}")
                if shipped.covers_subtree(q) and not new.covers_subtree(q):
                    broke("I10 covers_subtree(p) implies every probe under p is covered; shipped covers_subtree implies new", f"shipped⇒new {world.grants} {subjects} {level} at {q!r}")
                if new.covers_subtree(q) and any(not new.covers(r) for r in probes if s_covers(q, r)):
                    broke("I10 covers_subtree(p) implies every probe under p is covered; shipped covers_subtree implies new", f"unsound {world.grants} {subjects} {level} at {q!r}")
                for owner in (None, rng.choice(USERS)):
                    world.owners[q] = owner
                    o = set_rank(world, subjects, q) >= need
                    s = shipped.admits(q, owner)
                    n = new.admits(q, owner)
                    if not (o == s == n):
                        broke("I1 admits: oracle == shipped == new (every probe, every owner)", f"{world.grants} {subjects} {level} at {q!r} owner={owner}: oracle={o} shipped={s} new={n}")
                world.owners.pop(q, None)
    # I12: the empty subject set.
    for level in ("read", "read_write"):
        shipped = resolve({}, world.grants, level)
        new = resolve_rights({}, rows, level)
        if not (shipped.whole and new.whole):
            broke("I12 an empty subject set resolves to the whole mount in both resolvers (shipped vs new only; the oracle cannot answer)", f"{world.grants} {level}: shipped.whole={shipped.whole} new.whole={new.whole}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=20261002)
    ap.add_argument("--out", default=str(HERE / "runs" / "fuzz.md"))
    args = ap.parse_args()
    rng = random.Random(args.seed)
    examples: dict[str, str] = {}
    t0 = time.perf_counter()
    for i in range(args.cases):
        check_case(rng, examples)
        if i and i % 20000 == 0:
            print(f"{i} cases, {time.perf_counter() - t0:.0f} s, breaks so far {sum(INVARIANTS.values())}")
    took = time.perf_counter() - t0
    lines = [
        "# Fuzz run",
        "",
        f"- cases: {COUNTS['cases']:,} (seed {args.seed}), probes: {COUNTS['probes']:,}, {took:.0f} s",
        f"- segments: {SEGMENTS}",
        f"- shipped pieces carrying a NUL bound (the sibling bug), arm or owner pieces: {COUNTS['shipped NUL bounds (the sibling bug)']:,}",
        "",
        "| invariant | breaks |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in INVARIANTS.items()),
        "",
        "## First example per broken invariant",
        "",
        *([f"- {k}: {v}" for k, v in examples.items()] or ["none"]),
        "",
    ]
    Path(args.out).write_text("\n".join(lines))
    print("\n".join(lines))
    return 1 if sum(INVARIANTS.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
