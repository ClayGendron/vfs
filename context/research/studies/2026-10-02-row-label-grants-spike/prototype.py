"""Row-label grants: schema, labelling, relabel, compile, and statements. Study code only.

The shape under test. Every entry row carries two labels, written with
the row and relabelled when a posture or grant boundary changes:

- ``public_level`` — the level the nearest covering posture (``*``) row
  gives everyone: 0 none, 1 read, 2 read_write.
- ``domain_id`` — the id of the nearest covering *boundary*, a posture
  or grant prefix. Rows in one domain have identical coverage, so one
  domain id stands for every row's rights at once.

Visible, ``public_level`` variant:

    public_level >= :level  OR  path in the caller's ranges  OR  owner_id = :me

Visible, ``domain_id`` variant:

    domain_id IN (:domains the caller may see)  OR  owner_id = :me

The caller's ranges are the ADR 072 pieces (exact points + open ranges)
built from the caller's own grants only — no posture, no holes — with a
linear sorted merge; a subject set takes the sorted-merge intersection
of its members' spans. Nothing here is imported by vfs.
"""

from __future__ import annotations

import json
import time
from typing import Any, NamedTuple

from world import NONE, World

NEXT = "\x00"
ROOT = "/"
Span = tuple[str, str]  # half-open [lo, hi) in code point order (== UTF-8 byte order)


# ---------------------------------------------------------------------------
# Span algebra: cover, merge, intersect, subtract, split
# ---------------------------------------------------------------------------


def ancestors_and_self(path: str) -> list[str]:
    out = [path]
    while path != ROOT:
        path = path.rsplit("/", 1)[0] or ROOT
        out.append(path)
    return out


def cover(prefix: str) -> list[Span]:
    """The prefix row itself and everything beneath it, as two spans (the root is one)."""
    if prefix == ROOT:
        return [(ROOT, "0")]
    return [(prefix, prefix + NEXT), (prefix + "/", prefix + "0")]


def merge(spans: list[Span]) -> list[Span]:
    """Sorted, overlapping and touching spans joined — one linear pass after the sort."""
    out: list[Span] = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            if hi > out[-1][1]:
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return out


def intersect(a: list[Span], b: list[Span]) -> list[Span]:
    """The spans both merged lists cover — a two-pointer sweep."""
    out: list[Span] = []
    i = j = 0
    while i < len(a) and j < len(b):
        lo = max(a[i][0], b[j][0])
        hi = min(a[i][1], b[j][1])
        if lo < hi:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def subtract(keep: list[Span], cut: list[Span]) -> list[Span]:
    """The parts of merged *keep* no span of merged *cut* reaches — one linear sweep."""
    out: list[Span] = []
    j = 0
    for lo, hi in keep:
        cur = lo
        while j < len(cut) and cut[j][1] <= cur:
            j += 1
        k = j
        while k < len(cut) and cut[k][0] < hi:
            if cut[k][0] > cur:
                out.append((cur, cut[k][0]))
            cur = max(cur, cut[k][1])
            k += 1
        if cur < hi:
            out.append((cur, hi))
    return out


class Pieces(NamedTuple):
    """Exact paths (``path = p``) and open ranges (``lo < path < hi``) admitting the same rows."""

    points: list[str]
    opens: list[Span]


def split(spans: list[Span]) -> Pieces:
    """Half-open spans as exact points and open ranges; no bound ends in NEXT."""
    points: list[str] = []
    opens: list[Span] = []
    for lo, hi in spans:
        if hi == lo + NEXT:
            points.append(lo)
            continue
        low = lo
        if lo.endswith(NEXT):
            low = lo[:-1]
        elif lo == ROOT or not lo.endswith("/"):
            points.append(lo)
        high = hi
        if hi.endswith(NEXT):
            high = hi[:-1]
            points.append(high)
        if low < high:
            opens.append((low, high))
    return Pieces(points, opens)


def spans_of_prefixes(prefixes: list[str]) -> list[Span]:
    return merge([s for p in prefixes for s in cover(p)])


# ---------------------------------------------------------------------------
# Labels: the nearest posture and the nearest boundary of a path
# ---------------------------------------------------------------------------


