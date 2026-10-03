"""Parity: the range algebra against the pointwise oracle and the shipped resolver.

Three answers for every (world, subject set, level, path, owner):

- the oracle in ``tests.support.oracles.grants`` (the pure truth);
- the shipped ``vfs.storage.grants.resolve(...).admits``;
- this study's ``algebra.resolve_rights(...).admits``.

They must agree everywhere. The pieces the two resolvers emit must admit
the same paths; where the shipped pieces are well-formed the tuples must
be identical; where the shipped pieces carry a NUL bound (the sibling
case) the new pieces must not, and the world is listed.

Run from the repo root:

    uv run --no-sync python context/research/studies/2026-10-02-sorted-merge-range-algebra/parity.py --worlds 2000
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

from algebra import Pieces as NewPieces  # noqa: E402
from algebra import RangeRights, Row, contains, pieces_hold, resolve_rights  # noqa: E402
from tests.storage.test_grants import TRAPS  # noqa: E402
from tests.support.grant_worlds import FILES, GROUPS, PATHS, SUBJECT_SETS, USERS, random_world  # noqa: E402
from tests.support.oracles.grants import GrantWorld, set_rank  # noqa: E402
from vfs.storage.grants import LEVEL_RANK, GrantRow, Pieces, Rights, covers, resolve  # noqa: E402

LEVELS = ("read", "read_write")
OWNERS = (None, *USERS)

# The sibling generator: names of the shapes p + "0", p + "-x" beside p.
SIBLING_DIRS = ("/a", "/a0", "/a-b", "/a/b", "/a/b0", "/a/b-c", "/e", "/e0", "/e/f")
SIBLING_FILES = ("/top.md", "/a/x.md", "/a0/x.md", "/a-b/x.md", "/a/b/y.md", "/a/b0/y.md", "/e/v.md", "/e0/v.md")
SIBLING_PATHS = (*SIBLING_DIRS, *SIBLING_FILES)
SIBLING_PROBES = (*SIBLING_PATHS, "/a00", "/a0-x", "/a0/x", "/a/b00", "/e00", "/e-f", "/a-b0", "/a/b-c0")


def sibling_world(rng: random.Random) -> GrantWorld:
    """``random_world`` over a path set that holds sibling traps as grantable prefixes."""
    prefixes = ("/", *SIBLING_PATHS)
    rows = [GrantRow("*", "/", rng.choice(("none", "read", "read_write")))]
    rows += [
        GrantRow("*", prefix, rng.choice(("none", "read", "read_write")))
        for prefix in rng.sample(SIBLING_PATHS, rng.randint(0, 3))
    ]
    principals = (*USERS, *GROUPS)
    named = {(rng.choice(principals), rng.choice(prefixes)) for _ in range(rng.randint(0, 8))}
    rows += [GrantRow(principal, prefix, rng.choice(("read", "read_write"))) for principal, prefix in sorted(named)]
    member_of: dict[str, set[str]] = {}
    for user in USERS:
        member_of[user] = set(rng.sample(GROUPS, rng.randint(0, 2)))
    for i, inner in enumerate(GROUPS):
        member_of[inner] = {g for g in GROUPS[i + 1 :] if rng.random() < 0.4}
    owners = {path: rng.choice((None, *USERS)) for path in SIBLING_FILES}
    return GrantWorld(grants=rows, member_of=member_of, owners=owners)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def well_formed_shipped(found: Pieces) -> bool:
    """The test suite's ``_assert_well_formed``, as a predicate."""
    bounds = [*found.points, *(b for pair in found.opens for b in pair)]
    return (
        list(found.points) == sorted(set(found.points))
        and all(lo < hi for lo, hi in found.opens)
        and all(left[1] <= right[0] for left, right in pairwise(found.opens))
        and not any(bound[-1] < " " for bound in bounds)
    )


def check_new_pieces(found: NewPieces, prefixes: set[str]) -> list[str]:
    """Every invariant the new pieces must hold; returns the broken ones."""
    broken: list[str] = []
    bounds = [*found.points, *(b for pair in found.opens for b in pair)]
    if list(found.points) != sorted(set(found.points)):
        broken.append("points not sorted/unique")
    if not all(lo < hi for lo, hi in found.opens):
        broken.append("empty open range")
    if not all(left[1] <= right[0] for left, right in pairwise(found.opens)):
        broken.append("open ranges overlap or unsorted")
    if any("\x00" in b for b in bounds):
        broken.append("NUL in a bound")
    if any(b[-1] < " " for b in bounds):
        broken.append("bound ends below space")
    allowed = {"/", "0"} | prefixes | {p + "/" for p in prefixes} | {p + "0" for p in prefixes}
    if any(b not in allowed for b in bounds):
        broken.append("bound not in {p, p/, p0, /, 0}")
    if any(p in found.points and any(lo < p < hi for lo, hi in found.opens) for p in found.points):
        broken.append("point inside an open range")
    return broken


