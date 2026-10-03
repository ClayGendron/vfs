"""The pure resolver — the range algebra pinned against the pointwise oracle.

``resolve`` turns rows into sorted spans; ``Rights.admits`` bisects them
for one row. The oracle in ``tests.support.oracles.grants`` answers the
same question path by path with no algebra at all, so on every random
world — the base tree and the sibling tree whose names sort beside each
other — the two must agree for every path, subject set, and level. The
algebra's operations are pinned one by one beneath, each on the shape a
deliberate break would get wrong.
"""

from __future__ import annotations

import random
from itertools import pairwise
from typing import TYPE_CHECKING

import pytest

from tests.support.grant_worlds import LAYOUTS, SUBJECT_SETS, Layout, random_world
from tests.support.oracles.grants import everyone_rank, set_rank
from vfs.storage.grants import (
    FULL,
    LEVEL_RANK,
    ROOT,
    GrantRow,
    OwnerArm,
    Pieces,
    Rights,
    above,
    ancestors_and_self,
    contains,
    cover,
    cover_all,
    covers,
    end,
    inflight_regions,
    intersect,
    level_at,
    meet,
    meet_all,
    minimise,
    normalise,
    pieces,
    posture_regions,
    resolve,
    subtract,
    through,
    tree_key,
    union,
)

if TYPE_CHECKING:
    from vfs.storage.grants import GrantLevel

WORLDS = 400

# Every (layout, level) the parity tests run over.
CASES = [
    pytest.param(layout, level, id=f"{name}-{level}")
    for layout, name in zip(LAYOUTS, ("base", "siblings"), strict=True)
    for level in ("read", "read_write")
]


# ---------------------------------------------------------------------------
# Parity with the oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("layout", "level"), CASES)
def test_the_resolver_agrees_with_the_oracle_on_every_path(layout: Layout, level: GrantLevel) -> None:
    rng = random.Random(58)
    need = LEVEL_RANK[level]
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, level)
            for path in (*layout.paths, *layout.traps):
                for owner in (world.owners.get(path), None, *subjects):
                    world.owners[path] = owner
                    expected = set_rank(world, subjects, path) >= need
                    label = everyone_rank(world, path)
                    assert rights.admits(path, owner, label) is expected, (world, subjects, path, owner)
                    world.owners.pop(path, None)


@pytest.mark.parametrize(("layout", "level"), CASES)
def test_a_posture_row_in_flight_is_judged_by_the_rows_not_the_labels(layout: Layout, level: GrantLevel) -> None:
    # One posture row changes level and its relabel has not settled: every
    # row beneath it may still carry the old label, or already the new one.
    # The oracle judges by the rows; the resolver must agree whatever the
    # label says, and everywhere else the label is still the truth.
    rng = random.Random(84)
    need = LEVEL_RANK[level]
    probes = (*layout.paths, *layout.traps)
    for _ in range(WORLDS):
        before = random_world(rng, layout)
        stale = {path: everyone_rank(before, path) for path in probes}
        world = random_world(rng, layout)
        world.grants = list(before.grants)
        star = [row for row in world.grants if row.principal_id == "*"]
        changed = rng.choice(star)
        world.grants.remove(changed)
        world.grants.append(GrantRow("*", changed.path_prefix, rng.choice(("none", "read", "read_write"))))
        region = subtract(cover(changed.path_prefix), cover_all(_deeper(star, changed.path_prefix)))
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, level, pending={changed.path_prefix})
            for path in probes:
                expected = set_rank(world, subjects, path) >= need
                labels = {everyone_rank(world, path), stale[path]} if contains(region, path) else {stale[path]}
                for label in labels:
                    assert rights.admits(path, world.owners.get(path), label) is expected, (world, subjects, path)
            # The holes are the region or nothing; a cover is already in the spans.
            assert rights.holes in ((), region) or rights.whole


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
def test_without_the_owner_floor_ownership_grants_nothing(layout: Layout) -> None:
    rng = random.Random(67)
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, "read", owner_floor=False)
            assert not rights.owner_arms
            for path in layout.files:
                expected = set_rank(world, subjects, path, owner_floor=False) >= LEVEL_RANK["read"]
                assert rights.admits(path, world.owners[path], everyone_rank(world, path)) is expected


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
def test_covers_subtree_never_promises_a_row_it_does_not_cover(layout: Layout) -> None:
    rng = random.Random(70)
    probes = (*layout.paths, *layout.traps)
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        rights = resolve(world.closures(("u1", "u2")), world.grants, "read_write")
        for root in probes:
            if rights.covers_subtree(root):
                assert all(rights.covers(path) for path in probes if covers(root, path))