class Domains:
    """The boundary table: one id per posture-or-grant prefix, with its public level."""

    def __init__(self, w: World) -> None:
        prefixes = sorted(set(w.star) | {p for _, p, _ in w.grants})
        self.id_of: dict[str, int] = {p: i + 1 for i, p in enumerate(prefixes)}
        self.path_of: dict[int, str] = {i: p for p, i in self.id_of.items()}
        self.public: dict[int, int] = {self.id_of[p]: public_level(w.star, p) for p in prefixes}

    def rows(self) -> list[tuple[int, str, int]]:
        return [(i, p, self.public[i]) for p, i in self.id_of.items()]


def public_level(star: dict[str, int], path: str) -> int:
    """The level of the deepest posture row covering *path*; nothing covering means none."""
    for a in ancestors_and_self(path):
        lvl = star.get(a)
        if lvl is not None:
            return lvl
    return NONE


def domain_of(domains: Domains, path: str) -> int:
    for a in ancestors_and_self(path):
        d = domains.id_of.get(a)
        if d is not None:
            return d
    raise KeyError(path)


def labels(w: World, domains: Domains) -> list[tuple[int, int]]:
    """``(public_level, domain_id)`` per row, in row order — what a write stamps."""
    return [(public_level(w.star, p), domain_of(domains, p)) for _, p, _ in w.rows]


# ---------------------------------------------------------------------------
# Truth: the spec's rules in plain Python, per row
# ---------------------------------------------------------------------------


def truth(w: World, subjects: list[str], level: int, *, anonymous: bool = False, system: bool = False) -> set[int]:
    """Every row id the caller may see at *level*, straight from the rules.

    A member's level on a path is the max of the deepest posture row and
    every named row (its own or its groups') covering the path. A set
    sees a row when every member does, or when a member owns it and
    every other member sees it. Anonymous holds the posture only and
    owns nothing. System sees all.
    """
    if system:
        return {rid for rid, _, _ in w.rows}
    named: dict[str, dict[str, int]] = {}
    for m in subjects:
        cov: dict[str, int] = {}
        for p in w.principals_of(m):
            for prefix, lvl in w.by_principal.get(p, ()):
                if lvl > cov.get(prefix, 0):
                    cov[prefix] = lvl
        named[m] = cov
    out: set[int] = set()
    for rid, path, owner in w.rows:
        chain = ancestors_and_self(path)
        pub = public_level(w.star, path)
        if anonymous or not subjects:
            if pub >= level:
                out.add(rid)
            continue
        levels = {m: max(pub, max((named[m].get(a, 0) for a in chain), default=0)) for m in subjects}
        if all(v >= level for v in levels.values()):
            out.add(rid)
        elif owner in levels and all(v >= level for m, v in levels.items() if m != owner):
            out.add(rid)
    return out


# ---------------------------------------------------------------------------
# Compile: a caller's grants as sorted pieces
# ---------------------------------------------------------------------------


class Compiled(NamedTuple):
    """The caller's rights as pieces: the shared arms, and per member the owner-floor pieces.

    An owner entry of ``None`` means the floor is the plain ``owner_id = me``.
    """

    arms: Pieces
    owners: list[tuple[str, Pieces | None]]
    bind_bytes: int
    compile_us: float


def member_spans(by_principal: dict[str, list[tuple[str, int]]], principals: list[str], level: int) -> list[Span]:
    prefixes = [prefix for p in principals for prefix, lvl in by_principal.get(p, ()) if lvl >= level]
    return spans_of_prefixes(prefixes)


def compile_rights(w: World, subjects: list[str], level: int) -> Compiled:
    """The caller's own grants, merged per member, met across members — linear in the grants."""
    t0 = time.perf_counter()
    spans = {m: member_spans(w.by_principal, w.principals_of(m), level) for m in subjects}
    arms: list[Span] = []
    owners: list[tuple[str, Pieces | None]] = []
    if subjects:
        arms = spans[subjects[0]]
        for m in subjects[1:]:
            arms = intersect(arms, spans[m])
        for m in subjects:
            others = [spans[o] for o in subjects if o != m]
            if not others:
                owners.append((m, None))
                continue
            met = others[0]
            for o in others[1:]:
                met = intersect(met, o)
            owners.append((m, split(met)))
    pieces = split(arms)
    us = (time.perf_counter() - t0) * 1e6
    payload = json.dumps([pieces.points, pieces.opens, [(m, p and [p.points, p.opens]) for m, p in owners]])
    return Compiled(pieces, owners, len(payload.encode()), us)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class Names(NamedTuple):
    e: str  # entries
    c: str  # chunks
    d: str  # domains
    g: str  # grants
    m: str  # memberships


