"""Group permissions: max within each subject, min across the subject set.

A pure-Python model of spec 058's resolver once groups are in play,
checked three ways:

1. **Algebra.** A pointwise oracle (per subject: the maximum over the
   everyone rows, its own rows, its groups' rows and the owner floor;
   per set: the minimum over subjects) against the resolver's prefix
   algebra (per subject: the covering prefix set at a level; per set:
   the meet), on thousands of random worlds with nested groups and
   posture rows. Three deliberately wrong algebras run beside it so the
   difference is visible: groups pooled across the set, the owner floor
   only for a set of one (spec 058 section 3 step 4 as written), and the
   root prefix compiled literally as ``path LIKE '//%'``.
2. **SQL.** The resolved arms compiled to a ``WHERE`` clause and run on
   stdlib SQLite, compared row for row with the oracle.
3. **Budgets.** A sweep over subject-set sizes 1 to 64 and groups per
   principal 0 to 50 that counts the statements the resolver issues and
   the binds the compiled predicate needs, literal and fallback, against
   SQL Server's 2,099 parameters and Oracle's 1,000-element ``IN`` list.

    uv run --no-sync python model.py            # everything, ~1 min
    uv run --no-sync python model.py --quick    # fewer random worlds

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import reduce

# ---------------------------------------------------------------------------
# Constants and shared types
# ---------------------------------------------------------------------------

INVISIBLE, READ, READ_WRITE = 0, 1, 2
LEVEL_NAMES = {INVISIBLE: "invisible", READ: "read", READ_WRITE: "read_write"}
EVERYONE = "*"
GROUP_PREFIX = "group:"
ROOT = "/"

MSSQL_PARAMETER_BUDGET = 2_099
ORACLE_IN_LIST_BUDGET = 1_000
MSSQL_IN_LIST_BUDGET = 2_000
FILTER_BIND_RESERVE = 32
MAX_GROUP_DEPTH = 8


@dataclass
class World:
    """Entries, grant rows and direct memberships for one storage."""

    owner: dict[str, str | None]
    grants: list[tuple[str, str, int]]
    member_of: dict[str, set[str]] = field(default_factory=dict)

    @property
    def paths(self) -> list[str]:
        return sorted(self.owner)


@dataclass(frozen=True)
class Arm:
    """``prefix`` covers the row and none of ``holes`` does."""

    prefix: str
    holes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rights:
    """What the compiler receives: plain arms plus per-member owner arms."""

    arms: tuple[Arm, ...]
    owner_arms: tuple[tuple[str, tuple[str, ...]], ...]


# ---------------------------------------------------------------------------
# The oracle: pointwise max within a subject, min across the set
# ---------------------------------------------------------------------------


def covers(prefix: str, path: str) -> bool:
    return prefix == ROOT or path == prefix or path.startswith(prefix + "/")


def closure(world: World, principal: str, depth_cap: int = MAX_GROUP_DEPTH) -> tuple[set[str], int]:
    """Every group *principal* reaches, and the depth the walk needed."""
    seen: set[str] = set()
    frontier = {principal}
    depth = 0
    while True:
        nxt = set().union(*(world.member_of.get(p, set()) for p in frontier)) - seen - {principal}
        if not nxt:
            return seen, depth
        depth += 1
        if depth > depth_cap:
            msg = f"group walk from {principal} deeper than {depth_cap}"
            raise RecursionError(msg)
        seen |= nxt
        frontier = nxt


def everyone_level(world: World, path: str) -> int:
    rows = [(pf, lvl) for pid, pf, lvl in world.grants if pid == EVERYONE and covers(pf, path)]
    return max(rows, key=lambda r: len(r[0]))[1] if rows else INVISIBLE


def subject_level(world: World, sub: str, path: str) -> int:
    ids = {sub} | closure(world, sub)[0]
    granted = max((lvl for pid, pf, lvl in world.grants if pid in ids and covers(pf, path)), default=INVISIBLE)
    floor = READ_WRITE if world.owner.get(path) == sub else INVISIBLE
    return max(everyone_level(world, path), granted, floor)


def session_level(world: World, subjects: Sequence[str], path: str) -> int:
    return min(subject_level(world, s, path) for s in subjects)


# ---------------------------------------------------------------------------
# The resolver: covering prefix sets, the meet, the arms
# ---------------------------------------------------------------------------


def minimise(prefixes: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for pf in sorted(set(prefixes), key=lambda p: (p.count("/") if p != ROOT else 0, p)):
        if not any(covers(o, pf) for o in out):
            out.append(pf)
    return tuple(sorted(out))


def meet(a: Sequence[str], b: Sequence[str]) -> tuple[str, ...]:
    """The prefix set whose coverage is cover(a) intersected with cover(b)."""
    out = {y if covers(x, y) else x for x in a for y in b if covers(x, y) or covers(y, x)}
    return minimise(out)


def meet_all(sets: Sequence[Sequence[str]]) -> tuple[str, ...]:
    return reduce(meet, sets) if sets else (ROOT,)


def covering_set(world: World, ids: set[str], level: int) -> tuple[str, ...]:
    return minimise(pf for pid, pf, lvl in world.grants if pid in ids and pid != EVERYONE and lvl >= level)


def everyone_arms(world: World, level: int, *, nearest_only: bool = False) -> tuple[Arm, ...]:
    """Posture rows at *level*, each minus every lower ``*`` row beneath it.

    Every lower row counts, not only the nearest: under an open root, a
    shared ``/a`` with a private ``/a/b`` must still cut ``/a/b`` from the root arm.
    """
    star = {pf: lvl for pid, pf, lvl in world.grants if pid == EVERYONE}
    arms = []
    for pf, lvl in star.items():
        if lvl < level:
            continue
        below = [q for q in star if q != pf and covers(pf, q)]
        if nearest_only:
            below = [q for q in below if not any(r != q and covers(r, q) for r in below)]
        holes = minimise(q for q in below if star[q] < level)
        arms.append(Arm(pf, holes))
    return tuple(sorted(arms, key=lambda a: a.prefix))


def resolve(
    world: World,
    subjects: Sequence[str],
    level: int,
    *,
    pool_groups: bool = False,
    owner_floor: str = "per_member",
    nearest_holes: bool = False,
) -> Rights:
    """Spec 058's resolver with groups; the keyword flags switch on the three wrong variants.

    A member's owner arm keeps only the prefixes the shared arms do not
    already cover, and is dropped when none remain.
    """
    closures = {s: closure(world, s)[0] for s in subjects}
    pooled = set().union(*closures.values())
    ids = {s: {s} | (pooled if pool_groups else closures[s]) for s in subjects}
    covering = {s: covering_set(world, ids[s], level) for s in subjects}
    shared = meet_all([covering[s] for s in subjects])
    owner_arms = []
    for s in subjects:
        others = [covering[o] for o in subjects if o != s]
        rest = meet_all(others)
        if owner_floor == "single_only" and len(subjects) > 1:
            continue
        rest = tuple(p for p in rest if not any(covers(q, p) for q in shared))
        if rest:
            owner_arms.append((s, rest))
    arms = everyone_arms(world, level, nearest_only=nearest_holes) + tuple(Arm(p) for p in shared)
    return Rights(arms, tuple(owner_arms))


def admits(rights: Rights, path: str, owner: str | None) -> bool:
    if any(covers(a.prefix, path) and not any(covers(h, path) for h in a.holes) for a in rights.arms):
        return True
    return any(owner == s and any(covers(p, path) for p in rest) for s, rest in rights.owner_arms)


# ---------------------------------------------------------------------------
# The compiler, on SQLite
# ---------------------------------------------------------------------------


def like_escape(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"


def cover_sql(prefix: str, binds: list[str], *, literal_root: bool) -> str:
    if prefix == ROOT and not literal_root:
        return "1=1"
    binds += [prefix, like_escape(prefix)]
    return "(path = ? OR path LIKE ? ESCAPE '\\')"


def compile_where(rights: Rights, *, literal_root: bool = False) -> tuple[str, list[str]]:
    binds: list[str] = []
    parts = []
    for a in rights.arms:
        sql = cover_sql(a.prefix, binds, literal_root=literal_root)
        for h in a.holes:
            sql += " AND NOT " + cover_sql(h, binds, literal_root=literal_root)
        parts.append(f"({sql})")
    for s, rest in rights.owner_arms:
        binds.append(s)
        inner = " OR ".join(cover_sql(p, binds, literal_root=literal_root) for p in rest) or "1=0"
        parts.append(f"(owner_id = ? AND ({inner}))")
    return (" OR ".join(parts) or "1=0"), binds


def literal_binds(rights: Rights) -> int:
    return len(compile_where(rights)[1])


# ---------------------------------------------------------------------------
# Random worlds
# ---------------------------------------------------------------------------

SEGMENTS = ("a", "b", "c", "d", "x_y", "p%q")


def random_world(rng: random.Random, n_users: int = 8, n_groups: int = 6) -> World:
    paths = {ROOT}
    for _ in range(60):
        depth = rng.randint(1, 4)
        paths.add("/" + "/".join(rng.choice(SEGMENTS) for _ in range(depth)))
    for p in list(paths):
        while p != ROOT:
            paths.add(p)
            p = p.rsplit("/", 1)[0] or ROOT
    users = [f"u{i}" for i in range(n_users)]
    groups = [f"{GROUP_PREFIX}g{i}" for i in range(n_groups)]
    owner = {p: (rng.choice(users) if rng.random() < 0.4 else None) for p in paths}
    dirs = sorted(paths)
    grants = [(rng.choice(users + groups), rng.choice(dirs), rng.choice((READ, READ_WRITE))) for _ in range(rng.randint(4, 20))]
    posture = {ROOT: rng.choice((INVISIBLE, READ, READ_WRITE))}
    posture |= {rng.choice(dirs): rng.choice((INVISIBLE, READ, READ_WRITE)) for _ in range(rng.randint(0, 3))}
    grants += [(EVERYONE, pf, lvl) for pf, lvl in posture.items()]
    member_of: dict[str, set[str]] = {}
    for u in users:
        member_of[u] = set(rng.sample(groups, rng.randint(0, 3)))
    for i, g in enumerate(groups):
        if i and rng.random() < 0.5:
            member_of[g] = {rng.choice(groups[:i])}
    return World(owner, grants, member_of)


def check_algebra(worlds: int, seed: int) -> dict[str, int]:
    rng = random.Random(seed)
    tally = dict.fromkeys(("checks", "correct_wrong", "pooled_leaks", "pooled_hides", "single_only_hides", "nearest_holes_leaks", "sql_mismatch", "literal_root_hides"), 0)
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA case_sensitive_like = ON")
    db.execute("CREATE TABLE entry (path TEXT PRIMARY KEY, owner_id TEXT)")
    for _ in range(worlds):
        world = random_world(rng)
        db.execute("DELETE FROM entry")
        db.executemany("INSERT INTO entry VALUES (?, ?)", list(world.owner.items()))
        users = sorted({k for k in world.member_of if not k.startswith(GROUP_PREFIX)})
        subjects = rng.sample(users, rng.randint(1, 5))
        for level in (READ, READ_WRITE):
            right = resolve(world, subjects, level)
            pooled = resolve(world, subjects, level, pool_groups=True)
            single = resolve(world, subjects, level, owner_floor="single_only")
            nearest = resolve(world, subjects, level, nearest_holes=True)
            truth = {p for p in world.paths if session_level(world, subjects, p) >= level}
            for p in world.paths:
                o = world.owner[p]
                tally["checks"] += 1
                tally["correct_wrong"] += admits(right, p, o) != (p in truth)
                tally["pooled_leaks"] += admits(pooled, p, o) and p not in truth
                tally["pooled_hides"] += (not admits(pooled, p, o)) and p in truth
                tally["single_only_hides"] += (not admits(single, p, o)) and p in truth
                tally["nearest_holes_leaks"] += admits(nearest, p, o) and p not in truth
            for literal_root, key in ((False, "sql_mismatch"), (True, "literal_root_hides")):
                where, binds = compile_where(right, literal_root=literal_root)
                got = {r[0] for r in db.execute(f"SELECT path FROM entry WHERE {where}", binds)}  # noqa: S608
                tally[key] += len(truth ^ got) if key == "sql_mismatch" else len(truth - got)
    return tally


# ---------------------------------------------------------------------------
# The worked example
# ---------------------------------------------------------------------------


def example_world() -> World:
    g = GROUP_PREFIX
    owner = {
        "/eng/specs/api.md": None,
        "/vault/keys.md": None,
        "/design/mock.png": None,
        "/sales/deals.csv": None,
        "/ops/runbook.md": None,
        "/home/ann/shared/plan.md": "ann",
        "/home/ann/diary.md": "ann",
        "/public/readme.md": None,
    }
    grants = [
        (EVERYONE, ROOT, INVISIBLE),
        (EVERYONE, "/public", READ),
        (f"{g}eng", "/eng", READ_WRITE),
        (f"{g}security", "/vault", READ),
        (f"{g}design", "/design", READ_WRITE),
        (f"{g}ops", "/ops", READ),
        (f"{g}sales", "/sales", READ_WRITE),
        ("ann", "/sales", READ),
        ("john", "/design", READ),
        ("john", "/home/ann/shared", READ),
    ]
    member_of = {
        "ann": {f"{g}platform", f"{g}security", f"{g}design", f"{g}ops"},
        f"{g}platform": {f"{g}eng"},
        "john": {f"{g}eng", f"{g}sales"},
    }
    return World(owner, grants, member_of)


def explain_example() -> list[str]:
    world = example_world()
    lines = [
        "| path | Ann | John | Ann + John (min) | groups pooled (wrong) | owner floor only for one (wrong) |",
        "|---|---|---|---|---|---|",
    ]
    for p in sorted(world.owner):
        ann, john = subject_level(world, "ann", p), subject_level(world, "john", p)
        both = session_level(world, ["ann", "john"], p)
        pooled = max((lvl for lvl in (READ, READ_WRITE) if admits(resolve(world, ["ann", "john"], lvl, pool_groups=True), p, world.owner[p])), default=0)
        single = max((lvl for lvl in (READ, READ_WRITE) if admits(resolve(world, ["ann", "john"], lvl, owner_floor="single_only"), p, world.owner[p])), default=0)
        right = max((lvl for lvl in (READ, READ_WRITE) if admits(resolve(world, ["ann", "john"], lvl), p, world.owner[p])), default=0)
        assert right == both, (p, right, both)
        lines.append(
            f"| `{p}` | {LEVEL_NAMES[ann]} | {LEVEL_NAMES[john]} | **{LEVEL_NAMES[both]}** | "
            f"{_mark(pooled, both)} | {_mark(single, both)} |"
        )
    for level in (READ, READ_WRITE):
        r = resolve(world, ["ann", "john"], level)
        arms = ", ".join(a.prefix + (f" minus {', '.join(a.holes)}" if a.holes else "") for a in r.arms)
        owners = "; ".join(f"owner={s} AND under {', '.join(rest)}" for s, rest in r.owner_arms)
        lines.append(f"\nAnn + John at `{LEVEL_NAMES[level]}`: arms {arms or 'none'}; owner arms {owners or 'none'}; {literal_binds(r)} binds.")
    return lines


def _mark(got: int, want: int) -> str:
    if got == want:
        return LEVEL_NAMES[got]
    return f"{LEVEL_NAMES[got]} ({'LEAK' if got > want else 'over-hidden'})"


# ---------------------------------------------------------------------------
# Budgets at scale
# ---------------------------------------------------------------------------


@dataclass
class Corpus:
    """S1-shaped grants: Zipf top-level folders, team groups, one all-hands group."""

    world: World
    users: list[str]


def scale_corpus(rng: random.Random, groups_per_user: int, n_users: int = 2_000, n_groups: int = 300, nested: bool = True) -> Corpus:
    tops = [f"/t{i:03d}" for i in range(200)]
    weights = [1 / (i + 1) for i in range(len(tops))]

    def prefix(depth: int) -> str:
        return rng.choices(tops, weights)[0] + "".join(f"/s{rng.randint(0, 9)}" for _ in range(depth - 1))

    users = [f"u{i:05d}" for i in range(n_users)]
    groups = [f"{GROUP_PREFIX}team{i:03d}" for i in range(n_groups)]
    grants = [(EVERYONE, ROOT, INVISIBLE)] + [(EVERYONE, t, READ) for t in tops[:5]]
    for u in users:
        grants += [(u, prefix(rng.randint(2, 5)), rng.choice((READ, READ_WRITE))) for _ in range(5)]
    for grp in groups:
        grants += [(grp, prefix(rng.randint(1, 3)), rng.choice((READ, READ_WRITE))) for _ in range(5)]
    grants += [(f"{GROUP_PREFIX}all", t, READ) for t in tops[5:7]]
    member_of: dict[str, set[str]] = {}
    for u in users:
        member_of[u] = {f"{GROUP_PREFIX}all", *rng.sample(groups, groups_per_user)}
    if nested:
        for i, grp in enumerate(groups):
            if i >= 30:
                member_of[grp] = {groups[rng.randrange(0, 30)]}
    return Corpus(World({}, grants, member_of), users)


def walk_statements(world: World, subjects: Sequence[str], in_budget: int) -> int:
    """Membership-walk statements: one chunked ``IN`` per level of the walk."""
    frontier, seen, count = set(subjects), set(subjects), 0
    while frontier:
        count += -(-len(frontier) // in_budget)
        nxt = set().union(*(world.member_of.get(p, set()) for p in frontier)) - seen
        seen |= nxt
        frontier = nxt
    return count


def sweep(samples: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    arm_cap = (MSSQL_PARAMETER_BUDGET - FILTER_BIND_RESERVE) // 2
    lines = [
        "| n | groups each | distinct ids fetched | fetch stmts Oracle / SQL Server | walk stmts | cover per member (median) | meet arms | owner arms | literal binds (median / max) | literal over SQL Server budget | fallback binds, per-member group lists (median / max) | fallback over SQL Server budget | largest one-member id list |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    by_index: dict[int, Corpus] = {}
    for k in (0, 3, 10, 50):
        corpus = by_index.setdefault(k, scale_corpus(random.Random(seed + k), k))
        w = corpus.world
        for n in (1, 2, 5, 20, 64):
            rows = []
            for _ in range(samples):
                subs = rng.sample(corpus.users, n)
                closures = {s: closure(w, s)[0] for s in subs}
                ids = set(subs).union(*closures.values()) | {EVERYONE}
                r = resolve(w, subs, READ)
                covering = [covering_set(w, {s} | closures[s], READ) for s in subs]
                fallback = sum(1 + 1 + len(closures[s]) + 1 for s in subs)
                rows.append(
                    (
                        len(ids),
                        -(-len(ids) // ORACLE_IN_LIST_BUDGET),
                        -(-len(ids) // MSSQL_IN_LIST_BUDGET),
                        walk_statements(w, subs, ORACLE_IN_LIST_BUDGET),
                        statistics.median(len(c) for c in covering),
                        len(r.arms) - len(everyone_arms(w, READ)),
                        len(r.owner_arms),
                        literal_binds(r),
                        fallback,
                        max(1 + len(closures[s]) for s in subs),
                    )
                )
            col = list(zip(*rows, strict=True))
            lit, fb = col[7], col[8]
            lines.append(
                f"| {n} | {k} | {int(statistics.median(col[0]))} | {int(statistics.median(col[1]))} / {int(statistics.median(col[2]))} | "
                f"{int(statistics.median(col[3]))} | {statistics.median(col[4]):.0f} | {statistics.median(col[5]):.0f} | {statistics.median(col[6]):.0f} | "
                f"{int(statistics.median(lit))} / {max(lit)} | {sum(b > MSSQL_PARAMETER_BUDGET - FILTER_BIND_RESERVE for b in lit)}/{samples} | "
                f"{int(statistics.median(fb))} / {max(fb)} | {sum(b > MSSQL_PARAMETER_BUDGET - FILTER_BIND_RESERVE for b in fb)}/{samples} | {max(col[9])} |"
            )
    lines.append(f"\nSQL Server arm cap by binds alone: ({MSSQL_PARAMETER_BUDGET} - {FILTER_BIND_RESERVE}) // 2 = {arm_cap} arms.")
    return lines


def depth_demo() -> list[str]:
    g = GROUP_PREFIX
    chain = {f"{g}l{i}": {f"{g}l{i + 1}"} for i in range(12)}
    chain["ann"] = {f"{g}l0"}
    world = World({}, [], chain)
    out = []
    for cap in (4, 8, 16):
        try:
            got = closure(world, "ann", cap)
            out.append(f"cap {cap}: walk finished at depth {got[1]}, {len(got[0])} groups")
        except RecursionError as err:
            out.append(f"cap {cap}: refused ({err})")
    cyc = World({}, [], {"ann": {f"{g}a"}, f"{g}a": {f"{g}b"}, f"{g}b": {f"{g}a"}})
    got = closure(cyc, "ann")
    out.append(f"cycle a -> b -> a: walk terminates at depth {got[1]} with {sorted(got[0])} (visited set)")
    return out


def sqlite_arm_ceiling() -> int:
    """The largest prefix-arm count SQLite parses: its expression depth, not its binds, binds first."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE entry (path TEXT PRIMARY KEY, owner_id TEXT)")
    lo, hi = 1, 4_000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        rights = Rights(tuple(Arm(f"/t{i}") for i in range(mid)), ())
        where, binds = compile_where(rights)
        try:
            db.execute(f"SELECT count(*) FROM entry WHERE {where}", binds).fetchone()  # noqa: S608
            lo = mid
        except sqlite3.OperationalError:
            hi = mid - 1
    return lo


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    worlds = 300 if args.quick else 3_000
    samples = 5 if args.quick else 20

    print("## 1. Worked example: Ann, John, and the Ann + John session\n")
    print("\n".join(explain_example()))
    print(f"\n## 2. Algebra and SQL: {worlds} random worlds, nested groups, posture rows, sets of 1 to 5\n")
    tally = check_algebra(worlds, args.seed)
    for key, value in tally.items():
        print(f"- {key}: {value}")
    print(f"\n## 3. Budgets: S1-shaped grants, 2,000 users, 300 team groups (270 nested one level), {samples} random sets per cell, level read\n")
    print("\n".join(sweep(samples, args.seed)))
    ceiling = sqlite_arm_ceiling()
    print(f"\n## 4. SQLite {sqlite3.sqlite_version}: the literal predicate parses up to {ceiling} arms ({2 * ceiling} binds), one more fails\n")
    print(f"- spec 058's bind-only cap on SQLite would be (32,700 - {FILTER_BIND_RESERVE}) // 2 = {(32_700 - FILTER_BIND_RESERVE) // 2} arms")
    print("\n## 5. Nesting: a 13-deep chain and a cycle\n")
    print("\n".join(f"- {line}" for line in depth_demo()))


if __name__ == "__main__":
    main()
