"""Row grants — the levels, the rows, and the resolver's range algebra.

A grant row says *principal holds level at and below path_prefix*. Rows
only widen: there is no deny row, and a subject's level on a path is the
maximum over every row that covers it — its own, its groups', and the
everyone rows (principal ``*``) that carry a mount's posture. A subject
set holds a right only when every member does, so the set's coverage is
the meet (intersection) of the members' coverage, computed per member
first and never over a pooled bag of everyone's groups.

The everyone rows never enter a caller's compiled rights. What everyone
holds at a path — the deepest covering posture row's level,
:func:`level_at` — is stored on the entry row itself, so a caller's
:class:`Rights` hold only its own prefixes and grow with its grants,
never with the number of other principals on the mount. The posture
rows are consulted here only to label rows (:func:`posture_regions`),
by the storage layer when a row is written, and for the one exception:
a posture row whose relabel has not settled compiles the old way
(:func:`inflight_regions`), as a cover or a hole over the rows it is
still rewriting, so a reader sees the new posture before the labels do.

Coverage travels as *range sets*: sorted, disjoint, half-open spans
``[lo, hi)`` over path strings in bytewise order. ``[p, p + "\\x00")`` is
exactly the path ``p``, because no lawful path holds NUL, and
``[p + "/", p + "0")`` is everything beneath it, because ``0`` is the byte
after ``/``. Every operation — the union within a member, the meet across
members, the owner floor, one row's lookup — is one pass or one bisect
over sorted input, so the cost follows the number of rows, never their
product. The sentinel never leaves this module: :func:`pieces` turns
spans into exact paths and open ranges whose bounds are ``/``, ``0``,
``p``, ``p/`` or ``p0`` for a stored prefix ``p``.

This module is the pure half of the enforcement spine: no I/O, no SQL.
The database backend reads the rows and the membership closures, hands
them to :func:`resolve`, and compiles the :class:`Rights` it gets back
into predicates; :meth:`Rights.admits` is the same decision in Python,
exact for any number of grants, and the authority every row passes.

    rows = [GrantRow("group:eng", "/eng", "read_write")]
    rights = resolve({"ann": frozenset({"group:eng"})}, rows, "read")
    rights.admits("/eng/spec.md", owner_id=None, everyone_level=0)   # True — a grant
    rights.admits("/pub/faq.md", owner_id=None, everyone_level=1)    # True — everyone reads there
    rights.admits("/hr/case.md", owner_id=None, everyone_level=0)    # False
    rights.admits("/hr/case.md", owner_id="ann", everyone_level=0)   # True — the owner floor
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, get_args

from vfs.authority import EVERYONE_NAME

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Module constants and shared types
# ---------------------------------------------------------------------------

GrantLevel = Literal["none", "read", "read_write"]
"""A rung on the ladder. ``none`` is stored only on everyone rows, where it
narrows a posture; a principal's row states a positive level."""

GRANT_LEVELS: Final[frozenset[str]] = frozenset(get_args(GrantLevel))

LEVEL_RANK: Final[dict[str, int]] = {"none": 0, "read": 1, "read_write": 2}
"""The ladder's order: ``none < read < read_write``."""

Posture = Literal["open", "shared", "private"]
"""What a mount gives everyone at a path: read and write, read, or nothing."""

POSTURE_LEVELS: Final[dict[str, GrantLevel]] = {"open": "read_write", "shared": "read", "private": "none"}

ROOT: Final = "/"

MAX_GROUP_DEPTH: Final = 8
"""The deepest group nesting a membership write may create; the read-side
walk refuses past it rather than truncating."""

Span = tuple[str, str]
"""A half-open span ``[lo, hi)`` of path strings, in bytewise order."""

RangeSet = tuple[Span, ...]
"""Spans sorted, disjoint and not touching — the normal form every operation keeps."""

# Appended to a path, the least string above it: no lawful path holds NUL,
# so ``[p, p + _NEXT)`` is exactly ``p``. Internal only — never a bound.
_NEXT: Final = "\x00"

