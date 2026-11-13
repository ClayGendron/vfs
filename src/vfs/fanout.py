"""The fan-out planner: a scoped call's roots, patterns and exclusions, planned entry by entry.

A fan-out that names scope roots, path-arm patterns or capability skips
is planned before it is dispatched. :func:`plan_scope` composes each
pattern under each root into every entry the root reaches, residuates
the composed text into that entry's coordinates, and returns a
:class:`ScopePlan` of plain data. Past :data:`COMPOSED_ARM_LIMIT`
composed arms, an entry's owned roots ride beside the uncomposed arms
as its scope channel instead.

    plan = plan_scope(owners, keys, skip_paths, roots, patterns, exclusions, reach, literals, deadline)

The walk is pure: it reads no mount table, no router and no storage,
only the facts its caller resolved and the pattern text. So the router
runs it on a worker under a deadline, and a test runs it with no router
at all. :func:`walks` says whether a call's plan needs the worker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

from vfs.deadline import CHECK_EVERY
from vfs.paths import ROOT, address_of
from vfs.pattern_matching import ScopeChannel, composed_pattern, escape_glob, render_residual, residuals

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from vfs.deadline import Deadline
    from vfs.paths import Path

# Past this many composed arms in one entry (owned roots times arms), the roots
# ride beside the arms as a scope channel; the storage fan's arm ceiling.
COMPOSED_ARM_LIMIT: Final = 200


class ScopePlan(NamedTuple):
    """A fan-out's planned scope: what the residual walk derived, entry by entry.

    ``members`` maps each planned entry's bind path to its admissions in
    entry coordinates (``None``: unrestricted); an entry absent from it
    is not dispatched. ``exclusions`` holds the same entries' exclusion
    members, ``skips`` the capability-skip paths whose reach the walk
    found or could not determine, ``roots`` the scope roots planned
    whole, and ``completed`` whether the walk finished before its wall.
    ``scopes`` maps each entry past the composition limit to its scope
    channel: its owned roots in entry coordinates beside the uncomposed
    arms and exclusion arms.
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
    """The planning walk's residuations, its deadline read before every ``CHECK_EVERY``th one.

    The residuations arrive one call at a time, never as a sequence to
    chunk, so the walk counts them and reads the deadline it holds.
    """

    def __init__(self, deadline: Deadline) -> None:
        self._deadline = deadline
        self._count = 0

    def residuals(self, pattern: str, bind_path: Path) -> frozenset[tuple[str, ...]]:
        """:func:`~vfs.pattern_matching.residuals`, or :class:`_WallReached` past the deadline."""
        if self._count % CHECK_EVERY == 0 and self._deadline.expired():
            raise _WallReached
        self._count += 1
        return residuals(pattern, bind_path)


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
    Each root composes *patterns* and *exclusions* under itself into
    every entry it reaches and residuates them there; a root in
    *literals* also rides its owning entry as its own literal path. With
    no root, name arms copy verbatim, path arms residuate, and no
    *patterns* at all is unrestricted. A skip is kept where some *reach*
    pattern can reach its entry's rows.

    Composition is the product of an entry's owned roots and the arms,
    so past :data:`COMPOSED_ARM_LIMIT` composed arms an entry's owned
    roots (each rewritten once into its coordinates) ride its scope
    channel beside the arms instead. Three things still compose at any
    size, being bounded: an entry's owned roots within the limit, roots
    that address its whole side (its bind path, the trash head; at most
    two), and roots above a nested entry (at most its bind depth). A
    root's literal, under *literals*, stays on the entry-wide channel,
    one per root.

    The deadline is read before every ``CHECK_EVERY``th residuation,
    inside a root as well as between roots (between entries when there
    is no root), so the walk overruns its wall by at most that many
    residuations. A root, or
    with no root an entry, whose walk is stopped is dropped from the
    plan whole, its exclusions with it, and every skip not yet decided
    is kept: a coverage record never hides. Pure Python on its worker,
    the walk holds the GIL in turns, and the loop serves between them;
    the native residual walk is the direction.
    """
    walk = _Walk(deadline)
    members: dict[Path, set[str] | None] = {key: set() for key in keys} if roots else {}
    excluded: dict[Path, set[str]] = {key: set() for key in keys} if roots else {}
    switched = _switched_entries(owners, roots, len(patterns) + len(exclusions))
    channeled: dict[Path, list[Path]] = {key: [] for key in switched}
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
                    if key in switched and key == owners[root] and not _addresses_whole_side(root, key):
                        literal = _root_literal(root, key, literals, walk)
                        staged[key] = (literal, set(), root.without_mount(key))
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _path_covers(ancestor: Path, descendant: Path) -> bool:
    """Whether *descendant* sits at or beneath *ancestor* in the namespace."""
    if ancestor in (descendant, ROOT):
        return True
    return str(descendant).startswith(str(ancestor) + "/")


def _switched_entries(owners: Mapping[Path, Path], roots: tuple[Path, ...], arms: int) -> frozenset[Path]:
    """The entries whose owned roots, times the call's *arms*, compose past :data:`COMPOSED_ARM_LIMIT`.

    Only owned roots strictly beneath the entry's side count: a root that
    addresses the whole side composes at any size.
    """
    counts: dict[Path, int] = {}
    for root in roots:
        key = owners[root]
        if not _addresses_whole_side(root, key):
            counts[key] = counts.get(key, 0) + 1
    return frozenset(key for key, count in counts.items() if count * arms > COMPOSED_ARM_LIMIT)


def _addresses_whole_side(root: Path, key: Path) -> bool:
    """Whether *root*, owned by the entry bound at *key*, is that entry's root or its trash view's head."""
    return address_of(str(root.without_mount(key))).stored == "/"


def _root_literal(root: Path, key: Path, literals: frozenset[Path], walk: _Walk) -> set[str]:
    """A root in *literals* as its own literal path in its owning entry's coordinates; nothing otherwise."""
    if root not in literals:
        return set()
    return set(_residual_renders(escape_glob(str(root)), key, walk))


def _scope_channels(
    channeled: Mapping[Path, list[Path]], patterns: tuple[str, ...], exclusions: tuple[str, ...]
) -> dict[Path, ScopeChannel]:
    """Each switched entry's scope channel: its planned owned roots beside the call's uncomposed arms."""
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

    Empty-tuple residuals are dropped: the bind-point row is the
    parent's stored directory, never a child dispatch.
    """
    return sorted(render_residual(components) for components in walk.residuals(pattern, bind_path) if components)


def _glob_reaches(bind_path: Path, roots: tuple[Path, ...], pattern: str, walk: _Walk) -> bool:
    """Whether any scope root lets the pattern reach rows of this entry."""
    if any(_path_covers(bind_path, root) for root in roots):
        return True  # a root inside the entry names rows the entry holds
    return any(
        components for root in roots for components in walk.residuals(composed_pattern(root, pattern), bind_path)
    )
