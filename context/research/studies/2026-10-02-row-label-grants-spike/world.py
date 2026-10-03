"""The synthetic world: N users with private homes, shared folders, groups, grants, rows.

Parameters (fixed by the study brief; the baseline agent uses the same):

- users ``u000000 .. u(N-1)``; root posture open (``*`` at ``/`` = read_write)
- each user: ``/home/uNNNNNN`` posture none, plus a read_write grant to itself
- shared folders ``/shared/sNNNN``, S = N/100; groups ``g0000 .. g(G-1)``,
  G = N/200; each user in 5 groups (seeded); each shared folder: read to
  3 groups, read_write to 1 group, read to 10 individual users
- rows: 20 files per home, 200 per shared folder, 100 sibling-trap rows

One deliberate choice inside those parameters: for every fifth shared
folder the first of its three read groups is ``g0000``, so ``g0000`` is
the *grant-heavy group* (8 + S/5 grants) and "a user in a grant-heavy
group" is a member of it. Every other group gets ~8 grants whatever N is.

The sibling traps are ``/home/uNNNNNN-x`` for the first 100 users, each
with its own ``none`` posture and no grant: a range for ``/home/u000001``
that was one piece instead of two would leak ``/home/u000001-x``.

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

FILES_PER_HOME = 20
FILES_PER_SHARED = 200
TRAPS = 100
GROUPS_PER_USER = 5
READ_GROUPS = 3
WRITE_GROUPS = 1
READ_USERS = 10
HEAVY_GROUP = "group:g0000"
HEAVY_EVERY = 5

NONE, READ, READ_WRITE = 0, 1, 2


@dataclass
class World:
    n: int
    users: list[str]
    groups: list[str]
    members: dict[str, list[str]] = field(default_factory=dict)  # user -> its groups
    group_members: dict[str, list[str]] = field(default_factory=dict)  # group -> its users
    star: dict[str, int] = field(default_factory=dict)  # posture rows: prefix -> level
    grants: list[tuple[str, str, int]] = field(default_factory=list)  # (principal, prefix, level)
    by_principal: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    rows: list[tuple[int, str, str | None]] = field(default_factory=list)  # (id, path, owner)
    next_id: int = 1

    def add_row(self, path: str, owner: str | None = None) -> int:
        rid = self.next_id
        self.next_id += 1
        self.rows.append((rid, path, owner))
        return rid

    def add_grant(self, principal: str, prefix: str, level: int) -> None:
        self.grants.append((principal, prefix, level))
        self.by_principal.setdefault(principal, []).append((prefix, level))

    def principals_of(self, user: str) -> list[str]:
        return [user, *self.members.get(user, [])]


def build(
    n: int, seed: int = 20261002, *, files_per_home: int = FILES_PER_HOME, files_per_shared: int = FILES_PER_SHARED
) -> World:
    rng = random.Random(seed)
    users = [f"u{i:06d}" for i in range(n)]
    g_count = max(1, n // 200)
    groups = [f"group:g{i:04d}" for i in range(g_count)]
    w = World(n=n, users=users, groups=groups)
    for g in groups:
        w.group_members[g] = []
    for u in users:
        mine = rng.sample(groups, min(GROUPS_PER_USER, g_count))
        w.members[u] = mine
        for g in mine:
            w.group_members[g].append(u)

    w.star["/"] = READ_WRITE
    w.add_row("/")
    w.add_row("/home")
    w.add_row("/shared")
    for u in users:
        home = f"/home/{u}"
        w.star[home] = NONE
        w.add_grant(u, home, READ_WRITE)
        w.add_row(home)
        for f in range(files_per_home):
            w.add_row(f"{home}/f{f:03d}.md", u)
    for i in range(min(TRAPS, n)):
        trap = f"/home/u{i:06d}-x"
        w.star[trap] = NONE
        w.add_row(trap)
    s_count = max(1, n // 100)
    for s in range(s_count):
        folder = f"/shared/s{s:04d}"
        read_groups = rng.sample(groups, min(READ_GROUPS, g_count))
        if s % HEAVY_EVERY == 0 and HEAVY_GROUP not in read_groups:
            read_groups[0] = HEAVY_GROUP
        for g in read_groups:
            w.add_grant(g, folder, READ)
        for g in rng.sample(groups, min(WRITE_GROUPS, g_count)):
            w.add_grant(g, folder, READ_WRITE)
        for u in rng.sample(users, min(READ_USERS, n)):
            w.add_grant(u, folder, READ)
        w.add_row(folder)
        for f in range(files_per_shared):
            w.add_row(f"{folder}/d{f:03d}.md", rng.choice(users))
    return w


def callers(w: World) -> dict[str, dict]:
    """The five callers: ordinary, heavy-group member, two-subject, anonymous, system."""
    heavy = w.group_members[HEAVY_GROUP]
    heavy_user = heavy[0]
    ordinary = next((u for u in w.users[42:] if HEAVY_GROUP not in w.members[u]), w.users[42])
    partner = next(u for g in w.members[ordinary] for u in w.group_members[g] if u != ordinary)
    return {
        "ordinary": {"subjects": [ordinary]},
        "heavy group": {"subjects": [heavy_user]},
        "two subjects": {"subjects": [ordinary, partner]},
        "anonymous": {"subjects": [], "anonymous": True},
        "system": {"subjects": [], "system": True},
    }