@pytest.mark.parametrize(("layout", "level"), CASES)
def test_the_pieces_admit_exactly_what_the_spans_and_owner_arms_cover(layout: Layout, level: GrantLevel) -> None:
    rng = random.Random(72)
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        prefixes = {row.path_prefix for row in world.grants}
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, level)
            ranges = rights.ranges()
            owned = {arm.owner: arm.prefixes for arm in rights.owner_arms}
            assert [owner for owner, _ in ranges.owners] == list(owned)
            for found in (ranges.arms, *(found for _, found in ranges.owners)):
                _assert_well_formed(found, prefixes)
            for path in (*layout.paths, *layout.traps):
                assert _holds(ranges.arms, path) is rights.covers(path), (world, subjects, path)
                # An owner arm's pieces never name a row the spans already do.
                for owner, found in ranges.owners:
                    reached = any(covers(p, path) for p in owned[owner]) and not rights.covers(path)
                    assert _holds(found, path) is reached


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
def test_every_hidden_directory_with_a_visible_row_beneath_lies_above_a_root(layout: Layout) -> None:
    # The road is computed from the roots: a root is covered, its parent
    # is not, and every covered path lies under a root or an owner arm.
    rng = random.Random(74)
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        for subjects in SUBJECT_SETS:
            rights = resolve(world.closures(subjects), world.grants, "read")
            for root in rights.roots:
                assert rights.covers(root)
                assert root == ROOT or not rights.covers(ancestors_and_self(root)[1])
            for path in layout.paths:
                if rights.covers(path):
                    assert any(covers(root, path) for root in rights.roots)


# ---------------------------------------------------------------------------
# The everyone level
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
def test_level_at_is_the_deepest_covering_posture_row(layout: Layout) -> None:
    rng = random.Random(76)
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        star = {row.path_prefix: row.level for row in world.grants if row.principal_id == "*"}
        for path in (*layout.paths, *layout.traps, ROOT):
            assert LEVEL_RANK[level_at(star, path)] == everyone_rank(world, path)


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
def test_posture_regions_partition_the_mount_by_level(layout: Layout) -> None:
    # Each path lies in exactly the region of its level, or in none when
    # no posture row covers it — the shape the rebuild relabels from.
    rng = random.Random(77)
    for _ in range(WORLDS):
        world = random_world(rng, layout)
        star = {row.path_prefix: row.level for row in world.grants if row.principal_id == "*"}
        regions = posture_regions(star)
        for path in (*layout.paths, *layout.traps, ROOT):
            holding = [level for level, spans in regions.items() if contains(spans, path)]
            assert holding == [level_at(star, path)]


def test_posture_regions_are_empty_without_posture_rows() -> None:
    assert posture_regions({}) == {"none": (), "read": (), "read_write": ()}
    assert level_at({}, "/a") == "none"


# ---------------------------------------------------------------------------
# The prefix algebra
# ---------------------------------------------------------------------------


def test_tree_order_keeps_a_subtree_together() -> None:
    assert sorted(["/a-b", "/a/b", "/a", "/a0", "/"], key=tree_key) == ["/", "/a", "/a/b", "/a-b", "/a0"]


def test_minimise_drops_every_prefix_under_another() -> None:
    assert minimise(["/a/b", "/a", "/c/d", "/c/d/e"]) == ("/a", "/c/d")
    assert minimise(["/a", "/"]) == (ROOT,)
    assert minimise(["/a-b", "/a/c", "/a/c/d"]) == ("/a/c", "/a-b")
    assert minimise([]) == ()


def test_meet_is_the_intersection_of_coverage() -> None:
    assert meet(["/a"], ["/a/b", "/c"]) == ("/a/b",)
    assert meet(["/a/b"], ["/a"]) == ("/a/b",)
    assert meet(["/a"], ["/b"]) == ()
    assert meet([ROOT], ["/x"]) == ("/x",)
    # Both directions in one merge: the deeper side alternates.
    assert meet(["/a", "/b/c", "/d"], ["/a/x", "/b", "/d"]) == ("/a/x", "/b/c", "/d")


