"""A sorted-merge range algebra for grant resolution — the study's candidate.

Everything here is a pure function over sorted inputs. Three ideas:

1. A *range set* is a tuple of half-open spans ``[lo, hi)`` over path
   strings, sorted, disjoint and not touching. ``NEXT`` (``"\\x00"``) is the
   internal sentinel: ``[p, p + NEXT)`` is exactly the path ``p``, because
   no lawful path holds NUL. A sentinel never leaves this module in a
   bound: ``split_to_pieces`` strips it.
2. ``union``, ``intersect``, ``subtract`` and ``normalise`` are one linear
   pass over sorted input. ``union_many`` and ``normalise`` sort first,
   so the whole algebra is O(n log n).
3. Prefix sets (what a member is granted) are kept as prefixes, sorted in
   *tree order* — a prefix, then everything beneath it, then its next
   sibling — so ``minimise``, ``meet`` and ``uncovered`` are linear
   merges too. ``cover`` turns a prefix into its two spans.

``resolve_rights`` builds the shipped resolver's answer on these
primitives: the everyone region (deepest posture row wins), each member's
covering set, the meet across members, the shared arms and each member's
owner floor. ``RangeRights.admits`` is the pointwise decision.

This file imports nothing from ``vfs`` except the constants it must agree
with, so the parity harness can hold it against the shipped code.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, NamedTuple

NEXT: Final = "\x00"
ROOT: Final = "/"
EVERYONE: Final = "*"
LEVEL_RANK: Final[dict[str, int]] = {"none": 0, "read": 1, "read_write": 2}
FULL: Final = ((ROOT, "0"),)
"""The whole mount: every lawful path starts with ``/`` and ``0`` is the byte above it."""

Span = tuple[str, str]
RangeSet = tuple[Span, ...]


class Row(NamedTuple):
    principal_id: str
    path_prefix: str
    level: str


# ---------------------------------------------------------------------------
# Range sets
# ---------------------------------------------------------------------------


def cover(prefix: str) -> RangeSet:
    """*prefix* and everything beneath it, as spans: the point, then the open subtree."""
    if prefix == ROOT:
        return FULL
    return ((prefix, prefix + NEXT), (prefix + "/", prefix + "0"))


def normalise(spans: Iterable[Span]) -> RangeSet:
    """*spans* sorted, with overlapping and touching spans joined; empty spans dropped."""
    out: list[Span] = []
    for lo, hi in sorted(spans):
        if lo >= hi:
            continue
        if out and lo <= out[-1][1]:
            if hi > out[-1][1]:
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return tuple(out)


def union(a: RangeSet, b: RangeSet) -> RangeSet:
    """One merge pass over two normalised sets."""
    out: list[Span] = []
    i = j = 0
    while i < len(a) or j < len(b):
        if j >= len(b) or (i < len(a) and a[i] <= b[j]):
            lo, hi = a[i]
            i += 1
        else:
            lo, hi = b[j]
            j += 1
        if out and lo <= out[-1][1]:
            if hi > out[-1][1]:
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return tuple(out)


def union_many(sets: Iterable[RangeSet]) -> RangeSet:
    """The union of any number of sets: one sort, one merge pass."""
    return normalise(span for rs in sets for span in rs)


def intersect(a: RangeSet, b: RangeSet) -> RangeSet:
    """One two-pointer pass over two normalised sets."""
    out: list[Span] = []
    i = j = 0
    while i < len(a) and j < len(b):
        lo = max(a[i][0], b[j][0])
        hi = min(a[i][1], b[j][1])
        if lo < hi:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return tuple(out)


def subtract(keep: RangeSet, cut: RangeSet) -> RangeSet:
    """The parts of *keep* no span of *cut* reaches — one two-pointer pass."""
    out: list[Span] = []
    j = 0
    for lo, hi in keep:
        while j < len(cut) and cut[j][1] <= lo:
            j += 1
        k = j
        while k < len(cut) and cut[k][0] < hi:
            clo, chi = cut[k]
            if clo > lo:
                out.append((lo, clo))
            lo = max(lo, chi)
            if chi >= hi:
                break
            k += 1
        if lo < hi:
            out.append((lo, hi))
    return tuple(out)


def contains(rs: RangeSet, path: str) -> bool:
    """Whether *path* lies in some span.

    The last span whose ``lo <= path`` is the only candidate. No string
    sits strictly between ``path`` and ``path + NEXT``, so ``lo < path + NEXT``
    is exactly ``lo <= path``, and a one-element tuple keys the bisect.
    """
    i = bisect_left(rs, (path + NEXT,)) - 1
    return i >= 0 and rs[i][0] <= path < rs[i][1]


def subtree_contained(rs: RangeSet, path: str) -> bool:
    """Whether *path* and everything beneath it lies in *rs* — the ``covers_subtree`` question."""
    return all(_span_contained(rs, lo, hi) for lo, hi in cover(path))


def _span_contained(rs: RangeSet, lo: str, hi: str) -> bool:
    i = bisect_left(rs, (lo + NEXT,)) - 1
    return i >= 0 and rs[i][0] <= lo and hi <= rs[i][1]


# ---------------------------------------------------------------------------
# Pieces: what leaves for SQL
# ---------------------------------------------------------------------------


class Pieces(NamedTuple):
    points: tuple[str, ...]
    opens: tuple[tuple[str, str], ...]


def split_to_pieces(rs: RangeSet) -> Pieces:
    """Half-open spans as exact paths and open ranges, with no sentinel in any bound.

    Per span ``[lo, hi)``:
    - ``hi == lo + NEXT``: the exact path ``lo``.
    - lower bound: ``lo`` ending in ``NEXT`` is the path just above
      ``lo[:-1]``, so the open range starts (exclusively) at ``lo[:-1]``;
      a lawful ``lo`` is a point beside the open range; ``lo`` ending in
      ``/`` names no row, so it is an exclusive bound as it is.
    - upper bound: ``hi`` ending in ``NEXT`` means the span runs through
      the path ``hi[:-1]`` inclusive, so that path is a point and the
      open range ends (exclusively) at it. This is the sibling fix.
    """
    points: list[str] = []
    opens: list[tuple[str, str]] = []
    for lo, hi in rs:
        if hi == lo + NEXT:
            points.append(lo)
            continue
        if lo.endswith(NEXT):
            low = lo[:-1]
        else:
            low = lo
            if lo == ROOT or not lo.endswith("/"):
                points.append(lo)
        if hi.endswith(NEXT):
            high = hi[:-1]
            if low < high:
                opens.append((low, high))
            points.append(high)
        elif low < hi:
            opens.append((low, hi))
    return Pieces(tuple(points), tuple(opens))


def pieces_hold(found: Pieces, path: str) -> bool:
    """Pointwise reading of pieces, the way SQL would."""
    return path in found.points or any(lo < path < hi for lo, hi in found.opens)


# ---------------------------------------------------------------------------
# Prefix sets in tree order
# ---------------------------------------------------------------------------


def tree_key(prefix: str) -> tuple[str, ...]:
    """Sort key that lists a prefix, then its subtree, then its next sibling.

    Plain string order puts ``/a-b`` between ``/a`` and ``/a/b``; splitting on
    ``/`` compares segment by segment, so a subtree is one contiguous run.
    """
    return () if prefix == ROOT else tuple(prefix.split("/")[1:])


def covers(prefix: str, path: str) -> bool:
    return prefix == ROOT or path == prefix or path.startswith(prefix + "/")


def minimise(prefixes: Iterable[str]) -> tuple[str, ...]:
    """Tree-ordered prefixes, none under another — one pass after the sort."""
    kept: list[str] = []
    for prefix in sorted(set(prefixes), key=tree_key):
        if not kept or not covers(kept[-1], prefix):
            kept.append(prefix)
    return tuple(kept)


def meet(left: Sequence[str], right: Sequence[str]) -> tuple[str, ...]:
    """The prefixes covering exactly what both minimised, tree-ordered sets cover."""
    out: list[str] = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        if covers(a, b):
            out.append(b)
            j += 1
        elif covers(b, a):
            out.append(a)
            i += 1
        elif tree_key(a) < tree_key(b):
            i += 1
        else:
            j += 1
    return tuple(out)


def meet_all(sets: Sequence[Sequence[str]]) -> tuple[str, ...]:
    """The meet of every set; the meet of none is the whole mount."""
    if not sets:
        return (ROOT,)
    acc = tuple(sets[0])
    for other in sets[1:]:
        acc = meet(acc, other)
    return acc


def meet_all_but_each(sets: Sequence[Sequence[str]]) -> list[tuple[str, ...]]:
    """For each i, the meet of every set except the i-th — prefix and suffix meets, O(M·G)."""
    n = len(sets)
    before: list[tuple[str, ...] | None] = [None] * (n + 1)
    after: list[tuple[str, ...] | None] = [None] * (n + 1)
    for i in range(n):
        before[i + 1] = tuple(sets[i]) if before[i] is None else meet(before[i], sets[i])
    for i in range(n - 1, -1, -1):
        after[i] = tuple(sets[i]) if after[i + 1] is None else meet(sets[i], after[i + 1])
    out: list[tuple[str, ...]] = []
    for i in range(n):
        left, right = before[i], after[i + 1]
        if left is None and right is None:
            out.append((ROOT,))
        elif left is None:
            out.append(right)  # type: ignore[arg-type]
        elif right is None:
            out.append(left)
        else:
            out.append(meet(left, right))
    return out


def uncovered(prefixes: Sequence[str], by: Sequence[str]) -> tuple[str, ...]:
    """The tree-ordered *prefixes* that no prefix of minimised, tree-ordered *by* covers."""
    out: list[str] = []
    j = -1
    for p in prefixes:
        k = tree_key(p)
        while j + 1 < len(by) and tree_key(by[j + 1]) <= k:
            j += 1
        if j < 0 or not covers(by[j], p):
            out.append(p)
    return tuple(out)


def cover_all(prefixes: Iterable[str]) -> RangeSet:
    return union_many(cover(p) for p in prefixes)


# ---------------------------------------------------------------------------
# The everyone region
# ---------------------------------------------------------------------------


def everyone_region(star: Mapping[str, str], need: int) -> RangeSet:
    """Where the deepest covering posture row holds *need* or above.

    Each posture row owns the region of its subtree that no deeper posture
    row claims: its cover minus the covers of its nearest posture children.
    The admitted region is the union of the owned regions of qualifying
    rows. Children are found with a stack over tree order; every row is a
    child of exactly one parent, so the subtractions total O(n) spans.
    """
    ordered = sorted(star, key=tree_key)
    children: dict[str, list[str]] = {p: [] for p in ordered}
    stack: list[str] = []
    for p in ordered:
        while stack and not covers(stack[-1], p):
            stack.pop()
        if stack:
            children[stack[-1]].append(p)
        stack.append(p)
    regions: list[Span] = []
    for p in ordered:
        if LEVEL_RANK[star[p]] < need:
            continue
        cut = normalise(span for c in children[p] for span in cover(c))
        regions.extend(subtract(cover(p), cut))
    return normalise(regions)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RangeRights:
    """One authority's rights as range sets: the arms, and each member's owner floor."""

    level: str
    arms: RangeSet
    owners: Mapping[str, RangeSet]
    whole: bool
    shared: tuple[str, ...]
    owner_prefixes: Mapping[str, tuple[str, ...]]
    everyone: RangeSet

    def covers(self, path: str) -> bool:
        return self.whole or contains(self.arms, path)

    def covers_subtree(self, path: str) -> bool:
        return self.whole or subtree_contained(self.arms, path)

    def admits(self, path: str, owner_id: str | None) -> bool:
        if self.covers(path):
            return True
        if owner_id is None:
            return False
        owned = self.owners.get(owner_id)
        return owned is not None and contains(owned, path)

    def pieces(self) -> Pieces:
        return split_to_pieces(self.arms)

    def owner_pieces(self) -> dict[str, Pieces]:
        return {owner: split_to_pieces(rs) for owner, rs in self.owners.items()}


def resolve_rights(
    closures: Mapping[str, frozenset[str]],
    rows: Sequence[Row],
    level: str,
    *,
    owner_floor: bool = True,
) -> RangeRights:
    """The shipped resolver's answer, built on sorted merges.

    Steps, each a sort plus linear passes:
    1. everyone region E from the posture rows;
    2. per member, its covering prefixes (own + groups) minimised;
    3. the meet across members, as prefixes;
    4. arms = E ∪ cover(shared);
    5. owner floor per member: the meet of the *other* members, minus
       whatever shared already covers, as that member's owned region.
    """
    need = LEVEL_RANK[level]
    star = {row.path_prefix: row.level for row in rows if row.principal_id == EVERYONE}
    everyone = everyone_region(star, need)
    by_principal: dict[str, list[str]] = {}
    for row in rows:
        if row.principal_id != EVERYONE and LEVEL_RANK[row.level] >= need:
            by_principal.setdefault(row.principal_id, []).append(row.path_prefix)
    members = list(closures)
    covering = [minimise(p for pid in (*closures[sub], sub) for p in by_principal.get(pid, ())) for sub in members]
    shared = meet_all(covering)
    arms = union(everyone, cover_all(shared))
    whole = arms == FULL
    owners: dict[str, RangeSet] = {}
    owner_prefixes: dict[str, tuple[str, ...]] = {}
    if owner_floor and not whole:
        for sub, rest in zip(members, meet_all_but_each(covering), strict=True):
            trimmed = uncovered(rest, shared)
            if trimmed:
                owner_prefixes[sub] = trimmed
                owners[sub] = cover_all(trimmed)
    return RangeRights(level, arms, owners, whole, shared, owner_prefixes, everyone)
