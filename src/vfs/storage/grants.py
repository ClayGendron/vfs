"""Row grants — the levels, the rows, and the resolver's prefix algebra.

A grant row says *principal holds level at and below path_prefix*. Rows
only widen: there is no deny row, and a subject's level on a path is the
maximum over every row that covers it — its own, its groups', and the
everyone rows (principal ``*``) that carry a mount's posture. A subject
set holds a right only when every member does, so the set's coverage is
the meet (intersection) of the members' coverage, computed per member
first and never over a pooled bag of everyone's groups.

This module is the pure half of the enforcement spine: no I/O, no SQL.
The database backend reads the rows and the membership closures, hands
them to :func:`resolve`, and compiles the :class:`Rights` it gets back
into predicates; :meth:`Rights.admits` is the same decision in Python,
exact for any number of arms, and the authority every row passes.

    rows = [GrantRow("*", "/", "none"), GrantRow("group:eng", "/eng", "read_write")]
    rights = resolve({"ann": frozenset({"group:eng"})}, rows, "read")
    rights.admits("/eng/spec.md", owner_id=None)      # True
    rights.admits("/hr/case.md", owner_id=None)       # False
    rights.admits("/hr/case.md", owner_id="ann")      # True — the owner floor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import reduce
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
        path = path.rsplit("/", 1)[0] or ROOT
        out.append(path)
    return out


def minimise(prefixes: Iterable[str]) -> tuple[str, ...]:
    """The smallest prefix set with the same coverage: a prefix under another is dropped."""
    kept: set[str] = set()
    for prefix in sorted(set(prefixes), key=_depth):
        if not any(ancestor in kept for ancestor in ancestors_and_self(prefix)):
            kept.add(prefix)
    return tuple(sorted(kept))


def meet(left: Sequence[str], right: Sequence[str]) -> tuple[str, ...]:
    """The prefix set covering exactly what both *left* and *right* cover."""
    out = {b if covers(a, b) else a for a in left for b in right if covers(a, b) or covers(b, a)}
    return minimise(out)


def meet_all(sets: Sequence[Sequence[str]]) -> tuple[str, ...]:
    """The meet of every set; the meet of none is the whole mount."""
    return reduce(meet, sets[1:], tuple(sets[0])) if sets else (ROOT,)


# ---------------------------------------------------------------------------
# Resolved rights
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Arm:
    """Rows at or below *prefix*, except those at or below any of *holes*."""

    prefix: str
    holes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OwnerArm:
    """Rows *owner* owns that lie under one of *prefixes* — one member's owner floor."""

    owner: str
    prefixes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Rights:
    """What an authority holds at one level: arms plus per-member owner arms.

    ``whole`` means every row is admitted, so a caller may skip the
    predicate entirely — the fast path the default open posture takes.
    ``arms`` and ``owner_arms`` are empty when nothing is admitted.
    """

    level: GrantLevel
    arms: tuple[Arm, ...] = ()
    owner_arms: tuple[OwnerArm, ...] = ()
    whole: bool = False
    _by_prefix: dict[str, Arm] = field(init=False, repr=False, compare=False, hash=False)
    _owned: dict[str, frozenset[str]] = field(init=False, repr=False, compare=False, hash=False)
    _ranges: Ranges | None = field(init=False, default=None, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_prefix", {arm.prefix: arm for arm in self.arms})
        owned: dict[str, set[str]] = {}
        for arm in self.owner_arms:
            owned.setdefault(arm.owner, set()).update(arm.prefixes)
        object.__setattr__(self, "_owned", {owner: frozenset(ps) for owner, ps in owned.items()})

    @classmethod
    def everything(cls, level: GrantLevel) -> Rights:
        """Every row, at *level* — the system actor's rights and the open fast path."""
        return cls(level, (Arm(ROOT),), whole=True)

    @classmethod
    def nothing(cls, level: GrantLevel) -> Rights:
        """No row at all."""
        return cls(level)

    @property
    def empty(self) -> bool:
        return not self.arms and not self.owner_arms

    def covers(self, path: str) -> bool:
        """Whether an arm covers *path* — the rows a creation there would be visible by."""
        if self.whole:
            return True
        chain = ancestors_and_self(path)
        return any((arm := self._by_prefix.get(ancestor)) is not None and not _holed(arm, chain) for ancestor in chain)

    def covers_subtree(self, path: str) -> bool:
        """Whether one arm covers *path* and everything beneath it, no hole inside."""
        if self.whole:
            return True
        return any(
            (arm := self._by_prefix.get(ancestor)) is not None
            and not any(covers(hole, path) or covers(path, hole) for hole in arm.holes)
            for ancestor in ancestors_and_self(path)
        )

    def admits(self, path: str, owner_id: str | None) -> bool:
        """Whether the row at *path* owned by *owner_id* passes — the one authority."""
        if self.covers(path):
            return True
        if owner_id is None:
            return False
        prefixes = self._owned.get(owner_id)
        return prefixes is not None and any(ancestor in prefixes for ancestor in ancestors_and_self(path))

    def roots(self) -> tuple[str, ...]:
        """The arm prefixes: every visible row lies under one, or under an owner arm."""
        return tuple(self._by_prefix)

    def ranges(self) -> Ranges:
        """These rights as path pieces, computed once: the arms, and each owner arm by owner."""
        if self._ranges is None:
            owners = tuple((arm.owner, pieces(Arm(prefix) for prefix in arm.prefixes)) for arm in self.owner_arms)
            object.__setattr__(self, "_ranges", Ranges(pieces(self.arms), owners))
        assert self._ranges is not None
        return self._ranges


# ---------------------------------------------------------------------------
# Rights as path pieces
# ---------------------------------------------------------------------------


class Pieces(NamedTuple):
    """Rows matched exactly (``path = p``) or strictly between two bounds (``lo < path < hi``).

    Sorted and disjoint, in bytewise order — which is code point order,
    the order UTF-8 preserves. No bound is a path plus a low byte: SQL
    Server pads the shorter string with spaces before it compares.
    """

    points: tuple[str, ...]
    opens: tuple[tuple[str, str], ...]


class Ranges(NamedTuple):
    """One authority's rights as pieces: the arms', and each member's owner arm's."""

    arms: Pieces
    owners: tuple[tuple[str, Pieces], ...]


# Appended to a path, the least string above it: no lawful path holds NUL,
# so ``[p, p + _NEXT)`` is exactly ``p``. Internal only — never a bound.
_NEXT: Final = "\x00"


def pieces(arms: Iterable[Arm]) -> Pieces:
    """The rows *arms* admit, as sorted, disjoint exact paths and open ranges.

    A prefix is itself plus everything strictly between ``p/`` and
    ``p0`` — two pieces, because ``/a-b`` sorts between ``/a`` and
    ``/a/``. Holes are cut from their arm; arms then merge.

        pieces([Arm("/a", ("/a/b",))])
        # Pieces(points=('/a', '/a/b0'), opens=(('/a/', '/a/b'), ('/a/b', '/a/b/'), ('/a/b0', '/a0')))
    """
    spans: list[tuple[str, str]] = []
    for arm in arms:
        spans += _subtract(_spans(arm.prefix), [span for hole in arm.holes for span in _spans(hole)])
    return _split(_merged(spans))


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------


def resolve(
    closures: Mapping[str, frozenset[str]],
    rows: Sequence[GrantRow],
    level: GrantLevel,
    *,
    owner_floor: bool = True,
) -> Rights:
    """An authority's rights at *level*, from its members' group closures and the rows.

    *closures* maps each subject's ``sub`` to every group it belongs to,
    directly or by nesting; *rows* holds every row that names a subject,
    one of their groups, or everyone. Per member: the union of its own
    and its groups' rows at *level*, then the meet across members. The
    everyone rows are the same for every member, so they compile once
    beside the meet. The owner floor gives each member one owner arm,
    trimmed to what the shared arms do not already cover; *owner_floor*
    is off for an authority that owns nothing (anonymous).
    """
    need = LEVEL_RANK[level]
    star = {row.path_prefix: row.level for row in rows if row.principal_id == EVERYONE_NAME}
    everyone = _everyone_arms(star, need)
    named = [row for row in rows if row.principal_id != EVERYONE_NAME and LEVEL_RANK[row.level] >= need]
    covering = {
        sub: minimise(row.path_prefix for row in named if row.principal_id in (groups | {sub}))
        for sub, groups in closures.items()
    }
    shared = meet_all(list(covering.values()))
    arms = [*everyone, *(Arm(prefix) for prefix in shared if not _already(everyone, Arm(prefix)))]
    if any(arm.prefix == ROOT and not arm.holes for arm in arms):
        return Rights.everything(level)
    owner_arms: list[OwnerArm] = []
    if owner_floor:
        for sub in closures:
            rest = meet_all([covering[other] for other in closures if other != sub])
            trimmed = tuple(p for p in rest if not any(covers(q, p) for q in shared))
            if trimmed:
                owner_arms.append(OwnerArm(sub, trimmed))
    return Rights(level, tuple(arms), tuple(owner_arms))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _depth(prefix: str) -> tuple[int, str]:
    return (0 if prefix == ROOT else prefix.count("/"), prefix)


def _holed(arm: Arm, chain: Sequence[str]) -> bool:
    """Whether a hole of *arm* covers the path whose ancestor chain is *chain*."""
    return bool(arm.holes) and any(ancestor in arm.holes for ancestor in chain)


def _everyone_arms(star: Mapping[str, str], need: int) -> list[Arm]:
    """The posture rows at *need* or above, each minus every lower everyone row beneath it.

    Every lower row cuts, not only the nearest: under an open root, a
    shared ``/a`` holding a private ``/a/b`` must still cut ``/a/b`` from
    the root's arm. An arm already inside a qualifying ancestor arm with
    admitting all it admits adds nothing and is dropped.
    """
    qualifying = sorted((p for p, lvl in star.items() if LEVEL_RANK[lvl] >= need), key=_depth)
    arms: list[Arm] = []
    for prefix in qualifying:
        below = [q for q in star if q != prefix and covers(prefix, q) and LEVEL_RANK[star[q]] < need]
        arm = Arm(prefix, minimise(below))
        if not _already(arms, arm):
            arms.append(arm)
    return arms


def _already(arms: Sequence[Arm], candidate: Arm) -> bool:
    """Whether an arm in *arms* already admits every row *candidate* admits.

    It must cover the candidate's prefix through no hole, and each of its
    holes beneath that prefix must sit inside one of the candidate's own.
    """
    for arm in arms:
        if not covers(arm.prefix, candidate.prefix) or any(covers(hole, candidate.prefix) for hole in arm.holes):
            continue
        inner = [hole for hole in arm.holes if covers(candidate.prefix, hole)]
        if all(any(covers(own, hole) for own in candidate.holes) for hole in inner):
            return True
    return False


def _spans(prefix: str) -> list[tuple[str, str]]:
    """*prefix* and everything beneath it as half-open ``[lo, hi)`` spans."""
    if prefix == ROOT:
        return [(ROOT, "0")]
    return [(prefix, prefix + _NEXT), (prefix + "/", prefix + "0")]


def _merged(spans: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """*spans* sorted, with overlapping and touching spans joined."""
    out: list[tuple[str, str]] = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(hi, out[-1][1]))
        else:
            out.append((lo, hi))
    return out


def _subtract(keep: Iterable[tuple[str, str]], cut: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """The parts of *keep* that no span of *cut* reaches, in order."""
    out = _merged(keep)
    for cut_lo, cut_hi in _merged(cut):
        kept: list[tuple[str, str]] = []
        for lo, hi in out:
            if cut_hi <= lo or cut_lo >= hi:
                kept.append((lo, hi))
            else:
                kept += [(a, b) for a, b in ((lo, cut_lo), (cut_hi, hi)) if a < b]
        out = kept
    return out


def _split(spans: Sequence[tuple[str, str]]) -> Pieces:
    """Half-open spans as exact paths and open ranges, no bound ending in ``_NEXT``.

    A span that ends in ``_NEXT`` is one exact path: the gap just above a
    path is never cut, so a wider span always runs past it. An inclusive
    lower bound that is a lawful path becomes an exact path beside the
    open range; one ending in ``/`` never names a row, so it bounds the
    open range as it is.
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
        opens.append((low, hi))
    return Pieces(tuple(points), tuple(opens))
