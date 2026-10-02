"""The pure resolver — prefix algebra pinned against the pointwise oracle.

``resolve`` turns rows into arms; ``Rights.admits`` asks the arms about
one row. The oracle in ``tests.support.oracles.grants`` answers the same
question path by path with no algebra at all, so on every random world
the two must agree for every path, subject set, and level.
"""

from __future__ import annotations

import random
from itertools import pairwise

import pytest

from tests.support.grant_worlds import FILES, PATHS, SUBJECT_SETS, random_world
from tests.support.oracles.grants import set_rank
from vfs.storage.grants import (
    LEVEL_RANK,
    ROOT,
    Arm,
    GrantRow,
    Pieces,
    Rights,
    ancestors_and_self,
    covers,
    meet,
    meet_all,
    minimise,
    pieces,
    resolve,
)

WORLDS = 400

# Paths that sort beside the world's prefixes: "-" below "/", "0" just above it.
TRAPS = ("/a-b", "/a0", "/a/b-c", "/a/b0", "/a/b/c-d.md", "/a/b/c0", "/e-f", "/e0", "/e/f0")


# ---------------------------------------------------------------------------
# Parity with the oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["read", "read_write"])
def test_the_resolver_agrees_with_the_oracle_on_every_path(level: str) -> None:
    rng = random.Random(58)
    need = LEVEL_RANK[level]
    for _ in range(WORLDS):
        world = random_world(rng)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, level)  # ty: ignore[invalid-argument-type]
            for path in PATHS:
                expected = set_rank(world, subjects, path) >= need
                assert rights.admits(path, world.owners.get(path)) is expected, (world, subjects, path)


def test_without_the_owner_floor_ownership_grants_nothing() -> None:
    rng = random.Random(67)
    for _ in range(WORLDS):
        world = random_world(rng)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, "read", owner_floor=False)
            assert not rights.owner_arms
            for path in FILES:
                expected = set_rank(world, subjects, path, owner_floor=False) >= LEVEL_RANK["read"]
                assert rights.admits(path, world.owners[path]) is expected


def test_covers_subtree_never_promises_a_row_it_does_not_cover() -> None:
    rng = random.Random(70)
    for _ in range(WORLDS):
        world = random_world(rng)
        rights = resolve(world.closures(("u1", "u2")), world.grants, "read_write")
        for root in PATHS:
            if rights.covers_subtree(root):
                assert all(rights.covers(path) for path in PATHS if covers(root, path))


@pytest.mark.parametrize("level", ["read", "read_write"])
def test_the_pieces_admit_exactly_what_the_arms_and_owner_arms_cover(level: str) -> None:
    rng = random.Random(72)
    for _ in range(WORLDS):
        world = random_world(rng)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, level)  # ty: ignore[invalid-argument-type]
            ranges = rights.ranges()
            owned = {arm.owner: arm.prefixes for arm in rights.owner_arms}
            assert [owner for owner, _ in ranges.owners] == list(owned)
            for found in (ranges.arms, *(found for _, found in ranges.owners)):
                _assert_well_formed(found)
            for path in (*PATHS, *TRAPS):
                assert _holds(ranges.arms, path) is rights.covers(path), (world, subjects, path)
                for owner, found in ranges.owners:
                    assert _holds(found, path) is any(covers(p, path) for p in owned[owner])


# ---------------------------------------------------------------------------
# The prefix algebra
# ---------------------------------------------------------------------------


def test_minimise_drops_every_prefix_under_another() -> None:
    assert minimise(["/a/b", "/a", "/c/d", "/c/d/e"]) == ("/a", "/c/d")
    assert minimise(["/a", "/"]) == (ROOT,)
    assert minimise([]) == ()


def test_meet_is_the_intersection_of_coverage() -> None:
    assert meet(["/a"], ["/a/b", "/c"]) == ("/a/b",)
    assert meet(["/a/b"], ["/a"]) == ("/a/b",)
    assert meet(["/a"], ["/b"]) == ()
    assert meet([ROOT], ["/x"]) == ("/x",)


def test_the_meet_of_nothing_is_the_whole_mount() -> None:
    assert meet_all([]) == (ROOT,)
    assert meet_all([["/a"], ["/a/b"], ["/a/b/c", "/z"]]) == ("/a/b/c",)