def test_the_meet_of_nothing_is_the_whole_mount() -> None:
    assert meet_all([]) == (ROOT,)
    assert meet_all([["/a"], ["/a/b"], ["/a/b/c", "/z"]]) == ("/a/b/c",)


def test_ancestors_run_deepest_first_to_the_root() -> None:
    assert ancestors_and_self("/a/b") == ["/a/b", "/a", "/"]
    assert ancestors_and_self("/") == ["/"]


# ---------------------------------------------------------------------------
# Range sets
# ---------------------------------------------------------------------------


def test_a_prefix_covers_its_own_path_and_an_open_subtree() -> None:
    assert cover("/a") == (("/a", "/a\x00"), ("/a/", "/a0"))
    assert cover(ROOT) == FULL
    assert cover_all([]) == ()


def test_normalise_sorts_and_joins_overlapping_and_touching_spans() -> None:
    assert normalise([("/c", "/d"), ("/a", "/b"), ("/b", "/c")]) == (("/a", "/d"),)
    assert normalise([("/a", "/c"), ("/b", "/d")]) == (("/a", "/d"),)
    assert normalise([("/a", "/d"), ("/b", "/c")]) == (("/a", "/d"),)
    assert normalise([("/x", "/y"), ("/a", "/b")]) == (("/a", "/b"), ("/x", "/y"))


def test_union_merges_nested_prefixes_into_one() -> None:
    assert union(cover("/a"), cover("/a/b")) == cover("/a")
    assert union(cover("/a"), cover("/c")) == (*cover("/a"), *cover("/c"))
    assert union((), ()) == ()


def test_subtract_cuts_each_span_exactly_at_the_cut_bounds() -> None:
    # A cut's own bounds become the kept spans' bounds; nothing is kept
    # at the cut's start (the off-by-one a sentinel-appending break makes).
    assert subtract(cover("/a"), cover("/a/b")) == (
        ("/a", "/a\x00"),
        ("/a/", "/a/b"),
        ("/a/b\x00", "/a/b/"),
        ("/a/b0", "/a0"),
    )
    assert subtract(FULL, FULL) == ()
    assert subtract(cover("/a"), ()) == cover("/a")
    assert subtract((("/a", "/z"),), (("/", "/b"), ("/c", "/d"), ("/y", "0"))) == (("/b", "/c"), ("/d", "/y"))
    assert subtract((("/a", "/c"), ("/d", "/f")), (("/b", "/e"),)) == (("/a", "/b"), ("/e", "/f"))
    # Cuts that end before a kept span begins are skipped, never applied to a later span.
    assert subtract((("/m", "/n"), ("/x", "/y")), (("/a", "/b"), ("/c", "/m"), ("/w", "/x"))) == (
        ("/m", "/n"),
        ("/x", "/y"),
    )


def test_contains_bisects_to_the_one_candidate_span() -> None:
    spans = subtract(cover("/a"), cover("/a/b"))
    assert contains(spans, "/a") and contains(spans, "/a/c") and contains(spans, "/a/b-c") and contains(spans, "/a/b0")
    assert not contains(spans, "/a/b") and not contains(spans, "/a/b/x") and not contains(spans, "/a0")
    assert not contains((), "/a")
    assert not contains(spans, "/")


def test_intersect_keeps_exactly_the_overlap() -> None:
    assert intersect(cover("/a"), cover("/a/b")) == cover("/a/b")
    assert intersect(cover("/a"), cover("/b")) == ()
    assert intersect((("/a", "/c"), ("/d", "/f")), (("/b", "/e"),)) == (("/b", "/c"), ("/d", "/e"))
    assert intersect(FULL, cover("/x")) == cover("/x") and intersect((), FULL) == ()
    # The same answer as a double subtraction, on every shape the holes take.
    left, right = subtract(cover("/a"), cover("/a/b")), union(cover("/a/b"), cover("/a/c"))
    assert intersect(left, right) == subtract(left, subtract(left, right))