def names(ns: str) -> Names:
    return Names(f"{ns}e", f"{ns}c", f"{ns}d", f"{ns}g", f"{ns}m")


def ddl(dialect: str, t: Names) -> list[str]:
    path = 'TEXT COLLATE "C"' if dialect == "postgresql" else "TEXT"
    big = "BIGINT" if dialect == "postgresql" else "INTEGER"
    return [
        f"CREATE TABLE {t.e} (id {big} PRIMARY KEY, path {path} NOT NULL, owner_id TEXT, "
        f"public_level SMALLINT NOT NULL, domain_id {big} NOT NULL)",
        f"CREATE TABLE {t.c} (id {big} PRIMARY KEY, entry_id {big} NOT NULL, score INTEGER NOT NULL)",
        f"CREATE TABLE {t.d} (id {big} PRIMARY KEY, path {path} NOT NULL, public_level SMALLINT NOT NULL)",
        f"CREATE TABLE {t.g} (principal_id TEXT NOT NULL, path_prefix {path} NOT NULL, level SMALLINT NOT NULL)",
        f"CREATE TABLE {t.m} (principal_id TEXT NOT NULL, group_id TEXT NOT NULL)",
    ]


def index_ddl(t: Names) -> dict[str, str]:
    """Index name → statement, in the order they are built (sizes are measured per index)."""
    return {
        f"{t.e}_path": f"CREATE UNIQUE INDEX {t.e}_path ON {t.e} (path)",
        f"{t.e}_owner": f"CREATE INDEX {t.e}_owner ON {t.e} (owner_id)",
        f"{t.e}_public": f"CREATE INDEX {t.e}_public ON {t.e} (public_level)",
        f"{t.e}_public_path": f"CREATE INDEX {t.e}_public_path ON {t.e} (public_level, path)",
        f"{t.e}_domain": f"CREATE INDEX {t.e}_domain ON {t.e} (domain_id)",
        f"{t.c}_entry": f"CREATE INDEX {t.c}_entry ON {t.c} (entry_id)",
        f"{t.c}_score": f"CREATE INDEX {t.c}_score ON {t.c} (score)",
        f"{t.d}_path": f"CREATE UNIQUE INDEX {t.d}_path ON {t.d} (path)",
        f"{t.d}_public": f"CREATE INDEX {t.d}_public ON {t.d} (public_level)",
        f"{t.g}_principal": f"CREATE INDEX {t.g}_principal ON {t.g} (principal_id)",
        f"{t.m}_principal": f"CREATE INDEX {t.m}_principal ON {t.m} (principal_id)",
    }


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


class Dialect:
    """The text SQLite and Postgres need to unpack one bound list into rows."""

    def __init__(self, name: str) -> None:
        self.name = name

    def points(self, key: str, values: list[str]) -> tuple[str, str, dict[str, Any]]:
        """``(FROM fragment, value expr, binds)`` for a list of exact paths."""
        if self.name == "postgresql":
            return f"unnest(CAST(:{key} AS text[])) AS {key}(value)", f'{key}.value COLLATE "C"', {key: values}
        return f"json_each(:{key}) AS {key}", f"{key}.value", {key: json.dumps(values)}

    def opens(self, key: str, spans: list[Span]) -> tuple[str, str, str, dict[str, Any]]:
        """``(FROM fragment, lo expr, hi expr, binds)`` for a list of open ranges."""
        if self.name == "postgresql":
            frag = f"unnest(CAST(:{key}_lo AS text[]), CAST(:{key}_hi AS text[])) AS {key}(lo, hi)"
            binds = {f"{key}_lo": [lo for lo, _ in spans], f"{key}_hi": [hi for _, hi in spans]}
            return frag, f'{key}.lo COLLATE "C"', f'{key}.hi COLLATE "C"', binds
        frag = f"json_each(:{key}) AS {key}"
        return frag, f"{key}.value ->> 0", f"{key}.value ->> 1", {key: json.dumps(spans)}

    def points_pred(self, col: str, key: str, values: list[str]) -> tuple[str, dict[str, Any]]:
        if self.name == "postgresql":
            return f"{col} = ANY(CAST(:{key} AS text[]))", {key: values}
        return f"{col} IN (SELECT value FROM json_each(:{key}))", {key: json.dumps(values)}

    def opens_pred(self, col: str, key: str, spans: list[Span]) -> tuple[str, dict[str, Any]]:
        frag, lo, hi, binds = self.opens(key, spans)
        return f"EXISTS (SELECT 1 FROM {frag} WHERE {col} > {lo} AND {col} < {hi})", binds

    def ints_pred(self, col: str, key: str, values: list[int]) -> tuple[str, dict[str, Any]]:
        if self.name == "postgresql":
            return f"{col} = ANY(CAST(:{key} AS bigint[]))", {key: values}
        return f"{col} IN (SELECT value FROM json_each(:{key}))", {key: json.dumps(values)}


