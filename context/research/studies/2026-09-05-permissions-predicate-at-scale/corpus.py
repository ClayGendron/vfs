"""Deterministic synthetic corpus for the permissions-predicate study.

One seed produces the same entry rows, principals, grants, groups and
memberships on every engine, so the per-engine numbers compare like for
like. Shapes follow the study brief: ~200 top-level directories with a
Zipf-skewed row distribution, paths 2-8 segments deep, 10,000 principals
with Zipf-skewed ownership, ~5 direct grants per principal at mixed
depths, five "everyone" grants on top-level directories, and a groups
variant (memberships plus grants that name a group).
"""

from __future__ import annotations

import bisect
import random
from dataclasses import dataclass, field

TOPS = 200
PRINCIPALS = 10_000
GROUPS = 300
EVERYONE_TOP_RANKS = (0, 4, 19, 59, 149)
DEPTH_WEIGHTS = {2: 0.10, 3: 0.25, 4: 0.25, 5: 0.20, 6: 0.10, 7: 0.06, 8: 0.04}
EXT_WEIGHTS = {"md": 30, "py": 25, "txt": 15, "json": 10, "rs": 10, "csv": 5, "yaml": 5}
SEGMENTS = [
    "src", "docs", "lib", "tests", "notes", "data", "api", "core", "ui", "pkg",
    "internal", "spec", "assets", "build", "tools", "config", "models", "views",
    "handlers", "migrations", "scripts", "examples", "vendor", "cmd", "app",
    "server", "client", "shared", "utils", "research",
]
LEVELS = (("read", 60), ("write", 30), ("admin", 10))


def zipf_weights(n: int, s: float) -> list[float]:
    return [1.0 / (i + 1) ** s for i in range(n)]


@dataclass
class Corpus:
    entries: list[tuple[int, str, str, str, str | None, int, int | None]]  # id, path, owner, kind, ext, size, deleted flag
    principals: list[str]
    grant_flat: list[tuple[str, str, str]]  # (principal, prefix, level) direct + everyone expanded
    grant_g: list[tuple[str, str, str]]  # direct + everyone on g_all + group grants
    grant_gx: list[tuple[str, str, str]]  # grant_g fully expanded to principals
    member: list[tuple[str, str]]  # (principal, group)
    groups_of: dict[str, list[str]] = field(default_factory=dict)
    sorted_paths: list[str] = field(default_factory=list)
    path_to_id: dict[str, int] = field(default_factory=dict)
    owner_rows: dict[str, int] = field(default_factory=dict)

    def subtree_size(self, prefix: str) -> int:
        """Rows whose path is *prefix* or lies under it (sorted-list bisect)."""
        lo = bisect.bisect_left(self.sorted_paths, prefix)
        hi = bisect.bisect_left(self.sorted_paths, prefix + "0")  # '0' is the byte after '/'
        exact = 1 if lo < len(self.sorted_paths) and self.sorted_paths[lo] == prefix else 0
        lo2 = bisect.bisect_left(self.sorted_paths, prefix + "/")
        return exact + (hi - lo2)

    def subtree_ids(self, prefix: str) -> list[int]:
        lo2 = bisect.bisect_left(self.sorted_paths, prefix + "/")
        hi = bisect.bisect_left(self.sorted_paths, prefix + "0")
        ids = [self.path_to_id[p] for p in self.sorted_paths[lo2:hi]]
        if prefix in self.path_to_id:
            ids.append(self.path_to_id[prefix])
        return ids

    def prefixes_of(self, principal: str, table: list[tuple[str, str, str]] | None = None) -> list[str]:
        table = self.grant_flat if table is None else table
        return sorted({pf for p, pf, _ in table if p == principal})

    def visible_count(self, principal: str) -> int:
        """Rows the grant rows alone make visible (owner rows excluded), deduplicated."""
        ids: set[int] = set()
        for pf in minimise(self.prefixes_of(principal)):
            ids.update(self.subtree_ids(pf))
        return len(ids)


def minimise(prefixes: list[str]) -> list[str]:
    """Drop every prefix already covered by a shallower one in the set."""
    out: list[str] = []
    for pf in sorted(prefixes):
        if not any(pf == o or pf.startswith(o + "/") for o in out):
            out.append(pf)
    return out


def intersect_prefixes(a: list[str], b: list[str]) -> list[str]:
    """Prefix set whose coverage is cover(a) ∩ cover(b): the deeper of each nested pair."""
    out: set[str] = set()
    for x in a:
        for y in b:
            if x == y or y.startswith(x + "/"):
                out.add(y)
            elif x.startswith(y + "/"):
                out.add(x)
    return minimise(sorted(out))