def holds(found: Pieces, path: str) -> bool:
    return path in found.points or any(lo < path < hi for lo, hi in found.opens)


class Tally:
    def __init__(self) -> None:
        self.checks = 0
        self.failures: list[str] = []
        self.nul_worlds: list[str] = []
        self.identical_pieces = 0
        self.nul_pieces = 0
        self.subtree_more_complete = 0
        self.whole_more_complete = 0

    def fail(self, msg: str) -> None:
        self.failures.append(msg)
        if len(self.failures) <= 10:
            print("FAIL", msg)


def run_world(world: GrantWorld, probes: tuple[str, ...], tally: Tally, oracle_owners: bool, label: str) -> None:
    rows = [Row(*r) for r in world.grants]
    prefixes = {r.path_prefix for r in world.grants}
    for subjects in SUBJECT_SETS:
        closures = world.closures(subjects)
        for level in LEVELS:
            need = LEVEL_RANK[level]
            shipped: Rights = resolve(closures, world.grants, level)
            new: RangeRights = resolve_rights(closures, rows, level)
            ranges = shipped.ranges()
            new_pieces = new.pieces()
            new_owner_pieces = new.owner_pieces()
            # Pieces: new well-formed; identical to shipped where shipped is well-formed.
            broken = check_new_pieces(new_pieces, prefixes)
            if broken:
                tally.fail(f"{label} new pieces broken {broken}: {world.grants} {subjects} {level}")
            if well_formed_shipped(ranges.arms):
                if tuple(ranges.arms.points) != new_pieces.points or tuple(ranges.arms.opens) != new_pieces.opens:
                    tally.fail(f"{label} pieces differ: {ranges.arms} vs {new_pieces} :: {world.grants} {subjects} {level}")
                else:
                    tally.identical_pieces += 1
            else:
                tally.nul_pieces += 1
                tally.nul_worlds.append(f"{label} subjects={subjects} level={level} grants={world.grants} shipped={ranges.arms}")
            shipped_owned = {owner: found for owner, found in ranges.owners}
            for owner, found in new_owner_pieces.items():
                broken = check_new_pieces(found, prefixes)
                if broken:
                    tally.fail(f"{label} owner pieces broken {broken}: {world.grants} {subjects} {level}")
            if not new.whole and set(shipped_owned) != set(new_owner_pieces):
                tally.fail(f"{label} owner set differs {set(shipped_owned)} vs {set(new_owner_pieces)}")
            if shipped.whole and not new.whole:
                tally.fail(f"{label} shipped whole, new not: {world.grants} {subjects} {level}")
            if new.whole and not shipped.whole:
                tally.whole_more_complete += 1
            for path in probes:
                # covers / covers_subtree / pieces pointwise
                if shipped.covers(path) != new.covers(path):
                    tally.fail(f"{label} covers differs at {path!r}: {world.grants} {subjects} {level}")
                if pieces_hold(new_pieces, path) != new.covers(path):
                    tally.fail(f"{label} new pieces disagree with new covers at {path!r}")
                if holds(ranges.arms, path) != pieces_hold(new_pieces, path):
                    tally.fail(f"{label} shipped pieces vs new pieces at {path!r}: {world.grants} {subjects} {level}")
                if shipped.covers_subtree(path):
                    if not new.covers_subtree(path):
                        tally.fail(f"{label} covers_subtree shipped True new False at {path!r}")
                elif new.covers_subtree(path):
                    tally.subtree_more_complete += 1
                for owner, found in new_owner_pieces.items():
                    if (owner in shipped_owned and holds(shipped_owned[owner], path)) != pieces_hold(found, path):
                        tally.fail(f"{label} owner pieces differ for {owner} at {path!r}")
                    if pieces_hold(found, path) != contains(new.owners[owner], path):
                        tally.fail(f"{label} owner pieces vs owner set for {owner} at {path!r}")
                # admits, three ways
                own = world.owners.get(path)
                a_ship = shipped.admits(path, own)
                a_new = new.admits(path, own)
                a_orc = set_rank(world, subjects, path) >= need
                tally.checks += 1
                if not (a_ship == a_new == a_orc):
                    tally.fail(f"{label} admits {path!r} owner={own}: oracle={a_orc} shipped={a_ship} new={a_new} :: {world.grants} {subjects} {level}")
                for owner in OWNERS:
                    if owner == own:
                        continue
                    a_ship = shipped.admits(path, owner)
                    a_new = new.admits(path, owner)
                    tally.checks += 1
                    if a_ship != a_new:
                        tally.fail(f"{label} admits {path!r} owner={owner}: shipped={a_ship} new={a_new} :: {world.grants} {subjects} {level}")
                    if oracle_owners:
                        saved = world.owners.get(path)
                        world.owners[path] = owner
                        a_orc = set_rank(world, subjects, path) >= need
                        world.owners[path] = saved
                        if a_orc != a_new:
                            tally.fail(f"{label} admits {path!r} owner={owner}: oracle={a_orc} new={a_new} :: {world.grants} {subjects} {level}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worlds", type=int, default=2000)
    ap.add_argument("--oracle-owner-worlds", type=int, default=500, help="worlds on which every owner variant is also checked by the oracle")
    ap.add_argument("--out", default=str(HERE / "runs" / "parity.md"))
    args = ap.parse_args()

    tally = Tally()
    t0 = time.perf_counter()
    rng = random.Random(58)
    for i in range(args.worlds):
        run_world(random_world(rng), (*PATHS, *TRAPS), tally, i < args.oracle_owner_worlds, f"base#{i}")
    t_base = time.perf_counter() - t0
    base_checks, base_nul, base_ident = tally.checks, tally.nul_pieces, tally.identical_pieces

    t1 = time.perf_counter()
    rng = random.Random(7202)
    for i in range(args.worlds):
        run_world(sibling_world(rng), SIBLING_PROBES, tally, i < args.oracle_owner_worlds, f"sib#{i}")
    t_sib = time.perf_counter() - t1

    # The handful of hand-made shapes from the review and the ADR.
    hand = [
        ("review sibling", [GrantRow("*", "/", "none"), GrantRow("bob", "/v1", "read"), GrantRow("bob", "/v10", "read")], ("bob",)),
        ("adr pair", [GrantRow("*", "/", "none"), GrantRow("bob", "/proj1", "read"), GrantRow("bob", "/proj10", "read")], ("bob",)),
        ("hole on root", [GrantRow("*", "/", "none"), GrantRow("bob", "/", "read"), GrantRow("*", "/a", "read")], ("bob",)),
        ("hole is grant", [GrantRow("*", "/", "read"), GrantRow("*", "/a", "none"), GrantRow("bob", "/a", "read")], ("bob",)),
        ("nested", [GrantRow("*", "/", "read_write"), GrantRow("*", "/a", "none"), GrantRow("*", "/a/b", "read"), GrantRow("*", "/a/b/c", "none")], ("bob",)),
    ]
    for label, grants, subjects in hand:
        world = GrantWorld(grants=grants, member_of={}, owners={})
        probes = tuple({r.path_prefix for r in grants} | {r.path_prefix + s for r in grants for s in ("0", "/x", "-x", "00")} | {"/", "/zzz"})
        run_world(world, probes, tally, True, label)

    lines = [
        "# Parity run",
        "",
        f"- worlds: {args.worlds} base (seed 58, the test suite's generator) + {args.worlds} sibling (seed 7202), + 5 hand-made",
        f"- subject sets per world: {len(SUBJECT_SETS)}; levels: {len(LEVELS)}; probes per base world: {len(PATHS) + len(TRAPS)}; per sibling world: {len(SIBLING_PROBES)}",
        f"- admits checks (oracle vs shipped vs new, every owner variant): {tally.checks:,}",
        f"- failures: {len(tally.failures)}",
        f"- base worlds: {base_checks:,} checks in {t_base:.1f} s; pieces identical to shipped: {base_ident:,}; shipped pieces with a NUL bound: {base_nul}",
        f"- sibling worlds: {tally.checks - base_checks:,} checks in {t_sib:.1f} s; pieces identical to shipped: {tally.identical_pieces - base_ident:,}; shipped pieces with a NUL bound: {tally.nul_pieces - base_nul}",
        f"- (world, subjects, level) where the new `whole` is True and the shipped is False (new arms cover the mount through several arms): {tally.whole_more_complete}",
        f"- (world, subjects, level, path) where new `covers_subtree` is True and the shipped is False (never the reverse): {tally.subtree_more_complete}",
        "",
        "## Failures",
        "",
        *(tally.failures[:50] or ["none"]),
        "",
        f"## Worlds where the shipped pieces carry a NUL bound ({len(tally.nul_worlds)})",
        "",
        "In every one the new pieces hold no NUL and admit the same paths pointwise (checked above).",
        "",
        *(f"- {w}" for w in tally.nul_worlds),
        "",
    ]
    Path(args.out).write_text("\n".join(lines))
    print("\n".join(lines[:12]))
    print(f"NUL worlds listed: {len(tally.nul_worlds)}; wrote {args.out}")
    return 1 if tally.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
