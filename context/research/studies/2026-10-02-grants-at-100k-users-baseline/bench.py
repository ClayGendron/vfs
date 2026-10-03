"""The shipped grants design at N users — where it breaks, and why, number by number.

The world comes from ``world.py`` (one private home per user, dozens of
shared folders per user through groups). It is written straight into a
``DatabaseStorage`` mount's own tables with the shipped ``bulk_insert``,
so every measurement below runs the shipped code paths:

1. ``resolve_authority`` cold (the rows read plus two ``resolve`` calls),
   the pure ``resolve`` alone, and a warm cache hit — per caller.
2. ``Rights.ranges()`` (``pieces``) time, piece count, JSON bind bytes.
   A study-side linear ``fast_pieces`` is checked equal to the shipped
   output where the shipped one finishes, and stands in for it where
   it does not, so the engine side can still be measured.
3. The range join (``visible_entries``) — count and fetch, cold and
   warm, with the engine's plan.
4. The clause fan (``visibility_clauses``) — binds and terms per clause,
   latency or the failure text; plus a hole ladder to find the wall.
5. ``tree('/')``, ``glob('/shared/*/*.md')``, ``ls('/home')`` end to end
   through ``DatabaseStorage`` in a subprocess per call, so a runaway
   verb is killed at the cap instead of eating the run.
6. Cache churn: how many cached callers one grant write discards.
7. Memory: deep size of one cached ``Resolution`` before and after ranges.
8. ``Rights.admits`` per row by row shape — the hidden cost every
   row-check loop pays.

    uv run --no-sync python bench.py --engine sqlite --n 1000 --sweep
    uv run --no-sync python bench.py --engine postgres --url postgresql+asyncpg://... --n 10000

Writes ``runs/<engine>-<N>.md`` and ``runs/<engine>-<N>.json``. Study
code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import signal
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable
from ulid import ULID

from vfs.authority import Authority, Principal
from vfs.paths import Path
from vfs.storage.backends.database.backend import DatabaseStorage
from vfs.storage.backends.database.dialects import bulk_insert
from vfs.storage.backends.database.ranges import visible_entries
from vfs.storage.backends.database.rights import (
    RightsCache,
    _closures,
    _grant_rows,
    resolve_authority,
    visibility_clauses,
)
from vfs.storage.grants import (
    Arm,
    GrantRow,
    Pieces,
    Ranges,
    Rights,
    _everyone_arms,
    _merged,
    _spans,
    _split,
    ancestors_and_self,
    pieces,
    resolve,
)
from world import GROUPS_PER_USER, build, home_of

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = "/Users/claygendron/.claude/jobs/b627c391/tmp/research/baseline"
SYSTEM = Authority.system()
ORDINARY = "u000007"
PAIR = ("u000007", "u000008")
E2E_VERBS = ("tree /", "glob /shared/*/*.md", "ls /home")
SAMPLE_ROWS = 1_000


class StepTimeout(Exception):
    """A capped pure-Python step ran past its budget."""


@contextmanager
def capped(seconds: float):  # noqa: ANN201
    """Raise ``StepTimeout`` inside synchronous Python after *seconds* — never around an ``await``."""

    def handler(signum: int, frame: Any) -> None:
        raise StepTimeout

    old = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


class _Explain(Executable, ClauseElement):
    inherit_cache = False

    def __init__(self, stmt: Any, prefix: str) -> None:
        self.stmt = stmt
        self.prefix = prefix


@compiles(_Explain)
def _compile_explain(element: _Explain, compiler: Any, **kw: Any) -> str:
    return element.prefix + " " + compiler.process(element.stmt, **kw)


# ---------------------------------------------------------------------------
# Study-side linear pieces and a set-based admits oracle
# ---------------------------------------------------------------------------


def subtract_linear(keep: list[tuple[str, str]], cut: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """``keep`` minus ``cut``, both merged and sorted — one sweep, two pointers."""
    out: list[tuple[str, str]] = []
    j = 0
    for lo, hi in keep:
        cur = lo
        while j < len(cut) and cut[j][1] <= cur:
            j += 1
        k = j
        while k < len(cut) and cut[k][0] < hi:
            clo, chi = cut[k]
            if clo > cur:
                out.append((cur, clo))
            cur = max(cur, chi)
            if chi >= hi:
                break
            k += 1
        if cur < hi:
            out.append((cur, hi))
    return out


def fast_pieces(arms: Any) -> Pieces:
    """The same answer as ``vfs.storage.grants.pieces``, in O(H log H) per arm."""
    spans: list[tuple[str, str]] = []
    for arm in arms:
        keep = _merged(_spans(arm.prefix))
        cut = _merged([span for hole in arm.holes for span in _spans(hole)])
        spans += subtract_linear(keep, cut)
    return _split(_merged(spans))


def fast_ranges(rights: Rights) -> Ranges:
    owners = tuple((arm.owner, fast_pieces(Arm(p) for p in arm.prefixes)) for arm in rights.owner_arms)
    return Ranges(fast_pieces(rights.arms), owners)


class FastAdmits:
    """``Rights.admits`` with the holes in sets — the oracle for whole-table recall."""

    def __init__(self, rights: Rights) -> None:
        self.whole = rights.whole
        self.arms = {arm.prefix: frozenset(arm.holes) for arm in rights.arms}
        self.owned = rights._owned  # noqa: SLF001

    def __call__(self, path: str, owner: str | None) -> bool:
        if self.whole:
            return True
        chain = ancestors_and_self(path)
        for ancestor in chain:
            holes = self.arms.get(ancestor)
            if holes is not None and not any(a in holes for a in chain):
                return True
        if owner is None:
            return False
        prefixes = self.owned.get(owner)
        return prefixes is not None and any(a in prefixes for a in chain)


# ---------------------------------------------------------------------------
# Callers and the world load
# ---------------------------------------------------------------------------


def callers(world: Any) -> dict[str, Authority]:
    heavy = world.heavy_user()
    return {
        "ordinary": Authority.of(Principal(ORDINARY)),
        f"heavy ({heavy})": Authority.of(Principal(heavy)),
        "pair": Authority.on_behalf_of({Principal(p) for p in PAIR}, actor=Principal("agent", kind="service")),
        "anonymous": Authority.anonymous(),
        "system": SYSTEM,
    }


def caller_named(world: Any, label: str) -> Authority:
    for name, authority in callers(world).items():
        if name == label or name.startswith(label + " "):
            return authority
    raise KeyError(label)


def url_for(engine: str, url: str | None, ns: str) -> str:
    if engine == "sqlite":
        return f"sqlite+aiosqlite:///{os.path.join(SCRATCH, f'{ns}.sqlite')}"
    assert url, "postgres needs --url"
    return url


async def load(storage: DatabaseStorage, world: Any, log: Any) -> dict[str, float]:
    """The world into the mount's own tables: entries, grants, memberships; then ANALYZE."""
    host = storage._host  # noqa: SLF001
    tables = host.tables
    now = datetime.now(UTC)
    timings: dict[str, float] = {}
    async with host.session_factory() as session:
        root_id = (await session.execute(select(tables.entry.c.entry_id).where(tables.entry.c.path == "/"))).scalar_one()
    ids = {"/": root_id}
    counter = 1
    t0 = time.perf_counter()
    async with host.session_factory() as session, session.begin():
        batch: list[dict[str, Any]] = []
        for row in world.entries():
            if row.path == "/":
                continue
            entry_id = str(ULID.from_int(counter))
            counter += 1
            if row.kind == "directory":
                ids[row.path] = entry_id
            batch.append(
                {
                    "entry_id": entry_id,
                    "parent_id": ids[row.parent],
                    "path": row.path,
                    "name": row.path.rsplit("/", 1)[1],
                    "kind": row.kind,
                    "version": 1,
                    "ext": "md" if row.kind == "file" else None,
                    "lines": 1,
                    "size_bytes": 8,
                    "chunked": False,
                    "encoded": False,
                    "indexable": False,
                    "owner_id": row.owner,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if len(batch) >= 20_000:
                await bulk_insert(session, tables.entry, batch)
                batch = []
        if batch:
            await bulk_insert(session, tables.entry, batch)
    timings["entries_s"] = time.perf_counter() - t0
    log(f"  entries loaded: {counter - 1:,} rows in {timings['entries_s']:.0f}s")
    t0 = time.perf_counter()
    async with host.session_factory() as session, session.begin():
        rows = [
            {
                "principal_id": g.principal_id,
                "path_prefix": g.path_prefix,
                "level": g.level,
                "granted_by": "system",
                "granted_at": now,
                "revision": 0,
            }
            for g in world.grants
            if not (g.principal_id == "*" and g.path_prefix == "/")
        ]
        for i in range(0, len(rows), 50_000):
            await bulk_insert(session, tables.grants, rows[i : i + 50_000])
        members = [
            {"principal_id": user, "group_id": group, "granted_by": "system", "granted_at": now}
            for user, groups in world.member_of.items()
            for group in groups
        ]
        for i in range(0, len(members), 50_000):
            await bulk_insert(session, tables.memberships, members[i : i + 50_000])
    timings["grants_s"] = time.perf_counter() - t0
    log(f"  grants {len(rows):,} + memberships {len(members):,} loaded in {timings['grants_s']:.0f}s")
    t0 = time.perf_counter()
    async with host.session_factory() as session, session.begin():
        for table in (tables.entry, tables.grants, tables.memberships):
            await session.execute(text(f"ANALYZE {table.name}"))
    timings["analyze_s"] = time.perf_counter() - t0
    return timings


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def ms(seconds: float) -> float:
    return round(seconds * 1000, 2)


async def measure_resolution(storage: DatabaseStorage, authority: Authority, reps: int) -> dict[str, Any]:
    host = storage._host  # noqa: SLF001
    cold: list[float] = []
    resolution = None
    for _ in range(reps):
        cache = RightsCache()
        async with host.session_factory() as session:
            t0 = time.perf_counter()
            resolution = await resolve_authority(
                session, host.tables, host.profile, host.membership_budget, authority, cache
            )
            cold.append(time.perf_counter() - t0)
    assert resolution is not None and not hasattr(resolution, "kind")
    cache = RightsCache()
    async with host.session_factory() as session:
        await resolve_authority(session, host.tables, host.profile, host.membership_budget, authority, cache)
        t0 = time.perf_counter()
        await resolve_authority(session, host.tables, host.profile, host.membership_budget, authority, cache)
        warm = time.perf_counter() - t0
    out: dict[str, Any] = {
        "cold_ms": ms(statistics.median(cold)),
        "warm_hit_ms": ms(warm),
        "read_arms": len(resolution.read.arms),
        "read_holes": sum(len(a.holes) for a in resolution.read.arms),
        "owner_arms": len(resolution.read.owner_arms),
        "whole": resolution.read.whole,
    }
    if authority.is_system:
        return out | {"resolution": resolution}
    # The pure resolver on the rows the storage would hand it.
    subjects = authority.subject_names
    async with host.session_factory() as session:
        if authority.is_anonymous:
            closures = {sub: frozenset() for sub in subjects}
        else:
            walked = await _closures(session, host.tables, host.profile, host.membership_budget, subjects)
            assert isinstance(walked, dict)
            closures = walked
        ids = sorted({*subjects, "*", *(g for gs in closures.values() for g in gs)})
        rows = await _grant_rows(session, host.tables, host.profile, host.membership_budget, ids)
    pure: list[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        resolve(closures, rows, "read", owner_floor=not authority.is_anonymous)
        pure.append(time.perf_counter() - t0)
    star = {row.path_prefix: row.level for row in rows if row.principal_id == "*"}
    t0 = time.perf_counter()
    _everyone_arms(star, 1)
    out["everyone_arms_ms"] = ms(time.perf_counter() - t0)
    out["pure_resolve_read_ms"] = ms(statistics.median(pure))
    out["rows_read"] = len(rows)
    out["groups"] = sum(len(g) for g in closures.values())
    return out | {"resolution": resolution}


def fresh(rights: Rights) -> Rights:
    return Rights(rights.level, rights.arms, rights.owner_arms, rights.whole)


def measure_pieces(rights: Rights, cap: float, reps: int, *, skip_shipped: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    samples: list[float] = []
    shipped: Ranges | None = None
    for _ in range(0 if skip_shipped else reps):
        r = fresh(rights)
        try:
            with capped(cap):
                t0 = time.perf_counter()
                shipped = r.ranges()
                samples.append(time.perf_counter() - t0)
        except StepTimeout:
            out["shipped_ms"] = f"timed out at {cap:.0f}s"
            break
        if samples[-1] > 2.0:
            break  # one sample is enough past two seconds; the curve is what matters
    if skip_shipped:
        out["shipped_ms"] = "skipped: same holes as a caller that timed out"
    if samples:
        out["shipped_ms"] = ms(statistics.median(samples)) if len(samples) > 1 else ms(samples[0])
    t0 = time.perf_counter()
    fast = fast_ranges(rights)
    out["fast_ms"] = ms(time.perf_counter() - t0)
    out["fast_equals_shipped"] = (shipped == fast) if shipped is not None else "not checked (shipped timed out)"
    found = shipped if shipped is not None else fast
    out["points"] = len(found.arms.points)
    out["opens"] = len(found.arms.opens)
    out["owner_pieces"] = sum(len(p.points) + len(p.opens) for _, p in found.owners)
    out["bind_bytes"] = len(json.dumps(list(found.arms.points))) + len(json.dumps([list(p) for p in found.arms.opens]))
    return out | {"ranges": found}


async def time_statement(storage: DatabaseStorage, stmt: Any, reps: int, cap: float, *, scalar: bool) -> dict[str, Any]:
    """Cold = first run on a fresh session; warm = median of *reps* more (``reps=0``: cold only)."""
    host = storage._host  # noqa: SLF001
    samples: list[float] = []
    answer: Any = None
    for i in range(reps + 1):
        async with host.session_factory() as session:
            if host.profile.name == "postgresql":
                # A server-side cap too: a cancelled asyncpg statement can outlive its client.
                await session.execute(text(f"SET statement_timeout = {int(cap * 1000)}"))
            t0 = time.perf_counter()
            try:
                result = await asyncio.wait_for(session.execute(stmt), cap)
                answer = result.scalar_one() if scalar else [row[0] for row in result]
            except TimeoutError:
                return {"cold_ms": f"timed out at {cap:.0f}s", "warm_ms": None, "answer": None}
            except Exception as exc:  # noqa: BLE001 — the failure text is the finding
                return {"cold_ms": None, "warm_ms": None, "answer": None, "error": _first_line(exc)}
            dt = time.perf_counter() - t0
        if i == 0:
            cold = dt
        else:
            samples.append(dt)
    return {"cold_ms": ms(cold), "warm_ms": ms(statistics.median(samples)) if samples else None, "answer": answer}


async def plan_of(storage: DatabaseStorage, stmt: Any) -> str:
    host = storage._host  # noqa: SLF001
    prefix = "EXPLAIN (ANALYZE, BUFFERS)" if host.profile.name == "postgresql" else "EXPLAIN QUERY PLAN"
    async with host.session_factory() as session:
        try:
            rows = (await session.execute(_Explain(stmt, prefix))).all()
        except Exception as exc:  # noqa: BLE001
            return f"plan unavailable: {_first_line(exc)}"
    return "\n".join(str(row[-1]) for row in rows)


def _first_line(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"


def _terms(expr: Any) -> int:
    kids = list(expr.get_children())
    return 1 if not kids else sum(_terms(k) for k in kids)


async def measure_fan(storage: DatabaseStorage, rights: Rights, reps: int, cap: float) -> dict[str, Any]:
    host = storage._host  # noqa: SLF001
    entry = host.tables.entry
    t0 = time.perf_counter()
    clauses = visibility_clauses(entry, rights, host.profile, host.parameter_budget)
    build_s = time.perf_counter() - t0
    if clauses is None:
        return {"clauses": None, "note": "whole: no predicate"}
    out: dict[str, Any] = {"clauses": len(clauses), "build_ms": ms(build_s), "per_clause": []}
    total = 0
    holes = sum(len(a.holes) for a in rights.arms)
    for clause in clauses:
        stmt = select(func.count()).select_from(entry).where(clause.predicate)
        if host.profile.name == "postgresql" and 2_000 < holes and clause.binds <= 32_767:
            # Measured: past ~5,000 holes the backend wedges for minutes and ignores
            # statement_timeout and pg_terminate_backend. Not sent; see the ladder.
            timed = {"cold_ms": None, "warm_ms": None, "answer": None, "error": "not sent: 2,000 < holes and binds under the 32,767 driver cap (the backend wedges; see the hole ladder)"}
        else:
            timed = await time_statement(storage, stmt, reps, cap, scalar=True)
        if timed.get("answer") is not None:
            total += timed["answer"]
        out["per_clause"].append({"binds": clause.binds, "terms": _terms(clause.predicate)} | timed)
    out["count_sum"] = total
    return out


async def hole_ladder(storage: DatabaseStorage, ladder: list[int], cap: float) -> list[dict[str, Any]]:
    """One root arm with H holes through the clause fan: the first H that fails or passes 1 s."""
    host = storage._host  # noqa: SLF001
    entry = host.tables.entry
    out = []
    for h in ladder:
        rows = [GrantRow("*", "/", "read_write"), *(GrantRow("*", f"/home/u{i:06d}", "none") for i in range(h))]
        rights = resolve({"x": frozenset()}, rows, "read")
        clauses = visibility_clauses(entry, rights, host.profile, host.parameter_budget) or []
        stmt = select(func.count()).select_from(entry).where(clauses[0].predicate)
        timed = await time_statement(storage, stmt, 0, cap, scalar=True)
        out.append({"holes": h, "binds": clauses[0].binds, "clauses": len(clauses)} | timed)
        print(f"- ladder {out[-1]}", flush=True)
    return out


def measure_admits(rights: Rights, world: Any, user: str) -> dict[str, Any]:
    shared = world.shared[-1]
    probes = {
        "own home file": (f"{home_of(user)}/note000.md", user),
        "shared file (root arm)": (f"{shared}/doc000.md", None),
        "another user's home file (hidden)": (f"{home_of(world.users[-1])}/note000.md", world.users[-1]),
        "trap file": (f"{home_of(world.users[0])}-x/trap.md", None),
    }
    out: dict[str, Any] = {}
    for label, (path, owner) in probes.items():
        samples = []
        for _ in range(7):
            t0 = time.perf_counter()
            admitted = rights.admits(path, owner)
            samples.append(time.perf_counter() - t0)
        out[label] = {"us": round(statistics.median(samples) * 1e6, 1), "admitted": admitted}
    return out


def deep_size(obj: Any, seen: set[int] | None = None) -> int:
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return 0
    seen.add(id(obj))
    size = sys.getsizeof(obj)
    if isinstance(obj, (str, bytes, int, float, bool, type(None))):
        return size
    if isinstance(obj, dict):
        return size + sum(deep_size(k, seen) + deep_size(v, seen) for k, v in obj.items())
    if isinstance(obj, (list, tuple, set, frozenset)):
        return size + sum(deep_size(x, seen) for x in obj)
    for klass in type(obj).__mro__:
        for slot in getattr(klass, "__slots__", ()):
            if hasattr(obj, slot):
                size += deep_size(getattr(obj, slot), seen)
    if hasattr(obj, "__dict__"):
        size += deep_size(vars(obj), seen)
    return size


async def measure_churn(storage: DatabaseStorage, world: Any, users: int) -> dict[str, Any]:
    """Resolve *users* callers into one cache, write one grant, resolve again: how many missed."""
    host = storage._host  # noqa: SLF001
    cache = RightsCache()
    keys = []
    for user in world.users[:users]:
        authority = Authority.of(Principal(user))
        async with host.session_factory() as session:
            res = await resolve_authority(session, host.tables, host.profile, host.membership_budget, authority, cache)
            keys.append((authority.subject_names, res.revision))
    before = len(cache._entries)  # noqa: SLF001
    written = await storage.grant(path=Path(world.shared[0]), principal="u000001", level="read", authority=SYSTEM)
    assert written.success, written.errors
    misses = 0
    t0 = time.perf_counter()
    for user in world.users[:users]:
        authority = Authority.of(Principal(user))
        async with host.session_factory() as session:
            revision = await resolve_authority(
                session, host.tables, host.profile, host.membership_budget, authority, cache
            )
            if (authority.subject_names, revision.revision) not in keys:
                misses += 1
    recompute_s = time.perf_counter() - t0
    revoked = await storage.revoke(path=Path(world.shared[0]), principal="u000001", authority=SYSTEM)
    assert revoked.success, revoked.errors
    return {
        "cached_before": before,
        "callers": users,
        "misses_after_one_grant": misses,
        "recompute_s_for_callers": round(recompute_s, 3),
        "cache_capacity": 256,
    }


def meet_ladder(cap: float) -> list[dict[str, Any]]:
    """Out of world: the pair meet over a group holding G grants (the review's finding 7 shape)."""
    out = []
    for g in (1_000, 3_000, 10_000):
        rows = [GrantRow("*", "/", "none"), *(GrantRow("group:eng", f"/p/p{i:05d}", "read") for i in range(g))]
        t0 = time.perf_counter()
        resolve({"u1": frozenset({"group:eng"})}, rows, "read")
        single = time.perf_counter() - t0
        try:
            with capped(cap):
                t0 = time.perf_counter()
                resolve({"u1": frozenset({"group:eng"}), "u2": frozenset({"group:eng"})}, rows, "read")
                pair: Any = ms(time.perf_counter() - t0)
        except StepTimeout:
            pair = f"timed out at {cap:.0f}s"
        out.append({"grants": g, "single_ms": ms(single), "pair_ms": pair})
    return out


# ---------------------------------------------------------------------------
# End to end, one verb per subprocess
# ---------------------------------------------------------------------------


async def e2e_child(args: argparse.Namespace) -> None:
    world = build(args.n, files_per_home=args.files_per_home, files_per_shared=args.files_per_shared)
    authority = caller_named(world, args.caller)
    storage = DatabaseStorage(url=url_for(args.engine, args.url, args.ns), table_name=args.ns, posture="open")
    out: dict[str, Any] = {}
    try:
        await storage.first_touch()
        for label in ("cold", "warm"):
            t0 = time.perf_counter()
            if args.verb == "tree /":
                result = await storage.tree(path=Path("/"), authority=authority)
            elif args.verb == "glob /shared/*/*.md":
                result = await storage.glob(patterns=("/shared/*/*.md",), authority=authority)
            else:
                result = await storage.ls(path=Path("/home"), authority=authority)
            out[label] = {
                "ms": ms(time.perf_counter() - t0),
                "rows": len(result.observations),
                "errors": [f"{e.kind}: {e.message[:120]}" for e in result.errors][:3],
            }
    finally:
        await storage.close()
    print(json.dumps(out))


def run_e2e(engine: str, url: str | None, ns: str, n: int, fph: int, fps: int, caller: str, verb: str, cap: float) -> dict[str, Any]:
    cmd = [
        sys.executable, os.path.abspath(__file__), "--e2e", "--engine", engine, "--ns", ns, "--n", str(n),
        "--files-per-home", str(fph), "--files-per-shared", str(fps), "--caller", caller, "--verb", verb,
    ]
    if url:
        cmd += ["--url", url]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=cap, check=False)  # noqa: S603
    except subprocess.TimeoutExpired:
        return {"timed_out_s": cap}
    if done.returncode != 0:
        tail = (done.stderr or "").strip().splitlines()[-1:] or ["?"]
        return {"failed": tail[0][:200]}
    return json.loads(done.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> None:
    ns = f"bl_{uuid4().hex[:8]}"
    started = time.perf_counter()
    lines: list[str] = []
    data: dict[str, Any] = {"engine": args.engine, "n": args.n, "ns": ns}

    def log(line: str) -> None:
        print(line, flush=True)
        lines.append(line)

    world = build(args.n, files_per_home=args.files_per_home, files_per_shared=args.files_per_shared)
    data["world"] = {
        "users": len(world.users), "groups": len(world.groups), "shared": len(world.shared),
        "grant_rows": len(world.grants), "memberships": len(world.users) * GROUPS_PER_USER,
        "entries": world.entry_count(), "files_per_home": args.files_per_home, "files_per_shared": args.files_per_shared,
    }
    log(f"# {args.engine} — N={args.n:,}: {data['world']}")
    storage = DatabaseStorage(url=url_for(args.engine, args.url, ns), table_name=ns, posture="open")
    try:
        touched = await storage.first_touch()
        assert touched.success, touched.errors
        data["load"] = await load(storage, world, log)
        host = storage._host  # noqa: SLF001
        entry = host.tables.entry
        who = callers(world)
        if args.ladder_only:
            ladder = [1_000, 2_000, 5_000, 10_000, 16_383, 16_384, 20_000, 32_000]
            data["ladder"] = await hole_ladder(storage, ladder, args.cap)
            with open(os.path.join(HERE, "runs", f"{args.engine}-ladder.json"), "w") as f:
                json.dump(data, f, indent=1, default=str)
            return

        # 1. Resolution.
        log("\n## 1. resolve")
        resolutions: dict[str, Any] = {}
        data["resolve"] = {}
        for label, authority in who.items():
            r = await measure_resolution(storage, authority, args.reps)
            resolutions[label] = r.pop("resolution")
            data["resolve"][label] = r
            log(f"- {label}: {r}")

        # 2. Pieces.
        log("\n## 2. ranges()/pieces (read rights)")
        data["pieces"] = {}
        ranges_of: dict[str, Ranges] = {}
        timed_out_holes: set[int] = set()
        for label, resolution in resolutions.items():
            if resolution.read.whole:
                log(f"- {label}: whole, no pieces")
                continue
            holes = sum(len(a.holes) for a in resolution.read.arms)
            p = measure_pieces(resolution.read, args.cap, args.reps, skip_shipped=holes in timed_out_holes)
            if str(p["shipped_ms"]).startswith("timed out"):
                timed_out_holes.add(holes)
            ranges_of[label] = p.pop("ranges")
            data["pieces"][label] = p
            log(f"- {label}: {p}")

        # 3. The range join.
        log("\n## 3. range join (visible_entries)")
        data["join"] = {}
        source = host.profile.range_source
        assert source is not None
        for label, found in ranges_of.items():
            visible = visible_entries(entry, found, source)
            count_stmt = select(func.count()).select_from(entry.join(visible, visible.c.entry_id == entry.c.entry_id))
            fetch_stmt = select(entry.c.entry_id).join(visible, visible.c.entry_id == entry.c.entry_id)
            counted = await time_statement(storage, count_stmt, args.reps, args.cap, scalar=True)
            fetched = await time_statement(storage, fetch_stmt, args.reps, args.cap, scalar=False)
            got = fetched.pop("answer")
            data["join"][label] = {"count": counted, "fetch": fetched | {"rows": None if got is None else len(got)}}
            log(f"- {label}: count {counted} fetch {data['join'][label]['fetch']}")
            if label == "ordinary":
                data["join"][label]["plan"] = await plan_of(storage, count_stmt)
                ordinary_visible = got

        # Recall: the ordinary caller's join against Rights.admits on a sample and FastAdmits on every row.
        log("\n## 3b. recall of the ordinary caller's join")
        async with host.session_factory() as session:
            stored = (await session.execute(select(entry.c.entry_id, entry.c.path, entry.c.owner_id))).all()
        rights = resolutions["ordinary"].read
        fast = FastAdmits(rights)
        rng = random.Random(7)
        sample = rng.sample(stored, min(SAMPLE_ROWS, len(stored)))
        sample += [row for row in stored if "-x" in row.path or row.path.startswith(home_of(ORDINARY))]
        t0 = time.perf_counter()
        agree = sum(1 for row in sample if fast(row.path, row.owner_id) == rights.admits(row.path, row.owner_id))
        sample_s = time.perf_counter() - t0
        exact = {row.entry_id for row in stored if fast(row.path, row.owner_id)}
        recall: dict[str, Any] = {
            "sample_rows": len(sample), "oracle_agrees_with_admits": agree == len(sample),
            "admits_sample_s": round(sample_s, 2), "exact_visible": len(exact), "stored": len(stored),
        }
        if ordinary_visible is not None:
            got_set = set(ordinary_visible)
            recall |= {"join_rows": len(got_set), "recall": round(len(got_set & exact) / len(exact), 4), "extra": len(got_set - exact)}
        data["recall"] = recall
        log(f"- {recall}")

        # 4. The clause fan.
        log("\n## 4. clause fan (visibility_clauses)")
        data["fan"] = {}
        for label in ("ordinary", "pair", "anonymous"):
            f = await measure_fan(storage, resolutions[label].read, 1, args.cap)
            data["fan"][label] = f
            log(f"- {label}: clauses={f.get('clauses')} build={f.get('build_ms')}ms first={f.get('per_clause', [{}])[0]}")
        if args.sweep:
            ladder = [500, 900, 990, 1_000, 1_010, 1_100, 2_000] if args.engine == "sqlite" else [1_000, 2_000, 5_000, 10_000, 16_000, 16_383, 16_400, 20_000, 32_000]
            data["ladder"] = await hole_ladder(storage, ladder, args.cap)
            for step in data["ladder"]:
                log(f"- ladder {step}")

        # 5. End to end.
        log("\n## 5. end to end (one subprocess per call; cold = first call, warm = second)")
        data["e2e"] = {}
        for label in args.e2e_callers.split(","):
            data["e2e"][label] = {}
            for verb in E2E_VERBS:
                r = run_e2e(args.engine, args.url, ns, args.n, args.files_per_home, args.files_per_shared, label, verb, args.e2e_cap)
                data["e2e"][label][verb] = r
                log(f"- {label} {verb}: {r}")

        # 6. Churn.
        log("\n## 6. cache churn")
        data["churn"] = await measure_churn(storage, world, 20)
        log(f"- {data['churn']}")

        # 7. Memory.
        log("\n## 7. memory of one cached Resolution (ordinary)")
        res = resolutions["ordinary"]
        before = deep_size(res)
        with_ranges = deep_size(res) + deep_size(ranges_of["ordinary"])
        data["memory"] = {"resolution_bytes": before, "with_read_ranges_bytes": with_ranges, "x256_cache_mb": round(with_ranges * 256 / 1e6, 1)}
        log(f"- {data['memory']}")

        # 8. admits per row.
        log("\n## 8. Rights.admits per row (ordinary)")
        data["admits"] = measure_admits(res.read, world, ORDINARY)
        log(f"- {data['admits']}")
        if args.sweep:
            data["meet_ladder"] = meet_ladder(args.cap)
            log(f"- meet ladder: {data['meet_ladder']}")
    finally:
        if not args.keep:
            md = storage._host.tables.entry.metadata  # noqa: SLF001
            async with storage._host.engine.begin() as conn:  # noqa: SLF001
                await conn.run_sync(md.drop_all)
        await storage.close()
        if args.engine == "sqlite" and not args.keep:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(os.path.join(SCRATCH, f"{ns}.sqlite{suffix}"))
                except FileNotFoundError:
                    pass
    data["wall_s"] = round(time.perf_counter() - started, 1)
    log(f"\nTotal wall time {data['wall_s']}s.")
    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    stem = os.path.join(HERE, "runs", f"{args.engine}-{args.n}")
    with open(stem + ".json", "w") as f:
        json.dump(data, f, indent=1, default=str)
    with open(stem + ".md", "w") as f:
        f.write(render(data))
    print(f"→ {stem}.md", flush=True)


def render(d: dict[str, Any]) -> str:
    out = [f"# {d['engine']} — N = {d['n']:,}", "", f"World: {d['world']}", f"Load: {d['load']}", ""]
    out += ["## 1. Resolution (ms)", "", "| caller | cold resolve_authority | warm hit | pure resolve(read) | everyone_arms | rows read | read arms | holes | owner arms |", "|---|---|---|---|---|---|---|---|---|"]
    for k, r in d["resolve"].items():
        out.append(f"| {k} | {r['cold_ms']} | {r['warm_hit_ms']} | {r.get('pure_resolve_read_ms', '—')} | {r.get('everyone_arms_ms', '—')} | {r.get('rows_read', '—')} | {r['read_arms']} | {r['read_holes']} | {r['owner_arms']} |")
    out += ["", "## 2. ranges()/pieces (read rights)", "", "| caller | shipped pieces ms | linear pieces ms | equal | points | opens | owner pieces | bind bytes |", "|---|---|---|---|---|---|---|---|"]
    for k, p in d["pieces"].items():
        out.append(f"| {k} | {p['shipped_ms']} | {p['fast_ms']} | {p['fast_equals_shipped']} | {p['points']} | {p['opens']} | {p['owner_pieces']} | {p['bind_bytes']:,} |")
    out += ["", "## 3. Range join (visible_entries)", "", "| caller | count cold ms | count warm ms | count | fetch cold ms | fetch warm ms | rows |", "|---|---|---|---|---|---|---|"]
    for k, j in d["join"].items():
        c, f = j["count"], j["fetch"]
        out.append(f"| {k} | {c.get('cold_ms')} | {c.get('warm_ms')} | {c.get('answer', c.get('error'))} | {f.get('cold_ms')} | {f.get('warm_ms')} | {f.get('rows', f.get('error'))} |")
    out += ["", f"Recall (ordinary): {d['recall']}", "", "Plan of the ordinary caller's count statement:", "", "```", d["join"].get("ordinary", {}).get("plan", "—"), "```"]
    out += ["", "## 4. Clause fan (visibility_clauses)", "", "| caller | clauses | build ms | clause binds | clause terms | cold ms | warm ms | result |", "|---|---|---|---|---|---|---|---|"]
    for k, f in d["fan"].items():
        for c in f.get("per_clause", [])[:3]:
            out.append(f"| {k} | {f['clauses']} | {f['build_ms']} | {c['binds']} | {c['terms']} | {c.get('cold_ms')} | {c.get('warm_ms')} | {c.get('answer', c.get('error'))} |")
    if "ladder" in d:
        out += ["", "Hole ladder (one root arm with H holes, one clause, count statement):", "", "| holes | binds | cold ms | warm ms | result |", "|---|---|---|---|---|"]
        for s in d["ladder"]:
            out.append(f"| {s['holes']} | {s['binds']} | {s.get('cold_ms')} | {s.get('warm_ms')} | {s.get('answer', s.get('error'))} |")
    out += ["", "## 5. End to end through DatabaseStorage (ms; cold = first call in a fresh process, warm = second)", "", "| caller | verb | cold ms | warm ms | rows | note |", "|---|---|---|---|---|---|"]
    for k, verbs in d["e2e"].items():
        for verb, r in verbs.items():
            if "cold" in r:
                note = "; ".join(r["cold"]["errors"])
                out.append(f"| {k} | {verb} | {r['cold']['ms']} | {r['warm']['ms']} | {r['cold']['rows']} | {note} |")
            else:
                out.append(f"| {k} | {verb} | — | — | — | {r} |")
    out += ["", f"## 6. Cache churn: {d['churn']}", "", f"## 7. Memory: {d['memory']}", "", "## 8. Rights.admits per row (ordinary)", ""]
    for k, a in d["admits"].items():
        out.append(f"- {k}: {a['us']} µs (admitted={a['admitted']})")
    if "meet_ladder" in d:
        out += ["", f"Meet ladder (out of world): {d['meet_ladder']}"]
    out += ["", f"Total wall time {d['wall_s']}s."]
    return "\n".join(out) + "\n"


def results() -> str:
    """``results.md`` from every ``runs/<engine>-<N>.json``: one table per measurement, N and engine on every row."""
    runs = []
    for name in sorted(os.listdir(os.path.join(HERE, "runs"))):
        if name.endswith(".json") and "-ladder" not in name:
            with open(os.path.join(HERE, "runs", name)) as f:
                runs.append(json.load(f))
    runs.sort(key=lambda d: (d["engine"], d["n"]))
    out = ["# Results — every number with its engine and N", "",
           "Medians of 3 warm runs unless a cell says otherwise; cold = first run on a fresh session or process.",
           "`pieces` and `admits` are pure Python on the event loop. The 100k world has 2 files per home (see README).", ""]
    out += ["## World and load", "", "| engine | N | entries | grant rows | memberships | load entries s | load grants s |", "|---|---|---|---|---|---|---|"]
    for d in runs:
        w, l = d["world"], d["load"]
        out.append(f"| {d['engine']} | {d['n']:,} | {w['entries']:,} | {w['grant_rows']:,} | {w['memberships']:,} | {l['entries_s']:.1f} | {l['grants_s']:.1f} |")
    out += ["", "## 1. resolve_authority (ms)", "", "| engine | N | caller | cold (rows + 2×resolve) | warm cache hit | pure resolve(read) | _everyone_arms | rows read | holes | owner arms |", "|---|---|---|---|---|---|---|---|---|---|"]
    for d in runs:
        for k, r in d["resolve"].items():
            out.append(f"| {d['engine']} | {d['n']:,} | {k} | {r['cold_ms']} | {r['warm_hit_ms']} | {r.get('pure_resolve_read_ms', '—')} | {r.get('everyone_arms_ms', '—')} | {r.get('rows_read', '—')} | {r['read_holes']:,} | {r['owner_arms']} |")
    out += ["", "## 2. Rights.ranges() / pieces() (read rights)", "", "| engine | N | caller | shipped pieces ms | study linear ms | equal | points | opens | owner pieces | JSON bind bytes |", "|---|---|---|---|---|---|---|---|---|---|"]
    for d in runs:
        for k, p in d["pieces"].items():
            out.append(f"| {d['engine']} | {d['n']:,} | {k} | {p['shipped_ms']} | {p['fast_ms']} | {p['fast_equals_shipped']} | {p['points']:,} | {p['opens']:,} | {p['owner_pieces']} | {p['bind_bytes']:,} |")
    out += ["", "## 3. Range join — visible_entries (ms)", "", "| engine | N | caller | count cold | count warm | visible rows | fetch cold | fetch warm |", "|---|---|---|---|---|---|---|---|"]
    for d in runs:
        for k, j in d["join"].items():
            c, f = j["count"], j["fetch"]
            out.append(f"| {d['engine']} | {d['n']:,} | {k} | {c.get('cold_ms')} | {c.get('warm_ms')} | {c.get('answer', c.get('error'))} | {f.get('cold_ms')} | {f.get('warm_ms')} |")
    out += ["", "## 3b. Recall of the ordinary caller's join", "", "| engine | N | stored rows | exact visible | join rows | recall | extra | admits agrees with oracle on sample | sample rows | admits over sample s |", "|---|---|---|---|---|---|---|---|---|---|"]
    for d in runs:
        r = d["recall"]
        out.append(f"| {d['engine']} | {d['n']:,} | {r['stored']:,} | {r['exact_visible']:,} | {r.get('join_rows')} | {r.get('recall')} | {r.get('extra')} | {r['oracle_agrees_with_admits']} | {r['sample_rows']} | {r['admits_sample_s']} |")
    out += ["", "## 4. Clause fan — visibility_clauses (first clause; ms)", "", "| engine | N | caller | clauses | build ms | binds | terms | cold | warm | result |", "|---|---|---|---|---|---|---|---|---|---|"]
    for d in runs:
        for k, f in d["fan"].items():
            c = f["per_clause"][0]
            out.append(f"| {d['engine']} | {d['n']:,} | {k} | {f['clauses']} | {f['build_ms']} | {c['binds']:,} | {c['terms']:,} | {c.get('cold_ms')} | {c.get('warm_ms')} | {c.get('answer', c.get('error'))} |")
    out += ["", "### Hole ladder (one root arm with H holes, one clause, count over the N=1,000 table)", "", "| engine | holes | binds | cold ms | warm ms | result |", "|---|---|---|---|---|---|"]
    for d in runs:
        for s_ in d.get("ladder", []):
            out.append(f"| {d['engine']} | {s_['holes']:,} | {s_['binds']:,} | {s_.get('cold_ms')} | {s_.get('warm_ms')} | {s_.get('answer', s_.get('error'))} |")
    ladder = os.path.join(HERE, "runs", "postgres-ladder.json")
    if os.path.exists(ladder):
        with open(ladder) as f:
            for s_ in json.load(f).get("ladder", []):
                out.append(f"| postgres | {s_['holes']:,} | {s_['binds']:,} | {s_.get('cold_ms')} | {s_.get('warm_ms')} | {s_.get('answer', s_.get('error'))} |")
    out += ["", "## 5. End to end through DatabaseStorage (ms; one fresh process per verb, cold = first call, warm = second)", "", "| engine | N | caller | verb | cold | warm | rows | note |", "|---|---|---|---|---|---|---|---|"]
    for d in runs:
        for k, verbs in d["e2e"].items():
            for verb, r in verbs.items():
                if "cold" in r:
                    out.append(f"| {d['engine']} | {d['n']:,} | {k} | {verb} | {r['cold']['ms']} | {r['warm']['ms']} | {r['cold']['rows']:,} | {'; '.join(r['cold']['errors'])} |")
                else:
                    out.append(f"| {d['engine']} | {d['n']:,} | {k} | {verb} | — | — | — | {r} |")
    out += ["", "## 6. Cache churn (20 callers resolved, one grant written, 20 resolved again)", "", "| engine | N | cached before | misses after one grant | recompute s for 20 callers | per caller s | if all N read once (CPU s) |", "|---|---|---|---|---|---|---|"]
    for d in runs:
        c = d["churn"]
        per = c["recompute_s_for_callers"] / c["callers"]
        out.append(f"| {d['engine']} | {d['n']:,} | {c['cached_before']} | {c['misses_after_one_grant']} | {c['recompute_s_for_callers']} | {per:.3f} | {per * d['n']:,.0f} |")
    out += ["", "## 7. Memory of one cached Resolution (ordinary caller)", "", "| engine | N | Resolution bytes | plus read ranges bytes | 256-entry cache MB |", "|---|---|---|---|---|"]
    for d in runs:
        m = d["memory"]
        out.append(f"| {d['engine']} | {d['n']:,} | {m['resolution_bytes']:,} | {m['with_read_ranges_bytes']:,} | {m['x256_cache_mb']:,} |")
    out += ["", "## 8. Rights.admits per row (ordinary caller; µs)", "", "| engine | N | own home file | shared file (root arm) | hidden home file | trap file |", "|---|---|---|---|---|---|"]
    for d in runs:
        a = d["admits"]
        out.append(f"| {d['engine']} | {d['n']:,} | {a['own home file']['us']} | {a['shared file (root arm)']['us']} | {a["another user's home file (hidden)"]['us']} | {a['trap file']['us']} |")
    for d in runs:
        if "meet_ladder" in d:
            out += ["", f"## Meet ladder (out of world, pure Python; engine-independent, recorded on {d['engine']})", "", "| group grants | single-subject resolve ms | pair resolve ms |", "|---|---|---|"]
            out += [f"| {s_['grants']:,} | {s_['single_ms']} | {s_['pair_ms']} |" for s_ in d["meet_ladder"]]
            break
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="sqlite", choices=["sqlite", "postgres"])
    ap.add_argument("--url", default=os.environ.get("VFS_TEST_POSTGRES_URL"))
    ap.add_argument("--n", type=int, default=1_000)
    ap.add_argument("--files-per-home", type=int, default=20)
    ap.add_argument("--files-per-shared", type=int, default=200)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--cap", type=float, default=60.0, help="seconds per capped step")
    ap.add_argument("--e2e-cap", type=float, default=90.0, help="seconds per end-to-end subprocess")
    ap.add_argument("--sweep", action="store_true", help="also run the hole ladder and the meet ladder")
    ap.add_argument("--e2e-callers", default="ordinary,pair,anonymous,system")
    ap.add_argument("--ladder-only", action="store_true", help="only the hole ladder, on the N given")
    ap.add_argument("--results", action="store_true", help="assemble results.md from runs/*.json")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--e2e", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--ns", help=argparse.SUPPRESS)
    ap.add_argument("--caller", help=argparse.SUPPRESS)
    ap.add_argument("--verb", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.results:
        with open(os.path.join(HERE, "results.md"), "w") as f:
            f.write(results())
        print("→ results.md")
    elif a.e2e:
        asyncio.run(e2e_child(a))
    else:
        asyncio.run(run(a))
