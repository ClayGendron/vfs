"""Pointwise grant oracle — one path at a time, no prefix algebra.

The resolver in ``vfs.storage.grants`` works on prefix sets: it unions
each subject's covering prefixes and meets them across the subject set,
and reads what everyone holds off each row's stored label. This oracle
asks the same question the slow, obvious way, for one path at a time,
and computes the everyone level itself from the ``*`` rows — it is also
what every stored label is checked against:

- everyone holds the level of the deepest ``*`` row covering the path
  (:func:`everyone_rank`);
- a subject holds the maximum of that, of every row naming it or one
  of the groups it reaches, and of ``read_write`` on a row it owns;
- a subject set holds the minimum over its subjects;
- a trashed row is judged at its origin, the path it was deleted from
  (``origins`` maps each trash path to it), with the owner it had there.

A parity test runs both on random worlds; they must agree on every path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from vfs.authority import EVERYONE_NAME
from vfs.storage.grants import LEVEL_RANK, covers

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from vfs.storage.grants import GrantRow


@dataclass
class GrantWorld:
    """The rows one mount holds: grants, direct memberships, and row owners."""

    grants: list[GrantRow]
    member_of: dict[str, set[str]] = field(default_factory=dict)
    owners: dict[str, str | None] = field(default_factory=dict)
    origins: dict[str, str] = field(default_factory=dict)

    def judged(self, path: str) -> str:
        """The path *path*'s rights are judged by: its origin when it is a trash path, else itself."""
        return self.origins.get(path, path)

    def closure(self, principal: str) -> frozenset[str]:
        """Every group *principal* reaches, directly or through nesting."""
        seen: set[str] = set()
        frontier = {principal}
        while frontier:
            reached = set().union(*(self.member_of.get(p, set()) for p in frontier)) - seen
            seen |= reached
            frontier = reached
        return frozenset(seen - {principal})

    def closures(self, subjects: Iterable[str]) -> Mapping[str, frozenset[str]]:
        return {sub: self.closure(sub) for sub in subjects}


def everyone_rank(world: GrantWorld, path: str) -> int:
    """The rank the deepest covering ``*`` row gives everyone at the judged path; nothing when none covers."""
    path = world.judged(path)
    rows = [row for row in world.grants if row.principal_id == EVERYONE_NAME and covers(row.path_prefix, path)]
    if not rows:
        return LEVEL_RANK["none"]
    deepest = max(rows, key=lambda row: len(row.path_prefix))
    return LEVEL_RANK[deepest.level]


def subject_rank(world: GrantWorld, sub: str, path: str, *, owner_floor: bool = True) -> int:
    """The highest rank *sub* holds on *path*: everyone's, its own and its groups', its ownership."""
    path = world.judged(path)
    ids = {sub} | world.closure(sub)
    granted = max(
        (LEVEL_RANK[row.level] for row in world.grants if row.principal_id in ids and covers(row.path_prefix, path)),
        default=LEVEL_RANK["none"],
    )
    owned = LEVEL_RANK["read_write"] if owner_floor and world.owners.get(path) == sub else LEVEL_RANK["none"]
    return max(everyone_rank(world, path), granted, owned)


def set_rank(world: GrantWorld, subjects: Iterable[str], path: str, *, owner_floor: bool = True) -> int:
    """The rank a subject set holds on *path*: the lowest any one member holds."""
    return min(subject_rank(world, sub, path, owner_floor=owner_floor) for sub in subjects)
