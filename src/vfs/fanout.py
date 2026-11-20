"""The fan-out planner: a scoped call's roots, patterns and exclusions, planned entry by entry.

A fan-out that names scope roots, path-arm patterns or capability skips
is planned before it is dispatched. :func:`plan_scope` sends each root
strictly beneath its owning entry beside the uncomposed arms, as that
entry's scope channel, rewritten once into the entry's coordinates. Two
bounded kinds of root compose instead, each pattern joined under the
root and residuated into the entry's coordinates: a root whose joined
text must be read whole (an entry's own root, its trash view's head, a
live root above that head), and a root above a nested entry. The answer
is a :class:`ScopePlan` of plain data.

    plan = plan_scope(owners, keys, skip_paths, roots, patterns, exclusions, reach, literals, deadline)

The walk is pure: it reads no mount table, no router and no storage,
only the facts its caller resolved and the pattern text. So
:func:`planned_scope` runs it in place, or on a worker under a deadline,
as :func:`walks` says, and a test runs it with no router at all.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, NamedTuple

from vfs.deadline import CHECK_EVERY, WALL_TIME_BUDGET, Deadline
from vfs.offload import call_offloaded, offload_pool
from vfs.paths import ROOT, address_of
from vfs.pattern_matching import ScopeChannel, composed_pattern, escape_glob, render_residual, residuals

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from vfs.paths import Path


class ScopePlan(NamedTuple):
    """A fan-out's planned scope: what the residual walk derived, entry by entry.

    ``members`` maps each planned entry's bind path to its admissions in
    entry coordinates (``None``: unrestricted); an entry absent from it
    is not dispatched. ``exclusions`` holds the same entries' exclusion
    members, ``skips`` the capability-skip paths whose reach the walk
    found or could not determine, ``roots`` the scope roots planned
    whole, and ``completed`` whether the walk finished before its wall.
    ``scopes`` maps each entry owning a root strictly beneath its side to
    its scope channel: those roots in entry coordinates beside the
    uncomposed arms and exclusion arms.
    """

    members: dict[Path, set[str] | None]
    exclusions: dict[Path, set[str]]
    skips: frozenset[Path]
    roots: tuple[Path, ...]
    completed: bool
    scopes: dict[Path, ScopeChannel]


# ---------------------------------------------------------------------------
# The planning walk
# ---------------------------------------------------------------------------


def walks(
    roots: tuple[Path, ...], patterns: tuple[str, ...], exclusions: tuple[str, ...], skips: tuple[Path, ...]
) -> bool:
    """Whether planning residuates at all: a root, a path-arm pattern or a capability skip makes it."""
    return bool(roots or skips or any("/" in pattern for pattern in (*patterns, *exclusions)))


class _WallReached(Exception):  # noqa: N818 - a control-flow signal, not an error
    """A control-flow signal: the planning walk reached its wall; the stage stops there."""


class _Walk:
    """The planning walk's steps, its deadline read before every ``CHECK_EVERY``th one.

    A step is one residuation or one root rewritten into its entry's
    coordinates. The steps arrive one call at a time, never as a
    sequence to chunk, so the walk counts them and reads the deadline it
    holds: a plan that only rewrites roots is bounded as one that
    residuates is.
    """

    def __init__(self, deadline: Deadline) -> None:
        self._deadline = deadline
        self._count = 0

    def residuals(self, pattern: str, bind_path: Path) -> frozenset[tuple[str, ...]]:
        """:func:`~vfs.pattern_matching.residuals`, or :class:`_WallReached` past the deadline."""
        self._step()
        return residuals(pattern, bind_path)

    def rewritten(self, root: Path, key: Path) -> Path:
        """*root* in the coordinates of the entry bound at *key*, or :class:`_WallReached` past the deadline."""
        self._step()
        return root.without_mount(key)

    def _step(self) -> None:
        """Count one step, the deadline read before every ``CHECK_EVERY``th; :class:`_WallReached` once it passed."""
        if self._count % CHECK_EVERY == 0 and self._deadline.expired():
            raise _WallReached
        self._count += 1


def plan_scope(
    owners: Mapping[Path, Path],
    keys: Sequence[Path],
    skip_paths: Sequence[Path],
    roots: tuple[Path, ...],
    patterns: tuple[str, ...],
    exclusions: tuple[str, ...],
    reach: tuple[str, ...],
    literals: frozenset[Path],
    deadline: Deadline,
) -> ScopePlan:
    """A fan-out's residual walk: every capable entry's members, as plain data in and out.

    A pure function of the mount-table facts the router resolved on the
    loop (*owners* maps each scope root to its owning entry's bind path,
    *keys* are the capable entries' bind paths, *skip_paths* the
    capability skips') and the pattern text, so it runs on a worker.
    A root strictly beneath its owning entry's side rides that entry's
    scope channel beside the uncomposed *patterns* and *exclusions*,
    rewritten once into its coordinates; a root in *literals* also rides
    the entry as its own literal path. With no root, name arms copy
    verbatim, path arms residuate, and no *patterns* at all is
    unrestricted. A skip is kept where some *reach* pattern can reach
    its entry's rows.

    Two kinds of root compose instead, each arm joined under the root
    and residuated into every entry it reaches, and both are bounded. A
    root whose joined text must be read whole: an entry's own root or
    its trash view's head, which address a whole side, and a live root
    above that head, whose text with an arm can enter the view (at most
    three an entry). And a root above a nested entry (at most its bind
    depth). So a root and an arm mean what their joined text means as
    one pattern, however many roots the call names, and the plan's cost
    is linear in the roots. A root's literal, under *literals*, stays on
    the entry-wide channel, one per root.

    The deadline is read before every ``CHECK_EVERY``th step, a
    residuation or a root's rewrite, inside a root as well as between
    roots (between entries when there is no root), so the walk overruns
    its wall by at most that many steps. A root, or
    with no root an entry, whose walk is stopped is dropped from the
    plan whole, its exclusions with it, and every skip not yet decided
    is kept: a coverage record never hides. Pure Python on its worker,
    the walk holds the GIL in turns, and the loop serves between them;
    the native residual walk is the direction.
    """
    walk = _Walk(deadline)
    members: dict[Path, set[str] | None] = {key: set() for key in keys} if roots else {}
    excluded: dict[Path, set[str]] = {key: set() for key in keys} if roots else {}
    channeled: dict[Path, list[Path]] = {key: [] for key in keys}
    planned: list[Path] = []
    kept: set[Path] = set()
    decided = 0
    try:
        if roots:
            for root in roots:
                staged: dict[Path, tuple[set[str], set[str], Path | None]] = {}
                for key in keys:
                    if key != owners[root] and not _path_covers(root, key):
                        continue
                    if key == owners[root] and not _composes_whole(root, key):
                        literal = _root_literal(root, key, literals, walk)
                        staged[key] = (literal, set(), walk.rewritten(root, key))
                        continue
                    admitted, refused = _root_members(root, key, owners, patterns, exclusions, literals, walk)
                    staged[key] = (admitted, refused, None)
                for key, (admitted, refused, rel) in staged.items():
                    entry_members = members[key]
                    assert entry_members is not None
                    entry_members.update(admitted)
                    excluded[key].update(refused)
                    if rel is not None:
                        channeled[key].append(rel)
                planned.append(root)
        else:
            for key in keys:
                admitted = _composed_members(key, (), owners, patterns, walk) if patterns else None
                refused = _composed_members(key, (), owners, exclusions, walk)
                members[key], excluded[key] = admitted, refused
        for path in skip_paths:
            if any(_glob_reaches(path, roots or (ROOT,), pattern, walk) for pattern in reach):
                kept.add(path)
            decided += 1
    except _WallReached:
        kept.update(skip_paths[decided:])
        scopes = _scope_channels(channeled, patterns, exclusions)
        return ScopePlan(members, excluded, frozenset(kept), tuple(planned), completed=False, scopes=scopes)
    scopes = _scope_channels(channeled, patterns, exclusions)
    return ScopePlan(members, excluded, frozenset(kept), tuple(planned), completed=True, scopes=scopes)


async def planned_scope(
    owners: dict[Path, Path],
    keys: tuple[Path, ...],
    skip_paths: tuple[Path, ...],
    roots: tuple[Path, ...],
    patterns: tuple[str, ...],
    exclusions: tuple[str, ...],
    reach: tuple[str, ...],
    literals: frozenset[Path],
) -> ScopePlan:
    """Return the plan of which patterns each mount receives.

    A call with no root, no path arm and no skipped mount only copies its name arms to each mount.
    That costs one step for each arm, so it is planned in place. Every other plan is worked out in
    one hop to the process pool, within the time budget.
    """
    if not walks(roots, patterns, exclusions, skip_paths):
        return plan_scope(owners, keys, skip_paths, roots, patterns, exclusions, reach, literals, Deadline.never())
    deadline = Deadline.after(WALL_TIME_BUDGET)
    walk = partial(plan_scope, owners, keys, skip_paths, roots, patterns, exclusions, reach, literals, deadline)
    return await call_offloaded(offload_pool(), walk)


def scope_argument(plan: ScopePlan, key: Path) -> dict[str, ScopeChannel]:
    """Return the ``scope=`` argument for the call to one mount, or nothing when no root lies beneath it."""
    channel = plan.scopes.get(key)
    return {} if channel is None else {"scope": channel}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _path_covers(ancestor: Path, descendant: Path) -> bool:
    """Whether *descendant* sits at or beneath *ancestor* in the namespace."""
    if ancestor in (descendant, ROOT):
        return True
    return str(descendant).startswith(str(ancestor) + "/")


def _composes_whole(root: Path, key: Path) -> bool:
    """Whether *root*, owned by the entry bound at *key*, must compose with each arm instead of riding the scope.

    True when the trash view's head lies at or beneath the root in its
    entry's coordinates: the entry's root and the head itself address a
    whole side and leave no remainder to judge an arm against, and the
    text of a live root above the head, joined with an arm, can enter
    the view. Storage refuses the same roots on the scope by the same
    test, so the planner never sends one there.
    """
    return address_of(str(root.without_mount(key))).holds_trash_head


def _root_literal(root: Path, key: Path, literals: frozenset[Path], walk: _Walk) -> set[str]:
    """A root in *literals* as its own literal path in its owning entry's coordinates; nothing otherwise."""
    if root not in literals:
        return set()
    return set(_residual_renders(escape_glob(str(root)), key, walk))


def _scope_channels(
    channeled: Mapping[Path, list[Path]], patterns: tuple[str, ...], exclusions: tuple[str, ...]
) -> dict[Path, ScopeChannel]:
    """Each entry's scope channel, where it owns a planned root: those roots beside the call's uncomposed arms."""
    return {
        key: ScopeChannel(roots=tuple(dict.fromkeys(rels)), arms=patterns, arms_not=exclusions)
        for key, rels in channeled.items()
        if rels
    }


def _root_members(
    root: Path,
    key: Path,
    owners: Mapping[Path, Path],
    patterns: tuple[str, ...],
    exclusions: tuple[str, ...],
    literals: frozenset[Path],
    walk: _Walk,
) -> tuple[set[str], set[str]]:
    """One root's admissions and exclusions in one entry's coordinates, its literal path included."""
    admitted = _composed_members(key, (root,), owners, patterns, walk)
    if owners[root] == key:
        admitted.update(_root_literal(root, key, literals, walk))
    return admitted, _composed_members(key, (root,), owners, exclusions, walk)


def _composed_members(
    key: Path, roots: tuple[Path, ...], owners: Mapping[Path, Path], patterns: tuple[str, ...], walk: _Walk
) -> set[str]:
    """Entry-local renders of *patterns* under the call's scope shape.

    Unscoped: name-arm patterns broadcast verbatim (coordinate-free),
    path-arm patterns residuate against the bind path. Scoped: each
    pattern composes under each root reaching this entry, then
    residuates; a dead residual set simply contributes nothing.
    """
    members: set[str] = set()
    if not roots:
        for pattern in patterns:
            if "/" not in pattern:
                members.add(pattern)
            else:
                members.update(_residual_renders(pattern, key, walk))
        return members
    for root in roots:
        if key != owners[root] and not _path_covers(root, key):
            continue
        for pattern in patterns:
            members.update(_residual_renders(composed_pattern(root, pattern), key, walk))
    return members


def _residual_renders(pattern: str, bind_path: Path, walk: _Walk) -> list[str]:
    """Sorted entry-local renders of the pattern's live residuals.

    Empty-tuple residuals are dropped: the row at a mount point is the
    router's to return, from one stat of the mounted root, and never a
    pattern sent to the mount.
    """
    return sorted(render_residual(components) for components in walk.residuals(pattern, bind_path) if components)


def _glob_reaches(bind_path: Path, roots: tuple[Path, ...], pattern: str, walk: _Walk) -> bool:
    """Whether any scope root lets the pattern reach rows of this entry."""
    if any(_path_covers(bind_path, root) for root in roots):
        return True  # a root inside the entry names rows the entry holds
    return any(
        components for root in roots for components in walk.residuals(composed_pattern(root, pattern), bind_path)
    )