FULL: Final[RangeSet] = ((ROOT, "0"),)
"""The whole mount: every lawful path starts with ``/``, and ``0`` is the byte above it."""


class GrantRow(NamedTuple):
    """One stored grant: *principal_id* holds *level* on *path_prefix* and below."""

    principal_id: str
    path_prefix: str
    level: GrantLevel


# ---------------------------------------------------------------------------
# Coverage and the prefix algebra
# ---------------------------------------------------------------------------


def covers(prefix: str, path: str) -> bool:
    """Whether *path* is *prefix* itself or lies beneath it."""
    return prefix == ROOT or path == prefix or path.startswith(prefix + "/")


def ancestors_and_self(path: str) -> list[str]:
    """*path*, its parent, and so on up to the root, deepest first."""
    out = [path]
    while path != ROOT:
        path = _parent(path)
        out.append(path)
    return out


def level_at(star: Mapping[str, GrantLevel], path: str) -> GrantLevel:
    """The everyone level at *path*: the deepest posture row covering it, ``none`` when none does.

    *star* maps each posture prefix to its level; only the ancestors of
    *path* (and *path* itself) are consulted, so a map holding exactly
    those rows answers as the whole table would.
    """
    for ancestor in ancestors_and_self(path):
        level = star.get(ancestor)
        if level is not None:
            return level
    return "none"


def tree_key(prefix: str) -> tuple[str, ...]:
    """The sort key of *tree order*: a prefix, then everything beneath it, then its next sibling.

    Plain string order puts ``/a-b`` between ``/a`` and ``/a/b``; comparing
    segment by segment keeps a subtree one contiguous run, which is what
    lets :func:`minimise` and :func:`meet` finish in one pass.
    """
    return () if prefix == ROOT else tuple(prefix.split("/")[1:])


def minimise(prefixes: Iterable[str]) -> tuple[str, ...]:
    """The smallest prefix set with the same coverage, in tree order: a prefix under another is dropped."""
    kept: list[str] = []
    for prefix in sorted(set(prefixes), key=tree_key):
        if not kept or not covers(kept[-1], prefix):
            kept.append(prefix)
    return tuple(kept)


def meet(left: Sequence[str], right: Sequence[str]) -> tuple[str, ...]:
    """The prefix set covering exactly what both *left* and *right* cover.

    Both are minimised and in tree order, so one merge decides: where one
    prefix covers the other the deeper is the meet there, and the shallower
    may still meet what follows; otherwise the earlier one has nothing in
    common with anything beyond and is passed.
    """
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
    acc: tuple[str, ...] = (ROOT,)
    for prefixes in sets:
        acc = meet(acc, prefixes)
    return acc


# ---------------------------------------------------------------------------
# Range sets
# ---------------------------------------------------------------------------


def cover(prefix: str) -> RangeSet:
    """*prefix* and everything beneath it: the exact path, then the open subtree.

    Two spans, because bytes below ``/`` (such as ``-``) sort between a
    prefix and its children: ``/a-b`` lies between ``/a`` and ``/a/``.
    """
    if prefix == ROOT:
        return FULL
    return ((prefix, prefix + _NEXT), (prefix + "/", prefix + "0"))


def cover_all(prefixes: Iterable[str]) -> RangeSet:
    """The union of every prefix's cover."""
    return normalise(span for prefix in prefixes for span in cover(prefix))


def normalise(spans: Iterable[Span]) -> RangeSet:
    """*spans* (each non-empty) sorted, with overlapping and touching spans joined."""
    out: list[Span] = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            if hi > out[-1][1]:
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return tuple(out)


def union(left: RangeSet, right: RangeSet) -> RangeSet:
    """Every path in either set; two sorted runs merge in one pass."""
    return normalise((*left, *right))