class Caller(NamedTuple):
    compiled: Compiled | None  # None for anonymous and system
    anonymous: bool
    system: bool
    domains: list[int] | None = None  # the domain variant's list, when computed
    owner_domains: dict[str, list[int]] | None = None  # per member: the others' domains


def visible_sql(
    d: Dialect, t: Names, variant: str, caller: Caller, level: int, scope: Span | None = None
) -> tuple[str, dict[str, Any]]:
    """The visible entry ids as a UNION of index-seeking branches, and the binds."""
    params: dict[str, Any] = {"lvl": level}
    scoped = ""
    if scope is not None:
        scoped = " AND e.path > :slo AND e.path < :shi"
        params |= {"slo": scope[0], "shi": scope[1]}
    if caller.system:
        return f"SELECT e.id FROM {t.e} e WHERE 1=1{scoped}", params
    branches: list[str] = []
    if variant == "public":
        branches.append(f"SELECT e.id FROM {t.e} e WHERE e.public_level >= :lvl{scoped}")
    else:
        assert caller.domains is not None
        pred, binds = d.ints_pred("e.domain_id", "dom", caller.domains)
        params |= binds
        branches.append(f"SELECT e.id FROM {t.e} e WHERE {pred}{scoped}")
    if caller.anonymous or caller.compiled is None:
        return branches[0], params

    def range_branches(key: str, pieces: Pieces, where: str) -> None:
        if pieces.points:
            frag, value, binds = d.points(f"{key}p", pieces.points)
            params.update(binds)
            branches.append(f"SELECT e.id FROM {frag} JOIN {t.e} e ON e.path = {value}{where}{scoped}")
        if pieces.opens:
            frag, lo, hi, binds = d.opens(f"{key}r", pieces.opens)
            params.update(binds)
            branches.append(f"SELECT e.id FROM {frag} JOIN {t.e} e ON e.path > {lo} AND e.path < {hi}{where}{scoped}")

    if variant == "public":
        range_branches("a", caller.compiled.arms, "")
    for n, (owner, pieces) in enumerate(caller.compiled.owners):
        params[f"o{n}"] = owner
        if pieces is None:
            branches.append(f"SELECT e.id FROM {t.e} e WHERE e.owner_id = :o{n}{scoped}")
        elif variant == "public":
            range_branches(f"o{n}", pieces, f" WHERE e.owner_id = :o{n}")
        else:
            assert caller.owner_domains is not None
            pred, binds = d.ints_pred("e.domain_id", f"od{n}", caller.owner_domains[owner])
            params |= binds
            branches.append(f"SELECT e.id FROM {t.e} e WHERE e.owner_id = :o{n} AND {pred}{scoped}")
    return " UNION ".join(branches), params


