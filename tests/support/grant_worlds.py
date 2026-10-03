"""Random grant worlds — small trees, nested groups, postures and owners.

Shared by the resolver's parity test and the storage legs that replay the
same worlds through the public verbs. A world is small enough to check
every path against the pointwise oracle, and varied enough to hit the
hard cases: a posture hole under a wider posture, a group reached two
levels down, an owner arm the other members' grants trim.

Two layouts: the base tree, and a sibling tree whose names sort beside
each other in bytewise order — ``p`` beside ``p0``, ``p-x`` and ``p/x``,
segments ending in ``0``, ``-``, ``.``, ``!``, a space, ``~`` and
non-ASCII — the shapes whose range bounds touch and merge.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

from tests.support.oracles.grants import GrantWorld
from vfs.storage.grants import GrantLevel, GrantRow

if TYPE_CHECKING:
    import random


class Layout(NamedTuple):
    """One world's tree: what grants may name, and the probes that sort beside it."""

    directories: tuple[str, ...]
    files: tuple[str, ...]
    traps: tuple[str, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        return (*self.directories, *self.files)


DIRECTORIES: Final = ("/a", "/a/b", "/a/b/c", "/a/d", "/e", "/e/f")
FILES: Final = ("/top.md", "/a/x.md", "/a/b/y.md", "/a/b/c/z.md", "/a/d/w.md", "/e/v.md", "/e/f/u.md")
PATHS: Final = (*DIRECTORIES, *FILES)

# Paths that sort beside the base prefixes: "-" below "/", "0" just above it.
TRAPS: Final = ("/a-b", "/a0", "/a/b-c", "/a/b0", "/a/b/c-d.md", "/a/b/c0", "/e-f", "/e0", "/e/f0")

BASE: Final = Layout(DIRECTORIES, FILES, TRAPS)

SIBLINGS: Final = Layout(
    directories=("/a", "/a0", "/a-b", "/a.c", "/a!", "/a b", "/a~", "/é", "/é0", "/a/b", "/a/b0", "/v1", "/v10"),
    files=(
        "/top.md",
        "/a/x.md",
        "/a0/x.md",
        "/a-b/x.md",
        "/a.c/x.md",
        "/a!/x.md",
        "/a b/x.md",
        "/a~/x.md",
        "/é/x.md",
        "/é0/x.md",
        "/a/b/y.md",
        "/a/b0/y.md",
        "/v1/x.md",
        "/v10/x.md",
    ),
    traps=("/a00", "/a0-x", "/a0/x", "/a/b00", "/a/b-c", "/a-b0", "/é-x", "/v100", "/v1-x", "/v10-x", "/0", "/-", "/~"),
)

LAYOUTS: Final = (BASE, SIBLINGS)

USERS: Final = ("u1", "u2", "u3")
GROUPS: Final = ("group:g1", "group:g2", "group:g3")

# The subject sets every world is asked about: each user alone, a pair, all three.
SUBJECT_SETS: Final[tuple[tuple[str, ...], ...]] = (("u1",), ("u2",), ("u3",), ("u1", "u2"), USERS)

_NAMED_LEVELS: Final[tuple[GrantLevel, ...]] = ("read", "read_write")
_ALL_LEVELS: Final[tuple[GrantLevel, ...]] = ("none", "read", "read_write")


def random_world(rng: random.Random, layout: Layout = BASE) -> GrantWorld:
    """One world: a root posture, a few deeper postures, named grants, acyclic memberships, owners."""
    prefixes = ("/", *layout.paths)
    rows = [GrantRow("*", "/", rng.choice(_ALL_LEVELS))]
    rows += [GrantRow("*", prefix, rng.choice(_ALL_LEVELS)) for prefix in rng.sample(layout.paths, rng.randint(0, 3))]
    principals = (*USERS, *GROUPS)
    named = {(rng.choice(principals), rng.choice(prefixes)) for _ in range(rng.randint(0, 7))}
    rows += [GrantRow(principal, prefix, rng.choice(_NAMED_LEVELS)) for principal, prefix in sorted(named)]
    member_of: dict[str, set[str]] = {}
    for user in USERS:
        member_of[user] = set(rng.sample(GROUPS, rng.randint(0, 2)))
    for i, inner in enumerate(GROUPS):
        outer = [g for g in GROUPS[i + 1 :] if rng.random() < 0.4]
        member_of[inner] = set(outer)
    owners = {path: rng.choice((None, *USERS)) for path in layout.files}
    return GrantWorld(grants=rows, member_of=member_of, owners=owners)