def test_above_and_through_split_a_range_set_at_a_cursor() -> None:
    spans = subtract(cover("/a"), cover("/a/b"))
    # At a path inside a span: the path itself goes with ``through``.
    assert through(spans, "/a/c") == (("/a", "/a\x00"), ("/a/", "/a/b"), ("/a/b\x00", "/a/b/"), ("/a/b0", "/a/c\x00"))
    assert above(spans, "/a/c") == (("/a/c\x00", "/a0"),)
    assert union(through(spans, "/a/c"), above(spans, "/a/c")) == spans
    # At the end of the set nothing is above; at an exclusive bound the next span is whole.
    assert above(spans, end(spans)) == () and end(spans) == "/a0"
    assert above(spans, "/a/b") == (("/a/b\x00", "/a/b/"), ("/a/b0", "/a0"))
    assert end(union(cover("/v1"), cover("/v10"))) == "/v100" and end(cover("/a/b")) == "/a/b0"
    assert end((("/p", "/p\x00"),)) == "/p" and above((("/p", "/p\x00"),), "/p") == ()
    assert above((), "/x") == () and through((), "/x") == ()


def test_inflight_regions_are_each_pending_rows_region_split_by_its_new_level() -> None:
    star: dict[str, GrantLevel] = {"/": "read", "/a": "none", "/a/b": "read_write", "/c": "read_write"}
    region = subtract(cover("/a"), cover("/a/b"))
    # /a narrows below read: a hole at read; /c widens to read_write: a cover at both.
    assert inflight_regions(star, ["/a"], 1) == ((), region)
    assert inflight_regions(star, ["/c"], 1) == (cover("/c"), ())
    assert inflight_regions(star, ["/a", "/c"], 2) == (cover("/c"), region)
    # The root in flight: everything but the deeper rows' subtrees.
    whole = subtract(FULL, cover_all(("/a", "/c")))
    assert inflight_regions(star, ["/"], 1) == (whole, ())
    assert inflight_regions(star, ["/"], 2) == ((), whole)
    # Nested pending rows each own their region; a row with no children owns its cover.
    assert inflight_regions(star, ["/a", "/a/b"], 2) == (cover("/a/b"), region)
    assert inflight_regions(star, [], 1) == ((), ())


# ---------------------------------------------------------------------------
# Rights as path pieces
# ---------------------------------------------------------------------------


def test_a_prefix_is_its_own_path_and_an_open_range_beneath() -> None:
    assert pieces(cover("/a")) == Pieces(("/a",), (("/a/", "/a0"),))
    assert pieces(FULL) == Pieces((ROOT,), ((ROOT, "0"),))
    assert pieces(()) == Pieces((), ())


def test_a_hole_is_cut_and_its_siblings_stay() -> None:
    found = pieces(subtract(cover("/a"), cover("/a/b")))
    assert found == Pieces(("/a", "/a/b0"), (("/a/", "/a/b"), ("/a/b", "/a/b/"), ("/a/b0", "/a0")))
    assert _holds(found, "/a/b-c") and _holds(found, "/a/b0") and _holds(found, "/a/c")
    assert not _holds(found, "/a/b") and not _holds(found, "/a/b/x")


def test_sibling_prefixes_whose_subtrees_touch_ship_no_sentinel() -> None:
    # /v1's subtree ends exactly where the point /v10 begins, so the merged
    # span's upper bound carries the sentinel: it is the open range up to
    # /v10 plus the point /v10, never a bound ending in NUL.
    spans = union(cover("/v1"), cover("/v10"))
    assert spans == (("/v1", "/v1\x00"), ("/v1/", "/v10\x00"), ("/v10/", "/v100"))
    found = pieces(spans)
    assert found == Pieces(("/v1", "/v10"), (("/v1/", "/v10"), ("/v10/", "/v100")))
    _assert_well_formed(found, {"/v1", "/v10"})
    for path in ("/v1", "/v1/x", "/v10", "/v10/x", "/v1-x", "/v10-x"):
        assert _holds(found, path) is contains(spans, path)
    assert (
        _holds(found, "/v1/x") and _holds(found, "/v10") and not _holds(found, "/v100") and not _holds(found, "/v1-x")
    )


def test_the_ranges_are_computed_once() -> None:
    rights = resolve({"ann": frozenset()}, [GrantRow("ann", "/a", "read")], "read")
    assert rights.ranges() is rights.ranges()


# ---------------------------------------------------------------------------
# Rights shapes
# ---------------------------------------------------------------------------