def build(n_files: int, seed: int = 20260905) -> Corpus:
    rng = random.Random(seed)
    top_w = zipf_weights(TOPS, 1.0)
    seg_w = zipf_weights(len(SEGMENTS), 2.0)
    depths = list(DEPTH_WEIGHTS)
    depth_w = list(DEPTH_WEIGHTS.values())
    exts = list(EXT_WEIGHTS)
    ext_w = list(EXT_WEIGHTS.values())
    principals = [f"p{i:05d}" for i in range(PRINCIPALS)]
    owner_w = zipf_weights(PRINCIPALS, 1.0)
    owner_of_dir2: dict[str, str] = {}

    files: list[tuple[str, str, str | None, int, int | None]] = []
    dirs: set[str] = set()
    tops = rng.choices(range(TOPS), weights=top_w, k=n_files)
    dks = rng.choices(depths, weights=depth_w, k=n_files)
    exs = rng.choices(exts, weights=ext_w, k=n_files)
    for i in range(n_files):
        d = dks[i]
        segs = [f"t{tops[i]:03d}"]
        for _ in range(d - 2):
            segs.append(SEGMENTS[rng.choices(range(len(SEGMENTS)), weights=seg_w, k=1)[0]])
        parent = "/" + "/".join(segs)
        for k in range(1, len(segs) + 1):
            dirs.add("/" + "/".join(segs[:k]))
        dir2 = "/" + "/".join(segs[:2]) if len(segs) >= 2 else parent
        owner = owner_of_dir2.get(dir2)
        if owner is None:
            owner = principals[rng.choices(range(PRINCIPALS), weights=owner_w, k=1)[0]]
            owner_of_dir2[dir2] = owner
        size = int(rng.lognormvariate(8.0, 1.2))
        deleted = 1 if rng.random() < 0.02 else None
        files.append((f"{parent}/f{i}.{exs[i]}", owner, exs[i], size, deleted))

    entries: list[tuple[int, str, str, str, str | None, int, int | None]] = []
    next_id = 1
    for dpath in sorted(dirs):
        segs = dpath.split("/")[1:]
        dir2 = "/" + "/".join(segs[:2]) if len(segs) >= 2 else None
        owner = owner_of_dir2.get(dir2, "p00000") if dir2 else "p00000"
        entries.append((next_id, dpath, owner, "dir", None, 0, None))
        next_id += 1
    for path, owner, ext, size, deleted in files:
        entries.append((next_id, path, owner, "file", ext, size, deleted))
        next_id += 1

    dir_list = sorted(dirs)
    by_depth: dict[int, list[str]] = {}
    for dpath in dir_list:
        by_depth.setdefault(dpath.count("/"), []).append(dpath)
    depth_pick = [(1, 5), (2, 30), (3, 35), (4, 15), (5, 10), (6, 5)]
    depth_pick = [(d, w) for d, w in depth_pick if d in by_depth]
    level_names = [n for n, _ in LEVELS]
    level_w = [w for _, w in LEVELS]

    direct: set[tuple[str, str, str]] = set()
    for p in principals:
        k = min(12, max(1, int(rng.expovariate(1 / 4.5)) + 1))
        for _ in range(k):
            d = rng.choices([d for d, _ in depth_pick], weights=[w for _, w in depth_pick], k=1)[0]
            pf = rng.choice(by_depth[d])
            direct.add((p, pf, rng.choices(level_names, weights=level_w, k=1)[0]))
    everyone_prefixes = [f"/t{r:03d}" for r in EVERYONE_TOP_RANKS]
    grant_flat = sorted(direct) + [(p, pf, "read") for pf in everyone_prefixes for p in principals]

    group_names = [f"g{i:03d}" for i in range(GROUPS)]
    group_w = zipf_weights(GROUPS, 1.0)
    member: list[tuple[str, str]] = []
    groups_of: dict[str, list[str]] = {}
    members_of: dict[str, list[str]] = {g: [] for g in group_names}
    for p in principals:
        k = min(5, int(rng.expovariate(1 / 2.0)))
        gs = sorted({group_names[g] for g in rng.choices(range(GROUPS), weights=group_w, k=k)})
        groups_of[p] = gs + ["g_all"]
        for g in gs:
            member.append((p, g))
            members_of[g].append(p)
        member.append((p, "g_all"))
    members_of["g_all"] = list(principals)
    group_grants: set[tuple[str, str, str]] = set()
    while len(group_grants) < 3_000:
        g = rng.choice(group_names)
        d = rng.choices([d for d, _ in depth_pick], weights=[w for _, w in depth_pick], k=1)[0]
        group_grants.add((g, rng.choice(by_depth[d]), rng.choices(level_names, weights=level_w, k=1)[0]))
    grant_g = sorted(direct) + [("g_all", pf, "read") for pf in everyone_prefixes] + sorted(group_grants)
    expanded: set[tuple[str, str, str]] = set(direct)
    for g, pf, lvl in grant_g:
        if g.startswith("g"):
            expanded.update((p, pf, lvl) for p in members_of[g])
    grant_gx = sorted(expanded)

    corpus = Corpus(entries, principals, grant_flat, grant_g, grant_gx, member, groups_of)
    corpus.sorted_paths = sorted(e[1] for e in entries)
    corpus.path_to_id = {e[1]: e[0] for e in entries}
    owner_rows: dict[str, int] = {}
    for e in entries:
        owner_rows[e[2]] = owner_rows.get(e[2], 0) + 1
    corpus.owner_rows = owner_rows
    return corpus


def ancestors(path: str) -> list[str]:
    """The path itself and every ancestor directory, shallowest first."""
    segs = path.split("/")[1:]
    return ["/" + "/".join(segs[:k]) for k in range(1, len(segs) + 1)]


def resolve_level(path: str, grants: dict[str, str]) -> str | None:
    """Longest-prefix level for *path* from a {prefix: level} map: the app-side point check."""
    for anc in reversed(ancestors(path)):
        if anc in grants:
            return grants[anc]
    return None