def subtract(keep: RangeSet, cut: RangeSet) -> RangeSet:
    """The parts of *keep* that no span of *cut* reaches — one two-pointer pass."""
    out: list[Span] = []
    j = 0
    for lo, hi in keep:
        while j < len(cut) and cut[j][1] <= lo:
            j += 1
        k = j
        while k < len(cut) and cut[k][0] < hi:
            cut_lo, cut_hi = cut[k]
            if cut_lo > lo:
                out.append((lo, cut_lo))
            lo = max(lo, cut_hi)
            if cut_hi >= hi:
                break
            k += 1
        if lo < hi:
            out.append((lo, hi))
    return tuple(out)


def intersect(left: RangeSet, right: RangeSet) -> RangeSet:
    """The paths in both sets — one two-pointer pass."""
    out: list[Span] = []
    i = j = 0
    while i < len(left) and j < len(right):
        lo = max(left[i][0], right[j][0])
        hi = min(left[i][1], right[j][1])
        if lo < hi:
            out.append((lo, hi))
        if left[i][1] < right[j][1]:
            i += 1
        else:
            j += 1
    return tuple(out)


def above(spans: RangeSet, path: str) -> RangeSet:
    """The part of *spans* strictly past *path*: every path at or before it removed.

    A relabel's cursor: ``path`` is the last path a chunk rewrote, and
    the next chunk starts from what this leaves.
    """
    return subtract(spans, ((ROOT, path + _NEXT),))


def through(spans: RangeSet, path: str) -> RangeSet:
    """The part of *spans* at or before *path* — what :func:`above` leaves out."""
    return intersect(spans, ((ROOT, path + _NEXT),))


def end(spans: RangeSet) -> str:
    """A path every path in the non-empty *spans* lies at or before, with no sentinel.

    The last upper bound: the path itself when the span runs through it,
    else the bound as it is — no lawful path sits between it and the
    span, so ``above(spans, end(spans))`` is empty.
    """
    assert spans, "an empty range set has no end"
    return spans[-1][1].removesuffix(_NEXT)


def contains(spans: RangeSet, path: str) -> bool:
    """Whether *path* lies in some span — one bisect.

    The last span whose ``lo <= path`` is the only candidate, and no
    string sits strictly between ``path`` and ``path + "\\x00"``, so a
    one-element tuple keys the search.
    """
    i = bisect_left(spans, (path + _NEXT,)) - 1
    return i >= 0 and spans[i][0] <= path < spans[i][1]


def posture_regions(star: Mapping[str, GrantLevel]) -> dict[GrantLevel, RangeSet]:
    """The paths each level holds everyone at: every posture row's cover minus its posture children's.

    Posture rows in tree order, the nearest posture parent found by a
    stack, so every row is a child of exactly one parent and the
    subtractions total one pass. A level no row carries maps to an
    empty set; paths no row covers are in no region (the level there is
    ``none``, as :func:`level_at` answers).
    """
    children = _posture_children(star)
    parts: dict[GrantLevel, list[Span]] = {level: [] for level in get_args(GrantLevel)}
    for prefix, below in children.items():
        parts[star[prefix]].extend(subtract(cover(prefix), cover_all(below)))
    return {level: normalise(spans) for level, spans in parts.items()}


def inflight_regions(star: Mapping[str, GrantLevel], pending: Iterable[str], need: int) -> tuple[RangeSet, RangeSet]:
    """What the posture rows still being relabelled add at rank *need*: ``(covers, holes)``.

    A pending row's region is its cover minus its posture children's —
    exactly the rows its relabel rewrites, whose stored labels cannot be
    trusted until it settles. A reader admits a region outright when the
    row's new level reaches *need* (a cover) and ignores the label inside
    it when the level does not (a hole); the deeper posture rows keep
    their own effect through their own labels. *star* holds every
    pending row and every posture row beneath one; the sets are sized by
    those rows, never by the mount.
    """
    children = _posture_children(star)
    covers: list[Span] = []
    holes: list[Span] = []
    for prefix in pending:
        region = subtract(cover(prefix), cover_all(children[prefix]))
        (covers if LEVEL_RANK[star[prefix]] >= need else holes).extend(region)
    return normalise(covers), normalise(holes)