def test_ancestors_run_deepest_first_to_the_root() -> None:
    assert ancestors_and_self("/a/b") == ["/a/b", "/a", "/"]
    assert ancestors_and_self("/") == ["/"]


# ---------------------------------------------------------------------------
# Rights as path pieces
# ---------------------------------------------------------------------------


def test_a_prefix_is_its_own_path_and_an_open_range_beneath() -> None:
    assert pieces([Arm("/a")]) == Pieces(("/a",), (("/a/", "/a0"),))
    assert pieces([Arm(ROOT)]) == Pieces((ROOT,), ((ROOT, "0"),))
    assert pieces([]) == Pieces((), ())


def test_a_hole_is_cut_and_its_siblings_stay() -> None:
    found = pieces([Arm("/a", ("/a/b",))])
    assert found == Pieces(("/a", "/a/b0"), (("/a/", "/a/b"), ("/a/b", "/a/b/"), ("/a/b0", "/a0")))
    assert _holds(found, "/a/b-c") and _holds(found, "/a/b0") and _holds(found, "/a/c")
    assert not _holds(found, "/a/b") and not _holds(found, "/a/b/x")


def test_nested_arms_merge_into_one() -> None:
    assert pieces([Arm("/a"), Arm("/a/b")]) == pieces([Arm("/a")])


def test_the_ranges_are_computed_once() -> None:
    rights = resolve({"ann": frozenset()}, [GrantRow("*", ROOT, "none"), GrantRow("ann", "/a", "read")], "read")
    assert rights.ranges() is rights.ranges()


# ---------------------------------------------------------------------------
# Rights shapes
# ---------------------------------------------------------------------------


def test_an_open_root_resolves_to_the_whole_mount() -> None:
    rights = resolve({"ann": frozenset()}, [GrantRow("*", "/", "read_write")], "read_write")
    assert rights.whole and rights == Rights.everything("read_write")
    assert rights.covers("/any/where") and rights.covers_subtree("/any")


def test_nothing_is_empty_and_admits_nothing() -> None:
    rights = Rights.nothing("read")
    assert rights.empty
    assert not rights.admits("/a", owner_id=None)
    assert not rights.admits("/a", owner_id="ann")
    assert rights.roots() == ()


def test_a_posture_hole_cuts_every_covering_everyone_arm() -> None:
    # Under an open root, a shared /a holding a private /a/b: /a/b must be
    # cut from the root's arm too, not only from /a's.
    rows = [GrantRow("*", "/", "read_write"), GrantRow("*", "/a", "read"), GrantRow("*", "/a/b", "none")]
    rights = resolve({"ann": frozenset()}, rows, "read")
    assert rights.admits("/a/x", owner_id=None)
    assert not rights.admits("/a/b/x", owner_id=None)
    assert rights.arms == (Arm("/", ("/a/b",)),)


def test_owner_arms_are_per_member_and_trimmed_by_the_shared_arms() -> None:
    rows = [GrantRow("*", "/", "none"), GrantRow("bob", "/hr", "read"), GrantRow("ann", "/pub", "read")]
    rows.append(GrantRow("bob", "/pub", "read"))
    rights = resolve({"ann": frozenset(), "bob": frozenset()}, rows, "read")
    # ann's own row under /hr passes (bob reads /hr); under /pub the shared arm already covers it.
    assert [(arm.owner, arm.prefixes) for arm in rights.owner_arms] == [("ann", ("/hr",))]
    assert rights.admits("/hr/case.md", owner_id="ann")
    assert not rights.admits("/hr/case.md", owner_id="bob")
    assert rights.roots() == ("/pub",)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _holds(found: Pieces, path: str) -> bool:
    return path in found.points or any(lo < path < hi for lo, hi in found.opens)


def _assert_well_formed(found: Pieces) -> None:
    """Sorted, disjoint, and no bound a path plus a low byte."""
    assert list(found.points) == sorted(set(found.points))
    assert all(lo < hi for lo, hi in found.opens)
    assert all(left[1] <= right[0] for left, right in pairwise(found.opens))
    bounds = [*found.points, *(b for pair in found.opens for b in pair)]
    assert not any(bound[-1] < " " for bound in bounds)