def probe_predicate(d: Dialect, t: Names, variant: str, caller: Caller, level: int) -> tuple[str, dict[str, Any]]:
    """The same visibility as one inline predicate on ``e`` — for a top-k that walks the score index."""
    params: dict[str, Any] = {"lvl": level}
    if caller.system:
        return "1=1", params
    terms: list[str] = []
    if variant == "public":
        terms.append("e.public_level >= :lvl")
    else:
        assert caller.domains is not None
        pred, binds = d.ints_pred("e.domain_id", "dom", caller.domains)
        params |= binds
        terms.append(pred)
    if caller.anonymous or caller.compiled is None:
        return terms[0], params

    def range_terms(key: str, pieces: Pieces) -> list[str]:
        out: list[str] = []
        if pieces.points:
            pred, binds = d.points_pred("e.path", f"{key}p", pieces.points)
            params.update(binds)
            out.append(pred)
        if pieces.opens:
            pred, binds = d.opens_pred("e.path", f"{key}r", pieces.opens)
            params.update(binds)
            out.append(pred)
        return out

    if variant == "public":
        terms += range_terms("a", caller.compiled.arms)
    for n, (owner, pieces) in enumerate(caller.compiled.owners):
        params[f"o{n}"] = owner
        if pieces is None:
            terms.append(f"e.owner_id = :o{n}")
        elif variant == "public":
            inner = range_terms(f"o{n}", pieces)
            if inner:
                terms.append(f"(e.owner_id = :o{n} AND ({' OR '.join(inner)}))")
        else:
            assert caller.owner_domains is not None
            pred, binds = d.ints_pred("e.domain_id", f"od{n}", caller.owner_domains[owner])
            params |= binds
            terms.append(f"(e.owner_id = :o{n} AND {pred})")
    return "(" + " OR ".join(terms) + ")", params


def statements(
    d: Dialect, t: Names, variant: str, caller: Caller, level: int, scope: Span
) -> dict[str, tuple[str, dict[str, Any]]]:
    """The statement shapes timed per caller: entries, scoped entries, chunk count, top 10, top 10 by probe."""
    visible, params = visible_sql(d, t, variant, caller, level)
    scoped, sparams = visible_sql(d, t, variant, caller, level, scope)
    pred, pparams = probe_predicate(d, t, variant, caller, level)
    derived = f"FROM ({visible}) v JOIN {t.c} c ON c.entry_id = v.id"
    return {
        "entries": (visible, params),
        "scoped": (scoped, sparams),
        "count": (f"SELECT count(*) {derived}", params),
        "top10": (f"SELECT c.id {derived} ORDER BY c.score LIMIT 10", params),
        "top10 probe": (
            f"SELECT c.id FROM {t.c} c JOIN {t.e} e ON e.id = c.entry_id WHERE {pred} ORDER BY c.score LIMIT 10",
            pparams,
        ),
    }


def domain_list_sql(d: Dialect, t: Names, pieces: Pieces | None, level: int) -> tuple[str, dict[str, Any]]:
    """The domain variant's compile: every domain the caller may see — public ones plus granted ones."""
    params: dict[str, Any] = {"lvl": level}
    branches = [f"SELECT d.id FROM {t.d} d WHERE d.public_level >= :lvl"]
    if pieces is not None:
        if pieces.points:
            frag, value, binds = d.points("dp", pieces.points)
            params |= binds
            branches.append(f"SELECT d.id FROM {frag} JOIN {t.d} d ON d.path = {value}")
        if pieces.opens:
            frag, lo, hi, binds = d.opens("dr", pieces.opens)
            params |= binds
            branches.append(f"SELECT d.id FROM {frag} JOIN {t.d} d ON d.path > {lo} AND d.path < {hi}")
    return " UNION ".join(branches), params


# ---------------------------------------------------------------------------
# Relabel: the ranges a posture or boundary change must rewrite
# ---------------------------------------------------------------------------


def relabel_spans(prefix: str, deeper_boundaries: list[str]) -> list[Span]:
    """The rows whose nearest boundary is *prefix*: its cover minus every deeper boundary's cover."""
    return subtract(cover(prefix), spans_of_prefixes(deeper_boundaries))


def span_where(lo: str, hi: str) -> tuple[str, dict[str, Any]]:
    """A half-open span as a WHERE on ``path``: an exact row, or an inclusive-exclusive range."""
    if hi == lo + NEXT:
        return "path = :lo", {"lo": lo}
    return "path >= :lo AND path < :hi", {"lo": lo, "hi": hi}
