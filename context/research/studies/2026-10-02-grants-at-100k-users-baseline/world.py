"""The synthetic world for the grants-at-100k-users baseline — seeded, deterministic, importable.

The parameters are fixed by the study brief so that a parallel prototype
builds exactly the same world and the two can be compared number for
number. ``N`` is the only free parameter; everything else derives from it.

- Users ``u000000 .. u(N-1)``. Each has ``/home/uNNNNNN`` with posture
  ``none`` (an everyone row at ``none``) and a ``read_write`` grant to
  itself on it.
- Root posture ``open``: the everyone row ``("*", "/", "read_write")``,
  which is what vfs stores for ``posture("/", "open")``.
- ``S = N // 100`` shared folders ``/shared/sNNNN``; ``G = N // 200``
  groups ``group:gNNNN``; each user is a direct member of 5 groups.
- Each shared folder grants ``read`` to 3 groups and ``read_write`` to 1
  more group (4 distinct groups), plus ``read`` to 10 individual users.
- Rows: ``files_per_home`` files per home (20 by default), ``files_per_shared``
  per shared folder (200 by default), and 100 sibling traps
  ``/home/uNNNNNN-x`` (a directory with one file) beside the first 100
  homes — a range that treated ``/home/u000001`` as one span instead of
  two would leak or hide them.
- Home files are owned by their user (``owner_id``); everything else has
  no owner.

The RNG is ``random.Random(f"grants-baseline-{N}")`` and is drawn in this
order: for each user in order, ``rng.sample(groups, 5)``; then for each
shared folder in order, ``rng.sample(groups, 4)`` (first three ``read``,
the fourth ``read_write``) and then ``rng.sample(users, 10)``.

    world = build(1_000)
    world.grants[:3]       # the root posture, then u000000's two rows
    list(world.entries())  # EntryRow(path, kind, owner, parent)

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import NamedTuple

from vfs.storage.grants import GrantRow

GROUPS_PER_USER = 5
READ_GROUPS_PER_SHARED = 3
WRITE_GROUPS_PER_SHARED = 1
USERS_PER_SHARED = 10
TRAPS = 100
FILES_PER_HOME = 20
FILES_PER_SHARED = 200


class EntryRow(NamedTuple):
    """One row of the entry table: path, kind, owner, and the parent's path."""

    path: str
    kind: str
    owner: str | None
    parent: str | None


@dataclass(frozen=True)
class World:
    n: int
    files_per_home: int
    files_per_shared: int
    users: tuple[str, ...]
    groups: tuple[str, ...]
    shared: tuple[str, ...]
    member_of: dict[str, tuple[str, ...]]
    grants: tuple[GrantRow, ...]

    @property
    def homes(self) -> list[str]:
        return [home_of(user) for user in self.users]

    def closure(self, user: str) -> frozenset[str]:
        """The user's group set — flat, no nesting in this world."""
        return frozenset(self.member_of[user])

    def rows_for(self, subjects: tuple[str, ...]) -> list[GrantRow]:
        """Every grant row naming one of *subjects*, one of their groups, or everyone — what the resolver reads."""
        ids = {"*", *subjects, *(g for s in subjects for g in self.member_of.get(s, ()))}
        return [row for row in self.grants if row.principal_id in ids]

    def rows_by_principal(self) -> dict[str, int]:
        """How many rows name each principal (users, groups, everyone)."""
        counts: dict[str, int] = {}
        for row in self.grants:
            counts[row.principal_id] = counts.get(row.principal_id, 0) + 1
        return counts

    def grants_held(self, user: str, counts: dict[str, int] | None = None) -> int:
        """How many named rows reach *user* through itself and its groups."""
        by = self.rows_by_principal() if counts is None else counts
        return by.get(user, 0) + sum(by.get(g, 0) for g in self.member_of[user])

    def heavy_user(self) -> str:
        """The user whose own and group rows are the most numerous."""
        counts = self.rows_by_principal()
        return max(self.users, key=lambda u: (self.grants_held(u, counts), u))

    def entry_count(self) -> int:
        return (
            3  # /, /home, /shared
            + self.n * (1 + self.files_per_home)
            + len(self.shared) * (1 + self.files_per_shared)
            + min(TRAPS, self.n) * 2
        )

    def entries(self):  # noqa: ANN201 — a generator of EntryRow
        """Every entry row in a parent-before-child order; the root first."""
        yield EntryRow("/", "directory", None, None)
        yield EntryRow("/home", "directory", None, "/")
        yield EntryRow("/shared", "directory", None, "/")
        for user in self.users:
            home = home_of(user)
            yield EntryRow(home, "directory", None, "/home")
            for f in range(self.files_per_home):
                yield EntryRow(f"{home}/note{f:03d}.md", "file", user, home)
        for user in self.users[:TRAPS]:
            trap = home_of(user) + "-x"
            yield EntryRow(trap, "directory", None, "/home")
            yield EntryRow(f"{trap}/trap.md", "file", None, trap)
        for folder in self.shared:
            yield EntryRow(folder, "directory", None, "/shared")
            for f in range(self.files_per_shared):
                yield EntryRow(f"{folder}/doc{f:03d}.md", "file", None, folder)


def home_of(user: str) -> str:
    return f"/home/{user}"


def build(n: int, *, files_per_home: int = FILES_PER_HOME, files_per_shared: int = FILES_PER_SHARED) -> World:
    """The world for *n* users; the grant rows in the order the brief lists them."""
    rng = random.Random(f"grants-baseline-{n}")
    users = tuple(f"u{i:06d}" for i in range(n))
    groups = tuple(f"group:g{i:04d}" for i in range(max(GROUPS_PER_USER, n // 200)))
    shared = tuple(f"/shared/s{i:04d}" for i in range(n // 100))
    member_of = {user: tuple(rng.sample(groups, GROUPS_PER_USER)) for user in users}
    grants: list[GrantRow] = [GrantRow("*", "/", "read_write")]
    for user in users:
        home = home_of(user)
        grants.append(GrantRow("*", home, "none"))
        grants.append(GrantRow(user, home, "read_write"))
    for folder in shared:
        picked = rng.sample(groups, READ_GROUPS_PER_SHARED + WRITE_GROUPS_PER_SHARED)
        grants.extend(GrantRow(g, folder, "read") for g in picked[:READ_GROUPS_PER_SHARED])
        grants.extend(GrantRow(g, folder, "read_write") for g in picked[READ_GROUPS_PER_SHARED:])
        grants.extend(GrantRow(u, folder, "read") for u in rng.sample(users, USERS_PER_SHARED))
    return World(n, files_per_home, files_per_shared, users, groups, shared, member_of, tuple(grants))


if __name__ == "__main__":
    import sys

    world = build(int(sys.argv[1]) if len(sys.argv) > 1 else 1_000)
    heavy = world.heavy_user()
    print(
        f"N={world.n} users={len(world.users)} groups={len(world.groups)} shared={len(world.shared)} "
        f"grant rows={len(world.grants)} memberships={len(world.users) * GROUPS_PER_USER} "
        f"entries={world.entry_count()} ordinary=u000007 holds {world.grants_held('u000007')} "
        f"heavy={heavy} holds {world.grants_held(heavy)}"
    )