def test_a_grant_on_the_root_resolves_to_the_whole_mount() -> None:
    rights = resolve({"ann": frozenset()}, [GrantRow("ann", "/", "read_write")], "read_write")
    assert rights.whole and rights == Rights.everything("read_write")
    assert rights.covers("/any/where") and rights.covers_subtree("/any") and rights.covers_subtree(ROOT)
    assert rights.roots == (ROOT,)


def test_the_whole_mount_is_semantic_not_one_row() -> None:
    # A group reads the root and ann reads /a on top: the grants together
    # admit every row, so the predicate is skipped.
    rows = [GrantRow("group:g", "/", "read"), GrantRow("ann", "/a", "read")]
    assert resolve({"ann": frozenset({"group:g"})}, rows, "read").whole


def test_nothing_is_empty_and_admits_only_by_the_everyone_level() -> None:
    rights = Rights.nothing("read")
    assert rights.empty
    assert not rights.admits("/a", None, 0)
    assert not rights.admits("/a", "ann", 0)
    assert rights.admits("/a", None, 1) and rights.admits("/a", None, 2)
    assert rights.reaches("/a", 1) and not rights.reaches("/a", 0)
    assert not rights.covers_subtree("/a")
    assert rights.roots == ()


def test_posture_rows_never_enter_the_compile() -> None:
    # The everyone rows live on the entry rows: a caller with no grant of
    # its own compiles to nothing, and each row's label decides for it.
    rows = [GrantRow("*", "/", "read_write"), GrantRow("*", "/a", "read"), GrantRow("*", "/a/b", "none")]
    rights = resolve({"ann": frozenset()}, rows, "read")
    assert rights.spans == () and rights.roots == () and not rights.whole
    assert rights.owner_arms == (OwnerArm("ann", (ROOT,)),)
    assert rights.admits("/a/x", None, 1) and not rights.admits("/a/b/x", None, 0)
    assert rights.need == 1 and resolve({"ann": frozenset()}, rows, "read_write").need == 2


def test_the_everyone_level_is_read_before_the_pieces() -> None:
    rights = resolve({"ann": frozenset()}, [GrantRow("ann", "/a", "read")], "read_write")
    assert not rights.admits("/a/x", None, 1) and rights.admits("/a/x", None, 2)
    assert not rights.admits("/z", None, 1) and rights.admits("/z", "ann", 0)


def test_roots_are_the_granted_prefixes_no_other_grant_covers() -> None:
    rows = [GrantRow("ann", "/a/b/c", "read"), GrantRow("ann", "/z", "read"), GrantRow("ann", "/a/b/c/d", "read")]
    rights = resolve({"ann": frozenset()}, rows, "read")
    assert rights.roots == ("/a/b/c", "/z")
    assert rights.spans == cover_all(("/a/b/c", "/z"))


def test_owner_arms_are_per_member_and_trimmed_by_the_shared_prefixes() -> None:
    rows = [GrantRow("bob", "/hr", "read"), GrantRow("ann", "/pub", "read"), GrantRow("bob", "/pub", "read")]
    rights = resolve({"ann": frozenset(), "bob": frozenset()}, rows, "read")
    # ann's own row under /hr passes (bob reads /hr); under /pub the shared prefix already covers it.
    assert rights.owner_arms == (OwnerArm("ann", ("/hr",)),)
    assert rights.admits("/hr/case.md", "ann", 0)
    assert not rights.admits("/hr/case.md", "bob", 0)
    assert rights.roots == ("/pub",)


def test_an_owner_arm_never_names_a_row_the_spans_do() -> None:
    # ann's floor is the whole mount less /pub, which both already read:
    # the owner branch and the range branch stay disjoint by construction.
    rows = [GrantRow("ann", "/pub", "read"), GrantRow("bob", "/", "read")]
    rights = resolve({"ann": frozenset(), "bob": frozenset()}, rows, "read")
    assert rights.owner_arms == (OwnerArm("ann", (ROOT,)),)
    assert rights.ranges().owners[0][1] == pieces(subtract(FULL, cover("/pub")))


def test_a_lone_member_owns_everywhere_the_shared_prefixes_do_not_reach() -> None:
    rights = resolve({"ann": frozenset()}, [GrantRow("ann", "/pub", "read")], "read")
    assert rights.owner_arms == (OwnerArm("ann", (ROOT,)),)
    assert rights.admits("/hr/case.md", "ann", 0) and not rights.admits("/hr/case.md", None, 0)