# ---------------------------------------------------------------------------
# Resolved rights
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OwnerArm:
    """Rows *owner* owns that lie under one of *prefixes* — one member's owner floor."""

    owner: str
    prefixes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Rights:
    """What an authority holds at one level by its own grants: the covered spans plus per-member owner arms.

    ``spans`` is every path the authority's own rows reach outright;
    ``roots`` are the covered prefixes whose parent is not covered, so
    every row the grants reach lies beneath one of them or under an
    owner arm. What everyone holds is not here: it is read off each row
    as its ``everyone_level`` and compared with ``need``. ``whole``
    means the grants alone admit every row, so a caller may skip the
    predicate entirely. ``empty`` means the authority holds no grant of
    its own, and only the everyone level admits.

    ``holes`` are the regions whose stored labels cannot be trusted at
    this level while a posture row is being relabelled beneath them
    (:func:`inflight_regions`): a row inside one passes by the spans or
    the owner floor alone. The regions a relabel widens to this level
    are already in ``spans``. Both are empty except during a relabel.
    """

    level: GrantLevel
    spans: RangeSet = ()
    owner_arms: tuple[OwnerArm, ...] = ()
    roots: tuple[str, ...] = ()
    holes: RangeSet = ()
    _owned: dict[str, RangeSet] = field(init=False, repr=False, compare=False, hash=False)
    _ranges: Ranges | None = field(init=False, default=None, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        # Each owner arm less the spans: the owner branch never names a row the range branch does.
        owned = {arm.owner: subtract(cover_all(arm.prefixes), self.spans) for arm in self.owner_arms}
        object.__setattr__(self, "_owned", owned)

    @classmethod
    def everything(cls, level: GrantLevel) -> Rights:
        """Every row, at *level* — the system actor's rights and the open fast path."""
        return cls(level, FULL, roots=(ROOT,))

    @classmethod
    def nothing(cls, level: GrantLevel) -> Rights:
        """No row at all."""
        return cls(level)

    @property
    def need(self) -> int:
        """The rank a row's everyone level must reach to pass on its own."""
        return LEVEL_RANK[self.level]

    @property
    def whole(self) -> bool:
        return self.spans == FULL

    @property
    def empty(self) -> bool:
        return not self.spans and not self.owner_arms

    def covers(self, path: str) -> bool:
        """Whether the spans cover *path*."""
        return contains(self.spans, path)

    def reaches(self, path: str, everyone_level: int) -> bool:
        """Whether *path* passes by the everyone level there or by the spans — what a creation is judged by."""
        return everyone_level >= self.need or self.covers(path)

    def covers_subtree(self, path: str) -> bool:
        """Whether the spans cover *path* and everything beneath it, no gap inside."""
        return all(_contains_span(self.spans, lo, hi) for lo, hi in cover(path))

    def admits(self, path: str, owner_id: str | None, everyone_level: int) -> bool:
        """Whether the row at *path*, owned by *owner_id* and labelled *everyone_level*, passes — the one authority.

        *everyone_level* is the row's stored label: it decides unless the
        path lies in a hole, where only the spans and the owner floor do.
        """
        if everyone_level >= self.need and not contains(self.holes, path):
            return True
        if self.covers(path):
            return True
        if owner_id is None:
            return False
        owned = self._owned.get(owner_id)
        return owned is not None and contains(owned, path)

    def ranges(self) -> Ranges:
        """These rights as path pieces, computed once: the spans', each owner arm's by owner, and the holes'.

        Inside a hole the label is ignored, so the parts of the spans and
        of each owner arm that lie in one are carried separately: they
        admit a row whose label would otherwise have placed it in the
        everyone leg.
        """
        if self._ranges is None:
            owners = tuple((arm.owner, pieces(self._owned[arm.owner])) for arm in self.owner_arms)
            holed_owners = tuple(
                (arm.owner, pieces(intersect(self._owned[arm.owner], self.holes))) for arm in self.owner_arms
            )
            found = Ranges(
                pieces(self.spans),
                owners,
                pieces(self.holes),
                pieces(intersect(self.spans, self.holes)),
                tuple((owner, held) for owner, held in holed_owners if held.points or held.opens),
            )
            object.__setattr__(self, "_ranges", found)
        assert self._ranges is not None
        return self._ranges


# ---------------------------------------------------------------------------
# Rights as path pieces
# ---------------------------------------------------------------------------


class Pieces(NamedTuple):
    """Rows matched exactly (``path = p``) or strictly between two bounds (``lo < path < hi``).

    Sorted and disjoint, in bytewise order — which is code point order,
    the order UTF-8 preserves. Every bound is ``/``, ``0``, or a stored
    prefix ``p``, ``p/`` or ``p0``: never a path plus a low byte, which
    SQL Server would pad past and Postgres refuse.
    """

    points: tuple[str, ...]
    opens: tuple[tuple[str, str], ...]


class Ranges(NamedTuple):
    """One authority's rights as pieces: the spans', each member's owner arm's, and the holes'.

    ``holes`` is where the stored label is ignored; ``holed_arms`` and
    ``holed_owners`` are the spans' and each owner arm's parts inside
    it. All three are empty outside a relabel.
    """

    arms: Pieces
    owners: tuple[tuple[str, Pieces], ...]
    holes: Pieces = Pieces((), ())
    holed_arms: Pieces = Pieces((), ())
    holed_owners: tuple[tuple[str, Pieces], ...] = ()


def pieces(spans: RangeSet) -> Pieces:
    """*spans* as exact paths and open ranges, with no sentinel in any bound.

    Per span ``[lo, hi)``: ``hi == lo + "\\x00"`` is the exact path ``lo``.
    A lower bound ending in the sentinel is the path just above
    ``lo[:-1]``, so the open range starts (exclusively) at ``lo[:-1]``; a
    lawful ``lo`` is a point beside the open range; one ending in ``/``
    names no row, so it bounds the range as it is. An upper bound ending
    in the sentinel means the span runs *through* ``hi[:-1]``: the open
    range ends there and ``hi[:-1]`` is a point — a merge produces this
    edge whenever a subtree ends where its sibling begins (``/v1`` beside
    ``/v10``).

        pieces(subtract(cover("/a"), cover("/a/b")))
        # Pieces(points=('/a', '/a/b0'), opens=(('/a/', '/a/b'), ('/a/b', '/a/b/'), ('/a/b0', '/a0')))
    """
    points: list[str] = []
    opens: list[tuple[str, str]] = []
    for lo, hi in spans:
        if hi == lo + _NEXT:
            points.append(lo)
            continue
        low = lo.removesuffix(_NEXT)
        if low == lo and (lo == ROOT or not lo.endswith("/")):
            points.append(lo)
        high = hi.removesuffix(_NEXT)
        opens.append((low, high))
        if high != hi:
            points.append(high)
    return Pieces(tuple(points), tuple(opens))


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------


def resolve(
    closures: Mapping[str, frozenset[str]],
    rows: Sequence[GrantRow],
    level: GrantLevel,
    *,
    owner_floor: bool = True,
    pending: Iterable[str] = (),
) -> Rights:
    """An authority's rights at *level*, from its members' group closures and the rows.

    *closures* maps each subject's ``sub`` to every group it belongs to,
    directly or by nesting, and names at least one subject; *rows* holds
    every row that names a subject or one of their groups, keyed by
    ``(principal_id, path_prefix)``. Per member: the union of its own and
    its groups' rows at *level*, then the meet across members. The owner
    floor gives each member one owner arm — the other members' meet,
    trimmed to what the shared prefixes do not already cover;
    *owner_floor* is off for an authority that owns nothing (anonymous).

    An everyone row is ignored — the everyone level is read off each
    entry row instead — except at a prefix in *pending*, a posture row
    whose relabel has not settled: *rows* then also holds every everyone
    row beneath it, and the region it is rewriting joins the spans when
    its level reaches *level* and the holes otherwise
    (:func:`inflight_regions`).
    """
    assert closures, "an authority names at least one subject"
    need = LEVEL_RANK[level]
    by_principal: dict[str, list[str]] = {}
    star: dict[str, GrantLevel] = {}
    for row in rows:
        if row.principal_id == EVERYONE_NAME:
            star[row.path_prefix] = row.level
        elif LEVEL_RANK[row.level] >= need:
            by_principal.setdefault(row.principal_id, []).append(row.path_prefix)
    members = list(closures)
    covering = [minimise(p for pid in (sub, *closures[sub]) for p in by_principal.get(pid, ())) for sub in members]
    shared = meet_all(covering)
    unsettled = sorted(pending)
    covers, holes = inflight_regions(star, unsettled, need)
    spans = union(cover_all(shared), covers)
    if spans == FULL:
        return Rights.everything(level)
    owner_arms: list[OwnerArm] = []
    if owner_floor:
        for sub, rest in zip(members, _meet_all_but_each(covering), strict=True):
            trimmed = _uncovered(rest, shared)
            if trimmed:
                owner_arms.append(OwnerArm(sub, trimmed))
    widened = [prefix for prefix in unsettled if LEVEL_RANK[star[prefix]] >= need]
    return Rights(level, spans, tuple(owner_arms), _roots(spans, (*shared, *widened)), holes)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parent(path: str) -> str:
    return path.rsplit("/", 1)[0] or ROOT


def _posture_children(star: Mapping[str, GrantLevel]) -> dict[str, list[str]]:
    """Each posture prefix's nearest posture rows beneath it, the prefixes in tree order.

    A stack over the tree-ordered prefixes finds every row's nearest
    posture parent in one pass.
    """
    ordered = sorted(star, key=tree_key)
    children: dict[str, list[str]] = {prefix: [] for prefix in ordered}
    stack: list[str] = []
    for prefix in ordered:
        while stack and not covers(stack[-1], prefix):
            stack.pop()
        if stack:
            children[stack[-1]].append(prefix)
        stack.append(prefix)
    return children


def _contains_span(spans: RangeSet, lo: str, hi: str) -> bool:
    """Whether ``[lo, hi)`` lies whole inside one span."""
    i = bisect_left(spans, (lo + _NEXT,)) - 1
    return i >= 0 and spans[i][0] <= lo and hi <= spans[i][1]


def _meet_all_but_each(sets: Sequence[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """For each set, the meet of every other one — prefix and suffix meets, three per set."""
    before: list[tuple[str, ...]] = [(ROOT,)]
    for prefixes in sets[:-1]:
        before.append(meet(before[-1], prefixes))
    after: list[tuple[str, ...]] = [(ROOT,)]
    for prefixes in reversed(sets[1:]):
        after.append(meet(prefixes, after[-1]))
    return [meet(before[i], after[len(sets) - 1 - i]) for i in range(len(sets))]


def _uncovered(prefixes: Sequence[str], by: Sequence[str]) -> tuple[str, ...]:
    """The tree-ordered *prefixes* no prefix of the minimised, tree-ordered *by* covers."""
    out: list[str] = []
    j = -1
    for prefix in prefixes:
        key = tree_key(prefix)
        while j + 1 < len(by) and tree_key(by[j + 1]) <= key:
            j += 1
        if j < 0 or not covers(by[j], prefix):
            out.append(prefix)
    return tuple(out)


def _roots(spans: RangeSet, candidates: Iterable[str]) -> tuple[str, ...]:
    """The covered *candidates* whose parent is not covered, in tree order.

    A hidden directory with a visible row beneath it is a proper ancestor
    of one of these, so they are what the road is computed from.
    """
    return tuple(p for p in sorted(set(candidates), key=tree_key) if p == ROOT or not contains(spans, _parent(p)))