def test_a_pending_narrowing_is_a_hole_the_label_cannot_fill() -> None:
    rows = [GrantRow("*", "/", "read"), GrantRow("*", "/a", "none"), GrantRow("*", "/a/b", "read")]
    rows += [GrantRow("ann", "/a/c", "read"), GrantRow("ann", "/z", "read")]
    rights = resolve({"ann": frozenset()}, rows, "read", pending={"/a"})
    assert rights.holes == subtract(cover("/a"), cover("/a/b"))
    assert rights.spans == cover_all(("/a/c", "/z")) and rights.roots == ("/a/c", "/z")
    # A stale label inside the hole admits nothing; the grant and the owner floor still do.
    assert not rights.admits("/a/x", None, 1) and rights.admits("/a/c/x", None, 1)
    assert rights.admits("/a/x", "ann", 0) and not rights.admits("/a/x", "bob", 1)
    # Beneath the deeper posture row and outside the region the label is the truth.
    assert rights.admits("/a/b/x", None, 1) and rights.admits("/q", None, 1) and not rights.admits("/q", None, 0)
    # A creation is judged by the posture rows, so ``reaches`` keeps no hole.
    assert not rights.reaches("/a/x", 0) and rights.reaches("/a/x", 1)
    found = rights.ranges()
    assert found.holes == pieces(rights.holes)
    assert found.holed_arms == pieces(cover("/a/c"))
    assert found.holed_owners == (("ann", pieces(subtract(cover("/a"), cover_all(("/a/b", "/a/c"))))),)


def test_a_pending_widening_joins_the_spans_and_the_roots() -> None:
    rows = [GrantRow("*", "/", "none"), GrantRow("*", "/a", "read_write"), GrantRow("*", "/a/b", "none")]
    rights = resolve({"ann": frozenset()}, rows, "read", pending={"/a"})
    assert rights.holes == () and rights.spans == subtract(cover("/a"), cover("/a/b")) and rights.roots == ("/a",)
    assert rights.admits("/a/x", None, 0) and not rights.admits("/a/b/x", None, 0) and not rights.admits("/q", None, 0)
    assert rights.ranges().holed_arms == Pieces((), ()) and rights.ranges().holed_owners == ()
    # The root widening with nothing beneath it is the whole mount.
    whole = resolve({"ann": frozenset()}, [GrantRow("*", "/", "read")], "read", pending={"/"})
    assert whole.whole and whole.holes == ()
    # Settled rows never enter: without ``pending`` the same rows compile to nothing.
    assert resolve({"ann": frozenset()}, rows, "read").spans == ()


def test_three_members_each_get_the_meet_of_the_other_two() -> None:
    rows = [GrantRow("u1", "/a", "read"), GrantRow("u2", "/a/b", "read")]
    rows += [GrantRow("u3", "/a/b/c", "read"), GrantRow("u3", "/z", "read")]
    rights = resolve({"u1": frozenset(), "u2": frozenset(), "u3": frozenset()}, rows, "read")
    assert rights.spans == cover("/a/b/c")
    assert rights.owner_arms == (OwnerArm("u3", ("/a/b",)),)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _holds(found: Pieces, path: str) -> bool:
    return path in found.points or any(lo < path < hi for lo, hi in found.opens)


def _deeper(star: list[GrantRow], prefix: str) -> list[str]:
    return [row.path_prefix for row in star if row.path_prefix != prefix and covers(prefix, row.path_prefix)]


def _assert_well_formed(found: Pieces, prefixes: set[str]) -> None:
    """Sorted, disjoint, and every bound ``/``, ``0``, or a stored prefix ``p``, ``p/`` or ``p0``."""
    assert list(found.points) == sorted(set(found.points))
    assert all(lo < hi for lo, hi in found.opens)
    assert all(left[1] <= right[0] for left, right in pairwise(found.opens))
    assert not any(any(lo < point < hi for lo, hi in found.opens) for point in found.points)
    bounds = [*found.points, *(b for pair in found.opens for b in pair)]
    allowed = {ROOT, "0"} | prefixes | {p + "/" for p in prefixes} | {p + "0" for p in prefixes}
    assert all(bound in allowed for bound in bounds), bounds
    assert not any("\x00" in bound for bound in bounds)
    assert not any(bound[-1] < " " for bound in bounds)
